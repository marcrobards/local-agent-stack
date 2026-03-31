"""Validate Stage 4 — Present logic (Step 7 verification).

Tests card building, markdown rendering, and edge cases.
"""

import pytest

from models import (
    PresentationResult,
    ProductSpec,
    RawCandidate,
    ResultCard,
    VerifiedCandidate,
)
from stages.present import present, _render_card_md, _to_result_card


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def spec():
    return ProductSpec(
        item_type="linen tablecloth",
        color_description="dusty rose — muted warm pink",
        dimensions="60x84 inches",
        material="linen",
    )


def _make_verified(
    title="Product",
    url="https://example.com/1",
    price="$45.00",
    vendor="Shop",
    confidence="HIGH",
    color="PASS",
    color_desc="Warm muted pink",
    summary="Great match.",
    image_urls=None,
    specs=None,
):
    raw = RawCandidate(
        url=url,
        title=title,
        price=price,
        vendor=vendor,
        image_urls=image_urls if image_urls is not None else ["https://cdn.example.com/img.jpg"],
        specs=specs,
        source_site="example.com",
    )
    return VerifiedCandidate(
        raw=raw,
        spec_confidence=confidence,
        color_result=color,
        color_description=color_desc,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Result card conversion
# ---------------------------------------------------------------------------

class TestToResultCard:
    def test_basic_conversion(self):
        v = _make_verified()
        card = _to_result_card(v)
        assert card.title == "Product"
        assert card.product_url == "https://example.com/1"
        assert card.price == "$45.00"
        assert card.vendor == "Shop"
        assert card.color == "Warm muted pink"
        assert card.note == "Great match."
        assert card.photo_url == "https://cdn.example.com/img.jpg"

    def test_no_images(self):
        v = _make_verified(image_urls=[])
        card = _to_result_card(v)
        assert card.photo_url is None

    def test_specs_extracted(self):
        v = _make_verified(specs={"size": "60x84", "material": "linen"})
        card = _to_result_card(v)
        assert card.dimensions == "60x84"
        assert card.material == "linen"

    def test_no_specs(self):
        v = _make_verified(specs=None)
        card = _to_result_card(v)
        assert card.dimensions is None
        assert card.material is None


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

class TestRenderCardMd:
    def test_basic_card(self):
        card = ResultCard(
            title="Dusty Rose Tablecloth",
            product_url="https://etsy.com/listing/123",
            price="$45.00",
            vendor="LinenCraft",
            color="Warm muted pink",
            note="Excellent match on color and material.",
        )
        md = _render_card_md(card)
        assert "[**Dusty Rose Tablecloth**](https://etsy.com/listing/123)" in md
        assert "$45.00" in md
        assert "LinenCraft" in md
        assert "Warm muted pink" in md
        assert "Excellent match" in md

    def test_card_with_photo(self):
        card = ResultCard(
            title="Product",
            product_url="https://example.com/1",
            vendor="Shop",
            color="pink",
            note="Good.",
            photo_url="https://cdn.example.com/img.jpg",
        )
        md = _render_card_md(card)
        assert "![Product](https://cdn.example.com/img.jpg)" in md

    def test_card_without_price(self):
        card = ResultCard(
            title="Product",
            product_url="https://example.com/1",
            vendor="Shop",
            color="pink",
            note="Good.",
        )
        md = _render_card_md(card)
        assert "— " not in md  # no price separator

    def test_card_with_dimensions_and_material(self):
        card = ResultCard(
            title="Product",
            product_url="https://example.com/1",
            vendor="Shop",
            color="pink",
            dimensions="60x84",
            material="linen",
            note="Good.",
        )
        md = _render_card_md(card)
        assert "**Size:** 60x84" in md
        assert "**Material:** linen" in md


# ---------------------------------------------------------------------------
# Full present stage
# ---------------------------------------------------------------------------

class TestPresent:
    def test_confirmed_and_ambiguous_split(self, spec):
        verified = [
            _make_verified(title="Match A", confidence="HIGH", color="PASS"),
            _make_verified(title="Match B", confidence="MEDIUM", color="PASS"),
            _make_verified(title="Maybe C", confidence="HIGH", color="AMBIGUOUS"),
        ]
        result = present(spec, verified)

        assert isinstance(result, PresentationResult)
        assert len(result.results) == 3
        assert "dusty rose" in result.spec_summary

        # Markdown has both sections
        assert "Match A" in result.markdown
        assert "Match B" in result.markdown
        assert "Worth a look" in result.markdown
        assert "Maybe C" in result.markdown

    def test_no_ambiguous_omits_section(self, spec):
        verified = [
            _make_verified(title="Match A", color="PASS"),
            _make_verified(title="Match B", color="PASS"),
            _make_verified(title="Match C", color="PASS"),
        ]
        result = present(spec, verified)

        assert "Worth a look" not in result.markdown

    def test_sparse_results_noted(self, spec):
        verified = [
            _make_verified(title="Only One", color="PASS"),
        ]
        result = present(spec, verified)

        assert "1 strong match" in result.markdown

    def test_no_results(self, spec):
        result = present(spec, [])

        assert len(result.results) == 0
        assert "couldn't find" in result.markdown
        assert "broaden" in result.markdown or "adjust" in result.markdown

    def test_max_results_capped(self, spec):
        verified = [
            _make_verified(title=f"Product {i}", color="PASS")
            for i in range(20)
        ]
        result = present(spec, verified)

        assert len(result.results) == 15  # MAX_RESULTS

    def test_spec_summary_includes_dimensions(self, spec):
        verified = [_make_verified(color="PASS")]
        result = present(spec, verified)

        assert "60x84 inches" in result.spec_summary

    def test_footer_present(self, spec):
        verified = [
            _make_verified(color="PASS") for _ in range(5)
        ]
        result = present(spec, verified)

        assert "Let me know" in result.markdown

    def test_confirmed_before_ambiguous_in_results_list(self, spec):
        verified = [
            _make_verified(title="Ambiguous", color="AMBIGUOUS"),
            _make_verified(title="Confirmed", color="PASS"),
        ]
        result = present(spec, verified)

        # In the results list, confirmed cards come first
        titles = [r.title for r in result.results]
        assert titles.index("Confirmed") < titles.index("Ambiguous")
