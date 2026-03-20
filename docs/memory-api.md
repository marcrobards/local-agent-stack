# Memory API Reference

## Importing

```python
from memory import mem
```

All agents use this single shared instance. Do not instantiate `Memory` directly.

---

## mem.add()

Store a memory. mem0 will call the LLM to extract discrete facts from the input before storing.

```python
mem.add(
    data,           # str or list of message dicts
    user_id=None,   # scope (see Memory Scoping below)
    metadata=None   # dict of arbitrary key/value tags
)
```

**Examples:**

```python
# Store a plain fact
mem.add(
    "The project is called local-agent-stack.",
    user_id="shared"
)

# Store a conversation (mem0 extracts facts automatically)
mem.add(
    [
        {"role": "user", "content": "I prefer Python over JavaScript."},
        {"role": "assistant", "content": "Noted, I'll use Python for all code examples."}
    ],
    user_id="agent_1"
)

# Store with metadata tags for filtering later
mem.add(
    "The memory layer uses Qdrant and nomic-embed-text.",
    user_id="shared",
    metadata={"type": "architecture", "component": "memory"}
)
```

**Notes:**
- Slow — involves an LLM call on every write
- Call at end of session or only on meaningful exchanges, not after every message

---

## mem.search()

Search for memories semantically relevant to a query. Fast — vector lookup only, no LLM call.

```python
mem.search(
    query,          # str — natural language query
    user_id=None,   # scope to search within
    limit=5         # max number of results to return
)
```

**Returns:** dict with a `"results"` list. Each result has:
- `"memory"` — the stored text
- `"score"` — similarity score (higher = more relevant)
- `"metadata"` — any metadata stored with the memory

**Example:**

```python
results = mem.search("what tools does this project use?", user_id="shared", limit=3)
for r in results["results"]:
    print(f"({r['score']:.3f}) {r['memory']}")
```

---

## mem.get_all()

Retrieve all memories for a given scope, unfiltered.

```python
mem.get_all(user_id=None)
```

**Returns:** dict with a `"results"` list in the same format as `mem.search()`.

**Example:**

```python
all_memories = mem.get_all(user_id="agent_1")
for r in all_memories["results"]:
    print(r["memory"])
```

---

## mem.delete()

Delete a specific memory by its ID.

```python
mem.delete(memory_id)
```

Get the ID from a search or get_all result: `r["id"]`.

---

## mem.delete_all()

Delete all memories for a given scope.

```python
mem.delete_all(user_id="session_abc123")
```

Useful for clearing session-scoped memory at the end of a session.

---

## Memory Scoping

Use `user_id` to namespace memories. Follow this convention:

| Scope | `user_id` value | Use for |
|---|---|---|
| Agent-private | `"agent_1"`, `"agent_2"` | Facts and history private to one agent |
| Shared | `"shared"` | Project-wide context all agents can read |
| Session | `"session_<timestamp>"` | Ephemeral context; clear with `delete_all()` after session |

**Reading across scopes:**

Agents can search multiple scopes by calling `mem.search()` once per scope and merging results:

```python
from memory import mem

def recall(query: str, agent_id: str) -> list[str]:
    private = mem.search(query, user_id=agent_id, limit=3)
    shared = mem.search(query, user_id="shared", limit=3)
    all_results = private["results"] + shared["results"]
    all_results.sort(key=lambda r: r["score"], reverse=True)
    return [r["memory"] for r in all_results[:5]]
```

---

## Recommended agent pattern

Call `recall()` before each LLM call, and `mem.add()` at the end of each session:

```python
from memory import mem

AGENT_ID = "agent_1"

def run_agent(user_message: str) -> str:
    # 1. Recall relevant context before calling LLM
    memories = mem.search(user_message, user_id=AGENT_ID, limit=5)
    context = "\n".join(r["memory"] for r in memories["results"])

    # 2. Build prompt with memory context injected
    prompt = f"Relevant context:\n{context}\n\nUser: {user_message}"

    # 3. Call your LLM here (Ollama, etc.)
    response = call_llm(prompt)

    # 4. Store the exchange as a memory at end of session
    mem.add(
        [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": response}
        ],
        user_id=AGENT_ID
    )

    return response
```
