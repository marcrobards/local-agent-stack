"""Validate data model shapes — Step 1 verification."""

import pytest
from models import (
    ProductSpec,
    RawCandidate,
    ResultCard,
    SearchTarget,
    SearchTaskResult,
    PresentationResult,
    VerifiedCandidate,
)


# ---------------------------------------------------------------------------
# ProductSpec
# ---------------------------------------------------------------------------

class TestProductSpec:
    def test_minimal(self):
        spec = ProductSpec(
            item_type="linen tablecloth",
            color_description="dusty rose — muted warm pink",
        )
        assert spec.confirmed is False
        assert spec.search_targets == []
        assert spec.constraints == []
        assert spec.budget_max is None

    def test_full(self):
        spec = ProductSpec(
            item_type="Apple Watch band",
            color_description="forest green leather",
            dimensions="42mm",
            material="vegan leather",
            constraints=["vegan", "fits Apple Watch Series 9"],
            budget_max=50.0,
            search_targets=[
                SearchTarget(site="etsy.com", rationale="Strong for handmade watch bands"),
                SearchTarget(site="amazon.com", rationale="Wide selection, fast shipping"),
            ],
            confirmed=True,
        )
        assert spec.confirmed is True
        assert len(spec.search_targets) == 2
        assert spec.budget_max == 50.0

    def test_refinement_patch(self):
        """Spec updates work as patches — unchanged fields are preserved."""
        spec = ProductSpec(
            item_type="area rug",
            color_description="navy blue",
            dimensions="8x10 feet",
            budget_max=300.0,
        )
        updated = spec.model_copy(update={"budget_max": 200.0, "color_description": "muted navy"})
        assert updated.budget_max == 200.0
        assert updated.color_description == "muted navy"
        assert updated.item_type == "area rug"
        assert updated.dimensions == "8x10 feet"


# ---------------------------------------------------------------------------
# RawCandidate
# ---------------------------------------------------------------------------

class TestRawCandidate:
    def test_minimal(self):
        c = RawCandidate(
            url="https://etsy.com/listing/123",
            title="Linen Tablecloth",
            vendor="EtsySeller",
            source_site="etsy.com",
        )
        assert c.image_urls == []
        assert c.specs is None

    def test_full(self):
        c = RawCandidate(
            url="https://amazon.com/dp/ABC",
            title="Watch Band",
            price="$29.99",
            vendor="BandCo",
            description="Premium vegan leather band",
            specs={"size": "42mm", "material": "vegan leather", "colors": ["green", "black"]},
            image_urls=["https://cdn.example.com/img1.jpg", "https://cdn.example.com/img2.jpg"],
            source_site="amazon.com",
        )
        assert len(c.image_urls) == 2
        assert c.specs["material"] == "vegan leather"


# ---------------------------------------------------------------------------
# VerifiedCandidate
# ---------------------------------------------------------------------------

class TestVerifiedCandidate:
    def test_pass(self):
        raw = RawCandidate(
            url="https://etsy.com/listing/456",
            title="Dusty Rose Tablecloth",
            vendor="LinenShop",
            source_site="etsy.com",
        )
        v = VerifiedCandidate(
            raw=raw,
            spec_confidence="HIGH",
            color_result="PASS",
            color_description="Warm muted pink, consistent with dusty rose",
            summary="Strong match — color and material align with spec.",
        )
        assert v.drop is False

    def test_fail_sets_drop(self):
        raw = RawCandidate(
            url="https://amazon.com/dp/XYZ",
            title="Bright Red Tablecloth",
            vendor="TableCo",
            source_site="amazon.com",
        )
        v = VerifiedCandidate(
            raw=raw,
            spec_confidence="HIGH",
            color_result="FAIL",
            color_description="Bright cherry red, not pink",
            summary="Color is clearly red, not dusty rose.",
            drop=True,
        )
        assert v.drop is True

    def test_ambiguous(self):
        raw = RawCandidate(
            url="https://example.com/product/1",
            title="Pink Tablecloth",
            vendor="HomeGoods",
            source_site="example.com",
        )
        v = VerifiedCandidate(
            raw=raw,
            spec_confidence="MEDIUM",
            color_result="AMBIGUOUS",
            color_description="Appears pink but image is low quality",
            summary="Color might match but hard to tell from photos.",
        )
        assert v.drop is False
        assert v.color_result == "AMBIGUOUS"


# ---------------------------------------------------------------------------
# SearchTaskResult
# ---------------------------------------------------------------------------

class TestSearchTaskResult:
    def test_success(self):
        r = SearchTaskResult(
            site="etsy.com",
            candidates=[
                RawCandidate(url="https://etsy.com/1", title="A", vendor="V", source_site="etsy.com"),
                RawCandidate(url="https://etsy.com/2", title="B", vendor="V", source_site="etsy.com"),
            ],
        )
        assert len(r.candidates) == 2
        assert r.error is None

    def test_error(self):
        r = SearchTaskResult(site="blocked.com", error="403 Forbidden")
        assert r.candidates == []
        assert r.error == "403 Forbidden"


# ---------------------------------------------------------------------------
# ResultCard + PresentationResult
# ---------------------------------------------------------------------------

class TestPresentation:
    def test_result_card(self):
        card = ResultCard(
            title="Dusty Rose Linen Tablecloth",
            product_url="https://etsy.com/listing/789",
            price="$45.00",
            vendor="LinenCraft",
            color="Warm muted pink, matches dusty rose",
            note="Excellent match on color and material.",
        )
        assert card.photo_url is None
        assert card.dimensions is None

    def test_presentation_result(self):
        result = PresentationResult(
            spec_summary="Dusty rose linen tablecloth, 60x90 inches",
            results=[
                ResultCard(
                    title="Test",
                    product_url="https://example.com",
                    vendor="Shop",
                    color="pink",
                    note="Good match.",
                ),
            ],
            markdown="## Results\n\n1. **Test** — Good match.",
        )
        assert len(result.results) == 1


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_product_spec_json_roundtrip(self):
        spec = ProductSpec(
            item_type="watch band",
            color_description="forest green",
            constraints=["vegan"],
            search_targets=[SearchTarget(site="etsy.com", rationale="Good for bands")],
            confirmed=True,
        )
        json_str = spec.model_dump_json()
        restored = ProductSpec.model_validate_json(json_str)
        assert restored == spec

    def test_verified_candidate_json_roundtrip(self):
        raw = RawCandidate(
            url="https://example.com/1",
            title="Product",
            vendor="Seller",
            source_site="example.com",
            image_urls=["https://cdn.example.com/img.jpg"],
        )
        vc = VerifiedCandidate(
            raw=raw,
            spec_confidence="HIGH",
            color_result="PASS",
            color_description="Forest green as expected",
            summary="Great match.",
        )
        json_str = vc.model_dump_json()
        restored = VerifiedCandidate.model_validate_json(json_str)
        assert restored == vc
