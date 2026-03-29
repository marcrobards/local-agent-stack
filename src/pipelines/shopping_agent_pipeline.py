"""
title: Shopping Agent
author: local-agent-stack
version: 0.1.0
description: Helps the user find specific products online. Clarifies the
  request, searches multiple sources, verifies links, checks colors with a
  vision model, and presents tappable results.
requirements: ollama, mem0ai, qdrant-client, python-dotenv, requests, beautifulsoup4
"""

import asyncio
import sys
import os
import re
from pathlib import Path
from typing import Generator, Iterator, Union
from pydantic import BaseModel, Field

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

# ---------------------------------------------------------------------------
# Runtime config — read from environment, with sane defaults for Docker
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL  = os.getenv("OLLAMA_BASE_URL",  "http://ollama:11434")
TEXT_MODEL       = os.getenv("OLLAMA_LLM_MODEL",    "qwen2.5:7b")
VISION_MODEL     = os.getenv("OLLAMA_VISION_MODEL", "qwen2.5vl:7b")
USER_ID = os.getenv("USER_ID",    "user_1")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_prompt(stage: str) -> str:
    return (WORKFLOW_DIR / stage / "PROMPT.md").read_text()


def _ollama_chat(model: str, messages: list) -> str:
    client = OllamaClient(host=OLLAMA_BASE_URL)
    response = client.chat(model=model, messages=messages)
    return response["message"]["content"]


def _recall_danielle(query: str) -> str:
    """Pull relevant memories for the user. Fails silently if mem0 is down."""
    try:
        from memory import mem
        hits = mem.search(query, user_id=USER_ID, limit=5)
        results = hits.get("results", [])
        if not results:
            return ""
        lines = "\n".join(f"- {r['memory']}" for r in results)
        return f"Known preferences for the user:\n{lines}"
    except Exception:
        return ""


def _store_session(original_request: str, confirmed_spec: str) -> None:
    try:
        from memory import mem
        mem.add(
            [
                {"role": "user",      "content": original_request},
                {"role": "assistant", "content": confirmed_spec},
            ],
            user_id=USER_ID,
            metadata={"type": "shopping_session", "workflow": "online-shopping"},
        )
    except Exception:
        pass


def _extract_urls(text: str) -> list[str]:
    return re.findall(r"https?://[^\s\n\"'>]+", text)


# ---------------------------------------------------------------------------
# Stage runners
# ---------------------------------------------------------------------------

def _stage_clarify(conversation: list) -> str:
    system = _load_prompt("01-clarify-request")
    memory_context = _recall_danielle(conversation[-1]["content"])

    messages = [{"role": "system", "content": system}]
    if memory_context:
        # Inject as a second system message so it doesn't confuse turn order
        messages.append({"role": "system", "content": memory_context})
    messages.extend(conversation)

    return _ollama_chat(TEXT_MODEL, messages)


def _stage_search(spec: str) -> str:
    system = _load_prompt("02-search")
    tool_results = _run_search_tools(spec)

    user_content = spec
    if tool_results:
        user_content += f"\n\n--- Live search results ---\n{tool_results}"

    return _ollama_chat(TEXT_MODEL, [
        {"role": "system",  "content": system},
        {"role": "user",    "content": user_content},
    ])


def _run_search_tools(spec: str) -> str:
    try:
        from search import search_all, format_results
        query = spec.split("\n")[0][:120]
        sources = ["amazon", "google_shopping", "etsy", "target", "walmart"]
        results = asyncio.run(search_all(query, sources=sources))
        return format_results(results)
    except Exception:
        return ""


def _stage_verify(spec: str, candidates: str) -> str:
    system = _load_prompt("02-verify")
    page_data = _run_verify_tools(candidates)

    user_content = f"Confirmed product spec:\n{spec}\n\nCandidates:\n{candidates}"
    if page_data:
        user_content += f"\n\n--- Fetched page data ---\n{page_data}"

    return _ollama_chat(TEXT_MODEL, [
        {"role": "system", "content": system},
        {"role": "user",   "content": user_content},
    ])


def _run_verify_tools(candidates: str) -> str:
    try:
        from fetch_page import fetch_page
        rows = []
        for url in _extract_urls(candidates)[:10]:
            try:
                d = fetch_page(url)
                rows.append(
                    f"URL: {url}\n"
                    f"Status: {d.get('status','UNKNOWN')}\n"
                    f"Title: {d.get('title','')}\n"
                    f"Price: {d.get('price','')}\n"
                    f"Available: {d.get('available', False)}\n"
                )
            except Exception:
                rows.append(f"URL: {url}\nStatus: DEAD\n")
        return "\n".join(rows)
    except Exception:
        return ""


def _stage_color_verify(spec: str, verified: str) -> str:
    system = _load_prompt("02a-color-verify")
    vision_results = _run_color_verify_tools(spec, verified)

    user_content = f"Color spec:\n{spec}\n\nVerified candidates:\n{verified}"
    if vision_results:
        user_content += f"\n\n--- Vision color assessments ---\n{vision_results}"

    return _ollama_chat(TEXT_MODEL, [
        {"role": "system", "content": system},
        {"role": "user",   "content": user_content},
    ])


def _run_color_verify_tools(spec: str, candidates: str) -> str:
    try:
        import base64
        import requests as req
        from fetch_images import fetch_images

        rows = []
        for url in _extract_urls(candidates)[:8]:
            try:
                image_urls = fetch_images(url, max_images=2)
                if not image_urls:
                    continue
                img_resp = req.get(image_urls[0], timeout=10)
                img_resp.raise_for_status()
                img_b64 = base64.b64encode(img_resp.content).decode("utf-8")

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
                rows.append(f"URL: {url}\n{assessment}\n")
            except Exception as e:
                rows.append(
                    f"URL: {url}\nColor result: AMBIGUOUS\n"
                    f"Color note: Could not fetch image ({e})\n"
                )
        return "\n".join(rows)
    except Exception:
        return ""


def _stage_present(spec: str, color_verified: str) -> str:
    return _ollama_chat(TEXT_MODEL, [
        {"role": "system", "content": _load_prompt("03-present")},
        {"role": "user",   "content": (
            f"Confirmed product spec:\n{spec}\n\n"
            f"Color-verified candidates:\n{color_verified}"
        )},
    ])


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
        OLLAMA_BASE_URL: str = Field(
            default="http://ollama:11434",
            description="Ollama base URL (use Docker service name inside Compose network)"
        )
        TEXT_MODEL: str = Field(
            default="qwen2.5:7b",
            description="Model for text stages"
        )
        VISION_MODEL: str = Field(
            default="qwen2.5vl:7b",
            description="Model for color verification (stage 02a)"
        )
        USER_ID: str = Field(
            default="danielle",
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
        OLLAMA_BASE_URL  = self.valves.OLLAMA_BASE_URL
        TEXT_MODEL       = self.valves.TEXT_MODEL
        VISION_MODEL     = self.valves.VISION_MODEL
        USER_ID = self.valves.USER_ID

        def run() -> Generator:

            # --- Clarification phase ---
            confirmed, spec = _is_spec_confirmed(messages)

            if not confirmed:
                yield _stage_clarify(messages)
                return

            # --- Full pipeline ---
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

            yield result

        return run()
