import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import {
  createSession,
  listSessions,
  renameSession,
  deleteSession,
  getMessages,
  streamChat,
} from "./api";
import Sidebar from "./Sidebar";
import "./App.css";

export default function App() {
  const [sessions, setSessions] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const bottomRef = useRef(null);

  useEffect(() => {
    listSessions().then((existing) => {
      setSessions(existing);
      if (existing.length > 0) selectSession(existing[0].id);
    });
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  async function selectSession(id) {
    setActiveId(id);
    setInput("");
    setStreamingContent("");
    setStreaming(false);
    const msgs = await getMessages(id);
    if (Array.isArray(msgs)) setMessages(msgs);
  }

  // No database row is created here: an unused "New chat" that never receives a
  // message would otherwise linger in the sidebar forever. The session is
  // created on the first send instead.
  function startNewChat() {
    setActiveId(null);
    setMessages([]);
    setInput("");
    setStreamingContent("");
    setStreaming(false);
  }

  async function handleRename(id, title) {
    setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, title } : s)));
    await renameSession(id, title);
  }

  async function handleDelete(id) {
    const remaining = sessions.filter((s) => s.id !== id);
    setSessions(remaining);
    await deleteSession(id);

    if (id === activeId) {
      if (remaining.length > 0) {
        selectSession(remaining[0].id);
      } else {
        startNewChat();
      }
    }
  }

  async function handleSend() {
    if (!input.trim() || streaming) return;

    const userMsg = { role: "user", content: input.trim() };
    const isFirstMessage = messages.length === 0;
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setStreaming(true);
    setStreamingContent("");

    let sessionId = activeId;
    if (!sessionId) {
      ({ session_id: sessionId } = await createSession());
      setActiveId(sessionId);
    }

    let reply = "";
    streamChat(sessionId, userMsg.content, {
      onChunk: (token) => {
        reply += token;
        setStreamingContent(reply);
      },
      onDone: () => {
        setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
        setStreamingContent("");
        setStreaming(false);
        // The backend auto-titles a session from its first message; pull the
        // real title back so the sidebar doesn't keep showing "New chat".
        if (isFirstMessage) {
          listSessions().then(setSessions);
        }
      },
      onError: (err) => {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: `⚠️ ${err}`, failed: true },
        ]);
        setStreamingContent("");
        setStreaming(false);
      },
    });
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="app-layout">
      <Sidebar
        sessions={sessions}
        activeId={activeId}
        onSelect={selectSession}
        onNewChat={startNewChat}
        onRename={handleRename}
        onDelete={handleDelete}
      />

      <div className="app">
        <header className="header">
          <div className="header-title">
            <span className="logo">⚡</span>
            <span>LLM Chat</span>
            <span className="model-badge">gpt-oss-20b</span>
          </div>
        </header>

        <main className="chat-window">
          {messages.length === 0 && !streaming && (
            <div className="empty-state">
              <div className="empty-icon">💬</div>
              <p>Start a conversation</p>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`message ${msg.role}${msg.failed ? " failed" : ""}`}>
              <div className="avatar">{msg.role === "user" ? "U" : "AI"}</div>
              <div className="bubble">
                <ReactMarkdown>{msg.content}</ReactMarkdown>
              </div>
            </div>
          ))}

          {streaming && (
            <div className="message assistant">
              <div className="avatar">AI</div>
              <div className="bubble">
                {streamingContent ? (
                  <ReactMarkdown>{streamingContent}</ReactMarkdown>
                ) : (
                  <span className="typing-dots">
                    <span /><span /><span />
                  </span>
                )}
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </main>

        <footer className="input-area">
          <textarea
            className="input-box"
            placeholder="Type a message… (Enter to send, Shift+Enter for newline)"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            disabled={streaming}
          />
          <button
            className="send-btn"
            onClick={handleSend}
            disabled={streaming || !input.trim()}
          >
            {streaming ? "…" : "Send"}
          </button>
        </footer>
      </div>
    </div>
  );
}
