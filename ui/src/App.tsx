import { useState, useEffect, useCallback } from "react";
import { listWorkflows, getWorkflow, updateWorkflowIR } from "./api/client";
import type {
  WorkflowListItem,
  WorkflowDetailResponse,
  SelectedNode,
  IRNode,
} from "./types";
import { useUndoRedo } from "./utils/useUndoRedo";
import WorkflowGraph from "./components/WorkflowGraph";
import RunPanel from "./components/RunPanel";
import GeneratePanel from "./components/GeneratePanel";
import PropertyPanel from "./components/PropertyPanel";
import "./App.css";

export default function App() {
  const [workflows, setWorkflows] = useState<WorkflowListItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<WorkflowDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);

  // Phase 3: editing state with undo/redo
  const irHistory = useUndoRedo<IRNode | null>(null);
  const [selectedNode, setSelectedNode] = useState<SelectedNode | null>(null);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [saveError, setSaveError] = useState("");
  const [showDiff, setShowDiff] = useState(false);

  const editingIR = irHistory.value;

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
        .then((d) => {
          setDetail(d);
          if (d.agentir_json?.root) {
            const root = d.agentir_json.root as IRNode;
            irHistory.resetHistory(root);
          } else {
            irHistory.resetHistory(null);
          }
          setSelectedNode(null);
          setSaveStatus("idle");
          setSaveError("");
          setShowDiff(false);
        })
        .catch(() => {
          setDetail(null);
          irHistory.resetHistory(null);
        })
        .finally(() => setLoading(false));
    } else {
      setDetail(null);
      irHistory.resetHistory(null);
      setSelectedNode(null);
    }
  }, [selectedId]);

  function handleGenerated(workflowId: string) {
    loadList();
    setSelectedId(workflowId);
  }

  function handleIRChange(newRoot: IRNode) {
    irHistory.pushState(newRoot);
  }

  function handleRegenerateGraph() {
    if (editingIR) {
      irHistory.pushState({ ...editingIR });
    }
  }

  function handleUndo() {
    irHistory.undo();
  }

  function handleRedo() {
    irHistory.redo();
  }

  function handleShowDiff() {
    if (!editingIR || !detail?.agentir_json?.root) return;
    setShowDiff(true);
  }

  async function handleSave() {
    if (!selectedId || !editingIR || !detail?.agentir_json) return;

    setSaveStatus("saving");
    setSaveError("");

    const updatedAgentIR = {
      ...detail.agentir_json,
      root: editingIR,
    };

    try {
      const result = await updateWorkflowIR(selectedId, {
        agentir_json: updatedAgentIR as Record<string, unknown>,
      });

      if (result.success) {
        setSaveStatus("saved");
        const newDetail = await getWorkflow(selectedId);
        setDetail(newDetail);
        if (newDetail.agentir_json?.root) {
          irHistory.resetHistory(newDetail.agentir_json.root as IRNode);
        }
        setShowDiff(false);
        setTimeout(() => setSaveStatus("idle"), 2000);
      } else {
        const errs = [
          ...(result.validation_report?.errors?.map((e) => JSON.stringify(e)) ?? []),
          ...(result.compilation_errors ?? []),
        ].join("; ");
        setSaveError(errs || "Update failed");
        setSaveStatus("error");
      }
    } catch (err) {
      setSaveError(String(err));
      setSaveStatus("error");
    }
  }

  const hasIR = !!(detail?.agentir_json?.root && editingIR);
  const originalIR = detail?.agentir_json?.root as IRNode | undefined;

  // Keyboard shortcuts
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key === "z" && !e.shiftKey) {
        e.preventDefault();
        irHistory.undo();
      } else if (mod && (e.key === "y" || (e.key === "z" && e.shiftKey))) {
        e.preventDefault();
        irHistory.redo();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [irHistory.undo, irHistory.redo]);

  return (
    <div className="app">
      <header className="header">
        <h1>AgentIR — Workflow Dashboard</h1>
        <div className="header-actions">
          {hasIR && (
            <>
              <button
                className="btn-icon"
                onClick={handleUndo}
                disabled={!irHistory.canUndo}
                title="Undo (Ctrl+Z)"
              >
                ↩
              </button>
              <button
                className="btn-icon"
                onClick={handleRedo}
                disabled={!irHistory.canRedo}
                title="Redo (Ctrl+Y)"
              >
                ↪
              </button>
              <button className="btn-outline" onClick={handleShowDiff} title="Preview changes">
                Diff
              </button>
              <button
                className="btn-primary btn-save"
                onClick={handleSave}
                disabled={saveStatus === "saving"}
              >
                {saveStatus === "saving"
                  ? "Saving..."
                  : saveStatus === "saved"
                    ? "✓ Saved"
                    : "Save Changes"}
              </button>
            </>
          )}
          <GeneratePanel onGenerated={handleGenerated} />
        </div>
      </header>

      <div className="main">
        <aside className="sidebar">
          <h2>Workflows</h2>
          {workflows.length === 0 ? (
            <p className="hint">
              No workflows yet. Click "+ Generate Workflow" to create one.
            </p>
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
                    <span className={`status-tag status-${wf.status}`}>
                      {wf.status}
                    </span>
                    <span className="wf-date">
                      {wf.created_at.slice(0, 10)}
                    </span>
                  </div>
                  {wf.error && <div className="wf-error">{wf.error}</div>}
                </li>
              ))}
            </ul>
          )}
        </aside>

        <section className="content">
          {saveStatus === "error" && saveError && (
            <div className="save-error-bar">
              <span>⚠ Save failed: {saveError}</span>
              <button onClick={() => setSaveStatus("idle")}>✕</button>
            </div>
          )}

          {loading && <div className="loading">Loading...</div>}
          {!selectedId && !loading && (
            <div className="empty-state">
              <p>Select a workflow from the sidebar, or generate a new one.</p>
            </div>
          )}

          {detail && editingIR && (
            <>
              <div className="graph-with-panel">
                <div className="graph-section">
                  <WorkflowGraph
                    ir={editingIR}
                    onNodeSelect={setSelectedNode}
                  />
                </div>
                <PropertyPanel
                  selected={selectedNode}
                  rootIR={editingIR}
                  onIRChange={handleIRChange}
                  onClearSelection={() => setSelectedNode(null)}
                  onRegenerateGraph={handleRegenerateGraph}
                />
              </div>
              <RunPanel
                workflowId={detail.workflow_id}
                status={detail.status}
              />
            </>
          )}

          {detail && !editingIR && !loading && (
            <div className="empty-state">
              <p>Workflow "{detail.name}" has no AgentIR data.</p>
            </div>
          )}
        </section>
      </div>

      {/* IR Diff Modal */}
      {showDiff && editingIR && originalIR && (
        <div className="modal-overlay" onClick={() => setShowDiff(false)}>
          <div className="modal diff-modal" onClick={(e) => e.stopPropagation()}>
            <div className="diff-header">
              <h3>Changes Preview</h3>
              <button className="btn-close" onClick={() => setShowDiff(false)}>✕</button>
            </div>
            <div className="diff-body">
              <div className="diff-pane">
                <h4>Original (saved)</h4>
                <pre>{JSON.stringify(originalIR, null, 2)}</pre>
              </div>
              <div className="diff-pane">
                <h4>Modified (current)</h4>
                <pre>{JSON.stringify(editingIR, null, 2)}</pre>
              </div>
            </div>
            <div className="modal-actions">
              <button onClick={() => setShowDiff(false)}>Close</button>
              <button className="btn-primary" onClick={() => { setShowDiff(false); handleSave(); }}>
                Save Changes
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
