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
from typing import Any, Generator, Iterator, Literal, Optional, Union
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
LLM_PROVIDER     = os.getenv("LLM_PROVIDER", "claude")           # "ollama" or "claude"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL      = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
STAGE_OUTPUT_DIR  = Path(os.getenv("STAGE_OUTPUT_DIR", "/app/local-agent-stack/output"))


# ---------------------------------------------------------------------------
# Stage contracts — typed data flowing between stages
# ---------------------------------------------------------------------------

class ProductSpec(BaseModel):
    product_type: str
    color: str
    size: Optional[str] = None
    material: Optional[str] = None
    brand_preference: Optional[str] = None
    is_clothing: bool = False
    search_query: str
    summary: str


class SearchCandidate(BaseModel):
    url: str
    title: str
    price: Optional[str] = None
    source: str
    image_url: Optional[str] = None
    shop_name: Optional[str] = None
    specs: Optional[str] = None
    match_reason: str


class VerifiedCandidate(BaseModel):
    url: str
    title: str
    price: Optional[str] = None
    source: str
    image_url: Optional[str] = None
    shop_name: Optional[str] = None
    page_title: Optional[str] = None
    page_price: Optional[str] = None
    available: bool = True
    spec_confidence: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"
    confidence_note: str = ""


class ColorVerifiedCandidate(BaseModel):
    url: str
    title: str
    price: Optional[str] = None
    source: str
    image_url: Optional[str] = None
    shop_name: Optional[str] = None
    spec_confidence: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"
    confidence_note: str = ""
    color_result: Literal["PASS", "FAIL", "AMBIGUOUS"] = "AMBIGUOUS"
    color_note: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_prompt(stage: str) -> str:
    return (WORKFLOW_DIR / stage / "PROMPT.md").read_text()


def _new_session_dir() -> Path:
    from datetime import datetime
    session_dir = STAGE_OUTPUT_DIR / datetime.now().strftime("%Y%m%d-%H%M%S")
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def _save_stage(session_dir: Path, filename: str, content) -> None:
    path = session_dir / filename
    if isinstance(content, str):
        text = content
    elif isinstance(content, BaseModel):
        text = content.model_dump_json(indent=2)
    elif isinstance(content, list):
        text = json.dumps([c.model_dump() for c in content], indent=2)
    else:
        text = json.dumps(content, indent=2)
    path.write_text(text, encoding="utf-8")
    log.info("stage_output  saved %s (%d bytes)", path, len(text))


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


def _parse_llm_json(text: str) -> Any:
    """Extract a JSON object or array from an LLM response, stripping markdown fences."""
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = cleaned.find(start_char)
        end = cleaned.rfind(end_char)
        if start != -1 and end > start:
            return json.loads(cleaned[start:end + 1])
    return json.loads(cleaned)


def _extract_spec(confirmed_text: str) -> ProductSpec:
    """Ask the LLM to extract a structured ProductSpec from the confirmed prose."""
    log.info("extract_spec  INPUT  len=%d", len(confirmed_text))
    result = _text_chat([
        {"role": "system", "content": (
            "Extract the product specification from the confirmed summary below. "
            "Return ONLY valid JSON with these exact keys:\n"
            '  "product_type": string — what the product is\n'
            '  "color": string — full color description from the spec\n'
            '  "size": string or null — dimensions or size if mentioned\n'
            '  "material": string or null — material or fabric if mentioned\n'
            '  "brand_preference": string or null — brand preference or null\n'
            '  "is_clothing": boolean — true if this is a clothing/apparel item\n'
            '  "search_query": string — the single best search query to find this product online\n'
            '  "summary": string — the confirmed spec text, copied as-is\n'
            "\nReturn ONLY the JSON object. No other text."
        )},
        {"role": "user", "content": confirmed_text},
    ])
    data = _parse_llm_json(result)
    spec = ProductSpec.model_validate(data)
    log.info("extract_spec  OUTPUT  product_type=%s  query=%s", spec.product_type, spec.search_query)
    return spec


def _parse_color_assessment(text: str) -> tuple[str, str]:
    """Parse PASS/FAIL/AMBIGUOUS and note from vision model output."""
    result = "AMBIGUOUS"
    note = text.strip()

    for line in text.strip().splitlines():
        lower = line.lower().strip()
        if "color result" in lower or lower.startswith("result"):
            if "pass" in lower:
                result = "PASS"
            elif "fail" in lower:
                result = "FAIL"
        elif "color note" in lower or lower.startswith("note"):
            note = line.split(":", 1)[-1].strip() if ":" in line else line.strip()

    return result, note


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


def _stage_search(spec: ProductSpec) -> list[SearchCandidate]:
    """Search all sources. No LLM — tools return structured candidates directly."""
    log.info("━━━ STAGE: search ━━━")
    log.info("search  INPUT  query=%s  is_clothing=%s", spec.search_query, spec.is_clothing)
    try:
        from search import search_all
        sources = ["amazon", "google_shopping", "etsy", "target", "walmart"]
        if spec.is_clothing:
            sources.append("poshmark")
        log.info("search  sources=%s", sources)
        results = asyncio.run(search_all(spec.search_query, sources=sources))
        candidates = []
        for r in results:
            log.info("search  source=%s  candidates=%d  error=%s  elapsed=%.1fs",
                     r.source, len(r.candidates), r.error, r.elapsed)
            for c in r.candidates:
                log.info("search    candidate  url=%s  title=%.80s  price=%s", c.url, c.title, c.price)
                candidates.append(SearchCandidate(
                    url=c.url, title=c.title, price=c.price,
                    source=c.source, image_url=c.image_url,
                    shop_name=c.shop_name, specs=c.specs,
                    match_reason=c.match_reason,
                ))
        log.info("search  OUTPUT  total_candidates=%d", len(candidates))
        return candidates
    except Exception:
        log.error("search  FAILED", exc_info=True)
        return []


def _stage_verify(
    spec: ProductSpec, candidates: list[SearchCandidate]
) -> tuple[list[VerifiedCandidate], list[dict]]:
    """Fetch each page, filter dead links, then ask the LLM for spec confidence.

    Returns (verified_candidates, decisions) where decisions is a list of dicts
    recording the outcome for every input candidate — useful for debugging.
    """
    log.info("━━━ STAGE: verify ━━━")
    log.info("verify  INPUT  candidates=%d", len(candidates))
    from fetch_page import fetch_page

    decisions: list[dict] = []
    live: list[tuple[SearchCandidate, dict]] = []
    for c in candidates[:10]:
        decision: dict = {"url": c.url, "title": c.title, "source": c.source}
        try:
            log.info("verify  fetching  url=%s", c.url)
            page = fetch_page(c.url)
            status = page.get("status", "DEAD")
            log.info("verify  result  url=%s  status=%s  available=%s",
                     c.url, status, page.get("available"))
            decision["fetch_status"] = status
            decision["available"] = page.get("available")
            if status == "DEAD":
                decision["outcome"] = "DROPPED_DEAD_LINK"
                decisions.append(decision)
                continue
            live.append((c, page))
        except Exception as e:
            log.warning("verify  fetch_failed  url=%s", c.url, exc_info=True)
            decision["fetch_status"] = "ERROR"
            decision["fetch_error"] = str(e)
            decision["outcome"] = "DROPPED_FETCH_ERROR"
            decisions.append(decision)

    if not live:
        log.info("verify  OUTPUT  no live candidates")
        return [], decisions

    assessment_input = json.dumps({
        "spec": spec.model_dump(),
        "candidates": [
            {
                "url": c.url,
                "title": c.title,
                "price": c.price,
                "source": c.source,
                "page_title": page.get("title"),
                "page_price": page.get("price"),
                "page_description": page.get("description"),
            }
            for c, page in live
        ],
    }, indent=2)

    system = (
        "You are assessing how well each candidate product matches the spec. "
        "For each candidate, compare its page data against the spec on all "
        "attributes EXCEPT color (color is assessed separately).\n\n"
        "Return ONLY a JSON array. Each item must have:\n"
        '- "url" (string): the candidate URL\n'
        '- "spec_confidence" (string): "HIGH", "MEDIUM", or "LOW"\n'
        '- "confidence_note" (string): one sentence explaining the assessment\n\n'
        "HIGH = all non-color attributes clearly match.\n"
        "MEDIUM = most match but one is uncertain.\n"
        "LOW = plausibly relevant but key details missing or unclear."
    )

    assessments: dict[str, dict] = {}
    try:
        result = _text_chat([
            {"role": "system", "content": system},
            {"role": "user", "content": assessment_input},
        ])
        for a in _parse_llm_json(result):
            assessments[a["url"]] = a
    except Exception:
        log.warning("verify  LLM assessment failed, defaulting to MEDIUM", exc_info=True)

    verified = []
    for c, page in live:
        a = assessments.get(c.url, {})
        spec_confidence = a.get("spec_confidence", "MEDIUM")
        confidence_note = a.get("confidence_note", "Assessment unavailable")
        verified.append(VerifiedCandidate(
            url=c.url,
            title=c.title,
            price=c.price,
            source=c.source,
            image_url=c.image_url,
            shop_name=c.shop_name,
            page_title=page.get("title"),
            page_price=page.get("price"),
            available=page.get("available", False),
            spec_confidence=spec_confidence,
            confidence_note=confidence_note,
        ))
        decisions.append({
            "url": c.url,
            "title": c.title,
            "source": c.source,
            "fetch_status": "LIVE",
            "available": page.get("available"),
            "page_title": page.get("title"),
            "page_price": page.get("price"),
            "spec_confidence": spec_confidence,
            "confidence_note": confidence_note,
            "outcome": "INCLUDED",
        })

    log.info("verify  OUTPUT  verified=%d  decisions=%d", len(verified), len(decisions))
    return verified, decisions


def _stage_color_verify(
    spec: ProductSpec, candidates: list[VerifiedCandidate]
) -> list[ColorVerifiedCandidate]:
    """Fetch images, run vision model, parse results. No summary LLM call."""
    log.info("━━━ STAGE: color_verify ━━━")
    log.info("color_verify  INPUT  candidates=%d", len(candidates))
    import base64
    import requests as req
    from fetch_images import fetch_images

    results: list[ColorVerifiedCandidate] = []
    for c in candidates[:8]:
        try:
            # Prefer the image_url already captured from search results
            if c.image_url:
                image_urls = [c.image_url]
                log.info("color_verify  using_search_image  url=%s  image=%s", c.url, c.image_url)
            else:
                log.info("color_verify  fetching_images  url=%s", c.url)
                image_urls = fetch_images(c.url, max_images=2)
            log.info("color_verify  images_found=%d  url=%s", len(image_urls), c.url)

            if not image_urls:
                color_result, color_note = "AMBIGUOUS", "Could not fetch product images"
            else:
                img_resp = req.get(image_urls[0], timeout=10)
                img_resp.raise_for_status()
                img_b64 = base64.b64encode(img_resp.content).decode("utf-8")

                log.info("color_verify  vision_assess  url=%s  img_size=%d bytes",
                         c.url, len(img_resp.content))
                assessment = _ollama_chat(VISION_MODEL, [{
                    "role": "user",
                    "content": (
                        f"Product URL: {c.url}\n"
                        f"Color spec: {spec.color}\n\n"
                        "Assess this product image against the color spec.\n"
                        "Reply with EXACTLY two lines:\n"
                        "Color result: PASS / FAIL / AMBIGUOUS\n"
                        "Color note: [one or two sentences]"
                    ),
                    "images": [img_b64],
                }])
                log.info("color_verify  assessment  url=%s  raw=%.200s", c.url, assessment)
                color_result, color_note = _parse_color_assessment(assessment)

        except Exception as e:
            log.warning("color_verify  FAILED  url=%s  error=%s", c.url, e, exc_info=True)
            color_result, color_note = "AMBIGUOUS", f"Could not fetch image ({e})"

        log.info("color_verify  url=%s  result=%s", c.url, color_result)
        if color_result == "FAIL":
            continue

        results.append(ColorVerifiedCandidate(
            url=c.url,
            title=c.title,
            price=c.price,
            source=c.source,
            image_url=c.image_url,
            shop_name=c.shop_name,
            spec_confidence=c.spec_confidence,
            confidence_note=c.confidence_note,
            color_result=color_result,
            color_note=color_note,
        ))

    log.info("color_verify  OUTPUT  passed=%d", len(results))
    return results


def _stage_present(spec: ProductSpec, candidates: list[ColorVerifiedCandidate]) -> str:
    """Format structured results into user-facing prose. This is the one stage where the LLM writes freely."""
    log.info("━━━ STAGE: present ━━━")
    log.info("present  INPUT  candidates=%d", len(candidates))
    input_data = json.dumps({
        "spec_summary": spec.summary,
        "candidates": [c.model_dump() for c in candidates],
    }, indent=2)
    result = _text_chat([
        {"role": "system", "content": _load_prompt("03-present")},
        {"role": "user",   "content": input_data},
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
            default=os.getenv("LLM_PROVIDER", "claude"),
            description="LLM provider for text stages: 'ollama' (local) or 'claude' (Anthropic API)"
        )
        ANTHROPIC_API_KEY: str = Field(
            default=os.getenv("ANTHROPIC_API_KEY", ""),
            description="Anthropic API key (required when LLM_PROVIDER is 'claude')"
        )
        CLAUDE_MODEL: str = Field(
            default=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
            description="Claude model name (used when LLM_PROVIDER is 'claude')"
        )
        OLLAMA_BASE_URL: str = Field(
            default=os.getenv("OLLAMA_BASE_URL", "http://ollama:11434"),
            description="Ollama base URL (used for local text model and always for vision)"
        )
        TEXT_MODEL: str = Field(
            default=os.getenv("OLLAMA_LLM_MODEL", "qwen2.5:7b"),
            description="Ollama model for text stages (used when LLM_PROVIDER is 'ollama')"
        )
        VISION_MODEL: str = Field(
            default=os.getenv("OLLAMA_VISION_MODEL", "qwen2.5vl:7b"),
            description="Ollama model for color verification — always runs locally"
        )
        USER_ID: str = Field(
            default=os.getenv("USER_ID", "test_user"),
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
            confirmed, spec_text = _is_spec_confirmed(messages)
            log.info("pipe  confirmed=%s  spec_len=%d  user_message=%.200s",
                     confirmed, len(spec_text), user_message)

            if not confirmed:
                yield _stage_clarify(messages)
                return

            # --- Full pipeline ---
            log.info("══════════════ PIPELINE START ══════════════")
            session_dir = _new_session_dir()

            yield "✓ Got it, extracting spec…\n\n"
            spec = _extract_spec(spec_text)
            _save_stage(session_dir, "00-spec.json", spec)

            yield "🔍 Searching…\n\n"
            candidates = _stage_search(spec)
            _save_stage(session_dir, "01-search.json", candidates)

            yield "✅ Verifying links…\n\n"
            verified, verify_decisions = _stage_verify(spec, candidates)
            _save_stage(session_dir, "02-verify.json", verified)
            _save_stage(session_dir, "02-verify-decisions.json", verify_decisions)

            yield "🎨 Checking colors…\n\n"
            color_verified = _stage_color_verify(spec, verified)
            _save_stage(session_dir, "03-color-verify.json", color_verified)

            yield "📝 Putting results together…\n\n"
            result = _stage_present(spec, color_verified)
            _save_stage(session_dir, "04-present.md", result)

            # Store session in memory after success
            original_request = next(
                (m["content"] for m in messages if m["role"] == "user"),
                spec_text,
            )
            _store_session(original_request, spec_text)
            log.info("══════════════ PIPELINE COMPLETE ══════════════")
            log.info("stage_output  session_dir=%s", session_dir)

            yield result

        return run()
