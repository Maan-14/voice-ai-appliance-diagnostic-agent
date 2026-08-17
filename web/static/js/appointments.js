import { getAppointment, listAppointments } from "./api.js";
import { pageShell } from "./shell.js";

function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function fmtWhen(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function prettyStatus(status) {
  return String(status || "—").replaceAll("_", " ");
}

export async function renderAppointments(root, { go }, openId = null) {
  if (openId) {
    await renderDetail(root, { go }, openId);
    return;
  }

  root.innerHTML = pageShell(
    "appointments",
    "Appointments",
    "Technician visits booked through ARIA — chat, voice, or phone.",
    `<div class="hist-toolbar">
      <div class="hist-filters">
        <button class="chip active" data-status="" type="button">All</button>
        <button class="chip" data-status="confirmed" type="button">Confirmed</button>
        <button class="chip" data-status="completed" type="button">Completed</button>
        <button class="chip" data-status="cancelled" type="button">Cancelled</button>
      </div>
    </div>
    <div id="list"><div class="empty">Loading…</div></div>`
  );

  const list = root.querySelector("#list");
  let status = "";

  async function refresh() {
    try {
      const rows = await listAppointments({
        status: status || undefined,
      });
      if (!rows.length) {
        list.innerHTML = `
          <div class="empty">No appointments yet. Book one by talking to ARIA.</div>
          <p style="margin-top:1rem">
            <button class="btn btn-primary" id="talk" type="button">Talk to ARIA</button>
          </p>`;
        list.querySelector("#talk").onclick = () => go("landing");
        return;
      }
      list.innerHTML = rows
        .map((r) => {
          const st = esc(r.status || "");
          return `
          <div class="list-row hist-row" data-id="${esc(r.id)}">
            <div>
              <div>
                <span class="mode-badge status-${st}">${esc(prettyStatus(r.status))}</span>
                ${esc(r.customer_name || "Customer")}
              </div>
              <div class="meta">${esc(r.appliance_type || "Appliance")} · ${esc(
                r.technician_name || "Technician"
              )} · ZIP ${esc(r.service_zip || "—")}</div>
            </div>
            <div class="right">${esc(fmtWhen(r.scheduled_start))}<div class="meta">${esc(
              r.confirmation_code || ""
            )}</div></div>
          </div>`;
        })
        .join("");
      list.querySelectorAll(".hist-row").forEach((el) => {
        el.onclick = () => go("appointments", el.dataset.id);
      });
    } catch (err) {
      list.innerHTML = `<div class="empty">Could not load appointments.</div>`;
      console.error(err);
    }
  }

  root.querySelectorAll(".chip").forEach((btn) => {
    btn.onclick = () => {
      root.querySelectorAll(".chip").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      status = btn.dataset.status || "";
      refresh();
    };
  });
  refresh();
}

async function renderDetail(root, { go }, id) {
  root.innerHTML = pageShell(
    "appointments",
    "Appointment",
    "Loading booking…",
    `<div class="empty">Loading…</div>`
  );
  const page = root.querySelector(".page");
  try {
    const a = await getAppointment(id);
    page.innerHTML = `
      <button class="btn btn-ghost" id="backAppt" type="button">← Appointments</button>
      <div class="voice-session-card">
        <div class="sec-label">Confirmation</div>
        <h1 style="margin-top:0.35rem">${esc(a.confirmation_code)}</h1>
        <p class="lead">${esc(fmtWhen(a.scheduled_start))} – ${esc(fmtWhen(a.scheduled_end))}</p>
        <div class="mode-badge status-${esc(a.status || "")}">${esc(prettyStatus(a.status))}</div>
      </div>
      <div class="sec-label" style="margin-top:1.75rem">Visit</div>
      <div class="summary-grid">
        <div><div class="ax-l">Customer</div><div>${esc(a.customer_name || "—")}</div></div>
        <div><div class="ax-l">Phone</div><div>${esc(a.customer_phone || "—")}</div></div>
        <div><div class="ax-l">Address</div><div>${esc(a.service_address || "—")}</div></div>
        <div><div class="ax-l">ZIP</div><div>${esc(a.service_zip || "—")}</div></div>
        <div><div class="ax-l">Appliance</div><div>${esc(a.appliance_type || "—")}</div></div>
        <div><div class="ax-l">Technician</div><div>${esc(a.technician_name || "—")}</div></div>
      </div>
      <div class="sec-label" style="margin-top:1.75rem">Issue</div>
      <div class="detail">${esc(a.issue_summary || "—")}</div>
    `;
    page.querySelector("#backAppt").onclick = () => go("appointments");
  } catch (err) {
    page.innerHTML = `<div class="empty">Appointment not found.</div>`;
    console.error(err);
  }
}
