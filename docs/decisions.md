# Decisions Log

A record of significant architectural choices, what alternatives were considered, and why we chose what we chose.

---

## 2026-03-20 — Memory backend: mem0 + Qdrant

**Decision:** Use mem0 as the memory abstraction library with Qdrant as the vector store backend.

**Alternatives considered:**

- **SQLite (key-value)** — simple, zero dependencies, but no semantic search. Finding relevant memories requires exact keyword matching, which breaks down quickly with natural language.
- **OpenClaw** — a full AI assistant platform with mem0 memory built in. Rejected because it's a complete platform replacement, not a layer. We want memory as infrastructure we control, not bundled into an opinionated product.
- **Raw Qdrant without mem0** — possible, but mem0 adds valuable intelligence: it extracts discrete facts from raw text using the LLM before storing, rather than just dumping whatever text you give it.

**Reasons for mem0 + Qdrant:**

- mem0 handles all four memory types needed: short-term session context, long-term persistent facts, shared cross-agent memory, and episodic conversation history
- Qdrant runs cleanly in Docker with a named volume for persistence
- The combination is well-documented and actively maintained
- Fully local — no external API keys required
- mem0's `user_id` scoping maps naturally onto agent team patterns

---

## 2026-03-20 — Embedding model: nomic-embed-text

**Decision:** Use `nomic-embed-text:latest` via Ollama for embeddings.

**Alternatives considered:**

- **mxbai-embed-large** — 1024 dimensions, slightly higher quality embeddings, but known bugs with mem0's `.add()` (returns empty results silently as of late 2025)
- **snowflake-arctic-embed** — also 768 dimensions, less tested with mem0
- **Same model as LLM (qwen2.5:7b)** — Ollama supports using LLMs for embeddings but they are not optimized for it and produce lower quality vectors

**Reasons for nomic-embed-text:**

- Best-tested embedding model with mem0 + Qdrant
- 768 dimensions — well supported, no known compatibility issues
- Lightweight and fast — embedding calls are not the bottleneck

---

## 2026-03-20 — LLM for memory extraction: qwen2.5:7b

**Decision:** Use qwen2.5:7b (already running for agent inference) as the LLM mem0 calls internally for memory extraction.

**Notes:**

- Write performance is slow (5–15 seconds per `mem.add()` call) because qwen2.5:7b is a 7B model
- `llama3.2:3b` is a viable alternative for extraction only — smaller, faster, equally capable for mem0's structured extraction task
- This can be changed anytime via `OLLAMA_LLM_MODEL` in `.env` without affecting the rest of the stack

---

## 2026-03-20 — Python library pattern (not a service)

**Decision:** Run mem0 as a Python library imported by agent code, not as a standalone HTTP service.

**Alternatives considered:**

- **mem0 as a service** — mem0 can be run as a REST API server. This would let non-Python agents use memory via HTTP.

**Reasons for library pattern:**

- Simpler for now — no extra process to manage
- All current agent code is Python
- Easy to migrate to service later if non-Python agents are added

---

## 2026-03-20 — Qdrant version: latest

**Decision:** Use `qdrant/qdrant:latest` in docker-compose.yml rather than pinning a specific version.

**Context:** Initially pinned to `v1.13.0` based on a tutorial. The `qdrant-client` Python library installed by `pip install mem0ai` was at version 1.17.1, which is incompatible with server 1.13.0 (max supported gap is one minor version). This caused silent hangs on `mem.add()`.

**Decision:** Track latest server rather than pin client down, since we want a current Qdrant going forward. If a future client/server mismatch occurs, upgrade the server image.
