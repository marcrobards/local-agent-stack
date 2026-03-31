"""
Stage 1 — Clarify (spec §4, Stage 1)

Conversational stage that gathers product requirements from the user,
detects confirmation, and extracts a structured ProductSpec.
"""

import json
import logging
from pathlib import Path

import llm
from models import ProductSpec

log = logging.getLogger("shopping_agent.clarify")

_REPO_PROMPT = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "src" / "workflows" / "online-shopping" / "01-clarify-request" / "PROMPT.md"
)
_DOCKER_PROMPT = Path("/app/workflows/01-clarify-request/PROMPT.md")

PROMPT_PATH = _DOCKER_PROMPT if _DOCKER_PROMPT.exists() else _REPO_PROMPT

# ---------------------------------------------------------------------------
# Confirmation detection
# ---------------------------------------------------------------------------

_AFFIRMATIVES = frozenset({
    "yes", "yeah", "yep", "yup", "correct", "right", "ok", "okay",
    "sure", "absolutely", "perfect", "sounds good", "looks good",
    "that's right", "that's it", "go ahead", "go for it", "confirmed",
    "go", "search", "do it", "let's go", "ready",
})


def is_confirmed(messages: list[dict]) -> tuple[bool, str]:
    """Check if the user's last message is an affirmative confirming the spec.

    Returns (confirmed, spec_text) where spec_text is the assistant's
    confirmation summary that preceded the user's "yes".
    """
    if len(messages) < 2:
        return False, ""

    last_user = messages[-1].get("content", "").lower().strip()

    is_affirmative = (
        last_user in _AFFIRMATIVES
        or any(last_user.startswith(a) for a in _AFFIRMATIVES)
    )
    if not is_affirmative:
        return False, ""

    for msg in reversed(messages[:-1]):
        if msg.get("role") == "assistant":
            return True, msg["content"]

    return False, ""


# ---------------------------------------------------------------------------
# Clarify conversation turn
# ---------------------------------------------------------------------------

def clarify(messages: list[dict]) -> str:
    """Run one clarification turn. Returns the assistant's reply text."""
    log.info("clarify  messages=%d", len(messages))

    system_prompt = _load_prompt()
    llm_messages = [{"role": "system", "content": system_prompt}]
    llm_messages.extend(messages)

    reply = llm.chat(llm_messages)
    log.info("clarify  reply_len=%d", len(reply))
    return reply


# ---------------------------------------------------------------------------
# Spec extraction — runs after confirmation
# ---------------------------------------------------------------------------

_EXTRACT_SYSTEM = """\
You are extracting a structured product specification from a confirmed \
shopping request summary. You must also decide which websites to search.

Return ONLY valid JSON matching this exact schema:

{
  "item_type": "string — what the product is",
  "color_description": "string — full color description",
  "dimensions": "string or null — size/fit requirements",
  "material": "string or null — fabric, material, construction",
  "constraints": ["list of requirements, e.g. 'vegan', 'fits Apple Watch Series 9'"],
  "budget_max": null or number,
  "search_targets": [
    {"site": "domain.com", "rationale": "one sentence why this site is relevant"}
  ],
  "confirmed": true
}

For search_targets, reason about which 3–5 sites are most likely to carry \
this specific item type given the constraints, brand preferences, and price \
range. There is no fixed site list — choose the best sites for this product.

Return ONLY the JSON object. No other text."""


def extract_spec(confirmed_text: str) -> ProductSpec:
    """Ask the LLM to extract a ProductSpec from the confirmed summary."""
    log.info("extract_spec  input_len=%d", len(confirmed_text))

    result = llm.chat([
        {"role": "system", "content": _EXTRACT_SYSTEM},
        {"role": "user", "content": confirmed_text},
    ])

    data = llm.parse_json(result)
    spec = ProductSpec.model_validate(data)
    log.info(
        "extract_spec  item_type=%s  targets=%d  confirmed=%s",
        spec.item_type, len(spec.search_targets), spec.confirmed,
    )
    return spec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_prompt() -> str:
    """Load the clarify stage prompt from the workflows directory."""
    return PROMPT_PATH.read_text()
