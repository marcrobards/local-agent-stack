# Shopping Agent — Current State

**What it is:** A 5-stage pipeline that helps the user find products online, with a focus on color-accuracy verification. It runs inside Open WebUI via the Pipelines server.

**Status: ✅ Running** — pipeline starts and loads in Open WebUI.

## Architecture — What's Built

| Stage | Status | Implementation |
|---|---|---|
| **01-clarify-request** | ✅ Complete | PROMPT.md (94 lines) + Ollama `qwen2.5:7b`. Reads the user's mem0 preferences. Smoke test passes. |
| **02-search** | ✅ Complete | `search.py` — full Browser Use Cloud agent. Searches Amazon, Google Shopping, Etsy, Target, Walmart (+ Poshmark for clothing) **concurrently** via `asyncio.gather()`. Uses **Anthropic Claude Sonnet** (cloud) or Browser Use's own LLM. Structured `Candidate` dataclass, JSON parsing with code-fence stripping. |
| **02-verify** | ✅ Complete | `fetch_page.py` — requests+BeautifulSoup page fetcher. Checks for 404s, homepage redirects, out-of-stock signals. Returns LIVE/DEAD status. |
| **02a-color-verify** | ✅ Complete | `fetch_images.py` — extracts hero/product images (OG meta, CSS selectors, fallback). Vision model `qwen2.5vl:7b` assesses color PASS/FAIL/AMBIGUOUS. Smoke test generates a synthetic PNG. |
| **03-present** | ✅ Complete | PROMPT.md (119 lines) — formats results for Open WebUI with tappable links. |

## Pipeline Glue

`shopping_agent_pipeline.py`: Complete — manifold-type Pipeline class with Valves for config. Orchestrates all 5 stages as a generator (streams status updates). Spec-confirmation detection via affirmative matching. Stores sessions to mem0 on success. `_run_search_tools` calls `search_all()` + `format_results()` via `asyncio.run()` across all 5 sources.

## Infrastructure

- **Docker Compose:** All services defined in a single `docker-compose.yml` — shopping-pipeline, Ollama, Qdrant, Open WebUI, Beszel monitoring, and tool-profile smoke tests.
- **Cloud APIs required:** `ANTHROPIC_API_KEY` + `BROWSER_USE_API_KEY` (stage 02 search only — everything else is local Ollama)
- **Local infra:** Ollama (qwen2.5:7b + qwen2.5vl:7b + nomic-embed-text), Qdrant (mem0 vector store), Open WebUI + Pipelines server

## Remaining Gaps

1. **No end-to-end orchestration test** — smoke tests cover individual stages (01, 02a, browser-use POC, search) but there's no test that runs the full pipeline through all 5 stages.
