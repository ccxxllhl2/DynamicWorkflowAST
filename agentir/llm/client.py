"""LLM Client — creates callable functions from LLMConfig for OpenAI-compatible APIs.

Uses the `openai` Python package to communicate with any OpenAI-compatible endpoint
(OpenAI, DeepSeek, Anthropic, Ollama, Groq, Together, vLLM, etc.).
"""

from __future__ import annotations

from typing import Any, Callable

from agentir.llm.config import LLMConfig


def create_llm_callable(config: LLMConfig) -> Callable[[str], str]:
    """Create an LLM callable function from an LLMConfig.

    Uses the OpenAI Python SDK, which is compatible with all major providers
    (DeepSeek, Anthropic, Ollama, Groq, Together, etc.) via base_url override.

    Args:
        config: An LLMConfig instance with provider, model, api_key, base_url.

    Returns:
        A callable that takes a prompt string and returns the model's response.

    Raises:
        ImportError: If the `openai` package is not installed.
        ValueError: If config is incomplete (missing api_key or base_url).

    Example:
        config = LLMConfig.deepseek(api_key="sk-xxx")
        call_llm = create_llm_callable(config)
        response = call_llm("What is AgentIR?")
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError(
            "The 'openai' package is required to use LLMConfig with create_llm_callable(). "
            "Install it with: pip install openai"
        )

    if not config.api_key:
        # Ollama doesn't need an API key
        if config.provider != "ollama":
            raise ValueError(
                f"No API key configured for provider '{config.provider}'. "
                f"Set it via LLMConfig(api_key=...) or environment variable."
            )

    if not config.base_url:
        raise ValueError(
            f"No base URL configured for provider '{config.provider}'. "
            f"Set base_url in LLMConfig or use a known provider preset."
        )

    client_kwargs: dict[str, Any] = {
        "base_url": config.base_url,
    }
    if config.api_key:
        client_kwargs["api_key"] = config.api_key

    # Ollama sometimes needs a dummy key
    if config.provider == "ollama" and not config.api_key:
        client_kwargs["api_key"] = "ollama"

    client = OpenAI(**client_kwargs)

    extra_body = config.extra_body.copy() if config.extra_body else {}

    def call(prompt: str) -> str:
        response = client.chat.completions.create(
            model=config.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            extra_headers=config.extra_headers or None,
            extra_body=extra_body or None,
        )
        return response.choices[0].message.content or ""

    return call


def create_llm_callable_async(config: LLMConfig) -> Callable[[str], Any]:
    """Create an async LLM callable from an LLMConfig.

    Returns a callable that returns a coroutine (for use with asyncio).
    """
    try:
        from openai import AsyncOpenAI
    except ImportError:
        raise ImportError(
            "The 'openai' package is required. Install it with: pip install openai"
        )

    if not config.api_key and config.provider != "ollama":
        raise ValueError(
            f"No API key configured for provider '{config.provider}'."
        )

    if not config.base_url:
        raise ValueError(f"No base URL configured for provider '{config.provider}'.")

    client_kwargs: dict[str, Any] = {
        "base_url": config.base_url,
    }
    if config.api_key:
        client_kwargs["api_key"] = config.api_key
    if config.provider == "ollama" and not config.api_key:
        client_kwargs["api_key"] = "ollama"

    client = AsyncOpenAI(**client_kwargs)
    extra_body = config.extra_body.copy() if config.extra_body else {}

    async def call(prompt: str) -> str:
        response = await client.chat.completions.create(
            model=config.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            extra_headers=config.extra_headers or None,
            extra_body=extra_body or None,
        )
        return response.choices[0].message.content or ""

    return call
