# Shopping Agent — Current State

**What it is:** A 5-stage pipeline that helps a user ("Danielle") find products online, with a focus on color-accuracy verification. It's designed to run inside Open WebUI via the Pipelines server.

## Architecture — What's Built

| Stage | Status | Implementation |
|---|---|---|
| **01-clarify-request** | ✅ Complete | PROMPT.md (94 lines) + Ollama `qwen2.5:7b`. Reads Danielle's mem0 preferences. Smoke test passes. |
| **02-search** | ✅ Complete | `search.py` — full Browser Use Cloud agent. Searches Amazon, Google Shopping, Etsy, Target, Walmart (+ Poshmark for clothing). Uses **Anthropic Claude Sonnet** (cloud) or Browser Use's own LLM. Structured `Candidate` dataclass, JSON parsing with code-fence stripping. |
| **02-verify** | ✅ Complete | `fetch_page.py` — requests+BeautifulSoup page fetcher. Checks for 404s, homepage redirects, out-of-stock signals. Returns LIVE/DEAD status. |
| **02a-color-verify** | ✅ Complete | `fetch_images.py` — extracts hero/product images (OG meta, CSS selectors, fallback). Vision model `qwen2.5vl:7b` assesses color PASS/FAIL/AMBIGUOUS. Smoke test generates a synthetic PNG. |
| **03-present** | ✅ Complete | PROMPT.md (119 lines) — formats results for Open WebUI with tappable links. |

## Pipeline Glue

`shopping_agent_pipeline.py`: Complete — manifold-type Pipeline class with Valves for config. Orchestrates all 5 stages as a generator (streams status updates). Spec-confirmation detection via affirmative matching. Stores sessions to mem0 on success.

## Key Dependencies / External Services

- **Cloud APIs required:** `ANTHROPIC_API_KEY` + `BROWSER_USE_API_KEY` (stage 02 search only — everything else is local Ollama)
- **Local infra:** Ollama (qwen2.5:7b + qwen2.5vl:7b + nomic-embed-text), Qdrant (mem0 vector store), Open WebUI + Pipelines server

## What's NOT Done / Gaps

1. **Pipeline `_run_search_tools` is stale** — it imports `from search import search` (a synchronous `search()` function that doesn't exist). The actual `search.py` exposes `async search_source()` and `async search_all()`. This means **stage 02 search tool integration in the pipeline is broken** — it would silently fall back to LLM-only search via the prompt.
2. **No end-to-end orchestration test** — the smoke tests cover individual stages (01, 02a, browser-use POC, search) but there's no test that runs the full pipeline.
3. **Sequential search** — `search_all()` searches sources sequentially rather than concurrently (noted in code), which is slow across 5-6 sources with browser automation.
4. **Docker Compose split** — `docker-compose.shopping.yml` defines the pipeline service but it's a separate file, not merged into the main `docker-compose.yml`. The browser-use smoke test compose is also a standalone fragment.
5. **Single commit** — everything shipped in one initial commit, no iteration history.
