# Online Shopping Workflow

This workflow helps the user find specific products online. It is optimized
for searches where color accuracy is critical — the most common failure mode
in standard searches.

## Stages

1. **01-clarify-request** — Conversational clarification. Gathers a complete
   product spec from the user, asking targeted questions. Uses the user's
   stored preferences from memory. Ends with a confirmed spec.

2. **02-search** — Executes searches across five sources using the confirmed
   spec. Returns candidate product URLs for verification.

3. **02-verify** — Confirms each candidate link is real and assesses spec
   match confidence. Does not assess color.

4. **02a-color-verify** — Vision model (qwen2.5vl:7b) checks product images
   against the color description. Passes, fails, or marks ambiguous.

5. **03-present** — Formats color-verified results for the user in Open WebUI.
   Tappable links, friendly language, best matches first.

## Memory scoping

- Read at stage 01: `user_id="danielle"` — their preferences, past searches
- Written after stage 03: `user_id="danielle"` — successful session stored
- Session-scoped ephemeral data: `user_id="session_<timestamp>"`

## Models

- Text stages (01, 02, 02-verify, 03): qwen2.5:7b via Ollama
- Color verification (02a): qwen2.5vl:7b via Ollama

## Sources searched (stage 02)

Always: Amazon, Google Shopping, Etsy, Target/Walmart
Clothing only: Poshmark
