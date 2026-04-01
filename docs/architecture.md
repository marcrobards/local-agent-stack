# Architecture

## Overview

`local-agent-stack` is a layered platform for running AI agents locally. Each layer has a single responsibility and can be understood and tested independently. Most inference runs on local models via Ollama.

```
┌─────────────────────────────────────┐
│          Chat Interface             │
│            Open WebUI               │
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
- **qwen2.5vl:7b** — vision model, used for image analysis
- **nomic-embed-text** — embedding model, used by mem0 to convert text to vectors

### Open WebUI

Chat interface running on port 3000. Connects to Ollama for direct model access.

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
| User-specific | `"test_user"` | Permanent |
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

## Design principles

- **Local first** — most inference runs on local models via Ollama
- **Loosely coupled** — each layer can be swapped or upgraded independently
- **Explicit over magic** — agents call memory functions explicitly; nothing is injected automatically
- **Incremental** — add capabilities one layer at a time
