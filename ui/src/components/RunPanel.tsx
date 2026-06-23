import { useState, useEffect } from "react";
import { runWorkflow, getRunHistory } from "../api/client";
import type { RunRecord, NodeLogEntry } from "../types";

interface Props {
  workflowId: string;
  status: string;
}

export default function RunPanel({ workflowId, status }: Props) {
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [expandedRun, setExpandedRun] = useState<string | null>(null);

  useEffect(() => {
    if (workflowId) {
      loadRuns();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workflowId]);

  async function loadRuns() {
    try {
      const h = await getRunHistory(workflowId);
      setRuns(h.runs);
    } catch {
      // no runs yet
    }
  }

  async function handleRun() {
    setRunning(true);
    setError("");
    try {
      await runWorkflow(workflowId);
      await loadRuns();
    } catch (err) {
      setError(String(err));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="run-panel">
      <div className="run-header">
        <h3>Run History</h3>
        <button
          className="btn-primary"
          onClick={handleRun}
          disabled={running || status === "running"}
        >
          {running ? "▶ Running..." : "▶ Run Workflow"}
        </button>
        {error && <p className="error">{error}</p>}
      </div>

      {runs.length === 0 ? (
        <p className="hint">No runs yet. Click "Run Workflow" to execute.</p>
      ) : (
        <div className="run-list">
          {runs.map((run) => (
            <div
              key={run.run_id}
              className={`run-item ${run.success ? "run-success" : "run-fail"}`}
            >
              <div
                className="run-summary"
                onClick={() =>
                  setExpandedRun(expandedRun === run.run_id ? null : run.run_id)
                }
              >
                <span className="run-badge">{run.success ? "✅" : "❌"}</span>
                <span className="run-time">
                  {run.started_at.slice(11, 19)} — {run.elapsed_ms.toFixed(0)}ms
                </span>
                {run.error && <span className="run-error-msg">{run.error}</span>}
              </div>

              {expandedRun === run.run_id && (
                <div className="run-logs">
                  <NodeLogTable logs={run.node_logs} />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function NodeLogTable({ logs }: { logs: NodeLogEntry[] }) {
  if (logs.length === 0) return <p className="hint">No node logs captured.</p>;

  return (
    <table className="log-table">
      <thead>
        <tr>
          <th>Node</th>
          <th>Kind</th>
          <th>Event</th>
          <th>Data</th>
        </tr>
      </thead>
      <tbody>
        {logs.map((l, i) => (
          <tr key={i} className={l.event === "start" ? "row-start" : "row-end"}>
            <td><strong>{l.node}</strong></td>
            <td className="kind-tag">{l.kind}</td>
            <td>{l.event}</td>
            <td className="data-cell">{l.data || "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
