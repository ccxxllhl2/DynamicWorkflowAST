import { useState, useEffect, useCallback } from "react";
import { listWorkflows, getWorkflow } from "./api/client";
import type { WorkflowListItem, WorkflowDetailResponse } from "./types";
import WorkflowGraph from "./components/WorkflowGraph";
import RunPanel from "./components/RunPanel";
import GeneratePanel from "./components/GeneratePanel";
import "./App.css";

export default function App() {
  const [workflows, setWorkflows] = useState<WorkflowListItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<WorkflowDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const loadList = useCallback(async () => {
    try {
      const data = await listWorkflows();
      setWorkflows(data.items);
    } catch {
      // backend not reachable
    }
  }, []);

  useEffect(() => {
    loadList();
  }, [loadList]);

  useEffect(() => {
    if (selectedId) {
      setLoading(true);
      getWorkflow(selectedId)
        .then(setDetail)
        .catch(() => setDetail(null))
        .finally(() => setLoading(false));
    } else {
      setDetail(null);
    }
  }, [selectedId]);

  function handleGenerated(workflowId: string) {
    loadList();
    setSelectedId(workflowId);
  }

  return (
    <div className="app">
      <header className="header">
        <h1>AgentIR — Workflow Dashboard</h1>
        <GeneratePanel onGenerated={handleGenerated} />
      </header>

      <div className="main">
        <aside className="sidebar">
          <h2>Workflows</h2>
          {workflows.length === 0 ? (
            <p className="hint">No workflows yet. Click "+ Generate Workflow" to create one.</p>
          ) : (
            <ul className="wf-list">
              {workflows.map((wf) => (
                <li
                  key={wf.workflow_id}
                  className={`wf-item ${selectedId === wf.workflow_id ? "selected" : ""}`}
                  onClick={() => setSelectedId(wf.workflow_id)}
                >
                  <div className="wf-name">{wf.name || wf.workflow_id}</div>
                  <div className="wf-meta">
                    <span className={`status-tag status-${wf.status}`}>{wf.status}</span>
                    <span className="wf-date">{wf.created_at.slice(0, 10)}</span>
                  </div>
                  {wf.error && <div className="wf-error">{wf.error}</div>}
                </li>
              ))}
            </ul>
          )}
        </aside>

        <section className="content">
          {loading && <div className="loading">Loading...</div>}
          {!selectedId && !loading && (
            <div className="empty-state">
              <p>Select a workflow from the sidebar, or generate a new one.</p>
            </div>
          )}
          {detail && detail.agentir_json && (
            <>
              <div className="graph-section">
                <WorkflowGraph ir={detail.agentir_json.root} />
              </div>
              <RunPanel workflowId={detail.workflow_id} status={detail.status} />
            </>
          )}
          {detail && !detail.agentir_json && (
            <div className="empty-state">
              <p>Workflow "{detail.name}" has no AgentIR data.</p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
