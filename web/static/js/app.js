import { renderLanding, renderChat } from "./chat.js";
import { renderVoice } from "./voice.js";
import { renderOps } from "./ops.js";
import { renderHistory } from "./history.js";
import { renderSettings } from "./settings.js";

const root = document.getElementById("app");

function routeFromHash() {
  const raw = (location.hash || "#/").replace(/^#\/?/, "");
  const [name, id] = raw.split("/");
  if (name === "chat") return { name: "chat", id: id || null };
  if (name === "voice") return { name: "voice", id: null };
  if (name === "ops") return { name: "ops", id: null };
  if (name === "history") return { name: "history", id: id || null };
  if (name === "settings") return { name: "settings", id: null };
  return { name: "landing", id: null };
}

async function go(name, id = null) {
  const map = {
    landing: "#/",
    chat: id ? `#/chat/${id}` : "#/chat",
    voice: "#/voice",
    ops: "#/ops",
    history: id ? `#/history/${id}` : "#/history",
    settings: "#/settings",
  };
  const target = map[name] || "#/";
  if (location.hash !== target) {
    location.hash = target;
    return;
  }
  await paint(routeFromHash());
}

async function paint(route) {
  root.innerHTML = "";
  const { name, id } = route;
  if (name === "chat") await renderChat(root, { go }, id);
  else if (name === "voice") await renderVoice(root, { go });
  else if (name === "ops") await renderOps(root, { go });
  else if (name === "history") await renderHistory(root, { go }, id);
  else if (name === "settings") await renderSettings(root, { go });
  else await renderLanding(root, { go });
}

window.addEventListener("hashchange", () => paint(routeFromHash()));
paint(routeFromHash());
