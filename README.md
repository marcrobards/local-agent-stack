# local-agent-stack

A self-hosted AI agent platform running on a home Linux server. Inference runs locally via Ollama.

## What this is

A modular stack for running and orchestrating AI agents at home. Built incrementally — each layer is independently useful and loosely coupled.

## Current state

- ✅ Ollama — local LLM inference (qwen2.5:7b + qwen2.5vl:7b vision + nomic-embed-text embeddings)
- ✅ Memory layer — persistent shared memory for agents (mem0 + Qdrant)
- ✅ Open WebUI — chat interface
- ✅ Monitoring — Beszel server + container monitoring

## Stack

| Component | Role | Technology |
|---|---|---|
| LLM inference | Run models locally | Ollama (qwen2.5:7b, qwen2.5vl:7b) |
| Memory | Persistent agent memory | mem0 + Qdrant |
| Embeddings | Semantic search | nomic-embed-text (via Ollama) |
| Chat UI | User-facing interface | Open WebUI |
| Monitoring | Server & container health | Beszel |
| Containers | Service isolation | Docker Compose |
| Language | Agent code | Python 3.11 |

## Repository layout

```
local-agent-stack/
├── src/
│   └── agent-memory-layer/           # Memory layer (mem0 + Qdrant)
│       ├── memory/
│       │   ├── client.py             # mem singleton with Ollama timeout patch
│       │   └── config.py             # mem0 config from env vars
│       └── tests/
├── docs/
│   ├── architecture.md
│   ├── setup.md
│   ├── memory-api.md
│   ├── decisions.md
│   └── server-specs.md
├── docker-compose.yml
└── .env.example
```

## Quick start

```bash
# Start core services (Ollama, Open WebUI, Qdrant)
docker compose up -d
```

See [docs/setup.md](docs/setup.md) for full install instructions and troubleshooting.

## Tests

```bash
# Memory layer integration test (requires Ollama + Qdrant running)
python -m tests.smoke_test
```

## Documentation

- [Architecture](docs/architecture.md) — how the pieces fit together
- [Setup guide](docs/setup.md) — getting the stack running from scratch
- [Memory API](docs/memory-api.md) — how agents read and write memory
- [Decisions log](docs/decisions.md) — why we chose this stack
- [Server specs](docs/server-specs.md) — hardware details
