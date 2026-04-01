# Shopping Agent — Current State

*Last updated: 2026-03-31*

---

## Overview

The shopping agent is a 5-stage product search pipeline that takes a natural-language shopping request and returns verified, color-confirmed product recommendations. It runs inside Docker Compose on local hardware, with two cloud dependencies for the search stage: Browser Use Cloud (web browsing) and Anthropic Claude (LLM).

There are two implementations:
- **v1** — Open WebUI Pipelines server (`src/pipelines/shopping_agent_pipeline.py`) — superseded, commented out in docker-compose
- **v2** — Standalone FastAPI service (`src/shopping-agent/app.py`) — active, preferred

---

## Pipeline Architecture

```
User (Open WebUI or any OpenAI-compatible client)
  → Shopping Agent v2 (FastAPI, OpenAI-compatible API)
    → 1. Clarify   — extract product spec via LLM (Claude or qwen2.5:7b)
    → 2. Search    — Browser Use Cloud agents search 6 sites concurrently
    → 3. Verify    — fetch pages, assess spec match + color (Claude vision)
    → 4. Present   — format recommendations as markdown

Memory layer (v1 only, not yet integrated in v2):
  → mem0 + Qdrant + nomic-embed-text + qwen2.5:7b
```

The pipeline runs sequentially. Search dominates wall-clock time (~90s for 6 concurrent sources). Full end-to-end is roughly 3–5 minutes.

---

## Implementation Status

### What's working

| Component | Status | Notes |
|---|---|---|
| Clarify stage | ✅ Working | Conversational spec gathering; handles vague color input |
| Search stage | ✅ Working | 6 sources concurrent (Amazon, Google Shopping, Etsy, Target, Walmart, Poshmark) |
| Verify stage | ✅ Working | HTTP fetch + HTML extraction; spec confidence scoring |
| Color verify | ✅ Working | v1: local qwen2.5vl; v2: Claude vision integrated into verify |
| Present stage | ✅ Working | Markdown output, ordered by confidence + color match |
| Docker Compose | ✅ Working | v2 service active; v1 commented out |
| Memory layer | ✅ Working | mem0 + Qdrant, user_id scoping |
| Monitoring | ✅ Working | Beszel dashboard at port 8090 |

### Partial / caveats

| Issue | Impact |
|---|---|
| Memory not integrated in v2 | Sessions not stored; no recall of past preferences in v2 |
| Refinement logic (v2) | Code exists, untested in production |
| SPA product pages | Client-rendered pages (e.g. some Walmart pages) may appear dead |
| Image fetcher lazy-load | Lazy-loaded product images may not be captured |
| Streaming | v2 emits one chunk, not true character-by-character streaming |

### Not working

| Component | Status |
|---|---|
| v1 Pipelines server | Commented out in docker-compose; superseded by v2 |

---

## Key Source Files

| File | Purpose |
|---|---|
| `src/shopping-agent/app.py` | v2 FastAPI entrypoint; conversation state, stage orchestration |
| `src/pipelines/shopping_agent_pipeline.py` | v1 pipeline (inactive) |
| `src/workflows/online-shopping/02-search/tools/search.py` | Browser Use Cloud multi-source search |
| `src/workflows/online-shopping/02-verify/tools/fetch_page.py` | HTTP page fetch + metadata extraction |
| `src/workflows/online-shopping/02a-color-verify/tools/fetch_images.py` | Product image URL extraction |
| `src/agent-memory-layer/memory/client.py` | mem0 singleton with Ollama timeout patch |
| `src/agent-memory-layer/memory/config.py` | mem0 config from environment variables |
| `docker-compose.yml` | Service orchestration |

Workflow prompts (the stage "intelligence") live in `src/workflows/online-shopping/0*/`.

---

## Stage Details

### Stage 1 — Clarify

- Calls LLM (Claude or qwen2.5:7b, controlled by `LLM_PROVIDER`)
- Extracts a `ProductSpec` (Pydantic model): category, color, size, budget, brand, occasion, etc.
- Handles vague color input: precise descriptions proceed immediately; vague ones get one targeted question
- Outputs a spec summary for user confirmation before proceeding
- v1 recalls memory before clarifying (`mem.search()` on past preferences)

### Stage 2 — Search

- Launches one Browser Use Cloud agent per source (6 concurrent via asyncio)
- Each agent navigates the site, extracts up to 10 candidates: URL, title, price, image_url, shop_name, match_reason
- Agent response is natural language containing JSON; parser handles markdown fences and escaping variations
- Poshmark only queried when `is_clothing=True` in the spec
- No retry on agent failure; returns empty candidates for that source

**Known fragilities:**
- Parsing is regex-based; agent response format variation can drop results
- Agent may use steps navigating rather than extracting if task prompt is misread
- Dependent on `BROWSER_USE_API_KEY` and `ANTHROPIC_API_KEY` — no local fallback

### Stage 3 — Verify

- HTTP fetch of each candidate URL
- Detects dead links (404s, homepage redirects)
- Extracts title, price, availability from static HTML (5 CSS selector strategies for price)
- LLM rates spec confidence: HIGH / MEDIUM / LOW
- **v2 integrates color assessment here** — Claude vision assesses images against color spec
- **v1 has a separate color verify stage** — local qwen2.5vl:7b vision model

**Known fragilities:**
- No JavaScript rendering; SPA product pages may fail
- Out-of-stock detection is text-match only (doesn't check button state or form elements)
- Image lazy-loading not triggered; `data-src` is checked but scroll events aren't fired

### Stage 4 — Present (v1) / integrated in v2

- Orders results: PASS + HIGH confidence first, then good matches, then AMBIGUOUS
- Formats as markdown with clickable links
- Friendly tone; no pipeline jargon exposed to user

---

## External Dependencies

| Service | Required | Purpose |
|---|---|---|
| Browser Use Cloud | Yes | Web browsing for search stage |
| Anthropic Claude API | Yes | LLM for text stages + vision in v2 |
| Ollama (local) | Yes | qwen2.5:7b (text), qwen2.5vl:7b (vision, v1 only), nomic-embed-text (embeddings) |
| Qdrant (local) | Yes | Vector storage for memory layer |

The platform is described as "local-first" but search cannot run without the two cloud APIs.

---

## Configuration

Runtime config via environment variables. The most important ones:

```bash
# LLM routing
LLM_PROVIDER=claude            # "claude" or "ollama" for text stages
ANTHROPIC_API_KEY=sk-...       # Required
CLAUDE_MODEL=claude-sonnet-4-20250514

# Search
BROWSER_USE_API_KEY=...        # Required
SEARCH_LLM=anthropic           # "anthropic" or "browser-use"
SEARCH_MAX_RESULTS=10          # Candidates per source
SEARCH_MAX_STEPS=15            # Max browser agent steps per source

# Local models
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_LLM_MODEL=qwen2.5:7b
OLLAMA_VISION_MODEL=qwen2.5vl:7b

# Memory
USER_ID=user_1                 # Memory scope
QDRANT_HOST=qdrant
QDRANT_PORT=6333

# Debug
DEBUG_OUTPUT_DIR=/app/debug    # Search results saved here as JSON
```

Defaults work for local development without a `.env` file.

---

## Infrastructure

Services managed by Docker Compose:

| Service | Port | Image |
|---|---|---|
| ollama | 11434 | `ollama/ollama` |
| open-webui | 3000 | `ghcr.io/open-webui/open-webui:main` |
| qdrant | 6333, 6334 | `qdrant/qdrant:latest` |
| shopping-agent (v2) | internal 8000 | custom build |
| beszel | 8090 | monitoring |
| ~~shopping-pipeline (v1)~~ | ~~9099~~ | commented out |

Debug output is mounted at `./debug:/app/debug` in the shopping-agent container.

---

## Known Issues & Limitations

1. **Cloud dependency for search** — no local fallback if Browser Use Cloud or Anthropic API is unavailable
2. **Memory not in v2** — v2 doesn't store or recall sessions; user preferences are not persisted between conversations
3. **SPA sites** — product pages with client-side rendering may fail verification; no headless browser in verify stage
4. **Debug files accumulate** — search results saved to `DEBUG_OUTPUT_DIR` on every run; no cleanup
5. **No retry logic** — failed search sources and failed page fetches are silently dropped
6. **Streaming** — response is buffered then sent as one chunk; UI may show spinner until complete
7. **No multi-currency normalization** — prices extracted as strings, not parsed/compared
8. **Refinement untested** — v2 has a `stages.refine` module for follow-up adjustments but it hasn't been validated in production

---

## v1 vs v2 Differences

| | v1 (Pipelines) | v2 (FastAPI) |
|---|---|---|
| Server type | Open WebUI Pipelines | OpenAI-compatible FastAPI |
| Color verify | Separate stage, local qwen2.5vl | Integrated into verify, Claude vision |
| Memory integration | Yes (add + search) | Not yet |
| Refinement support | No | Yes (untested) |
| Debug output | Stage JSON files | Search JSON only |
| Status | Inactive (commented out) | Active |

---

## Documentation

| File | Contents |
|---|---|
| `docs/architecture.md` | Layered architecture diagram and data flow |
| `docs/decisions.md` | Component choice rationale (read before swapping anything) |
| `docs/memory-api.md` | `mem` API reference with examples |
| `docs/setup.md` | Installation, troubleshooting, smoke tests |
| `CLAUDE.md` | Quick reference for Claude Code |
