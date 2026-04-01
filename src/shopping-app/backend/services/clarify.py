import json
import os
import re

from anthropic import AsyncAnthropic

client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SYSTEM_PROMPT = """You are a shopping assistant helping Danielle find products online. Your job is to gather enough detail about what she's looking for so we can search for it effectively.

Guidelines:
- Ask focused clarifying questions, one at a time
- Ask about: item type, color/style, size, material, price range, occasion/use
- Reference any known preferences provided below when relevant
- When you have enough detail to search effectively, output a JSON block with the search specification and the marker "spec_ready": true
- The spec JSON must include at minimum: item_description, color, price_max, notes
- Format the spec as: ```json
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

    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=system,
        messages=messages,
    )

    reply = response.content[0].text

    spec = None
    if '"spec_ready": true' in reply or '"spec_ready":true' in reply:
        try:
            json_match = re.search(r"```json\s*(\{.*?\})\s*```", reply, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(1))
                if parsed.get("spec_ready"):
                    spec = parsed.get("spec", parsed)
        except (json.JSONDecodeError, AttributeError):
            pass

    return reply, spec
