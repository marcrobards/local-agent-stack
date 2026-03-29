# Stage Contracts — Structured Handoffs

**Date:** 2026-03-29
**Status:** Draft

## Problem

Every stage passes free-text strings to the next. Structured tool data (dataclasses, dicts) gets flattened to prose, fed through an LLM, and the LLM's rewrite becomes the contract. This is lossy — URLs get mangled, fields get dropped, and downstream stages rely on regex to recover structure that existed moments earlier.

## Principle

**LLMs judge. Code formats.** Structured data flows between stages as typed objects. LLMs are called only when human-like judgment is needed (clarifying requirements, assessing spec confidence, evaluating color). They are never used to reformat data that already has structure.

## Contracts

### Contract 1: `ProductSpec` — Clarify → all downstream

The clarify stage's LLM converses with the user and, once confirmed, produces a structured spec. This is the one place we ask the LLM to output JSON, because the spec originates from unstructured conversation.

```python
class ProductSpec(BaseModel):
    product_type: str              # "linen tablecloth"
    color: str                     # "dusty rose — muted, warm, not bright"
    size: str | None = None        # "60x84 inches"
    material: str | None = None    # "linen"
    brand_preference: str | None = None  # "no preference" / "West Elm"
    is_clothing: bool = False
    search_query: str              # LLM-generated best search string
    summary: str                   # human-readable confirmation paragraph
```

**Who produces it:** The clarify LLM, via a JSON-mode follow-up call after the user confirms the prose summary.

**Who consumes it:** Search (uses `search_query` + `is_clothing`), Verify (uses all fields for confidence assessment), Color Verify (uses `color`), Present (uses `summary` for context).

---

### Contract 2: `SearchCandidate` — Search → Verify

Already exists as `Candidate` in `search.py`. The fix is to stop discarding it.

```python
class SearchCandidate(BaseModel):
    url: str
    title: str
    price: str | None = None
    source: str                    # "amazon", "etsy", etc.
    shop_name: str | None = None   # Etsy/Poshmark seller
    match_reason: str
```

**Who produces it:** `search.py` tools (Browser Use). No LLM involved.

**Who consumes it:** Verify stage — iterates the list, fetches each URL.

**What changes:** `_stage_search()` stops sending tool results through an LLM for re-summarization. It returns the `SearchCandidate` list directly. The search-stage LLM call is removed — the Browser Use agents already do the searching.

---

### Contract 3: `VerifiedCandidate` — Verify → Color Verify

```python
class VerifiedCandidate(BaseModel):
    url: str
    title: str
    price: str | None = None
    source: str
    shop_name: str | None = None
    page_title: str | None = None  # from fetched page
    page_price: str | None = None  # from fetched page
    available: bool
    spec_confidence: Literal["HIGH", "MEDIUM", "LOW"]
    confidence_note: str           # LLM-generated: why this confidence level
```

**Who produces it:** The verify stage. `fetch_page()` provides the mechanical data (status, availability, page title/price). The LLM assesses spec confidence by comparing page data against the `ProductSpec`.

**LLM's role:** Given a `SearchCandidate` + `fetch_page()` result + `ProductSpec`, output `spec_confidence` and `confidence_note` as JSON. This is a judgment call the LLM is good at.

**Who consumes it:** Color Verify — iterates the list, fetches images for each URL.

**Dead links are filtered out here** — they never reach color verify.

---

### Contract 4: `ColorVerifiedCandidate` — Color Verify → Present

```python
class ColorVerifiedCandidate(BaseModel):
    url: str
    title: str
    price: str | None = None
    source: str
    shop_name: str | None = None
    spec_confidence: Literal["HIGH", "MEDIUM", "LOW"]
    confidence_note: str
    color_result: Literal["PASS", "FAIL", "AMBIGUOUS"]
    color_note: str                # vision model's assessment
```

**Who produces it:** Color verify stage. `fetch_images()` gets image URLs (mechanical). The Ollama vision model assesses color match (judgment). The result is parsed from the vision model's response.

**FAIL candidates are dropped** — they never reach present.

**Who consumes it:** Present stage — the LLM formats these into user-facing prose.

---

## What Changes Per Stage

### Stage 01 — Clarify

- **Conversation phase:** No change — LLM converses freely in prose.
- **After confirmation:** Add a second LLM call that extracts a `ProductSpec` JSON from the confirmed prose spec. Use Claude's JSON output or a strict prompt.
- **Output:** `ProductSpec` object (saved as `00-spec.json`).

### Stage 02 — Search

- **Remove the LLM call entirely.** The `_stage_search()` function currently sends tool results through an LLM to "summarize" them. The tools already return structured `Candidate` objects — this LLM call destroys structure for no benefit.
- **Fix query construction:** Replace `spec.split("\n")[0][:120]` with `spec.search_query` from the `ProductSpec`.
- **Output:** `list[SearchCandidate]` (saved as `01-search.json`).

### Stage 02-Verify

- **Keep the `fetch_page()` tool calls** — mechanical, already structured.
- **Change the LLM call:** Instead of sending everything as prose and hoping for structured output, send each candidate's page data + the `ProductSpec` and ask for a JSON response with `spec_confidence` and `confidence_note`.
- **Filter:** Drop candidates where `fetch_page()` returned DEAD.
- **Output:** `list[VerifiedCandidate]` (saved as `02-verify.json`).

### Stage 02a — Color Verify

- **Keep `fetch_images()` tool calls** — mechanical.
- **Keep vision model calls** — judgment, stays on Ollama.
- **Parse vision output:** Extract PASS/FAIL/AMBIGUOUS and the note from the vision model's text response. If parsing fails, default to AMBIGUOUS.
- **Remove the summary LLM call.** Currently `_stage_color_verify()` sends vision results through a text LLM to summarize. The vision model's structured output (once parsed) IS the data — no re-summarization needed.
- **Filter:** Drop FAIL candidates.
- **Output:** `list[ColorVerifiedCandidate]` (saved as `03-color-verify.json`).

### Stage 03 — Present

- **Keep the LLM call** — this is the one stage where prose output IS the goal.
- **Input is now structured:** The LLM receives a typed list of `ColorVerifiedCandidate` objects serialized as JSON, plus the `ProductSpec.summary`. Much cleaner than parsing another LLM's free-text output.
- **Output:** Prose for the user (saved as `04-present.md`).

## Summary of LLM Calls After Refactor

| Stage | LLM call | Purpose | Provider |
|-------|----------|---------|----------|
| 01 Clarify | Conversation | Extract requirements | Claude |
| 01 Clarify | JSON extraction | `ProductSpec` from confirmed prose | Claude |
| 02 Search | **Removed** | Was redundant re-summarization | — |
| 02-Verify | JSON assessment | Spec confidence per candidate | Claude |
| 02a Color | Vision assessment | Color match per candidate | Ollama (local) |
| 02a Color | **Removed** | Was redundant re-summarization | — |
| 03 Present | Prose formatting | User-facing results | Claude |

**Net effect:** 7 LLM calls → 5 LLM calls. Two redundant summarization calls removed. All remaining calls have a clear, non-overlapping purpose.

## File Output Changes

Stage output files switch from `.md` (prose) to `.json` (structured) for intermediate stages:

```
output/20260329-143022/
  00-spec.json            ← ProductSpec
  01-search.json          ← list[SearchCandidate]
  02-verify.json          ← list[VerifiedCandidate]
  03-color-verify.json    ← list[ColorVerifiedCandidate]
  04-present.md           ← user-facing prose (unchanged)
```
