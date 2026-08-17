import {
  archiveConversation,
  getConversation,
  listConversations,
} from "./api.js";
import { pageShell } from "./shell.js";

function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function fmtDuration(sec) {
  if (!sec && sec !== 0) return "";
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}m ${String(s).padStart(2, "0")}s`;
}

function fmtWhen(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export async function renderHistory(root, { go }, openId = null) {
  if (openId) {
    await renderDetail(root, { go }, openId);
    return;
  }

  root.innerHTML = pageShell(
    "history",
    "History",
    "Text chats and voice session transcripts.",
    `<div class="hist-toolbar">
      <input class="side-search" id="search" type="search" placeholder="Search title or transcript" />
      <div class="hist-filters">
        <button class="chip active" data-mode="">All</button>
        <button class="chip" data-mode="text">Text</button>
        <button class="chip" data-mode="voice">Voice</button>
      </div>
    </div>
    <div id="list"><div class="empty">Loading…</div></div>`
  );

  const list = root.querySelector("#list");
  const search = root.querySelector("#search");
  let mode = "";

  async function refresh() {
    try {
      const rows = await listConversations({
        mode: mode || undefined,
        q: search.value.trim() || undefined,
      });
      if (!rows.length) {
        list.innerHTML = `
          <div class="empty">Your conversations will appear here.</div>
          <p style="margin-top:1rem">
            <button class="btn btn-primary" id="talk" type="button">Talk to ARIA</button>
          </p>`;
        list.querySelector("#talk").onclick = () => go("landing");
        return;
      }
      list.innerHTML = rows
        .map((r) => {
          const badge = r.mode === "voice" ? "VOICE" : "TEXT";
          const dur =
            r.mode === "voice" && r.duration_seconds
              ? ` · ${fmtDuration(r.duration_seconds)}`
              : "";
          return `
          <div class="list-row hist-row" data-id="${esc(r.id)}" data-mode="${esc(r.mode)}">
            <div>
              <div><span class="mode-badge ${r.mode}">${badge}</span> ${esc(r.title)}</div>
              <div class="meta">${esc(r.appliance || r.diagnosis || "Diagnostic session")}${dur}</div>
            </div>
            <div class="right">${esc(fmtWhen(r.updated_at || r.created_at))}</div>
          </div>`;
        })
        .join("");
      list.querySelectorAll(".hist-row").forEach((el) => {
        el.onclick = () => {
          if (el.dataset.mode === "text") go("chat", el.dataset.id);
          else go("history", el.dataset.id);
        };
      });
    } catch (err) {
      list.innerHTML = `<div class="empty">Could not load history.</div>`;
      console.error(err);
    }
  }

  root.querySelectorAll(".chip").forEach((btn) => {
    btn.onclick = () => {
      root.querySelectorAll(".chip").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      mode = btn.dataset.mode || "";
      refresh();
    };
  });
  let t;
  search.addEventListener("input", () => {
    clearTimeout(t);
    t = setTimeout(refresh, 220);
  });
  refresh();
}

async function renderDetail(root, { go }, id) {
  root.innerHTML = pageShell(
    "history",
    "Voice session",
    "Loading transcript…",
    `<div class="empty">Loading…</div>`
  );
  const page = root.querySelector(".page");
  try {
    const c = await getConversation(id);
    if (c.mode === "text") {
      go("chat", id);
      return;
    }
    const msgs = (c.messages || [])
      .map((m) => {
        const who = m.role === "user" ? "CUSTOMER" : "ARIA";
        return `<div class="tx-msg"><div class="tx-who">${who}</div><div class="tx-body">${esc(m.content)}</div></div>`;
      })
      .join("");
    page.innerHTML = `
      <button class="btn btn-ghost" id="backHist" type="button">← History</button>
      <div class="voice-session-card">
        <div class="sec-label">Voice session</div>
        <h1 style="margin-top:0.35rem">${esc(c.title)}</h1>
        <p class="lead">${esc(fmtWhen(c.created_at))}${
          c.duration_seconds ? ` · ${fmtDuration(c.duration_seconds)}` : ""
        }</p>
        <div class="mode-badge voice">Voice session</div>
      </div>
      <div class="sec-label" style="margin-top:1.75rem">Transcript</div>
      <div class="transcript">${msgs || '<div class="empty">No transcript saved.</div>'}</div>
      <div class="sec-label" style="margin-top:1.75rem">Session summary</div>
      <div class="summary-grid">
        <div><div class="ax-l">Appliance</div><div>${esc(c.appliance || "—")}</div></div>
        <div><div class="ax-l">Severity</div><div>${esc(c.severity || "—")}</div></div>
        <div><div class="ax-l">Diagnosis</div><div>${esc(c.diagnosis || "—")}</div></div>
        <div><div class="ax-l">Outcome</div><div>${esc((c.outcome || "—").toString().replaceAll("_", " "))}</div></div>
      </div>
      <p style="margin-top:1.5rem">
        <button class="btn btn-danger" id="hide" type="button">Remove from history</button>
      </p>
    `;
    page.querySelector("#backHist").onclick = () => go("history");
    page.querySelector("#hide").onclick = async () => {
      await archiveConversation(id);
      go("history");
    };
  } catch (err) {
    page.innerHTML = `<div class="empty">Conversation not found.</div>`;
    console.error(err);
  }
}
