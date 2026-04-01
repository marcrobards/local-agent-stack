# local-agent-stack

A self-hosted AI agent platform running on a home Linux server. Inference runs locally via Ollama. Cloud APIs are used where local models fall short.

## What this is

A modular stack for running and orchestrating AI agents at home. Built incrementally — each layer is independently useful and loosely coupled.

## Current state

- ✅ Ollama — local LLM inference (qwen2.5:7b + qwen2.5vl:7b vision + nomic-embed-text embeddings)
- ✅ Memory layer — persistent shared memory for agents (mem0 + Qdrant)
- ✅ Open WebUI — chat interface
- ✅ Monitoring — Beszel server + container monitoring
- ✅ Shopping app — AI-powered shopping agent with clarification chat, web search, and product results

## Stack

| Component | Role | Technology |
|---|---|---|
| LLM inference | Run models locally | Ollama (qwen2.5:7b, qwen2.5vl:7b) |
| Memory | Persistent agent memory | mem0 + Qdrant |
| Embeddings | Semantic search | nomic-embed-text (via Ollama) |
| Chat UI | User-facing interface | Open WebUI |
| Monitoring | Server & container health | Beszel |
| Shopping backend | API + agent orchestration | FastAPI (Python) |
| Shopping frontend | Shopping UI | React + TypeScript |
| Web browsing | Live product search | Browser Use Cloud |
| Cloud LLM | Site selection + clarification | Claude (Anthropic API) |
| Containers | Service isolation | Docker Compose |

## Repository layout

```
local-agent-stack/
├── src/
│   ├── agent-memory-layer/           # Memory layer (mem0 + Qdrant)
│   │   ├── memory/
│   │   │   ├── client.py             # mem singleton with Ollama timeout patch
│   │   │   └── config.py             # mem0 config from env vars
│   │   └── tests/
│   └── shopping-app/                 # AI shopping agent
│       ├── backend/                  # FastAPI app
│       │   ├── main.py
│       │   ├── models.py
│       │   ├── db.py
│       │   ├── routers/
│       │   │   ├── searches.py       # Search CRUD + trigger endpoint
│       │   │   └── preferences.py    # User shopping preferences
│       │   └── services/
│       │       ├── search.py         # Browser Use + Claude site selection
│       │       ├── clarify.py        # Clarification chat (Claude)
│       │       └── preferences.py    # Preference management
│       └── frontend/                 # React + TypeScript UI
│           └── src/app/
│               ├── SearchList.tsx    # Search history view
│               ├── SearchDetail.tsx  # Results + clarification chat
│               ├── ClarifyChat.tsx   # Chat component
│               └── ProductCard.tsx   # Product result card
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
# Start core services (Ollama, Open WebUI, Qdrant, Beszel, Shopping App)
docker compose up -d

# Start with optional memory chat tool
docker compose --profile tools up -d
```

The shopping app requires an Anthropic API key and Browser Use Cloud credentials in `.env`.

See [docs/setup.md](docs/setup.md) for full install instructions and troubleshooting.

## Shopping app

The shopping app is an AI agent that takes a natural-language shopping request, clarifies it through conversation, then executes live web searches across multiple retail sites.

**Flow:**
1. User submits a search (e.g. "blue linen tote bag under $50")
2. Claude asks clarifying questions via chat if needed
3. Claude selects 2–4 relevant retail sites
4. Browser Use Cloud scrapes each site for matching products
5. Results are displayed as product cards with images, prices, and links

**Services:** frontend at `:3001`, backend API at `:8000`

## Memory layer

Agents import a Python singleton `mem` for shared persistent memory:

```python
from memory import mem
mem.add("user prefers minimal UIs", user_id="shared")
results = mem.search("UI preferences", user_id="shared")
```

**Memory scoping via `user_id`:**
- `user_id="agent_1"` — private to that agent
- `user_id="shared"` — readable by all agents
- `user_id="session_<timestamp>"` — ephemeral

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
