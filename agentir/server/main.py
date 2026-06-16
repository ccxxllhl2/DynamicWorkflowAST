"""FastAPI application factory for the AgentIR server."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agentir.artifacts.store import WorkflowArtifactStore
from agentir.server.config import ServerConfig
from agentir.server.routes import router as workflow_router
from agentir.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def create_app(config: ServerConfig | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        config: Server configuration. If None, loads from environment.

    Returns:
        A fully configured FastAPI application.
    """
    if config is None:
        config = ServerConfig.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Initialize services on startup."""
        # Validate LLM configuration
        if not config.is_ready():
            import warnings

            warnings.warn(
                "LLM configuration is incomplete. "
                "Set AGENTIR_LLM_PROVIDER, AGENTIR_LLM_API_KEY, "
                "and AGENTIR_LLM_MODEL environment variables, "
                "or create a .env file. "
                "See .env.example for details.",
                RuntimeWarning,
                stacklevel=2,
            )

        # Initialize artifact store
        logger.info(
            "Artifact store initialized at %s",
            config.artifacts_dir.resolve(),
        )

        # Initialize tool registry
        tool_registry = ToolRegistry.from_directory(config.tools_dir)
        app.state.tool_registry = tool_registry
        logger.info(
            "Tool registry: %d tools discovered from %s",
            len(tool_registry.tools),
            config.tools_dir.resolve(),
        )

        yield

    app = FastAPI(
        title=config.title,
        description=config.description,
        version=config.version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Store config and artifact store in app state for dependency injection
    app.state.config = config
    app.state.artifact_store = WorkflowArtifactStore(config.artifacts_dir)

    # CORS — allow all origins for development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    app.include_router(workflow_router)

    # Root redirect to docs
    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return {
            "name": config.title,
            "version": config.version,
            "docs": "/docs",
            "health": "/api/v1/health",
        }

    return app
