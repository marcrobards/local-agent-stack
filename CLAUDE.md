# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

A self-hosted AI agent platform running mostly locally via Ollama. Cloud APIs are available for agent stages that require them; everything else runs on local hardware. The platform is layered so each layer is independently useful and loosely coupled.

**Current implementation status:**
- ✅ Ollama — local LLM inference (qwen2.5:7b + qwen2.5vl:7b vision + nomic-embed-text embeddings)
- ✅ Memory layer — persistent shared memory (mem0 + Qdrant)
- ✅ Web interface — Open WebUI chat interface
- ✅ Monitoring — Beszel server + container monitoring

## Common Commands

**Start infrastructure:**
```bash
docker compose up -d                          # Ollama, Open-WebUI, Qdrant
docker compose --profile tools up -d         # Also includes memory-chat tool
```

**Python environment:**
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r src/agent-memory-layer/requirements.txt
```

**Run tests:**
```bash
python -m tests.smoke_test                   # End-to-end integration test (write, search, cross-agent read)
```

**Interactive memory testing:**
```bash
docker compose --profile tools run --rm memory-chat
```

**Health checks:**
```bash
curl http://localhost:11434/api/tags          # Ollama
curl http://localhost:6333/healthz            # Qdrant
```

**Deploy to remote server (lenovo-laptop):**
```bash
./deploy
```

## Architecture

Agents import a Python singleton `mem` for memory access — this was a deliberate simplicity choice (easy to wrap in HTTP later if needed).

```
User (Open WebUI)
  → Agent Pipeline (Open WebUI Pipelines)

Memory layer (available to all agents):
  → from memory import mem
    → mem.add() / mem.search()
      → mem0 library
        → qwen2.5:7b (Ollama) — fact extraction
        → nomic-embed-text (Ollama) — vectorization
        → Qdrant — vector storage/retrieval
```

**Memory scoping via `user_id`:**
- `user_id="agent_1"` — private to that agent
- `user_id="shared"` — readable by all agents
- `user_id="session_<timestamp>"` — ephemeral

**Key source files:**
- `src/agent-memory-layer/memory/client.py` — `mem` singleton with Ollama timeout patching
- `src/agent-memory-layer/memory/config.py` — mem0 config built from environment variables
- `src/agent-memory-layer/memory/__init__.py` — exports `mem` for agent imports
- `src/agent-memory-layer/tests/smoke_test.py` — integration test
- `docker-compose.yml` — service orchestration (Ollama 11434, Open WebUI 3000, Qdrant 6333/6334, Beszel 8090)

## Configuration

Runtime config via environment variables (see `.env.example`). The `config.py` constructs the mem0 config dict from these — defaults work for local development with no `.env` file needed.

## Documentation

- `docs/architecture.md` — layered architecture diagram and data flow
- `docs/decisions.md` — why each component was chosen (read before swapping components)
- `docs/memory-api.md` — API reference for using `mem` in agents
- `docs/setup.md` — installation and troubleshooting
