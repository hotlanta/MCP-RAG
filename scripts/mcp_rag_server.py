#!/usr/bin/env python3
"""
MCP Server for PostgreSQL RAG System
Provides document search capabilities via MCP protocol
"""

import json
import asyncio
from typing import Any
import psycopg2
import requests
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource

# Configuration
DSN = "postgresql://rag_user:mysecretpassword@localhost:5432/knowledge_db"
OLLAMA_URL = "http://localhost:11434"
EMBEDDING_MODEL = "nomic-embed-text"

# Initialize MCP server
server = Server("rag-search")


def get_embedding(text: str) -> list:
    """Get embedding vector from Ollama"""
    r = requests.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": EMBEDDING_MODEL, "prompt": text},
        timeout=60
    )
    r.raise_for_status()
    return r.json()["embedding"]


def search_documents(query: str, collection: str = "documents@v1", limit: int = 5) -> list:
    """Search for relevant documents in PostgreSQL"""
    conn = psycopg2.connect(DSN)
    cursor = conn.cursor()
    
    try:
        # Get query embedding
        query_vector = get_embedding(query)
        vector_str = f"'[{','.join(map(str, query_vector))}]'::vector"
        
        # Search using vector similarity
        cursor.execute(f"""
            SELECT text, vmetadata, vector <-> {vector_str} AS distance
            FROM document_chunk
            WHERE collection_name = %s
            ORDER BY vector <-> {vector_str}
            LIMIT %s;
        """, (collection, limit))
        
        results = cursor.fetchall()
        
        return [
            {
                "text": text,
                "metadata": metadata,
                "distance": float(distance)
            }
            for text, metadata, distance in results
        ]
    finally:
        cursor.close()
        conn.close()


def list_collections() -> list:
    """List all available document collections"""
    conn = psycopg2.connect(DSN)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT DISTINCT collection_name, COUNT(*) as chunk_count
            FROM document_chunk
            GROUP BY collection_name
            ORDER BY collection_name;
        """)
        
        results = cursor.fetchall()
        
        return [
            {
                "collection": name,
                "chunks": count
            }
            for name, count in results
        ]
    finally:
        cursor.close()
        conn.close()


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List available MCP tools"""
    return [
        Tool(
            name="search_documents",
            description="Search for relevant documents in the RAG knowledge base using semantic search",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query or question to find relevant documents for"
                    },
                    "collection": {
                        "type": "string",
                        "description": "The document collection to search in (default: documents@v1)",
                        "default": "documents@v1"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default: 5)",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 20
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="list_collections",
            description="List all available document collections in the knowledge base",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool execution requests"""
    
    if name == "search_documents":
        query = arguments.get("query")
        collection = arguments.get("collection", "documents@v1")
        limit = arguments.get("limit", 5)
        
        if not query:
            return [TextContent(
                type="text",
                text="Error: No query provided"
            )]
        
        try:
            results = search_documents(query, collection, limit)
            
            if not results:
                return [TextContent(
                    type="text",
                    text=f"No documents found matching: {query}"
                )]
            
            # Format results
            output = f"Found {len(results)} relevant documents for '{query}':\n\n"
            
            for i, result in enumerate(results, 1):
                source = result['metadata'].get('source', 'unknown')
                distance = result['distance']
                text = result['text']
                
                output += f"**Document {i}** (Source: {source}, Similarity: {1-distance:.2%})\n"
                output += f"{text}\n\n"
                output += "---\n\n"
            
            return [TextContent(
                type="text",
                text=output
            )]
            
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"Error searching documents: {str(e)}"
            )]
    
    elif name == "list_collections":
        try:
            collections = list_collections()
            
            if not collections:
                return [TextContent(
                    type="text",
                    text="No collections found in the knowledge base"
                )]
            
            output = "Available document collections:\n\n"
            for coll in collections:
                output += f"- **{coll['collection']}**: {coll['chunks']} chunks\n"
            
            return [TextContent(
                type="text",
                text=output
            )]
            
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"Error listing collections: {str(e)}"
            )]
    
    else:
        return [TextContent(
            type="text",
            text=f"Unknown tool: {name}"
        )]


async def main():
    """Run the MCP server"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="rag-search",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )
        )


if __name__ == "__main__":
    asyncio.run(main())