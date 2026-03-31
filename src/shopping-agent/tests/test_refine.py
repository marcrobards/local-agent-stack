"""Validate refinement loop logic (Step 8 verification).

Tests refinement detection, spec merging, and conversation state detection.
"""

import json
from unittest.mock import patch

import pytest

from models import ProductSpec
from stages.refine import (
    RESULTS_MARKER,
    find_last_spec_and_results,
    is_refinement,
    merge_refinement,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_conversation(
    include_results=True,
    refinement_msg=None,
    spec_summary="Dusty rose linen tablecloth, 60x84 inches. Ready?",
):
    """Build a realistic conversation history."""
    messages = [
        {"role": "user", "content": "I need a tablecloth"},
        {"role": "assistant", "content": "What color are you thinking?"},
        {"role": "user", "content": "dusty rose, 60x84, linen"},
        {"role": "assistant", "content": spec_summary},
        {"role": "user", "content": "yes"},
    ]
    if include_results:
        messages.append({
            "role": "assistant",
            "content": (
                "[**Dusty Rose Tablecloth**](https://etsy.com/1) — $45.00\n\n"
                "Great match.\n\n---\n\n"
                f"Let me know if any look promising.\n\n{RESULTS_MARKER}"
            ),
        })
    if refinement_msg:
        messages.append({"role": "user", "content": refinement_msg})
    return messages


# ---------------------------------------------------------------------------
# find_last_spec_and_results
# ---------------------------------------------------------------------------

class TestFindLastSpecAndResults:
    def test_no_results_yet(self):
        messages = _build_conversation(include_results=False)
        spec_text, has_results = find_last_spec_and_results(messages)
        assert has_results is False
        assert spec_text == ""

    def test_results_present(self):
        messages = _build_conversation(include_results=True)
        spec_text, has_results = find_last_spec_and_results(messages)
        assert has_results is True
        assert "Dusty rose linen tablecloth" in spec_text

    def test_multiple_rounds(self):
        """After two rounds of results, still finds the original spec."""
        messages = _build_conversation(include_results=True, refinement_msg="try cheaper")
        # Second round of results
        messages.append({
            "role": "assistant",
            "content": f"Here are cheaper options.\n\n{RESULTS_MARKER}",
        })
        spec_text, has_results = find_last_spec_and_results(messages)
        assert has_results is True
        # Should find the confirmation spec, not the results
        assert "tablecloth" in spec_text.lower()


# ---------------------------------------------------------------------------
# is_refinement
# ---------------------------------------------------------------------------

class TestIsRefinement:
    def test_not_refinement_before_results(self):
        messages = _build_conversation(include_results=False)
        messages.append({"role": "user", "content": "try cheaper"})
        refining, _, _ = is_refinement(messages)
        assert refining is False

    def test_refinement_after_results(self):
        messages = _build_conversation(
            include_results=True,
            refinement_msg="try something more affordable",
        )
        refining, spec_text, feedback = is_refinement(messages)
        assert refining is True
        assert "Dusty rose" in spec_text
        assert "more affordable" in feedback

    def test_various_feedback_types(self):
        for feedback_text in [
            "more muted color",
            "smaller please",
            "try Etsy only",
            "under $50",
            "different brand",
        ]:
            messages = _build_conversation(
                include_results=True,
                refinement_msg=feedback_text,
            )
            refining, _, feedback = is_refinement(messages)
            assert refining is True, f"Should detect refinement: {feedback_text}"
            assert feedback == feedback_text

    def test_short_conversation_not_refinement(self):
        messages = [
            {"role": "user", "content": "hello"},
        ]
        refining, _, _ = is_refinement(messages)
        assert refining is False

    def test_second_round_refinement(self):
        """Refinement after second round of results."""
        messages = _build_conversation(include_results=True, refinement_msg="try cheaper")
        messages.append({
            "role": "assistant",
            "content": f"Cheaper results.\n\n{RESULTS_MARKER}",
        })
        messages.append({"role": "user", "content": "even cheaper"})

        refining, spec_text, feedback = is_refinement(messages)
        assert refining is True
        assert feedback == "even cheaper"


# ---------------------------------------------------------------------------
# merge_refinement (mocked LLM)
# ---------------------------------------------------------------------------

class TestMergeRefinement:
    @patch("stages.refine.llm")
    def test_color_update(self, mock_llm):
        mock_llm.chat.return_value = json.dumps({
            "item_type": "linen tablecloth",
            "color_description": "sage green — soft, muted",
            "dimensions": "60x84 inches",
            "material": "linen",
            "constraints": [],
            "budget_max": None,
            "search_targets": [
                {"site": "etsy.com", "rationale": "Good for linens"},
            ],
            "confirmed": True,
        })
        mock_llm.parse_json.side_effect = json.loads

        spec = merge_refinement(
            "Dusty rose linen tablecloth, 60x84 inches",
            "actually I want sage green instead",
        )

        assert spec.color_description == "sage green — soft, muted"
        assert spec.item_type == "linen tablecloth"
        assert spec.dimensions == "60x84 inches"

    @patch("stages.refine.llm")
    def test_budget_update(self, mock_llm):
        mock_llm.chat.return_value = json.dumps({
            "item_type": "linen tablecloth",
            "color_description": "dusty rose",
            "dimensions": "60x84 inches",
            "material": "linen",
            "constraints": [],
            "budget_max": 50.0,
            "search_targets": [
                {"site": "amazon.com", "rationale": "Affordable options"},
                {"site": "walmart.com", "rationale": "Budget-friendly"},
            ],
            "confirmed": True,
        })
        mock_llm.parse_json.side_effect = json.loads

        spec = merge_refinement(
            "Dusty rose linen tablecloth, 60x84 inches",
            "under $50",
        )

        assert spec.budget_max == 50.0
        assert spec.color_description == "dusty rose"
        # Sites may have changed for budget
        assert len(spec.search_targets) >= 1

    @patch("stages.refine.llm")
    def test_site_replacement(self, mock_llm):
        mock_llm.chat.return_value = json.dumps({
            "item_type": "linen tablecloth",
            "color_description": "dusty rose",
            "dimensions": "60x84 inches",
            "material": "linen",
            "constraints": [],
            "budget_max": None,
            "search_targets": [
                {"site": "etsy.com", "rationale": "User requested Etsy only"},
            ],
            "confirmed": True,
        })
        mock_llm.parse_json.side_effect = json.loads

        spec = merge_refinement(
            "Dusty rose linen tablecloth, 60x84 inches",
            "try Etsy only",
        )

        assert len(spec.search_targets) == 1
        assert spec.search_targets[0].site == "etsy.com"

    @patch("stages.refine.llm")
    def test_prompt_includes_both_spec_and_feedback(self, mock_llm):
        mock_llm.chat.return_value = json.dumps({
            "item_type": "tablecloth",
            "color_description": "dusty rose",
            "dimensions": None,
            "material": None,
            "constraints": [],
            "budget_max": None,
            "search_targets": [],
            "confirmed": True,
        })
        mock_llm.parse_json.side_effect = json.loads

        merge_refinement("Original spec text", "some feedback")

        call_args = mock_llm.chat.call_args[0][0]
        user_msg = call_args[-1]["content"]
        assert "Original spec text" in user_msg
        assert "some feedback" in user_msg
