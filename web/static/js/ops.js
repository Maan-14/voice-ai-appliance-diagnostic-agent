import { getOps } from "./api.js";
import { pageShell } from "./shell.js";

function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

export async function renderOps(root, { go }) {
  root.innerHTML = pageShell(
    "ops",
    "Operations",
    "A concise view of live and recent diagnostic activity.",
    `<div class="empty">Loading…</div>`
  );

  const page = root.querySelector(".page");
  try {
    const data = await getOps();
    const live = data.live || [];
    const recent = data.recent || [];
    page.innerHTML = `
      <h1>Operations</h1>
      <p class="lead">A concise view of live and recent diagnostic activity.</p>
      <div class="ops-kpis">
        <div class="ops-kpi"><div class="l">Active conversations</div><div class="n">${data.active_conversations}</div></div>
        <div class="ops-kpi"><div class="l">Total calls</div><div class="n">${data.total_calls}</div></div>
        <div class="ops-kpi"><div class="l">Appointments booked</div><div class="n">${data.appointments}</div></div>
      </div>
      <div class="sec-label">Live conversations</div>
      ${
        live.length
          ? live
              .map(
                (r) => `
          <div class="list-row">
            <div>
              <div>${esc(r.name)}</div>
              <div class="meta">${esc(r.mode)} · ${esc(r.summary)}</div>
            </div>
          </div>`
              )
              .join("")
          : `<div class="empty">No live phone calls right now.</div>`
      }
      <div class="sec-label" style="margin-top:1.75rem">Recent</div>
      ${
        recent.length
          ? recent
              .slice(0, 8)
              .map(
                (r) => `
          <div class="list-row">
            <div>
              <div>${esc(r.title || r.name || "Session")}</div>
              <div class="meta">${esc((r.mode || "").toString().toUpperCase())} · ${esc(r.appliance || r.diagnosis || r.summary || "")}</div>
            </div>
            <div class="right">${esc((r.outcome || "").toString().replaceAll("_", " "))}</div>
          </div>`
              )
              .join("")
          : `<div class="empty">No sessions yet.</div>`
      }
      <p style="margin-top:2rem"><button class="btn btn-primary" id="talk" type="button">Talk to ARIA</button></p>
    `;
    page.querySelector("#talk").onclick = () => go("landing");
  } catch (err) {
    page.innerHTML = `<div class="empty">Could not load operations.</div>`;
    console.error(err);
  }
}
