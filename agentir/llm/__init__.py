"""LLM Configuration module — provider settings, API clients, agent configs.

Compatible with all major LLM providers via OpenAI-compatible API:
OpenAI, DeepSeek, Anthropic, Ollama, Groq, Together, vLLM, and custom endpoints.
"""

from agentir.llm.config import AgentConfig, LLMConfig, ProviderName
from agentir.llm.client import create_llm_callable, create_llm_callable_async

__all__ = [
    "AgentConfig",
    "LLMConfig",
    "ProviderName",
    "create_llm_callable",
    "create_llm_callable_async",
]
