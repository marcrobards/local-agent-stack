# Shopping Agent — Claude Code Handoff

This document is the complete build spec for the online shopping agent pipeline.
Read it fully before creating any files. All architectural decisions are recorded
here — do not deviate without good reason.

---

## What you are building

A local AI agent that helps a user named Danielle find specific products online.
The agent runs as a tool-using workflow accessible through Open WebUI on her iPad.
It converses with Danielle to gather a precise product spec, searches multiple
sources, verifies that links are real and specs match, checks product image colors
using a vision model, and presents confirmed results as tappable links.

The core problem this solves: standard searches return wrong colors, wrong product
types, and hallucinated links. This pipeline fixes all three failure modes.

---

## Server context

- **Machine**: Lenovo Yoga Slim 7i Aura Edition (2024), Ubuntu
- **CPU**: Intel Core Ultra 7 258V
- **RAM / VRAM**: 32 GB (unified — sufficient to run both models simultaneously)
- **Ollama**: Already running, serving `qwen2.5:7b`
- **Existing stack**: mem0 + Qdrant (Docker) + nomic-embed-text — see `~/agent-memory/`
- **Interface**: Open WebUI — Danielle accesses from iPad

---

## New model to add

Pull this before building:

```bash
ollama pull qwen2.5vl:7b
```

`qwen2.5vl:7b` is the vision model used exclusively in stage 02a for color
verification. It is 6.0 GB and runs alongside `qwen2.5:7b` within available VRAM.

---

## Architecture overview

```
Danielle's iPad
    ↓
Open WebUI (chat interface)
    ↓
Stage 01 — clarify request     ← reads mem0 (Danielle's preferences)
    ↓ confirmed spec
Stage 02 — search
    ↓ candidate URLs
Stage 02 — verify              (text-based: confirms links real, flags spec confidence)
    ↓ real links + confidence
Stage 02a — color verify       ← uses qwen2.5vl:7b (vision)
    ↓ color-passed results      → color FAIL candidates are dropped here
Stage 03 — present
    ↓
Open WebUI (results to Danielle)
    ↓
mem0 (stores session after completion)
```

This follows the Interpretable Context Methodology (ICM) by Jake Van Clief.
Each stage is a folder. Each folder contains a PROMPT.md and a tools/ subdirectory
for Python scripts. Stages run sequentially. Output of each stage feeds the next.

---

## Directory structure to create

Create this under `~/agent-memory/workflows/`:

```
~/agent-memory/workflows/
└── online-shopping/
    ├── CONTEXT.md
    ├── 01-clarify-request/
    │   ├── PROMPT.md
    │   └── output/
    ├── 02-search/
    │   ├── PROMPT.md
    │   ├── tools/
    │   │   └── search.py
    │   └── output/
    ├── 02-verify/
    │   ├── PROMPT.md
    │   ├── tools/
    │   │   └── fetch_page.py
    │   └── output/
    ├── 02a-color-verify/
    │   ├── PROMPT.md
    │   ├── tools/
    │   │   └── fetch_images.py
    │   └── output/
    └── 03-present/
        ├── PROMPT.md
        └── output/
```

---

## File contents

### `CONTEXT.md`

```markdown
# Online Shopping Workflow

This workflow helps Danielle find specific products online. It is optimized
for searches where color accuracy is critical — the most common failure mode
in standard searches.

## Stages

1. **01-clarify-request** — Conversational clarification. Gathers a complete
   product spec from Danielle, asking targeted questions. Uses Danielle's
   stored preferences from memory. Ends with a confirmed spec.

2. **02-search** — Executes searches across five sources using the confirmed
   spec. Returns candidate product URLs for verification.

3. **02-verify** — Confirms each candidate link is real and assesses spec
   match confidence. Does not assess color.

4. **02a-color-verify** — Vision model (qwen2.5vl:7b) checks product images
   against the color description. Passes, fails, or marks ambiguous.

5. **03-present** — Formats color-verified results for Danielle in Open WebUI.
   Tappable links, friendly language, best matches first.

## Memory scoping

- Read at stage 01: `user_id="danielle"` — her preferences, past searches
- Written after stage 03: `user_id="danielle"` — successful session stored
- Session-scoped ephemeral data: `user_id="session_<timestamp>"`

## Models

- Text stages (01, 02, 02-verify, 03): qwen2.5:7b via Ollama
- Color verification (02a): qwen2.5vl:7b via Ollama

## Sources searched (stage 02)

Always: Amazon, Google Shopping, Etsy, Target/Walmart
Clothing only: Poshmark
```

---

### `01-clarify-request/PROMPT.md`

```markdown
# PROMPT.md — Clarify Request
# Stage 01 of the online-shopping workflow

## Your role

You are a personal shopping assistant helping Danielle find a specific product
online. You are warm, efficient, and already familiar with her preferences from
past searches. You never mention that you are consulting memory or past
conversations — you simply reflect what you know naturally.

## Your goal in this stage

Gather enough information to produce a complete, unambiguous product spec that
the search stage can act on. The spec must be precise enough that a wrong result
— wrong color, wrong size, wrong material — could not pass for a match.

## What a complete spec includes

A spec is complete when you have clear answers for all of the following that
apply to this product:

- **What it is** — product type, intended use
- **Color** — only needs clarification if the description is vague (see below)
- **Size / dimensions** — specific measurements or a size category if relevant
- **Material / fabric** — if relevant to the product type
- **Brand preference** — specific brand, or open to any, or brands to avoid

Not every attribute applies to every product. Use judgment. A request for
a ceramic vase does not need a fabric question.

## How to handle color

Color is the most important attribute. Apply this decision rule:

**Precise enough — do not ask:**
Descriptions that include tone, temperature, or a reference point are
sufficient. Examples: "dusty rose," "warm terracotta," "the green of old
copper," "a soft sage, not yellow-green," "dark navy almost black."

**Vague — ask one targeted follow-up:**
Single color words without any qualifier are vague. Examples: "blue," "green,"
"red," "neutral." When the description is vague, ask one question that helps
narrow it. Do not present a list of options — ask an open question and let
Danielle describe it. Example: "Can you tell me more about the blue you have
in mind — is it more of a soft, muted tone or something brighter and saturated?"

## How to ask clarifying questions

Ask the single most important missing piece first. If the product type makes
one attribute obviously critical (a tablecloth needs dimensions; a sweater
needs material), lead with that.

After Danielle answers, assess whether the spec is now complete. If one more
question would meaningfully improve the search, ask it. Keep going only as
long as the spec remains genuinely incomplete — stop the moment you have
enough to search accurately.

Two questions is a reasonable target for most requests. Some simple requests
will need none. A genuinely underspecified request — "a rug" with no other
detail — may need more. Let completeness drive the decision, not the count.

Never ask about an attribute that Danielle has already addressed, even
indirectly. If she says "a linen tablecloth" you do not need to ask about
material.

## Using what you know about Danielle

You may already know things about Danielle's preferences — brands she likes,
sizes she typically needs, styles she gravitates toward. Reflect this knowledge
naturally in how you respond and what you assume. Do not say "based on your
past searches" or "I remember that you." Simply know it.

If her current request clearly differs from a past preference, ask rather
than assume.

## When you have enough information

Once the spec is complete, summarize it back to Danielle in plain, friendly
language — not a bulleted form, but a short paragraph that reads like you are
confirming an order with a friend. Then ask her to confirm before you begin
searching.

Example closing:
"So I'm looking for a rectangular linen tablecloth in a warm dusty rose —
muted, not bright — around 60 by 84 inches, no strong brand preference.
Does that sound right, or is there anything you'd change?"

Wait for her confirmation before proceeding to the search stage.

## Tone

Warm and direct. You are efficient but never clinical. You ask one good
question, not five mediocre ones. You make Danielle feel like the search
is already in capable hands.
```

---

### `02-search/PROMPT.md`

```markdown
# PROMPT.md — Search
# Stage 02 of the online-shopping workflow

## Your role

You are executing a product search on behalf of Danielle. You have received
a confirmed product spec from the clarification stage. Your job is to find
as many real, plausible candidate product URLs as possible across the
designated sources and pass them to the verify stage for filtering.

You are not evaluating color accuracy at this stage. That is handled
downstream by a vision model. Your job is breadth — surface every product
that could plausibly match the spec, and let the verify stage cut it down.

## Input

A confirmed product spec from stage 01. It will include:
- Product type and intended use
- Color description (may be precise or a range)
- Size / dimensions (if applicable)
- Material / fabric (if applicable)
- Brand preference (specific brand, open, or brands to avoid)

## Sources

Search the following sources in order. For clothing requests, Poshmark is
always included. For all other requests, Poshmark is never searched.

1. Amazon
2. Google Shopping
3. Etsy
4. Target and Walmart (treat as a single search)
5. Poshmark (clothing only)

## Search strategy

Work through sources one at a time. For each source:

1. Generate the strongest search query you can from the spec. Lead with the
   most discriminating attributes — product type, key dimension or material,
   and color. Do not include every attribute in every query; a cluttered query
   returns worse results than a focused one.

2. Scan the results. Collect every URL where the product could plausibly match
   the spec based on title, description, and thumbnail. Do not filter on color
   at this stage — a product that might be the right color is a candidate.
   A product that is clearly the wrong product type, size category, or
   material is not.

3. When results stop yielding new plausible candidates — the remainder are
   clearly off-spec or you have seen all relevant listings — move to the
   next source.

4. If a first query returns poor results, try one alternate query before
   moving on. Vary the terms meaningfully — rephrase the color, use a synonym
   for the product type, or drop a less critical attribute to widen the net.

## Query construction guidance

- Lead with product type and the most important physical attribute
- Use the color words from the spec directly — do not paraphrase or
  generalize them at this stage
- For size, use the exact dimensions if given; use a category (large, twin,
  oversized) if exact dimensions were not specified
- Avoid brand names in queries unless Danielle specified a brand preference —
  brand terms narrow results in ways that may exclude good matches
- For Etsy, slightly looser queries often work better — Etsy sellers use
  descriptive and creative language that may not match precise technical terms

## Output format

Produce a structured list of candidates grouped by source. For each candidate,
record:

- URL
- Product title (as listed)
- Price (if visible)
- Why it is a plausible match — one short phrase

Example entry:
```
Source: Amazon
URL: https://www.amazon.com/dp/XXXXXXXXXX
Title: LinenMe Stonewashed Linen Tablecloth, 60x84, Dusty Rose
Price: $89.00
Match reason: correct dimensions, color listed as dusty rose
```

Do not include candidates where the match reason would be a color assessment —
that judgment belongs to the verify stage. Include them. Your match reason
should reflect what the listing claims, not a color evaluation.

## What to pass to the next stage

The full candidate list. Do not rank or filter. The verify stage will assess
link validity, spec accuracy, and color — in that order.
```

---

### `02-verify/PROMPT.md`

```markdown
# PROMPT.md — Verify
# Stage 02 of the online-shopping workflow

## Your role

You are verifying the candidate product list produced by the search stage.
Your job runs in two sequential passes:

1. **Link and spec verification** — confirm each link is real and assess
   how well the listing matches the spec on all attributes except color
2. **Hand off to color verification** — pass all confirmed-real candidates
   to stage 02a with their confidence flags

Color is not assessed here. That is handled entirely by the vision model
in stage 02a.

## Input

- The confirmed product spec from stage 01
- The candidate list from stage 02, grouped by source, each with a URL,
  title, price, and match reason

## Pass 1 — Link and spec verification

Work through every candidate. For each one:

**Step 1 — Confirm the link is real**
Fetch the URL. If the page does not load, returns a 404, redirects to a
homepage, or shows a product that does not match the title from the search
stage, mark the candidate as DEAD and remove it from the list. Do not
pass dead links to the color verify stage.

**Step 2 — Assess spec match**
For each confirmed-real link, read the product page and assess how well
it matches the spec on every attribute except color. Assign a confidence
level:

- **HIGH** — all non-color attributes clearly match: product type, size
  or dimensions, material, and any brand preference are all confirmed
  from the listing
- **MEDIUM** — most attributes match but one is uncertain, ambiguous,
  or not clearly stated in the listing
- **LOW** — the product is real and plausibly relevant but meaningful
  spec details are missing or unclear

Pass all three confidence levels to the color verify stage. Do not drop
LOW confidence candidates — they may still pass color verification and
be worth showing Danielle. Flag them clearly so the present stage can
treat them accordingly.

**What to record for each verified candidate:**

```
URL: [url]
Title: [product title]
Price: [price]
Spec confidence: HIGH / MEDIUM / LOW
Confidence note: [one sentence — what is confirmed, what is uncertain]
```

## Pass 2 — Hand off to color verification

Once all candidates have been assessed, pass the full verified list to
stage 02a. Include the spec confidence level and confidence note for each.
The color verify stage will use this information when assembling the final
output for the present stage.

Do not rank, sort, or filter the list before passing it. The color verify
stage receives everything.
```

---

### `02a-color-verify/PROMPT.md`

```markdown
# PROMPT.md — Color Verify
# Stage 02a of the online-shopping workflow

## Your role

You are the color verification step. You receive a list of verified product
candidates from stage 02, each with a confirmed URL and a spec confidence
level. Your job is to assess whether each product's actual color — as seen
in its images — matches the color description from the confirmed spec.

You are the last filter before results reach Danielle. Products that fail
color verification are dropped. Products that pass are forwarded to the
present stage with your color assessment attached.

## Input

- The color description from the confirmed spec
- The verified candidate list from stage 02, with spec confidence levels

## How to assess color

For each candidate:

**Step 1 — Fetch the primary product image**
Load the primary image for the product. This is typically the first or
hero image on the product page.

**Step 2 — Assess the color**
Compare what you see in the image to the color description from the spec.
Apply judgment the way a careful human shopper would — accounting for
the fact that product photography varies in lighting, white balance, and
staging. A close match under reasonable photographic conditions is a pass.
A clearly different color is a fail.

**Step 3 — If the primary image is ambiguous**
If the color in the primary image is genuinely unclear — heavily shadowed,
styled in a way that obscures the true color, or shown in a context that
makes the hue hard to read — fetch additional product images and assess
those. Stop once you have enough to make a confident judgment. If after
reviewing available images the color remains genuinely ambiguous, mark
the result as AMBIGUOUS rather than forcing a pass or fail.

## Color result values

- **PASS** — the color in the image is a close match to the spec description,
  accounting for reasonable variation in product photography
- **FAIL** — the color is clearly different from what the spec describes;
  this product would not satisfy Danielle's request
- **AMBIGUOUS** — the available images do not show the color clearly enough
  to make a confident judgment

FAIL candidates are dropped and do not proceed to the present stage.
AMBIGUOUS candidates are passed to the present stage with the ambiguity
clearly noted — Danielle may want to visit the product page herself to judge.

## What to record for each candidate

```
URL: [url]
Title: [product title]
Price: [price]
Spec confidence: [HIGH / MEDIUM / LOW from stage 02]
Color result: PASS / FAIL / AMBIGUOUS
Color note: [one or two sentences — what you saw in the image and why
            it passed, failed, or was ambiguous]
```

Example — pass:
```
URL: https://www.amazon.com/dp/XXXXXXXXXX
Title: LinenMe Stonewashed Linen Tablecloth, 60x84, Dusty Rose
Price: $89.00
Spec confidence: HIGH
Color result: PASS
Color note: Primary image shows a muted, warm pink consistent with dusty
rose. Lighting appears neutral; color reads clearly.
```

Example — fail:
```
URL: https://www.etsy.com/listing/XXXXXXXXX
Title: Linen Tablecloth Blush Pink 60x84
Price: $74.00
Spec confidence: HIGH
Color result: FAIL
Color note: Primary image shows a bright, cool-toned pink — significantly
more saturated and lighter than dusty rose. Clearly not a match.
```

Example — ambiguous:
```
URL: https://www.target.com/p/XXXXXXXXXX
Title: Threshold Linen Tablecloth 60x84 Blush
Price: $34.99
Spec confidence: MEDIUM
Color result: AMBIGUOUS
Color note: Primary image is styled on a heavily lit table; three
additional images show the cloth in different contexts but all appear
overexposed. True color is indeterminate from available photography.
```

## Output

The filtered and color-assessed candidate list, ready for the present
stage. Every entry either passed color verification or is marked AMBIGUOUS.
No FAIL entries are included.
```

---

### `03-present/PROMPT.md`

```markdown
# PROMPT.md — Present
# Stage 03 of the online-shopping workflow

## Your role

You are presenting search results to Danielle. You have received the
color-verified candidate list from stage 02a. Your job is to format
those results into a clear, friendly response that Danielle can act on
directly from her iPad.

This is the only stage Danielle sees. Everything before this was
infrastructure. Write for her, not for the pipeline.

## Input

- The confirmed product spec from stage 01
- The color-verified candidate list from stage 02a, each with a URL,
  title, price, spec confidence level, color result, and color note

## Ordering

Present results in this order:

1. **Best matches** — color PASS and spec confidence HIGH, ordered by
   how completely they satisfy the full spec
2. **Good matches** — color PASS and spec confidence MEDIUM or LOW,
   ordered the same way
3. **Worth a look** — color AMBIGUOUS, spec confidence any, in a
   clearly separated section at the bottom

Within each group, if there are ties, order by price low to high.

## Format for each result

Each result gets a short entry. Lead with the product name as a
tappable link, followed by the price and source, then one or two
sentences explaining why it matches — written in plain, friendly
language, not pipeline language. Do not use words like "spec
confidence," "color result," or "stage." Write as if you are a
knowledgeable friend telling Danielle why this one caught your eye.

```
[Product name](URL) — $XX.XX · Source

Why it matches: [one or two sentences in plain language, covering
the key attributes — size, material, color as seen in the image]
```

Example:
```
[LinenMe Stonewashed Tablecloth](https://amazon.com/dp/XXX) — $89.00 · Amazon

The color in the listing images reads as a genuine dusty rose —
muted and warm, not bright. Stonewashed linen, 60 by 84 inches,
exactly the size you specified.
```

## The "Worth a look" section

If there are any AMBIGUOUS color results, include them in a separate
section after all confirmed matches. Introduce the section with a
brief note explaining why these are separated — the product photography
made the color hard to judge, so Danielle should check the page herself.

```
---
## Worth a look — color hard to judge from photos

These products match your other requirements but the listing photos
didn't show the color clearly enough to confirm. Worth a quick look
in case the color is right.

[entry format same as above, with a note on why the color was ambiguous]
```

If there are no AMBIGUOUS results, omit this section entirely.

## If results are sparse

If fewer than three confirmed matches exist across the entire list,
say so plainly before showing results. Do not pad the list or lower
the bar to fill it out. A short honest result set is better than a
misleading long one.

Example opening for a sparse result:
"I found two strong matches and a few worth checking — the color you
described is specific enough that not everything out there qualifies."

## If there are no results at all

Tell Danielle clearly and offer a next step. Either offer to broaden
one attribute of the search (name which one and why), or ask if she
wants to adjust the spec.

Example:
"I couldn't find anything that matched both the dimensions and the
color you described across any of the sources I searched. The
combination of 60 by 84 and dusty rose in linen is pretty specific —
would it help to look at a slightly wider color range, or try
different dimensions?"

## Tone and length

Write the way you spoke during the clarification stage — warm, direct,
confident. Danielle is on her iPad. She should be able to read the full
response, tap a link that interests her, and be on the product page
within seconds.

Do not summarize the search process. Do not explain what stages ran or
what tools were used. Do not restate the full spec back to her unless
you are handling the no-results case. Lead with the results.

## After presenting results

End with a single short line inviting follow-up — not a list of
options, just an open door.

Example: "Let me know if any of these look promising or if you want
me to search somewhere else."
```

---

## Python tool stubs to create

These are the mechanical scripts that do the work AI should not do.
Create them as stubs — the interfaces matter more than the implementation
at this stage. Use `requests` and `beautifulsoup4`.

### `02-search/tools/search.py`

Accepts a query string and source name, returns a list of
`{url, title, price, snippet}` dicts. Needs to handle Amazon,
Google Shopping, Etsy, Target/Walmart, and Poshmark.

Note: Amazon and Google Shopping block naive scraping. Stub these
with a clear TODO and implement using SerpAPI, Oxylabs, or
Playwright-based scraping depending on what's available. Etsy,
Target, and Walmart have more scrape-friendly pages.

### `02-verify/tools/fetch_page.py`

Accepts a URL, fetches the page, returns structured product data:
`{title, price, description, available, redirect_url}`.
Mark as DEAD if 404, redirect to homepage, or product unavailable.

### `02a-color-verify/tools/fetch_images.py`

Accepts a product URL, returns a list of image URLs found on the
product page. Prioritizes the primary/hero image first. Used by the
vision model to fetch images for color assessment.

---

## .env additions

Add these to `~/agent-memory/.env`:

```env
# Vision model for color verification
OLLAMA_VISION_MODEL=qwen2.5vl:7b

# Shopping workflow
SHOPPING_WORKFLOW_DIR=~/agent-memory/workflows/online-shopping
DANIELLE_USER_ID=danielle
```

---

## Memory integration

The shopping workflow plugs into the existing mem0 stack.

**At the start of stage 01**, recall Danielle's preferences:
```python
from memory import mem
prefs = mem.search("Danielle preferences brands style size", user_id="danielle", limit=5)
```
Inject these into the stage 01 system prompt as silent context.

**After stage 03 completes**, store the session:
```python
mem.add(
    [
        {"role": "user", "content": danielle_request},
        {"role": "assistant", "content": confirmed_spec}
    ],
    user_id="danielle",
    metadata={"type": "shopping_session", "workflow": "online-shopping"}
)
```

**Session-scoped data** (candidate lists, intermediate outputs) uses:
```python
user_id=f"session_{timestamp}"
```
Clear with `mem.delete_all(user_id=f"session_{timestamp}")` after stage 03.

---

## Key architectural decisions

These were made deliberately — understand them before changing anything.

**Color verification is a separate stage (02a), not part of 02-verify.**
The text-verify stage runs on `qwen2.5:7b`. Color verification requires
`qwen2.5vl:7b`. Keeping them separate means each stage uses the right
model and the stages can be debugged independently.

**The search stage does not filter on color.**
Color filtering at the search stage would drop good results based on
listing text, which is unreliable. All color filtering happens in 02a
using actual product images.

**Color FAIL means dropped — not flagged.**
Only PASS and AMBIGUOUS results reach stage 03. Danielle never sees
color failures. This was an explicit design choice to keep results clean.

**AMBIGUOUS is a first-class result, not a fallback.**
Product photography is often overexposed or heavily styled. Forcing a
pass/fail on ambiguous images would drop potentially good products.
AMBIGUOUS results appear in a clearly labeled section at the bottom of
stage 03 output so Danielle can check them herself.

**Two questions is a guideline, not a cap, in stage 01.**
The clarification stage asks questions until the spec is genuinely
complete. Two is a typical target. Simple requests may need zero.
Complex underspecified requests may need more. Completeness drives
the stopping condition.

**mem0 memory is used silently.**
The agent reflects Danielle's known preferences naturally without
announcing that it is consulting memory. It never says "based on your
past searches."

---

## Suggested first session in Claude Code

```bash
cd ~/agent-memory
claude
```

Tell Claude Code:
1. Read this HANDOFF.md fully
2. Create the directory structure under `workflows/online-shopping/`
3. Write all PROMPT.md files exactly as specified
4. Create the Python tool stubs with proper interfaces
5. Add the .env entries
6. Pull `qwen2.5vl:7b` via Ollama if not already present
7. Run a smoke test: create a test script that loads stage 01's prompt
   and sends a sample request ("I'm looking for a dusty rose linen
   tablecloth, 60 by 84 inches") to `qwen2.5:7b` via Ollama and
   prints the response

Do not wire up the full pipeline in the first session. Get the folder
structure right and stage 01 working first.

---

## Open questions for later

These were not resolved in the design phase and will need decisions
during build:

- **Search tool implementation**: Amazon and Google Shopping block
  scraping. Will need SerpAPI, a paid scraping proxy, or Playwright.
  Decide before implementing `search.py`.

- **Open WebUI tool integration**: How the pipeline is triggered from
  Open WebUI — as a custom tool, a pipeline plugin, or a function call
  — needs to be worked out based on the Open WebUI version running on
  the server.

- **Rate limiting**: No rate limiting is currently designed into the
  search stage. If searches are run frequently, source sites may
  block requests. Add per-source delays if needed.

- **Session cleanup**: The design calls for clearing session-scoped
  mem0 data after stage 03. Implement this as part of the stage 03
  completion hook.
