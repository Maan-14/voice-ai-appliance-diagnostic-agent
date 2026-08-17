/** Shared chrome: product title + dashboard nav. */
export function siteNav(active = "") {
  const items = [
    ["history", "History", "#/history"],
    ["appointments", "Appointments", "#/appointments"],
    ["ops", "Operations", "#/ops"],
  ];
  return `<nav class="site-nav" aria-label="Dashboard">
    ${items
      .map(
        ([id, label, href]) =>
          `<a href="${href}" class="${id === active ? "active" : ""}">${label}</a>`
      )
      .join("")}
  </nav>`;
}

export function pageShell(active, title, lead, body) {
  return `
    <div class="landing">
      <header class="topbar solid">
        <a class="brand brand-link" href="#/">
          <strong>ARIA</strong><span>– Appliance Diagnostic Agent</span>
        </a>
        <div class="top-right">
          ${siteNav(active)}
        </div>
      </header>
      <div class="page">
        <h1>${title}</h1>
        <p class="lead">${lead}</p>
        ${body}
      </div>
    </div>
  `;
}
