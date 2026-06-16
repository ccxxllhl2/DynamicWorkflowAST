"""CLI entry point for the AgentIR server.

Usage:
    agentir-server              # Start with default settings
    agentir-server --port 9000  # Custom port
    agentir-server --reload     # Hot-reload during development
    agentir tools scan          # Scan tools/ directory and show discovered tools
"""

from __future__ import annotations

import argparse
import sys


def _cmd_tools_scan(args) -> None:
    """Scan the tools directory and print discovered tools."""
    from pathlib import Path

    from agentir.tools.registry import ToolRegistry

    tools_dir = Path(args.dir) if args.dir else Path.cwd() / "tools"
    tools_dir = tools_dir.resolve()

    if not tools_dir.is_dir():
        print(f"⚠ Tools directory not found: {tools_dir}")
        print(f"  Create it with: mkdir {tools_dir}")
        return

    registry = ToolRegistry.from_directory(tools_dir)
    tools = registry.list_tools()

    if not tools:
        print(f"No tools found in {tools_dir}")
        print("Create a Python file with an async def execute() function:")
        print(f"  {tools_dir}/my_tool.py")
        print()
        print("Example:")
        print("  async def execute(query: str) -> str:")
        print('      """Search the web for information."""')
        print("      # ... your implementation")
        print("      return results")
        return

    print(f"Found {len(tools)} tool(s) in {tools_dir}:")
    print()
    for t in tools:
        params = ", ".join(
            f"{k}: {v}" if v else k for k, v in t.input_params.items()
        )
        ret = f" -> {t.output_type}" if t.output_type else ""
        print(f"  {t.name}")
        print(f"    function:  {t.function}({params}){ret}")
        if t.description:
            print(f"    desc:      {t.description}")
        print(f"    source:    {t.path}")
        print()


def main() -> None:
    """Start the AgentIR server or run management commands."""
    parser = argparse.ArgumentParser(
        description="AgentIR Workflow Generator Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Environment variables:\n"
            "  AGENTIR_LLM_PROVIDER     LLM provider (deepseek, openai, ...)\n"
            "  AGENTIR_LLM_API_KEY      API key\n"
            "  AGENTIR_LLM_MODEL        Model name\n"
            "  AGENTIR_HOST             Server host (default: 0.0.0.0)\n"
            "  AGENTIR_PORT             Server port (default: 8000)\n"
        ),
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ---- "tools" subcommand group ----
    tools_parser = subparsers.add_parser("tools", help="Tool management commands")
    tools_sub = tools_parser.add_subparsers(dest="subcommand")

    scan_parser = tools_sub.add_parser("scan", help="Scan tools directory for tools")
    scan_parser.add_argument(
        "--dir",
        default=None,
        help="Tools directory path (default: ./tools)",
    )

    # ---- Server options ----
    parser.add_argument(
        "--host",
        default=None,
        help="Server host (default: 0.0.0.0 or AGENTIR_HOST env)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Server port (default: 8000 or AGENTIR_PORT env)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable hot-reload for development",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode",
    )

    args = parser.parse_args()

    # Handle subcommands
    if args.command == "tools" and args.subcommand == "scan":
        _cmd_tools_scan(args)
        return

    # Import here to avoid startup delay for --help
    from agentir.server.config import ServerConfig

    overrides: dict = {}
    if args.host:
        overrides["host"] = args.host
    if args.port:
        overrides["port"] = args.port
    if args.debug:
        overrides["debug"] = True

    config = ServerConfig.from_env(**overrides)

    print(f"Starting AgentIR Server v{config.version}")
    print(f"  Provider:    {config.llm.provider}")
    print(f"  Model:       {config.llm.model}")
    print(f"  Base URL:    {config.llm.base_url}")
    print(f"  API Key:     {'configured' if config.llm.api_key else 'NOT SET'}")
    print(f"  Tools Dir:   {config.tools_dir}")
    print(f"  Artifacts:   {config.artifacts_dir}")
    print(f"  Listen:      http://{config.host}:{config.port}")
    print(f"  Docs:        http://{config.host}:{config.port}/docs")
    print()

    import uvicorn

    uvicorn.run(
        "agentir.server.main:create_app",
        factory=True,
        host=config.host,
        port=config.port,
        reload=args.reload,
        log_level="debug" if config.debug else "info",
    )


if __name__ == "__main__":
    main()
