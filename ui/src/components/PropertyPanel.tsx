import { useState, useEffect } from "react";
import type { IRNode, SelectedNode } from "../types";
import { updateNodeProperty, getContainerLabel, isContainer, isLeaf, getChildList, addChildNode, removeNode, getAvailableChildTypes } from "../utils/ir-tree-ops";

interface Props {
  selected: SelectedNode | null;
  rootIR: IRNode;
  onIRChange: (newRoot: IRNode) => void;
  onClearSelection: () => void;
  onRegenerateGraph: () => void;
}

export default function PropertyPanel({
  selected,
  rootIR,
  onIRChange,
  onClearSelection,
  onRegenerateGraph,
}: Props) {
  const [agentName, setAgentName] = useState("");
  const [agentInstruction, setAgentInstruction] = useState("");
  const [toolName, setToolName] = useState("");
  const [subworkflowName, setSubworkflowName] = useState("");
  const [expression, setExpression] = useState("");
  const [maxIterations, setMaxIterations] = useState(3);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (selected) {
      const irNode = selected.irNode;
      if (irNode.type === "agent") {
        setAgentName(irNode.agent);
        setAgentInstruction((irNode as { instruction?: string }).instruction || "");
      } else if (irNode.type === "tool") {
        setToolName(irNode.tool);
      } else if (irNode.type === "subworkflow") {
        setSubworkflowName(irNode.workflow);
      } else if (irNode.type === "condition") {
        setExpression(irNode.expression);
      } else if (irNode.type === "loop") {
        setMaxIterations(irNode.max_iterations);
      }
      setDirty(false);
    }
  }, [selected]);

  function handleSave() {
    if (!selected) return;

    if (selected.kind === "agent" && agentName.trim()) {
      const newRoot = updateNodeProperty(rootIR, selected.irPath, "agent", agentName.trim());
      updateNodeProperty(newRoot, selected.irPath, "instruction", agentInstruction.trim());
      onIRChange(newRoot);
    } else if (selected.kind === "tool" && toolName.trim()) {
      const newRoot = updateNodeProperty(rootIR, selected.irPath, "tool", toolName.trim());
      onIRChange(newRoot);
    } else if (selected.kind === "subworkflow" && subworkflowName.trim()) {
      const newRoot = updateNodeProperty(rootIR, selected.irPath, "workflow", subworkflowName.trim());
      onIRChange(newRoot);
    } else if (selected.kind === "condition" && expression.trim()) {
      const newRoot = updateNodeProperty(rootIR, selected.irPath, "expression", expression.trim());
      onIRChange(newRoot);
    } else if (selected.kind === "loop" && maxIterations > 0) {
      const newRoot = updateNodeProperty(rootIR, selected.irPath, "max_iterations", maxIterations);
      onIRChange(newRoot);
    }
    setDirty(false);
    onRegenerateGraph();
  }

  function handleAddChild(childType: string) {
    if (!selected) return;
    const newRoot = addChildNode(rootIR, selected.irPath, childType);
    onIRChange(newRoot);
    onRegenerateGraph();
  }

  function handleDeleteNode() {
    if (!selected) return;
    const newRoot = removeNode(rootIR, selected.irPath);
    if (newRoot) {
      onIRChange(newRoot);
      onClearSelection();
      onRegenerateGraph();
    }
  }

  if (!selected) {
    return (
      <div className="property-panel">
        <div className="panel-header">
          <h3>Properties</h3>
        </div>
        <div className="panel-empty">
          <p>Click a node to edit its properties.</p>
        </div>
      </div>
    );
  }

  const irNode = selected.irNode;
  const canHaveChildren = isContainer(irNode);
  const isLeafNode = isLeaf(irNode);

  return (
    <div className="property-panel">
      <div className="panel-header">
        <h3>Properties</h3>
        <button className="btn-close" onClick={onClearSelection}>
          ✕
        </button>
      </div>

      <div className="panel-body">
        <div className="prop-section">
          <label className="prop-label">Type</label>
          <span className={`prop-kind kind-${selected.kind}`}>
            {selected.kind.toUpperCase()}
          </span>
        </div>

        {isLeafNode && selected.kind === "agent" && (
          <>
            <div className="prop-section">
              <label className="prop-label">Agent Name</label>
              <input
                className="prop-input"
                value={agentName}
                onChange={(e) => {
                  setAgentName(e.target.value);
                  setDirty(true);
                }}
                placeholder="e.g. researcher"
              />
            </div>
            <div className="prop-section">
              <label className="prop-label">Instruction (System Prompt)</label>
              <textarea
                className="prop-input prop-textarea"
                value={agentInstruction}
                onChange={(e) => {
                  setAgentInstruction(e.target.value);
                  setDirty(true);
                }}
                placeholder="e.g. Research the latest AI trends and summarize key findings"
                rows={3}
              />
            </div>
          </>
        )}

        {isLeafNode && selected.kind === "tool" && (
          <div className="prop-section">
            <label className="prop-label">Tool Name</label>
            <input
              className="prop-input"
              value={toolName}
              onChange={(e) => {
                setToolName(e.target.value);
                setDirty(true);
              }}
              placeholder="e.g. web_search"
            />
          </div>
        )}

        {isLeafNode && selected.kind === "subworkflow" && (
          <div className="prop-section">
            <label className="prop-label">Sub-Workflow Name</label>
            <input
              className="prop-input"
              value={subworkflowName}
              onChange={(e) => {
                setSubworkflowName(e.target.value);
                setDirty(true);
              }}
              placeholder="e.g. data_pipeline"
            />
          </div>
        )}

        {selected.kind === "condition" && (
          <div className="prop-section">
            <label className="prop-label">Expression</label>
            <input
              className="prop-input"
              value={expression}
              onChange={(e) => {
                setExpression(e.target.value);
                setDirty(true);
              }}
              placeholder="e.g. output.needs_review"
            />
          </div>
        )}

        {selected.kind === "loop" && (
          <div className="prop-section">
            <label className="prop-label">Max Iterations</label>
            <input
              className="prop-input"
              type="number"
              min={1}
              value={maxIterations}
              onChange={(e) => {
                setMaxIterations(parseInt(e.target.value) || 1);
                setDirty(true);
              }}
            />
          </div>
        )}

        {canHaveChildren && (
          <div className="prop-section">
            <label className="prop-label">
              {getContainerLabel(irNode)} Children ({getChildList(irNode)?.list.length ?? 0})
            </label>
            <div className="child-actions">
              {getAvailableChildTypes(irNode).map((childType) => (
                <button
                  key={childType}
                  className="btn-add-child"
                  onClick={() => handleAddChild(childType)}
                >
                  + {childType}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="prop-actions">
          {dirty && (
            <button className="btn-primary btn-save-prop" onClick={handleSave}>
              Save Changes
            </button>
          )}
          <button className="btn-delete" onClick={handleDeleteNode}>
            Delete Node
          </button>
        </div>
      </div>
    </div>
  );
}
