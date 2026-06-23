/** TypeScript types matching the AgentIR backend API responses. */

export interface WorkflowListItem {
  workflow_id: string;
  name: string;
  description: string;
  requirement: string;
  created_at: string;
  status: "generated" | "running" | "completed" | "failed";
  elapsed_ms: number;
  error: string;
}

export interface WorkflowListResponse {
  total: number;
  offset: number;
  limit: number;
  items: WorkflowListItem[];
}

export interface WorkflowDetailResponse {
  workflow_id: string;
  name: string;
  description: string;
  requirement: string;
  created_at: string;
  status: string;
  elapsed_ms: number;
  error: string;
  agentir_json: AgentIR | null;
}

export interface WorkflowGenerateResponse {
  workflow_id: string;
  success: boolean;
  plan_result: {
    success: boolean;
    workflow_name: string;
    workflow_version: string;
    workflow_description: string;
    retries: number;
    errors: string[];
  };
  agentir_json: AgentIR | null;
  validation_report: {
    is_valid: boolean;
    error_count: number;
    warning_count: number;
    errors: Record<string, unknown>[];
    warnings: Record<string, unknown>[];
  };
  adk_source_code: string | null;
  compilation_errors: string[];
  elapsed_ms: number;
}

export interface NodeLogEntry {
  node: string;
  kind: string;
  event: "start" | "end";
  data: string;
}

export interface WorkflowRunResponse {
  success: boolean;
  workflow_id: string;
  exit_code: number;
  stdout: string;
  stderr: string;
  node_logs: NodeLogEntry[];
  log_path: string;
  started_at: string;
  finished_at: string;
  elapsed_ms: number;
  errors: string[];
}

export interface RunRecord {
  run_id: string;
  workflow_id: string;
  started_at: string;
  finished_at: string;
  elapsed_ms: number;
  success: boolean;
  exit_code: number;
  node_logs: NodeLogEntry[];
  log_path: string;
  error: string;
}

export interface RunHistoryResponse {
  workflow_id: string;
  runs: RunRecord[];
}

export interface ToolInfo {
  name: string;
  function: string;
  description: string;
  input_params: Record<string, string>;
  output_type: string;
  path: string;
}

// ---- AgentIR Schema types ----

export type IRNode = AgentIRNode | SequenceIRNode | ParallelIRNode | ConditionIRNode | LoopIRNode | ToolIRNode;

export interface AgentIR {
  name: string;
  version: string;
  description: string;
  root: IRNode;
}

export interface AgentIRNode {
  type: "agent";
  agent: string;
}

export interface SequenceIRNode {
  type: "sequence";
  steps: IRNode[];
}

export interface ParallelIRNode {
  type: "parallel";
  branches: IRNode[];
}

export interface ConditionIRNode {
  type: "condition";
  expression: string;
  true_branch: IRNode;
  false_branch: IRNode;
}

export interface LoopIRNode {
  type: "loop";
  max_iterations: number;
  body: IRNode;
}

export interface ToolIRNode {
  type: "tool";
  tool: string;
}

// ---- ReactFlow types ----

export interface FlowNode {
  id: string;
  type: string;
  position: { x: number; y: number };
  data: {
    label: string;
    kind: string;
  };
}

export interface FlowEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
  animated?: boolean;
  style?: Record<string, string | number>;
}
