"""
Stage 3 — Verify + Color (spec §4, Stage 3)

One Claude call per candidate (up to 4 concurrent) assessing both spec match
and color from image_urls already collected by Browser Use. No additional web
fetching.

Output: list of VerifiedCandidates with drop=False, sorted by match quality.
"""

import asyncio
import json
import logging
from typing import Optional

import llm
from models import ProductSpec, RawCandidate, VerifiedCandidate

log = logging.getLogger("shopping_agent.verify")

MAX_CONCURRENT = 4

# ---------------------------------------------------------------------------
# System prompt for combined verify + color assessment
# ---------------------------------------------------------------------------

_VERIFY_SYSTEM = """\
You are assessing a product candidate against a shopping specification.
Evaluate BOTH spec match (non-color attributes) and color match (from the \
product images).

Return ONLY valid JSON with these exact keys:

{
  "spec_confidence": "HIGH" | "MEDIUM" | "LOW",
  "color_result": "PASS" | "FAIL" | "AMBIGUOUS",
  "color_description": "plain language description of the color you see in the images",
  "summary": "1-2 sentences explaining why this is or isn't a match"
}

Spec confidence rules:
- HIGH = all non-color attributes clearly match the spec
- MEDIUM = most match but one is uncertain or missing
- LOW = plausibly relevant but key details missing or clearly wrong

Color assessment rules:
- PASS = color in the images is a close match to the spec's color description, \
accounting for normal variation in product photography
- FAIL = color is clearly different from what the spec describes
- AMBIGUOUS = images do not show the color clearly enough to judge confidently

Return ONLY the JSON object. No other text."""


# ---------------------------------------------------------------------------
# Single candidate assessment
# ---------------------------------------------------------------------------

def _build_assessment_text(spec: ProductSpec, candidate: RawCandidate) -> str:
    """Build the text prompt describing the spec and candidate for assessment."""
    spec_lines = [
        f"Item type: {spec.item_type}",
        f"Color wanted: {spec.color_description}",
    ]
    if spec.dimensions:
        spec_lines.append(f"Dimensions: {spec.dimensions}")
    if spec.material:
        spec_lines.append(f"Material: {spec.material}")
    if spec.constraints:
        spec_lines.append(f"Constraints: {', '.join(spec.constraints)}")
    if spec.budget_max is not None:
        spec_lines.append(f"Budget max: ${spec.budget_max:.2f}")

    candidate_lines = [
        f"Title: {candidate.title}",
        f"Price: {candidate.price or 'not listed'}",
        f"Vendor: {candidate.vendor}",
        f"URL: {candidate.url}",
    ]
    if candidate.description:
        candidate_lines.append(f"Description: {candidate.description[:500]}")
    if candidate.specs:
        candidate_lines.append(f"Specs: {json.dumps(candidate.specs)}")

    return (
        "## Product Specification\n"
        + "\n".join(spec_lines)
        + "\n\n## Candidate Product\n"
        + "\n".join(candidate_lines)
        + "\n\nAssess this candidate against the spec. "
        "Look at the product images to evaluate the color."
    )


def verify_candidate(
    spec: ProductSpec, candidate: RawCandidate
) -> VerifiedCandidate:
    """Assess a single candidate against the spec using Claude with vision."""
    log.info("verify_candidate  url=%s  images=%d", candidate.url, len(candidate.image_urls))

    text = _build_assessment_text(spec, candidate)

    if candidate.image_urls:
        raw_response = llm.chat_with_images(
            system=_VERIFY_SYSTEM,
            text=text,
            image_urls=candidate.image_urls,
        )
    else:
        raw_response = llm.chat([
            {"role": "system", "content": _VERIFY_SYSTEM},
            {"role": "user", "content": (
                text
                + "\n\nNote: No product images available. "
                "Set color_result to AMBIGUOUS and color_description to "
                "'No images provided — color could not be assessed'."
            )},
        ])

    try:
        data = llm.parse_json(raw_response)
    except (json.JSONDecodeError, ValueError):
        log.warning("verify_candidate  parse failed  url=%s  raw=%.200s", candidate.url, raw_response)
        data = {}

    color_result = data.get("color_result", "AMBIGUOUS")
    if color_result not in ("PASS", "FAIL", "AMBIGUOUS"):
        color_result = "AMBIGUOUS"

    spec_confidence = data.get("spec_confidence", "MEDIUM")
    if spec_confidence not in ("HIGH", "MEDIUM", "LOW"):
        spec_confidence = "MEDIUM"

    return VerifiedCandidate(
        raw=candidate,
        spec_confidence=spec_confidence,
        color_result=color_result,
        color_description=data.get("color_description", "Unable to assess color"),
        summary=data.get("summary", "Assessment unavailable"),
        drop=color_result == "FAIL",
    )


# ---------------------------------------------------------------------------
# Batch verification with concurrency limit
# ---------------------------------------------------------------------------

async def _verify_one(
    sem: asyncio.Semaphore,
    spec: ProductSpec,
    candidate: RawCandidate,
) -> VerifiedCandidate:
    """Verify one candidate, respecting the concurrency semaphore."""
    async with sem:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, verify_candidate, spec, candidate)


async def verify_all(
    spec: ProductSpec, candidates: list[RawCandidate]
) -> list[VerifiedCandidate]:
    """Verify all candidates concurrently (up to MAX_CONCURRENT).
    Returns only non-dropped candidates, sorted by match quality."""
    log.info("verify_all  candidates=%d", len(candidates))

    sem = asyncio.Semaphore(MAX_CONCURRENT)
    results = await asyncio.gather(
        *(_verify_one(sem, spec, c) for c in candidates),
        return_exceptions=True,
    )

    verified = []
    for r in results:
        if isinstance(r, Exception):
            log.warning("verify_all  candidate failed: %s", r)
            continue
        if not r.drop:
            verified.append(r)

    verified.sort(key=_sort_key)
    log.info(
        "verify_all  passed=%d  dropped=%d",
        len(verified), len(candidates) - len(verified),
    )
    return verified


def verify_all_sync(
    spec: ProductSpec, candidates: list[RawCandidate]
) -> list[VerifiedCandidate]:
    """Synchronous wrapper around verify_all for non-async callers."""
    return asyncio.run(verify_all(spec, candidates))


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------

_CONFIDENCE_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
_COLOR_ORDER = {"PASS": 0, "AMBIGUOUS": 1, "FAIL": 2}


def _sort_key(v: VerifiedCandidate) -> tuple[int, int]:
    """Sort: HIGH+PASS first, then MEDIUM/LOW, then AMBIGUOUS at end."""
    return (
        _COLOR_ORDER.get(v.color_result, 2),
        _CONFIDENCE_ORDER.get(v.spec_confidence, 2),
    )