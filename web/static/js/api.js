/** Thin fetch helpers for /api/aria */

export async function getStatus() {
  const r = await fetch("/api/aria/status");
  if (!r.ok) throw new Error("status failed");
  return r.json();
}

export async function createSession(mode = "text") {
  const r = await fetch(`/api/aria/session?mode=${encodeURIComponent(mode)}`, {
    method: "POST",
  });
  if (!r.ok) throw new Error("Could not start session");
  return r.json();
}

export async function persistSession(callContext, conversationId, durationSeconds) {
  await fetch("/api/aria/session/persist", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      call_context: callContext,
      conversation_id: conversationId || null,
      duration_seconds: durationSeconds ?? null,
    }),
  });
}

export async function listConversations({ mode, q, limit = 50 } = {}) {
  const params = new URLSearchParams();
  if (mode) params.set("mode", mode);
  if (q) params.set("q", q);
  params.set("limit", String(limit));
  const r = await fetch(`/api/aria/conversations?${params}`);
  if (!r.ok) throw new Error("list failed");
  return r.json();
}

export async function getConversation(id) {
  const r = await fetch(`/api/aria/conversations/${encodeURIComponent(id)}`);
  if (!r.ok) throw new Error("not found");
  return r.json();
}

export async function renameConversation(id, title) {
  const r = await fetch(`/api/aria/conversations/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!r.ok) throw new Error("rename failed");
  return r.json();
}

export async function archiveConversation(id) {
  const r = await fetch(`/api/aria/conversations/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!r.ok) throw new Error("archive failed");
  return r.json();
}

export async function getOps() {
  const r = await fetch("/api/aria/ops");
  if (!r.ok) throw new Error("ops failed");
  return r.json();
}

export async function listAppointments({ status, limit = 50 } = {}) {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  params.set("limit", String(limit));
  const r = await fetch(`/api/aria/appointments?${params}`);
  if (!r.ok) throw new Error("appointments failed");
  return r.json();
}

export async function getAppointment(id) {
  const r = await fetch(`/api/aria/appointments/${encodeURIComponent(id)}`);
  if (!r.ok) throw new Error("not found");
  return r.json();
}

export async function streamChat({
  message,
  callContext,
  history,
  conversationId,
  onDelta,
  onStatus,
  onDone,
  onTitle,
  signal,
}) {
  const r = await fetch("/api/aria/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      call_context: callContext,
      history,
      conversation_id: conversationId || null,
    }),
    signal,
  });
  if (!r.ok || !r.body) throw new Error("Chat stream failed");

  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  while (true) {
    if (signal?.aborted) {
      try {
        await reader.cancel();
      } catch {
        /* ignore */
      }
      throw new DOMException("Aborted", "AbortError");
    }
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop() || "";
    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data:")) continue;
      const json = JSON.parse(line.slice(5).trim());
      if (json.type === "delta") onDelta?.(json.text || "");
      else if (json.type === "status") onStatus?.(json.status);
      else if (json.type === "done") {
        onDone?.(json);
        // Voice callers omit onTitle — return immediately so TTS can drain.
        // Text callers keep reading for the follow-up title event.
        if (!onTitle) {
          try {
            await reader.cancel();
          } catch {
            /* ignore */
          }
          return;
        }
      } else if (json.type === "title") {
        onTitle?.(json.title || "");
        return;
      } else if (json.type === "error") throw new Error(json.message || "Agent error");
    }
  }
}

export async function chatTurn({
  message,
  callContext,
  history,
  conversationId,
  signal,
}) {
  const r = await fetch("/api/aria/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      call_context: callContext,
      history,
      conversation_id: conversationId || null,
    }),
    signal,
  });
  if (!r.ok) throw new Error("Chat failed");
  return r.json();
}

export async function transcribeBlob(blob, filename = "utterance.webm", signal) {
  const fd = new FormData();
  fd.append("file", blob, filename);
  const r = await fetch("/api/aria/transcribe", { method: "POST", body: fd, signal });
  if (!r.ok) throw new Error("Transcription failed");
  const data = await r.json();
  return data.text || "";
}

export async function speakText(text, signal) {
  const r = await fetch("/api/aria/speak", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
    signal,
  });
  if (!r.ok) throw new Error("TTS failed");
  return r.blob();
}
