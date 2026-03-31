"""
Shopping Agent — Data Models (Step 1)

All typed data structures passed between pipeline stages.
No logic — just the schema. See docs/shopping-agent-spec.md §3.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# §3.2 — SearchTarget
# ---------------------------------------------------------------------------

class SearchTarget(BaseModel):
    """One site the agent decides to search. No fixed site list — the agent
    reasons about which sites are relevant for the specific item type."""

    site: str = Field(description="Domain, e.g. 'etsy.com', 'bandwerk.com'")
    rationale: str = Field(description="Why this site is relevant for this item")


# ---------------------------------------------------------------------------
# §3.1 — ProductSpec
# ---------------------------------------------------------------------------

class ProductSpec(BaseModel):
    """Central data structure. Created during clarification, persisted across
    the session, updated with each refinement round."""

    item_type: str = Field(description="e.g. 'linen tablecloth', 'Apple Watch band'")
    color_description: str = Field(description="Plain language, e.g. 'dusty rose — muted warm pink'")
    dimensions: Optional[str] = Field(default=None, description="Size or fit requirements")
    material: Optional[str] = Field(default=None, description="Fabric, material, construction")
    constraints: list[str] = Field(default_factory=list, description="e.g. ['vegan', 'fits Apple Watch Series 9']")
    budget_max: Optional[float] = Field(default=None, description="Optional price ceiling")
    search_targets: list[SearchTarget] = Field(default_factory=list, description="Agent-chosen sites to search")
    confirmed: bool = Field(default=False, description="False = still clarifying, True = ready to search")


# ---------------------------------------------------------------------------
# §3.3 — RawCandidate
# ---------------------------------------------------------------------------

class RawCandidate(BaseModel):
    """Returned by Browser Use per product page visited.
    No judgment — pure extraction."""

    url: str = Field(description="Direct product page URL")
    title: str = Field(description="Product title as listed")
    price: Optional[str] = Field(default=None, description="Price as shown, including sale price")
    vendor: str = Field(description="Site or seller name")
    description: Optional[str] = Field(default=None, description="Full product description text")
    specs: Optional[dict] = Field(default=None, description="Structured attributes: dimensions, material, sizes/colors")
    image_urls: list[str] = Field(default_factory=list, description="Product image URLs from the page")
    source_site: str = Field(description="Which SearchTarget domain this came from")


# ---------------------------------------------------------------------------
# §3.4 — VerifiedCandidate
# ---------------------------------------------------------------------------

class VerifiedCandidate(BaseModel):
    """Produced by the verify stage. Claude reasons over RawCandidate data —
    no additional web fetching."""

    raw: RawCandidate
    spec_confidence: Literal["HIGH", "MEDIUM", "LOW"] = Field(
        description="How well non-color attributes match the spec"
    )
    color_result: Literal["PASS", "FAIL", "AMBIGUOUS"] = Field(
        description="Color assessment from product images"
    )
    color_description: str = Field(
        description="Plain language description of the color as seen in images"
    )
    summary: str = Field(
        description="1–2 sentences for the user explaining why this is or isn't a match"
    )
    drop: bool = Field(
        default=False,
        description="True if color_result is FAIL — excluded from results"
    )


# ---------------------------------------------------------------------------
# Browser Use task output (Stage 2 per-site result)
# ---------------------------------------------------------------------------

class SearchTaskResult(BaseModel):
    """Output from a single Browser Use task (one per SearchTarget)."""

    candidates: list[RawCandidate] = Field(default_factory=list)
    site: str = Field(description="Which SearchTarget domain was searched")
    error: Optional[str] = Field(default=None, description="Set if the site blocked or timed out")


# ---------------------------------------------------------------------------
# Result card (Stage 4 output)
# ---------------------------------------------------------------------------

class ResultCard(BaseModel):
    """A single product card shown to the user in the final presentation."""

    photo_url: Optional[str] = Field(default=None, description="Product image URL")
    title: str
    product_url: str = Field(description="Direct link to product page")
    price: Optional[str] = None
    vendor: str
    color: str = Field(description="Plain language color as seen in images")
    dimensions: Optional[str] = None
    material: Optional[str] = None
    note: str = Field(description="1–2 sentences on match quality")


class PresentationResult(BaseModel):
    """Canonical output of Stage 4 — structured JSON for future custom UI."""

    spec_summary: str
    results: list[ResultCard]
    markdown: str = Field(description="Markdown rendering for Open WebUI")
