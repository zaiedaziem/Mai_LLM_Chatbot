import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import { createSession, getMessages, streamChat, clearSession } from "./api";
import "./App.css";

export default function App() {
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState("");
  const bottomRef = useRef(null);

  useEffect(() => {
    const saved = localStorage.getItem("session_id");
    if (saved) {
      setSessionId(saved);
      getMessages(saved).then((msgs) => {
        if (Array.isArray(msgs)) setMessages(msgs);
      });
    } else {
      createSession().then(({ session_id }) => {
        localStorage.setItem("session_id", session_id);
        setSessionId(session_id);
      });
    }
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  function handleSend() {
    if (!input.trim() || streaming || !sessionId) return;

    const userMsg = { role: "user", content: input.trim() };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setStreaming(true);
    setStreamingContent("");

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

  async function handleNewChat() {
    if (sessionId) await clearSession(sessionId);
    localStorage.removeItem("session_id");
    const { session_id } = await createSession();
    localStorage.setItem("session_id", session_id);
    setSessionId(session_id);
    setMessages([]);
    setInput("");
    setStreamingContent("");
  }

  return (
    <div className="app">
      <header className="header">
        <div className="header-title">
          <span className="logo">⚡</span>
          <span>LLM Chat</span>
          <span className="model-badge">gpt-oss-20b</span>
        </div>
        <button className="new-chat-btn" onClick={handleNewChat}>
          + New Chat
        </button>
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
  );
}
