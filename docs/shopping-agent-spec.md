# Shopping Agent — Workflow Specification

**local-agent-stack · v1.0 draft · March 2026**
**Designed for Danielle**

---

## 1. Purpose

This document specifies the complete workflow for a shopping agent that helps Danielle find products to purchase. It covers how the agent clarifies requests, searches across relevant sites, verifies and filters results, presents findings, and handles refinement when initial results are not satisfactory.

**Design goals**

- Eliminate manual multi-site searching — the agent chooses and searches all relevant sites
- Solve color accuracy — the #1 failure mode of standard product searches
- Return 10–15 curated results with enough detail to decide before clicking
- Support natural-language refinement across multiple search rounds
- Produce structured output that works in Open WebUI today and a custom UI later

---

## 2. User Experience Overview

From Danielle's perspective, the interaction has three moments:

| Moment | Description |
|--------|-------------|
| **Describe** | She opens the chat and describes what she wants in her own words. The agent asks 2–3 targeted follow-up questions to fill in any gaps, then reads back a short confirmation spec and asks if she's ready to search. |
| **Wait** | She confirms and the agent acknowledges it is searching. She waits — typically a minute or two — and results appear in the same chat thread. |
| **Review or refine** | She reviews the results. Each card shows a product photo, price, vendor, color in plain language, dimensions, material, and a direct link to the product page. If she doesn't like the results, she says so in plain language and the agent searches again with the updated criteria. |

---

## 3. Data Model

All data passed between stages is typed. No stage receives a raw string from the previous one.

### 3.1 ProductSpec

The central data structure. Created during clarification, persisted across the session, updated with each refinement round.

| Field | Description |
|-------|-------------|
| `item_type` | e.g. "linen tablecloth", "Apple Watch band", "area rug" |
| `color_description` | Plain language, e.g. "dusty rose — muted warm pink" |
| `dimensions` | Size or fit requirements. Nullable. |
| `material` | Fabric, material, construction. Nullable. |
| `constraints` | List of requirements, e.g. `["vegan", "fits Apple Watch Series 9"]` |
| `budget_max` | Optional price ceiling |
| `search_targets` | List of `SearchTarget` (see below), agent-chosen |
| `confirmed` | Boolean. `False` = still clarifying, `True` = ready to search |

### 3.2 SearchTarget

One entry per site the agent decides to search. There is no fixed site list — the agent reasons about which sites are relevant for the specific item type.

| Field | Description |
|-------|-------------|
| `site` | Domain, e.g. "etsy.com", "bandwerk.com", "amazon.com" |
| `rationale` | One sentence explaining why this site is relevant for this item |

### 3.3 RawCandidate

Returned by Browser Use per product page visited. No judgment — pure extraction.

| Field | Description |
|-------|-------------|
| `url` | Direct product page URL |
| `title` | Product title as listed |
| `price` | Price as shown, including sale price if present |
| `vendor` | Site or seller name |
| `description` | Full product description text from the page |
| `specs` | Structured attributes: dimensions, material, available sizes/colors |
| `image_urls` | List of product image URLs from the page |
| `source_site` | Which `SearchTarget` this came from |

### 3.4 VerifiedCandidate

Produced by the verify stage. Claude reasons over `RawCandidate` data — no additional web fetching.

| Field | Description |
|-------|-------------|
| `raw` | The original `RawCandidate` |
| `spec_confidence` | `HIGH` / `MEDIUM` / `LOW` — how well non-color attributes match the spec |
| `color_result` | `PASS` / `FAIL` / `AMBIGUOUS` |
| `color_description` | Plain language description of the color as seen in the images |
| `summary` | 1–2 sentences for Danielle explaining why this result is or isn't a match |
| `drop` | `True` if `color_result` is `FAIL`; this candidate is excluded from results |

---

## 4. Workflow Stages

### Stage 1 — Clarify
*Conversational · claude-sonnet · multiple turns*

**Trigger:** Danielle's first message in a new chat, or any message before the spec is confirmed.

**Behaviour:**
- Receives the full conversation history on each turn
- Asks at most 2–3 targeted questions to fill in gaps relevant to the item type
- Does not ask for information that isn't needed for this specific item
- When enough information exists, reads back a short one-line confirmation spec and asks "Ready to search?"
- Detects confirmation when Danielle explicitly says "go", "search", "yes", or equivalent affirmative

**Output:** A `ProductSpec` with `confirmed: True`. The `search_targets` list is populated at this point — the agent reasons about which sites are most likely to carry this specific item and includes a rationale for each.

**Site selection logic**

There is no fixed site list. The agent considers item type, constraints, brand preferences, and price range to decide where to look.

| Item type | Example sites chosen |
|-----------|----------------------|
| Vegan watch band | Amazon, Etsy, bandwerk.com, nomadgoods.com |
| Specific rug brand | Brand's own site, Wayfair, Rugs Direct |
| Vintage clothing | Poshmark, Depop, ThredUp, Etsy |
| Linen tablecloth | Etsy, Amazon, Crate & Barrel, Williams Sonoma |
| Pillow case pattern | Etsy, Society6, Spoonflower, Amazon |

During refinement, if Danielle says "try somewhere more affordable" or "look on Etsy instead", the agent reconsiders `search_targets` entirely and updates the spec.

---

### Stage 2 — Search
*Browser Use Cloud v3 · parallel per site*

**Trigger:** `ProductSpec` with `confirmed: True` received from Stage 1, or updated `ProductSpec` from the refinement loop.

**Behaviour:**
- One Browser Use v3 agent task per `SearchTarget`, all launched concurrently with `asyncio.gather`
- Each task has two phases:
  - **Phase A — search results page:** find listings matching the query
  - **Phase B — product pages:** for each promising result, open the product page and extract full details
- Errors or timeouts on any site are silently dropped — the rest of the results proceed
- No judgment is made about spec match or color — extraction only

**Browser Use task output schema (per task):**

| Field | Description |
|-------|-------------|
| `candidates` | List of `RawCandidate` objects |
| `site` | Which `SearchTarget` was searched |
| `error` | Nullable. Set if the site blocked or timed out. |

**Output:** All non-errored `RawCandidate`s across all sites, flattened into a single list. Typically 30–60 raw candidates before verification.

---

### Stage 3 — Verify + Color
*claude-sonnet with vision · concurrent per candidate*

**Trigger:** List of `RawCandidate`s from Stage 2.

**Behaviour:**
- One Claude call per candidate, up to 4 concurrent to avoid rate limits
- Claude receives: the `ProductSpec`, the `RawCandidate` (including `image_urls`), and is asked to assess both spec match and color
- No web fetching — Claude works entirely from data Browser Use already collected
- Color is assessed from the `image_urls` in the `RawCandidate`; Claude describes what it sees in plain language
- Candidates with `color_result: FAIL` are marked `drop: True` and excluded from Stage 4
- Candidates with `color_result: AMBIGUOUS` are passed through and flagged for Danielle

**Color assessment rules:**

| Result | Meaning |
|--------|---------|
| `PASS` | Color in the images is a close match to the spec's `color_description`, accounting for normal variation in product photography |
| `FAIL` | Color is clearly different from what the spec describes — excluded from results |
| `AMBIGUOUS` | Images do not show the color clearly enough to make a confident judgment — passed through with a note |

**Output:** List of `VerifiedCandidate`s with `drop: False`, sorted: `HIGH` spec confidence + `PASS` color first, then `MEDIUM`/`LOW`, then `AMBIGUOUS` at the end.

---

### Stage 4 — Present
*claude-sonnet · formats results for Danielle*

**Trigger:** List of `VerifiedCandidate`s from Stage 3.

**Behaviour:**
- Formats the top 10–15 results as product cards
- Best matches (`HIGH` + `PASS`) are shown first, then `MEDIUM`/`LOW`, then `AMBIGUOUS` in a clearly separated section
- If fewer than 3 confirmed matches exist, says so plainly before showing results
- Written for Danielle — plain language, not pipeline terminology

**Each result card contains:**

| Field | Description |
|-------|-------------|
| Photo | Product image, rendered inline |
| Title + link | Product name as a clickable link opening the product page directly |
| Price | As extracted, including sale price if present |
| Vendor | Site or seller name |
| Color | Plain language description of the actual color seen in the images |
| Dimensions | Size or fit details if present |
| Material | Material or construction details if present |
| Note | 1–2 sentences explaining why this is or isn't a strong match |

**Output:** Structured JSON list of result objects (for future custom UI) plus a markdown rendering for Open WebUI. The JSON is the canonical output — markdown is derived from it.

---

## 5. Refinement Loop

When Danielle is not satisfied with results, she provides plain-language feedback in the chat. The agent merges this into the existing `ProductSpec` and re-runs from Stage 2.

### 5.1 Spec merging

The `ProductSpec` is not discarded between rounds. Refinements are applied as patches:

| Danielle says | What changes |
|---------------|--------------|
| "More muted color" | Updates `color_description`; all other fields unchanged |
| "Smaller please" | Updates `dimensions`; all other fields unchanged |
| "Try Etsy only" | Replaces `search_targets` with Etsy; all spec fields unchanged |
| "Under $50" | Sets or updates `budget_max`; all other fields unchanged |
| "Something more affordable" | Agent updates `budget_max` and reconsiders `search_targets` for value-oriented sites |
| "Different brand" | Adds brand exclusion to `constraints`; agent may update `search_targets` |

### 5.2 Site re-selection on refinement

When a refinement implies a different set of sites (e.g. "more affordable", "try somewhere local", "different brand"), the agent re-reasons about `search_targets` from scratch using the updated spec. It does not simply add or remove one site — it reconsiders the full list given the new constraints.

### 5.3 Loop termination

The loop continues as long as Danielle provides refinements. It ends when she clicks through to a product page, explicitly says she is done, or closes the chat. There is no hard limit on refinement rounds.

---

## 6. System Boundaries

### 6.1 Responsibilities

| Component | Owns |
|-----------|------|
| **Browser Use v3** | All web interaction — search results pages, product pages, image URL extraction. No judgment. |
| **Claude (Stages 1, 3, 4)** | All reasoning — site selection, spec extraction, color assessment, result presentation, refinement merging. |
| **FastAPI service** | Orchestration — routing turns, managing the `ProductSpec` state, running the pipeline, streaming results back to Open WebUI. |
| **Open WebUI** | Front-end — chat interface, markdown rendering, link handling. Connects via the OpenAI-compatible `/v1/chat/completions` endpoint. |

### 6.2 What this system does not do

- Does not place orders or interact with checkout flows
- Does not store payment information
- Does not track prices over time
- Does not create accounts on retail sites
- Does not follow redirects to login-gated pages

### 6.3 Front-end flexibility

The pipeline produces a structured JSON list of result objects. The current front-end is Open WebUI with markdown rendering. A custom web UI (image grid, tappable cards) can be introduced later without changing the pipeline — only the present stage's rendering layer changes.

---

## 7. Open Questions

These are not blockers for the first build but should be decided before a production deployment.

| Question | Detail |
|----------|--------|
| **Session persistence** | Should the `ProductSpec` and search history persist across chat sessions? If Danielle comes back the next day, does the agent remember what she was looking for? |
| **Result deduplication** | If the same product appears on two different sites (e.g. Amazon and the brand's own site), should it be shown once or twice? |
| **Image hosting** | Product images are served from retailer CDNs. They can expire or be removed. Should the system cache image URLs or fetch and re-host them? |
| **Poshmark / resale** | Resale listings are one-of-a-kind and sell quickly. Should these be flagged with a "buy soon" note given stock risk? |
| **Browser Use cost** | Each Browser Use task opens multiple product pages. A 5-site search opening 10 pages each is 50 page loads. Cost per search round should be monitored. |

---

## 8. Recommended Build Order

Build and validate one stage at a time before wiring them together.

| Step | Task |
|------|------|
| 1 | **Data models** — define all Pydantic models in `models.py`. No logic, just the schema. Validate the shape before writing any stage code. |
| 2 | **FastAPI skeleton** — `/v1/models` and `/v1/chat/completions` endpoints returning stubs. Confirm Open WebUI can connect and see the model in the dropdown. |
| 3 | **Stage 1 — clarify** — confirm `ProductSpec` is produced correctly with a real conversation. Validate `confirmed: True` triggers correctly. |
| 4 | **Stage 2 smoke test** — single site, single Browser Use v3 task, inspect raw `RawCandidate` output. Validate the structured output schema. |
| 5 | **Stage 2 full** — all sites in parallel. Validate error handling and result merging across sources. |
| 6 | **Stage 3 — verify + color** — run against Stage 2 output. Validate color assessment quality against known test cases (e.g. a known dusty rose listing, a known wrong-color listing). |
| 7 | **Stage 4 — present** — wire the full pipeline end to end. Validate card rendering in Open WebUI. |
| 8 | **Refinement loop** — validate spec merging and re-search with plain-language inputs across multiple rounds. |
