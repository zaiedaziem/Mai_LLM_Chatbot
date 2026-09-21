const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export async function createSession() {
  const res = await fetch(`${BASE_URL}/sessions`, { method: "POST" });
  if (!res.ok) throw new Error("Could not start a session");
  return res.json();
}

export async function listSessions() {
  const res = await fetch(`${BASE_URL}/sessions`);
  if (!res.ok) throw new Error("Could not load sessions");
  return res.json();
}

export async function renameSession(sessionId, title) {
  const res = await fetch(`${BASE_URL}/sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error("Could not rename session");
  return res.json();
}

export async function deleteSession(sessionId) {
  await fetch(`${BASE_URL}/sessions/${sessionId}`, { method: "DELETE" });
}

export async function getMessages(sessionId) {
  const res = await fetch(`${BASE_URL}/sessions/${sessionId}/messages`);
  if (!res.ok) throw new Error("Could not load history");
  return res.json();
}

/**
 * Streams one assistant reply, invoking onChunk for each token as it arrives.
 * Returns a promise that settles when the stream ends.
 */
export async function streamChat(sessionId, message, { onChunk, onDone, onError }) {
  try {
    const res = await fetch(`${BASE_URL}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message }),
    });

    if (!res.ok) {
      // Errors before streaming starts are ordinary HTTP responses (e.g. 429
      // from the rate limiter), so the detail is in the JSON body.
      const detail = await res.json().then((b) => b.detail).catch(() => null);
      const retryAfter = res.headers.get("Retry-After");
      if (res.status === 429) {
        onError(`Slow down — you've hit the rate limit. Try again in ${retryAfter ?? "a few"} seconds.`);
      } else {
        onError(detail ?? `Server responded ${res.status}`);
      }
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    // A network chunk can end mid-line, so hold the tail back until the
    // newline that completes it arrives.
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const event = JSON.parse(line.slice(6));
        if (event.error) return onError(event.error);
        if (event.done) return onDone();
        if (event.content) onChunk(event.content);
      }
    }
    onDone();
  } catch (err) {
    onError(err.message ?? String(err));
  }
}
