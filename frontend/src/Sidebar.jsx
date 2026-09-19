import { useState } from "react";

export default function Sidebar({
  sessions,
  activeId,
  onSelect,
  onNewChat,
  onRename,
  onDelete,
}) {
  const [editingId, setEditingId] = useState(null);
  const [draft, setDraft] = useState("");

  function startEditing(session) {
    setEditingId(session.id);
    setDraft(session.title || "New chat");
  }

  function commitRename(session) {
    const title = draft.trim();
    setEditingId(null);
    if (title && title !== session.title) onRename(session.id, title);
  }

  return (
    <aside className="sidebar">
      <button className="new-chat-btn sidebar-new-chat" onClick={onNewChat}>
        + New Chat
      </button>

      <div className="session-list">
        {sessions.length === 0 && (
          <div className="session-list-empty">No conversations yet</div>
        )}

        {sessions.map((session) => (
          <div
            key={session.id}
            className={`session-item ${session.id === activeId ? "active" : ""}`}
            onClick={() => editingId !== session.id && onSelect(session.id)}
          >
            {editingId === session.id ? (
              <input
                className="session-rename-input"
                value={draft}
                autoFocus
                onChange={(e) => setDraft(e.target.value)}
                onClick={(e) => e.stopPropagation()}
                onBlur={() => commitRename(session)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commitRename(session);
                  if (e.key === "Escape") setEditingId(null);
                }}
              />
            ) : (
              <>
                <span className="session-title">
                  {session.title || "New chat"}
                </span>
                <div className="session-actions">
                  <button
                    className="session-action-btn"
                    title="Rename"
                    onClick={(e) => {
                      e.stopPropagation();
                      startEditing(session);
                    }}
                  >
                    ✎
                  </button>
                  <button
                    className="session-action-btn"
                    title="Delete"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(session.id);
                    }}
                  >
                    ✕
                  </button>
                </div>
              </>
            )}
          </div>
        ))}
      </div>
    </aside>
  );
}
