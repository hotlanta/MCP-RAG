import psycopg2
import requests

# --------------------------
# Configuration
# --------------------------
DB_DSN = "postgresql://rag_user:mysecretpassword@localhost:5432/knowledge_db"
OLLAMA_EMBED_URL = "http://localhost:11434/api/embeddings"
MODEL_NAME = "nomic-embed-text"
PROMPT = "Hello world"  # Your test query
TOP_K = 3

# --------------------------
# Step 1: Get embedding
# --------------------------
response = requests.post(
    OLLAMA_EMBED_URL,
    json={"model": MODEL_NAME, "prompt": PROMPT}
)

response.raise_for_status()
hello_embedding = response.json()["embedding"]  # full embedding list
vector_length = len(hello_embedding)
print(f"Embedding dimension: {vector_length}")

# Convert to Postgres pgvector ARRAY syntax
vector_str = "ARRAY[" + ",".join(map(str, hello_embedding)) + "]::vector"

# --------------------------
# Step 2: Connect to DB
# --------------------------
conn = psycopg2.connect(DB_DSN)
cur = conn.cursor()

# --------------------------
# Step 3: Run nearest-neighbor query
# --------------------------
query = f"""
SELECT id, text, vector <=> {vector_str} AS distance
FROM document_chunk
ORDER BY distance
LIMIT {TOP_K};
"""

cur.execute(query)
results = cur.fetchall()

# --------------------------
# Step 4: Print results
# --------------------------
print(f"\nTop {TOP_K} closest document chunks to: '{PROMPT}'\n")
for row in results:
    doc_id, text, distance = row
    snippet = text[:200].replace("\n", " ") + "..."  # show first 200 chars
    print(f"ID: {doc_id}\nDistance: {distance}\nText snippet: {snippet}\n---")

# ----
