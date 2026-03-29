# local-agent-stack

A self-hosted AI agent platform running on a home Linux server. Most inference runs locally via Ollama — the shopping workflow uses cloud APIs for web search only.

## What this is

A modular stack for running and orchestrating AI agents at home. Built incrementally — each layer is independently useful and loosely coupled.

## Current state

- ✅ Ollama — local LLM inference (qwen2.5:7b + qwen2.5vl:7b vision)
- ✅ Memory layer — persistent shared memory for agents (mem0 + Qdrant + nomic-embed-text)
- ✅ Open WebUI — chat interface with Pipelines server integration
- ✅ Shopping agent — 5-stage product search pipeline running in Open WebUI
- ✅ Monitoring — Beszel server + container monitoring

## Stack

| Component | Role | Technology |
|---|---|---|
| LLM inference | Run models locally | Ollama (qwen2.5:7b, qwen2.5vl:7b) |
| Memory | Persistent agent memory | mem0 + Qdrant |
| Embeddings | Semantic search | nomic-embed-text (via Ollama) |
| Web search | Browser automation | Browser Use Cloud + Anthropic Claude Sonnet |
| Chat UI | User-facing interface | Open WebUI + Pipelines server |
| Monitoring | Server & container health | Beszel |
| Containers | Service isolation | Docker Compose |
| Language | Agent code | Python 3.11 (Pipelines container) |

## Shopping agent

A 5-stage pipeline that helps find specific products online, with color-accuracy verification via a vision model:

1. **Clarify request** — conversational clarification using the user's stored preferences from memory
2. **Search** — concurrent searches across Amazon, Google Shopping, Etsy, Target, Walmart (+ Poshmark for clothing) via Browser Use Cloud
3. **Verify** — confirms each candidate URL is live and assesses spec match
4. **Color verify** — vision model (qwen2.5vl:7b) checks product images against the color description
5. **Present** — formats results with tappable links in Open WebUI

Appears as "Shopping Agent" in the Open WebUI model dropdown.

## Repository layout

```
local-agent-stack/
├── src/
│   ├── agent-memory-layer/       # Memory layer (mem0 + Qdrant)
│   │   ├── memory/
│   │   │   ├── __init__.py
│   │   │   ├── client.py
│   │   │   └── config.py
│   │   └── tests/
│   ├── pipelines/
│   │   └── shopping_agent_pipeline.py
│   └── workflows/
│       └── online-shopping/
│           ├── 01-clarify-request/    # Stage prompts + tools
│           ├── 02-search/
│           ├── 02-verify/
│           ├── 02a-color-verify/
│           ├── 03-present/
│           └── tests/
├── docs/
│   ├── architecture.md
│   ├── setup.md
│   ├── memory-api.md
│   ├── decisions.md
│   └── server-specs.md
├── docker-compose.yml
├── Dockerfile.pipeline
├── Dockerfile.browser-use
├── deploy
├── .env.example
└── README.md
```

## Quick start

```bash
# Start core services
docker compose up -d

# Build and start the shopping pipeline
docker compose build shopping-pipeline
docker compose up -d shopping-pipeline

# Then in Open WebUI (http://localhost:3000):
#   Admin Panel → Settings → Connections → + (add connection)
#   URL:     http://shopping-pipeline:9099
#   API Key: 0p3n-w3bu!
#   Save — "Shopping Agent" appears in the model dropdown.
```

See [docs/setup.md](docs/setup.md) for full install instructions.

## Smoke tests

```bash
# Memory layer integration test
python -m tests.smoke_test

# Stage 01 — clarify request (requires Ollama)
docker compose --profile tools run --rm smoke-test-stage02a

# Stage 02 — browser-use search (requires ANTHROPIC_API_KEY + BROWSER_USE_API_KEY)
docker compose --profile tools run --rm smoke-test-browser-use
```

## Documentation

- [Architecture](docs/architecture.md) — how the pieces fit together
- [Setup guide](docs/setup.md) — getting the stack running from scratch
- [Memory API](docs/memory-api.md) — how agents read and write memory
- [Decisions log](docs/decisions.md) — why we chose this stack
- [Server specs](docs/server-specs.md) — hardware details
