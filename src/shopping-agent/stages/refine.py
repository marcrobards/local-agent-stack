"""
Refinement loop (spec §5)

Detects when the user is providing feedback after seeing results,
merges feedback into the existing ProductSpec, and signals that the
pipeline should re-run.

The ProductSpec is not discarded between rounds — refinements are patches.
"""

import logging

import llm
from models import ProductSpec

log = logging.getLogger("shopping_agent.refine")

# A marker embedded in pipeline results so we can detect refinement state
# from conversation history. Present in the markdown footer.
RESULTS_MARKER = "<!-- shopping-agent:results -->"


# ---------------------------------------------------------------------------
# Refinement detection
# ---------------------------------------------------------------------------

def find_last_spec_and_results(messages: list[dict]) -> tuple[str, bool]:
    """Scan conversation history to find the confirmed spec text and whether
    results have been presented.

    Returns (spec_text, has_results).
    - spec_text: the assistant's confirmation summary before the user said "yes"
    - has_results: True if the pipeline has already run (results marker found)
    """
    has_results = False
    spec_text = ""

    for i, msg in enumerate(messages):
        if msg.get("role") == "assistant" and RESULTS_MARKER in msg.get("content", ""):
            has_results = True

    if has_results:
        # Walk backwards to find the original confirmation exchange:
        # the pattern is assistant summary → user affirmative → assistant results
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if msg.get("role") != "assistant":
                continue
            if RESULTS_MARKER in msg.get("content", ""):
                # This is a results message. The spec is from the confirmation
                # exchange before it. Walk back to find user affirmative then
                # the assistant summary before that.
                for j in range(i - 1, -1, -1):
                    if messages[j].get("role") == "assistant" and RESULTS_MARKER not in messages[j].get("content", ""):
                        spec_text = messages[j]["content"]
                        break
                break

    return spec_text, has_results


def is_refinement(messages: list[dict]) -> tuple[bool, str, str]:
    """Determine if the user's latest message is a refinement request.

    Returns (is_refining, spec_text, feedback).
    """
    if len(messages) < 4:
        return False, "", ""

    spec_text, has_results = find_last_spec_and_results(messages)
    if not has_results:
        return False, "", ""

    last_user = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user = msg["content"]
            break

    if not last_user:
        return False, "", ""

    return True, spec_text, last_user


# ---------------------------------------------------------------------------
# Spec merging
# ---------------------------------------------------------------------------

_MERGE_SYSTEM = """\
You are updating a product search specification based on user feedback.

You will receive the original spec summary and the user's refinement request.
Merge the feedback into an updated spec. The original spec is NOT discarded —
only the fields mentioned in the feedback should change.

Rules:
- If the user says "more muted color" → update color_description only
- If the user says "smaller" → update dimensions only
- If the user says "try Etsy only" → replace search_targets with just Etsy
- If the user says "under $50" → set or update budget_max
- If the user says "something more affordable" → update budget_max AND \
reconsider search_targets for value-oriented sites
- If the feedback implies different sites → re-reason search_targets from scratch

Return ONLY valid JSON matching this exact schema:

{
  "item_type": "string",
  "color_description": "string",
  "dimensions": "string or null",
  "material": "string or null",
  "constraints": ["list"],
  "budget_max": null or number,
  "search_targets": [
    {"site": "domain.com", "rationale": "why this site"}
  ],
  "confirmed": true
}

Return ONLY the JSON object. No other text."""


def merge_refinement(spec_text: str, feedback: str) -> ProductSpec:
    """Merge user feedback into the existing spec and return an updated ProductSpec."""
    log.info("merge_refinement  feedback=%.200s", feedback)

    result = llm.chat([
        {"role": "system", "content": _MERGE_SYSTEM},
        {"role": "user", "content": (
            f"## Original spec\n{spec_text}\n\n"
            f"## User feedback\n{feedback}\n\n"
            "Merge the feedback into an updated product specification."
        )},
    ])

    data = llm.parse_json(result)
    spec = ProductSpec.model_validate(data)
    log.info(
        "merge_refinement  item_type=%s  targets=%d",
        spec.item_type, len(spec.search_targets),
    )
    return spec
