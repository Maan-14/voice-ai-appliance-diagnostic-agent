/** Shared chrome helpers (no product navbar — Talk / Voice first). */
export function pageShell(_active, title, lead, body) {
  return `
    <div class="landing">
      <header class="topbar solid">
        <a class="brand brand-link" href="#/">
          <strong>ARIA</strong><span>${title}</span>
        </a>
      </header>
      <div class="page">
        <h1>${title}</h1>
        <p class="lead">${lead}</p>
        ${body}
      </div>
    </div>
  `;
}
