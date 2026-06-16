"""Tests for the AgentIR Tools module — scanner, registry, and workflow integration."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


# ---- Test: Tool Scanner ----

class TestToolScanner:
    def test_scan_simple_tool(self):
        from agentir.tools.scanner import ToolInfo

        src = '''async def execute(query: str) -> str:
    """Search the web for information."""
    return f"Results for {query}"
'''
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(src)
            f.flush()
            info = ToolInfo.from_file(Path(f.name))
            Path(f.name).unlink()

        assert info is not None
        assert info.name != ""
        assert info.function == "execute"
        assert info.description == "Search the web for information."
        assert info.input_params == {"query": "str"}
        assert info.output_type == "str"

    def test_scan_tool_without_execute(self):
        from agentir.tools.scanner import ToolInfo

        src = '''def helper(): pass
'''
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(src)
            f.flush()
            info = ToolInfo.from_file(Path(f.name))
            Path(f.name).unlink()

        assert info is None

    def test_scan_tool_regular_function(self):
        """Regular def (not async) should NOT be discovered as a tool."""
        from agentir.tools.scanner import ToolInfo

        src = '''def execute(query: str) -> str:
    """Sync version."""
    return query
'''
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(src)
            f.flush()
            info = ToolInfo.from_file(Path(f.name))
            Path(f.name).unlink()

        assert info is None  # Only async def is recognized

    def test_scan_syntax_error_file(self):
        from agentir.tools.scanner import ToolInfo

        src = "this is not python !!!"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(src)
            f.flush()
            info = ToolInfo.from_file(Path(f.name))
            Path(f.name).unlink()

        assert info is None

    def test_scan_tool_without_docstring(self):
        from agentir.tools.scanner import ToolInfo

        src = "async def execute(data: dict) -> list:\n    return []\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(src)
            f.flush()
            info = ToolInfo.from_file(Path(f.name))
            Path(f.name).unlink()

        assert info is not None
        assert info.description == ""
        assert info.input_params == {"data": "dict"}
        assert info.output_type == "list"


# ---- Test: Tool Registry ----

class TestToolRegistry:
    def test_from_directory_empty(self):
        from agentir.tools.registry import ToolRegistry

        with tempfile.TemporaryDirectory() as tmp:
            registry = ToolRegistry.from_directory(tmp)
            assert len(registry.tools) == 0
            assert registry.list_tools() == []

    def test_from_directory_with_tools(self):
        from agentir.tools.registry import ToolRegistry

        with tempfile.TemporaryDirectory() as tmp:
            tools_dir = Path(tmp)
            (tools_dir / "web_search.py").write_text(
                'async def execute(query: str) -> str:\n'
                '    """Search the web."""\n'
                '    return query\n'
            )
            (tools_dir / "calculator.py").write_text(
                'async def execute(expression: str) -> str:\n'
                '    """Calculate things."""\n'
                '    return expression\n'
            )

            registry = ToolRegistry.from_directory(tools_dir)
            assert len(registry.tools) == 2
            assert registry.has("web_search")
            assert registry.has("calculator")
            assert not registry.has("nonexistent")

    def test_get_tool_info(self):
        from agentir.tools.registry import ToolRegistry

        with tempfile.TemporaryDirectory() as tmp:
            tools_dir = Path(tmp)
            (tools_dir / "my_tool.py").write_text(
                'async def execute(x: int) -> bool:\n'
                '    """My tool."""\n'
                '    return True\n'
            )
            registry = ToolRegistry.from_directory(tools_dir)
            info = registry.get("my_tool")
            assert info is not None
            assert info.name == "my_tool"
            assert info.description == "My tool."
            assert info.input_params == {"x": "int"}
            assert info.output_type == "bool"

    def test_empty_registry(self):
        from agentir.tools.registry import ToolRegistry

        registry = ToolRegistry.empty()
        assert len(registry.tools) == 0
        assert registry.to_prompt_context() == "No custom tools available."

    def test_to_prompt_context(self):
        from agentir.tools.registry import ToolRegistry

        with tempfile.TemporaryDirectory() as tmp:
            tools_dir = Path(tmp)
            (tools_dir / "search.py").write_text(
                'async def execute(q: str) -> str:\n'
                '    """Search."""\n'
                '    return q\n'
            )
            registry = ToolRegistry.from_directory(tools_dir)
            ctx = registry.to_prompt_context()
            assert "search" in ctx
            assert "Search." in ctx
            assert "execute(q: str)" in ctx

    def test_skips_init_and_hidden(self):
        from agentir.tools.registry import ToolRegistry

        with tempfile.TemporaryDirectory() as tmp:
            tools_dir = Path(tmp)
            (tools_dir / "__init__.py").write_text(
                'async def execute(x: str) -> str:\n    return x\n'
            )
            (tools_dir / "_internal.py").write_text(
                'async def execute(x: str) -> str:\n    return x\n'
            )
            (tools_dir / ".hidden.py").write_text(
                'async def execute(x: str) -> str:\n    return x\n'
            )
            (tools_dir / "valid.py").write_text(
                'async def execute(x: str) -> str:\n    return x\n'
            )

            registry = ToolRegistry.from_directory(tools_dir)
            assert len(registry.tools) == 1
            assert registry.has("valid")


# ---- Test: ToolNode IR ----

class TestToolNode:
    def test_tool_node_model(self):
        from agentir.ir.nodes import ToolNode

        node = ToolNode(tool="web_search")
        assert node.type == "tool"
        assert node.tool == "web_search"
        data = node.model_dump()
        assert data == {"type": "tool", "tool": "web_search"}

    def test_tool_node_in_workflow(self):
        from agentir.ir.models import WorkflowDefinition
        from agentir.ir.nodes import AgentNode, SequenceNode, ToolNode

        wf = WorkflowDefinition(
            name="tool_test",
            root=SequenceNode(steps=[
                ToolNode(tool="search"),
                AgentNode(agent="analyzer"),
            ]),
        )
        data = wf.model_dump()
        assert data["root"]["steps"][0]["type"] == "tool"
        assert data["root"]["steps"][0]["tool"] == "search"

    def test_tool_node_json_roundtrip(self):
        from agentir.ir.schema import workflow_from_json
        from agentir.ir.nodes import AgentNode, SequenceNode, ToolNode

        json_str = (
            '{"name":"test","version":"0.1.0","root":'
            '{"type":"sequence","steps":['
            '{"type":"tool","tool":"web_search"},'
            '{"type":"agent","agent":"analyst"}'
            ']}}'
        )
        wf = workflow_from_json(json_str)
        assert len(wf.root.steps) == 2
        assert isinstance(wf.root.steps[0], ToolNode)
        assert wf.root.steps[0].tool == "web_search"
        assert isinstance(wf.root.steps[1], AgentNode)


# ---- Test: Validator with Tools ----

class TestValidatorTools:
    def test_valid_tool_passes(self):
        from agentir.ir.models import WorkflowDefinition
        from agentir.ir.nodes import ToolNode
        from agentir.tools.registry import ToolRegistry
        from agentir.validator.validator import validate_workflow

        wf = WorkflowDefinition(
            name="tool_wf",
            root=ToolNode(tool="web_search"),
        )

        # Without registry — should pass (tool existence not checked)
        report = validate_workflow(wf)
        assert report.is_valid

        # With registry containing the tool — should pass
        registry = ToolRegistry.empty()
        # We need to add the tool to the registry without a file
        from agentir.tools.scanner import ToolInfo
        registry.tools["web_search"] = ToolInfo(
            name="web_search", path="/fake/web_search.py"
        )
        report = validate_workflow(wf, tool_registry=registry)
        assert report.is_valid

    def test_missing_tool_detected(self):
        from agentir.ir.models import WorkflowDefinition
        from agentir.ir.nodes import ToolNode
        from agentir.tools.registry import ToolRegistry
        from agentir.validator.validator import validate_workflow

        wf = WorkflowDefinition(
            name="tool_wf",
            root=ToolNode(tool="nonexistent_tool"),
        )
        registry = ToolRegistry.empty()
        report = validate_workflow(wf, tool_registry=registry)
        assert not report.is_valid
        assert any("TOOL_NOT_FOUND" in str(e) for e in report.errors)


# ---- Test: Compiler with Tools ----

class TestCompilerTools:
    def test_compile_simple_tool_workflow(self):
        from agentir.ir.models import WorkflowDefinition
        from agentir.ir.nodes import AgentNode, SequenceNode, ToolNode
        from agentir.compiler.adk import ADKCompiler

        compiler = ADKCompiler()
        wf = WorkflowDefinition(
            name="tool_agent_workflow",
            root=SequenceNode(steps=[
                ToolNode(tool="web_search"),
                AgentNode(agent="analyst"),
            ]),
        )
        result = compiler.compile(wf, tools_dir="./tools")
        assert result.success
        code = result.source_code

        # Check tool wrapper
        assert "tool_web_search" in code
        assert "from web_search import execute" in code
        assert "ctx.run_node(tool_web_search" in code
        assert "ctx.run_node(analyst" in code

        # Check sys path setup
        assert "sys.path.insert" in code

        # Must be valid Python
        compile(code, "<generated>", "exec")

    def test_compile_parallel_tools(self):
        from agentir.ir.models import WorkflowDefinition
        from agentir.ir.nodes import ParallelNode, ToolNode
        from agentir.compiler.adk import ADKCompiler

        compiler = ADKCompiler()
        wf = WorkflowDefinition(
            name="parallel_tools",
            root=ParallelNode(branches=[
                ToolNode(tool="web_search"),
                ToolNode(tool="calculator"),
            ]),
        )
        result = compiler.compile(wf, tools_dir="./tools")
        assert result.success
        code = result.source_code
        assert "asyncio.gather" in code
        assert "tool_web_search" in code
        assert "tool_calculator" in code
        assert "web_search import" in code
        assert "calculator import" in code
        compile(code, "<generated>", "exec")

    def test_compile_no_tools_in_workflow(self):
        from agentir.ir.models import WorkflowDefinition
        from agentir.ir.nodes import AgentNode
        from agentir.compiler.adk import ADKCompiler

        compiler = ADKCompiler()
        wf = WorkflowDefinition(
            name="no_tools",
            root=AgentNode(agent="simple"),
        )
        result = compiler.compile(wf)
        assert result.success
        # No tool imports or sys.path manipulation
        assert "sys.path.insert" not in result.source_code
        assert "from" not in result.source_code.split("from google.adk")[0]


# ---- Test: Planner with Tools ----

class TestPlannerTools:
    def test_system_prompt_has_tool_node_type(self):
        from agentir.planner.planner import _SYSTEM_PROMPT

        assert "ToolNode" in _SYSTEM_PROMPT
        assert '"tool"' in _SYSTEM_PROMPT
        assert "{tool_context}" in _SYSTEM_PROMPT

    def test_build_prompt_with_tools(self):
        from agentir.planner.planner import Planner
        from agentir.tools.registry import ToolRegistry
        from agentir.tools.scanner import ToolInfo

        # Create a minimal tool registry
        registry = ToolRegistry.empty()
        registry.tools["web_search"] = ToolInfo(
            name="web_search",
            path="/fake/web_search.py",
            description="Search the web for information.",
            input_params={"query": "str"},
            output_type="str",
        )

        def dummy_llm(prompt: str) -> str:
            assert "web_search" in prompt
            assert "Search the web for information" in prompt
            assert "ToolNode" in prompt
            import json
            return json.dumps({
                "name": "search_flow",
                "root": {
                    "type": "sequence",
                    "steps": [
                        {"type": "tool", "tool": "web_search"},
                        {"type": "agent", "agent": "analyst"},
                    ],
                },
            })

        planner = Planner(llm_callable=dummy_llm)
        result = planner.plan("Search then analyze", available_tools=registry)
        assert result.success
        assert result.workflow is not None


# ---- Test: Integration (Compiler + Tools via Server API) ----

class TestServerToolEndpoints:
    def test_tool_list_empty(self):
        """Test /api/v1/tools when no tools exist."""
        from agentir.tools.registry import ToolRegistry

        registry = ToolRegistry.empty()
        assert len(registry.list_tools()) == 0
        assert registry.to_prompt_context() == "No custom tools available."
