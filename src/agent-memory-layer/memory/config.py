import os
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", 120))

MEM0_CONFIG = {
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "collection_name": os.getenv("QDRANT_COLLECTION", "agent_memory"),
            "host": os.getenv("QDRANT_HOST", "localhost"),
            "port": int(os.getenv("QDRANT_PORT", 6333)),
            "embedding_model_dims": int(os.getenv("OLLAMA_EMBED_DIMS", 768)),
        },
    },
    "llm": {
        "provider": "ollama",
        "config": {
            "model": os.getenv("OLLAMA_LLM_MODEL", "qwen2.5:7b"),
            "temperature": 0,
            "max_tokens": 2000,
            "ollama_base_url": OLLAMA_BASE_URL,
        },
    },
    "embedder": {
        "provider": "ollama",
        "config": {
            "model": os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text:latest"),
            "ollama_base_url": OLLAMA_BASE_URL,
        },
    },
}
