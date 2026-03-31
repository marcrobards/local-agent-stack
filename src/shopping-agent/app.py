"""
Shopping Agent — FastAPI Service (Step 2)

OpenAI-compatible API so Open WebUI can connect via:
  Admin Panel → Settings → Connections → + (add connection)
  URL: http://shopping-agent:8000/v1

Endpoints:
  GET  /v1/models              — model list (Open WebUI discovery)
  POST /v1/chat/completions    — chat completions (streaming + non-streaming)
  GET  /health                 — liveness check
"""

import json
import logging
import time
import uuid

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from stages.clarify import clarify, extract_spec, is_confirmed
from stages.present import present
from stages.refine import is_refinement, merge_refinement
from stages.search import flatten_candidates, search_all
from stages.verify import verify_all

log = logging.getLogger("shopping_agent.app")

app = FastAPI(title="Shopping Agent", version="0.1.0")

MODEL_ID = "shopping-agent"


# ---------------------------------------------------------------------------
# OpenAI-compatible request/response schemas
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = MODEL_ID
    messages: list[ChatMessage]
    stream: bool = False


class Choice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str = MODEL_ID
    choices: list[Choice]
    usage: Usage = Field(default_factory=Usage)


# ---------------------------------------------------------------------------
# GET /v1/models — Open WebUI calls this to discover available models
# ---------------------------------------------------------------------------

@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": MODEL_ID,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "local-agent-stack",
            }
        ],
    }


# ---------------------------------------------------------------------------
# Full pipeline — runs stages 1–4 after spec is confirmed
# ---------------------------------------------------------------------------

async def _run_pipeline(spec_text: str, spec: "ProductSpec | None" = None) -> str:
    """Run the full search → verify → present pipeline.

    If spec is provided (refinement), use it directly.
    Otherwise extract from spec_text (first run).
    """
    if spec is None:
        spec = extract_spec(spec_text)
    log.info("pipeline  item_type=%s  targets=%d", spec.item_type, len(spec.search_targets))

    search_results = await search_all(spec)
    candidates = flatten_candidates(search_results)
    log.info("pipeline  raw_candidates=%d", len(candidates))

    # Dump search results for debugging
    import os, datetime
    debug_dir = os.environ.get("DEBUG_OUTPUT_DIR", "/tmp")
    ts = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    debug_path = os.path.join(debug_dir, f"search_results_{ts}.json")
    with open(debug_path, "w") as f:
        json.dump([c.model_dump() for c in candidates], f, indent=2)
    log.info("pipeline  search results written to %s", debug_path)

    if not candidates:
        return (
            f"I searched {len(spec.search_targets)} sites for a "
            f"{spec.color_description} {spec.item_type} but couldn't find any results. "
            "Would you like me to try different sites or adjust the search?"
        )

    verified = await verify_all(spec, candidates)
    log.info("pipeline  verified=%d", len(verified))

    result = present(spec, verified)
    return result.markdown


# ---------------------------------------------------------------------------
# POST /v1/chat/completions
# ---------------------------------------------------------------------------

@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    # Check conversation state: refinement > confirmation > clarify
    refining, ref_spec_text, feedback = is_refinement(messages)
    if refining:
        log.info("refinement — merging feedback and re-running pipeline")
        spec = merge_refinement(ref_spec_text, feedback)
        reply = await _run_pipeline(ref_spec_text, spec=spec)
    else:
        confirmed, spec_text = is_confirmed(messages)
        if confirmed:
            log.info("spec confirmed — running full pipeline")
            reply = await _run_pipeline(spec_text)
        else:
            reply = clarify(messages)

    if request.stream:
        return StreamingResponse(
            _stream_response(reply),
            media_type="text/event-stream",
        )

    return ChatCompletionResponse(
        choices=[
            Choice(message=ChatMessage(role="assistant", content=reply))
        ],
    )


def _stream_response(text: str):
    """Yield SSE chunks in OpenAI streaming format."""
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    # Single content chunk
    chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": MODEL_ID,
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": text},
                "finish_reason": None,
            }
        ],
    }
    yield f"data: {json.dumps(chunk)}\n\n"

    # Stop chunk
    stop_chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": MODEL_ID,
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": "stop",
            }
        ],
    }
    yield f"data: {json.dumps(stop_chunk)}\n\n"
    yield "data: [DONE]\n\n"


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok"}
