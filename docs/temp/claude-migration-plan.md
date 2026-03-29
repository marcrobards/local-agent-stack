# Plan: Route AI Calls Through Claude API

**Date:** 2026-03-29
**Status:** Draft

## Goal

Switch all text LLM calls in the shopping agent pipeline from Ollama (qwen2.5:7b) to the Anthropic Claude API. Two exceptions remain unchanged:

- **Vision model (color verify)** — stays local via Ollama (qwen2.5vl:7b)
- **Browser Use search** — stays cloud-based (Anthropic + Browser Use Cloud, unchanged)

## Current State

| Stage | LLM call | Current provider | Target provider |
|-------|----------|-----------------|-----------------|
| 01 Clarify | `_text_chat()` | Ollama qwen2.5:7b | **Claude API** |
| 02 Search (browser agent) | Browser Use `ChatAnthropic` | Cloud (Anthropic) | Cloud (no change) |
| 02 Search (summarize) | `_text_chat()` | Ollama qwen2.5:7b | **Claude API** |
| 02-Verify (summarize) | `_text_chat()` | Ollama qwen2.5:7b | **Claude API** |
| 02a Color Verify (vision) | `_ollama_chat(VISION_MODEL)` | Ollama qwen2.5vl:7b | Ollama (no change) |
| 02a Color Verify (summarize) | `_text_chat()` | Ollama qwen2.5:7b | **Claude API** |
| 03 Present | `_text_chat()` | Ollama qwen2.5:7b | **Claude API** |
| Memory extraction (mem0) | mem0 internal → Ollama | Ollama qwen2.5:7b | Ollama (no change) |
| Embeddings (mem0) | mem0 internal → Ollama | nomic-embed-text | Ollama (no change) |

### What stays on Ollama

- Vision model (qwen2.5vl:7b) — called directly in `_run_color_verify_tools()`
- mem0's internal LLM calls (memory extraction + embeddings) — configured in `memory/config.py`, independent of the pipeline's LLM_PROVIDER setting
- Ollama itself still runs for the above; it is NOT removed from the stack

## Changes Required

### 1. Set `LLM_PROVIDER=claude` (config only — no code change)

The routing infrastructure already exists. `_text_chat()` checks `LLM_PROVIDER` and dispatches to `_claude_chat()` or `_ollama_chat()` accordingly. The `_claude_chat()` function and the `anthropic` dependency are already in place.

**Files:** `.env` only

```
LLM_PROVIDER=claude
```

That's it. The pipeline code already supports this via the `LLM_PROVIDER` env var and the Valves UI in Open WebUI.

### 2. Verify `ANTHROPIC_API_KEY` is set

The key is already in `.env` (used by Browser Use search). The same key will now also be used by `_claude_chat()` for all text stages. No new key needed.

**Files:** No change — already configured.

### 3. Verify `CLAUDE_MODEL` default is acceptable

Currently defaults to `claude-sonnet-4-20250514`. This can be overridden in `.env` or via the Open WebUI Valves UI.

**Files:** No change needed unless a different model is desired.

### 4. Pass `CLAUDE_MODEL` to the container (optional)

If you want to override the default Claude model, add to docker-compose.yml:

**File:** `docker-compose.yml` → `shopping-pipeline.environment`

```yaml
- CLAUDE_MODEL=${CLAUDE_MODEL:-claude-sonnet-4-20250514}
```

### 5. Update `.env.example` to reflect the new default

**File:** `.env.example`

```
LLM_PROVIDER=claude
```

### 6. Update documentation

**Files to update:**

| File | What to change |
|------|---------------|
| `docs/architecture.md` | Update the stage table: stages 01, 02 (summarize), 02-verify, 02a (summarize), 03 now use Claude API. Update the "Local first" principle to "Local-where-it-matters" or similar. Update the shopping pipeline flow diagram. |
| `src/workflows/online-shopping/CONTEXT.md` | Update the "Models" section to reflect Claude for text stages. |
| `AGENTS.md` | Update the "LLM inference" line in Stack section. |
| `docs/decisions.md` | Add a new decision entry documenting why we're switching text stages to Claude (quality, speed, etc.). |

## What Does NOT Change

- `search.py` — Browser Use search is already cloud-based with its own Anthropic client; completely independent of `LLM_PROVIDER`
- `fetch_page.py` — No LLM calls, just HTTP + BeautifulSoup
- `fetch_images.py` — No LLM calls, just HTTP + BeautifulSoup
- `memory/client.py`, `memory/config.py` — mem0 continues using Ollama for memory extraction and embeddings
- `_ollama_chat()` — Stays in the codebase; still called for vision model
- `docker-compose.yml` Ollama service — Still needed for vision + mem0
- `Dockerfile.pipeline` — No change; `anthropic` pip package already installed

## Execution Steps

1. **Set `LLM_PROVIDER=claude` in `.env`**
2. **Rebuild the pipeline container:** `docker compose build shopping-pipeline`
3. **Restart:** `docker compose up -d shopping-pipeline`
4. **Test:** Send a shopping query through Open WebUI and verify:
   - Clarify stage responds (Claude)
   - Search runs (Browser Use Cloud — unchanged)
   - Verify stage responds (Claude)
   - Color verify images are assessed (Ollama vision — unchanged)
   - Color verify summary responds (Claude)
   - Present stage formats results (Claude)
5. **Check logs:** `docker logs shopping-pipeline` — look for `claude_chat` log lines at each stage
6. **Update docs** per section 6 above
7. **Update `.env.example`**

## Cost Impact

All text stages now incur Anthropic API costs. Rough estimate per shopping query:
- ~5 Claude API calls (clarify, search summarize, verify, color-verify summarize, present)
- Each call: ~1k–4k input tokens, ~500–2k output tokens
- At Claude Sonnet pricing: roughly $0.02–0.05 per full shopping query

## Rollback

Set `LLM_PROVIDER=ollama` in `.env` and restart. The Ollama path is fully preserved.
