from httpx import Timeout
from ollama import Client as OllamaClient
from mem0 import Memory
from .config import MEM0_CONFIG, OLLAMA_BASE_URL, OLLAMA_TIMEOUT

# Shared singleton — import this in all agents
mem = Memory.from_config(MEM0_CONFIG)

# mem0 doesn't expose a timeout for its Ollama LLM client,
# so patch it after init to avoid timeouts on slow hardware.
mem.llm.client = OllamaClient(
    host=OLLAMA_BASE_URL,
    timeout=Timeout(OLLAMA_TIMEOUT, connect=10.0),
)
