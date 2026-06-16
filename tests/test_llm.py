"""Tests for the LLM configuration module."""

import os

import pytest

from agentir.llm.config import (
    AgentConfig,
    LLMConfig,
    ProviderName,
    _PROVIDER_PRESETS,
)
from agentir.llm.client import create_llm_callable


# ---- Test: AgentConfig ----

class TestAgentConfig:
    def test_basic_config(self):
        cfg = AgentConfig(
            agent_name="researcher",
            model="deepseek-chat",
            instruction="You are a researcher.",
            temperature=0.3,
        )
        assert cfg.agent_name == "researcher"
        assert cfg.model == "deepseek-chat"
        assert cfg.instruction == "You are a researcher."
        assert cfg.temperature == 0.3

    def test_defaults(self):
        cfg = AgentConfig(agent_name="worker")
        assert cfg.agent_name == "worker"
        assert cfg.model == ""
        assert cfg.instruction == ""
        assert cfg.tools == []
        assert cfg.temperature is None

    def test_with_tools(self):
        cfg = AgentConfig(
            agent_name="assistant",
            tools=["google_search", "calculator"],
        )
        assert cfg.tools == ["google_search", "calculator"]


# ---- Test: Provider Presets ----

class TestProviderPresets:
    def test_all_providers_have_presets(self):
        providers = ["openai", "deepseek", "anthropic", "ollama", "groq", "together", "custom"]
        for p in providers:
            assert p in _PROVIDER_PRESETS, f"Missing preset for {p}"

    def test_deepseek_preset(self):
        preset = _PROVIDER_PRESETS["deepseek"]
        assert preset["base_url"] == "https://api.deepseek.com"
        assert preset["default_model"] == "deepseek-chat"
        assert preset["env_api_key"] == "DEEPSEEK_API_KEY"

    def test_openai_preset(self):
        preset = _PROVIDER_PRESETS["openai"]
        assert preset["base_url"] == "https://api.openai.com/v1"
        assert preset["default_model"] == "gpt-4o"

    def test_ollama_preset(self):
        preset = _PROVIDER_PRESETS["ollama"]
        assert preset["base_url"] == "http://localhost:11434/v1"
        assert "llama" in preset["default_model"]


# ---- Test: LLMConfig - Factory Methods ----

class TestLLMConfigFactory:
    def test_deepseek_factory(self):
        config = LLMConfig.deepseek(api_key="sk-test", model="deepseek-chat")
        assert config.provider == "deepseek"
        assert config.api_key == "sk-test"
        assert config.model == "deepseek-chat"
        assert config.base_url == "https://api.deepseek.com"

    def test_openai_factory(self):
        config = LLMConfig.openai(api_key="sk-test")
        assert config.provider == "openai"
        assert config.model == "gpt-4o"  # default
        assert config.base_url == "https://api.openai.com/v1"

    def test_ollama_factory(self):
        config = LLMConfig.ollama(model="llama3")
        assert config.provider == "ollama"
        assert config.model == "llama3"
        assert "localhost:11434" in config.base_url

    def test_custom_factory(self):
        config = LLMConfig.custom(
            base_url="https://my-llm.example.com/v1",
            model="my-model",
            api_key="key123",
        )
        assert config.provider == "custom"
        assert config.base_url == "https://my-llm.example.com/v1"
        assert config.model == "my-model"
        assert config.api_key == "key123"


# ---- Test: LLMConfig - Environment Variables ----

class TestLLMConfigEnv:
    def test_resolve_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env-test")
        config = LLMConfig.deepseek()
        assert config.api_key == "sk-env-test"

    def test_agentir_llm_api_key_overrides_provider(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek")
        monkeypatch.setenv("AGENTIR_LLM_API_KEY", "sk-override")
        config = LLMConfig.deepseek()
        assert config.api_key == "sk-override"

    def test_resolve_model_from_default(self):
        config = LLMConfig.deepseek(api_key="sk")
        assert config.model == "deepseek-chat"

    def test_resolve_temperature_from_env(self, monkeypatch):
        monkeypatch.setenv("AGENTIR_LLM_TEMPERATURE", "0.3")
        config = LLMConfig.deepseek(api_key="sk")
        assert config.temperature == 0.3

    def test_resolve_max_tokens_from_env(self, monkeypatch):
        monkeypatch.setenv("AGENTIR_LLM_MAX_TOKENS", "2048")
        config = LLMConfig.deepseek(api_key="sk")
        assert config.max_tokens == 2048

    def test_default_agent_model_resolved(self):
        config = LLMConfig.deepseek(api_key="sk")
        assert config.default_agent_model == "deepseek-chat"


# ---- Test: LLMConfig - from_env ----

class TestLLMConfigFromEnv:
    def test_from_env_basic(self, monkeypatch):
        monkeypatch.setenv("AGENTIR_LLM_PROVIDER", "deepseek")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-from-env")
        monkeypatch.setenv("AGENTIR_LLM_MODEL", "deepseek-reasoner")

        config = LLMConfig.from_env()
        assert config.provider == "deepseek"
        assert config.api_key == "sk-from-env"
        assert config.model == "deepseek-reasoner"

    def test_from_env_with_overrides(self, monkeypatch):
        monkeypatch.setenv("AGENTIR_LLM_PROVIDER", "deepseek")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")

        config = LLMConfig.from_env(model="my-override-model", temperature=0.5)
        assert config.provider == "deepseek"
        assert config.model == "my-override-model"
        assert config.temperature == 0.5

    def test_from_env_unknown_provider_falls_back_to_custom(self, monkeypatch):
        monkeypatch.setenv("AGENTIR_LLM_PROVIDER", "unknown-provider")
        config = LLMConfig.from_env()
        assert config.provider == "custom"


# ---- Test: LLMConfig - Agent Config Helpers ----

class TestLLMConfigAgentHelpers:
    def test_set_agent(self):
        config = LLMConfig.deepseek(api_key="sk")
        config.set_agent("researcher", instruction="You research.")
        cfg = config.get_agent_config("researcher")
        assert cfg is not None
        assert cfg.agent_name == "researcher"
        assert cfg.instruction == "You research."
        assert cfg.model == "deepseek-chat"  # inherited from default_agent_model

    def test_set_agent_chaining(self):
        config = LLMConfig.deepseek(api_key="sk") \
            .set_agent("a", model="gpt-4o", instruction="A") \
            .set_agent("b", model="claude", instruction="B")
        assert config.get_agent_config("a").model == "gpt-4o"
        assert config.get_agent_config("b").model == "claude"

    def test_set_agents_batch(self):
        config = LLMConfig.deepseek(api_key="sk")
        config.set_agents_batch(
            ["researcher", "writer", "reviewer"],
            model="deepseek-chat",
            instruction_template="You are the {agent_name} specialist.",
        )
        for name in ["researcher", "writer", "reviewer"]:
            cfg = config.get_agent_config(name)
            assert cfg is not None
            assert cfg.model == "deepseek-chat"
            assert name in cfg.instruction
            assert "specialist" in cfg.instruction

    def test_get_agent_config_missing(self):
        config = LLMConfig.deepseek(api_key="sk")
        assert config.get_agent_config("nonexistent") is None


# ---- Test: LLMConfig - Custom Fields ----

class TestLLMConfigCustom:
    def test_extra_headers(self):
        config = LLMConfig.deepseek(api_key="sk", extra_headers={"X-Custom": "value"})
        assert config.extra_headers["X-Custom"] == "value"

    def test_extra_body(self):
        config = LLMConfig.deepseek(api_key="sk", extra_body={"top_k": 50})
        assert config.extra_body["top_k"] == 50

    def test_temperature_default(self):
        config = LLMConfig(provider="openai", api_key="sk", model="gpt-4o")
        assert config.temperature == 0.7

    def test_max_tokens_default(self):
        config = LLMConfig(provider="openai", api_key="sk", model="gpt-4o")
        assert config.max_tokens == 4096


# ---- Test: create_llm_callable ----

class TestCreateLLMCallable:
    def test_missing_openai_package(self, monkeypatch):
        """When openai is not installed, should raise ImportError."""
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "openai":
                raise ImportError("No module named 'openai'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        config = LLMConfig.deepseek(api_key="sk-test")
        with pytest.raises(ImportError, match="openai"):
            create_llm_callable(config)

    def test_missing_api_key_raises(self):
        """Should raise ValueError when no API key is available."""
        config = LLMConfig(provider="deepseek", base_url="https://api.deepseek.com", model="deepseek-chat")
        with pytest.raises(ValueError, match="No API key"):
            create_llm_callable(config)

    def test_missing_base_url_raises(self):
        config = LLMConfig(provider="custom", api_key="sk", model="test")
        with pytest.raises(ValueError, match="No base URL"):
            create_llm_callable(config)

    def test_ollama_no_api_key_ok(self, monkeypatch):
        """Ollama should work without an API key."""
        monkeypatch.setattr("openai.OpenAI", _FakeOpenAI)
        config = LLMConfig.ollama(model="llama3")
        callable_fn = create_llm_callable(config)
        result = callable_fn("Hello")
        assert result == "fake response"

    def test_creates_callable_with_openai_client(self, monkeypatch):
        """Verify the callable works end-to-end with a mock."""
        monkeypatch.setattr("openai.OpenAI", _FakeOpenAI)
        config = LLMConfig.deepseek(api_key="sk-test", model="deepseek-chat")
        callable_fn = create_llm_callable(config)
        result = callable_fn("Hello")
        assert result == "fake response"


# ---- Fake OpenAI client for testing ----

class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeCompletion:
    def __init__(self, content="fake response"):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def create(self, **kwargs):
        return _FakeCompletion()


class _FakeOpenAI:
    def __init__(self, **kwargs):
        self.chat = _FakeChat()


class _FakeChat:
    def __init__(self):
        self.completions = _FakeCompletions()
