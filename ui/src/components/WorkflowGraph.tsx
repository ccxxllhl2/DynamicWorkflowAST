import { useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type NodeProps,
  Handle,
  Position,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { irToGraph } from "../utils/ir-to-graph";
import type { IRNode, FlowNode } from "../types";

// ---- Custom Nodes ----

function AgentNodeView({ data }: NodeProps) {
  return (
    <div className="rf-node agent-node">
      <Handle type="target" position={Position.Top} />
      <div className="node-icon">🤖</div>
      <div className="node-label">{data.label as string}</div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

function ToolNodeView({ data }: NodeProps) {
  return (
    <div className="rf-node tool-node">
      <Handle type="target" position={Position.Top} />
      <div className="node-icon">🔧</div>
      <div className="node-label">{data.label as string}</div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

function ConditionNodeView({ data }: NodeProps) {
  return (
    <div className="rf-node condition-node">
      <Handle type="target" position={Position.Top} />
      <div className="node-label cond-label">{data.label as string}</div>
      <Handle type="source" position={Position.Bottom} id="true" />
      <Handle type="source" position={Position.Left} id="false" />
    </div>
  );
}

function LoopNodeView({ data }: NodeProps) {
  return (
    <div className="rf-node loop-node">
      <Handle type="target" position={Position.Top} />
      <div className="node-icon">🔄</div>
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
  condition: ConditionNodeView,
  loop: LoopNodeView,
  helper: HelperNodeView,
};

// ---- Main Component ----

interface Props {
  ir: IRNode;
}

export default function WorkflowGraph({ ir }: Props) {
  const { nodes, edges } = useMemo(() => irToGraph(ir), [ir]);

  return (
    <div className="graph-container">
      <ReactFlow
        nodes={nodes as FlowNode[]}
        edges={edges as Record<string, unknown>[]}
        nodeTypes={nodeTypes as Record<string, React.ComponentType<NodeProps>>}
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
              case "agent": return "#3b82f6";
              case "tool": return "#22c55e";
              case "condition": return "#f59e0b";
              case "loop": return "#a855f7";
              default: return "#94a3b8";
            }
          }}
        />
      </ReactFlow>
    </div>
  );
}
