"""
Search tool — Stage 02
Accepts a product spec and searches each configured source using Browser Use Cloud.
Returns candidate product listings grouped by source.

Env vars:
    ANTHROPIC_API_KEY       — required if SEARCH_LLM=anthropic (default)
    BROWSER_USE_API_KEY     — required
    SEARCH_LLM              — optional: "anthropic" (default) or "browser-use"
    ANTHROPIC_MODEL         — optional, default: claude-sonnet-4-0
    SEARCH_MAX_RESULTS      — optional, default: 10
    SEARCH_MAX_STEPS        — optional, default: 15

Usage (standalone):
    python search.py "dusty rose linen tablecloth 60x84" [source]

    source is optional — omit to search all sources, or pass one of:
    amazon, google_shopping, etsy, target, walmart, poshmark

    Poshmark is only searched when explicitly requested or when the spec
    includes is_clothing=True.
"""

import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

from browser_use import Agent, Browser, ChatAnthropic

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SEARCH_LLM = os.getenv("SEARCH_LLM", "anthropic").lower()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-0")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
BROWSER_USE_API_KEY = os.getenv("BROWSER_USE_API_KEY")
MAX_RESULTS = int(os.getenv("SEARCH_MAX_RESULTS", "10"))
MAX_STEPS = int(os.getenv("SEARCH_MAX_STEPS", "15"))

SUPPORTED_SOURCES = ["amazon", "google_shopping", "etsy", "target", "walmart", "poshmark"]

# Source URLs and search patterns
SOURCE_CONFIG = {
    "amazon": {
        "url": "https://www.amazon.com/s",
        "param": "k",
        "label": "Amazon",
    },
    "google_shopping": {
        "url": "https://www.google.com/search",
        "param": "q",
        "label": "Google Shopping",
        "suffix": "&tbm=shop",
    },
    "etsy": {
        "url": "https://www.etsy.com/search",
        "param": "q",
        "label": "Etsy",
    },
    "target": {
        "url": "https://www.target.com/s",
        "param": "searchTerm",
        "label": "Target",
    },
    "walmart": {
        "url": "https://www.walmart.com/search",
        "param": "q",
        "label": "Walmart",
    },
    "poshmark": {
        "url": "https://poshmark.com/search",
        "param": "query",
        "label": "Poshmark",
    },
}


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    url: str
    title: str
    price: Optional[str]
    match_reason: str
    source: str
    shop_name: Optional[str] = None


@dataclass
class SearchResult:
    source: str
    query: str
    candidates: list[Candidate] = field(default_factory=list)
    error: Optional[str] = None
    elapsed: float = 0.0


# ---------------------------------------------------------------------------
# LLM factory
# ---------------------------------------------------------------------------

def _make_llm():
    """Build the LLM instance based on SEARCH_LLM env var."""
    if SEARCH_LLM == "browser-use":
        try:
            from browser_use import ChatBrowserUse
            return ChatBrowserUse()
        except ImportError:
            raise ImportError(
                "SEARCH_LLM=browser-use requires browser-use>=0.12 with ChatBrowserUse. "
                "Fall back to SEARCH_LLM=anthropic or upgrade browser-use."
            )
    else:
        # Default: anthropic
        if not ANTHROPIC_API_KEY:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY is not set. "
                "Add it to your .env or set SEARCH_LLM=browser-use to use "
                "the Browser Use Cloud model instead."
            )
        return ChatAnthropic(model=ANTHROPIC_MODEL)


# ---------------------------------------------------------------------------
# Core search function
# ---------------------------------------------------------------------------

async def search_source(query: str, source: str) -> SearchResult:
    """
    Search a single source for products matching the query.
    Uses a Browser Use Cloud agent to perform the search and extract results.

    Args:
        query: Search query string built from the product spec.
        source: One of the SUPPORTED_SOURCES.

    Returns:
        SearchResult with candidates list (may be empty on failure).
    """
    source = source.lower().strip()
    if source not in SUPPORTED_SOURCES:
        raise ValueError(f"Unknown source: {source!r}. Supported: {SUPPORTED_SOURCES}")

    if not BROWSER_USE_API_KEY:
        raise EnvironmentError(
            "BROWSER_USE_API_KEY is not set. "
            "Get a key at https://cloud.browser-use.com."
        )

    cfg = SOURCE_CONFIG[source]
    label = cfg["label"]
    result = SearchResult(source=source, query=query)
    start = time.time()

    task = _build_task(query, source, cfg, MAX_RESULTS)

    llm = _make_llm()
    browser = Browser(use_cloud=True, cloud_proxy_country_code="us")

    try:
        agent = Agent(
            task=task,
            llm=llm,
            browser=browser,
            max_actions_per_step=3,
            tool_call_in_content=False,
            skills=['75d9f278-01ba-48e6-be98-ac4783985527'],
        )
        run_result = await agent.run(max_steps=MAX_STEPS)
        raw = run_result.final_result()
        result.candidates = _parse_results(raw, source, label)
    except Exception as exc:
        result.error = str(exc)
    finally:
        result.elapsed = time.time() - start
        try:
            await browser.stop()
        except Exception:
            pass

    return result


def _build_task(query: str, source: str, cfg: dict, max_results: int) -> str:
    """Build the browser agent task string for a given source."""
    label = cfg["label"]

    # Construct the search URL directly so the agent doesn't waste steps
    # navigating to the homepage first.
    search_url = f"{cfg['url']}?{cfg['param']}={query.replace(' ', '+')}"
    if "suffix" in cfg:
        search_url += cfg["suffix"]

    shop_field = ""
    if source in ("etsy", "poshmark"):
        shop_field = '\n- Shop name / seller (if visible)'

    return f"""Go to this URL: {search_url}

You are searching {label} for: "{query}"

From the search results page, extract up to {max_results} product listings that could plausibly match this search. Do not open individual product pages.

For each listing extract:
- Product title (as listed)
- Price (if visible; include sale price if shown)
- Full product URL (the direct link to the product page){shop_field}
- One short phrase explaining why it is a plausible match (based on title/description only — do not evaluate color)

Ignore sponsored listings, ads, and unrelated category results.

Return ONLY a JSON array. No prose before or after. Each item must have these keys:
  title, price, url, match_reason{', shop_name' if source in ('etsy', 'poshmark') else ''}

If fewer than {max_results} plausible results exist, return however many there are.
If the page fails to load or returns no results, return an empty array: []
"""


def _parse_results(raw: Optional[str], source: str, label: str) -> list[Candidate]:
    """
    Parse the agent's raw string output into a list of Candidate objects.
    Handles JSON wrapped in markdown code fences.
    """
    if not raw:
        return []

    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()

    # Find the JSON array (agent sometimes adds preamble text)
    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if not match:
        return []

    try:
        items = json.loads(match.group())
    except json.JSONDecodeError:
        return []

    candidates = []
    for item in items:
        if not isinstance(item, dict):
            continue
        url = item.get("url", "").strip()
        title = item.get("title", "").strip()
        if not url or not title:
            continue
        candidates.append(Candidate(
            url=url,
            title=title,
            price=item.get("price"),
            match_reason=item.get("match_reason", ""),
            source=source,
            shop_name=item.get("shop_name"),
        ))
    return candidates


# ---------------------------------------------------------------------------
# Multi-source search
# ---------------------------------------------------------------------------

async def search_all(
    query: str,
    sources: Optional[list[str]] = None,
    is_clothing: bool = False,
) -> list[SearchResult]:
    """
    Search all relevant sources sequentially and return results.

    Args:
        query:       The search query string.
        sources:     Explicit list of sources to search. If None, uses defaults.
        is_clothing: If True, Poshmark is included in default source list.

    Returns:
        List of SearchResult, one per source, in order searched.
    """
    if sources is None:
        sources = ["amazon", "google_shopping", "etsy", "target", "walmart"]
        if is_clothing:
            sources.append("poshmark")

    labels = [SOURCE_CONFIG[s]["label"] for s in sources]
    print(f"  🔍 Searching {', '.join(labels)} concurrently...", flush=True)

    results = await asyncio.gather(*(search_source(query, s) for s in sources))

    for result in results:
        label = SOURCE_CONFIG[result.source]["label"]
        status = f"✅ {len(result.candidates)} candidates" if not result.error else f"❌ {result.error}"
        print(f"     {label}: {status} ({result.elapsed:.1f}s)", flush=True)

    return list(results)


def format_results(results: list[SearchResult]) -> str:
    """Format search results as a readable candidate list (matches PROMPT.md output format)."""
    lines = []
    total = 0

    for result in results:
        label = SOURCE_CONFIG[result.source]["label"]
        if result.error:
            lines.append(f"\n## {label}\nError: {result.error}\n")
            continue
        if not result.candidates:
            lines.append(f"\n## {label}\n(no results)\n")
            continue

        lines.append(f"\n## {label}")
        for c in result.candidates:
            lines.append(f"\nSource: {label}")
            lines.append(f"URL: {c.url}")
            lines.append(f"Title: {c.title}")
            lines.append(f"Price: {c.price or 'not listed'}")
            if c.shop_name:
                lines.append(f"Shop: {c.shop_name}")
            lines.append(f"Match reason: {c.match_reason}")
            total += 1

    lines.insert(0, f"# Search results — {total} total candidates")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

async def _main():
    query = sys.argv[1] if len(sys.argv) > 1 else "dusty rose linen tablecloth 60x84"
    source_arg = sys.argv[2] if len(sys.argv) > 2 else None

    print(f"Query: {query}")
    if source_arg:
        print(f"Source: {source_arg}")
        results = [await search_source(query, source_arg)]
    else:
        print("Sources: all (non-clothing defaults)")
        results = await search_all(query)

    print()
    print(format_results(results))
    print()

    # Also dump raw JSON for pipeline consumption
    all_candidates = []
    for r in results:
        for c in r.candidates:
            all_candidates.append({
                "source": c.source,
                "url": c.url,
                "title": c.title,
                "price": c.price,
                "shop_name": c.shop_name,
                "match_reason": c.match_reason,
            })

    print("--- JSON output ---")
    print(json.dumps(all_candidates, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())