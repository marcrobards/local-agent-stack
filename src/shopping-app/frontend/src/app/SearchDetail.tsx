import { useState, useEffect, useCallback, useRef } from "react";
import { ClarifyChat } from "./ClarifyChat";
import { ProductCard } from "./ProductCard";
import { api } from "./api";

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface Product {
  name: string;
  price: string;
  store: string;
  image_url: string | null;
  product_url: string;
}

interface SearchData {
  id: string;
  status: string;
  spec: Record<string, unknown> | null;
  messages: Message[];
  results: Product[];
  error: string | null;
}

const SEARCHING_MESSAGES = [
  "Browsing stores…",
  "Finding products…",
  "Comparing prices…",
  "Almost there…",
];

export function SearchDetail({
  searchId,
  onBack,
}: {
  searchId: string;
  onBack: () => void;
}) {
  const [data, setData] = useState<SearchData | null>(null);
  const [loading, setLoading] = useState(true);
  const [confirming, setConfirming] = useState(false);
  const [searchingMsgIdx, setSearchingMsgIdx] = useState(0);
  const [specExpanded, setSpecExpanded] = useState(true);
  const [refineText, setRefineText] = useState("");
  const [refining, setRefining] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const result = await api<SearchData>(`/searches/${searchId}`);
      setData(result);
    } catch {
      // keep existing data on error
    } finally {
      setLoading(false);
    }
  }, [searchId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Poll when searching
  useEffect(() => {
    if (data?.status !== "searching") {
      if (pollRef.current) clearInterval(pollRef.current);
      return;
    }

    pollRef.current = setInterval(async () => {
      try {
        const status = await api<{ status: string }>(
          `/searches/${searchId}/status`
        );
        if (status.status !== "searching") {
          fetchData();
        }
      } catch {
        // ignore polling errors
      }
    }, 10000);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [data?.status, searchId, fetchData]);

  // Cycle searching messages
  useEffect(() => {
    if (data?.status !== "searching") return;
    const interval = setInterval(() => {
      setSearchingMsgIdx((i) => (i + 1) % SEARCHING_MESSAGES.length);
    }, 3000);
    return () => clearInterval(interval);
  }, [data?.status]);

  const handleConfirm = async () => {
    if (confirming) return;
    setConfirming(true);
    try {
      await api(`/searches/${searchId}/confirm`, { method: "POST" });
      await fetchData();
    } finally {
      setConfirming(false);
    }
  };

  const handleRefine = async () => {
    if (!refineText.trim() || refining) return;
    setRefining(true);
    try {
      await api(`/searches/${searchId}/refine`, {
        method: "POST",
        body: JSON.stringify({ content: refineText.trim() }),
      });
      setRefineText("");
      await fetchData();
    } finally {
      setRefining(false);
    }
  };

  if (loading || !data) {
    return (
      <>
        <div className="header">
          <button className="header-back" onClick={onBack}>
            Back
          </button>
        </div>
        <div className="loading">
          <div className="spinner" />
        </div>
      </>
    );
  }

  const specDescription =
    data.spec && typeof data.spec.item_description === "string"
      ? data.spec.item_description
      : null;

  // ── Clarifying ──
  if (data.status === "clarifying") {
    return (
      <div className="detail-container">
        <div className="header">
          <button className="header-back" onClick={onBack}>
            Back
          </button>
          <div className="detail-header-actions">
            <button
              className={`btn-primary ${data.spec ? "btn-highlight" : ""}`}
              onClick={handleConfirm}
              disabled={confirming}
            >
              {confirming ? "Starting…" : "Search for this →"}
            </button>
          </div>
        </div>
        <ClarifyChat
          searchId={searchId}
          messages={data.messages || []}
          onMessageSent={fetchData}
        />
      </div>
    );
  }

  // ── Searching ──
  if (data.status === "searching") {
    return (
      <div className="detail-container">
        <div className="header">
          <button className="header-back" onClick={onBack}>
            Back
          </button>
        </div>
        {specDescription && (
          <div className="spec-card">
            <div className="spec-card-body">
              <p>{specDescription}</p>
            </div>
          </div>
        )}
        <div className="loading">
          <div className="spinner" />
          <span className="loading-text">
            {SEARCHING_MESSAGES[searchingMsgIdx]}
          </span>
        </div>
      </div>
    );
  }

  // ── Failed ──
  if (data.status === "failed") {
    return (
      <div className="detail-container">
        <div className="header">
          <button className="header-back" onClick={onBack}>
            Back
          </button>
        </div>
        <div className="error-state">
          <div className="error-state-emoji">😔</div>
          <p className="error-state-text">
            Something went wrong with this search.
            {data.error && <><br /><small>{data.error}</small></>}
          </p>
          <button className="btn-primary" onClick={handleConfirm}>
            Try again
          </button>
        </div>
      </div>
    );
  }

  // ── Complete (results) ──
  return (
    <div className="detail-container">
      <div className="header">
        <button className="header-back" onClick={onBack}>
          Back
        </button>
      </div>
      <div className="detail-body">
        {specDescription && (
          <div className="spec-card">
            <div
              className="spec-card-header"
              onClick={() => setSpecExpanded(!specExpanded)}
            >
              <h3>What you searched for</h3>
              <button className="spec-card-toggle">
                {specExpanded ? "▲" : "▼"}
              </button>
            </div>
            {specExpanded && (
              <div className="spec-card-body">
                <p>{specDescription}</p>
              </div>
            )}
          </div>
        )}

        {data.results && data.results.length > 0 ? (
          <div className="product-grid">
            {data.results.map((p, i) => (
              <ProductCard key={i} product={p} />
            ))}
          </div>
        ) : (
          <div className="empty-state">
            <div className="empty-state-emoji">🔍</div>
            <p className="empty-state-text">No products found.</p>
          </div>
        )}

        <div className="refine-section">
          <p className="refine-label">Not quite right? Tell me more:</p>
          <div className="refine-row">
            <input
              type="text"
              value={refineText}
              onChange={(e) => setRefineText(e.target.value)}
              placeholder="e.g. cheaper options, different color…"
              onKeyDown={(e) => {
                if (e.key === "Enter") handleRefine();
              }}
            />
            <button
              className="btn-primary"
              onClick={handleRefine}
              disabled={refining || !refineText.trim()}
            >
              {refining ? "…" : "Send"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
