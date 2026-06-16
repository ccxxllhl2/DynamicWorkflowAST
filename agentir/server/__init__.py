"""AgentIR Server — FastAPI microservice for NL→Workflow generation."""

from agentir.server.main import create_app
from agentir.server.config import ServerConfig

__all__ = ["create_app", "ServerConfig"]
