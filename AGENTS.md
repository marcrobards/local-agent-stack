# AGENTS.md

Instructions for AI agents working in this repository.

## Project Overview

Self-hosted AI agent platform running locally via Ollama. Cloud APIs are available for agent stages that require them; everything else runs on local hardware. Layers are independently useful and loosely coupled.

## Stack

- **LLM inference:** Ollama (qwen2.5:7b, qwen2.5vl:7b vision, nomic-embed-text embeddings)
- **Memory:** mem0 + Qdrant vector DB
- **Pipeline host:** Open WebUI Pipelines
- **Web interface:** Open WebUI
- **Monitoring:** Beszel
- **Orchestration:** Docker Compose

## Architecture

Memory is accessed via a Python singleton `from memory import mem` (`mem.add()` / `mem.search()`). Memory scoping uses `user_id`: `"agent_1"` (private), `"shared"` (cross-agent), `"session_<timestamp>"` (ephemeral).

## Key Files

| File | Purpose |
|------|---------|
| `src/agent-memory-layer/memory/client.py` | `mem` singleton + Ollama timeout patching |
| `src/agent-memory-layer/memory/config.py` | mem0 config from env vars |
| `src/agent-memory-layer/memory/__init__.py` | Exports `mem` |
| `docker-compose.yml` | Service orchestration |

## Commands

```bash
docker compose up -d                          # Start core services
docker compose --profile tools up -d         # Include memory-chat tool
python -m tests.smoke_test                   # Integration tests
curl http://localhost:11434/api/tags          # Ollama health
curl http://localhost:6333/healthz            # Qdrant health
./deploy                                      # Deploy to remote server
```

## Conventions

- **Config:** Environment variables (see `.env.example`); `config.py` builds the mem0 config dict. Defaults work without a `.env` file.
- **Memory access:** Always use the `mem` singleton — do not instantiate mem0 directly.
- **Python deps:** `src/agent-memory-layer/requirements.txt`
- **Read `docs/decisions.md`** before swapping any component — it documents why each was chosen.
- **Secrets:** Never log or expose API keys. Cloud keys are passed via env vars only.
- **Docker ports:** Ollama 11434, Open WebUI 3000, Qdrant 6333/6334, Beszel 8090.

## Documentation

- `docs/architecture.md` — layered architecture diagram and data flow
- `docs/decisions.md` — component choice rationale
- `docs/memory-api.md` — `mem` API reference
- `docs/setup.md` — installation and troubleshooting
