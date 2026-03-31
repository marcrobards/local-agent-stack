# Shopping Agent

Shopping agent that helps find products online. Clarifies requests, searches
across relevant sites, verifies and filters results (including color accuracy),
and presents curated findings.

See `docs/shopping-agent-spec.md` for the full workflow specification.

## Build Order

Each stage is built and validated independently before wiring them together.

| Step | Status | Description |
|------|--------|-------------|
| 1 | ✅ | Data models (`models.py`) |
| 2 | ✅ | FastAPI skeleton — `/v1/models` + `/v1/chat/completions` stubs |
| 3 | ✅ | Stage 1 — Clarify |
| 4 | ✅ | Stage 2 — Search (single site smoke test) |
| 5 | ✅ | Stage 2 — Search (all sites, parallel) |
| 6 | ✅ | Stage 3 — Verify + Color |
| 7 | ✅ | Stage 4 — Present (full pipeline end-to-end) |
| 8 | ✅ | Refinement loop |

## Deployment

```bash
# Build and start (alongside existing services)
docker compose up -d shopping-agent

# Verify it's running
docker logs shopping-agent
curl http://localhost:8000/health  # only if ports are uncommented
```

Then in Open WebUI: **Admin Panel → Settings → Connections → +**
- URL: `http://shopping-agent:8000/v1`
- API Key: any value
- Save — "shopping-agent" appears in the model dropdown

Requires `ANTHROPIC_API_KEY` and `BROWSER_USE_API_KEY` in your `.env`.

## Development

```bash
cd src/shopping-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests/ -v
```
