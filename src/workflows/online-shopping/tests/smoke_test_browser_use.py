#!/usr/bin/env python3
"""
Smoke test — browser-use + Claude Sonnet POC
Proves browser-use can search Etsy via claude-sonnet-4-0 (cloud).

Run via Docker:
    docker compose --profile tools run --rm smoke-test-browser-use

Run directly:
    cd ~/local-agent-stack
    source venv/bin/activate
    python src/workflows/online-shopping/tests/smoke_test_browser_use.py

Env vars:
    ANTHROPIC_API_KEY       — required
    BROWSER_USE_API_KEY     — required (Browser Use Cloud stealth browser)
    ANTHROPIC_MODEL         — optional, default: claude-sonnet-4-0
"""

import asyncio
import json
import os
import time

from browser_use import Agent, Browser, ChatAnthropic

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-0")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
BROWSER_USE_API_KEY = os.getenv("BROWSER_USE_API_KEY")

SEARCH_QUERY = "dusty rose linen tablecloth 60x84"
SEARCH_SITE = "https://www.etsy.com"
MAX_STEPS = 15  # Claude is much more efficient — 15 is plenty


async def main():
    if not ANTHROPIC_API_KEY:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set. "
            "Add it to your .env or pass it via the environment."
        )

    if not BROWSER_USE_API_KEY:
        raise EnvironmentError(
            "BROWSER_USE_API_KEY is not set. "
            "Get a key at https://cloud.browser-use.com and add it to your .env."
        )

    print("=== browser-use + Claude Sonnet POC ===")
    print()
    print(f"Model:      {MODEL}")
    print(f"Target:     {SEARCH_SITE}")
    print(f"Query:      {SEARCH_QUERY}")
    print(f"Max steps:  {MAX_STEPS}")
    print(f"Browser:    Browser Use Cloud (stealth)")
    print("─" * 42)
    print()

    llm = ChatAnthropic(model=MODEL)

    browser = Browser(
        use_cloud=True,
        cloud_proxy_country_code="us",
    )

    task = (
        f'Go to {SEARCH_SITE} and search for "{SEARCH_QUERY}".\n'
        f"\n"
        f"From the search results page, extract the first 5 product listings.\n"
        f"For each listing, extract:\n"
        f"- Product title\n"
        f"- Price\n"
        f"- Product URL (the link to the product page)\n"
        f"- Shop name (the seller)\n"
        f"\n"
        f"Return the results as a JSON array. Each item should have keys:\n"
        f"title, price, url, shop_name\n"
        f"\n"
        f"If fewer than 5 results appear, return however many are available.\n"
        f"Do not click into individual product pages — extract from the\n"
        f"search results page only."
    )

    agent = Agent(
        task=task,
        llm=llm,
        browser=browser,
        max_actions_per_step=3,
        tool_call_in_content=False,
    )

    print("⏳ Running browser-use agent...")
    print()

    start = time.time()
    try:
        result = await agent.run(max_steps=MAX_STEPS)
        elapsed = time.time() - start

        final_result = result.final_result()
        history = result.history

        print(f"✅ Agent completed in {elapsed:.1f} seconds ({len(history)} steps)")
        print()
        print("Results:")

        if final_result:
            try:
                parsed = json.loads(final_result)
                print(json.dumps(parsed, indent=2))
            except json.JSONDecodeError:
                print(final_result)
        else:
            print("(no final result returned by agent)")

    except Exception as exc:
        elapsed = time.time() - start
        print(f"❌ Agent failed after {elapsed:.1f} seconds")
        print(f"Error: {exc}")
        raise

    finally:
        try:
            await browser.stop()
        except (AttributeError, Exception):
            pass

    print()
    print("=== POC complete ===")


if __name__ == "__main__":
    asyncio.run(main())