"""
Shopping Agent — LLM client helpers.

Thin wrappers around Anthropic and Ollama so stage code stays clean.
"""

import json
import logging
import re
from typing import Any

import anthropic
from ollama import Client as OllamaClient

import config

log = logging.getLogger("shopping_agent.llm")


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


def chat_with_images(
    system: str,
    text: str,
    image_urls: list[str],
) -> str:
    """Send a Claude message with inline image URLs for vision assessment.

    Always uses Claude regardless of LLM_PROVIDER — Ollama vision is not
    used for the combined verify+color stage.
    """
    log.info("chat_with_images  model=%s  images=%d", config.CLAUDE_MODEL, len(image_urls))
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    content_blocks: list[dict] = []
    for url in image_urls[:3]:
        content_blocks.append({
            "type": "image",
            "source": {"type": "url", "url": url},
        })
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


def parse_json(text: str) -> Any:
    """Extract a JSON object or array from LLM output, stripping markdown fences."""
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = cleaned.find(start_char)
        end = cleaned.rfind(end_char)
        if start != -1 and end > start:
            return json.loads(cleaned[start : end + 1])
    return json.loads(cleaned)
