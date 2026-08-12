import { getStatus } from "./api.js";
import { pageShell } from "./shell.js";

export async function renderSettings(root) {
  root.innerHTML = pageShell(
    "settings",
    "Settings",
    "Connectivity status only — secrets are never shown.",
    `<div class="empty">Loading…</div>`
  );
  const page = root.querySelector(".page");

  try {
    const s = await getStatus();
    page.innerHTML = `
      <h1>Settings</h1>
      <p class="lead">Connectivity status only — secrets are never shown.</p>
      <div class="status-grid">
        <div class="status-item"><span>Environment</span><span class="v">${s.env || "—"}</span></div>
        <div class="status-item">
          <span>OpenAI</span>
          <span class="v"><span class="dot ${s.openai ? "" : "warn"}"></span>${s.openai ? "Configured" : "Not configured"}</span>
        </div>
        <div class="status-item">
          <span>Twilio</span>
          <span class="v"><span class="dot ${s.twilio ? "" : "warn"}"></span>${s.twilio ? "Configured" : "Not configured"}</span>
        </div>
        <div class="status-item"><span>App</span><span class="v">${s.app || "ARIA"}</span></div>
      </div>
      <p class="empty" style="margin-top:1.5rem">API keys, tokens, and credentials are never displayed in this UI.</p>
    `;
  } catch (err) {
    page.innerHTML = `<div class="empty">Could not load settings.</div>`;
    console.error(err);
  }
}
