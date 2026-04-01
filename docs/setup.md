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
ollama pull qwen2.5vl:7b
ollama pull nomic-embed-text:latest
```

- `qwen2.5:7b` — LLM inference and memory extraction
- `qwen2.5vl:7b` — vision model
- `nomic-embed-text` — embeddings

## 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and fill in the required values:

| Variable | Purpose |
|---|---|
| `OLLAMA_VISION_MODEL` | Vision model (default: `qwen2.5vl:7b`) |
| `BESZEL_TOKEN` | Token for Beszel monitoring agent (see Beszel first-time setup in `docker-compose.yml`) |
| `BESZEL_KEY` | Key for Beszel monitoring agent |

## 4. Start services

```bash
docker compose up -d
```

This starts all core services:

- **Ollama** — LLM inference (port 11434)
- **Open WebUI** — chat interface (port 3000)
- **Qdrant** — vector storage (ports 6333/6334)
- **Beszel** — server/container monitoring (port 8090)

Verify services are running:

```bash
curl http://localhost:11434/api/tags    # Ollama
curl http://localhost:6333/healthz     # Qdrant
```

The Qdrant dashboard is available at http://localhost:6333/dashboard.

## 5. Set up Python environment (optional)

For local memory layer development and testing:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r src/agent-memory-layer/requirements.txt
```

## Smoke tests

### Memory layer

Run from the `src/agent-memory-layer/` directory:

```bash
cd src/agent-memory-layer
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
