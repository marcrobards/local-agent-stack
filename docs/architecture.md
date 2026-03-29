# Architecture

## Overview

`local-agent-stack` is a layered platform for running AI agents locally. Each layer has a single responsibility and can be understood and tested independently. Most inference runs on local models via Ollama — only the product search stage calls cloud APIs (Anthropic + Browser Use Cloud).

```
┌─────────────────────────────────────┐
│          Chat Interface             │
│            Open WebUI               │
├─────────────────────────────────────┤
│       Shopping Agent Pipeline       │
│  clarify → search → verify →       │
│  color-verify → present            │
├─────────────────────────────────────┤
│           Memory Layer              │
│     mem0  ←→  Qdrant  ←→  Ollama   │
├─────────────────────────────────────┤
│         LLM Inference               │
│   Ollama (text, vision, embeddings) │
├─────────────────────────────────────┤
│          Monitoring                 │
│            Beszel                   │
├─────────────────────────────────────┤
│           Infrastructure            │
│         Docker Compose              │
└─────────────────────────────────────┘
```

## Components

### Ollama

Runs all local models. Exposes a REST API on port 11434. Currently serving:

- **qwen2.5:7b** — general purpose LLM, used for pipeline text stages and by mem0 for memory extraction
- **qwen2.5vl:7b** — vision model, used for color verification (stage 02a)
- **nomic-embed-text** — embedding model, used by mem0 to convert text to vectors

### Open WebUI

Chat interface running on port 3000. Connects to:

- **Ollama** for direct model access
- **Shopping Agent Pipeline** via the Pipelines server (internal port 9099, not exposed to host)

Users interact with the shopping agent by selecting "Shopping Agent" from the model dropdown.

### Shopping Agent Pipeline

A 5-stage pipeline (`src/pipelines/shopping_agent_pipeline.py`) running inside an Open WebUI Pipelines server container. Stages:

| Stage | Name | Model / Tool | Runs locally? |
|---|---|---|---|
| 01 | Clarify request | qwen2.5:7b + mem0 memory recall | ✅ Yes |
| 02 | Search | Browser Use Cloud + Anthropic Claude Sonnet | ❌ Cloud APIs |
| 02-verify | Link/spec verification | requests + BeautifulSoup | ✅ Yes |
| 02a | Color verification | qwen2.5vl:7b (vision) | ✅ Yes |
| 03 | Present results | qwen2.5:7b (formats with tappable links) | ✅ Yes |

The pipeline runs as a manifold pipe inside the Pipelines server. The container is built from `Dockerfile.pipeline`, which layers project dependencies and the pipeline script onto the `ghcr.io/open-webui/pipelines:main` base image.

Workflow prompts and tools live in `src/workflows/online-shopping/`, organized by stage:

```
src/workflows/online-shopping/
├── 01-clarify-request/
├── 02-search/
├── 02-verify/
├── 02a-color-verify/
├── 03-present/
└── tests/
```

### Qdrant

Vector database running in Docker. Stores memories as high-dimensional vectors alongside their original text. Exposes:

- REST API on port 6333
- gRPC on port 6334
- Web dashboard at http://localhost:6333/dashboard

Data is persisted to a named Docker volume (`qdrant_data`) so memories survive container restarts.

### mem0

Python library that sits between agent code and Qdrant. Handles:

- **Memory extraction** — calls qwen2.5:7b to distill raw text into discrete facts before storing
- **Embedding** — calls nomic-embed-text to vectorize facts for semantic storage
- **Scoped retrieval** — namespaces memories by `user_id` so agents can have private or shared memory

### Memory layer (`memory/`)

A thin Python wrapper around mem0 that exposes a singleton `mem` object. All agents import from here. This keeps the mem0 config and connection logic in one place.

### Beszel

Lightweight server and Docker container monitoring. Dashboard at http://localhost:8090. Runs two services:

- **beszel** — monitoring hub/dashboard
- **beszel-agent** — host-level agent that reports metrics (runs with `network_mode: host` and Docker socket access)

## Memory scoping

Memory is namespaced by `user_id`. Convention:

| Scope | `user_id` | Lifetime |
|---|---|---|
| Agent-private | `"agent_1"`, `"agent_2"` | Permanent |
| Shared across agents | `"shared"` | Permanent |
| User-specific | `"danielle"` | Permanent |
| Session-scoped | `"session_<timestamp>"` | Cleared after session |

## Data flow

### Write (mem.add)

```
agent code
  → mem.add("text", user_id="agent_1")
    → qwen2.5:7b extracts key facts from text
      → nomic-embed-text vectorizes each fact
        → Qdrant stores vector + original text
```

### Read (mem.search)

```
agent code
  → mem.search("query", user_id="agent_1")
    → nomic-embed-text vectorizes query
      → Qdrant returns closest matching vectors
        → agent receives list of relevant memories
```

Reads do not involve the LLM — they are fast vector lookups only.

### Shopping pipeline flow

```
User message (Open WebUI)
  → Pipelines server → Shopping Agent Pipeline
    → Stage 01: clarify request (qwen2.5:7b + mem0 recall)
    → User confirms spec
    → Stage 02: search (Browser Use Cloud + Anthropic Claude Sonnet)
    → Stage 02-verify: fetch & verify links (requests + BeautifulSoup)
    → Stage 02a: color verification (qwen2.5vl:7b vision model)
    → Stage 03: present results (qwen2.5:7b, tappable links)
    → Store session in mem0
  → Response streamed back to Open WebUI
```

## Design principles

- **Local first** — most inference runs on local models via Ollama; only the search stage uses cloud APIs (Anthropic + Browser Use Cloud)
- **Loosely coupled** — each layer can be swapped or upgraded independently
- **Explicit over magic** — agents call memory functions explicitly; nothing is injected automatically
- **Incremental** — add capabilities one layer at a time
