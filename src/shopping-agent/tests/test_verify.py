"""Validate Stage 3 — Verify + Color logic (Step 6 verification).

Tests assessment text building, result parsing, sorting, and async flow
without hitting Claude.
"""

import json
from unittest.mock import patch, MagicMock

import pytest

from models import ProductSpec, RawCandidate, VerifiedCandidate
from stages.verify import (
    _build_assessment_text,
    _sort_key,
    verify_candidate,
    verify_all_sync,
)


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
        budget_max=60.0,
    )


@pytest.fixture
def candidate_with_images():
    return RawCandidate(
        url="https://etsy.com/listing/123",
        title="Dusty Rose Linen Tablecloth 60x84",
        price="$45.00",
        vendor="LinenCraft",
        description="Beautiful handmade linen tablecloth in dusty rose",
        specs={"size": "60x84", "material": "100% linen"},
        image_urls=["https://cdn.etsy.com/img1.jpg", "https://cdn.etsy.com/img2.jpg"],
        source_site="etsy.com",
    )


@pytest.fixture
def candidate_no_images():
    return RawCandidate(
        url="https://amazon.com/dp/ABC",
        title="Pink Tablecloth",
        price="$29.99",
        vendor="TableCo",
        source_site="amazon.com",
    )


# ---------------------------------------------------------------------------
# Assessment text building
# ---------------------------------------------------------------------------

class TestBuildAssessmentText:
    def test_includes_spec_fields(self, spec, candidate_with_images):
        text = _build_assessment_text(spec, candidate_with_images)
        assert "linen tablecloth" in text
        assert "dusty rose" in text
        assert "60x84 inches" in text
        assert "linen" in text
        assert "$60.00" in text

    def test_includes_candidate_fields(self, spec, candidate_with_images):
        text = _build_assessment_text(spec, candidate_with_images)
        assert "Dusty Rose Linen Tablecloth 60x84" in text
        assert "$45.00" in text
        assert "LinenCraft" in text
        assert "handmade linen" in text

    def test_optional_fields_omitted_when_none(self, candidate_with_images):
        minimal_spec = ProductSpec(
            item_type="tablecloth",
            color_description="pink",
        )
        text = _build_assessment_text(minimal_spec, candidate_with_images)
        assert "Dimensions:" not in text
        assert "Material:" not in text
        assert "Budget" not in text

    def test_constraints_included(self, candidate_with_images):
        spec = ProductSpec(
            item_type="watch band",
            color_description="green",
            constraints=["vegan", "fits Series 9"],
        )
        text = _build_assessment_text(spec, candidate_with_images)
        assert "vegan" in text
        assert "fits Series 9" in text


# ---------------------------------------------------------------------------
# Single candidate verification (mocked LLM)
# ---------------------------------------------------------------------------

class TestVerifyCandidate:
    @patch("stages.verify.llm")
    def test_pass_with_images(self, mock_llm, spec, candidate_with_images):
        mock_llm.chat_with_images.return_value = json.dumps({
            "spec_confidence": "HIGH",
            "color_result": "PASS",
            "color_description": "Warm muted pink, consistent with dusty rose",
            "summary": "Strong match — color and material align perfectly.",
        })
        mock_llm.parse_json.side_effect = json.loads

        result = verify_candidate(spec, candidate_with_images)

        assert isinstance(result, VerifiedCandidate)
        assert result.spec_confidence == "HIGH"
        assert result.color_result == "PASS"
        assert result.drop is False
        assert result.raw == candidate_with_images
        mock_llm.chat_with_images.assert_called_once()

    @patch("stages.verify.llm")
    def test_fail_sets_drop(self, mock_llm, spec, candidate_with_images):
        mock_llm.chat_with_images.return_value = json.dumps({
            "spec_confidence": "HIGH",
            "color_result": "FAIL",
            "color_description": "Bright cherry red, not pink at all",
            "summary": "Color is clearly wrong — red, not dusty rose.",
        })
        mock_llm.parse_json.side_effect = json.loads

        result = verify_candidate(spec, candidate_with_images)

        assert result.drop is True
        assert result.color_result == "FAIL"

    @patch("stages.verify.llm")
    def test_ambiguous_passes_through(self, mock_llm, spec, candidate_with_images):
        mock_llm.chat_with_images.return_value = json.dumps({
            "spec_confidence": "MEDIUM",
            "color_result": "AMBIGUOUS",
            "color_description": "Image quality too low to determine exact shade",
            "summary": "Spec seems to match but color is uncertain from photos.",
        })
        mock_llm.parse_json.side_effect = json.loads

        result = verify_candidate(spec, candidate_with_images)

        assert result.drop is False
        assert result.color_result == "AMBIGUOUS"

    @patch("stages.verify.llm")
    def test_no_images_uses_text_chat(self, mock_llm, spec, candidate_no_images):
        mock_llm.chat.return_value = json.dumps({
            "spec_confidence": "LOW",
            "color_result": "AMBIGUOUS",
            "color_description": "No images available",
            "summary": "Cannot assess color without product images.",
        })
        mock_llm.parse_json.side_effect = json.loads

        result = verify_candidate(spec, candidate_no_images)

        assert result.color_result == "AMBIGUOUS"
        assert result.spec_confidence == "LOW"
        mock_llm.chat.assert_called_once()
        mock_llm.chat_with_images.assert_not_called()

    @patch("stages.verify.llm")
    def test_parse_failure_defaults(self, mock_llm, spec, candidate_with_images):
        mock_llm.chat_with_images.return_value = "Sorry, I can't assess this."
        mock_llm.parse_json.side_effect = ValueError("no JSON")

        result = verify_candidate(spec, candidate_with_images)

        assert result.spec_confidence == "MEDIUM"
        assert result.color_result == "AMBIGUOUS"
        assert result.drop is False
        assert "Unable to assess" in result.color_description

    @patch("stages.verify.llm")
    def test_invalid_values_default(self, mock_llm, spec, candidate_with_images):
        mock_llm.chat_with_images.return_value = json.dumps({
            "spec_confidence": "VERY_HIGH",
            "color_result": "MAYBE",
            "color_description": "Pinkish",
            "summary": "Looks okay.",
        })
        mock_llm.parse_json.side_effect = json.loads

        result = verify_candidate(spec, candidate_with_images)

        assert result.spec_confidence == "MEDIUM"
        assert result.color_result == "AMBIGUOUS"


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------

class TestSorting:
    def _make_verified(self, confidence, color):
        raw = RawCandidate(
            url="https://example.com/1", title="P", vendor="V", source_site="x.com"
        )
        return VerifiedCandidate(
            raw=raw,
            spec_confidence=confidence,
            color_result=color,
            color_description="test",
            summary="test",
        )

    def test_high_pass_first(self):
        candidates = [
            self._make_verified("LOW", "AMBIGUOUS"),
            self._make_verified("HIGH", "PASS"),
            self._make_verified("MEDIUM", "PASS"),
        ]
        candidates.sort(key=_sort_key)
        assert candidates[0].spec_confidence == "HIGH"
        assert candidates[0].color_result == "PASS"
        assert candidates[1].spec_confidence == "MEDIUM"
        assert candidates[2].color_result == "AMBIGUOUS"

    def test_ambiguous_last(self):
        candidates = [
            self._make_verified("HIGH", "AMBIGUOUS"),
            self._make_verified("LOW", "PASS"),
        ]
        candidates.sort(key=_sort_key)
        assert candidates[0].color_result == "PASS"
        assert candidates[1].color_result == "AMBIGUOUS"


# ---------------------------------------------------------------------------
# Batch verify (mocked)
# ---------------------------------------------------------------------------

class TestVerifyAll:
    @patch("stages.verify.llm")
    def test_drops_failed_candidates(self, mock_llm, spec):
        responses = [
            json.dumps({
                "spec_confidence": "HIGH", "color_result": "PASS",
                "color_description": "pink", "summary": "match",
            }),
            json.dumps({
                "spec_confidence": "HIGH", "color_result": "FAIL",
                "color_description": "red", "summary": "wrong color",
            }),
            json.dumps({
                "spec_confidence": "MEDIUM", "color_result": "AMBIGUOUS",
                "color_description": "unclear", "summary": "maybe",
            }),
        ]
        mock_llm.chat.side_effect = responses
        mock_llm.parse_json.side_effect = json.loads

        candidates = [
            RawCandidate(url=f"https://e.com/{i}", title=f"P{i}", vendor="V", source_site="e.com")
            for i in range(3)
        ]

        results = verify_all_sync(spec, candidates)

        assert len(results) == 2  # FAIL dropped
        assert results[0].color_result == "PASS"  # sorted first
        assert results[1].color_result == "AMBIGUOUS"  # sorted last

    @patch("stages.verify.llm")
    def test_sorted_output(self, mock_llm, spec):
        responses = [
            json.dumps({
                "spec_confidence": "LOW", "color_result": "AMBIGUOUS",
                "color_description": "unclear", "summary": "maybe",
            }),
            json.dumps({
                "spec_confidence": "HIGH", "color_result": "PASS",
                "color_description": "dusty rose", "summary": "perfect",
            }),
            json.dumps({
                "spec_confidence": "MEDIUM", "color_result": "PASS",
                "color_description": "pinkish", "summary": "good",
            }),
        ]
        mock_llm.chat.side_effect = responses
        mock_llm.parse_json.side_effect = json.loads

        candidates = [
            RawCandidate(url=f"https://e.com/{i}", title=f"P{i}", vendor="V", source_site="e.com")
            for i in range(3)
        ]

        results = verify_all_sync(spec, candidates)

        assert len(results) == 3
        assert results[0].spec_confidence == "HIGH"
        assert results[0].color_result == "PASS"
        assert results[1].spec_confidence == "MEDIUM"
        assert results[1].color_result == "PASS"
        assert results[2].color_result == "AMBIGUOUS"

    @patch("stages.verify.llm")
    def test_empty_candidates(self, mock_llm, spec):
        results = verify_all_sync(spec, [])
        assert results == []
        mock_llm.chat.assert_not_called()
        mock_llm.chat_with_images.assert_not_called()
