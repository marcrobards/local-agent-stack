# local-agent-stack

A self-hosted AI agent platform running on a home Linux server. Most inference runs locally via Ollama — the shopping workflow uses cloud APIs for web search only.

## What this is

A modular stack for running and orchestrating AI agents at home. Built incrementally — each layer is independently useful and loosely coupled.

## Current state

- ✅ Ollama — local LLM inference (qwen2.5:7b + qwen2.5vl:7b vision + nomic-embed-text embeddings)
- ✅ Memory layer — persistent shared memory for agents (mem0 + Qdrant)
- ✅ Open WebUI — chat interface connected to the shopping agent
- ✅ Shopping agent — 5-stage product search pipeline (standalone FastAPI service)
- ✅ Monitoring — Beszel server + container monitoring

## Stack

| Component | Role | Technology |
|---|---|---|
| LLM inference | Run models locally | Ollama (qwen2.5:7b, qwen2.5vl:7b) |
| Memory | Persistent agent memory | mem0 + Qdrant |
| Embeddings | Semantic search | nomic-embed-text (via Ollama) |
| Web search | Browser automation | Browser Use Cloud + Anthropic Claude |
| Chat UI | User-facing interface | Open WebUI |
| Agent server | OpenAI-compatible API | FastAPI (shopping-agent) |
| Monitoring | Server & container health | Beszel |
| Containers | Service isolation | Docker Compose |
| Language | Agent code | Python 3.11 |

## Shopping agent

A 5-stage pipeline that finds specific products online, with color-accuracy verification:

1. **Clarify** — conversational spec gathering; handles vague color descriptions with targeted follow-ups
2. **Search** — concurrent searches across Amazon, Google Shopping, Etsy, Target, Walmart (+ Poshmark for clothing) via Browser Use Cloud
3. **Verify** — confirms each candidate URL is live, assesses spec match, and checks color accuracy via Claude vision
4. **Present** — formats results as markdown ordered by match quality

The agent runs as a standalone FastAPI service exposing an OpenAI-compatible `/v1/chat/completions` endpoint. Open WebUI connects to it as a custom model connection.

> **Cloud dependencies for search:** `BROWSER_USE_API_KEY` (Browser Use Cloud) and `ANTHROPIC_API_KEY` (Anthropic) are required. Everything else runs locally.

## Repository layout

```
local-agent-stack/
├── src/
│   ├── shopping-agent/               # Active shopping agent (FastAPI, v2)
│   │   ├── app.py                    # Entrypoint, conversation state, stage orchestration
│   │   ├── stages/
│   │   │   ├── clarify.py
│   │   │   ├── search.py
│   │   │   ├── verify.py
│   │   │   ├── present.py
│   │   │   └── refine.py
│   │   └── tests/
│   ├── agent-memory-layer/           # Memory layer (mem0 + Qdrant)
│   │   ├── memory/
│   │   │   ├── client.py             # mem singleton with Ollama timeout patch
│   │   │   └── config.py             # mem0 config from env vars
│   │   └── tests/
│   ├── pipelines/
│   │   └── shopping_agent_pipeline.py  # v1 pipeline (inactive, superseded by v2)
│   └── workflows/
│       └── online-shopping/          # Stage prompts and tools
│           ├── 01-clarify-request/
│           ├── 02-search/
│           ├── 02-verify/
│           ├── 02a-color-verify/
│           └── 03-present/
├── docs/
│   ├── architecture.md
│   ├── setup.md
│   ├── memory-api.md
│   ├── decisions.md
│   ├── server-specs.md
│   └── shopping-agent-state.md       # Detailed current state of the shopping agent
├── docker-compose.yml
├── Dockerfile.shopping-agent
├── Dockerfile.pipeline               # v1 (inactive)
├── Dockerfile.browser-use
├── deploy
└── .env.example
```

## Quick start

```bash
# Start core services (Ollama, Open WebUI, Qdrant)
docker compose up -d

# Build and start the shopping agent
docker compose build shopping-agent
docker compose up -d shopping-agent

# Then in Open WebUI (http://localhost:3000):
#   Admin Panel → Settings → Connections → + (add connection)
#   URL:     http://shopping-agent:8000
#   API Key: any value
#   Save — "Shopping Agent" appears in the model dropdown.
```

See [docs/setup.md](docs/setup.md) for full install instructions and troubleshooting.

## Tests

```bash
# Memory layer integration test (requires Ollama + Qdrant running)
python -m tests.smoke_test

# Shopping agent unit tests
cd src/shopping-agent && python -m pytest tests/
```

## Documentation

- [Architecture](docs/architecture.md) — how the pieces fit together
- [Shopping agent state](docs/shopping-agent-state.md) — detailed current status, known issues, stage breakdown
- [Setup guide](docs/setup.md) — getting the stack running from scratch
- [Memory API](docs/memory-api.md) — how agents read and write memory
- [Decisions log](docs/decisions.md) — why we chose this stack
- [Server specs](docs/server-specs.md) — hardware details
