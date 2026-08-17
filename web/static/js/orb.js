/** Audio-reactive ARIA orb — violet / indigo / cyan. */
export class AriaOrb {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.level = 0;
    this.target = 0;
    this.phase = 0;
    this.state = "idle";
    this._raf = 0;
    this._resize();
    window.addEventListener("resize", () => this._resize());
  }

  setState(state) {
    this.state = state;
  }

  setLevel(n) {
    this.target = Math.max(0, Math.min(1, n));
  }

  start() {
    const tick = () => {
      this._draw();
      this._raf = requestAnimationFrame(tick);
    };
    cancelAnimationFrame(this._raf);
    this._raf = requestAnimationFrame(tick);
  }

  stop() {
    cancelAnimationFrame(this._raf);
    this.setLevel(0);
  }

  _resize() {
    const dpr = window.devicePixelRatio || 1;
    const rect = this.canvas.getBoundingClientRect();
    this.canvas.width = rect.width * dpr;
    this.canvas.height = rect.height * dpr;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.w = rect.width;
    this.h = rect.height;
  }

  _draw() {
    const { ctx, w, h } = this;
    this.level += (this.target - this.level) * 0.16;
    const spin =
      this.state === "thinking" ? 0.055 : this.state === "speaking" ? 0.04 : 0.028;
    this.phase += spin + this.level * 0.04;

    ctx.clearRect(0, 0, w, h);
    const cx = w / 2;
    const cy = h / 2;
    const base = Math.min(w, h) * 0.22;

    let pulse = 0.05 + Math.sin(this.phase) * 0.02;
    if (this.state === "thinking") pulse = 0.1 + Math.sin(this.phase * 1.6) * 0.05;
    if (this.state === "listening") pulse = 0.06 + this.level * 0.32;
    if (this.state === "user_speaking") pulse = 0.1 + this.level * 0.45;
    if (this.state === "speaking") pulse = 0.14 + this.level * 0.38;
    if (this.state === "ended" || this.state === "idle") pulse = 0.04;

    const r = base * (1 + pulse);

    const glow = ctx.createRadialGradient(cx, cy, r * 0.15, cx, cy, r * 2.4);
    glow.addColorStop(0, "rgba(124,92,255,0.4)");
    glow.addColorStop(0.35, "rgba(91,108,255,0.16)");
    glow.addColorStop(0.7, "rgba(79,209,255,0.06)");
    glow.addColorStop(1, "rgba(79,209,255,0)");
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.arc(cx, cy, r * 2.35, 0, Math.PI * 2);
    ctx.fill();

    for (let i = 0; i < 3; i++) {
      const t = (this.phase * 0.35 + i / 3) % 1;
      const rr = r * (1.2 + t * (0.5 + this.level * 0.45));
      ctx.strokeStyle = `rgba(79,209,255,${(1 - t) * 0.14})`;
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      ctx.arc(cx, cy, rr, 0, Math.PI * 2);
      ctx.stroke();
    }

    const core = ctx.createRadialGradient(
      cx - r * 0.25,
      cy - r * 0.3,
      r * 0.08,
      cx,
      cy,
      r
    );
    core.addColorStop(0, "#c4b5fd");
    core.addColorStop(0.35, "#7c5cff");
    core.addColorStop(0.7, "#5b6cff");
    core.addColorStop(1, "#312e81");
    ctx.fillStyle = core;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = "rgba(255,255,255,0.22)";
    ctx.beginPath();
    ctx.ellipse(cx - r * 0.28, cy - r * 0.32, r * 0.32, r * 0.2, -0.45, 0, Math.PI * 2);
    ctx.fill();

    // Cyan rim highlight
    ctx.strokeStyle = "rgba(79,209,255,0.35)";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(cx, cy, r * 0.98, -0.8, 0.6);
    ctx.stroke();
  }
}
