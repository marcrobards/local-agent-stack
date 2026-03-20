"""
Smoke test — Stage 01 (Clarify Request)
Loads the stage 01 prompt and sends a sample request to qwen2.5:7b via Ollama.
"""

import os
from pathlib import Path

from ollama import Client

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL = os.getenv("OLLAMA_LLM_MODEL", "qwen2.5:7b")

WORKFLOW_DIR = Path(__file__).resolve().parent.parent


def load_prompt(stage_dir: str) -> str:
    prompt_path = WORKFLOW_DIR / stage_dir / "PROMPT.md"
    return prompt_path.read_text()


def main():
    system_prompt = load_prompt("01-clarify-request")
    user_message = "I'm looking for a dusty rose linen tablecloth, 60 by 84 inches"

    print(f"Model: {MODEL}")
    print(f"Ollama: {OLLAMA_BASE_URL}")
    print(f"Prompt loaded from: {WORKFLOW_DIR / '01-clarify-request' / 'PROMPT.md'}")
    print(f"User message: {user_message}")
    print("-" * 60)

    client = Client(host=OLLAMA_BASE_URL)
    response = client.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )

    print(response["message"]["content"])


if __name__ == "__main__":
    main()
