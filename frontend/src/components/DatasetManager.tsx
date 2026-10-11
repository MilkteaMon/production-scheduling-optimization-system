import { useState } from "react";
import { Archive, RotateCcw, Search, X } from "lucide-react";
import { api, type Dataset } from "../api/client";
import { datasetDescription, datasetMatches } from "../data/datasets";
import DialogFrame from "./DialogFrame";

export default function DatasetManager({
  datasets,
  showTests,
  onShowTests,
  onSelect,
  onChanged,
  onClose,
}: {
  datasets: Dataset[];
  showTests: boolean;
  onShowTests: (show: boolean) => void;
  onSelect: (d: Dataset) => void;
  onChanged: (d: Dataset) => void;
  onClose: () => void;
}) {
  const [search, setSearch] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const filtered = datasets.filter(
    (d) =>
      (showTests || !d.is_test) && (showArchived || !d.is_archived) && datasetMatches(d, search),
  );
  async function archive(d: Dataset) {
    setBusy(d.id);
    setError("");
    try {
      const changed = await api<Dataset>(`/datasets/${d.id}/visibility`, {
        method: "PATCH",
        body: JSON.stringify({ is_archived: !d.is_archived }),
      });
      onChanged(changed);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  }
  return (
    <DialogFrame onClose={onClose} labelledBy="datasets-title" className="modal dataset-manager">
      <div className="modal-title">
        <div>
          <span className="eyebrow">WORKLOAD LIBRARY</span>
          <h2 id="datasets-title">Manage datasets</h2>
        </div>
        <button className="icon-button" aria-label="Close dataset manager" onClick={onClose}>
          <X size={20} />
        </button>
      </div>
      <p className="dialog-intro">
        Select a workload or archive it from the default list. Jobs and saved schedules stay intact.
      </p>
      <label className="search-label">
        <Search size={16} />
        <span className="sr-only">Search datasets</span>
        <input
          placeholder="Search name, profile, seed or ID"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </label>
      <div className="library-filters">
        <label>
          <input
            type="checkbox"
            checked={showTests}
            onChange={(e) => onShowTests(e.target.checked)}
          />
          Show test data
        </label>
        <label>
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(e) => setShowArchived(e.target.checked)}
          />
          Show archived
        </label>
        <span>
          {filtered.length} of {datasets.length} datasets
        </span>
      </div>
      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}
      <div className="library-list">
        {filtered.map((d) => (
          <article className="library-row" key={d.id}>
            <div>
              <strong>{d.name}</strong>
              <p>{datasetDescription(d).split(" · ").slice(1).join(" · ")}</p>
              <p>Created {new Date(d.created_at).toLocaleString("en-GB")}</p>
              <div className="library-badges">
                <span className="badge neutral">
                  {d.source_kind === "synthetic" ? "Synthetic" : "CSV import"}
                </span>
                {d.is_test && <span className="badge warning">Test data</span>}
                {d.is_archived && <span className="badge neutral">Archived</span>}
              </div>
            </div>
            <div className="library-actions">
              <button
                className="button secondary"
                disabled={d.is_archived || busy !== null}
                aria-label={`Use dataset ${d.name} ${d.id.slice(0, 6)}`}
                onClick={() => {
                  onSelect(d);
                  onClose();
                }}
              >
                Use dataset
              </button>
              <button
                className="icon-button"
                disabled={busy !== null}
                onClick={() => archive(d)}
                aria-label={`${d.is_archived ? "Restore" : "Archive"} dataset ${d.name} ${d.id.slice(0, 6)}`}
              >
                {d.is_archived ? <RotateCcw size={17} /> : <Archive size={17} />}
              </button>
            </div>
          </article>
        ))}
        {filtered.length === 0 && (
          <p className="library-empty">
            No matching datasets. Adjust the search or visibility filters.
          </p>
        )}
      </div>
    </DialogFrame>
  );
}
