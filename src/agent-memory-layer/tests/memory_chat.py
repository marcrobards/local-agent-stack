#!/usr/bin/env python3
"""
Interactive memory tester for local-agent-stack.

Run via Docker Compose from the project root:

    docker compose run --rm memory-chat

This starts an interactive session inside the memory-chat container
with Qdrant and Ollama available on the Docker network.

Tests the full write→extract→embed→store→search loop manually.
"""

import sys

from memory import mem


DIVIDER = "─" * 60


def print_header():
    print("\n" + DIVIDER)
    print("  Agent Memory — Interactive Tester")
    print(DIVIDER)
    print("  Type a message to store it as a memory.")
    print("  Type 'quit' or Ctrl+C to exit.\n")
    print("  Special commands:")
    print("    /search <query>  — search without storing")
    print("    /clear           — delete all memories for this session")
    print("    /scope           — show current user_id")
    print(DIVIDER + "\n")


def get_user_id() -> str:
    print("Enter a user_id to scope memories (e.g. agent_1, shared).")
    print("Leave blank to use 'agent_1': ", end="")
    uid = input().strip()
    return uid if uid else "agent_1"


def show_search_results(results: list, heading: str = "Top search results"):
    print(f"\n  📡 {heading}:")
    if not results:
        print("     (no results)")
        return
    for r in results:
        score = r.get("score", 0)
        memory = r.get("memory", "")
        bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
        print(f"     [{bar}] {score:.3f}  {memory}")


def show_all_memories(user_id: str):
    all_mem = mem.get_all(user_id=user_id)
    results = all_mem.get("results", [])
    print(f"\n  🗂  All stored memories for '{user_id}' ({len(results)} total):")
    if not results:
        print("     (none yet)")
        return
    for i, r in enumerate(results, 1):
        mtype = r.get("metadata", {}).get("type", "—")
        memory = r.get("memory", "")
        print(f"     {i}. [{mtype}] {memory}")


def store_and_display(message: str, user_id: str):
    print(f"\n  ⏳ Storing memory... (LLM extraction in progress, may take 5–15s)")

    # Capture state before so we can diff what was added
    before = mem.get_all(user_id=user_id)
    before_ids = {r["id"] for r in before.get("results", [])}

    mem.add(message, user_id=user_id, metadata={"type": "episodic"})

    # Diff to find newly extracted facts
    after = mem.get_all(user_id=user_id)
    after_results = after.get("results", [])
    new_facts = [r for r in after_results if r["id"] not in before_ids]

    print(f"\n  ✅ Done. mem0 extracted {len(new_facts)} fact(s) from your input:")
    if new_facts:
        for f in new_facts:
            print(f"     → {f['memory']}")
    else:
        print("     (mem0 may have merged this into an existing memory)")

    # Search using the original message as the query
    hits = mem.search(message, user_id=user_id, limit=5)
    show_search_results(hits.get("results", []))

    # Show full memory store
    show_all_memories(user_id)


def handle_search(query: str, user_id: str):
    print(f"\n  ⏳ Searching for: '{query}'")
    hits = mem.search(query, user_id=user_id, limit=5)
    show_search_results(hits.get("results", []), heading=f"Results for '{query}'")


def handle_clear(user_id: str):
    confirm = input(f"\n  ⚠️  Delete ALL memories for '{user_id}'? (yes/no): ").strip()
    if confirm.lower() == "yes":
        mem.delete_all(user_id=user_id)
        print(f"  🗑  Cleared all memories for '{user_id}'.")
    else:
        print("  Cancelled.")


def main():
    print_header()
    user_id = get_user_id()
    print(f"\n  Scoped to user_id: '{user_id}'\n")

    # Show existing memories on startup
    show_all_memories(user_id)
    print()

    while True:
        try:
            print(DIVIDER)
            user_input = input("  You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n  Exiting. Memories are persisted in Qdrant.\n")
            sys.exit(0)

        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit"):
            print("\n  Exiting. Memories are persisted in Qdrant.\n")
            sys.exit(0)

        elif user_input.startswith("/search "):
            query = user_input[len("/search "):].strip()
            if query:
                handle_search(query, user_id)
            else:
                print("  Usage: /search <your query>")

        elif user_input == "/clear":
            handle_clear(user_id)

        elif user_input == "/scope":
            print(f"\n  Current user_id: '{user_id}'")

        elif user_input.startswith("/"):
            print("  Unknown command. Try /search <query>, /clear, or /scope.")

        else:
            store_and_display(user_input, user_id)

        print()


if __name__ == "__main__":
    main()
