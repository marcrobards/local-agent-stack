import { useState, useEffect } from "react";
import { api } from "./api";

interface Search {
  id: string;
  status: string;
  spec: Record<string, unknown> | null;
  created_at: string;
}

function timeAgo(date: string): string {
  const seconds = Math.floor((Date.now() - new Date(date).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function statusLabel(status: string): string {
  switch (status) {
    case "searching":
      return "Searching…";
    case "complete":
      return "Done";
    case "failed":
      return "Failed";
    case "clarifying":
      return "Clarifying";
    default:
      return status;
  }
}

function specSummary(spec: Record<string, unknown> | null): string {
  if (!spec) return "New search";
  if (typeof spec.item_description === "string" && spec.item_description) {
    return spec.item_description;
  }
  return "New search";
}

export function SearchList({
  onOpenSearch,
}: {
  onOpenSearch: (id: string) => void;
}) {
  const [searches, setSearches] = useState<Search[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    api<Search[]>("/searches")
      .then(setSearches)
      .catch(() => setSearches([]))
      .finally(() => setLoading(false));
  }, []);

  const createSearch = async () => {
    if (creating) return;
    setCreating(true);
    try {
      const result = await api<{ id: string }>("/searches", {
        method: "POST",
      });
      onOpenSearch(result.id);
    } catch {
      setCreating(false);
    }
  };

  const sorted = [...searches].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );

  return (
    <>
      <div className="header">
        <h1>Shopping</h1>
        <button
          className="btn-primary"
          onClick={createSearch}
          disabled={creating}
        >
          {creating ? "Creating…" : "New Search"}
        </button>
      </div>

      {loading ? (
        <div className="loading">
          <div className="spinner" />
        </div>
      ) : sorted.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-emoji">🛍️</div>
          <p className="empty-state-text">
            No searches yet.
            <br />
            Tap New Search to get started!
          </p>
        </div>
      ) : (
        <div className="search-list">
          {sorted.map((s) => (
            <div
              key={s.id}
              className="search-row"
              onClick={() => onOpenSearch(s.id)}
            >
              <div className="search-row-content">
                <div className="search-row-top">
                  <span className="search-row-time">
                    {timeAgo(s.created_at)}
                  </span>
                  <span className={`status-badge ${s.status}`}>
                    {statusLabel(s.status)}
                  </span>
                </div>
                <div className="search-row-summary">
                  {specSummary(s.spec)}
                </div>
              </div>
              <span className="search-row-arrow">›</span>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
