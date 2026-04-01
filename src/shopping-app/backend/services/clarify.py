import json
import logging
import os
import re

from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SYSTEM_PROMPT = """You are a shopping assistant helping Danielle find products online. Your job is to gather enough detail about what she's looking for so we can search for it effectively.

Guidelines:
- Ask focused clarifying questions, one at a time
- Ask about: item type, color/style, size, material, price range, occasion/use
- Reference any known preferences provided below when relevant
- When you have enough detail to search effectively, write a short friendly confirmation of what you'll search for, then on a NEW LINE output the spec JSON block
- The confirmation should read naturally, e.g. "Got it! I'll search for a navy blue lightweight zip-up hoodie in size small, under $100."
- The spec JSON must include at minimum: item_description, color, price_max, notes
- Format the spec block as: ```spec
{{"spec_ready": true, "spec": {{"item_description": "...", "color": "...", "price_max": "...", "notes": "..."}}}}
```
- Keep your tone friendly and concise — this is a tool, not a chatbot
- Don't ask unnecessary questions — if the user has given enough info, produce the spec

{preferences_section}"""


async def clarify(
    messages: list[dict], preferences: list[dict] | None = None
) -> tuple[str, dict | None]:
    """Returns (assistant_reply, spec_or_none)."""
    prefs_text = ""
    if preferences:
        prefs_text = "Known preferences:\n" + "\n".join(
            f"- {p['key']}: {p['value']}" for p in preferences
        )

    system = SYSTEM_PROMPT.format(preferences_section=prefs_text)

    logger.info("Calling Claude clarify with %d messages", len(messages))
    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=system,
        messages=messages,
    )

    reply = response.content[0].text
    logger.info("Claude reply: %s", reply[:200])

    # Extract spec if present
    spec = None
    display_reply = reply

    # Try ```spec or ```json fenced blocks
    spec_match = re.search(r"```(?:spec|json)\s*(\{.*?\})\s*```", reply, re.DOTALL)
    if spec_match:
        try:
            parsed = json.loads(spec_match.group(1))
            if parsed.get("spec_ready"):
                spec = parsed.get("spec", parsed)
                logger.info("Spec extracted: %s", json.dumps(spec))
            # Remove the JSON block from displayed message
            display_reply = reply[: spec_match.start()].strip()
            if not display_reply:
                display_reply = "Got it! I have everything I need. Tap 'Search for this' to start searching."
        except (json.JSONDecodeError, AttributeError) as e:
            logger.warning("Failed to parse spec JSON: %s", e)

    # Fallback: try to find raw spec_ready JSON anywhere
    if spec is None and ('"spec_ready": true' in reply or '"spec_ready":true' in reply):
        try:
            raw_match = re.search(r"\{[^{}]*\"spec_ready\"[^{}]*\{[^{}]*\}[^{}]*\}", reply, re.DOTALL)
            if raw_match:
                parsed = json.loads(raw_match.group(0))
                if parsed.get("spec_ready"):
                    spec = parsed.get("spec", parsed)
                    logger.info("Spec extracted (fallback): %s", json.dumps(spec))
                    display_reply = reply[: raw_match.start()].strip()
                    if not display_reply:
                        display_reply = "Got it! I have everything I need. Tap 'Search for this' to start searching."
        except (json.JSONDecodeError, AttributeError) as e:
            logger.warning("Fallback spec parse failed: %s", e)

    return display_reply, spec
