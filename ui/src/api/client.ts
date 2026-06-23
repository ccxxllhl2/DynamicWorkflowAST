/** API client for the AgentIR backend. */

const API_BASE = "http://localhost:8000/api/v1";

import type {
  WorkflowListResponse,
  WorkflowDetailResponse,
  WorkflowGenerateResponse,
  WorkflowRunResponse,
  RunHistoryResponse,
  ToolInfo,
} from "../types";

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, options);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

export function listWorkflows(offset = 0, limit = 50): Promise<WorkflowListResponse> {
  return request<WorkflowListResponse>(`/workflows?offset=${offset}&limit=${limit}`);
}

export function getWorkflow(workflowId: string): Promise<WorkflowDetailResponse> {
  return request<WorkflowDetailResponse>(`/workflows/${workflowId}`);
}

export function generateWorkflow(
  requirement: string,
  options?: Record<string, unknown>
): Promise<WorkflowGenerateResponse> {
  return request<WorkflowGenerateResponse>("/workflows/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ requirement, options }),
  });
}

export function runWorkflow(
  workflowId: string,
  inputText = "",
  timeoutSeconds = 300
): Promise<WorkflowRunResponse> {
  return request<WorkflowRunResponse>(`/workflows/${workflowId}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ input_text: inputText, timeout_seconds: timeoutSeconds }),
  });
}

export function getRunHistory(workflowId: string): Promise<RunHistoryResponse> {
  return request<RunHistoryResponse>(`/workflows/${workflowId}/runs`);
}

export function listTools(): Promise<ToolInfo[]> {
  return request<ToolInfo[]>("/tools");
}
