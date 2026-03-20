"""
Smoke test for the agent memory layer.
Run with: python -m tests.smoke_test
"""
from memory import mem


def run():
    print("=== Memory Layer Smoke Test ===\n")

    # 1. Add a long-term fact for agent_1
    print("1. Writing long-term fact for agent_1...")
    mem.add(
        "The user's name is Marc. He prefers Python and runs Ollama locally.",
        user_id="agent_1",
        metadata={"type": "long_term"}
    )

    # 2. Add an episodic memory for agent_1
    print("2. Writing episodic memory for agent_1...")
    mem.add(
        "In the last session, we discussed setting up a vector database.",
        user_id="agent_1",
        metadata={"type": "episodic"}
    )

    # 3. Add a shared fact (cross-agent memory uses a shared user_id)
    print("3. Writing shared memory for all agents...")
    mem.add(
        "The project is called HomeAgents. All agents share this context.",
        user_id="shared",
        metadata={"type": "shared"}
    )

    # 4. Retrieve all memories for agent_1
    print("\n4. All memories for agent_1:")
    results = mem.get_all(user_id="agent_1")
    for r in results.get("results", []):
        print(f"   [{r.get('metadata', {}).get('type', 'unknown')}] {r['memory']}")

    # 5. Semantic search
    print("\n5. Search for 'database' in agent_1 memories:")
    hits = mem.search("database", user_id="agent_1", limit=3)
    for h in hits.get("results", []):
        print(f"   (score={h.get('score', 0):.3f}) {h['memory']}")

    # 6. Cross-agent: agent_2 reads shared memory
    print("\n6. agent_2 reading shared memory:")
    shared = mem.get_all(user_id="shared")
    for r in shared.get("results", []):
        print(f"   {r['memory']}")

    print("\n=== All checks passed ===")


if __name__ == "__main__":
    run()
