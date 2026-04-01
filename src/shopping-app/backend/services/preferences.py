import os
import uuid

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
COLLECTION = "shopping_preferences"
VECTOR_SIZE = 768

client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)


def ensure_collection():
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION not in collections:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )


async def embed_text(text: str) -> list[float]:
    async with httpx.AsyncClient() as http:
        resp = await http.post(
            f"{OLLAMA_BASE_URL}/api/embed",
            json={"model": "nomic-embed-text", "input": text},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.json()["embeddings"][0]


async def store_preference(key: str, value: str):
    ensure_collection()
    text = f"{key}: {value}"
    vector = await embed_text(text)
    point = PointStruct(
        id=str(uuid.uuid4()),
        vector=vector,
        payload={"user_id": "danielle", "key": key, "value": value},
    )
    client.upsert(collection_name=COLLECTION, points=[point])


async def recall_preferences(query: str, limit: int = 5) -> list[dict]:
    ensure_collection()
    try:
        vector = await embed_text(query)
        results = client.query_points(
            collection_name=COLLECTION,
            query=vector,
            limit=limit,
        )
        return [
            {"key": p.payload["key"], "value": p.payload["value"]}
            for p in results.points
        ]
    except Exception:
        return []
