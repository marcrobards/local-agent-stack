#!/usr/bin/env python3
"""
Smoke test — Stage 02 search.py
Exercises search_source() against a single source using Browser Use Cloud.

Run via Docker:
    docker compose --profile tools run --rm smoke-test-search

    Override source and query via env vars:
    SEARCH_SOURCE=amazon SEARCH_QUERY="dusty rose tablecloth" \
        docker compose --profile tools run --rm smoke-test-search

Run directly:
    cd ~/local-agent-stack
    source venv/bin/activate
    python src/workflows/online-shopping/tests/smoke_test_search.py

Env vars:
    ANTHROPIC_API_KEY       — required (unless SEARCH_LLM=browser-use)
    BROWSER_USE_API_KEY     — required
    SEARCH_SOURCE           — optional, default: etsy
    SEARCH_QUERY            — optional, default: dusty rose linen tablecloth 60x84
    SEARCH_LLM              — optional: anthropic (default) or browser-use
    ANTHROPIC_MODEL         — optional, default: claude-sonnet-4-0
    SEARCH_MAX_RESULTS      — optional, default: 10
    SEARCH_MAX_STEPS        — optional, default: 15
"""

import asyncio
import json
import os
import sys

# search.py lives alongside this test file in the same directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from search import search_source, format_results, SOURCE_CONFIG

SEARCH_QUERY = os.getenv("SEARCH_QUERY", "dusty rose linen tablecloth 60x84")
SEARCH_SOURCE = os.getenv("SEARCH_SOURCE", "etsy")


async def main():
    if SEARCH_SOURCE not in SOURCE_CONFIG:
        print(f"❌ Unknown source: {SEARCH_SOURCE!r}")
        print(f"   Supported: {list(SOURCE_CONFIG.keys())}")
        sys.exit(1)

    label = SOURCE_CONFIG[SEARCH_SOURCE]["label"]

    print("=== Stage 02 search smoke test ===")
    print()
    print(f"Source:  {label}")
    print(f"Query:   {SEARCH_QUERY}")
    print(f"LLM:     {os.getenv('SEARCH_LLM', 'anthropic')} / {os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-4-0')}")
    print("─" * 42)
    print()

    print(f"  🔍 Searching {label}...", flush=True)
    result = await search_source(SEARCH_QUERY, SEARCH_SOURCE)

    if result.error:
        print(f"❌ Search failed after {result.elapsed:.1f}s")
        print(f"   Error: {result.error}")
        sys.exit(1)

    print(f"✅ Search completed in {result.elapsed:.1f}s — {len(result.candidates)} candidates")
    print()

    # Human-readable output (matches PROMPT.md format)
    print(format_results([result]))
    print()

    # Raw JSON for pipeline consumption
    print("--- JSON output ---")
    candidates_json = [
        {
            "source": c.source,
            "url": c.url,
            "title": c.title,
            "price": c.price,
            "shop_name": c.shop_name,
            "match_reason": c.match_reason,
        }
        for c in result.candidates
    ]
    print(json.dumps(candidates_json, indent=2))
    print()
    print("=== smoke test complete ===")


if __name__ == "__main__":
    asyncio.run(main())
