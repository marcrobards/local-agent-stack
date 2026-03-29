"""
title: Shopping Agent
author: local-agent-stack
version: 0.1.0
description: Helps the user find specific products online. Clarifies the
  request, searches multiple sources, verifies links, checks colors with a
  vision model, and presents tappable results.
requirements: ollama, mem0ai, qdrant-client, python-dotenv, requests, beautifulsoup4, anthropic
"""

import asyncio
import json
import logging
import sys
import os
import re
from pathlib import Path
from typing import Generator, Iterator, Union
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Logging — writes to container stdout (visible via `docker logs`)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("shopping_agent")

# ---------------------------------------------------------------------------
# Paths — everything lives under /app/local-agent-stack inside the container
# ---------------------------------------------------------------------------
REPO_ROOT      = Path("/app/local-agent-stack")
MEMORY_MODULE  = REPO_ROOT / "src" / "agent-memory-layer"
WORKFLOW_DIR   = REPO_ROOT / "src" / "workflows" / "online-shopping"

for p in [str(MEMORY_MODULE), str(WORKFLOW_DIR / "02-search" / "tools"),
          str(WORKFLOW_DIR / "02-verify" / "tools"),
          str(WORKFLOW_DIR / "02a-color-verify" / "tools")]:
    if p not in sys.path:
        sys.path.insert(0, p)

from ollama import Client as OllamaClient
import anthropic

# ---------------------------------------------------------------------------
# Runtime config — read from environment, with sane defaults for Docker
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL  = os.getenv("OLLAMA_BASE_URL",  "http://ollama:11434")
TEXT_MODEL       = os.getenv("OLLAMA_LLM_MODEL",    "qwen2.5:7b")
VISION_MODEL     = os.getenv("OLLAMA_VISION_MODEL", "qwen2.5vl:7b")
USER_ID = os.getenv("USER_ID",    "user_1")
LLM_PROVIDER     = os.getenv("LLM_PROVIDER", "ollama")           # "ollama" or "claude"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL      = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_prompt(stage: str) -> str:
    return (WORKFLOW_DIR / stage / "PROMPT.md").read_text()


def _ollama_chat(model: str, messages: list) -> str:
    log.info("ollama_chat  model=%s  messages=%d", model, len(messages))
    client = OllamaClient(host=OLLAMA_BASE_URL)
    response = client.chat(model=model, messages=messages)
    content = response["message"]["content"]
    log.info("ollama_chat  response_len=%d  preview=%.200s", len(content), content)
    return content


def _claude_chat(messages: list) -> str:
    """Send a chat request to the Anthropic API (Claude)."""
    log.info("claude_chat  model=%s  messages=%d", CLAUDE_MODEL, len(messages))
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Separate system prompt from conversation messages
    system_parts = []
    chat_msgs = []
    for msg in messages:
        if msg["role"] == "system":
            system_parts.append(msg["content"])
        else:
            chat_msgs.append({"role": msg["role"], "content": msg["content"]})

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system="\n\n".join(system_parts) if system_parts else anthropic.NOT_GIVEN,
        messages=chat_msgs,
    )
    content = response.content[0].text
    log.info("claude_chat  response_len=%d  preview=%.200s", len(content), content)
    return content


def _text_chat(messages: list) -> str:
    """Route text LLM calls to either Ollama or Claude based on LLM_PROVIDER."""
    if LLM_PROVIDER == "claude":
        return _claude_chat(messages)
    return _ollama_chat(TEXT_MODEL, messages)


def _recall_user(query: str) -> str:
    """Pull relevant memories for the user. Fails silently if mem0 is down."""
    try:
        from memory import mem
        log.info("memory_recall  user_id=%s  query=%.120s", USER_ID, query)
        hits = mem.search(query, user_id=USER_ID, limit=5)
        results = hits.get("results", [])
        log.info("memory_recall  hits=%d", len(results))
        if not results:
            return ""
        lines = "\n".join(f"- {r['memory']}" for r in results)
        return f"Known preferences for the user:\n{lines}"
    except Exception:
        log.warning("memory_recall  FAILED", exc_info=True)
        return ""


def _store_session(original_request: str, confirmed_spec: str) -> None:
    try:
        from memory import mem
        log.info("memory_store  user_id=%s  request=%.120s", USER_ID, original_request)
        mem.add(
            [
                {"role": "user",      "content": original_request},
                {"role": "assistant", "content": confirmed_spec},
            ],
            user_id=USER_ID,
            metadata={"type": "shopping_session", "workflow": "online-shopping"},
        )
        log.info("memory_store  OK")
    except Exception:
        log.warning("memory_store  FAILED", exc_info=True)


def _extract_urls(text: str) -> list[str]:
    return re.findall(r"https?://[^\s\n\"'>]+", text)


# ---------------------------------------------------------------------------
# Stage runners
# ---------------------------------------------------------------------------

def _stage_clarify(conversation: list) -> str:
    log.info("━━━ STAGE: clarify ━━━")
    log.info("clarify  INPUT  user_message=%.300s", conversation[-1]["content"])
    system = _load_prompt("01-clarify-request")
    memory_context = _recall_user(conversation[-1]["content"])

    messages = [{"role": "system", "content": system}]
    if memory_context:
        messages.append({"role": "system", "content": memory_context})
    messages.extend(conversation)

    result = _text_chat(messages)
    log.info("clarify  OUTPUT  len=%d  preview=%.300s", len(result), result)
    return result


def _stage_search(spec: str) -> str:
    log.info("━━━ STAGE: search ━━━")
    log.info("search  INPUT  spec=%.500s", spec)
    system = _load_prompt("02-search")
    tool_results = _run_search_tools(spec)
    log.info("search  tool_results_len=%d", len(tool_results))

    user_content = spec
    if tool_results:
        user_content += f"\n\n--- Live search results ---\n{tool_results}"

    result = _text_chat([
        {"role": "system",  "content": system},
        {"role": "user",    "content": user_content},
    ])
    log.info("search  OUTPUT  len=%d  preview=%.500s", len(result), result)
    return result


def _run_search_tools(spec: str) -> str:
    try:
        from search import search_all, format_results
        query = spec.split("\n")[0][:120]
        sources = ["amazon", "google_shopping", "etsy", "target", "walmart"]
        log.info("search_tools  query=%.120s  sources=%s", query, sources)
        results = asyncio.run(search_all(query, sources=sources))
        formatted = format_results(results)
        log.info("search_tools  results=%d sources  formatted_len=%d", len(results), len(formatted))
        for r in results:
            log.info("search_tools  source=%s  candidates=%d  error=%s  elapsed=%.1fs",
                     r.source, len(r.candidates), r.error, r.elapsed)
            for c in r.candidates:
                log.info("search_tools    candidate  url=%s  title=%.80s  price=%s", c.url, c.title, c.price)
        return formatted
    except Exception:
        log.error("search_tools  FAILED", exc_info=True)
        return ""


def _stage_verify(spec: str, candidates: str) -> str:
    log.info("━━━ STAGE: verify ━━━")
    log.info("verify  INPUT  spec_len=%d  candidates_len=%d", len(spec), len(candidates))
    urls = _extract_urls(candidates)
    log.info("verify  INPUT  urls_found=%d  urls=%s", len(urls), urls[:10])
    system = _load_prompt("02-verify")
    page_data = _run_verify_tools(candidates)
    log.info("verify  page_data_len=%d", len(page_data))

    user_content = f"Confirmed product spec:\n{spec}\n\nCandidates:\n{candidates}"
    if page_data:
        user_content += f"\n\n--- Fetched page data ---\n{page_data}"

    result = _text_chat([
        {"role": "system", "content": system},
        {"role": "user",   "content": user_content},
    ])
    log.info("verify  OUTPUT  len=%d  preview=%.500s", len(result), result)
    return result


def _run_verify_tools(candidates: str) -> str:
    try:
        from fetch_page import fetch_page
        rows = []
        for url in _extract_urls(candidates)[:10]:
            try:
                log.info("verify_tool  fetching  url=%s", url)
                d = fetch_page(url)
                log.info("verify_tool  result  url=%s  status=%s  title=%.80s  price=%s  available=%s  redirect=%s",
                         url, d.get('status'), d.get('title'), d.get('price'),
                         d.get('available'), d.get('redirect_url'))
                rows.append(
                    f"URL: {url}\n"
                    f"Status: {d.get('status','UNKNOWN')}\n"
                    f"Title: {d.get('title','')}\n"
                    f"Price: {d.get('price','')}\n"
                    f"Available: {d.get('available', False)}\n"
                )
            except Exception:
                log.warning("verify_tool  FAILED  url=%s", url, exc_info=True)
                rows.append(f"URL: {url}\nStatus: DEAD\n")
        return "\n".join(rows)
    except Exception:
        log.error("verify_tools  FAILED (import or setup)", exc_info=True)
        return ""


def _stage_color_verify(spec: str, verified: str) -> str:
    log.info("━━━ STAGE: color_verify ━━━")
    log.info("color_verify  INPUT  spec_len=%d  verified_len=%d", len(spec), len(verified))
    system = _load_prompt("02a-color-verify")
    vision_results = _run_color_verify_tools(spec, verified)
    log.info("color_verify  vision_results_len=%d", len(vision_results))

    user_content = f"Color spec:\n{spec}\n\nVerified candidates:\n{verified}"
    if vision_results:
        user_content += f"\n\n--- Vision color assessments ---\n{vision_results}"

    result = _text_chat([
        {"role": "system", "content": system},
        {"role": "user",   "content": user_content},
    ])
    log.info("color_verify  OUTPUT  len=%d  preview=%.500s", len(result), result)
    return result


def _run_color_verify_tools(spec: str, candidates: str) -> str:
    try:
        import base64
        import requests as req
        from fetch_images import fetch_images

        rows = []
        for url in _extract_urls(candidates)[:8]:
            try:
                log.info("color_tool  fetching_images  url=%s", url)
                image_urls = fetch_images(url, max_images=2)
                log.info("color_tool  images_found=%d  url=%s  image_urls=%s", len(image_urls), url, image_urls[:2])
                if not image_urls:
                    continue
                img_resp = req.get(image_urls[0], timeout=10)
                img_resp.raise_for_status()
                img_b64 = base64.b64encode(img_resp.content).decode("utf-8")

                log.info("color_tool  vision_assess  url=%s  image=%s  img_size=%d bytes",
                         url, image_urls[0], len(img_resp.content))
                assessment = _ollama_chat(VISION_MODEL, [{
                    "role": "user",
                    "content": (
                        f"Product URL: {url}\n"
                        f"Color spec: {spec}\n\n"
                        "Assess this product image against the color spec.\n"
                        "Reply with:\nColor result: PASS / FAIL / AMBIGUOUS\n"
                        "Color note: [one or two sentences]"
                    ),
                    "images": [img_b64],
                }])
                log.info("color_tool  assessment  url=%s  result=%.200s", url, assessment)
                rows.append(f"URL: {url}\n{assessment}\n")
            except Exception as e:
                log.warning("color_tool  FAILED  url=%s  error=%s", url, e, exc_info=True)
                rows.append(
                    f"URL: {url}\nColor result: AMBIGUOUS\n"
                    f"Color note: Could not fetch image ({e})\n"
                )
        return "\n".join(rows)
    except Exception:
        log.error("color_verify_tools  FAILED (import or setup)", exc_info=True)
        return ""


def _stage_present(spec: str, color_verified: str) -> str:
    log.info("━━━ STAGE: present ━━━")
    log.info("present  INPUT  spec_len=%d  color_verified_len=%d", len(spec), len(color_verified))
    result = _text_chat([
        {"role": "system", "content": _load_prompt("03-present")},
        {"role": "user",   "content": (
            f"Confirmed product spec:\n{spec}\n\n"
            f"Color-verified candidates:\n{color_verified}"
        )},
    ])
    log.info("present  OUTPUT  len=%d  preview=%.500s", len(result), result)
    return result


# ---------------------------------------------------------------------------
# Spec-confirmed detection
# ---------------------------------------------------------------------------

def _is_spec_confirmed(messages: list) -> tuple[bool, str]:
    """
    Returns (confirmed, spec_text).
    Confirmed when the user's last message is a short affirmative after the
    assistant summarised the spec and asked for confirmation.
    """
    if len(messages) < 2:
        return False, ""

    last_user = messages[-1]["content"].lower().strip()
    affirmatives = {
        "yes", "yeah", "yep", "yup", "correct", "right", "ok", "okay",
        "sure", "absolutely", "perfect", "sounds good", "looks good",
        "that's right", "that's it", "go ahead", "go for it", "confirmed",
    }
    # Match exact or starts-with for short affirmatives
    is_affirmative = (
        last_user in affirmatives
        or any(last_user.startswith(a) for a in affirmatives)
    )
    if not is_affirmative:
        return False, ""

    # The spec is the last assistant message before the user's yes
    for msg in reversed(messages[:-1]):
        if msg["role"] == "assistant":
            return True, msg["content"]

    return False, ""


# ---------------------------------------------------------------------------
# The Pipeline class (Pipelines server expects this name)
# ---------------------------------------------------------------------------

class Pipeline:

    class Valves(BaseModel):
        LLM_PROVIDER: str = Field(
            default="ollama",
            description="LLM provider for text stages: 'ollama' (local) or 'claude' (Anthropic API)"
        )
        ANTHROPIC_API_KEY: str = Field(
            default="",
            description="Anthropic API key (required when LLM_PROVIDER is 'claude')"
        )
        CLAUDE_MODEL: str = Field(
            default="claude-sonnet-4-20250514",
            description="Claude model name (used when LLM_PROVIDER is 'claude')"
        )
        OLLAMA_BASE_URL: str = Field(
            default="http://ollama:11434",
            description="Ollama base URL (used for local text model and always for vision)"
        )
        TEXT_MODEL: str = Field(
            default="qwen2.5:7b",
            description="Ollama model for text stages (used when LLM_PROVIDER is 'ollama')"
        )
        VISION_MODEL: str = Field(
            default="qwen2.5vl:7b",
            description="Ollama model for color verification — always runs locally"
        )
        USER_ID: str = Field(
            default="test_user",
            description="mem0 user_id for the user's memory scope"
        )

    def __init__(self):
        self.type   = "manifold"  # was "pipe"
        self.id     = "shopping_agent"
        self.name   = "Shopping Agent"
        self.valves = self.Valves()

    def pipelines(self) -> list[dict]:
        return [{"id": "shopping_agent", "name": ""}]

    def pipe(
        self,
        user_message: str,
        model_id: str,
        messages: list[dict],
        body: dict,
    ) -> Union[str, Generator, Iterator]:
        """
        Called by the Pipelines server on every message.
        The Pipelines server uses a different signature than Open WebUI Functions:
          - user_message: the latest user message text
          - messages: full conversation history
          - body: raw request body
        Status updates stream as plain text lines prefixed with '…' so the user
        can see progress while the pipeline runs.
        """

        # Apply valve overrides to module-level config
        global OLLAMA_BASE_URL, TEXT_MODEL, VISION_MODEL, USER_ID
        global LLM_PROVIDER, ANTHROPIC_API_KEY, CLAUDE_MODEL
        OLLAMA_BASE_URL  = self.valves.OLLAMA_BASE_URL
        TEXT_MODEL       = self.valves.TEXT_MODEL
        VISION_MODEL     = self.valves.VISION_MODEL
        USER_ID          = self.valves.USER_ID
        LLM_PROVIDER     = self.valves.LLM_PROVIDER
        ANTHROPIC_API_KEY = self.valves.ANTHROPIC_API_KEY
        CLAUDE_MODEL     = self.valves.CLAUDE_MODEL

        def run() -> Generator:

            # --- Clarification phase ---
            confirmed, spec = _is_spec_confirmed(messages)
            log.info("pipe  confirmed=%s  spec_len=%d  user_message=%.200s",
                     confirmed, len(spec), user_message)

            if not confirmed:
                yield _stage_clarify(messages)
                return

            # --- Full pipeline ---
            log.info("══════════════ PIPELINE START ══════════════")
            yield "✓ Got it, searching now…\n\n"

            candidates = _stage_search(spec)
            yield "🔍 Links found, verifying…\n\n"

            verified = _stage_verify(spec, candidates)
            yield "✅ Links verified, checking colors…\n\n"

            color_verified = _stage_color_verify(spec, verified)
            yield "🎨 Colors checked, putting results together…\n\n"

            result = _stage_present(spec, color_verified)

            # Store session in memory after success
            original_request = next(
                (m["content"] for m in messages if m["role"] == "user"),
                spec,
            )
            _store_session(original_request, spec)
            log.info("══════════════ PIPELINE COMPLETE ══════════════")

            yield result

        return run()
