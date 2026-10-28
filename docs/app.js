"use strict";

const TOPICS = ["mercados", "tech", "geopolitica"];
const LANG_NAMES = { es: "español", en: "inglés", ar: "árabe", he: "hebreo", de: "alemán", fr: "francés" };
const RTL = new Set(["ar", "he"]);
const PAGE = 40;
const REFRESH_MS = 10 * 60 * 1000;

const state = { data: null, status: null, region: "", shown: {}, activeTab: "mercados" };
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
    state.data = data;
    state.status = status;
    fillSources();
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
  select.replaceChildren(el("option", { value: "", text: "Todos los medios" }),
    ...names.map((name) => el("option", { value: name, text: name })));
  select.value = names.includes(current) ? current : "";
}

function renderHeader() {
  const { data, status } = state;
  let text = `Actualizado ${timeAgo(data.updated)} (${formatDate(data.updated)})`;
  if (data.translation && data.translation.pending) {
    text += ` · ${data.translation.pending} noticias esperando traducción`;
  }
  $("updated").textContent = text;
  const failing = status.total - status.ok;
  const color = failing === 0 ? "var(--ok)" : failing <= 5 ? "var(--warn)" : "var(--err)";
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
    if (state.region && !(item.regions || []).includes(state.region)) return false;
    if (lang && item.lang !== lang) return false;
    if (source && item.source !== source) return false;
    if (q) {
      const haystack = [item.title, item.summary, item.title_es, item.summary_es].join(" ").toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    return true;
  });
}

function card(item) {
  const translated = Boolean(item.title_es);
  const needsTranslation = !["es", "en"].includes(item.lang);
  const meta = el("div", { class: "meta" },
    el("span", { class: "src", text: item.source }),
    el("span", { text: timeAgo(item.published), title: formatDate(item.published) }));
  for (const region of item.regions || []) {
    meta.append(el("span", { class: "tag", text: state.data.regions[region] || region }));
  }
  if (translated) meta.append(el("span", { class: "tag tr", text: `Traducido del ${LANG_NAMES[item.lang]}` }));
  else if (needsTranslation) meta.append(el("span", { class: "tag tr", text: "Traducción pendiente" }));

  const showOriginalText = !translated;
  const dir = RTL.has(item.lang) && showOriginalText ? "rtl" : null;
  const textLang = showOriginalText ? item.lang : "es";
  const summary = translated ? item.summary_es : item.summary;
  const node = el("article", { class: "card" },
    meta,
    el("h3", { lang: textLang, dir },
      el("a", { href: item.link, target: "_blank", rel: "noopener", text: translated ? item.title_es : item.title })),
    summary ? el("p", { lang: textLang, dir, text: summary }) : null);

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
  for (const topic of TOPICS) {
    const list = items.filter((i) => i.topic === topic);
    const label = state.data.topics[topic] || topic;
    const limit = state.shown[topic] || PAGE;
    const col = el("section", { class: `col${state.activeTab === topic ? " active" : ""}`, "data-topic": topic, "aria-label": label },
      el("div", { class: "col-head" }, el("h2", { text: label }), el("span", { class: "count", text: `${list.length}` })));
    if (!list.length) col.append(el("p", { class: "empty", text: "No hay noticias con estos filtros." }));
    list.slice(0, limit).forEach((item) => col.append(card(item)));
    if (list.length > limit) {
      col.append(el("button", { type: "button", class: "more", text: `Ver más (${list.length - limit})`,
        onclick: () => { state.shown[topic] = limit + PAGE; render(); } }));
    }
    board.append(col);
    tabs.append(el("button", { type: "button", class: "tab", role: "tab", "aria-selected": String(state.activeTab === topic),
      text: `${label} (${list.length})`, onclick: () => { state.activeTab = topic; render(); } }));
  }
}

function setup() {
  for (const id of ["q", "lang", "source", "period"]) {
    $(id).addEventListener("input", () => { state.shown = {}; render(); });
  }
  document.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      state.region = chip.dataset.region;
      document.querySelectorAll(".chip").forEach((c) => c.setAttribute("aria-pressed", String(c === chip)));
      state.shown = {};
      render();
    });
  });
  $("status-btn").addEventListener("click", () => {
    const panel = $("status");
    panel.hidden = !panel.hidden;
    $("status-btn").setAttribute("aria-expanded", String(!panel.hidden));
  });
  load();
  setInterval(load, REFRESH_MS);
}

setup();
