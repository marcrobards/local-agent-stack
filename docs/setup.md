# Setup Guide

## Prerequisites

- Linux (Ubuntu 22.04+ recommended)
- Docker and Docker Compose installed and running
- Python 3.12+
- Ollama installed and running (`ollama serve`)

## 1. Clone the repo

```bash
git clone https://github.com/<your-username>/local-agent-stack.git
cd local-agent-stack
```

## 2. Pull required Ollama models

```bash
ollama pull qwen2.5:7b
ollama pull nomic-embed-text:latest
```

Both are required. `qwen2.5:7b` handles LLM inference and memory extraction. `nomic-embed-text` handles embeddings.

## 3. Configure environment

```bash
cp .env.example .env
```

The defaults in `.env.example` work out of the box for a local setup. Edit only if your Ollama port or Qdrant port differ from the defaults.

## 4. Start Qdrant

```bash
docker compose up -d
```

Verify it's running:

```bash
curl http://localhost:6333/healthz
# expected: {"title":"qdrant - vector search engine"}
```

The Qdrant dashboard is available at http://localhost:6333/dashboard.

## 5. Set up Python environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 6. Run the smoke test

```bash
python -m tests.smoke_test
```

Expected output:

```
=== Memory Layer Smoke Test ===

1. Writing long-term fact for agent_1...
2. Writing episodic memory for agent_1...
3. Writing shared memory for all agents...

4. All memories for agent_1:
   [long_term] ...
   [episodic] ...

5. Search for 'database' in agent_1 memories:
   (score=0.xxx) ...

6. agent_2 reading shared memory:
   ...

=== All checks passed ===
```

Note: writes are slow (5–15 seconds each) because mem0 calls the LLM to extract facts on every `mem.add()`. This is expected.

## Troubleshooting

### Smoke test hangs

Check that both services are healthy:

```bash
curl http://localhost:11434/api/tags    # Ollama
curl http://localhost:6333/healthz     # Qdrant
```

If Qdrant reports a version compatibility warning, upgrade the server:

```bash
docker compose down
# edit docker-compose.yml: change image to qdrant/qdrant:latest
docker compose up -d
```

### Qdrant version mismatch warning

The `qdrant-client` Python library and the Qdrant server must be within one minor version of each other. Always use `qdrant/qdrant:latest` in `docker-compose.yml` to stay current with the client.

### Slow writes

This is normal. Each `mem.add()` call invokes qwen2.5:7b for memory extraction. To speed up:

- Switch `OLLAMA_LLM_MODEL` in `.env` to `llama3.2:3b` for extraction (faster, equally capable for this task)
- Batch writes — call `mem.add()` at end of session, not after every message

## Stopping the stack

```bash
docker compose down
```

Qdrant data is persisted in the `qdrant_data` Docker volume and will survive restarts.
