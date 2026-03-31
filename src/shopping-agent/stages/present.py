"""
Stage 4 — Present (spec §4, Stage 4)

Formats verified candidates into ResultCards and renders markdown for Open WebUI.
The structured JSON (PresentationResult) is the canonical output — markdown is
derived from it.
"""

import logging
from typing import Optional

from models import (
    PresentationResult,
    ProductSpec,
    ResultCard,
    VerifiedCandidate,
)
from stages.refine import RESULTS_MARKER

log = logging.getLogger("shopping_agent.present")

MAX_RESULTS = 15


# ---------------------------------------------------------------------------
# Build result cards from verified candidates
# ---------------------------------------------------------------------------

def _to_result_card(v: VerifiedCandidate) -> ResultCard:
    """Convert a VerifiedCandidate into a ResultCard for presentation."""
    raw = v.raw
    return ResultCard(
        photo_url=raw.image_urls[0] if raw.image_urls else None,
        title=raw.title,
        product_url=raw.url,
        price=raw.price,
        vendor=raw.vendor,
        color=v.color_description,
        dimensions=raw.specs.get("size") or raw.specs.get("dimensions") if raw.specs else None,
        material=raw.specs.get("material") if raw.specs else None,
        note=v.summary,
    )


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _render_card_md(card: ResultCard) -> str:
    """Render a single ResultCard as markdown."""
    lines = []

    if card.photo_url:
        lines.append(f"![{card.title}]({card.photo_url})")
        lines.append("")

    price_str = f" — {card.price}" if card.price else ""
    lines.append(f"[**{card.title}**]({card.product_url}){price_str} · {card.vendor}")
    lines.append("")

    details = []
    if card.color:
        details.append(f"**Color:** {card.color}")
    if card.dimensions:
        details.append(f"**Size:** {card.dimensions}")
    if card.material:
        details.append(f"**Material:** {card.material}")
    if details:
        lines.append(" · ".join(details))
        lines.append("")

    lines.append(card.note)
    return "\n".join(lines)


def _render_markdown(
    spec: ProductSpec,
    confirmed_cards: list[ResultCard],
    ambiguous_cards: list[ResultCard],
) -> str:
    """Render the full presentation as markdown for Open WebUI."""
    parts: list[str] = []

    total_confirmed = len(confirmed_cards)

    if total_confirmed == 0 and not ambiguous_cards:
        parts.append(
            f"I couldn't find anything that matched your request for "
            f"a {spec.color_description} {spec.item_type} across the sites I searched. "
            f"Would you like me to broaden the color range or try different sites?"
        )
        parts.append(RESULTS_MARKER)
        return "\n\n".join(parts)

    if total_confirmed < 3:
        parts.append(
            f"I found {total_confirmed} strong match{'es' if total_confirmed != 1 else ''}"
            + (f" and {len(ambiguous_cards)} worth checking" if ambiguous_cards else "")
            + " — the specifics you described narrowed things down quite a bit."
        )
        parts.append("")

    for card in confirmed_cards:
        parts.append(_render_card_md(card))

    if ambiguous_cards:
        parts.append("---")
        parts.append("## Worth a look — color hard to judge from photos")
        parts.append(
            "These match your other requirements but the listing photos "
            "didn't show the color clearly enough to confirm. Worth a quick look."
        )
        parts.append("")
        for card in ambiguous_cards:
            parts.append(_render_card_md(card))

    parts.append("---")
    parts.append("Let me know if any of these look promising or if you'd like me to search somewhere else.")
    parts.append(RESULTS_MARKER)

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Present stage entry point
# ---------------------------------------------------------------------------

def present(
    spec: ProductSpec, verified: list[VerifiedCandidate]
) -> PresentationResult:
    """Format verified candidates into structured results + markdown.

    Takes the top MAX_RESULTS candidates (already sorted by verify stage),
    splits into confirmed (PASS) and ambiguous groups, builds ResultCards,
    and renders markdown.
    """
    log.info("present  candidates=%d", len(verified))

    top = verified[:MAX_RESULTS]

    confirmed_cards: list[ResultCard] = []
    ambiguous_cards: list[ResultCard] = []

    for v in top:
        card = _to_result_card(v)
        if v.color_result == "AMBIGUOUS":
            ambiguous_cards.append(card)
        else:
            confirmed_cards.append(card)

    all_cards = confirmed_cards + ambiguous_cards
    spec_summary = f"{spec.color_description} {spec.item_type}"
    if spec.dimensions:
        spec_summary += f", {spec.dimensions}"

    markdown = _render_markdown(spec, confirmed_cards, ambiguous_cards)

    log.info(
        "present  confirmed=%d  ambiguous=%d  markdown_len=%d",
        len(confirmed_cards), len(ambiguous_cards), len(markdown),
    )

    return PresentationResult(
        spec_summary=spec_summary,
        results=all_cards,
        markdown=markdown,
    )
