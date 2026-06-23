import { useState } from "react";
import { generateWorkflow } from "../api/client";

interface Props {
  onGenerated: (workflowId: string) => void;
}

export default function GeneratePanel({ onGenerated }: Props) {
  const [open, setOpen] = useState(false);
  const [requirement, setRequirement] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!requirement.trim()) return;
    setLoading(true);
    setError("");
    try {
      const result = await generateWorkflow(requirement.trim());
      if (result.success) {
        onGenerated(result.workflow_id);
        setRequirement("");
        setOpen(false);
      } else {
        setError(result.plan_result.errors.join("; ") || "Generation failed");
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <button className="btn-primary" onClick={() => setOpen(true)}>
        + Generate Workflow
      </button>

      {open && (
        <div className="modal-overlay" onClick={() => setOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Generate Workflow from NL</h3>
            <form onSubmit={handleSubmit}>
              <textarea
                value={requirement}
                onChange={(e) => setRequirement(e.target.value)}
                placeholder="Describe your workflow in natural language..."
                rows={4}
                autoFocus
              />
              {error && <p className="error">{error}</p>}
              <div className="modal-actions">
                <button type="button" onClick={() => setOpen(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={loading}>
                  {loading ? "Generating..." : "Generate"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
