#!/usr/bin/env python3

import argparse
import concurrent.futures
import hashlib
import json
import os
import sys
import time
from typing import List, Dict

import psycopg2
from psycopg2.extras import execute_batch
from tqdm import tqdm
import requests

# -----------------------------
# CONFIG
# -----------------------------

EMBEDDING_DIM = 768
DEFAULT_CHUNK_SIZE = 800
DEFAULT_OVERLAP = 120
MAX_WORKERS = min(8, os.cpu_count() or 4)

SCHEMA_VERSION = 1

# -----------------------------
# DATABASE MANAGER
# -----------------------------

class DatabaseManager:
    def __init__(self, dsn: str):
        self.conn = psycopg2.connect(dsn)
        self.conn.autocommit = False
        self.cursor = self.conn.cursor()

    def initialize_schema(self):
        # Extensions
        self.cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")

        # Schema version table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS rag_schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT now()
            );
        """)

        self.cursor.execute("""
            SELECT MAX(version) FROM rag_schema_version;
        """)
        current_version = self.cursor.fetchone()[0] or 0

        if current_version < SCHEMA_VERSION:
            self._apply_migrations(current_version)

        # Core table
        self.cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS document_chunk (
                id TEXT PRIMARY KEY,
                vector vector({EMBEDDING_DIM}),
                collection_name TEXT NOT NULL,
                text TEXT,
                vmetadata JSONB
            );
        """)

        # Indexes (IVFFlat + HNSW)
        self.cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_document_chunk_collection_name
            ON document_chunk (collection_name);
        """)

        self.cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_document_chunk_vector_ivfflat
            ON document_chunk
            USING ivfflat (vector vector_cosine_ops)
            WITH (lists = 100);
        """)

        self.cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_document_chunk_vector_hnsw
            ON document_chunk
            USING hnsw (vector vector_cosine_ops);
        """)

        self.conn.commit()

    def _apply_migrations(self, from_version: int):
        # Placeholder for future migrations
        self.cursor.execute(
            "INSERT INTO rag_schema_version (version) VALUES (%s)",
            (SCHEMA_VERSION,)
        )
        self.conn.commit()

    def insert_chunks(self, rows: List[tuple]):
        sql = """
            INSERT INTO document_chunk (id, vector, collection_name, text, vmetadata)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING;
        """
        execute_batch(self.cursor, sql, rows, page_size=100)
        self.conn.commit()

    def similarity_search(self, query_vector, collection, limit=5):
        # Convert Python list to pgvector literal
        query_vector_str = f"'[{','.join(map(str, query_vector))}]'::vector"

        self.cursor.execute(f"""
            SELECT text, vmetadata, vector <-> {query_vector_str} AS distance
            FROM document_chunk
            WHERE collection_name = %s
            ORDER BY vector <-> {query_vector_str}
            LIMIT %s;
        """, (query_vector, collection, limit))
        return self.cursor.fetchall()

# -----------------------------
# CHUNKING
# -----------------------------

def auto_chunk(text: str, target_size=DEFAULT_CHUNK_SIZE, overlap=DEFAULT_OVERLAP):
    words = text.split()
    # Auto-adjust chunk size for very short or very long documents
    if len(words) < target_size:
        target_size = max(50, len(words) // 2)
        overlap = max(10, target_size // 10)
    elif len(words) > 5000:
        target_size = min(target_size * 2, 2000)

    chunks = []
    start = 0

    while start < len(words):
        end = start + target_size
        chunk_words = words[start:end]
        chunks.append(" ".join(chunk_words))
        start = end - overlap

    return chunks

# -----------------------------
# EMBEDDING
# -----------------------------

class Embedder:
    def __init__(self, model="nomic-embed-text", base_url="http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def embed(self, texts):
        if isinstance(texts, str):
            texts = [texts]

        vectors = []
        for text in texts:
            r = requests.post(
                f"{self.base_url}/api/embeddings",
                json={
                    "model": self.model,
                    "prompt": text
                },
                timeout=60
            )
            r.raise_for_status()
            vectors.append(r.json()["embedding"])
        return vectors

    def embed_batch(self, texts):
        # same as embed, kept for compatibility
        return self.embed(texts)

# -----------------------------
# INGESTION
# -----------------------------

def hash_id(text: str, collection: str):
    return hashlib.sha1(f"{collection}:{text}".encode()).hexdigest()

def process_file(embedder: Embedder, chunks: List[str], file: str, collection: str):
    vectors = embedder.embed(chunks)
    rows = []

    # Derive product from folder structure
    rel_path = os.path.relpath(file, base_folder)  # relative to base folder
    product = rel_path.split(os.sep)[0]  # first folder = product

    for chunk, vector in zip(chunks, vectors):
        rows.append((
            hash_id(chunk, collection),
            vector,
            collection,
            chunk,
            json.dumps({
                "source": os.path.basename(file),
                "product": product
            })
        ))
    return rows

def ingest_folder(db: DatabaseManager, embedder: Embedder, folder: str, collection: str):
    files = [
        os.path.join(root, f)
        for root, _, filenames in os.walk(folder)
        for f in filenames
        if f.lower().endswith((".txt", ".md"))
    ]

    rows = []

    with concurrent.futures.ThreadPoolExecutor(MAX_WORKERS) as executor:
        futures = []

        for file in files:
            with open(file, "r", encoding="utf-8") as f:
                text = f.read()

            chunks = auto_chunk(text)

            futures.append(
                executor.submit(process_file, embedder, chunks, file, collection, folder)
            )

        for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures)):
            rows.extend(future.result())

    db.insert_chunks(rows)

# -----------------------------
# VERIFY CLI WITH SUMMARY
# -----------------------------
import requests

def verify_rag(db: DatabaseManager, embedder: Embedder, collection: str, top_k=5):
    """
    Interactive query tool: retrieves top matching chunks from DB
    and asks Ollama to generate a concise executive summary.
    """
    print("\nEnter a query (Ctrl+C to exit):\n")
    while True:
        query = input("> ").strip()
        if not query:
            continue

        # Step 1: Embed the query
        vector = embedder.embed([query])[0]  # returns a list

        # Step 2: Retrieve top chunks
        results = db.similarity_search(vector, collection, limit=top_k)

        if not results:
            print("No relevant documents found.\n")
            continue

        # Step 3: Concatenate retrieved text
        top_chunks = [text for text, meta, dist in results]
        combined_text = "\n\n".join(top_chunks)

        # Step 4: Generate summary using Ollama
        prompt = (
            f"Provide a concise, readable executive summary of the following documents "
            f"(retain key details, ignore links and headers):\n\n{combined_text}"
        )

        try:
            r = requests.post(
                "http://localhost:11434/api/completions",
                json={
                    "model": "llama3.1-rag",
                    "prompt": prompt,
                    "temperature": 0.3,
                    "max_tokens": 500
                },
                timeout=120
            )
            r.raise_for_status()
            summary = r.json()["completion"].strip()
            print("\n--- EXECUTIVE SUMMARY ---\n")
            print(summary)
            print("\n-------------------------\n")
        except requests.RequestException as e:
            print(f"Error generating summary: {e}\n")

# -----------------------------
# MAIN
# -----------------------------

def main():
    parser = argparse.ArgumentParser(description="RAG Processor")
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--folder", help="Folder to ingest")
    parser.add_argument("--collection", required=True)
    parser.add_argument("--version", default="v1")
    parser.add_argument("--verify", action="store_true")

    args = parser.parse_args()

    collection = f"{args.collection}@{args.version}"

    db = DatabaseManager(args.dsn)
    db.initialize_schema()

    embedder = Embedder()

    if args.folder:
        ingest_folder(db, embedder, args.folder, collection)

    if args.verify:
        verify_rag(db, embedder, collection)

if __name__ == "__main__":
    main()