import { useMemo, useCallback } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type NodeProps,
  type Node,
  Handle,
  Position,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { irToGraph } from "../utils/ir-to-graph";
import type { IRNode, FlowNode, FlowEdge, SelectedNode } from "../types";

// ---- Custom Nodes ----

function AgentNodeView({ data, selected }: NodeProps) {
  return (
    <div className={`rf-node agent-node ${selected ? "selected-node" : ""}`}>
      <Handle type="target" position={Position.Top} />
      <div className="node-icon">🤖</div>
      <div className="node-label">{data.label as string}</div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

function ToolNodeView({ data, selected }: NodeProps) {
  return (
    <div className={`rf-node tool-node ${selected ? "selected-node" : ""}`}>
      <Handle type="target" position={Position.Top} />
      <div className="node-icon">🔧</div>
      <div className="node-label">{data.label as string}</div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

function ConditionNodeView({ data, selected }: NodeProps) {
  return (
    <div className={`rf-node condition-node ${selected ? "selected-node" : ""}`}>
      <Handle type="target" position={Position.Top} />
      <div className="node-label cond-label">{data.label as string}</div>
      <Handle type="source" position={Position.Bottom} id="true" />
      <Handle type="source" position={Position.Left} id="false" />
    </div>
  );
}

function LoopNodeView({ data, selected }: NodeProps) {
  return (
    <div className={`rf-node loop-node ${selected ? "selected-node" : ""}`}>
      <Handle type="target" position={Position.Top} />
      <div className="node-icon">🔄</div>
      <div className="node-label">{data.label as string}</div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

function SubWorkflowNodeView({ data, selected }: NodeProps) {
  return (
    <div className={`rf-node subworkflow-node ${selected ? "selected-node" : ""}`}>
      <Handle type="target" position={Position.Top} />
      <div className="node-icon">📦</div>
      <div className="node-label">{data.label as string}</div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

function HelperNodeView({ data }: NodeProps) {
  return (
    <div className="rf-node helper-node">
      <Handle type="target" position={Position.Top} />
      <div className="node-label helper-label">{data.label as string}</div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

const nodeTypes = {
  agent: AgentNodeView,
  tool: ToolNodeView,
  subworkflow: SubWorkflowNodeView,
  condition: ConditionNodeView,
  loop: LoopNodeView,
  helper: HelperNodeView,
};

// ---- Main Component ----

interface Props {
  ir: IRNode;
  onNodeSelect?: (selected: SelectedNode | null) => void;
}

export default function WorkflowGraph({ ir, onNodeSelect }: Props) {
  const { nodes, edges } = useMemo(() => irToGraph(ir), [ir]);

  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      if (!onNodeSelect) return;

      const data = node.data as {
        label: string;
        kind: string;
        irPath?: (string | number)[];
        irNode?: IRNode;
      };

      // Helper nodes (START, fork, join, merge, exit) don't have IR paths
      if (!data.irPath || !data.irNode) {
        onNodeSelect(null);
        return;
      }

      onNodeSelect({
        nodeId: node.id,
        irPath: data.irPath,
        label: data.label,
        kind: data.kind,
        irNode: data.irNode,
      });
    },
    [onNodeSelect]
  );

  const handlePaneClick = useCallback(() => {
    if (onNodeSelect) {
      onNodeSelect(null);
    }
  }, [onNodeSelect]);

  return (
    <div className="graph-container">
      <ReactFlow
        nodes={nodes as FlowNode[]}
        edges={edges as FlowEdge[]}
        nodeTypes={nodeTypes as Record<string, React.ComponentType<NodeProps>>}
        onNodeClick={handleNodeClick}
        onPaneClick={handlePaneClick}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        attributionPosition="bottom-left"
      >
        <Background />
        <Controls />
        <MiniMap
          nodeColor={(n) => {
            const kind = (n.data as { kind?: string })?.kind;
            switch (kind) {
              case "agent":
                return "#3b82f6";
              case "tool":
                return "#22c55e";
              case "subworkflow":
                return "#06b6d4";
              case "condition":
                return "#f59e0b";
              case "loop":
                return "#a855f7";
              default:
                return "#94a3b8";
            }
          }}
        />
      </ReactFlow>
    </div>
  );
}
