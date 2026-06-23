"""Server configuration — loads LLM settings from environment.

Users configure their LLM provider via environment variables or a .env file.
On startup, the server builds an LLMConfig from the environment and validates it.

Supported environment variables:
    AGENTIR_LLM_PROVIDER    — "deepseek", "openai", "ollama", "groq", "together", "custom"
    AGENTIR_LLM_MODEL       — Model name override
    AGENTIR_LLM_API_KEY     — API key (generic)
    AGENTIR_LLM_BASE_URL    — Custom base URL
    AGENTIR_LLM_TEMPERATURE — Sampling temperature (default: 0.7)
    AGENTIR_LLM_MAX_TOKENS  — Max output tokens (default: 4096)

Provider-specific env vars (fallback if AGENTIR_LLM_API_KEY is not set):
    DEEPSEEK_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY,
    GROQ_API_KEY, TOGETHER_API_KEY
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentir.llm.config import LLMConfig
from agentir.agents.registry import AgentRegistry as AgentReg


def _find_dotenv() -> str | None:
    """Look for a .env file in the current working directory or project root."""
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent.parent / ".env",
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def _load_dotenv() -> None:
    """Load .env file if python-dotenv is available."""
    env_path = _find_dotenv()
    if env_path is None:
        return
    try:
        from dotenv import load_dotenv  # type: ignore[import-untyped]

        load_dotenv(env_path)
    except ImportError:
        # python-dotenv not installed — silently skip; env vars must be set externally
        pass


@dataclass
class ServerConfig:
    """Server-level configuration loaded from environment."""

    llm: LLMConfig = field(default_factory=LLMConfig.from_env)
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    artifacts_dir: Path = field(default_factory=lambda: Path.cwd() / "artifacts")
    tools_dir: Path = field(default_factory=lambda: Path.cwd() / "tools")
    agents_dir: Path = field(default_factory=lambda: Path.cwd() / "agents")
    title: str = "AgentIR Workflow Generator"
    description: str = (
        "Convert natural language descriptions of agent workflows into "
        "runnable ADK 2.0 Python code."
    )
    version: str = "0.1.0"

    @classmethod
    def from_env(cls, **overrides: Any) -> ServerConfig:
        """Build ServerConfig from environment variables.

        Loads .env file if present, then reads environment variables.
        Accepts keyword overrides for programmatic use.
        """
        _load_dotenv()

        llm_config = LLMConfig.from_env()

        host = os.getenv("AGENTIR_HOST", "0.0.0.0")
        port_str = os.getenv("AGENTIR_PORT", "8000")
        try:
            port = int(port_str)
        except ValueError:
            port = 8000

        debug = os.getenv("AGENTIR_DEBUG", "").lower() in ("1", "true", "yes")

        artifacts_dir_str = os.getenv("AGENTIR_ARTIFACTS_DIR", "")
        artifacts_dir = (
            Path(artifacts_dir_str).resolve()
            if artifacts_dir_str
            else Path.cwd() / "artifacts"
        )

        tools_dir_str = os.getenv("AGENTIR_TOOLS_DIR", "")
        tools_dir = (
            Path(tools_dir_str).resolve()
            if tools_dir_str
            else Path.cwd() / "tools"
        )

        agents_dir_str = os.getenv("AGENTIR_AGENTS_DIR", "")
        agents_dir = (
            Path(agents_dir_str).resolve()
            if agents_dir_str
            else Path.cwd() / "agents"
        )

        # Load pre-defined agents into LLMConfig
        agent_reg = AgentReg.from_directory(agents_dir)
        if agent_reg.agents:
            if not llm_config.default_agent_model:
                llm_config.default_agent_model = llm_config.model
            for name, ag in agent_reg.agents.items():
                llm_config.set_agent(
                    agent_name=name,
                    model=ag.model or llm_config.default_agent_model,
                    instruction=ag.instruction,
                    temperature=ag.temperature,
                )

        return cls(
            llm=llm_config,
            host=str(overrides.get("host", host)),
            port=int(overrides.get("port", port)),
            debug=bool(overrides.get("debug", debug)),
            artifacts_dir=Path(overrides.get("artifacts_dir", artifacts_dir)),
            tools_dir=Path(overrides.get("tools_dir", tools_dir)),
            agents_dir=Path(overrides.get("agents_dir", agents_dir)),
            title=str(overrides.get("title", "AgentIR Workflow Generator")),
        )

    def is_ready(self) -> bool:
        """Check if the LLM configuration is ready to make API calls."""
        return bool(self.llm.base_url and self.llm.model)
