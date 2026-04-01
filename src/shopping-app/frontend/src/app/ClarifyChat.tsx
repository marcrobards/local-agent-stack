import { useState, useRef, useEffect } from "react";
import { api } from "./api";

interface Message {
  role: "user" | "assistant";
  content: string;
}

export function ClarifyChat({
  searchId,
  messages,
  onMessageSent,
}: {
  searchId: string;
  messages: Message[];
  onMessageSent: () => void;
}) {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const threadRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [messages]);

  const send = async () => {
    if (!text.trim() || sending) return;
    const content = text.trim();
    setText("");
    setSending(true);
    try {
      await api(`/searches/${searchId}/messages`, {
        method: "POST",
        body: JSON.stringify({ content }),
      });
      onMessageSent();
    } finally {
      setSending(false);
    }
  };

  return (
    <>
      <div className="chat-thread" ref={threadRef}>
        {messages.length === 0 && (
          <div className="empty-state">
            <div className="empty-state-emoji">💬</div>
            <p className="empty-state-text">
              Describe what you're looking for and I'll help narrow it down.
            </p>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`message ${m.role}`}>
            {m.content}
          </div>
        ))}
      </div>
      <div className="chat-input">
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Describe what you're looking for…"
          onKeyDown={(e) => {
            if (e.key === "Enter") send();
          }}
          disabled={sending}
        />
        <button
          className="btn-primary"
          onClick={send}
          disabled={sending || !text.trim()}
        >
          {sending ? "…" : "Send"}
        </button>
      </div>
    </>
  );
}
