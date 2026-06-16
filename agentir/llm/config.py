"""LLM Configuration — provider presets, model settings, environment variable support.

Compatible with all major LLM providers via OpenAI-compatible API:
OpenAI, DeepSeek, Anthropic, Ollama, Groq, Together, vLLM, and more.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Literal


# ---- Provider Type ----

# Known provider identifiers (used as presets; open-ended via custom_base_url)
ProviderName = Literal[
    "openai",
    "deepseek",
    "anthropic",
    "ollama",
    "groq",
    "together",
    "custom",
]


# ---- Provider Presets ----

_PROVIDER_PRESETS: dict[ProviderName, dict[str, str]] = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "env_api_key": "OPENAI_API_KEY",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
        "env_api_key": "DEEPSEEK_API_KEY",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "default_model": "claude-sonnet-4-20250514",
        "env_api_key": "ANTHROPIC_API_KEY",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "default_model": "llama3",
        "env_api_key": "OLLAMA_API_KEY",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.1-70b-versatile",
        "env_api_key": "GROQ_API_KEY",
    },
    "together": {
        "base_url": "https://api.together.xyz/v1",
        "default_model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "env_api_key": "TOGETHER_API_KEY",
    },
    "custom": {
        "base_url": "",
        "default_model": "",
        "env_api_key": "",
    },
}


# ---- Agent Config (for Compiler output) ----

@dataclass
class AgentConfig:
    """Per-agent configuration injected into compiled workflow code.

    Controls model, instruction, and tools for each agent in the output.

    Example:
        AgentConfig(
            agent_name="researcher",
            model="deepseek-chat",
            instruction="You are a research specialist.",
            temperature=0.3,
        )
    """

    agent_name: str
    model: str = ""
    instruction: str = ""
    tools: list[str] = field(default_factory=list)
    temperature: float | None = None

    # Allow passing extra kwargs for future extensions
    extra: dict[str, Any] = field(default_factory=dict)


# ---- LLM Config ----

@dataclass
class LLMConfig:
    """Configuration for an LLM provider.

    Encapsulates all settings needed to call an LLM API.
    Works with any OpenAI-compatible endpoint (OpenAI, DeepSeek, Ollama, etc.).

    Quick start with DeepSeek:
        # Option A: Explicit
        config = LLMConfig(
            provider="deepseek",
            api_key="sk-xxx",
            model="deepseek-chat",
        )

        # Option B: From environment
        # export DEEPSEEK_API_KEY=sk-xxx
        config = LLMConfig(provider="deepseek")

        # Option C: Preset factory
        config = LLMConfig.deepseek(api_key="sk-xxx")
    """

    provider: ProviderName = "openai"
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    extra_headers: dict[str, str] = field(default_factory=dict)
    extra_body: dict[str, Any] = field(default_factory=dict)

    # Per-agent compiler configuration
    agent_configs: dict[str, AgentConfig] = field(default_factory=dict)
    default_agent_model: str = ""
    default_agent_instruction: str = ""

    def __post_init__(self) -> None:
        """Resolve defaults from provider preset and environment."""
        preset = _PROVIDER_PRESETS.get(self.provider, {})

        # Resolve model
        if not self.model:
            self.model = preset.get("default_model", "")

        # Resolve base_url
        if not self.base_url:
            env_url = os.getenv("AGENTIR_LLM_BASE_URL", "")
            self.base_url = env_url or preset.get("base_url", "")

        # Resolve api_key
        if not self.api_key:
            # 1. AGENTIR_LLM_API_KEY (explicit override)
            env_key = os.getenv("AGENTIR_LLM_API_KEY", "")
            if env_key:
                self.api_key = env_key
            else:
                # 2. Provider-specific env var (e.g., DEEPSEEK_API_KEY)
                env_var = preset.get("env_api_key", "")
                if env_var:
                    self.api_key = os.getenv(env_var, "")

        # Resolve temperature / max_tokens from env
        env_temp = os.getenv("AGENTIR_LLM_TEMPERATURE", "")
        if env_temp:
            try:
                self.temperature = float(env_temp)
            except ValueError:
                pass

        env_max_tokens = os.getenv("AGENTIR_LLM_MAX_TOKENS", "")
        if env_max_tokens:
            try:
                self.max_tokens = int(env_max_tokens)
            except ValueError:
                pass

        # Resolve default agent model/instruction
        if not self.default_agent_model:
            self.default_agent_model = self.model

    # ---- Factory Methods ----

    @classmethod
    def openai(
        cls,
        api_key: str = "",
        model: str = "",
        **kwargs: Any,
    ) -> LLMConfig:
        """Create an OpenAI config."""
        return cls(provider="openai", api_key=api_key, model=model, **kwargs)

    @classmethod
    def deepseek(
        cls,
        api_key: str = "",
        model: str = "",
        **kwargs: Any,
    ) -> LLMConfig:
        """Create a DeepSeek config.

        DeepSeek uses an OpenAI-compatible API at https://api.deepseek.com.
        Set environment variable DEEPSEEK_API_KEY or pass api_key explicitly.
        """
        return cls(provider="deepseek", api_key=api_key, model=model, **kwargs)

    @classmethod
    def anthropic(
        cls,
        api_key: str = "",
        model: str = "",
        **kwargs: Any,
    ) -> LLMConfig:
        """Create an Anthropic config (via OpenAI-compatible endpoint)."""
        return cls(provider="anthropic", api_key=api_key, model=model, **kwargs)

    @classmethod
    def ollama(
        cls,
        model: str = "",
        base_url: str = "",
        **kwargs: Any,
    ) -> LLMConfig:
        """Create an Ollama config for local models.

        Ollama provides an OpenAI-compatible endpoint at http://localhost:11434/v1.
        No API key needed for local use.
        """
        return cls(
            provider="ollama",
            model=model,
            base_url=base_url,
            temperature=0.7,
            **kwargs,
        )

    @classmethod
    def groq(
        cls,
        api_key: str = "",
        model: str = "",
        **kwargs: Any,
    ) -> LLMConfig:
        """Create a Groq config."""
        return cls(provider="groq", api_key=api_key, model=model, **kwargs)

    @classmethod
    def together(
        cls,
        api_key: str = "",
        model: str = "",
        **kwargs: Any,
    ) -> LLMConfig:
        """Create a Together AI config."""
        return cls(provider="together", api_key=api_key, model=model, **kwargs)

    @classmethod
    def custom(
        cls,
        base_url: str,
        model: str = "",
        api_key: str = "",
        **kwargs: Any,
    ) -> LLMConfig:
        """Create a custom provider config for any OpenAI-compatible endpoint.

        Use this for self-hosted vLLM, local LM Studio, or any custom endpoint.
        """
        return cls(
            provider="custom",
            base_url=base_url,
            model=model,
            api_key=api_key,
            **kwargs,
        )

    @classmethod
    def from_env(cls, **overrides: Any) -> LLMConfig:
        """Create a config entirely from environment variables.

        Environment variables:
            AGENTIR_LLM_PROVIDER   — provider name (default: "openai")
            AGENTIR_LLM_MODEL      — model name
            AGENTIR_LLM_API_KEY    — API key
            AGENTIR_LLM_BASE_URL   — base URL
            AGENTIR_LLM_TEMPERATURE — temperature
            AGENTIR_LLM_MAX_TOKENS  — max tokens

        Provider-specific API keys also work:
            OPENAI_API_KEY, DEEPSEEK_API_KEY, etc.

        Override any setting via keyword arguments.
        """
        provider = os.getenv("AGENTIR_LLM_PROVIDER", "openai")
        # Validate provider
        valid_providers = set(_PROVIDER_PRESETS.keys())
        if provider not in valid_providers:
            provider = "custom"

        config = cls(
            provider=provider,  # type: ignore[arg-type]
            model=os.getenv("AGENTIR_LLM_MODEL", ""),
        )

        # Apply overrides
        for key, value in overrides.items():
            if hasattr(config, key):
                setattr(config, key, value)

        return config

    # ---- Agent Config Helpers ----

    def set_agent(
        self,
        agent_name: str,
        model: str = "",
        instruction: str = "",
        tools: list[str] | None = None,
        temperature: float | None = None,
    ) -> LLMConfig:
        """Configure a specific agent for the compiler output.

        Returns self for chaining.
        """
        self.agent_configs[agent_name] = AgentConfig(
            agent_name=agent_name,
            model=model or self.default_agent_model,
            instruction=instruction or self.default_agent_instruction,
            tools=tools or [],
            temperature=temperature,
        )
        return self

    def set_agents_batch(
        self,
        agent_names: list[str],
        model: str = "",
        instruction_template: str = "",
    ) -> LLMConfig:
        """Configure multiple agents at once.

        Args:
            agent_names: List of agent names to configure.
            model: Model for all agents (default: self.default_agent_model).
            instruction_template: Template with {agent_name} placeholder.
                E.g., "You are the {agent_name} agent."
        """
        for name in agent_names:
            instruction = (
                instruction_template.format(agent_name=name)
                if instruction_template
                else ""
            )
            self.set_agent(name, model=model, instruction=instruction)
        return self

    def get_agent_config(self, agent_name: str) -> AgentConfig | None:
        """Get the config for a specific agent, or None."""
        return self.agent_configs.get(agent_name)
