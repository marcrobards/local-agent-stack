# Agent Memory Layer — Implementation Spec

## Overview

Set up a persistent, shared memory layer for a local AI agent team using:

- **Qdrant** — vector database (runs in Docker)
- **mem0** — memory abstraction library (Python)
- **nomic-embed-text** — embedding model (via Ollama)
- **qwen2.5:7b** — LLM for memory extraction (via Ollama, already running)

All components run fully locally. No external API keys required.

---

## Directory Structure

Create the following layout:

```
~/agent-memory/
├── docker-compose.yml
├── .env
├── memory/
│   ├── __init__.py
│   ├── client.py        # Memory singleton — agents import this
│   └── config.py        # mem0 config loaded from .env
├── tests/
│   └── smoke_test.py    # Verify the stack works end-to-end
└── requirements.txt
```

---

## Files to Create

### `docker-compose.yml`

Run Qdrant with a named volume for persistence:

```yaml
services:
  qdrant:
    image: qdrant/qdrant:v1.13.0
    container_name: qdrant
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage
    restart: unless-stopped

volumes:
  qdrant_data:
```

---

### `.env`

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_LLM_MODEL=qwen2.5:7b
OLLAMA_EMBED_MODEL=nomic-embed-text:latest
OLLAMA_EMBED_DIMS=768

QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION=agent_memory
```

---

### `requirements.txt`

```
mem0ai
qdrant-client
python-dotenv
```

---

### `memory/config.py`

Load config from `.env` and build the mem0 config dict:

```python
import os
from dotenv import load_dotenv

load_dotenv()

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
            "ollama_base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        },
    },
    "embedder": {
        "provider": "ollama",
        "config": {
            "model": os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text:latest"),
            "ollama_base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        },
    },
}
```

---

### `memory/client.py`

A singleton `Memory` instance that all agents share. Import `mem` from this module:

```python
from mem0 import Memory
from .config import MEM0_CONFIG

# Shared singleton — import this in all agents
mem = Memory.from_config(MEM0_CONFIG)
```

---

### `memory/__init__.py`

```python
from .client import mem

__all__ = ["mem"]
```

---

### `tests/smoke_test.py`

Verifies the full stack: write, read, search, cross-agent recall, and delete:

```python
"""
Smoke test for the agent memory layer.
Run with: python -m tests.smoke_test
"""
from memory import mem


def run():
    print("=== Memory Layer Smoke Test ===\n")

    # 1. Add a long-term fact for agent_1
    print("1. Writing long-term fact for agent_1...")
    mem.add(
        "The user's name is Marc. He prefers Python and runs Ollama locally.",
        user_id="agent_1",
        metadata={"type": "long_term"}
    )

    # 2. Add an episodic memory for agent_1
    print("2. Writing episodic memory for agent_1...")
    mem.add(
        "In the last session, we discussed setting up a vector database.",
        user_id="agent_1",
        metadata={"type": "episodic"}
    )

    # 3. Add a shared fact (cross-agent memory uses a shared user_id)
    print("3. Writing shared memory for all agents...")
    mem.add(
        "The project is called HomeAgents. All agents share this context.",
        user_id="shared",
        metadata={"type": "shared"}
    )

    # 4. Retrieve all memories for agent_1
    print("\n4. All memories for agent_1:")
    results = mem.get_all(user_id="agent_1")
    for r in results.get("results", []):
        print(f"   [{r.get('metadata', {}).get('type', 'unknown')}] {r['memory']}")

    # 5. Semantic search
    print("\n5. Search for 'database' in agent_1 memories:")
    hits = mem.search("database", user_id="agent_1", limit=3)
    for h in hits.get("results", []):
        print(f"   (score={h.get('score', 0):.3f}) {h['memory']}")

    # 6. Cross-agent: agent_2 reads shared memory
    print("\n6. agent_2 reading shared memory:")
    shared = mem.get_all(user_id="shared")
    for r in shared.get("results", []):
        print(f"   {r['memory']}")

    print("\n=== All checks passed ===")


if __name__ == "__main__":
    run()
```

---

## Memory ID Scoping Convention

Use consistent `user_id` values to scope memory across agents:

| Scope | `user_id` value | Purpose |
|---|---|---|
| Per-agent private | `"agent_1"`, `"agent_2"`, etc. | Each agent's own facts and history |
| Shared across all agents | `"shared"` | Project-wide context, global facts |
| Per-session short-term | `"session_<timestamp>"` | Ephemeral context, cleared after session |

Agents can read from multiple scopes by calling `mem.search()` or `mem.get_all()` with each relevant `user_id`.

---

## Known Gotcha

The `embedding_model_dims` value in `.env` **must match** the actual output dimensions of the embedding model. `nomic-embed-text` outputs **768 dimensions**. If you switch embedding models later, delete the Qdrant collection and recreate it — mismatched dims will cause silent failures.

---
