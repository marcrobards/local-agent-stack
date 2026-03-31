"""
Shopping Agent — Runtime configuration.

All settings are read from environment variables with sensible defaults.
"""

import os

LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "claude")
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_LLM_MODEL: str = os.getenv("OLLAMA_LLM_MODEL", "qwen2.5:7b")
OLLAMA_VISION_MODEL: str = os.getenv("OLLAMA_VISION_MODEL", "qwen2.5vl:7b")
USER_ID: str = os.getenv("USER_ID", "user_1")

# Browser Use Cloud
BROWSER_USE_API_KEY: str = os.getenv("BROWSER_USE_API_KEY", "")
SEARCH_LLM: str = os.getenv("SEARCH_LLM", "anthropic")
ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-0")
SEARCH_MAX_RESULTS: int = int(os.getenv("SEARCH_MAX_RESULTS", "10"))
SEARCH_MAX_STEPS: int = int(os.getenv("SEARCH_MAX_STEPS", "15"))
