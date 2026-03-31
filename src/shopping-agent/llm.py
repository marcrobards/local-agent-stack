"""
Shopping Agent — LLM client helpers.

Thin wrappers around Anthropic and Ollama so stage code stays clean.
"""

import base64
import json
import logging
import re
from typing import Any

import anthropic
import requests
from ollama import Client as OllamaClient

import config

log = logging.getLogger("shopping_agent.llm")

# ---------------------------------------------------------------------------
# Image fetch timeout — keep short; verify stage has many concurrent calls
# ---------------------------------------------------------------------------

_IMAGE_FETCH_TIMEOUT = 5  # seconds

# Supported media types for Claude vision
_SUPPORTED_IMAGE_TYPES = frozenset({
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
})


# ---------------------------------------------------------------------------
# Chat helpers
# ---------------------------------------------------------------------------

def chat(messages: list[dict]) -> str:
    """Send a chat request using the configured LLM provider."""
    if config.LLM_PROVIDER == "claude":
        return _claude_chat(messages)
    return _ollama_chat(messages)


def _claude_chat(messages: list[dict]) -> str:
    log.info("claude_chat  model=%s  messages=%d", config.CLAUDE_MODEL, len(messages))
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    system_parts = []
    chat_msgs = []
    for msg in messages:
        if msg["role"] == "system":
            system_parts.append(msg["content"])
        else:
            chat_msgs.append({"role": msg["role"], "content": msg["content"]})

    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=4096,
        system="\n\n".join(system_parts) if system_parts else anthropic.NOT_GIVEN,
        messages=chat_msgs,
    )
    content = response.content[0].text
    log.info("claude_chat  response_len=%d", len(content))
    return content


def _ollama_chat(messages: list[dict]) -> str:
    log.info("ollama_chat  model=%s  messages=%d", config.OLLAMA_LLM_MODEL, len(messages))
    client = OllamaClient(host=config.OLLAMA_BASE_URL)
    response = client.chat(model=config.OLLAMA_LLM_MODEL, messages=messages)
    content = response["message"]["content"]
    log.info("ollama_chat  response_len=%d", len(content))
    return content


# ---------------------------------------------------------------------------
# Image fetching
# ---------------------------------------------------------------------------

def _fetch_image_as_base64(url: str) -> tuple[str, str] | None:
    """Fetch a product image URL and return (base64_data, media_type).

    Returns None if the fetch fails or the response is not a usable image.

    Retailer CDNs block Anthropic's servers when images are passed as URL
    references — the API fetches them server-side without browser headers,
    which triggers 403s on most CDNs (Bonobos imgix, Patagonia demandware,
    UNIQLO image servers, etc.). Fetching here with a browser User-Agent and
    base64-encoding the result is the reliable path.
    """
    try:
        resp = requests.get(
            url,
            timeout=_IMAGE_FETCH_TIMEOUT,
            headers={
                # Mimic a browser request — many CDNs check User-Agent
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                # Some CDNs validate Referer against the product domain
                "Referer": url,
                "Accept": "image/webp,image/png,image/*,*/*;q=0.8",
            },
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        log.debug("_fetch_image_as_base64  fetch error  url=%s  exc=%s", url, exc)
        return None

    if resp.status_code != 200:
        log.debug(
            "_fetch_image_as_base64  non-200  url=%s  status=%d",
            url, resp.status_code,
        )
        return None

    if not resp.content:
        log.debug("_fetch_image_as_base64  empty body  url=%s", url)
        return None

    # Detect content type from response headers; fall back to JPEG
    content_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip().lower()
    if content_type not in _SUPPORTED_IMAGE_TYPES:
        # Some CDNs return "application/octet-stream" for images — assume JPEG
        if resp.content[:3] == b"\xff\xd8\xff":
            content_type = "image/jpeg"
        elif resp.content[:8] == b"\x89PNG\r\n\x1a\n":
            content_type = "image/png"
        elif resp.content[:4] == b"RIFF" and resp.content[8:12] == b"WEBP":
            content_type = "image/webp"
        else:
            log.debug(
                "_fetch_image_as_base64  unsupported type  url=%s  type=%s",
                url, content_type,
            )
            return None

    # Skip suspiciously small responses — likely placeholders or 1x1 tracking pixels
    if len(resp.content) < 500:
        log.debug(
            "_fetch_image_as_base64  too small (%d bytes), skipping  url=%s",
            len(resp.content), url,
        )
        return None

    encoded = base64.standard_b64encode(resp.content).decode("utf-8")
    log.debug(
        "_fetch_image_as_base64  ok  url=%s  type=%s  bytes=%d",
        url, content_type, len(resp.content),
    )
    return encoded, content_type


# ---------------------------------------------------------------------------
# Vision call
# ---------------------------------------------------------------------------

def chat_with_images(
    system: str,
    text: str,
    image_urls: list[str],
) -> str:
    """Send a Claude message with product images for vision assessment.

    Fetches each image URL from this container (with browser headers) and
    sends base64-encoded data to the Anthropic API. This is more reliable
    than passing CDN URLs directly — Anthropic's servers fetch URL-type
    images without browser headers, which most retailer CDNs block.

    Always uses Claude regardless of LLM_PROVIDER — Ollama vision is not
    used for the combined verify+color stage.

    If all image fetches fail, appends an explicit instruction to the prompt
    so Claude sets color_result to AMBIGUOUS rather than guessing.
    """
    log.info("chat_with_images  model=%s  images=%d", config.CLAUDE_MODEL, len(image_urls))
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    content_blocks: list[dict] = []
    successful = 0
    failed = 0

    for url in image_urls[:3]:
        result = _fetch_image_as_base64(url)
        if result:
            data, media_type = result
            content_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": data,
                },
            })
            successful += 1
        else:
            failed += 1
            log.info("chat_with_images  image fetch failed  url=%s", url)

    log.info(
        "chat_with_images  fetched=%d  failed=%d",
        successful, failed,
    )

    # If no images loaded, tell Claude explicitly so it returns AMBIGUOUS
    # rather than hallucinating a color assessment from nothing.
    if successful == 0:
        text = (
            text
            + "\n\nNote: Product images could not be retrieved. "
            "You have no visual information about this product's color. "
            "Set color_result to AMBIGUOUS and color_description to "
            "'Images unavailable — color could not be assessed'."
        )

    content_blocks.append({"type": "text", "text": text})

    response = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": content_blocks}],
    )
    result = response.content[0].text
    log.info("chat_with_images  response_len=%d", len(result))
    return result


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------

def parse_json(text: str) -> Any:
    """Extract a JSON object or array from LLM output, stripping markdown fences."""
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = cleaned.find(start_char)
        end = cleaned.rfind(end_char)
        if start != -1 and end > start:
            return json.loads(cleaned[start : end + 1])
    return json.loads(cleaned)