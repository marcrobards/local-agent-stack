"""
Stage 2 — Search (spec §4, Stage 2)

One Browser Use Cloud v3 agent task per SearchTarget, all launched concurrently.
Each task searches a site and extracts RawCandidate data. No judgment — pure extraction.

Env vars:
    BROWSER_USE_API_KEY  — required
    ANTHROPIC_API_KEY    — required when SEARCH_LLM=anthropic (default)
    SEARCH_LLM           — "anthropic" (default) or "browser-use"
    SEARCH_MAX_RESULTS   — per-site result cap (default: 10)
    SEARCH_MAX_STEPS     — max browser agent steps (default: 15)
"""

import asyncio
import json
import logging
import re
import time
from typing import Optional
from urllib.parse import quote_plus

import config
from models import ProductSpec, RawCandidate, SearchTarget, SearchTaskResult

log = logging.getLogger("shopping_agent.search")


# ---------------------------------------------------------------------------
# Query builder
# ---------------------------------------------------------------------------

def build_query(spec: ProductSpec) -> str:
    """Build a search query string from the ProductSpec."""
    parts = [spec.item_type]
    if spec.color_description:
        parts.append(spec.color_description.split("—")[0].strip())
    if spec.dimensions:
        parts.append(spec.dimensions)
    if spec.material:
        parts.append(spec.material)
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Search URL builder
# ---------------------------------------------------------------------------

# Common site search URL patterns.  For sites not listed here the agent
# navigates to the site and searches manually.
_SITE_SEARCH_PATTERNS: dict[str, dict] = {
    "amazon.com": {"url": "https://www.amazon.com/s", "param": "k"},
    "etsy.com": {"url": "https://www.etsy.com/search", "param": "q"},
    "walmart.com": {"url": "https://www.walmart.com/search", "param": "q"},
    "target.com": {"url": "https://www.target.com/s", "param": "searchTerm"},
    "poshmark.com": {"url": "https://poshmark.com/search", "param": "query"},
    "wayfair.com": {"url": "https://www.wayfair.com/keyword.php", "param": "keyword"},
    "google.com": {"url": "https://www.google.com/search", "param": "q", "suffix": "&tbm=shop"},
}


def _search_url_for(site: str, query: str) -> Optional[str]:
    """Return a direct search URL for a known site, or None."""
    domain = site.lower().strip().removeprefix("www.")
    cfg = _SITE_SEARCH_PATTERNS.get(domain)
    if not cfg:
        return None
    url = f"{cfg['url']}?{cfg['param']}={quote_plus(query)}"
    if "suffix" in cfg:
        url += cfg["suffix"]
    return url


# ---------------------------------------------------------------------------
# Browser Use task prompt
# ---------------------------------------------------------------------------

def _build_task(query: str, target: SearchTarget, max_results: int) -> str:
    """Build the browser agent task string for a SearchTarget."""
    search_url = _search_url_for(target.site, query)

    if search_url:
        nav_instruction = f"Go to this URL: {search_url}"
    else:
        nav_instruction = (
            f"Go to https://www.{target.site} and search for: \"{query}\""
        )

    return f"""{nav_instruction}

You are searching {target.site} for: "{query}"

From the search results page, find up to {max_results} product listings that look relevant.

For each promising listing, open its product page and extract:
- Product title (as listed on the page)
- Price (as shown, including sale price if present)
- Full product URL (the direct link to this product page)
- Product image URLs (the src of 1–3 product images on the page)
- Seller/vendor name
- Full product description text
- Any structured specs visible (dimensions, material, available sizes/colors)

When you have collected the listings, call the done action immediately with ONLY a JSON array. Do not add any prose. Each item must have these keys:
  title, price, url, image_urls, vendor, description, specs

If fewer than {max_results} results exist, return however many there are.
If the page fails to load or returns no results, call done with an empty array: []
"""


# ---------------------------------------------------------------------------
# LLM + Browser factory
# ---------------------------------------------------------------------------

def _make_llm():
    """Build the LLM instance for Browser Use."""
    from browser_use import ChatAnthropic

    if config.SEARCH_LLM.lower() == "browser-use":
        from browser_use import ChatBrowserUse
        return ChatBrowserUse()

    if not config.ANTHROPIC_API_KEY:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set. "
            "Set it in .env or use SEARCH_LLM=browser-use."
        )
    return ChatAnthropic(model=config.ANTHROPIC_MODEL)


# ---------------------------------------------------------------------------
# Result parsing
# ---------------------------------------------------------------------------

def parse_raw_results(raw: Optional[str], site: str) -> list[RawCandidate]:
    """Parse Browser Use agent output into RawCandidate objects."""
    if not raw:
        return []

    # Strip markdown fences
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
    # Strip triple-quote wrappers
    cleaned = re.sub(r'^"{3}', "", cleaned)
    cleaned = re.sub(r'"{3}$', "", cleaned).strip()
    # Unescape
    if r'\"' in cleaned:
        cleaned = cleaned.replace(r'\"', '"')

    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if not match:
        log.warning("search  %s: no JSON array in output (%d chars)", site, len(raw))
        return []

    try:
        items = json.loads(match.group())
    except json.JSONDecodeError as exc:
        log.warning("search  %s: JSON parse error: %s", site, exc)
        return []

    candidates = []
    for item in items:
        if not isinstance(item, dict):
            continue
        url = item.get("url", "").strip()
        title = item.get("title", "").strip()
        if not url or not title:
            continue

        # Normalize image_urls — agent may return string or list
        img = item.get("image_urls") or item.get("image_url")
        if isinstance(img, str):
            image_urls = [img] if img else []
        elif isinstance(img, list):
            image_urls = [u for u in img if isinstance(u, str) and u]
        else:
            image_urls = []

        # Normalize specs — may be string or dict
        specs = item.get("specs")
        if isinstance(specs, str):
            specs = {"raw": specs} if specs else None

        candidates.append(RawCandidate(
            url=url,
            title=title,
            price=item.get("price"),
            vendor=item.get("vendor") or item.get("shop_name") or site,
            description=item.get("description"),
            specs=specs,
            image_urls=image_urls,
            source_site=site,
        ))

    return candidates


# ---------------------------------------------------------------------------
# Single-site search
# ---------------------------------------------------------------------------

async def search_site(query: str, target: SearchTarget) -> SearchTaskResult:
    """Search a single site using Browser Use Cloud. Returns a SearchTaskResult."""
    log.info("search_site  site=%s  query=%s", target.site, query)
    result = SearchTaskResult(site=target.site)
    start = time.time()

    if not config.BROWSER_USE_API_KEY:
        result.error = "BROWSER_USE_API_KEY not set"
        return result

    from browser_use import Agent, Browser

    task = _build_task(query, target, config.SEARCH_MAX_RESULTS)
    llm = _make_llm()
    browser = Browser(use_cloud=True, cloud_proxy_country_code="us")

    try:
        agent = Agent(
            task=task,
            llm=llm,
            browser=browser,
            max_actions_per_step=3,
            tool_call_in_content=False,
        )
        run_result = await agent.run(max_steps=config.SEARCH_MAX_STEPS)
        raw_output = run_result.final_result()
        log.info(
            "search_site  site=%s  raw_len=%s",
            target.site, len(raw_output) if raw_output else 0,
        )
        result.candidates = parse_raw_results(raw_output, target.site)
    except Exception as exc:
        log.warning("search_site  site=%s  error=%s", target.site, exc, exc_info=True)
        result.error = str(exc)
    finally:
        elapsed = time.time() - start
        log.info(
            "search_site  site=%s  candidates=%d  error=%s  elapsed=%.1fs",
            target.site, len(result.candidates), result.error, elapsed,
        )
        try:
            await browser.stop()
        except Exception:
            pass

    return result


# ---------------------------------------------------------------------------
# Multi-site search (Step 5 — all sites in parallel)
# ---------------------------------------------------------------------------

async def search_all(spec: ProductSpec) -> list[SearchTaskResult]:
    """Search all sites in spec.search_targets concurrently.
    Returns one SearchTaskResult per target. Errors are captured, not raised."""
    query = build_query(spec)
    log.info(
        "search_all  query=%s  targets=%s",
        query, [t.site for t in spec.search_targets],
    )

    results = await asyncio.gather(
        *(search_site(query, t) for t in spec.search_targets)
    )

    total = sum(len(r.candidates) for r in results)
    errors = sum(1 for r in results if r.error)
    log.info("search_all  total_candidates=%d  errors=%d", total, errors)
    return list(results)


def flatten_candidates(results: list[SearchTaskResult]) -> list[RawCandidate]:
    """Flatten per-site results into a single candidate list, dropping errored sites."""
    return [c for r in results if not r.error for c in r.candidates]
