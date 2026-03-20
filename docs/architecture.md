# Architecture

## Overview

`local-agent-stack` is a layered platform. Each layer has a single responsibility and can be understood and tested independently.

```
┌─────────────────────────────────────┐
│           Agents (future)           │
│   orchestration, tools, personas    │
├─────────────────────────────────────┤
│           Memory Layer              │
│     mem0  ←→  Qdrant  ←→  Ollama    │
├─────────────────────────────────────┤
│         LLM Inference               │
│              Ollama                 │
├─────────────────────────────────────┤
│           Infrastructure            │
│         Docker Compose              │
└─────────────────────────────────────┘
```

## Components

### Ollama

Runs all local models. Exposes a REST API on port 11434. Currently serving:

- **qwen2.5:7b** — general purpose LLM, used by agents and by mem0 for memory extraction
- **nomic-embed-text** — embedding model, used by mem0 to convert text to vectors

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

## Memory scoping

Memory is namespaced by `user_id`. Convention:

| Scope | `user_id` | Lifetime |
|---|---|---|
| Agent-private | `"agent_1"`, `"agent_2"` | Permanent |
| Shared across agents | `"shared"` | Permanent |
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

- **Local first** — nothing leaves the machine
- **Loosely coupled** — each layer can be swapped or upgraded independently
- **Explicit over magic** — agents call memory functions explicitly; nothing is injected automatically
- **Incremental** — add capabilities one layer at a time
