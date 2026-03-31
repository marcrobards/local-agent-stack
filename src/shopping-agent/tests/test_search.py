"""Validate Stage 2 — Search logic (Step 4 verification).

Tests query building, URL building, result parsing, and async flow
without hitting Browser Use Cloud.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models import ProductSpec, RawCandidate, SearchTarget, SearchTaskResult
from stages.search import (
    build_query,
    flatten_candidates,
    parse_raw_results,
    _search_url_for,
    _build_task,
)


# ---------------------------------------------------------------------------
# Query builder
# ---------------------------------------------------------------------------

class TestBuildQuery:
    def test_basic(self):
        spec = ProductSpec(
            item_type="linen tablecloth",
            color_description="dusty rose",
        )
        assert build_query(spec) == "linen tablecloth dusty rose"

    def test_with_dimensions_and_material(self):
        spec = ProductSpec(
            item_type="area rug",
            color_description="navy blue — deep, saturated",
            dimensions="8x10 feet",
            material="wool",
        )
        q = build_query(spec)
        assert "area rug" in q
        assert "navy blue" in q
        assert "8x10 feet" in q
        assert "wool" in q

    def test_color_dash_stripped(self):
        spec = ProductSpec(
            item_type="watch band",
            color_description="forest green — dark, rich",
        )
        q = build_query(spec)
        assert "forest green" in q
        assert "dark, rich" not in q


# ---------------------------------------------------------------------------
# URL builder
# ---------------------------------------------------------------------------

class TestSearchUrl:
    def test_known_site_amazon(self):
        url = _search_url_for("amazon.com", "dusty rose tablecloth")
        assert url.startswith("https://www.amazon.com/s?k=")
        assert "dusty+rose+tablecloth" in url

    def test_known_site_etsy(self):
        url = _search_url_for("etsy.com", "linen napkins")
        assert url.startswith("https://www.etsy.com/search?q=")

    def test_known_site_google_shopping(self):
        url = _search_url_for("google.com", "test")
        assert "&tbm=shop" in url

    def test_www_prefix_stripped(self):
        url = _search_url_for("www.amazon.com", "test")
        assert url is not None
        assert "amazon.com" in url

    def test_unknown_site_returns_none(self):
        assert _search_url_for("bandwerk.com", "watch band") is None
        assert _search_url_for("rugsusa.com", "rug") is None


# ---------------------------------------------------------------------------
# Task builder
# ---------------------------------------------------------------------------

class TestBuildTask:
    def test_known_site_includes_url(self):
        target = SearchTarget(site="etsy.com", rationale="Handmade linens")
        task = _build_task("dusty rose tablecloth", target, 10)
        assert "https://www.etsy.com/search" in task
        assert "dusty rose tablecloth" in task
        assert "10" in task

    def test_unknown_site_navigates_to_domain(self):
        target = SearchTarget(site="bandwerk.com", rationale="Watch band specialist")
        task = _build_task("green watch band", target, 5)
        assert "https://www.bandwerk.com" in task
        assert "search for" in task


# ---------------------------------------------------------------------------
# Result parsing
# ---------------------------------------------------------------------------

class TestParseRawResults:
    def test_valid_json_array(self):
        raw = json.dumps([
            {
                "title": "Dusty Rose Linen Tablecloth",
                "price": "$45.00",
                "url": "https://etsy.com/listing/123",
                "image_urls": ["https://cdn.etsy.com/img1.jpg"],
                "vendor": "LinenCraft",
                "description": "Beautiful handmade linen tablecloth",
                "specs": {"size": "60x84", "material": "linen"},
            },
            {
                "title": "Pink Tablecloth",
                "price": "$29.99",
                "url": "https://etsy.com/listing/456",
                "image_urls": [],
                "vendor": "TableShop",
                "description": None,
                "specs": None,
            },
        ])

        candidates = parse_raw_results(raw, "etsy.com")
        assert len(candidates) == 2
        assert candidates[0].title == "Dusty Rose Linen Tablecloth"
        assert candidates[0].price == "$45.00"
        assert candidates[0].source_site == "etsy.com"
        assert candidates[0].vendor == "LinenCraft"
        assert len(candidates[0].image_urls) == 1
        assert candidates[0].specs == {"size": "60x84", "material": "linen"}

    def test_markdown_fenced_json(self):
        raw = '```json\n[{"title": "Test", "url": "https://example.com/1", "vendor": "V"}]\n```'
        candidates = parse_raw_results(raw, "example.com")
        assert len(candidates) == 1
        assert candidates[0].title == "Test"

    def test_image_url_string_normalized_to_list(self):
        raw = json.dumps([{
            "title": "Product",
            "url": "https://example.com/p",
            "image_url": "https://cdn.example.com/img.jpg",
            "vendor": "Shop",
        }])
        candidates = parse_raw_results(raw, "example.com")
        assert candidates[0].image_urls == ["https://cdn.example.com/img.jpg"]

    def test_specs_string_normalized_to_dict(self):
        raw = json.dumps([{
            "title": "Product",
            "url": "https://example.com/p",
            "vendor": "Shop",
            "specs": "60x84 inches, linen",
        }])
        candidates = parse_raw_results(raw, "example.com")
        assert candidates[0].specs == {"raw": "60x84 inches, linen"}

    def test_skips_items_without_url(self):
        raw = json.dumps([
            {"title": "No URL", "vendor": "Shop"},
            {"title": "Has URL", "url": "https://example.com/1", "vendor": "Shop"},
        ])
        candidates = parse_raw_results(raw, "example.com")
        assert len(candidates) == 1

    def test_skips_items_without_title(self):
        raw = json.dumps([
            {"url": "https://example.com/1", "vendor": "Shop"},
        ])
        candidates = parse_raw_results(raw, "example.com")
        assert len(candidates) == 0

    def test_empty_input(self):
        assert parse_raw_results(None, "x") == []
        assert parse_raw_results("", "x") == []

    def test_no_json_array(self):
        assert parse_raw_results("No results found on this page.", "x") == []

    def test_escaped_json(self):
        raw = r'[{\"title\": \"Escaped\", \"url\": \"https://example.com/1\", \"vendor\": \"V\"}]'
        candidates = parse_raw_results(raw, "example.com")
        assert len(candidates) == 1

    def test_vendor_falls_back_to_site(self):
        raw = json.dumps([{
            "title": "Product",
            "url": "https://example.com/p",
        }])
        candidates = parse_raw_results(raw, "example.com")
        assert candidates[0].vendor == "example.com"

    def test_preamble_before_json(self):
        raw = 'Here are the results I found:\n\n[{"title": "A", "url": "https://e.com/1", "vendor": "V"}]'
        candidates = parse_raw_results(raw, "e.com")
        assert len(candidates) == 1


# ---------------------------------------------------------------------------
# Flatten candidates
# ---------------------------------------------------------------------------

class TestFlattenCandidates:
    def test_merges_successful_results(self):
        results = [
            SearchTaskResult(
                site="etsy.com",
                candidates=[
                    RawCandidate(url="https://etsy.com/1", title="A", vendor="V", source_site="etsy.com"),
                    RawCandidate(url="https://etsy.com/2", title="B", vendor="V", source_site="etsy.com"),
                ],
            ),
            SearchTaskResult(
                site="amazon.com",
                candidates=[
                    RawCandidate(url="https://amazon.com/1", title="C", vendor="V", source_site="amazon.com"),
                ],
            ),
        ]
        flat = flatten_candidates(results)
        assert len(flat) == 3

    def test_skips_errored_sites(self):
        results = [
            SearchTaskResult(site="blocked.com", error="403 Forbidden"),
            SearchTaskResult(
                site="etsy.com",
                candidates=[
                    RawCandidate(url="https://etsy.com/1", title="A", vendor="V", source_site="etsy.com"),
                ],
            ),
        ]
        flat = flatten_candidates(results)
        assert len(flat) == 1
        assert flat[0].source_site == "etsy.com"

    def test_empty_results(self):
        assert flatten_candidates([]) == []


# ---------------------------------------------------------------------------
# Async search_site (mocked Browser Use)
# ---------------------------------------------------------------------------

class TestSearchSite:
    @pytest.mark.asyncio
    async def test_single_site_returns_task_result(self):
        import sys

        mock_raw = json.dumps([{
            "title": "Test Product",
            "url": "https://etsy.com/listing/999",
            "price": "$30.00",
            "vendor": "TestSeller",
            "image_urls": ["https://cdn.etsy.com/img.jpg"],
            "description": "A great product",
            "specs": None,
        }])

        mock_run_result = MagicMock()
        mock_run_result.final_result.return_value = mock_raw

        mock_agent_cls = MagicMock()
        mock_agent_instance = MagicMock()
        mock_agent_instance.run = AsyncMock(return_value=mock_run_result)
        mock_agent_cls.return_value = mock_agent_instance

        mock_browser_cls = MagicMock()
        mock_browser_instance = MagicMock()
        mock_browser_instance.stop = AsyncMock()
        mock_browser_cls.return_value = mock_browser_instance

        mock_browser_use = MagicMock()
        mock_browser_use.Agent = mock_agent_cls
        mock_browser_use.Browser = mock_browser_cls
        mock_browser_use.ChatAnthropic = MagicMock()

        with patch.dict(sys.modules, {"browser_use": mock_browser_use}), \
             patch("stages.search.config") as mock_config:
            mock_config.BROWSER_USE_API_KEY = "test-key"
            mock_config.ANTHROPIC_API_KEY = "test-key"
            mock_config.SEARCH_LLM = "anthropic"
            mock_config.ANTHROPIC_MODEL = "claude-sonnet-4-0"
            mock_config.SEARCH_MAX_RESULTS = 10
            mock_config.SEARCH_MAX_STEPS = 15

            from stages.search import search_site
            target = SearchTarget(site="etsy.com", rationale="Good for handmade")
            result = await search_site("dusty rose tablecloth", target)

        assert isinstance(result, SearchTaskResult)
        assert result.site == "etsy.com"
        assert result.error is None
        assert len(result.candidates) == 1
        assert result.candidates[0].title == "Test Product"
        assert result.candidates[0].source_site == "etsy.com"

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_error(self):
        with patch("stages.search.config") as mock_config:
            mock_config.BROWSER_USE_API_KEY = ""

            from stages.search import search_site
            target = SearchTarget(site="etsy.com", rationale="test")
            result = await search_site("test query", target)

        assert result.error == "BROWSER_USE_API_KEY not set"
        assert result.candidates == []


# ---------------------------------------------------------------------------
# Async search_all (mocked)
# ---------------------------------------------------------------------------

class TestSearchAll:
    @pytest.mark.asyncio
    async def test_parallel_search_returns_all_results(self):
        async def fake_search_site(query, target):
            return SearchTaskResult(
                site=target.site,
                candidates=[
                    RawCandidate(
                        url=f"https://{target.site}/1",
                        title=f"Product from {target.site}",
                        vendor="V",
                        source_site=target.site,
                    )
                ],
            )

        spec = ProductSpec(
            item_type="tablecloth",
            color_description="dusty rose",
            search_targets=[
                SearchTarget(site="etsy.com", rationale="Handmade"),
                SearchTarget(site="amazon.com", rationale="Wide selection"),
            ],
            confirmed=True,
        )

        with patch("stages.search.search_site", side_effect=fake_search_site):
            from stages.search import search_all
            results = await search_all(spec)

        assert len(results) == 2
        sites = {r.site for r in results}
        assert sites == {"etsy.com", "amazon.com"}
        total = sum(len(r.candidates) for r in results)
        assert total == 2
