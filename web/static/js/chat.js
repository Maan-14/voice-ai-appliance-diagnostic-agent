import {
  archiveConversation,
  createSession,
  getConversation,
  getStatus,
  listConversations,
  persistSession,
  renameConversation,
  streamChat,
} from "./api.js";
import { siteNav } from "./shell.js";

function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function relativeTime(iso) {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const diff = Date.now() - t;
  const m = Math.floor(diff / 60000);
  if (m < 1) return "Just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d === 1) return "Yesterday";
  if (d < 7) return `${d}d ago`;
  return new Date(iso).toLocaleDateString();
}

function groupLabel(iso) {
  if (!iso) return "Older";
  const day = new Date(iso);
  const today = new Date();
  const startToday = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const startYday = new Date(startToday);
  startYday.setDate(startYday.getDate() - 1);
  if (day >= startToday) return "Today";
  if (day >= startYday) return "Yesterday";
  return "Older";
}

export async function renderChat(root, { go }, openId = null) {
  let session = openId ? await getConversation(openId) : await createSession("text");
  let conversationId = session.id || session.session_id;
  let callContext = session.call_context;
  let history = session.history || [];
  let messages = (session.messages || []).map((m) => ({
    role: m.role === "user" ? "user" : "assistant",
    content: m.content,
  }));
  if (!messages.length && session.greeting) {
    messages = [{ role: "assistant", content: session.greeting }];
  }
  let busy = false;
  let abortCtl = null;
  let sidebarItems = [];

  root.innerHTML = `
    <div class="chat-layout">
      <aside class="chat-sidebar">
        <div class="side-brand">
          <strong>ARIA</strong>
          <button class="btn btn-primary side-new" id="new" type="button">New chat</button>
        </div>
        <input class="side-search" id="search" type="search" placeholder="Search conversations" />
        <div class="side-list" id="sideList"><div class="empty">Loading…</div></div>
      </aside>
      <div class="chat-shell">
        <header class="topbar solid">
          <button class="back" id="back" type="button">
            ← ARIA
            <small>– Appliance Diagnostic Agent</small>
          </button>
          <div class="top-right">
            <span class="chat-title" id="chatTitle">${esc(session.title || "New conversation")}</span>
          </div>
        </header>
        <main class="chat-main" id="thread"></main>
        <div class="composer-wrap">
          <form class="composer" id="form">
            <textarea id="input" rows="1" placeholder="Message ARIA..." autocomplete="off"></textarea>
            <button class="send" id="send" type="submit" aria-label="Send">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                <path d="M12 19V5M12 5l-6 6M12 5l6 6" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </button>
          </form>
        </div>
      </div>
    </div>
  `;

  const thread = root.querySelector("#thread");
  const form = root.querySelector("#form");
  const input = root.querySelector("#input");
  const sendBtn = root.querySelector("#send");
  const sideList = root.querySelector("#sideList");
  const chatTitle = root.querySelector("#chatTitle");
  const search = root.querySelector("#search");

  const NEAR_BOTTOM_PX = 140;
  let stickToBottom = true;
  let streamRaf = 0;

  function isNearBottom() {
    return (
      document.documentElement.scrollHeight - window.scrollY - window.innerHeight <
      NEAR_BOTTOM_PX
    );
  }

  window.addEventListener(
    "scroll",
    () => {
      stickToBottom = isNearBottom();
    },
    { passive: true }
  );

  function scrollThread(force = false) {
    if (!force && !stickToBottom) return;
    stickToBottom = true;
    window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "auto" });
  }

  function msgHtml(m, extraClass = "") {
    const who = m.role === "user" ? "You" : "ARIA";
    const cls = m.role === "user" ? "user" : "assistant";
    return `<div class="msg ${cls} ${extraClass}"><div class="who">${who}</div><div class="bubble">${esc(m.content)}</div></div>`;
  }

  root.querySelector("#back").onclick = () => go("landing");
  root.querySelector("#new").onclick = () => go("chat");

  async function refreshSidebar(q = "") {
    try {
      sidebarItems = await listConversations({ mode: "text", q: q || undefined });
    } catch {
      sidebarItems = [];
    }
    const groups = { Today: [], Yesterday: [], Older: [] };
    for (const c of sidebarItems) {
      groups[groupLabel(c.updated_at || c.created_at)].push(c);
    }
    let html = "";
    for (const [label, items] of Object.entries(groups)) {
      if (!items.length) continue;
      html += `<div class="side-sec">${label}</div>`;
      for (const c of items) {
        const active = c.id === conversationId ? "active" : "";
        html += `
          <div class="side-item ${active}" data-id="${esc(c.id)}">
            <div class="side-item-main">
              <div class="side-item-title">${esc(c.title)}</div>
              <div class="side-item-meta">${esc(relativeTime(c.updated_at))}</div>
            </div>
            <button class="side-menu" data-menu="${esc(c.id)}" type="button" title="More">⋯</button>
          </div>`;
      }
    }
    sideList.innerHTML = html || `<div class="empty">Your conversations will appear here.</div>`;
    sideList.querySelectorAll(".side-item").forEach((el) => {
      el.onclick = (e) => {
        if (e.target.closest("[data-menu]")) return;
        go("chat", el.dataset.id);
      };
    });
    sideList.querySelectorAll("[data-menu]").forEach((btn) => {
      btn.onclick = async (e) => {
        e.stopPropagation();
        const id = btn.dataset.menu;
        const action = window.prompt("Type rename or delete");
        if (!action) return;
        if (action.toLowerCase() === "delete") {
          await archiveConversation(id);
          if (id === conversationId) go("chat");
          else refreshSidebar(search.value.trim());
        } else if (action.toLowerCase().startsWith("rename")) {
          const title = window.prompt("New title");
          if (title) {
            await renameConversation(id, title);
            if (id === conversationId) chatTitle.textContent = title;
            refreshSidebar(search.value.trim());
          }
        }
      };
    });
  }

  function paint(opts = {}) {
    thread.innerHTML = messages.map((m) => msgHtml(m)).join("");
    if (opts.typing) showTyping();
    scrollThread(opts.forceScroll);
  }

  function showTyping() {
    if (thread.querySelector("#typingRow") || thread.querySelector("#streamRow")) return;
    thread.insertAdjacentHTML(
      "beforeend",
      `<div class="msg assistant enter" id="typingRow">
        <div class="who">ARIA</div>
        <div class="typing"><i></i><i></i><i></i></div>
      </div>`
    );
    scrollThread(true);
  }

  function applyStreamText(text) {
    thread.querySelector("#typingRow")?.remove();
    let row = thread.querySelector("#streamRow");
    if (!row) {
      thread.insertAdjacentHTML(
        "beforeend",
        `<div class="msg assistant enter" id="streamRow"><div class="who">ARIA</div><div class="bubble"></div></div>`
      );
      row = thread.querySelector("#streamRow");
    }
    row.querySelector(".bubble").textContent = text;
    scrollThread();
  }

  function upsertStream(text) {
    if (streamRaf) cancelAnimationFrame(streamRaf);
    streamRaf = requestAnimationFrame(() => {
      streamRaf = 0;
      applyStreamText(text);
    });
  }

  paint();
  refreshSidebar();
  input.focus();

  let searchTimer;
  search.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => refreshSidebar(search.value.trim()), 220);
  });

  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 140)}px`;
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text || busy) return;
    busy = true;
    sendBtn.disabled = true;
    input.value = "";
    input.style.height = "auto";

    messages.push({ role: "user", content: text });
    const userNode = document.createElement("div");
    userNode.innerHTML = msgHtml({ role: "user", content: text }, "enter");
    thread.appendChild(userNode.firstElementChild);
    showTyping();

    let assistant = { role: "assistant", content: "" };
    let started = false;
    abortCtl = new AbortController();

    try {
      await streamChat({
        message: text,
        callContext,
        history,
        conversationId,
        signal: abortCtl.signal,
        onStatus() {
          showTyping();
        },
        onDelta(delta) {
          if (!started) {
            started = true;
            messages.push(assistant);
          }
          assistant.content += delta;
          upsertStream(assistant.content);
        },
        onDone(payload) {
          if (!started) {
            messages.push(assistant);
            assistant.content = payload.reply || "";
          } else if (!assistant.content && payload.reply) {
            assistant.content = payload.reply;
          }
          callContext = payload.call_context;
          history = payload.history || [];
          if (streamRaf) {
            cancelAnimationFrame(streamRaf);
            streamRaf = 0;
          }
          applyStreamText(assistant.content);
          thread.querySelector("#streamRow")?.removeAttribute("id");
          refreshSidebar(search.value.trim());
        },
        onTitle(title) {
          if (title) {
            chatTitle.textContent = title;
            refreshSidebar(search.value.trim());
          }
        },
      });
    } catch (err) {
      if (err?.name !== "AbortError") {
        messages.push({
          role: "assistant",
          content: "Something went wrong. Please try again.",
        });
        paint();
        console.error(err);
      }
    } finally {
      busy = false;
      sendBtn.disabled = false;
      input.focus();
    }
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  window.addEventListener("beforeunload", () => {
    persistSession(callContext, conversationId).catch(() => {});
  });
}

export async function renderLanding(root, { go }) {
  let status = { openai: false };
  try {
    status = await getStatus();
  } catch {
    status = { openai: false };
  }

  root.innerHTML = `
    <div class="landing">
      <header class="topbar">
        <div class="brand">
          <strong>ARIA</strong>
          <span>– Appliance Diagnostic Agent</span>
        </div>
        <div class="top-right">
          ${siteNav("landing")}
          <div class="status-pill">
            <span class="dot ${status.openai ? "" : "warn"}"></span>
            ${status.openai ? "Operational" : "Setup needed"}
          </div>
        </div>
      </header>
      <section class="hero">
        <h1>How can ARIA help with your appliance?</h1>
        <p class="lead">Diagnose an appliance problem through a natural conversation with ARIA.</p>
        <div class="mode-grid">
          <article class="mode-card" id="go-text" tabindex="0">
            <div class="icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <path d="M4 6.5A2.5 2.5 0 016.5 4h11A2.5 2.5 0 0120 6.5v7A2.5 2.5 0 0117.5 16H9l-4 3.5V6.5z" stroke="currentColor" stroke-width="1.6"/>
              </svg>
            </div>
            <h2>Chat with ARIA</h2>
            <p>Describe what’s happening and troubleshoot it together.</p>
            <div class="cta">Start text chat <span>→</span></div>
          </article>
          <article class="mode-card" id="go-voice" tabindex="0">
            <div class="icon">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <rect x="9" y="3" width="6" height="11" rx="3" stroke="currentColor" stroke-width="1.6"/>
                <path d="M5 11a7 7 0 0014 0M12 18v3" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
              </svg>
            </div>
            <h2>Talk to ARIA</h2>
            <p>Have a natural hands-free conversation with ARIA.</p>
            <div class="cta">Start voice conversation <span>→</span></div>
          </article>
        </div>
      </section>
    </div>
  `;

  root.querySelector("#go-text").onclick = () => go("chat");
  root.querySelector("#go-voice").onclick = () => go("voice");
}
