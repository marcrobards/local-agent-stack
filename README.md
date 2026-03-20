# local-agent-stack

A self-hosted AI agent platform running fully locally on a home Linux server. No cloud dependencies, no API keys, no data leaving the machine.

## What this is

A modular stack for running and orchestrating AI agents at home. Built incrementally — each layer is independently useful and loosely coupled.

## Current state

- ✅ Ollama — local LLM inference (qwen2.5:7b)
- ✅ Memory layer — persistent shared memory for agents (mem0 + Qdrant + nomic-embed-text)
- 🔲 Agent framework — orchestration and agent definitions
- 🔲 Tool layer — what agents can actually do
- 🔲 Web interface — chat UI for interacting with agents

## Stack

| Component | Role | Technology |
|---|---|---|
| LLM inference | Run models locally | Ollama |
| Memory | Persistent agent memory | mem0 + Qdrant |
| Embeddings | Semantic search | nomic-embed-text (via Ollama) |
| Containers | Service isolation | Docker Compose |
| Language | Agent code | Python 3.12 |

## Repository layout

```
local-agent-stack/
├── memory/               # Memory layer (mem0 + Qdrant)
│   ├── __init__.py
│   ├── client.py
│   └── config.py
├── tests/
│   └── smoke_test.py
├── docs/
│   ├── architecture.md
│   ├── setup.md
│   ├── memory-api.md
│   └── decisions.md
├── docker-compose.yml
├── .env.example
├── requirements.txt
└── README.md
```

## Quick start

See [docs/setup.md](docs/setup.md) for full install instructions.

## Documentation

- [Architecture](docs/architecture.md) — how the pieces fit together
- [Setup guide](docs/setup.md) — getting the stack running from scratch
- [Memory API](docs/memory-api.md) — how agents read and write memory
- [Decisions log](docs/decisions.md) — why we chose this stack
