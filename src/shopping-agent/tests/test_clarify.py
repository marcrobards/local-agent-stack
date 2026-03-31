"""Validate Stage 1 — Clarify logic (Step 3 verification).

Tests confirmation detection and spec extraction without hitting a real LLM.
"""

import json
from unittest.mock import patch

import pytest

from models import ProductSpec
from stages.clarify import clarify, extract_spec, is_confirmed


# ---------------------------------------------------------------------------
# Confirmation detection
# ---------------------------------------------------------------------------

class TestIsConfirmed:
    def test_short_conversation_not_confirmed(self):
        confirmed, _ = is_confirmed([
            {"role": "user", "content": "I need a tablecloth"},
        ])
        assert confirmed is False

    def test_affirmative_after_assistant_summary(self):
        messages = [
            {"role": "user", "content": "I need a dusty rose linen tablecloth"},
            {"role": "assistant", "content": "So I'm looking for a rectangular linen tablecloth in dusty rose, about 60x84 inches. Does that sound right?"},
            {"role": "user", "content": "yes"},
        ]
        confirmed, spec_text = is_confirmed(messages)
        assert confirmed is True
        assert "dusty rose" in spec_text

    def test_go_ahead_is_affirmative(self):
        messages = [
            {"role": "user", "content": "watch band"},
            {"role": "assistant", "content": "Forest green vegan leather Apple Watch band for Series 9, under $50. Ready to search?"},
            {"role": "user", "content": "go ahead"},
        ]
        confirmed, _ = is_confirmed(messages)
        assert confirmed is True

    def test_sounds_good_is_affirmative(self):
        messages = [
            {"role": "user", "content": "rug"},
            {"role": "assistant", "content": "Navy blue area rug, 8x10. Sound right?"},
            {"role": "user", "content": "sounds good"},
        ]
        confirmed, _ = is_confirmed(messages)
        assert confirmed is True

    def test_non_affirmative_not_confirmed(self):
        messages = [
            {"role": "user", "content": "tablecloth"},
            {"role": "assistant", "content": "What color?"},
            {"role": "user", "content": "dusty rose"},
        ]
        confirmed, _ = is_confirmed(messages)
        assert confirmed is False

    def test_refinement_not_confirmed(self):
        messages = [
            {"role": "user", "content": "tablecloth"},
            {"role": "assistant", "content": "Dusty rose linen tablecloth. Ready?"},
            {"role": "user", "content": "actually make it 60x90 instead"},
        ]
        confirmed, _ = is_confirmed(messages)
        assert confirmed is False

    def test_prefix_match(self):
        messages = [
            {"role": "user", "content": "need a rug"},
            {"role": "assistant", "content": "Navy rug, 8x10. Ready?"},
            {"role": "user", "content": "yes please"},
        ]
        confirmed, _ = is_confirmed(messages)
        assert confirmed is True

    def test_search_is_affirmative(self):
        messages = [
            {"role": "user", "content": "tablecloth"},
            {"role": "assistant", "content": "Dusty rose linen tablecloth. Shall I search?"},
            {"role": "user", "content": "search"},
        ]
        confirmed, _ = is_confirmed(messages)
        assert confirmed is True

    def test_returns_last_assistant_message(self):
        messages = [
            {"role": "user", "content": "tablecloth"},
            {"role": "assistant", "content": "First reply"},
            {"role": "user", "content": "dusty rose, 60x84"},
            {"role": "assistant", "content": "Final confirmation summary"},
            {"role": "user", "content": "yes"},
        ]
        confirmed, spec_text = is_confirmed(messages)
        assert confirmed is True
        assert spec_text == "Final confirmation summary"


# ---------------------------------------------------------------------------
# Clarify turn (mocked LLM)
# ---------------------------------------------------------------------------

class TestClarify:
    @patch("stages.clarify.llm")
    def test_returns_llm_reply(self, mock_llm):
        mock_llm.chat.return_value = "What color are you thinking?"
        messages = [{"role": "user", "content": "I need a tablecloth"}]

        reply = clarify(messages)

        assert reply == "What color are you thinking?"
        mock_llm.chat.assert_called_once()
        call_args = mock_llm.chat.call_args[0][0]
        assert call_args[0]["role"] == "system"
        assert call_args[-1]["role"] == "user"
        assert call_args[-1]["content"] == "I need a tablecloth"

    @patch("stages.clarify.llm")
    def test_passes_full_conversation(self, mock_llm):
        mock_llm.chat.return_value = "Got it — dusty rose. What size?"
        messages = [
            {"role": "user", "content": "tablecloth"},
            {"role": "assistant", "content": "What color?"},
            {"role": "user", "content": "dusty rose"},
        ]

        clarify(messages)

        call_args = mock_llm.chat.call_args[0][0]
        # system prompt + 3 conversation messages
        assert len(call_args) == 4
        assert call_args[1]["content"] == "tablecloth"
        assert call_args[3]["content"] == "dusty rose"


# ---------------------------------------------------------------------------
# Spec extraction (mocked LLM)
# ---------------------------------------------------------------------------

class TestExtractSpec:
    @patch("stages.clarify.llm")
    def test_extracts_spec_from_confirmed_text(self, mock_llm):
        mock_llm.chat.return_value = json.dumps({
            "item_type": "linen tablecloth",
            "color_description": "dusty rose — muted warm pink",
            "dimensions": "60x84 inches",
            "material": "linen",
            "constraints": [],
            "budget_max": None,
            "search_targets": [
                {"site": "etsy.com", "rationale": "Strong for handmade linens"},
                {"site": "amazon.com", "rationale": "Wide selection"},
            ],
            "confirmed": True,
        })
        mock_llm.parse_json.side_effect = json.loads

        spec = extract_spec("Dusty rose linen tablecloth, 60x84 inches")

        assert isinstance(spec, ProductSpec)
        assert spec.item_type == "linen tablecloth"
        assert spec.confirmed is True
        assert len(spec.search_targets) == 2
        assert spec.search_targets[0].site == "etsy.com"

    @patch("stages.clarify.llm")
    def test_extracts_spec_with_constraints(self, mock_llm):
        mock_llm.chat.return_value = json.dumps({
            "item_type": "Apple Watch band",
            "color_description": "forest green leather",
            "dimensions": "42mm",
            "material": "vegan leather",
            "constraints": ["vegan", "fits Apple Watch Series 9"],
            "budget_max": 50.0,
            "search_targets": [
                {"site": "etsy.com", "rationale": "Handmade vegan bands"},
                {"site": "amazon.com", "rationale": "Wide selection"},
                {"site": "bandwerk.com", "rationale": "Specialist watch bands"},
            ],
            "confirmed": True,
        })
        mock_llm.parse_json.side_effect = json.loads

        spec = extract_spec("Forest green vegan leather Apple Watch band, 42mm, under $50")

        assert spec.budget_max == 50.0
        assert "vegan" in spec.constraints
        assert len(spec.search_targets) == 3

    @patch("stages.clarify.llm")
    def test_handles_markdown_fenced_json(self, mock_llm):
        raw_json = {
            "item_type": "area rug",
            "color_description": "navy blue",
            "dimensions": "8x10 feet",
            "material": None,
            "constraints": [],
            "budget_max": 300.0,
            "search_targets": [
                {"site": "wayfair.com", "rationale": "Large rug selection"},
            ],
            "confirmed": True,
        }
        mock_llm.chat.return_value = f"```json\n{json.dumps(raw_json)}\n```"
        # Use real parse_json for this test
        from llm import parse_json as real_parse_json
        mock_llm.parse_json.side_effect = real_parse_json

        spec = extract_spec("Navy blue area rug, 8x10, under $300")

        assert spec.item_type == "area rug"
        assert spec.budget_max == 300.0


# ---------------------------------------------------------------------------
# End-to-end flow (mocked LLM)
# ---------------------------------------------------------------------------

class TestClarifyFlow:
    @patch("stages.clarify.llm")
    def test_multi_turn_then_confirm(self, mock_llm):
        """Simulate a multi-turn conversation through confirmation."""
        # Turn 1: user asks, agent clarifies
        mock_llm.chat.return_value = "What color are you thinking for the tablecloth?"
        turn1 = clarify([{"role": "user", "content": "I need a tablecloth"}])
        assert "color" in turn1.lower()

        # Turn 2: user provides color, agent asks size
        mock_llm.chat.return_value = "Lovely — dusty rose. What size do you need?"
        turn2 = clarify([
            {"role": "user", "content": "I need a tablecloth"},
            {"role": "assistant", "content": turn1},
            {"role": "user", "content": "dusty rose"},
        ])
        assert "size" in turn2.lower()

        # Turn 3: user provides size, agent summarizes
        summary = "So I'm looking for a dusty rose linen tablecloth, about 60x84 inches. Does that sound right?"
        mock_llm.chat.return_value = summary
        turn3 = clarify([
            {"role": "user", "content": "I need a tablecloth"},
            {"role": "assistant", "content": turn1},
            {"role": "user", "content": "dusty rose"},
            {"role": "assistant", "content": turn2},
            {"role": "user", "content": "60 by 84"},
        ])

        # Confirmation check
        messages = [
            {"role": "user", "content": "I need a tablecloth"},
            {"role": "assistant", "content": turn1},
            {"role": "user", "content": "dusty rose"},
            {"role": "assistant", "content": turn2},
            {"role": "user", "content": "60 by 84"},
            {"role": "assistant", "content": turn3},
            {"role": "user", "content": "yes"},
        ]
        confirmed, spec_text = is_confirmed(messages)
        assert confirmed is True
        assert spec_text == summary
