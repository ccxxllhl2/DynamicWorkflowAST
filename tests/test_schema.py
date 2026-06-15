"""Tests for schema utilities: serialization helpers."""

import json
import tempfile
from pathlib import Path

from agentir.ir.models import WorkflowDefinition
from agentir.ir.nodes import AgentNode, SequenceNode
from agentir.ir.schema import (
    generate_json_schema,
    node_to_dict,
    node_to_json,
    workflow_from_dict,
    workflow_from_file,
    workflow_from_json,
    workflow_to_dict,
    workflow_to_file,
    workflow_to_json,
)


class TestSerialization:
    def test_workflow_to_dict(self):
        wf = WorkflowDefinition(
            name="test", root=AgentNode(agent="researcher")
        )
        d = workflow_to_dict(wf)
        assert d["name"] == "test"
        assert d["root"]["type"] == "agent"

    def test_workflow_to_json(self):
        wf = WorkflowDefinition(
            name="test", root=AgentNode(agent="researcher")
        )
        s = workflow_to_json(wf)
        assert isinstance(s, str)
        data = json.loads(s)
        assert data["name"] == "test"

    def test_workflow_from_dict(self):
        wf = workflow_from_dict(
            {"name": "test", "root": {"type": "agent", "agent": "researcher"}}
        )
        assert wf.name == "test"
        assert wf.root.agent == "researcher"

    def test_workflow_from_json(self):
        wf = workflow_from_json(
            '{"name": "test", "root": {"type": "agent", "agent": "researcher"}}'
        )
        assert wf.name == "test"

    def test_workflow_roundtrip_dict(self):
        original = WorkflowDefinition(
            name="roundtrip",
            version="1.0.0",
            description="test",
            root=SequenceNode(
                steps=[
                    AgentNode(agent="a"),
                    AgentNode(agent="b"),
                ]
            ),
        )
        d = workflow_to_dict(original)
        restored = workflow_from_dict(d)
        assert restored.name == original.name
        assert restored.version == original.version
        assert len(restored.root.steps) == 2

    def test_workflow_roundtrip_json(self):
        original = WorkflowDefinition(
            name="rt", root=AgentNode(agent="test")
        )
        s = workflow_to_json(original)
        restored = workflow_from_json(s)
        assert restored.name == "rt"

    def test_node_to_dict(self):
        node = AgentNode(agent="test")
        d = node_to_dict(node)
        assert d == {"type": "agent", "agent": "test"}

    def test_node_to_json(self):
        node = AgentNode(agent="test")
        s = node_to_json(node)
        assert "agent" in s


class TestFileIO:
    def test_workflow_to_file_and_from_file(self):
        wf = WorkflowDefinition(
            name="file_test",
            root=AgentNode(agent="researcher"),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test_workflow.json"
            workflow_to_file(wf, filepath)
            assert filepath.exists()

            loaded = workflow_from_file(filepath)
            assert loaded.name == "file_test"
            assert loaded.root.agent == "researcher"

    def test_workflow_to_file_creates_parent_dirs(self):
        wf = WorkflowDefinition(
            name="nested", root=AgentNode(agent="r")
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "a" / "b" / "workflow.json"
            workflow_to_file(wf, filepath)
            assert filepath.exists()


class TestJsonSchema:
    def test_generates_json_schema(self):
        schema = generate_json_schema()
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "name" in schema["properties"]
        assert "root" in schema["properties"]
        assert schema["required"] == ["name", "root"]

    def test_json_schema_is_valid(self):
        schema = generate_json_schema()
        # Ensure it's a valid JSON-serializable dict
        json.dumps(schema)
