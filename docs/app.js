"use strict";

// Columnas del tablero: todo mezclado, y los dos focos regionales.
const COLUMNS = [
  { id: "todo", label: "Lo último", hint: "Todas las regiones y temas, mezclados", filter: () => true },
  { id: "africa", label: "África", hint: "Foco África", filter: (i) => (i.regions || []).includes("africa") },
  { id: "medio_oriente", label: "Medio Oriente", hint: "Foco Medio Oriente", filter: (i) => (i.regions || []).includes("medio_oriente") },
];
const LANG_NAMES = {
  es: "español", en: "inglés", ar: "árabe", he: "hebreo", de: "alemán", fr: "francés",
  hi: "hindi", bn: "bengalí", zh: "chino", ja: "japonés", am: "amhárico",
};
const RTL = new Set(["ar", "he"]);
const PAGE = 40;
const REFRESH_MS = 10 * 60 * 1000;
// Para mezclar: no más de una nota seguida del mismo medio si hay otra de hasta 2 h de diferencia.
const MIX_WINDOW_S = 2 * 3600;

const state = { data: null, status: null, topics: new Set(), shown: {}, activeTab: "todo" };
const $ = (id) => document.getElementById(id);

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const child of children) if (child) node.append(child);
  return node;
}

function timeAgo(ts) {
  const minutes = Math.max(0, Math.round((Date.now() / 1000 - ts) / 60));
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `hace ${hours} h`;
  const days = Math.round(hours / 24);
  return `hace ${days} ${days === 1 ? "día" : "días"}`;
}

function formatDate(ts) {
  return new Date(ts * 1000).toLocaleString("es-AR", { dateStyle: "medium", timeStyle: "short" });
}

async function loadJSON(path) {
  const response = await fetch(`${path}?t=${Date.now()}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
}

async function load() {
  try {
    const [data, status] = await Promise.all([loadJSON("data/news.json"), loadJSON("data/feeds-status.json")]);
    // Compatibilidad con el formato anterior (un solo tema por noticia).
    for (const item of data.items) if (!item.topics) item.topics = item.topic ? [item.topic] : [];
    state.data = data;
    state.status = status;
    fillSources();
    renderTopicChips();
    renderHeader();
    renderStatus();
    render();
  } catch (error) {
    $("updated").textContent = "Todavía no hay datos: el robot corre una vez por hora.";
    console.error(error);
  }
}

function fillSources() {
  const select = $("source");
  const current = select.value;
  const names = [...new Set(state.data.items.map((i) => i.source))].sort((a, b) => a.localeCompare(b, "es"));
  select.replaceChildren(el("option", { value: "", text: `Todos los medios (${names.length})` }),
    ...names.map((name) => el("option", { value: name, text: name })));
  select.value = names.includes(current) ? current : "";
}

function renderTopicChips() {
  const box = $("topics");
  const chip = (id, label) => el("button", {
    type: "button", class: "chip", "data-topic": id,
    "aria-pressed": String(id ? state.topics.has(id) : state.topics.size === 0),
    onclick: () => {
      if (!id) state.topics.clear();
      else if (state.topics.has(id)) state.topics.delete(id);
      else state.topics.add(id);
      state.shown = {};
      renderTopicChips();
      render();
    },
  }, id ? el("span", { class: "dot", "aria-hidden": "true" }) : null, label);
  box.replaceChildren(chip("", "Todos los temas"),
    ...Object.entries(state.data.topics).map(([id, label]) => chip(id, label)));
}

function renderHeader() {
  const { data, status } = state;
  const sources = new Set(status.feeds.map((f) => f.source)).size;
  let text = `Actualizado ${timeAgo(data.updated)} (${formatDate(data.updated)}) · ${sources} medios`;
  if (data.translation && data.translation.pending) {
    text += ` · ${data.translation.pending} noticias esperando traducción`;
  }
  $("updated").textContent = text;
  const failing = status.total - status.ok;
  const color = failing <= 3 ? "var(--ok)" : failing <= 10 ? "var(--warn)" : "var(--err)";
  $("status-btn").replaceChildren(el("span", { class: "dot", style: `background:${color}` }),
    `Fuentes: ${status.ok}/${status.total} OK`);
}

function renderStatus() {
  const rows = state.status.feeds.map((feed) => {
    let mark = "✅", cls = "st-ok", note = `${feed.items} noticias`;
    if (!feed.ok) {
      mark = feed.last_ok ? "⚠️" : "❌";
      cls = feed.last_ok ? "st-warn" : "st-err";
      note = feed.error + (feed.last_ok ? ` · último OK ${timeAgo(feed.last_ok)}` : " · nunca funcionó");
    }
    return el("tr", {},
      el("td", { class: cls, text: mark }),
      el("td", { text: feed.source }),
      el("td", { text: LANG_NAMES[feed.lang] || feed.lang }),
      el("td", { class: cls, text: note }),
      el("td", { class: "url", text: feed.url }));
  });
  $("status").replaceChildren(el("div", { class: "status-inner" },
    el("table", {},
      el("thead", {}, el("tr", {}, ...["", "Medio", "Idioma", "Estado", "Feed"].map((h) => el("th", { text: h })))),
      el("tbody", {}, ...rows))));
}

function filtered() {
  const q = $("q").value.trim().toLowerCase();
  const lang = $("lang").value;
  const source = $("source").value;
  const since = Date.now() / 1000 - Number($("period").value) * 3600;
  return state.data.items.filter((item) => {
    if (item.published < since) return false;
    if (state.topics.size && !item.topics.some((t) => state.topics.has(t))) return false;
    if (lang && item.lang !== lang) return false;
    if (source && item.source !== source) return false;
    if (q) {
      const haystack = [item.title, item.summary, item.title_es, item.summary_es].join(" ").toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    return true;
  });
}

// Ordena por fecha, pero evita rachas del mismo medio: si la siguiente nota es del mismo
// medio que la anterior, adelanta una de otro medio publicada hasta 2 h después.
function mix(items) {
  const pending = [...items].sort((a, b) => b.published - a.published);
  const out = [];
  while (pending.length) {
    let pick = 0;
    const last = out[out.length - 1];
    if (last && pending[0].source === last.source) {
      const alt = pending.findIndex((i) => i.source !== last.source);
      if (alt > 0 && pending[0].published - pending[alt].published <= MIX_WINDOW_S) pick = alt;
    }
    out.push(pending.splice(pick, 1)[0]);
  }
  return out;
}

function card(item, columnId) {
  const translated = Boolean(item.title_es);
  const needsTranslation = !["es", "en"].includes(item.lang);
  const meta = el("div", { class: "meta" },
    el("span", { class: "src", text: item.source }),
    el("span", { text: timeAgo(item.published), title: formatDate(item.published) }));
  for (const region of item.regions || []) {
    if (region !== columnId) meta.append(el("span", { class: "tag", text: state.data.regions[region] || region }));
  }
  if (translated) meta.append(el("span", { class: "tag tr", text: `Traducido del ${LANG_NAMES[item.lang]}` }));
  else if (needsTranslation) meta.append(el("span", { class: "tag tr", text: "Traducción pendiente" }));

  const showOriginalText = !translated;
  const dir = RTL.has(item.lang) && showOriginalText ? "rtl" : null;
  const textLang = showOriginalText ? item.lang : "es";
  const summary = translated ? item.summary_es : item.summary;
  const topics = item.topics.length ? el("div", { class: "topics" },
    ...item.topics.map((t) => el("span", { class: "topic", "data-topic": t, text: state.data.topics[t] || t }))) : null;
  const node = el("article", { class: "card" },
    meta,
    el("h3", { lang: textLang, dir },
      el("a", { href: item.link, target: "_blank", rel: "noopener", text: translated ? item.title_es : item.title })),
    summary ? el("p", { class: "summary", lang: textLang, dir, text: summary }) : null,
    topics);

  if (translated) {
    const original = el("div", { class: "orig", lang: item.lang, dir: RTL.has(item.lang) ? "rtl" : "ltr", hidden: "" },
      el("strong", { text: item.title }), item.summary ? el("p", { text: item.summary }) : null);
    const button = el("button", { type: "button", class: "orig-btn", "aria-expanded": "false", text: "▸ Ver original" });
    button.addEventListener("click", () => {
      const open = original.hidden;
      original.hidden = !open;
      button.setAttribute("aria-expanded", String(open));
      button.textContent = open ? "▾ Ocultar original" : "▸ Ver original";
    });
    node.append(button, original);
  }
  return node;
}

function render() {
  if (!state.data) return;
  const items = filtered();
  const board = $("board");
  const tabs = $("tabs");
  board.replaceChildren();
  tabs.replaceChildren();
  for (const column of COLUMNS) {
    const list = mix(items.filter(column.filter));
    const limit = state.shown[column.id] || PAGE;
    const col = el("section", {
      class: `col${state.activeTab === column.id ? " active" : ""}`, "data-col": column.id, "aria-label": column.label,
    }, el("div", { class: "col-head" },
      el("div", {}, el("h2", { text: column.label }), el("span", { class: "hint", text: column.hint })),
      el("span", { class: "count", text: `${list.length}` })));
    if (!list.length) col.append(el("p", { class: "empty", text: "No hay noticias con estos filtros." }));
    list.slice(0, limit).forEach((item) => col.append(card(item, column.id)));
    if (list.length > limit) {
      col.append(el("button", { type: "button", class: "more", text: `Ver más (${list.length - limit})`,
        onclick: () => { state.shown[column.id] = limit + PAGE; render(); } }));
    }
    board.append(col);
    tabs.append(el("button", { type: "button", class: "tab", role: "tab", "aria-selected": String(state.activeTab === column.id),
      text: `${column.label} (${list.length})`, onclick: () => { state.activeTab = column.id; render(); window.scrollTo(0, 0); } }));
  }
}

function setup() {
  for (const id of ["q", "lang", "source", "period"]) {
    $(id).addEventListener("input", () => { state.shown = {}; render(); });
  }
  $("status-btn").addEventListener("click", () => {
    const panel = $("status");
    panel.hidden = !panel.hidden;
    $("status-btn").setAttribute("aria-expanded", String(!panel.hidden));
  });
  load();
  setInterval(load, REFRESH_MS);
}

setup();
