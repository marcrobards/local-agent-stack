"""Validate OpenAI-compatible API endpoints — Step 2 verification."""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _mock_llm():
    """Mock LLM calls so app tests don't need an API key."""
    with patch("stages.clarify.llm") as mock:
        mock.chat.return_value = "What color are you looking for?"
        yield mock


# ---------------------------------------------------------------------------
# GET /v1/models
# ---------------------------------------------------------------------------

class TestListModels:
    def test_returns_model_list(self, client):
        resp = client.get("/v1/models")
        assert resp.status_code == 200
        body = resp.json()
        assert body["object"] == "list"
        assert len(body["data"]) == 1
        assert body["data"][0]["id"] == "shopping-agent"
        assert body["data"][0]["owned_by"] == "local-agent-stack"


# ---------------------------------------------------------------------------
# POST /v1/chat/completions — non-streaming
# ---------------------------------------------------------------------------

class TestChatCompletions:
    def test_clarify_response(self, client):
        resp = client.post("/v1/chat/completions", json={
            "model": "shopping-agent",
            "messages": [
                {"role": "user", "content": "I need a dusty rose tablecloth"},
            ],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["object"] == "chat.completion"
        assert body["model"] == "shopping-agent"
        assert len(body["choices"]) == 1
        assert body["choices"][0]["finish_reason"] == "stop"
        assert body["choices"][0]["message"]["role"] == "assistant"

    def test_multi_turn_clarify(self, client):
        resp = client.post("/v1/chat/completions", json={
            "model": "shopping-agent",
            "messages": [
                {"role": "user", "content": "first message"},
                {"role": "assistant", "content": "hi"},
                {"role": "user", "content": "second message"},
            ],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["choices"][0]["message"]["content"] == "What color are you looking for?"

    def test_confirmed_spec_runs_pipeline(self, client, _mock_llm):
        _mock_llm.chat.return_value = json.dumps({
            "item_type": "tablecloth",
            "color_description": "dusty rose",
            "dimensions": "60x84",
            "material": "linen",
            "constraints": [],
            "budget_max": None,
            "search_targets": [{"site": "etsy.com", "rationale": "Linens"}],
            "confirmed": True,
        })
        _mock_llm.parse_json.side_effect = json.loads

        from models import RawCandidate, SearchTaskResult, VerifiedCandidate

        mock_search_result = SearchTaskResult(
            site="etsy.com",
            candidates=[RawCandidate(
                url="https://etsy.com/listing/1",
                title="Dusty Rose Tablecloth",
                price="$45.00",
                vendor="LinenCraft",
                image_urls=["https://cdn.etsy.com/img.jpg"],
                source_site="etsy.com",
            )],
        )
        mock_verified = VerifiedCandidate(
            raw=mock_search_result.candidates[0],
            spec_confidence="HIGH",
            color_result="PASS",
            color_description="Warm muted pink",
            summary="Great match.",
        )

        with patch("app.search_all", return_value=[mock_search_result]), \
             patch("app.verify_all", return_value=[mock_verified]):
            resp = client.post("/v1/chat/completions", json={
                "model": "shopping-agent",
                "messages": [
                    {"role": "user", "content": "tablecloth"},
                    {"role": "assistant", "content": "Dusty rose linen tablecloth, 60x84. Ready?"},
                    {"role": "user", "content": "yes"},
                ],
            })

        assert resp.status_code == 200
        body = resp.json()
        content = body["choices"][0]["message"]["content"]
        assert "Dusty Rose Tablecloth" in content
        assert "LinenCraft" in content

    def test_response_has_id(self, client):
        resp = client.post("/v1/chat/completions", json={
            "model": "shopping-agent",
            "messages": [{"role": "user", "content": "test"}],
        })
        body = resp.json()
        assert body["id"].startswith("chatcmpl-")

    def test_usage_field_present(self, client):
        resp = client.post("/v1/chat/completions", json={
            "model": "shopping-agent",
            "messages": [{"role": "user", "content": "test"}],
        })
        body = resp.json()
        assert "usage" in body
        assert body["usage"]["total_tokens"] == 0


# ---------------------------------------------------------------------------
# POST /v1/chat/completions — streaming
# ---------------------------------------------------------------------------

class TestStreaming:
    def test_stream_clarify_response(self, client):
        resp = client.post("/v1/chat/completions", json={
            "model": "shopping-agent",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": True,
        })
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        lines = resp.text.strip().split("\n")
        data_lines = [l for l in lines if l.startswith("data: ")]
        assert len(data_lines) == 3  # content chunk + stop chunk + [DONE]

        # First chunk has content from clarify mock
        first = json.loads(data_lines[0].removeprefix("data: "))
        assert first["object"] == "chat.completion.chunk"
        assert first["choices"][0]["delta"]["content"] == "What color are you looking for?"
        assert first["choices"][0]["finish_reason"] is None

        # Second chunk is stop
        second = json.loads(data_lines[1].removeprefix("data: "))
        assert second["choices"][0]["finish_reason"] == "stop"

        # Last line is [DONE]
        assert data_lines[2] == "data: [DONE]"


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
