"""Tests for the ADK Compiler."""

import pytest

from agentir.compiler.adk.compiler import ADKCompiler, FlatGraph, _flatten_node, _generate_python_code, _make_node_ref
from agentir.compiler.base import CompilationResult
from agentir.ir.models import WorkflowDefinition
from agentir.ir.nodes import (
    AgentNode,
    ConditionNode,
    LoopNode,
    ParallelNode,
    SequenceNode,
)


class TestFlatGraph:
    def test_add_agent(self):
        graph = FlatGraph()
        node_id = graph.add_agent("researcher")
        assert node_id == "researcher_1"
        assert graph.nodes[node_id].kind == "agent"
        assert graph.nodes[node_id].agent_name == "researcher"

    def test_add_multiple_agents_same_name(self):
        graph = FlatGraph()
        id1 = graph.add_agent("worker")
        id2 = graph.add_agent("worker")
        assert id1 == "worker_1"
        assert id2 == "worker_2"

    def test_add_helper(self):
        graph = FlatGraph()
        node_id = graph.add_helper("fork")
        assert node_id == "fork_1"
        assert graph.nodes[node_id].kind == "fork"

    def test_add_edge(self):
        graph = FlatGraph()
        graph.add_edge("a", "b")
        assert len(graph.edges) == 1
        assert graph.edges[0].from_id == "a"
        assert graph.edges[0].to_id == "b"

    def test_add_edge_with_route(self):
        graph = FlatGraph()
        graph.add_edge("a", "b", route="true")
        assert graph.edges[0].route == "true"

    def test_terminal_node(self):
        graph = FlatGraph()
        tid = graph.get_terminal_id()
        assert tid == "__TERMINAL__"
        assert graph.nodes[tid].kind == "terminal"
        # Calling again returns same
        assert graph.get_terminal_id() == "__TERMINAL__"


class TestFlattenNode:
    def _make_graph(self) -> FlatGraph:
        graph = FlatGraph()
        graph.get_terminal_id()  # ensure terminal exists
        return graph

    def test_flatten_agent(self):
        graph = self._make_graph()
        node = AgentNode(agent="researcher")
        exit_id = _flatten_node(node, graph, "__START__")
        assert exit_id == "researcher_1"
        assert len(graph.nodes) >= 2  # terminal + agent
        assert any(e.from_id == "__START__" and e.to_id == "researcher_1" for e in graph.edges)

    def test_flatten_sequence(self):
        graph = self._make_graph()
        node = SequenceNode(steps=[
            AgentNode(agent="a"),
            AgentNode(agent="b"),
            AgentNode(agent="c"),
        ])
        exit_id = _flatten_node(node, graph, "__START__")
        # Verify chain exists: START → a_* → b_* → c_*
        edges_from: dict[str, str] = {}
        for e in graph.edges:
            if e.route == "":
                edges_from[e.from_id] = e.to_id

        a_node = edges_from["__START__"]
        assert a_node.startswith("a_")
        b_node = edges_from[a_node]
        assert b_node.startswith("b_")
        c_node = edges_from[b_node]
        assert c_node.startswith("c_")
        assert exit_id == c_node

    def test_flatten_parallel(self):
        graph = self._make_graph()
        node = ParallelNode(branches=[
            AgentNode(agent="worker_a"),
            AgentNode(agent="worker_b"),
        ])
        exit_id = _flatten_node(node, graph, "__START__")
        # Should have fork and join
        assert any(n.kind == "fork" for n in graph.nodes.values())
        assert any(n.kind == "join" for n in graph.nodes.values())
        # exit should be a join node
        assert graph.nodes[exit_id].kind == "join"

    def test_flatten_condition(self):
        graph = self._make_graph()
        node = ConditionNode(
            expression="x > 0",
            true_branch=AgentNode(agent="positive"),
            false_branch=AgentNode(agent="negative"),
        )
        exit_id = _flatten_node(node, graph, "__START__")
        # Should have condition helper and merge join
        assert any(n.kind == "condition" for n in graph.nodes.values())
        assert any(e.route == "true" for e in graph.edges)
        assert any(e.route == "false" for e in graph.edges)
        # exit should be merge join
        assert graph.nodes[exit_id].kind == "join"

    def test_flatten_loop(self):
        graph = self._make_graph()
        node = LoopNode(
            max_iterations=3,
            body=AgentNode(agent="processor"),
        )
        exit_id = _flatten_node(node, graph, "__START__")
        # Should have loop_counter and a done route
        assert any(n.kind == "loop_counter" for n in graph.nodes.values())
        counter = next(n for n in graph.nodes.values() if n.kind == "loop_counter")
        assert counter.max_iterations == 3

    def test_flatten_complex_nested(self):
        """Test flattening a complex nested workflow."""
        graph = self._make_graph()
        node = SequenceNode(steps=[
            AgentNode(agent="start"),
            ConditionNode(
                expression="check",
                true_branch=LoopNode(
                    max_iterations=2,
                    body=AgentNode(agent="retry"),
                ),
                false_branch=ParallelNode(branches=[
                    AgentNode(agent="fast_a"),
                    AgentNode(agent="fast_b"),
                ]),
            ),
            AgentNode(agent="finish"),
        ])
        exit_id = _flatten_node(node, graph, "__START__")
        # Should produce a valid graph
        assert len(graph.nodes) > 0
        assert len(graph.edges) > 0


class TestCodeGeneration:
    def test_generate_simple_workflow(self):
        graph = FlatGraph()
        graph.get_terminal_id()
        a_id = graph.add_agent("researcher")
        graph.add_edge("__START__", a_id)
        graph.add_edge(a_id, "__TERMINAL__")

        code = _generate_python_code(graph)
        assert "LlmAgent" in code
        assert "Workflow" in code
        assert "researcher" in code
        assert "START" in code

    def test_generated_code_is_valid_python_syntax(self):
        graph = FlatGraph()
        graph.get_terminal_id()
        a_id = graph.add_agent("agent_a")
        b_id = graph.add_agent("agent_b")
        graph.add_edge("__START__", a_id)
        graph.add_edge(a_id, b_id)
        graph.add_edge(b_id, "__TERMINAL__")

        code = _generate_python_code(graph)
        # Verify it compiles as Python
        compile(code, "<generated>", "exec")

    def test_generated_code_with_condition(self):
        graph = FlatGraph()
        graph.get_terminal_id()
        cond_id = graph.add_helper("condition", expression="x > 0")
        t_id = graph.add_agent("true_agent")
        f_id = graph.add_agent("false_agent")
        merge_id = graph.add_helper("join")

        graph.add_edge("__START__", cond_id)
        graph.add_edge(cond_id, t_id, route="true")
        graph.add_edge(cond_id, f_id, route="false")
        graph.add_edge(t_id, merge_id)
        graph.add_edge(f_id, merge_id)
        graph.add_edge(merge_id, "__TERMINAL__")

        code = _generate_python_code(graph)
        assert "condition" in code
        assert '"true"' in code or "'true'" in code
        assert '"false"' in code or "'false'" in code
        compile(code, "<generated>", "exec")

    def test_generated_code_with_loop(self):
        graph = FlatGraph()
        graph.get_terminal_id()
        counter_id = graph.add_helper("loop_counter", max_iterations=3)
        body_id = graph.add_agent("processor")
        exit_id = graph.add_helper("join")

        graph.add_edge("__START__", counter_id)
        graph.add_edge(counter_id, body_id)
        graph.add_edge(body_id, counter_id)
        graph.add_edge(counter_id, exit_id, route="done")
        graph.add_edge(exit_id, "__TERMINAL__")

        code = _generate_python_code(graph)
        assert "loop_counter" in code
        assert "max_iterations" in code or "3" in code
        compile(code, "<generated>", "exec")


class TestADKCompiler:
    def test_compile_simple_agent(self):
        compiler = ADKCompiler()
        wf = WorkflowDefinition(
            name="simple",
            root=AgentNode(agent="researcher"),
        )
        result = compiler.compile(wf)
        assert result.success
        assert result.runtime == "adk"
        assert "researcher" in result.source_code
        assert "LlmAgent" in result.source_code
        assert "Workflow" in result.source_code

    def test_compile_sequence(self):
        compiler = ADKCompiler()
        wf = WorkflowDefinition(
            name="pipeline",
            root=SequenceNode(steps=[
                AgentNode(agent="step1"),
                AgentNode(agent="step2"),
                AgentNode(agent="step3"),
            ]),
        )
        result = compiler.compile(wf)
        assert result.success
        # Verify generated code compiles
        compile(result.source_code, "<generated>", "exec")

    def test_compile_parallel(self):
        compiler = ADKCompiler()
        wf = WorkflowDefinition(
            name="parallel_job",
            root=ParallelNode(branches=[
                AgentNode(agent="worker1"),
                AgentNode(agent="worker2"),
            ]),
        )
        result = compiler.compile(wf)
        assert result.success
        assert "fork" in result.source_code.lower() or "@node" in result.source_code.lower()
        compile(result.source_code, "<generated>", "exec")

    def test_compile_condition(self):
        compiler = ADKCompiler()
        wf = WorkflowDefinition(
            name="branching",
            root=ConditionNode(
                expression="quality > 0.8",
                true_branch=AgentNode(agent="publish"),
                false_branch=AgentNode(agent="revise"),
            ),
        )
        result = compiler.compile(wf)
        assert result.success
        compile(result.source_code, "<generated>", "exec")

    def test_compile_loop(self):
        compiler = ADKCompiler()
        wf = WorkflowDefinition(
            name="retry_loop",
            root=LoopNode(
                max_iterations=5,
                body=AgentNode(agent="reviewer"),
            ),
        )
        result = compiler.compile(wf)
        assert result.success
        compile(result.source_code, "<generated>", "exec")

    def test_compile_complex_workflow(self):
        compiler = ADKCompiler()
        wf = WorkflowDefinition(
            name="research_pipeline",
            description="Full research pipeline",
            root=SequenceNode(steps=[
                AgentNode(agent="researcher"),
                ConditionNode(
                    expression="needs_review",
                    true_branch=LoopNode(
                        max_iterations=3,
                        body=AgentNode(agent="reviewer"),
                    ),
                    false_branch=AgentNode(agent="writer"),
                ),
                AgentNode(agent="publisher"),
            ]),
        )
        result = compiler.compile(wf)
        assert result.success
        assert "researcher" in result.source_code
        assert "reviewer" in result.source_code
        assert "writer" in result.source_code
        assert "publisher" in result.source_code
        # Should be valid Python
        compile(result.source_code, "<generated>", "exec")

    def test_compile_parallel_translation(self):
        compiler = ADKCompiler()
        wf = WorkflowDefinition(
            name="translation",
            root=SequenceNode(steps=[
                AgentNode(agent="extractor"),
                ParallelNode(branches=[
                    AgentNode(agent="translator_en"),
                    AgentNode(agent="translator_zh"),
                ]),
                AgentNode(agent="merger"),
            ]),
        )
        result = compiler.compile(wf)
        assert result.success
        compile(result.source_code, "<generated>", "exec")


class TestCompilationResult:
    def test_success_result(self):
        result = CompilationResult(
            success=True,
            source_code="print('hello')",
            runtime="adk",
        )
        assert result.success
        assert result.code == "print('hello')"

    def test_failure_result(self):
        result = CompilationResult(
            success=False,
            errors=["Something went wrong"],
            runtime="adk",
        )
        assert not result.success
        assert len(result.errors) == 1


# ---- Test: ADK Compiler with AgentConfig (model/instruction injection) ----

class TestADKCompilerWithAgentConfig:
    """Test agent configuration injection into compiled code."""

    def test_compile_with_agent_model(self):
        """AgentConfig.model should appear in generated code."""
        from agentir.llm.config import AgentConfig

        compiler = ADKCompiler()
        wf = WorkflowDefinition(
            name="model_test",
            root=AgentNode(agent="researcher"),
        )
        configs = {
            "researcher": AgentConfig(
                agent_name="researcher",
                model="deepseek-chat",
                instruction="You research topics.",
            ),
        }
        result = compiler.compile(wf, agent_configs=configs)
        assert result.success
        assert "model=\"deepseek-chat\"" in result.source_code
        assert "You research topics." in result.source_code
        compile(result.source_code, "<generated>", "exec")

    def test_compile_with_agent_tools(self):
        """AgentConfig.tools should appear in generated code."""
        from agentir.llm.config import AgentConfig

        compiler = ADKCompiler()
        wf = WorkflowDefinition(
            name="tools_test",
            root=AgentNode(agent="assistant"),
        )
        configs = {
            "assistant": AgentConfig(
                agent_name="assistant",
                model="gpt-4o",
                instruction="You are helpful.",
                tools=["google_search", "calculator"],
            ),
        }
        result = compiler.compile(wf, agent_configs=configs)
        assert result.success
        assert "tools=[" in result.source_code
        assert "google_search" in result.source_code
        assert "calculator" in result.source_code
        compile(result.source_code, "<generated>", "exec")

    def test_compile_with_agent_temperature(self):
        """AgentConfig.temperature should appear in generated code."""
        from agentir.llm.config import AgentConfig

        compiler = ADKCompiler()
        wf = WorkflowDefinition(
            name="temp_test",
            root=AgentNode(agent="creative"),
        )
        configs = {
            "creative": AgentConfig(
                agent_name="creative",
                model="deepseek-chat",
                temperature=0.9,
            ),
        }
        result = compiler.compile(wf, agent_configs=configs)
        assert result.success
        assert "temperature=0.9" in result.source_code
        compile(result.source_code, "<generated>", "exec")

    def test_compile_multiple_agents_with_configs(self):
        """Each agent should get its own model and instruction."""
        from agentir.llm.config import AgentConfig

        compiler = ADKCompiler()
        wf = WorkflowDefinition(
            name="multi_agent",
            root=SequenceNode(steps=[
                AgentNode(agent="researcher"),
                AgentNode(agent="writer"),
            ]),
        )
        configs = {
            "researcher": AgentConfig(
                agent_name="researcher",
                model="deepseek-chat",
                instruction="Research deeply.",
            ),
            "writer": AgentConfig(
                agent_name="writer",
                model="deepseek-reasoner",
                instruction="Write eloquently.",
            ),
        }
        result = compiler.compile(wf, agent_configs=configs)
        assert result.success
        assert 'model="deepseek-chat"' in result.source_code
        assert 'model="deepseek-reasoner"' in result.source_code
        assert "Research deeply." in result.source_code
        assert "Write eloquently." in result.source_code
        compile(result.source_code, "<generated>", "exec")

    def test_compile_without_agent_configs_uses_defaults(self):
        """Without AgentConfig, should use compiler defaults."""
        compiler = ADKCompiler(
            default_model="gemini-2.0-flash",
            default_instruction_template="I am {agent_name}.",
        )
        wf = WorkflowDefinition(
            name="defaults_test",
            root=AgentNode(agent="helper"),
        )
        result = compiler.compile(wf)
        assert result.success
        assert 'model="gemini-2.0-flash"' in result.source_code
        assert "I am helper." in result.source_code
        compile(result.source_code, "<generated>", "exec")

    def test_compile_partial_configs_falls_back_to_defaults(self):
        """Agents without configs should get defaults."""
        from agentir.llm.config import AgentConfig

        compiler = ADKCompiler()
        wf = WorkflowDefinition(
            name="partial_test",
            root=SequenceNode(steps=[
                AgentNode(agent="configured"),
                AgentNode(agent="not_configured"),
            ]),
        )
        configs = {
            "configured": AgentConfig(
                agent_name="configured",
                model="deepseek-chat",
                instruction="Custom instruction.",
            ),
        }
        result = compiler.compile(wf, agent_configs=configs)
        assert result.success
        assert 'model="deepseek-chat"' in result.source_code
        assert "Custom instruction." in result.source_code
        # not_configured gets default
        assert 'model="gemini-2.0-flash"' in result.source_code
        compile(result.source_code, "<generated>", "exec")

    def test_compile_no_tools_field_when_empty(self):
        """When tools list is empty, tools= should NOT appear in output."""
        from agentir.llm.config import AgentConfig

        compiler = ADKCompiler()
        wf = WorkflowDefinition(
            name="no_tools_test",
            root=AgentNode(agent="basic"),
        )
        result = compiler.compile(wf)  # No agent_configs at all
        assert "tools=" not in result.source_code
        compile(result.source_code, "<generated>", "exec")

    def test_compile_no_temperature_field_when_none(self):
        """When temperature is None, it should NOT appear in output."""
        from agentir.llm.config import AgentConfig

        compiler = ADKCompiler()
        wf = WorkflowDefinition(
            name="no_temp_test",
            root=AgentNode(agent="basic"),
        )
        configs = {
            "basic": AgentConfig(agent_name="basic", model="gpt-4o", temperature=None),
        }
        result = compiler.compile(wf, agent_configs=configs)
        assert "temperature=" not in result.source_code
        compile(result.source_code, "<generated>", "exec")

    def test_full_pipeline_with_agent_configs(self):
        """NL → Planner → AgentIR → ADK Compiler (with agent configs) → valid Python."""
        from agentir.llm.config import AgentConfig

        compiler = ADKCompiler()
        wf = WorkflowDefinition(
            name="full_pipeline",
            description="End-to-end with agent configs",
            root=SequenceNode(steps=[
                AgentNode(agent="researcher"),
                ConditionNode(
                    expression="output.needs_review",
                    true_branch=LoopNode(
                        max_iterations=3,
                        body=AgentNode(agent="reviewer"),
                    ),
                    false_branch=AgentNode(agent="writer"),
                ),
                AgentNode(agent="publisher"),
            ]),
        )
        configs = {
            "researcher": AgentConfig(
                agent_name="researcher", model="deepseek-chat",
                instruction="You are a researcher.", temperature=0.3,
            ),
            "reviewer": AgentConfig(
                agent_name="reviewer", model="deepseek-chat",
                instruction="You are a reviewer.", temperature=0.1,
            ),
            "writer": AgentConfig(
                agent_name="writer", model="deepseek-reasoner",
                instruction="You are a writer.", temperature=0.5,
            ),
            "publisher": AgentConfig(
                agent_name="publisher", model="deepseek-chat",
                instruction="You are a publisher.", tools=["publish_api"],
            ),
        }
        result = compiler.compile(wf, agent_configs=configs)
        assert result.success

        # Verify all agents have their configs
        assert 'model="deepseek-chat"' in result.source_code
        assert 'model="deepseek-reasoner"' in result.source_code
        assert "You are a researcher." in result.source_code
        assert "You are a reviewer." in result.source_code
        assert "You are a writer." in result.source_code
        assert "You are a publisher." in result.source_code
        assert "temperature=0.3" in result.source_code
        assert "temperature=0.1" in result.source_code
        assert "temperature=0.5" in result.source_code
        assert "publish_api" in result.source_code

        # Must be valid Python
        compile(result.source_code, "<generated>", "exec")
