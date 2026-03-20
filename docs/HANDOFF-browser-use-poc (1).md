# Browser-Use POC — Coding Agent Handoff

This document is the complete build spec for a proof-of-concept smoke test.
Read it fully before creating any files. All decisions are recorded here.

---

## What you are building

A single smoke test script that proves `browser-use` can drive a headless
browser via Ollama's `qwen2.5:7b` to search a shopping site and extract
structured product candidate data. This is a proof-of-concept for replacing
the stub search tools in the online-shopping workflow.

The test must run fully locally — no cloud API keys, no external services
beyond Ollama.

---

## Why browser-use

The online-shopping workflow (see `src/workflows/online-shopping/`) has a
search stage (02) with tool stubs that cannot actually search Amazon or
Google Shopping — those sites block naive scraping. Rather than paying for
a SERP API ($75+/month for SerpApi), we are testing `browser-use`, an
open-source Python library that lets an LLM agent drive a real browser.

browser-use works with local Ollama models including `qwen2.5:7b`. If this
POC succeeds, browser-use replaces all five source-specific search
implementations with a single agent that can navigate any shopping site.

---

## Server context

- **Machine**: Lenovo Yoga Slim 7i Aura Edition (2024), Ubuntu
- **CPU**: Intel Core Ultra 7 258V (2.2 GHz base)
- **RAM**: 32 GB
- **Ollama**: Already running, serving `qwen2.5:7b` on port 11434
- **Python**: 3.12
- **Repo**: `~/local-agent-stack`
- **Existing shopping workflow**: `src/workflows/online-shopping/`
- **Existing tests**: `src/workflows/online-shopping/tests/`

---

## Files to create

### 1. `src/workflows/online-shopping/tests/smoke_test_browser_use.py`

The smoke test script. Full spec in the "Smoke test spec" section below.

### 2. `src/workflows/online-shopping/Dockerfile.browser-use`

```dockerfile
FROM browseruse/browseruse:latest

ENV IN_DOCKER=True
ENV PYTHONUNBUFFERED=1

# browser-use image has the library + Chromium pre-installed.
# We only need to add the Ollama LLM connector.
RUN pip install --no-cache-dir langchain-ollama

WORKDIR /app
```

The official `browseruse/browseruse:latest` image includes browser-use,
Playwright, and Chromium. We only add `langchain-ollama` for the Ollama
connection. Do NOT add `langchain-openai` or any cloud LLM packages.

### 3. Update `docker-compose.yml` (project root)

Add this service alongside the existing services. Place it after the
`smoke-test-stage02a` service:

```yaml
  smoke-test-browser-use:
    profiles: ["tools"]
    build:
      context: ./src/workflows/online-shopping
      dockerfile: Dockerfile.browser-use
    container_name: smoke-test-browser-use
    init: true
    ipc: host
    command: ["python", "/app/tests/smoke_test_browser_use.py"]
    environment:
      - OLLAMA_BASE_URL=http://ollama:11434
      - OLLAMA_LLM_MODEL=qwen2.5:7b
      - IN_DOCKER=true
    volumes:
      - ./src/workflows/online-shopping/tests:/app/tests:ro
    depends_on:
      - ollama
```

**Key settings explained:**

- `init: true` — adds tini as PID 1, prevents zombie Chromium processes
- `ipc: host` — shares host IPC namespace so Chromium has enough shared
  memory (Docker's default 64MB `/dev/shm` causes Chromium crashes).
  Alternative if `ipc: host` causes issues: use `shm_size: '2gb'` instead.
- `profiles: ["tools"]` — matches the existing pattern for test services;
  won't start with a plain `docker compose up -d`
- The test script is bind-mounted read-only so you can iterate without
  rebuilding the image
- `OLLAMA_BASE_URL` points to the Ollama container on the Docker network

**Run with:**

```bash
docker compose --profile tools run --rm smoke-test-browser-use
```

To build fresh and run:

```bash
docker compose --profile tools build smoke-test-browser-use
docker compose --profile tools run --rm smoke-test-browser-use
```

---

## Alternative: Run without Docker

If you prefer to test directly on the server (simpler for debugging),
skip the Dockerfile and docker-compose changes and instead:

```bash
cd ~/local-agent-stack
source venv/bin/activate
pip install browser-use langchain-ollama
playwright install chromium
python src/workflows/online-shopping/tests/smoke_test_browser_use.py
```

This works because Ollama is already running on the host at
`localhost:11434`. The Docker setup is for consistency with the rest
of the stack, but is not required for the POC.

---

## Smoke test spec

### Test parameters

```python
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL = os.getenv("OLLAMA_LLM_MODEL", "qwen2.5:7b")

# Matches the example used in other shopping workflow smoke tests
SEARCH_QUERY = "dusty rose linen tablecloth 60x84"
SEARCH_SITE = "https://www.etsy.com"
MAX_STEPS = 25
```

### Agent setup

Use `langchain-ollama`'s `ChatOllama` as the LLM backend:

```python
from langchain_ollama import ChatOllama
from browser_use import Agent, Browser, BrowserConfig

llm = ChatOllama(
    model=MODEL,
    base_url=OLLAMA_BASE_URL,
    num_ctx=32000,
)
```

Configure the browser to run headless:

```python
browser = Browser(
    config=BrowserConfig(
        headless=True,
    )
)
```

### Agent task

The task prompt should be explicit and structured. The agent needs to:

1. Go to Etsy
2. Search for the product
3. Extract specific fields from the results
4. Return structured data

Write the task as a single string with clear instructions:

```
Go to {SEARCH_SITE} and search for "{SEARCH_QUERY}".

From the search results page, extract the first 5 product listings.
For each listing, extract:
- Product title
- Price
- Product URL (the link to the product page)
- Shop name (the seller)

Return the results as a JSON array. Each item should have keys:
title, price, url, shop_name

If fewer than 5 results appear, return however many are available.
Do not click into individual product pages — extract from the
search results page only.
```

### Agent execution

```python
agent = Agent(
    task=task,
    llm=llm,
    browser=browser,
    max_actions_per_step=3,
    tool_call_in_content=False,
)

result = await agent.run(max_steps=MAX_STEPS)
```

**Important:** `tool_call_in_content=False` is required for Ollama models.
Without it, browser-use may fail to parse tool calls from qwen2.5:7b.

### Output

Print timing and results clearly:

```
=== browser-use + Ollama POC ===

Model:      qwen2.5:7b
Ollama:     http://localhost:11434
Target:     https://www.etsy.com
Query:      dusty rose linen tablecloth 60x84
Max steps:  25
──────────────────────────────────────────

⏳ Running browser-use agent...

✅ Agent completed in {elapsed:.1f} seconds ({steps} steps)

Results:
{json-formatted results}

=== POC complete ===
```

If the agent fails or times out, print the error and any partial results.
Do not swallow exceptions — this is a diagnostic test.

### Cleanup

Always close the browser, even on failure:

```python
try:
    result = await agent.run(max_steps=MAX_STEPS)
finally:
    await browser.close()
```

### Full script structure

```python
#!/usr/bin/env python3
"""
Smoke test — browser-use + Ollama POC
Proves browser-use can search Etsy via qwen2.5:7b running locally.

Run via Docker:
    docker compose --profile tools run --rm smoke-test-browser-use

Run directly:
    cd ~/local-agent-stack
    source venv/bin/activate
    python src/workflows/online-shopping/tests/smoke_test_browser_use.py
"""

import asyncio
import json
import os
import time

from langchain_ollama import ChatOllama
from browser_use import Agent, Browser, BrowserConfig

# Config
OLLAMA_BASE_URL = ...
MODEL = ...
SEARCH_QUERY = ...
SEARCH_SITE = ...
MAX_STEPS = 25

async def main():
    # Print header with config
    # Set up LLM (ChatOllama)
    # Set up browser (headless)
    # Define task string
    # Create agent
    # Run with timing, wrapped in try/finally for browser cleanup
    # Print results and timing
    # Close browser

if __name__ == "__main__":
    asyncio.run(main())
```

The script should be self-contained. No imports from the rest of the
project. No dependency on mem0 or Qdrant.

---

## What success looks like

**Pass:** The agent navigates to Etsy, performs a search, and returns at
least one structured result with a title, price, and URL. The URL should
be a real Etsy product listing (starts with `https://www.etsy.com/listing/`).

**Acceptable but flagged:** The agent completes but results are messy —
JSON not cleanly parsed, some fields missing, or the agent took many
steps. This tells us browser-use works but the task prompt needs tuning.

**Fail:** The agent hangs, crashes, cannot parse tool calls from
qwen2.5:7b, or never reaches the search results page. This tells us
qwen2.5:7b may not be capable enough for browser-use and we may need
a larger model or a different approach.

---

## What to measure and report

After running the test, record:

1. **Total wall-clock time** — how long from start to result
2. **Number of agent steps** — how many actions the agent took
3. **Result quality** — did we get structured product data back?
4. **Error log** — any exceptions, tool call parse failures, or timeouts
5. **browser-use version** — `pip show browser-use | grep Version`

These measurements determine whether browser-use is viable on this
hardware for the shopping workflow.

---

## Known risks and mitigations

**Risk: qwen2.5:7b may struggle with browser-use's tool calling format.**
browser-use was primarily tested with GPT-4o and Claude. Local 7B models
are at the edge of what works reliably. The `tool_call_in_content=False`
flag helps. If tool call parsing fails consistently, try `qwen2.5:14b`
(if VRAM allows) or `llama3.1:8b` as alternatives.

**Risk: Etsy may block or CAPTCHA the headless browser.**
Playwright's default Chromium can be fingerprinted. If Etsy blocks the
request, try running with `headless=False` first to see what happens
visually, then investigate browser-use's stealth options or its cloud
browser offering.

**Risk: Slow performance on CPU-only inference.**
qwen2.5:7b runs on CPU on this hardware. Each agent step requires an
LLM call, and with 15-25 steps expected, the total time could be
5-15 minutes. This is acceptable for a POC — we're testing capability,
not speed.

**Risk: `num_ctx=32000` may cause memory pressure.**
32GB RAM with a 7B model at 32k context should be fine, but monitor
memory usage. If Ollama gets OOM-killed, reduce to `num_ctx=16000`.

**Risk: Chromium crashes in Docker with default `/dev/shm`.**
Docker limits `/dev/shm` to 64MB by default. Chromium needs more.
The docker-compose service uses `ipc: host` to share the host's IPC
namespace. If this causes issues, switch to `shm_size: '2gb'` instead.

---

## What NOT to do

- Do not wire this into the existing search.py or any pipeline stage yet.
  This is a standalone POC.
- Do not install any cloud LLM packages (openai, anthropic, etc.).
- Do not use browser-use's cloud browser feature. Local Playwright only.
- Do not try to search Amazon or Google Shopping in this POC. Etsy only.
- Do not spend time on error recovery or retries. If it fails, report
  the failure clearly.

---

## After the POC

If the test passes, the next steps are:

1. Test against Amazon (harder anti-bot) to see if browser-use can
   handle it, or if we need a hybrid approach (browser-use for
   scrape-friendly sites, SERP API for Amazon/Google)
2. Refine the task prompt to get cleaner structured output
3. Integrate browser-use as the search tool in stage 02, replacing
   the current stubs in `src/workflows/online-shopping/02-search/tools/search.py`
4. Add browser-use and langchain-ollama to the project's requirements
5. Update CLAUDE.md and docs/architecture.md to reflect browser-use

If the test fails, we revisit the three options: SERP API, Playwright
with manual scraping logic, or a larger local model.
