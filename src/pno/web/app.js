/* P&O · People & Organisation — the screens. Talks to Python through the Qt bridge (desktop) or HTTP (development). */
(function () {
"use strict";
const { esc, fmtv } = Charts;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
window.PNO_errors = [];
window.addEventListener("error", e => window.PNO_errors.push(String(e.message)));
window.addEventListener("unhandledrejection", e => window.PNO_errors.push(String(e.reason && e.reason.message || e.reason)));

/* ---------------------------------------------------------------- bridge */
const API = (() => {
  let bridge = null, seq = 0;
  const waiting = {};
  const ready = new Promise(res => {
    if (window.qt && window.qt.webChannelTransport) {
      const sc = document.createElement("script");
      sc.src = "qrc:///qtwebchannel/qwebchannel.js";
      sc.onload = () => new QWebChannel(qt.webChannelTransport, ch => {
        bridge = ch.objects.bridge;
        bridge.reply.connect((rid, out) => { const f = waiting[rid]; delete waiting[rid]; if (f) f(JSON.parse(out)); });
        res();
      });
      document.head.appendChild(sc);
    } else res();
  });
  async function call(method, params = {}) {
    await ready;
    let out;
    if (bridge) {
      out = await new Promise(r => { const id = "r" + (++seq); waiting[id] = r; bridge.request(id, method, JSON.stringify(params)); });
    } else {
      const r = await fetch("/api/" + method, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(params) });
      out = await r.json();
    }
    if (out && out.error) throw new Error(out.error);
    return out;
  }
  return { call, ready };
})();
window.PNO_API = API;

/* ---------------------------------------------------------------- state */
const store = {
  get(k, d) { try { const v = localStorage.getItem("pno." + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem("pno." + k, JSON.stringify(v)); } catch (e) { /* storage blocked */ } },
};
const S = { page: "home", arg: null, month: null, months: [], compare: null, scope: store.get("scope", {}), opts: {}, init: null,
  chat: [], attach: [], people: { q: "", role: "", band: "", sort: "score", desc: true, flag: "" }, perfRole: "SM",
  attTab: "fixes", setTab: "scoring", busy: 0, selected: new Set(), importSess: null };
window.PNO_state = S;

const ICON = {
  home: '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
  people: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.6-3.6 3.3-5.5 6.5-5.5s5.9 1.9 6.5 5.5"/><circle cx="17.5" cy="9" r="2.5"/><path d="M16 14.6c2.8.2 4.8 1.9 5.4 4.9"/>',
  perf: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  stores: '<path d="M3 9.5 4.5 4h15L21 9.5M3 9.5h18M3 9.5V20h18V9.5M9 20v-5h6v5"/>',
  att: '<rect x="3" y="4.5" width="18" height="16" rx="2.5"/><path d="M3 9.5h18M8 2.5v4M16 2.5v4M8 14l2.5 2.5L16 12"/>',
  org: '<rect x="9" y="2.5" width="6" height="5" rx="1.2"/><rect x="2.5" y="16.5" width="6" height="5" rx="1.2"/><rect x="15.5" y="16.5" width="6" height="5" rx="1.2"/><path d="M12 7.5V12M5.5 16.5V12h13v4.5"/>',
  ask: '<path d="M21 12a8.5 8.5 0 0 1-12.6 7.4L3 21l1.6-5.2A8.5 8.5 0 1 1 21 12z"/><path d="M8.5 10.5h7M8.5 13.5h4.5"/>',
  import: '<path d="M12 3v12M7 10l5 5 5-5M4 19.5h16"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  export: '<path d="M12 15V3M7 8l5-5 5 5M5 13v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6"/>',
  play: '<path d="M7 4.5v15l12-7.5z"/>', x: '<path d="M6 6l12 12M18 6 6 18"/>', back: '<path d="M15 5l-7 7 7 7"/>',
  attach: '<path d="M20.5 11.5 12 20a5.5 5.5 0 0 1-7.8-7.8l8.5-8.5a3.7 3.7 0 0 1 5.2 5.2l-8.5 8.5a1.8 1.8 0 0 1-2.6-2.6L14.6 7"/>',
  send: '<path d="M4 12 20 4l-6 16-3-7z"/>', file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
  paste: '<rect x="6" y="4" width="12" height="17" rx="2"/><path d="M9 4V3h6v1"/>', undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>',
  review: '<path d="M4 4h16v16H4z"/><path d="M4 10h16M10 10v10"/>',
  talent: '<circle cx="12" cy="7" r="3.5"/><path d="M5 21c.8-4 3.6-6 7-6s6.2 2 7 6"/><path d="m17 3 1 2 2 .3-1.5 1.4.4 2.1-1.9-1-1.9 1 .4-2.1L14 5.3l2-.3z"/>',
  retention: '<path d="M16 3h5v5"/><path d="M21 3l-7 7"/><path d="M11 5H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-6"/>',
  shifts: '<rect x="3" y="4.5" width="18" height="16" rx="2.5"/><path d="M3 9.5h18M8 2.5v4M16 2.5v4M7 13h2M11 13h2M15 13h2M7 17h2M11 17h2"/>',
  data: '<ellipse cx="12" cy="5.5" rx="8" ry="3"/><path d="M4 5.5v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6M4 11.5v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
  nps: '<path d="M12 21s-7-4.4-9.3-9A5.2 5.2 0 0 1 12 6.6 5.2 5.2 0 0 1 21.3 12C19 16.6 12 21 12 21z"/>',
  spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8"/>',
};
const ic = (n, s = 19) => `<svg viewBox="0 0 24 24" width="${s}" height="${s}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICON[n] || ""}</svg>`;
const NAV = [["home", "Overview", "home"], ["review", "Business review", "review"], ["stores", "Stores", "stores"],
  ["people", "People", "people"], ["talent", "Leaders & talent", "talent"], ["attendance", "Attendance", "att"],
  ["retention", "Turnover", "retention"], ["nps", "Customer NPS", "nps"], ["shifts", "Shift roster", "shifts"], ["data", "Other data", "data"],
  ["ask", "Ask P&O AI", "ask"], ["import", "Import data", "import"], ["settings", "Settings", "settings"]];
const NAV_GROUP = { retention: "Insights", ask: "Tools" };
const FILTER_PAGES = new Set(["home", "people", "performance", "stores", "store", "attendance", "org"]);
const PAGE_TITLE = { home: "Overview", review: "Business review", stores: "Stores", store: "Store", people: "People", performance: "Performance",
  talent: "Leaders & talent", attendance: "Attendance", org: "Org chart", retention: "Turnover", nps: "Customer NPS", shifts: "Shift roster",
  data: "Other data", ask: "Ask P&O AI", import: "Import data", settings: "Settings" };
const ROLES = [["", "Everyone"], ["MANAGERS", "All managers"], ["GM", "Store managers"], ["DH", "Department heads"], ["SM", "Section managers"],
  ["CCO", "CCO"], ["HBM", "H&B leads"], ["STAFF", "Staff"]];
const BANDS = [["excellent", "Outstanding"], ["good", "Strong"], ["ok", "Meets"], ["warn", "Needs improvement"], ["bad", "Concern"]];

/* ---------------------------------------------------------------- helpers */
const initials = n => String(n || "?").split(/\s+/).filter(w => w && !/^muhammad$/i.test(w)).slice(0, 2).map(w => w[0]).join("").toUpperCase() || "?";
const scoreTxt = v => v == null ? "—" : (+v).toFixed(1);
const pct = (v, d = 0) => v == null ? "—" : (+v).toFixed(d) + "%";
const money = v => v == null ? "—" : Math.round(v).toLocaleString("en-US");
const pill = (v, band) => `<span class="score-pill b-${band || "none"}">${scoreTxt(v)}</span>`;
const fmtDate = d => { if (!d) return "—"; const x = new Date(d + "T00:00:00"); return x.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }); };
const delta = (d, good, fmt) => {
  if (d == null) return "";
  const up = d > 0.0499, down = d < -0.0499;
  const cls = !up && !down ? "flat" : ((up && good === "up") || (down && good === "down")) ? "up" : good ? "down" : "flat";
  const v = fmt === "int" ? Math.round(d).toLocaleString("en-US") : Math.abs(d).toFixed(1) + (fmt && fmt.startsWith("pct") ? " pts" : "");
  return `<span class="delta ${cls}">${up ? "▲" : down ? "▼" : "•"} ${fmt === "int" ? (d > 0 ? "+" : "") + v : v}</span>`;
};
const statusChip = p => p.status === "new_joiner" ? `<span class="chip info">New joiner</span>` : p.status === "not_enough_data" ? `<span class="chip">Not enough data</span>` : "";
function toast(msg, opts = {}) {
  const t = document.createElement("div");
  t.className = "toast" + (opts.err ? " err" : "");
  t.innerHTML = `<span>${esc(msg)}</span>` + (opts.action ? `<button>${esc(opts.action)}</button>` : "");
  if (opts.action) t.querySelector("button").onclick = () => { opts.onAction(); t.remove(); };
  $("#toasts").appendChild(t);
  setTimeout(() => { t.style.transition = "opacity .3s"; t.style.opacity = "0"; setTimeout(() => t.remove(), 320); }, opts.ms || 3800);
}
const fail = e => toast(e.message || String(e), { err: true, ms: 6000 });
async function call(m, p) { try { return await API.call(m, p); } catch (e) { fail(e); e.shown = true; throw e; } }
const req = (extra = {}) => ({ month: S.month, scope: S.scope, ...extra });

/* ---------------------------------------------------------------- shell */
function sideHtml() {
  return `
    <div class="brand"><div class="logo maf"><img src="maf-mark.png" alt="Majid Al Futtaim"></div><div><b>P&amp;O</b><small>People &amp; Organisation</small></div></div>
    <nav class="nav" id="nav">${NAV.map(([k, l, i]) => (NAV_GROUP[k] ? `<div class="nav-label">${NAV_GROUP[k]}</div>` : "") +
      `<button data-go="${k}" ${S.page === k || (S.page === "store" && k === "stores") ? 'aria-current="page"' : ""}>${ic(i)}<span>${l}</span>${k === "settings" && S.init && S.init.unsure_stores ? `<span class="badge">${S.init.unsure_stores}</span>` : ""}</button>`).join("")}</nav>
    <div class="side-foot">
      ${S.init && S.init.demo ? `<button class="demo-pill" data-act="demo-off" title="Return to your own data">DEMO DATA · exit</button>` : ""}
      <button class="ai-pill" data-go="settings" data-tab="ai"><span class="dot ${S.init && S.init.ai.active === "basic" ? "off" : ""}"></span><span>${esc(S.init ? S.init.ai.label : "AI")}</span></button>
      <span>Offline · data stays on this PC</span><span>v${esc(S.init ? S.init.version : "")}</span>
    </div>
  `;
}
function shell() {
  if ($("#view") && $(".side")) { updateSide(); topbar(); return; }     // built once; later only parts are refreshed
  $("#app").innerHTML = `
  <aside class="side">${sideHtml()}</aside>
  <div class="main">
    <header class="top" id="top"></header>
    <div class="view" id="view"></div>
    <div class="present-bar"><button class="btn sm" data-act="present-prev">▲</button><button class="btn sm" data-act="present-next">▼</button><button class="btn sm" data-act="present">Exit</button></div>
  </div>`;
  topbar();
}
function updateSide() { const sd = $(".side"); if (sd) sd.innerHTML = sideHtml(); }

function topbar() {
  const o = S.opts || {};
  const sel = (key, label, list, all) => `<div class="fsel ${S.scope[key] ? "set" : ""}"><label>${label}</label><select data-scope="${key}">
      <option value="">${all}</option>${(list || []).map(x => `<option value="${esc(x.value)}" ${String(S.scope[key] || "") === String(x.value) ? "selected" : ""}>${esc(x.label)}</option>`).join("")}</select></div>`;
  const months = S.months || [];
  const crumbs = ["Pakistan"];
  const lbl = (list, v) => (list || []).find(x => String(x.value) === String(v));
  if (S.scope.city) crumbs.push(["city", (lbl(o.cities, S.scope.city) || {}).label || S.scope.city]);
  if (S.scope.format) crumbs.push(["format", (lbl(o.formats, S.scope.format) || {}).label || S.scope.format]);
  if (S.scope.store_id) crumbs.push(["store_id", (lbl(o.stores, S.scope.store_id) || {}).label || "Store"]);
  if (S.scope.dept) crumbs.push(["dept", (lbl(o.depts, S.scope.dept) || {}).label || S.scope.dept]);
  if (S.scope.section) crumbs.push(["section", S.scope.section]);
  const filters = FILTER_PAGES.has(S.page);
  const back = (S.hist || []).length ? `<button class="btn back" data-act="back" title="Back (Alt+←)">${ic("back", 16)}Back</button>` : "";
  $("#top").innerHTML = `
    <div class="top-row">
      ${back}
      ${filters ? "" : `<div class="crumbs"><span class="ptitle">${esc(PAGE_TITLE[S.page] || "")}</span></div>`}
      <div class="crumbs" ${filters ? "" : 'style="display:none"'}>${crumbs.map((c, i) => i === 0 ? `<button data-act="scope-clear">🇵🇰 Pakistan</button>` : `<span class="sep">›</span>${i === crumbs.length - 1 ? `<span>${esc(c[1])}</span>` : `<button data-act="scope-up" data-key="${c[0]}">${esc(c[1])}</button>`}`).join("")}</div>
      <div class="spacer"></div>
      <div class="search hide-present">${ic("search", 16)}<input id="q" placeholder="Search people or stores  (Ctrl+K)" autocomplete="off"><div id="sugg"></div></div>
      ${["ask", "import", "settings", "data"].includes(S.page) ? "" : `<button class="btn" data-act="export">${ic("export", 16)}Export</button>
      <button class="btn gold hide-present" data-act="present">${ic("play", 14)}Present</button>`}
    </div>
    <div class="top-row filters" ${filters ? "" : 'style="display:none"'}>
      ${sel("city", "City", o.cities, "All cities")}${sel("store_id", "Store", o.stores, "All stores")}${sel("dept", "Dept", o.depts, "All departments")}
      <span class="${S.moreFilters ? "" : "more-off"}" style="display:contents">${sel("format", "Format", o.formats, "All formats")}${sel("section", "Section", o.sections, "All sections")}</span>
      <button class="btn sm ghost" data-act="more-filters">${S.moreFilters ? "Fewer filters" : "More filters"}</button>
      <div class="spacer"></div>
      <div class="fsel"><label>Month</label><select id="month">${months.map(m => `<option value="${m.value}" ${m.value === S.month ? "selected" : ""}>${esc(m.label)}</option>`).join("") || "<option>No data yet</option>"}</select></div>
      <div class="fsel ${S.moreFilters ? "" : "more-off"}"><label>Compare</label><select id="compare"><option value="">Previous month</option>${months.filter(m => m.value !== S.month).map(m => `<option value="${m.value}" ${m.value === S.compare ? "selected" : ""}>${esc(m.label)}</option>`).join("")}</select></div>
    </div>`;
  $$("select[data-scope]").forEach(s => s.onchange = () => setScope(s.dataset.scope, s.value));
  const ms = $("#month"); if (ms) ms.onchange = () => { S.month = ms.value; S.compare = null; refreshOptions().then(render); };
  const cs = $("#compare"); if (cs) cs.onchange = () => { S.compare = cs.value || null; render(); };
  wireSearch();
}

async function setScope(key, value) {
  const downstream = { city: ["store_id", "section"], format: ["store_id", "section"], store_id: ["section"], dept: ["section"], section: [] };
  if (value === "" || value == null) delete S.scope[key]; else S.scope[key] = key === "store_id" ? +value : value;
  (downstream[key] || []).forEach(k => delete S.scope[k]);
  store.set("scope", S.scope);
  await refreshOptions();
  render();
}

async function refreshOptions() {
  if (!S.month) { S.opts = {}; topbar(); return; }
  try { S.opts = await API.call("options", { month: S.month, scope: S.scope }); } catch (e) { S.opts = {}; }
  // drop filters that no longer exist in this month
  const ok = (k, list) => !S.scope[k] || (list || []).some(x => String(x.value) === String(S.scope[k]));
  for (const [k, l] of [["city", "cities"], ["format", "formats"], ["store_id", "stores"], ["dept", "depts"], ["section", "sections"]]) if (!ok(k, S.opts[l])) delete S.scope[k];
  topbar();
}

function wireSearch() {
  const q = $("#q"), box = $("#sugg");
  if (!q) return;
  let t = null, items = [], on = -1;
  const close = () => { box.innerHTML = ""; items = []; on = -1; };
  q.oninput = () => {
    clearTimeout(t);
    t = setTimeout(async () => {
      const v = q.value.trim();
      if (v.length < 2) return close();
      let r; try { r = await API.call("search", { q: v, month: S.month }); } catch (e) { return close(); }
      items = [...r.people.map(p => ({ k: "p", id: p.emp, a: p.name, b: p.sub })), ...r.stores.map(s => ({ k: "s", id: s.store_id, a: s.name, b: s.sub }))];
      box.innerHTML = items.length ? `<div class="sugg">${r.people.length ? '<div class="sh">People</div>' : ""}${items.map((x, i) => (x.k === "s" && (i === 0 || items[i - 1].k === "p") ? '<div class="sh">Stores</div>' : "") +
        `<button data-i="${i}"><b>${esc(x.a)}</b><small>${esc(x.b)}</small></button>`).join("")}</div>` : `<div class="sugg"><div class="empty" style="padding:14px">Nothing found</div></div>`;
      $$("button", box).forEach(b => b.onmousedown = e => { e.preventDefault(); pick(items[+b.dataset.i]); });
    }, 140);
  };
  q.onkeydown = e => {
    const bs = $$("button", box);
    if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); on = Math.max(0, Math.min(bs.length - 1, on + (e.key === "ArrowDown" ? 1 : -1))); bs.forEach((b, i) => b.classList.toggle("on", i === on)); }
    if (e.key === "Enter" && items.length) pick(items[on < 0 ? 0 : on]);
    if (e.key === "Escape") { close(); q.blur(); }
  };
  q.onblur = () => setTimeout(close, 150);
  const pick = x => { close(); q.value = ""; if (!x) return; if (x.k === "p") openPerson(x.id); else go("store", x.id); };
}

/* ---------------------------------------------------------------- routing */
function go(page, arg = null, opts = {}) {
  if (!opts.back && S.page && (S.page !== page || S.arg !== arg)) { S.hist = (S.hist || []).concat([[S.page, S.arg]]).slice(-30); }
  S.page = page; S.arg = arg;
  topbar();
  $$("#nav button").forEach(b => b.toggleAttribute("aria-current", b.dataset.go === (page === "store" ? "stores" : page)));
  $$("#nav button[aria-current]").forEach(b => b.setAttribute("aria-current", "page"));
  store.set("page", page === "store" ? "stores" : page);
  render();
}
window.go = go;

const PERIOD_PAGES = ["review", "talent", "retention", "shifts", "nps"];
async function render() {
  const view = $("#view");
  if (!view) return;
  const token = ++S.busy;
  const page = S.page, arg = S.arg;
  const cur = view.firstElementChild;
  const same = cur && cur.dataset.page === page && S.shownArg === arg;   // a refresh of the screen already shown
  // keep what is on screen while the data loads; only a slow load shows a spinner (no blank flash)
  if (cur) cur.classList.add("stale");
  const slow = setTimeout(() => { if (token === S.busy && !same) view.innerHTML = `<div class="page"><div class="loading"><span class="spin"></span>Loading…</div></div>`; }, 260);
  try {
    if (PERIOD_PAGES.includes(page)) DATA[page] = null;
    let html = await (PAGES[page] || PAGES.home)(arg);
    if (token !== S.busy) return;
    const pd = PERIOD_PAGES.includes(page) && DATA[page];
    if (pd && pd.period) {
      DATA.period = pd.period;
      if (!pd.has_data && pd.period.view && pd.period.view.type !== "latest")
        html = `<div class="ph"><div><h1>${esc(PAGE_TITLE[page] || "")}</h1></div></div><div class="panel"><div class="empty">Nothing in this tab for <b>${esc(pd.period.label)}</b>. Pick another period above, or import data for it.</div></div>`;
    }
    view.innerHTML = `<div class="page${same ? "" : " enter"}" data-page="${page}">${html}</div>`;
    if (pd && pd.period) {
      const pg = view.firstElementChild, ph = pg.querySelector(":scope > .ph");
      if (ph) ph.insertAdjacentHTML("afterend", periodBar(pd.period)); else pg.insertAdjacentHTML("afterbegin", periodBar(pd.period));
    }
    if (!same) view.scrollTop = 0;
    S.shownArg = arg;
    const after = AFTER[page]; if (after) after();
  } catch (e) {
    if (token !== S.busy) return;
    view.innerHTML = `<div class="page" data-page="${page}"><div class="errbox">${esc(e.message || e)}</div></div>`;
  } finally {
    clearTimeout(slow);
  }
}

/* ---------------------------------------------------------------- pages */
const PAGES = {}, AFTER = {};
let DATA = {};

function noData() {
  return `<div class="panel"><div class="hero">
    <div class="logo maf big"><img src="maf-logo.png" alt="Majid Al Futtaim"></div>
    <h2>Welcome to P&amp;O</h2>
    <p>Bring in your reports to see people, attendance and performance in one place: the employee roster, the biometric attendance (MTD),
    the section productivity report (MTD or YTD) and the BO 200-10-05 store net sales report. Everything stays on this PC.</p>
    <div class="row" style="justify-content:center"><button class="btn primary" data-go="import">${ic("import", 16)}Import reports</button>
    <button class="btn" data-act="demo-on">${ic("spark", 16)}Try with demo data</button></div></div></div>`;
}

PAGES.home = async () => {
  if (!S.month) return noData();
  const d = DATA.home = await API.call("dashboard", req({ compare: S.compare }));
  if (!d.has_data) return noData();
  const cards = d.cards.map(c => {
    const val = c.fmt === "score" ? `${scoreTxt(c.value)}<small>/10</small>` : c.fmt === "int" ? (c.value ?? 0).toLocaleString("en-US") : c.fmt === "pct" ? pct(c.value, 1) : pct(c.value);
    const target = { headcount: "people", absence: "attendance", score: "performance", sales: "stores", productivity: "stores" }[c.key];
    return `<button class="kpi" data-go="${target}"><span class="kpi-l">${esc(c.label)}</span><span class="kpi-v">${c.value == null ? "—" : val}</span>
      <span class="kpi-s">${delta(c.delta, c.good, c.fmt)}<span>${esc(c.sub || "")}</span></span></button>`;
  }).join("");
  const plist = (rows, start = 1) => rows.length ? rows.map((p, i) => `<button class="prow" data-person="${p.emp}"><span class="rank">${start + i}</span><span class="av">${esc(initials(p.name))}</span>
      <span class="who"><b>${esc(p.name)}</b><small>${esc(p.role_label)} · ${esc(p.store)}</small></span>${pill(p.score, p.band_key)}</button>`).join("") : `<div class="empty">No scores yet</div>`;
  const alerts = d.alerts.length ? d.alerts.map(a => `<button class="alert ${a.level}" data-act="alert" data-key="${a.key}"><span class="ic">${a.level === "bad" ? "!" : a.level === "warn" ? "•" : "i"}</span>
      <span><b>${esc(a.text)}</b>${a.items ? `<small style="display:block;color:var(--muted)">${esc(a.items.slice(0, 3).join(" · "))}${a.items.length > 3 ? " …" : ""}</small>` : ""}</span></button>`).join("")
    : `<div class="empty" style="padding:18px">Nothing needs attention 🎉</div>`;
  return `
    <div class="ph slide"><div><h1>${esc(d.scope_label.split(" › ").pop())} · ${esc(d.month_label)}</h1>
      <p>Data up to ${fmtDate(d.as_of)}${d.complete ? " · complete month" : ` · day ${d.data_days}`}${d.compare ? ` · compared with ${esc((S.months.find(m => m.value === d.compare) || {}).label || d.compare)}` : ""}</p></div>
      ${d.provisional ? `<span class="chip warn">Provisional: early in the month</span>` : ""}</div>
    ${d.warnings.map(w => `<div class="banner warn">${esc(w)}</div>`).join("")}
    <div class="kpis stagger k5">${cards}</div>
    <div class="grid g32 slide stagger">
      <div class="panel"><div class="phd"><h2>Store league</h2><small>Average score of everyone in the store · click a store to focus</small></div><div id="ch-league"></div></div>
      <div class="panel"><div class="phd"><h2>Score bands</h2><small>Click a band to see the people</small></div><div id="ch-dist"></div>
        <div class="legend">${BANDS.map(([k, l]) => `<span><i class="b-${k}"></i>${l}</span>`).join("")}</div></div>
    </div>
    <div class="grid g3 slide stagger">
      <div class="panel"><div class="phd"><h2>Top performers</h2><button class="btn sm ghost" data-act="people-sort" data-desc="1">See all</button></div><div class="plist">${plist(d.top)}</div></div>
      <div class="panel"><div class="phd"><h2>Needs attention</h2><button class="btn sm ghost" data-act="people-sort" data-desc="0">See all</button></div><div class="plist">${plist(d.bottom)}</div></div>
      <div class="panel"><div class="phd"><h2>Things to know</h2></div><div style="display:flex;flex-direction:column;gap:8px">${alerts}</div></div>
    </div>
    <div class="grid g3 slide stagger">
      <div class="panel"><div class="phd"><h2>Average score</h2><small>out of 10</small></div><div id="ch-t1"></div></div>
      <div class="panel"><div class="phd"><h2>Real absence</h2><small>System shows ${pct(d.attendance.system_absence_pct, 1)}</small></div><div id="ch-t2"></div></div>
      <div class="panel"><div class="phd"><h2>Sales vs budget</h2><small>Total store, % of budget</small></div><div id="ch-t3"></div></div>
    </div>`;
};
AFTER.home = () => {
  const d = DATA.home;
  if (!d || !$("#ch-league")) return;
  const lg = d.league.slice(0, 18);
  Charts.hbar($("#ch-league"), { labels: lg.map(r => r.store + (r.format ? " · " + r.format : "")), values: lg.map(r => r.score), fmt: "score", max: 10, name: "Average score",
    colors: lg.map(r => `var(--${band(r.score)})`), tips: lg.map(r => `GM ${r.gm || "—"} ${scoreTxt(r.gm_score)} · sales ${pct(r.sales_pct)} of budget · absence ${pct(r.absence_pct, 1)}`),
    onClick: i => setScope("store_id", lg[i].store_id) });
  Charts.columns($("#ch-dist"), { labels: d.distribution.map(x => x.label.replace("Meets expectation", "Meets").replace("Needs improvement", "Needs impr.")), tipLabels: d.distribution.map(x => x.label),
    series: [{ name: "People", values: d.distribution.map(x => x.count), colors: d.distribution.map(x => `var(--${x.key})`) }], height: 230,
    onClick: i => { S.people = { ...S.people, band: d.distribution[i].key, flag: "" }; go("people"); } });
  const lab = d.trend.map(t => t.label);
  Charts.line($("#ch-t1"), { labels: lab, series: [{ name: "Average score", values: d.trend.map(t => t.score) }], fmt: "score", height: 170, area: true });
  Charts.line($("#ch-t2"), { labels: lab, series: [{ name: "Real absence", values: d.trend.map(t => t.absence), color: "var(--s2)" }], fmt: "pct", height: 170, area: true });
  Charts.line($("#ch-t3"), { labels: lab, series: [{ name: "Sales vs budget", values: d.trend.map(t => t.sales), color: "var(--s3)" }], fmt: "pct0", height: 170, ref: 100, refLabel: "Budget", area: true });
};
function band(v) { return v == null ? "none" : v >= 9 ? "excellent" : v >= 7.5 ? "good" : v >= 6 ? "ok" : v >= 4 ? "warn" : "bad"; }

/* people: long lists are drawn in chunks as you scroll, so the screen opens instantly */
const PEOPLE_CHUNK = 80;
const compareBtn = () => S.selected.size >= 2 ? `<button class="btn primary" data-act="compare">Compare ${S.selected.size}</button>` : "";
function drawCompareBtn() { const b = $("#cmpbtn"); if (b) b.innerHTML = compareBtn(); }
const personRow = p => `<tr class="click" data-person="${p.emp}"><td><input type="checkbox" data-sel="${p.emp}" ${S.selected.has(p.emp) ? "checked" : ""}></td>
        <td><b>${esc(p.name)}</b><span class="sub">${esc(p.designation)} · ${esc(p.emp)}</span></td><td>${esc(p.role_label)}</td><td>${esc(p.store)}<span class="sub">${esc(p.format || "")}</span></td>
        <td>${esc(p.dept || "—")}<span class="sub">${esc(p.section || "")}</span></td><td class="n">${p.score == null ? statusChip(p) || "—" : pill(p.score, p.band_key)}${p.provisional && p.score != null ? '<span class="sub">provisional</span>' : ""}</td>
        <td class="n">${p.delta == null ? "" : delta(p.delta, "up")}</td><td class="n">${scoreTxt(p.attendance)}</td><td class="n">${p.absent ?? "—"}</td><td class="n">${p.fixes || ""}</td></tr>`;
PAGES.people = async () => {
  if (!S.month) return noData();
  const P = S.people;
  const d = DATA.people = await API.call("people", req({ q: P.q, role: P.role, band: P.band, sort: P.sort, desc: P.desc, flag: P.flag, limit: 600 }));
  const counts = Object.fromEntries(d.roles.map(r => [r.value, r.count]));
  const total = d.roles.reduce((a, r) => a + r.count, 0);
  const th = (k, l, n) => `<th class="sort ${n ? "n" : ""}" data-act="sort" data-key="${k}">${l}${P.sort === k ? (P.desc ? " ↓" : " ↑") : ""}</th>`;
  const flagName = { long_absence: "Absent 7+ days in a row", fixes: "Has punches to fix", managers: "Reporting line to confirm", new_joiners: "New joiners" }[P.flag];
  return `<div class="ph"><div><h1>People</h1><p>${d.total.toLocaleString("en-US")} people · ${esc(S.months.find(m => m.value === d.month)?.label || "")}. Click anyone to open their profile.</p></div>
      <div class="actions"><span id="cmpbtn">${compareBtn()}</span><button class="btn" data-go="performance">${ic("perf", 16)}Rankings by role</button><button class="btn" data-go="org">${ic("org", 16)}Org chart</button><button class="btn" data-act="export" data-pack="people">${ic("export", 16)}Export list</button></div></div>
    <div class="panel"><div class="row">
      <div class="search" style="flex:1 1 260px;max-width:none">${ic("search", 16)}<input id="pq" placeholder="Name, employee number, designation or store" value="${esc(P.q)}"></div>
      <div class="seg">${ROLES.map(([k, l]) => `<button data-act="role" data-role="${k}" aria-pressed="${P.role === k}">${l}<span class="c">${k === "" ? total : k === "MANAGERS" ? total - (counts.STAFF || 0) : counts[k] || 0}</span></button>`).join("")}</div></div>
      <div class="row"><div class="seg"><button data-act="band" data-band="" aria-pressed="${!P.band}">All bands</button>${BANDS.map(([k, l]) => `<button data-act="band" data-band="${k}" aria-pressed="${P.band === k}">${l}</button>`).join("")}</div>
      ${flagName ? `<span class="chip gold">${esc(flagName)} <button class="btn sm ghost" data-act="flag-clear" style="padding:0 4px">✕</button></span>` : ""}</div>
    </div>
    <div class="panel flush"><div class="tbl-wrap" style="max-height:calc(100vh - 330px)"><table class="t"><thead><tr><th style="width:34px"></th>
      ${th("name", "Person")}${th("role", "Role")}${th("store", "Store")}<th>Department</th>${th("score", "Score", 1)}<th class="n">Change</th>${th("attendance", "Attendance", 1)}${th("absent", "Absent days", 1)}${th("fixes", "Punches to fix", 1)}</tr></thead>
      <tbody id="ptbody">${d.rows.slice(0, PEOPLE_CHUNK).map(personRow).join("") ||
        `<tr><td colspan="10"><div class="empty">Nobody matches these filters.</div></td></tr>`}</tbody></table></div></div>`;
};
AFTER.people = () => {
  const wrap = $('[data-page="people"] .tbl-wrap'), body = $("#ptbody"), rows = DATA.people ? DATA.people.rows : [];
  if (wrap && body) {
    let shown = Math.min(PEOPLE_CHUNK, rows.length);
    const more = () => {
      if (shown >= rows.length || wrap.scrollTop + wrap.clientHeight < wrap.scrollHeight - 600) return;
      body.insertAdjacentHTML("beforeend", rows.slice(shown, shown + 120).map(personRow).join(""));
      shown = Math.min(shown + 120, rows.length);
    };
    wrap.addEventListener("scroll", more, { passive: true });
  }
  const q = $("#pq"); let t;
  if (q) { q.oninput = () => { clearTimeout(t); t = setTimeout(() => { S.people.q = q.value; render().then(() => { const n = $("#pq"); if (n) { n.focus(); n.setSelectionRange(n.value.length, n.value.length); } }); }, 260); }; }
  if (body) body.addEventListener("click", e => {          // one listener also covers rows added while scrolling
    const c = e.target.closest("[data-sel]"); if (!c) return;
    e.stopPropagation();
    c.checked ? S.selected.add(c.dataset.sel) : S.selected.delete(c.dataset.sel);
    if (S.selected.size > 4) { S.selected.delete(c.dataset.sel); c.checked = false; toast("Compare up to 4 people at a time."); }
    drawCompareBtn();
  });
};

/* performance */
PAGES.performance = async () => {
  if (!S.month) return noData();
  const role = S.perfRole;
  const d = DATA.perf = await API.call("people", req({ role, sort: "score", desc: true, limit: 200 }));
  const rows = d.rows.filter(r => r.score != null);
  return `<div class="ph"><div><h1>Performance</h1><p>Ranking by role on the KPIs each role controls. ▲▼ shows the change since last month.</p></div>
    <button class="btn" data-act="export" data-pack="scorecard">${ic("export", 16)}Manager scorecards</button></div>
    <div class="seg">${ROLES.filter(r => r[0] && r[0] !== "MANAGERS").map(([k, l]) => `<button data-act="perf-role" data-role="${k}" aria-pressed="${role === k}">${l}</button>`).join("")}</div>
    <div class="grid g23">
      <div class="panel"><div class="phd"><h2>Score by person</h2><small>${rows.length} scored</small></div><div id="ch-perf"></div></div>
      <div class="panel flush"><div class="tbl-wrap" style="max-height:calc(100vh - 290px)"><table class="t"><thead><tr><th>#</th><th>Person</th><th>Store</th><th class="n">Score</th><th class="n">Change</th><th class="n">Measured on</th></tr></thead>
      <tbody>${rows.map((p, i) => `<tr class="click" data-person="${p.emp}"><td class="n">${i + 1}</td><td><b>${esc(p.name)}</b><span class="sub">${esc(p.designation)}</span></td><td>${esc(p.store)}</td>
        <td class="n">${pill(p.score, p.band_key)}</td><td class="n">${p.delta == null ? "" : delta(p.delta, "up")}</td><td class="n">${p.coverage}%</td></tr>`).join("") || `<tr><td colspan="6"><div class="empty">No scored people for this role and filter.</div></td></tr>`}</tbody></table></div></div>
    </div>`;
};
AFTER.performance = () => {
  const rows = (DATA.perf.rows || []).filter(r => r.score != null).slice(0, 30);
  if ($("#ch-perf")) Charts.hbar($("#ch-perf"), { labels: rows.map(r => r.name), values: rows.map(r => r.score), max: 10, fmt: "score", name: "Score",
    colors: rows.map(r => `var(--${r.band_key})`), tips: rows.map(r => `${r.designation} · ${r.store}`), onClick: i => openPerson(rows[i].emp) });
};

/* stores */
PAGES.stores = async () => {
  if (!S.month) return noData();
  const d = await API.call("stores", req());
  return `<div class="ph"><div><h1>Stores</h1><p>${d.rows.length} stores · average score of everyone in the store, with the store manager's own score.</p></div>
    <button class="btn" data-act="export" data-pack="director">${ic("export", 16)}Export</button></div>
    <div class="stores stagger">${d.rows.map(r => `<button class="scard" data-act="store" data-id="${r.store_id}">
      <div class="top2">${Charts.ring(r.score, 62, band(r.score))}<div style="min-width:0"><h3>${esc(r.store)} <span class="fmt">${esc(r.format || "")}</span></h3>
      <small style="color:var(--muted)">${esc(r.gm ? "GM " + r.gm : "No store manager in roster")}${r.gm_score != null ? " · " + scoreTxt(r.gm_score) : ""}</small><br><small style="color:var(--muted)">${r.people} people</small></div></div>
      <div class="meta"><div><small>Sales</small><b>${pct(r.sales_pct)}</b></div><div><small>Productivity</small><b>${pct(r.prod_pct)}</b></div><div><small>Absence</small><b>${pct(r.absence_pct, 1)}</b></div></div></button>`).join("") || `<div class="empty">No stores in this filter.</div>`}</div>`;
};

PAGES.store = async id => {
  const d = DATA.store = await API.call("store", { store_id: id, month: S.month });
  const t = d.total || {};
  const comp = (d.gm_components || []).map(compRow).join("");
  const secRows = rows => rows.map(r => `<tr><td><b>${esc(r.code)}</b> ${esc(r.name)}</td><td>${esc(r.managers.join(", ") || "—")}</td><td class="n">${money(r.actual)}</td>
    <td class="n"><div class="bar-cell"><div class="track"><div class="fill" style="width:${Math.min(100, (r.sales_pct || 0) / 1.3)}%;background:${(r.sales_pct || 0) >= 100 ? "var(--good)" : "var(--warn)"}"></div></div>${pct(r.sales_pct)}</div></td>
    <td class="n">${r.growth == null ? "—" : (r.growth > 0 ? "+" : "") + r.growth.toFixed(1) + "%"}</td><td class="n">${pct(r.waste, 1)}</td><td class="n">${pct(r.oos, 1)}</td><td class="n">${pct(r.prod_pct)}</td></tr>`).join("");
  return `<div class="ph"><div><button class="btn sm ghost" data-go="stores">${ic("back", 14)} Stores</button><h1 style="margin-top:6px">${esc(d.store)} <span class="fmt">${esc(d.format)}</span></h1>
    <p>${esc(d.format_label)} · ${esc(d.city)}${d.code ? " · store " + esc(d.code) : ""} · ${esc(d.month_label)}${d.sales_as_of ? " · sales up to " + fmtDate(d.sales_as_of) : ""}</p></div>
    <div class="actions"><button class="btn" data-act="focus-store" data-id="${d.store_id}">Focus dashboard on this store</button><button class="btn primary" data-act="export" data-pack="store" data-store="${d.store_id}">${ic("export", 16)}Store report</button></div></div>
    <div class="kpis stagger">
      <div class="kpi"><span class="kpi-l">Store score</span><span class="kpi-v">${scoreTxt(d.score)}<small>/10</small></span><span class="kpi-s">${d.people} people</span></div>
      <div class="kpi"><span class="kpi-l">Sales vs budget</span><span class="kpi-v">${pct(t.sales_pct)}</span><span class="kpi-s">${money(t.actual)} · ${t.growth == null ? "" : (t.growth > 0 ? "+" : "") + t.growth.toFixed(1) + "% vs LY"}</span></div>
      <div class="kpi"><span class="kpi-l">Real absence</span><span class="kpi-v">${pct(d.attendance.absence_pct, 1)}</span><span class="kpi-s">System ${pct(d.attendance.system_absence_pct, 1)} · ${d.attendance.fixes} punches to fix</span></div>
      <div class="kpi"><span class="kpi-l">Full 9h days</span><span class="kpi-v">${pct(d.attendance.compliance_pct)}</span><span class="kpi-s">${d.attendance.long_absence} long absences</span></div>
    </div>
    <div class="grid g2">
      <div class="panel"><div class="phd"><h2>Store manager</h2>${d.gm ? `<button class="btn sm" data-person="${d.gm.emp}">Open profile</button>` : ""}</div>
        ${d.gm ? `<div class="row">${Charts.ring(d.gm.score, 70, d.gm.band_key)}<div><b style="font-size:16px">${esc(d.gm.name)}</b><br><small style="color:var(--muted)">${esc(d.gm.designation)} · ${esc(d.gm.band)}</small></div></div>${comp}` : `<div class="empty">No store manager in the roster for this store.</div>`}</div>
      <div class="panel"><div class="phd"><h2>Managers</h2><small>${d.managers.length}</small></div><div class="plist">${d.managers.map(p => `<button class="prow" data-person="${p.emp}"><span class="av">${esc(initials(p.name))}</span><span class="who"><b>${esc(p.name)}</b><small>${esc(p.designation)} · ${esc(p.role_label)}</small></span>${pill(p.score, p.band_key)}</button>`).join("") || '<div class="empty">No managers found.</div>'}</div></div>
    </div>
    ${d.departments.length ? `<div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Departments</h2></div><div class="tbl-wrap"><table class="t"><thead><tr><th>Department</th><th>Head</th><th class="n">Sales</th><th class="n">vs budget</th><th class="n">Growth</th><th class="n">Waste</th><th class="n">OOS</th><th class="n">Productivity</th></tr></thead><tbody>${secRows(d.departments)}</tbody></table></div></div>` : ""}
    ${d.sections.length ? `<div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Sections and their managers</h2><small>Growth is context only (not scored)</small></div><div class="tbl-wrap"><table class="t"><thead><tr><th>Section</th><th>Manager</th><th class="n">Sales</th><th class="n">vs budget</th><th class="n">Growth</th><th class="n">Waste</th><th class="n">OOS</th><th class="n">Productivity</th></tr></thead><tbody>${secRows(d.sections)}</tbody></table></div></div>` : `<div class="banner">No BO 200-10-05 sales report for this store and month.</div>`}
    <div class="grid g2">
      <div class="panel"><div class="phd"><h2>Productivity</h2><small>% of target</small></div><div id="ch-prod"></div></div>
      <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Attendance by section</h2></div><div class="tbl-wrap" style="max-height:360px"><table class="t"><thead><tr><th>Section</th><th class="n">People</th><th class="n">Real absence</th><th class="n">Full 9h</th><th class="n">To fix</th></tr></thead>
      <tbody>${d.attendance_sections.map(s => `<tr><td>${esc(s.section)}</td><td class="n">${s.people}</td><td class="n">${pct(s.absence_pct, 1)}</td><td class="n">${pct(s.compliance_pct)}</td><td class="n">${s.fixes || ""}</td></tr>`).join("")}</tbody></table></div></div>
    </div>`;
};
AFTER.store = () => {
  const pr = (DATA.store.productivity || []).filter(p => p.pct != null);
  if ($("#ch-prod")) Charts.hbar($("#ch-prod"), { labels: pr.map(p => p.row), values: pr.map(p => p.pct), fmt: "pct0", ref: 100, name: "% of target",
    colors: pr.map(p => p.pct >= 100 ? "var(--good)" : p.pct >= 90 ? "var(--ok)" : "var(--warn)"), tips: pr.map(p => `actual ${fmtv(p.actual)} · target ${fmtv(p.target)} · LY ${fmtv(p.ly)}`) });
};

/* attendance */
PAGES.attendance = async () => {
  if (!S.month) return noData();
  const d = DATA.att = await API.call("attendance", req());
  const t = d.totals;
  const tabs = [["fixes", `Punches to fix (${d.fixes.length})`], ["long", `Long absences (${d.long_absence.length})`], ["low", "Lowest 9h compliance"], ["store", "By store"], ["register", `Register (${d.register.length})`]];
  const kinds = { missing_in: ["Missing IN", "warn"], missing_out: ["Missing OUT", "warn"], punched_absent: ["Punched but marked absent", "bad"] };
  const tab = S.attTab;
  let body = "";
  if (tab === "fixes") body = `<table class="t"><thead><tr><th>Store</th><th>Person</th><th>Date</th><th>Problem</th><th>IN</th><th>OUT</th><th class="n">Hours from punches</th></tr></thead><tbody>${d.fixes.slice(0, 1500).map(f => `<tr class="click" data-person="${f.emp}"><td>${esc(f.store)}</td><td><b>${esc(f.name)}</b><span class="sub">${esc(f.section)}</span></td><td>${fmtDate(f.day)}</td><td><span class="chip ${kinds[f.kind][1]}">${kinds[f.kind][0]}</span></td><td>${f.t_in || "—"}</td><td>${f.t_out || "—"}</td><td class="n">${f.hours || "—"}</td></tr>`).join("") || `<tr><td colspan="7"><div class="empty">No missing punches 🎉</div></td></tr>`}</tbody></table>`;
  else if (tab === "long") body = peopleAtt(d.long_absence, true);
  else if (tab === "low") body = peopleAtt(d.low_compliance);
  else if (tab === "register") body = peopleAtt(d.register);
  else body = `<table class="t"><thead><tr><th>Store</th><th class="n">People</th><th class="n">Real absence</th><th class="n">System absence</th><th class="n">Full 9h days</th><th class="n">Avg day</th><th class="n">To fix</th><th class="n">Long absences</th></tr></thead><tbody>${d.by_store.map(s => `<tr class="click" data-act="store" data-id="${s.store_id}"><td><b>${esc(s.store)}</b> <span class="fmt">${esc(s.format)}</span></td><td class="n">${s.people}</td><td class="n">${pct(s.absence_pct, 1)}</td><td class="n">${pct(s.system_absence_pct, 1)}</td><td class="n">${pct(s.compliance_pct)}</td><td class="n">${s.avg_minutes ? Math.floor(s.avg_minutes / 60) + ":" + String(s.avg_minutes % 60).padStart(2, "0") : "—"}</td><td class="n">${s.fixes}</td><td class="n">${s.long_absence}</td></tr>`).join("")}</tbody></table>`;
  return `<div class="ph"><div><h1>Attendance</h1><p>${esc(d.month_label)} up to ${fmtDate(d.as_of)}. Real absence leaves out weekly offs (1 a week; Sat–Sun for head office), gazetted holidays and booked leave. Missing punches count as worked but need fixing.</p></div>
    <button class="btn" data-act="export" data-pack="attendance">${ic("export", 16)}Attendance exceptions</button></div>
    <div class="kpis stagger">
      <div class="kpi"><span class="kpi-l">Real absence</span><span class="kpi-v">${pct(t.absence_pct, 1)}</span><span class="kpi-s">${t.absent.toLocaleString("en-US")} days of ${t.due.toLocaleString("en-US")} due</span></div>
      <div class="kpi"><span class="kpi-l">System says</span><span class="kpi-v">${pct(t.system_absence_pct, 1)}</span><span class="kpi-s">Counts offs, leave and missing punches as absent</span></div>
      <div class="kpi"><span class="kpi-l">Full 9-hour days</span><span class="kpi-v">${pct(t.compliance_pct)}</span><span class="kpi-s">Average day ${t.avg_minutes ? Math.floor(t.avg_minutes / 60) + ":" + String(t.avg_minutes % 60).padStart(2, "0") : "—"} · ${t.overtime_hours.toLocaleString("en-US")} h above 9h</span></div>
      <div class="kpi"><span class="kpi-l">Punches to fix</span><span class="kpi-v">${t.fixes.toLocaleString("en-US")}</span><span class="kpi-s">${t.long_absence} people absent 7+ days in a row</span></div>
    </div>
    <div class="panel"><div class="phd"><h2>People at work each day</h2><small>Worked · absent · weekly off · leave / holiday</small></div><div id="ch-daily"></div></div>
    <div class="seg">${tabs.map(([k, l]) => `<button data-act="att-tab" data-tab="${k}" aria-pressed="${tab === k}">${l}</button>`).join("")}</div>
    <div class="panel flush"><div class="tbl-wrap" style="max-height:640px">${body}</div></div>`;
};
function peopleAtt(rows, long) {
  return `<table class="t"><thead><tr><th>Person</th><th>Store</th><th class="n">Worked</th><th class="n">Absent</th>${long ? '<th class="n">In a row</th>' : ""}<th class="n">Leave</th><th class="n">Offs</th><th class="n">System absent</th><th class="n">Full 9h</th><th class="n">Avg day</th><th class="n">Attendance</th></tr></thead>
  <tbody>${rows.map(r => `<tr class="click" data-person="${r.emp}"><td><b>${esc(r.name)}</b><span class="sub">${esc(r.designation)}</span></td><td>${esc(r.store)}</td><td class="n">${r.worked}</td><td class="n">${r.absent}</td>${long ? `<td class="n"><b>${r.longest}</b></td>` : ""}<td class="n">${r.leave}</td><td class="n">${r.off}</td><td class="n">${r.sys_absent ?? "—"}</td><td class="n">${pct(r.compliance)}</td><td class="n">${r.avg_hours || "—"}</td><td class="n">${scoreTxt(r.attendance)}</td></tr>`).join("") || `<tr><td colspan="11"><div class="empty">Nobody here.</div></td></tr>`}</tbody></table>`;
}
AFTER.attendance = () => {
  const d = DATA.att.daily;
  if ($("#ch-daily")) Charts.columns($("#ch-daily"), { labels: d.map(x => x.label), tipLabels: d.map(x => fmtDate(x.day)), height: 200, valueLabels: false,
    series: [{ name: "Worked", values: d.map(x => x.worked), color: "var(--good)" }, { name: "Absent", values: d.map(x => x.absent), color: "var(--bad)" },
      { name: "Weekly off", values: d.map(x => x.off), color: "var(--none)" }, { name: "Leave / holiday", values: d.map(x => x.leave + x.holiday), color: "var(--s2)" }] });
};

/* org chart */
PAGES.org = async () => {
  if (!S.month) return noData();
  const sts = S.opts.stores || [];
  let sid = S.scope.store_id || ((sts.find(s => s.format === "HM") || sts[0] || {}).value);
  if (!sid) return `<div class="empty">Import a roster to see the org chart.</div>`;
  const d = await API.call("org", { month: S.month, store_id: sid, auto: !S.scope.store_id });
  if (d.store_id) sid = d.store_id;
  const node = (n, depth) => `<li><div class="node ${n.role === "EXT" ? "ext" : ""}" ${n.emp ? `data-person="${n.emp}"` : ""} role="button" tabindex="0">
      ${n.children.length ? `<span class="tg" data-act="tree-toggle">${depth > 1 ? "+" : "–"}</span>` : ""}
      ${n.role === "EXT" ? "" : `<span class="av">${esc(initials(n.name))}</span>`}<span><b>${esc(n.name)}</b><small>${esc(n.designation || "")}${n.children.length ? ` · ${n.children.length} report${n.children.length > 1 ? "s" : ""}` : ""}</small></span>
      ${n.score != null ? pill(n.score, n.band) : ""}</div>${n.children.length ? `<ul ${depth > 1 ? "hidden" : ""}>${n.children.map(c => node(c, depth + 1)).join("")}</ul>` : ""}</li>`;
  return `<div class="ph"><div><h1>Org chart</h1><p>${esc((S.opts.stores.find(s => s.value == sid) || {}).label || "")} · ${d.people} people · reporting lines from the roster (matched by name within the store first).</p></div>
    <div class="actions"><div class="fsel"><label>Store</label><select data-scope="store_id">${(S.opts.stores || []).map(s => `<option value="${s.value}" ${s.value == sid ? "selected" : ""}>${esc(s.label)}</option>`).join("")}</select></div>
    <button class="btn" data-act="tree-all">Expand all</button></div></div>
    <div class="panel org">${d.tree.length ? `<ul class="tree" style="padding-left:0">${d.tree.map(n => node(n, 0)).join("")}</ul>` : `<div class="empty">Nobody from this store is in the roster for this month. Pick another store or import its roster.</div>`}</div>`;
};
AFTER.org = () => { $$(".page select[data-scope]").forEach(s => s.onchange = () => setScope("store_id", s.value)); };

/* ask: a Claude-style analyst chat */
const SUGGEST = [
  ["📊", "Brief me for the country review", "Headline numbers, best and worst stores, priorities"],
  ["🏬", "Which stores need attention and why?", "Ranked alerts from every report"],
  ["⭐", "Who are the top 10 section leaders?", "Leader index with strengths and gaps"],
  ["🚪", "Where is turnover highest and why?", "Hotspots, reasons, voluntary vs terminations"],
  ["💬", "How is customer NPS changing?", "Best and worst categories, movers"],
  ["🧭", "Compare Fortress and Emporium", "Side by side on every measure"]];
const chatStore = { list() { return store.get("chats", []); }, save(list) { store.set("chats", list.slice(0, 25)); } };
function saveChat() {
  if (!S.chat.length || S.chat.some(m => m.pending)) return;
  const list = chatStore.list().filter(c => c.id !== S.chatId);
  S.chatId = S.chatId || ("c" + Date.now());
  const first = S.chat.find(m => m.role === "user");
  list.unshift({ id: S.chatId, title: (first && first.content || "Chat").slice(0, 60), at: Date.now(), msgs: S.chat.map(m => ({ ...m, blocks: (m.blocks || []).slice(0, 8) })) });
  chatStore.save(list);
}
const hello = () => { const h = new Date().getHours(); return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"; };
const engBtn = () => { const st = S.init.ai; return `<span class="dot ${st.active === "basic" ? "off" : ""}"></span>${esc(st.label)}<span class="caret">▾</span>`; };
const ENG_DESC = { auto: "Best available, switches by itself if one fails", groq: "Fast cloud AI", gemini: "Google's models", openrouter: "GPT, Claude, Llama, DeepSeek…", offline: "Runs on this PC", basic: "No AI service, always works" };
function engMenuHtml() {
  const st = S.init.ai;
  return st.choices.map(c => `<button data-act="eng-pick" data-mode="${c.id}" ${c.ready ? "" : "disabled"} aria-pressed="${st.mode === c.id}">
      <b>${st.mode === c.id ? "✓ " : ""}${esc(c.name)}${c.id === "auto" && st.mode === "auto" ? ` <span class="chip good">${esc(st.label)}</span>` : ""}</b>
      <small>${c.ready ? esc(ENG_DESC[c.id]) : c.id === "offline" ? "Not installed · Settings → AI" : "No key yet · add it in Settings → AI"}</small></button>`).join("")
    + `<button data-go="settings" data-tab="ai"><b>⚙ AI settings & keys…</b><small>Add Groq, Gemini or OpenRouter keys, pick models</small></button>`;
}
async function setEngine(mode) {
  const st = await API.call("agent_settings", { mode });
  S.init.ai = { ...S.init.ai, ...st };
  const b = $("#engbtn"); if (b) b.innerHTML = engBtn();
  const pill = document.querySelector(".ai-pill"); if (pill) pill.innerHTML = `<span class="dot ${st.active === "basic" ? "off" : ""}"></span><span>${esc(st.label)}</span>`;
  return st;
}
function composerHtml(big) {
  const st = S.init.ai;
  return `<div class="cbox ${big ? "big" : ""}" id="cbox">
      <div class="att" id="att">${attChips()}</div>
      <textarea id="askq" rows="${big ? 3 : 1}" placeholder="Ask anything about your stores, people, sales, turnover, NPS… or drop a file"></textarea>
      <div class="cbar"><button class="cbtn" data-act="ask-attach" title="Attach files">${ic("attach", 18)}</button>
        <button class="cbtn" data-act="ask-paste" title="Paste a table">${ic("paste", 17)}</button>
        <div class="menu-wrap"><button class="cmodel" data-act="eng-menu" title="Switch AI" id="engbtn">${engBtn()}</button><div class="cmenu up" id="engmenu" hidden></div></div>
        <span class="spacer"></span><button class="csend" data-act="ask-send" title="Send (Enter)">${ic("send", 17)}</button></div></div>`;
}
PAGES.ask = async () => {
  const chats = chatStore.list();
  const head = `<div class="chat-head"><button class="btn sm ghost" data-act="ask-clear">${ic("spark", 14)}New chat</button>
    <div class="menu-wrap"><button class="btn sm ghost" data-act="ask-hist">History ▾</button><div class="cmenu" id="cmenu" hidden>${chats.length ? chats.map(c => `<button data-act="ask-open" data-id="${c.id}"><b>${esc(c.title)}</b><small>${new Date(c.at).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}</small></button>`).join("") : `<div class="empty" style="padding:12px">No saved chats yet</div>`}</div></div></div>`;
  if (!S.chat.length) return `<div class="chat2 empty-chat">${head}<div class="welcome"><div class="logo maf big"><img src="maf-logo.png" alt="Majid Al Futtaim"></div>
      <h1>${hello()}</h1><p>I'm your P&amp;O analyst. I read everything imported into P&amp;O and answer with numbers, charts and recommendations.</p>
      ${composerHtml(true)}
      <div class="scards">${SUGGEST.map(([e, q, d]) => `<button class="scard" data-act="ask-sugg" data-q="${esc(q)}"><span class="se">${e}</span><b>${esc(q)}</b><small>${esc(d)}</small></button>`).join("")}</div></div></div>`;
  return `<div class="chat2">${head}<div class="msgs2" id="msgs">${S.chat.map(renderMsg).join("")}</div><div class="cfoot">${composerHtml(false)}
    <small>Answers come from your imported data · the AI can make mistakes, check important numbers</small></div></div>`;
};
AFTER.ask = () => {
  const ta = $("#askq");
  if (!ta) return;
  const grow = () => { ta.style.height = "auto"; ta.style.height = Math.min(220, ta.scrollHeight) + "px"; };
  ta.oninput = grow;
  ta.onkeydown = e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(ta.value); } };
  ta.focus();
  const box = $("#cbox");
  if (box && !window.qt) {
    box.addEventListener("dragover", e => { e.preventDefault(); box.classList.add("over"); });
    box.addEventListener("dragleave", () => box.classList.remove("over"));
    box.addEventListener("drop", async e => { e.preventDefault(); box.classList.remove("over"); for (const f of e.dataTransfer.files) S.attachUp = (S.attachUp || []).concat([f]); toast("Attached " + e.dataTransfer.files.length + " file(s)"); $("#att").innerHTML = attChips(); });
  }
  drawBlocks();
  const m = $("#msgs"); if (m) m.scrollTop = m.scrollHeight;
};

/* markdown → rich HTML: headings, lists, tables, callouts, code, coloured +/- figures, and ```chart / ```kpis blocks */
function inline(t) {
  return t.replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/(^|[^*\w])\*(?!\s)(.+?)\*(?!\*)/g, "$1<i>$2</i>").replace(/(^|\s)_(\S.*?\S|\S)_(?=\s|$|[.,;:])/g, "$1<i>$2</i>")
    .replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/(^|[\s(>])([+−-]\s?\d[\d,.]*\s?(%|pp|pts)?)(?=[\s),.;<]|$)/g, (m, a, n) => `${a}<span class="${/^[+]/.test(n) ? "pos" : "neg"}">${n}</span>`);
}
function md(src) {
  const lines = String(src || "").replace(/\r/g, "").split("\n");
  let out = "", i = 0;
  const fenced = [];
  while (i < lines.length) {
    let l = lines[i];
    const fence = l.match(/^```\s*(\w+)?/);
    if (fence) {
      const lang = (fence[1] || "").toLowerCase(), body = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) body.push(lines[i++]);
      i++;
      if (["chart", "kpis", "kpi"].includes(lang)) { try { fenced.push(JSON.parse(body.join("\n"))); out += `<div class="mblock" data-f="${fenced.length - 1}"></div>`; continue; } catch (e) { /* show as code */ } }
      out += `<pre class="code"><code>${esc(body.join("\n"))}</code></pre>`;
      continue;
    }
    if (/^\s*\|.*\|\s*$/.test(l) && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1])) {
      const row = x => x.trim().replace(/^\||\|$/g, "").split("|").map(c => c.trim());
      const head = row(l); i += 2; const body = [];
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) body.push(row(lines[i++]));
      const num = c => /^[+−-]?[\d,.]+\s?(%|M|bn|K|pp|pts)?$/.test(c.replace(/\*\*/g, ""));
      out += `<div class="mtable"><table><thead><tr>${head.map(h => `<th>${inline(esc(h))}</th>`).join("")}</tr></thead><tbody>${body.map(r => `<tr>${r.map(c => `<td class="${num(c) ? "n" : ""}">${inline(esc(c))}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
      continue;
    }
    if (/^\s*>/.test(l)) {
      const q = []; while (i < lines.length && /^\s*>/.test(lines[i])) q.push(lines[i++].replace(/^\s*>\s?/, ""));
      const txt = q.join(" "), kind = /^(⚠|\*\*(risk|warning|watch|concern))/i.test(txt) ? "warn" : /^(✅|\*\*(good|win|strength))/i.test(txt) ? "good" : "info";
      out += `<div class="callout ${kind}">${inline(esc(txt))}</div>`;
      continue;
    }
    if (/^\s*([-*•]|\d+[.)])\s+/.test(l)) {
      const ordered = /^\s*\d+[.)]/.test(l);
      out += ordered ? "<ol>" : "<ul>";
      while (i < lines.length && /^\s*([-*•]|\d+[.)])\s+/.test(lines[i])) {
        const sub = /^\s{2,}/.test(lines[i]);
        out += `<li class="${sub ? "sub" : ""}">${inline(esc(lines[i].replace(/^\s*([-*•]|\d+[.)])\s+/, "")))}</li>`;
        i++;
      }
      out += ordered ? "</ol>" : "</ul>";
      continue;
    }
    if (/^\s*(---|\*\*\*)\s*$/.test(l)) { out += "<hr>"; i++; continue; }
    const h = l.match(/^(#{1,4})\s+(.*)$/);
    if (h) { out += `<h${Math.min(4, h[1].length + 1)}>${inline(esc(h[2]))}</h${Math.min(4, h[1].length + 1)}>`; i++; continue; }
    if (l.trim()) {
      const para = [l]; i++;
      while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|\s*[-*•]\s|\s*\d+[.)]\s|\s*>|```|\s*\|)/.test(lines[i])) para.push(lines[i++]);
      out += `<p>${inline(esc(para.join(" ")))}</p>`;
    } else i++;
  }
  md.last = fenced;
  return out;
}
function kpiCards(items) {
  return `<div class="mkpis">${(items || []).slice(0, 6).map(k => `<div class="mkpi ${esc(k.tone || "")}"><span>${esc(k.label || "")}</span><b>${esc(String(k.value ?? "—"))}</b>${k.sub ? `<small>${esc(k.sub)}</small>` : ""}</div>`).join("")}</div>`;
}
function blockHtml(b, i, j) {
  if (b.type === "kpis") return kpiCards(b.items);
  if (b.type === "table") return `<div class="mtable"><div class="mt">${esc(b.title || "")}</div><table><thead><tr>${b.columns.map(c => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${b.rows.slice(0, 60).map(r => `<tr>${b.columns.map(c => `<td class="${typeof r[c] === "number" ? "n" : ""}">${esc(r[c] ?? "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  return `<div class="mchartbox"><div class="mt">${esc(b.title || "")}</div><div class="mchart" data-m="${i}" data-b="${j}"></div></div>`;
}
function renderMsg(m, i) {
  if (m.role === "user") return `<div class="umsg"><div class="ub">${esc(m.content)}${m.files ? `<div class="uf">📎 ${esc(m.files.join(", "))}</div>` : ""}</div></div>`;
  if (m.pending) return `<div class="amsg"><div class="aav"><img src="maf-mark.png" alt=""></div><div class="abody"><div class="thinking"><span class="typing"><i></i><i></i><i></i></span><span id="think-t">Reading your data…</span></div></div></div>`;
  let body = md(m.content);
  const fenced = md.last || [];
  m.fenced = fenced;
  const kpiBlocks = (m.blocks || []).map((b, j) => b.type === "kpis" ? blockHtml(b, i, j) : "").join("");
  const blocks = (m.blocks || []).map((b, j) => b.type === "kpis" ? "" : blockHtml(b, i, j)).join("");
  const acts = (m.actions || []).map(a => `<div class="action"><b>${esc(a.title)}</b><ul>${a.items.slice(0, 12).map(it => `<li>${esc(actionLine(a.kind, it))}</li>`).join("")}${a.items.length > 12 ? `<li>…and ${a.items.length - 12} more</li>` : ""}</ul>
    ${a.done ? `<span class="chip ${a.done === "ok" ? "good" : ""}">${a.done === "ok" ? "Saved" : "Cancelled"}</span>` : `<div class="row"><button class="btn primary sm" data-act="confirm" data-id="${a.id}" data-m="${i}">Confirm</button><button class="btn sm" data-act="cancel" data-id="${a.id}" data-m="${i}">Cancel</button></div>`}</div>`).join("");
  const cut = body.indexOf("</p>") > -1 && body.indexOf("</p>") < 600 ? body.indexOf("</p>") + 4 : body.indexOf("<ul>") > -1 && body.indexOf("<ul>") < 400 ? body.indexOf("<ul>") : 0;
  const lead = kpiBlocks && cut ? body.slice(0, cut) : "", rest = kpiBlocks && cut ? body.slice(cut) : body;
  return `<div class="amsg"><div class="aav"><img src="maf-mark.png" alt=""></div><div class="abody">${lead ? `<div class="md">${lead}</div>` : ""}${kpiBlocks}<div class="md">${rest}</div>${blocks}${acts}
    <div class="ameta"><button class="mbtn" data-act="msg-copy" data-m="${i}" title="Copy">⧉ Copy</button><button class="mbtn" data-act="msg-retry" data-m="${i}" title="Ask again">↻ Retry</button>
    <span>${esc(m.engine_label || "")}${m.seconds != null ? ` · ${m.seconds}s` : ""}</span></div></div></div>`;
}
function actionLine(kind, it) {
  if (kind === "leave") return `${it.name} (${it.emp}): ${it.type}, ${fmtDate(it.from)} – ${fmtDate(it.to)}`;
  if (kind === "holiday") return `${fmtDate(it.day)}: ${it.name}`;
  if (kind === "note") return `${it.name}: ${it.text}`;
  if (kind === "import") return `${it.file}: ${(it.tables || []).join(", ")}`;
  return JSON.stringify(it);
}
function drawChartSpec(el, b) {
  const s0 = (b.series || [])[0] || {};
  const fmt = b.fmt || "num";
  if (b.kind === "donut" || b.kind === "pie") Charts.donut(el, { labels: b.labels, values: s0.values || [], fmt, center: b.center || s0.name });
  else if (b.kind === "hbar") Charts.hbar(el, { labels: b.labels, values: s0.values || [], name: s0.name, fmt, ref: b.ref,
    colors: b.colors || (s0.values || []).map((v, k) => b.tone === "signed" ? (v >= 0 ? "var(--good)" : "var(--bad)") : Charts.PAL[0]) });
  else if (b.kind === "line") Charts.line(el, { labels: b.labels, series: b.series, height: 220, area: (b.series || []).length === 1, fmt, ref: b.ref });
  else Charts.columns(el, { labels: b.labels, series: b.series, height: 220, fmt });
}
function drawBlocks() {
  $$(".mchart").forEach(el => {
    const b = S.chat[+el.dataset.m].blocks[+el.dataset.b];
    if (!b || el.dataset.drawn) return;
    el.dataset.drawn = 1; drawChartSpec(el, b);
  });
  $$(".amsg").forEach((am, idx) => {
    const msgIdx = S.chat.filter(m => m.role !== "user").length ? null : null;
    am.querySelectorAll(".mblock").forEach(el => {
      if (el.dataset.drawn) return;
      const host = el.closest(".amsg"), all = $$(".amsg"), k = all.indexOf(host);
      const msg = S.chat.filter(m => m.role !== "user")[k];
      const spec = msg && msg.fenced && msg.fenced[+el.dataset.f];
      if (!spec) return;
      el.dataset.drawn = 1;
      if (Array.isArray(spec) || spec.items) el.innerHTML = kpiCards(Array.isArray(spec) ? spec : spec.items);
      else { el.innerHTML = `<div class="mchartbox"><div class="mt">${esc(spec.title || "")}</div><div class="mc"></div></div>`; drawChartSpec(el.querySelector(".mc"), spec); }
    });
  });
}
function drawChat() {
  const m = $("#msgs");
  if (!m || S.page !== "ask") return render();
  m.innerHTML = S.chat.map(renderMsg).join("");
  const att = $("#att"); if (att) att.innerHTML = attChips();
  drawBlocks();
  m.scrollTop = m.scrollHeight;
}
const attChips = () => S.attach.map((p, i) => `<span class="achip">${ic("file", 13)}${esc(p.split(/[\\/]/).pop())}<button data-act="att-rm" data-i="${i}">✕</button></span>`).join("")
  + (S.attachUp || []).map((f, i) => `<span class="achip">${ic("file", 13)}${esc(f.name)}<button data-act="attup-rm" data-i="${i}">✕</button></span>`).join("");
const THINK = ["Reading your data…", "Working out the numbers…", "Comparing stores and sections…", "Writing it up…"];
async function ask(text) {
  text = (text || "").trim();
  if (!text && !S.attach.length && !(S.attachUp || []).length) return;
  if (S.asking) return;
  S.asking = true;
  if (S.attachUp && S.attachUp.length) {            // browser: upload dropped files, then import them as part of the chat
    const files = [];
    for (const f of S.attachUp) { const buf = new Uint8Array(await f.arrayBuffer()); let bin = ""; for (let k = 0; k < buf.length; k += 32768) bin += String.fromCharCode.apply(null, buf.subarray(k, k + 32768)); files.push({ name: f.name, b64: btoa(bin) }); }
    try { const r = await API.call("agent_upload", { files }); S.attach.push(...(r.paths || [])); } catch (e) { fail(e); }
    S.attachUp = [];
  }
  const files = S.attach.slice();
  const wasEmpty = !S.chat.length;
  S.chat.push({ role: "user", content: text || "(file)", files: files.length ? files.map(f => f.split(/[\\/]/).pop()) : null });
  S.chat.push({ role: "assistant", pending: true });
  S.attach = [];
  const ta0 = $("#askq"); if (ta0) { ta0.value = ""; ta0.style.height = "auto"; }
  if (wasEmpty) await render(); else drawChat();
  let k = 0; const tick = setInterval(() => { const t = $("#think-t"); if (t) t.textContent = THINK[Math.min(++k, THINK.length - 1)]; }, 1600);
  try {
    const hist = S.chat.filter(m => !m.pending && m.content).slice(-10, -1).map(m => ({ role: m.role, content: m.content }));
    const r = await API.call("agent_ask", { question: text, history: hist, month: S.month, scope: S.scope, attachments: files });
    S.chat[S.chat.length - 1] = { role: "assistant", content: r.answer, blocks: r.blocks, actions: r.actions, engine_label: r.engine_label, seconds: r.seconds, q: text };
  } catch (e) {
    S.chat[S.chat.length - 1] = { role: "assistant", content: "Sorry, something went wrong: " + (e.message || e), blocks: [], actions: [], q: text };
  }
  clearInterval(tick);
  S.asking = false;
  saveChat();
  if (S.page === "ask") drawChat();
}
const CHAT_ACTS = {
  "ask-hist": () => { const m = $("#cmenu"); if (m) m.hidden = !m.hidden; },
  "eng-menu": () => { const m = $("#engmenu"); if (!m) return; m.innerHTML = engMenuHtml(); m.hidden = !m.hidden; },
  "eng-pick": async b => { const m = $("#engmenu"); if (m) m.hidden = true; const st = await setEngine(b.dataset.mode); toast(`Now answering with ${st.label}`); },
  "ask-open": b => { const c = chatStore.list().find(x => x.id === b.dataset.id); if (c) { S.chat = c.msgs; S.chatId = c.id; render(); } },
  "ask-paste": () => {
    const m = modal(`<h3>Paste a table for the AI</h3><p style="color:var(--muted);margin:0 0 10px">Copy cells from Excel and paste them here. The AI reads it with your question.</p><textarea class="input" id="cp-t" rows="10" style="width:100%;font-family:monospace;font-size:12px"></textarea>
      <div class="row" style="justify-content:flex-end;margin-top:10px"><button class="btn" data-act="modal-close">Cancel</button><button class="btn primary" id="cp-go">Add to message</button></div>`);
    $("#cp-go", m).onclick = async () => { const t = $("#cp-t", m).value; if (!t.trim()) return; closeModal(); const r = await call("agent_upload", { files: [{ name: "Pasted table.txt", b64: btoa(unescape(encodeURIComponent(t))) }] }); S.attach.push(...(r.paths || [])); const a = $("#att"); if (a) a.innerHTML = attChips(); };
  },
  "attup-rm": b => { S.attachUp.splice(+b.dataset.i, 1); $("#att").innerHTML = attChips(); },
  "msg-copy": b => { const m = S.chat[+b.dataset.m]; try { navigator.clipboard.writeText(m.content || ""); toast("Copied"); } catch (e) { toast("Copy is not available here", { err: true }); } },
  "msg-retry": b => { const m = S.chat[+b.dataset.m]; if (m && m.q != null) ask(m.q); },
};

/* import */
function impPeriod(f, r, sess) {
  const p = r.period || { type: "general" };
  const a = `data-file="${esc(f.file)}" data-sheet="${esc(r.sheet)}"`;
  const to = p.to || r.month || sess.suggested_month || "";
  return `<label class="dx-l">Data covers<select class="input" data-opt="period_type" data-imp-pt ${a}>${(f.period_types || []).map(t => `<option value="${t.value}" ${t.value === p.type ? "selected" : ""}>${esc(t.label)}</option>`).join("")}</select></label>
    <label class="dx-l imp-from" ${p.type === "ytd" ? "" : "hidden"}>From month<input class="input" type="month" data-opt="period_from" ${a} value="${esc(p.from || (to ? to.slice(0, 4) + "-01" : ""))}"></label>
    <label class="dx-l imp-to" ${p.type === "general" ? "hidden" : ""}><span>${p.type === "ytd" ? "Up to month" : "Month"}</span><input class="input" type="month" data-opt="period_to" ${a} value="${esc(to)}"></label>
    <small class="imp-why">${p.type === "general" ? "Used for every period (MTD and YTD views)." : esc(p.why || "")}${r.dated && p.type !== "general" ? " Rows have their own dates, so any month or YTD range can be cut from them." : ""}</small>`;
}
document.addEventListener("change", e => {
  const sel = e.target.closest && e.target.closest("[data-imp-pt]");
  if (!sel) return;
  const box = sel.closest(".imp-opts"), t = sel.value;
  box.querySelector(".imp-from").hidden = t !== "ytd";
  box.querySelector(".imp-to").hidden = t === "general";
  box.querySelector(".imp-to span").textContent = t === "ytd" ? "Up to month" : "Month";
  box.querySelector(".imp-why").textContent = t === "general" ? "Used for every period (MTD and YTD views)." : t === "ytd" ? "Year to date: figures add up from the first month to the last." : "Month to date: figures for this one month.";
});
PAGES.import = async () => {
  const h = await API.call("imports");
  const sess = S.importSess;
  const kindIcon = { roster: "👥", attendance: "🕘", productivity: "📈", sales: "🧾", leave: "🏖️", po_rating: "⭐", po_role: "🪪", po_shift: "🗓️", po_turnover: "🚪", po_da: "⚖️", po_nps: "💬", po_shrink: "📦", dataset: "📊" };
  const preview = sess ? sess.files.map((f, fi) => `<div class="fcard"><div class="kind">${ic("file", 18)}<b>${esc(f.file)}</b>${f.results.length ? "" : `<span class="chip bad">Not recognised</span>`}</div>
      ${f.results.map(r => `<div style="display:flex;flex-direction:column;gap:6px;padding-left:4px;border-left:3px solid var(--gold-2);padding:4px 10px">
        <div class="row"><b>${kindIcon[r.kind] || ""} ${esc(r.label)}</b><span class="chip">${esc(r.sheet)}</span><span class="chip good">${r.rows.toLocaleString("en-US")} rows</span>${r.month ? `<span class="chip info">${esc(r.month)}</span>` : ""}</div>
        <small style="color:var(--muted)">${esc(r.summary)}</small>
        <div class="imp-opts">
          <label class="dx-l">This sheet is<select class="input" data-opt="kind" data-file="${esc(f.file)}" data-sheet="${esc(r.sheet)}">${(f.kinds || []).map(k => `<option value="${k.value}" ${k.value === r.kind ? "selected" : ""}>${esc(k.label)}</option>`).join("")}</select></label>
          ${impPeriod(f, r, sess)}
          <label class="dx-l">${r.kind === "roster" ? "Roster as of" : "Last day (optional)"}<input class="input" type="date" data-opt="as_of" data-file="${esc(f.file)}" data-sheet="${esc(r.sheet)}" value="${r.kind === "roster" ? (r.as_of || new Date().toISOString().slice(0, 10)) : esc(r.as_of || "")}"></label>
          <details class="imp-more"><summary>Name and description (optional, helps the AI)</summary><div class="imp-more-b">
          <label class="dx-l">Name<input class="input" data-opt="title" data-file="${esc(f.file)}" data-sheet="${esc(r.sheet)}" placeholder="${esc(r.sheet)}"></label>
          <label class="dx-l imp-note">What is this sheet about?<textarea class="input" rows="2" data-opt="note" data-file="${esc(f.file)}" data-sheet="${esc(r.sheet)}" placeholder="e.g. Weekly footfall and conversion by store from the Ops team, week 41"></textarea></label></div></details>
        </div>
        ${r.warnings.filter(w => !(/Choose the month/.test(w) && r.period && r.period.to)).map(w => `<small style="color:var(--warn-ink)">⚠ ${esc(w)}</small>`).join("")}
        ${r.preview && r.preview.length ? `<details><summary style="cursor:pointer;color:var(--brand);font-weight:700;font-size:12.5px">Preview</summary><div class="tbl-wrap" style="max-height:220px;margin-top:6px"><table class="t"><thead><tr>${Object.keys(r.preview[0]).filter(k => typeof r.preview[0][k] !== "object").map(k => `<th>${esc(k)}</th>`).join("")}</tr></thead><tbody>${r.preview.map(p => `<tr>${Object.keys(r.preview[0]).filter(k => typeof r.preview[0][k] !== "object").map(k => `<td>${esc(p[k] ?? "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div></details>` : ""}</div>`).join("")}
      ${f.skipped.length ? `<small style="color:var(--muted)">Ignored sheets: ${esc(f.skipped.join(", "))}</small>` : ""}</div>`).join("") + (sess.errors || []).map(e => `<div class="errbox">${esc(e.file)}: ${esc(e.error)}</div>`).join("") : "";
  const kinds = { roster: "Roster", attendance: "Attendance", productivity: "Productivity", sales: "BO sales", leave: "Leave", holiday: "Holiday",
    po_rating: "Ratings", po_role: "Time in role", po_shift: "Shift roster", po_turnover: "Turnover", po_da: "DA", po_nps: "NPS", po_shrink: "Shrinkage", dataset: "Other data" };
  return `<div class="ph"><div><h1>Import data</h1><p>Drop files or paste cells from Excel, one sheet or many. Each sheet is recognised by its columns; you can
    change what it is, whether it is general data or covers a month (MTD) or year to date (YTD), and describe it before saving. Anything else is kept under Other data with charts and insights.</p></div></div>
    ${S.init.unsure_stores ? `<div class="banner">🏬 ${S.init.unsure_stores} store name${S.init.unsure_stores > 1 ? "s were" : " was"} matched with less certainty. <button class="btn sm" data-go="settings" data-tab="stores">Check store names</button></div>` : ""}
    <div class="drop" id="drop"><div class="ic">${ic("import", 26)}</div><h3>Drop report files here</h3><p style="margin:0;color:var(--muted)">Excel (.xlsx, .xls, .xlsm), CSV or text · as many as you like</p>
      <div class="row" style="justify-content:center"><button class="btn primary" data-act="pick">${ic("file", 16)}Choose files</button><button class="btn" data-act="paste">${ic("paste", 16)}Paste data</button></div>
      <input type="file" id="filein" multiple hidden accept=".xlsx,.xls,.xlsm,.xlsb,.csv,.txt,.tsv,.htm,.html"></div>
    ${sess ? `<div class="panel"><div class="phd"><h2>Ready to import</h2><div class="tools"><button class="btn" data-act="import-cancel">Cancel</button><button class="btn primary" data-act="import-commit" ${sess.files.some(f => f.results.length) ? "" : "disabled"}>Import ${sess.files.reduce((a, f) => a + f.results.length, 0)} table${sess.files.reduce((a, f) => a + f.results.length, 0) === 1 ? "" : "s"}</button></div></div>${preview}</div>` : ""}
    <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Import history</h2><small>Undo removes an import's data; Restore brings it back</small></div><div class="tbl-wrap" style="max-height:520px"><table class="t"><thead><tr><th>When</th><th>Type</th><th>File</th><th>Period</th><th class="n">Rows</th><th>Summary</th><th></th></tr></thead>
    <tbody>${h.rows.map(r => `<tr style="${r.active ? "" : "opacity:.5"}"><td>${esc(r.created_at.replace("T", " ").slice(0, 16))}</td><td><span class="chip">${esc(kinds[r.kind] || r.kind)}</span></td><td>${esc(r.file_name)}<span class="sub">${esc(r.source)}</span></td>
      <td class="nw">${r.period_label ? `<span class="chip ${r.period_type === "ytd" ? "gold" : r.period_type === "mtd" ? "info" : ""}">${esc(r.period_label)}</span>` : esc(r.as_of || r.month || "")}</td><td class="n">${r.rows.toLocaleString("en-US")}</td><td>${esc(r.summary)}${r.warnings.length ? `<span class="sub">⚠ ${esc(r.warnings[0])}</span>` : ""}</td>
      <td class="n">${r.active ? `<button class="btn sm" data-act="undo" data-id="${r.id}">${ic("undo", 13)}Undo</button>` : `<button class="btn sm" data-act="redo" data-id="${r.id}">Restore</button>`}</td></tr>`).join("") || `<tr><td colspan="7"><div class="empty">Nothing imported yet.</div></td></tr>`}</tbody></table></div></div>`;
};
AFTER.import = () => {
  const drop = $("#drop"), fi = $("#filein");
  if (!drop) return;
  ["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, () => drop.classList.remove("over")));
  drop.addEventListener("drop", e => { e.preventDefault(); if (e.dataTransfer.files.length && !window.qt) uploadFiles(e.dataTransfer.files); });
  fi.onchange = () => { if (fi.files.length) uploadFiles(fi.files); };
};
async function uploadFiles(fileList) {
  const files = [];
  for (const f of fileList) {
    const buf = await f.arrayBuffer();
    let bin = ""; const bytes = new Uint8Array(buf);
    for (let i = 0; i < bytes.length; i += 32768) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 32768));
    files.push({ name: f.name, b64: btoa(bin) });
  }
  S.importSess = await call("import_upload", { files });
  render();
}
window.PNO_drop = async paths => {
  if (S.page === "ask") { S.attach.push(...paths); drawChat(); return; }
  if (S.page !== "import") { S.page = "import"; $$("#nav button").forEach(b => b.toggleAttribute("aria-current", b.dataset.go === "import")); }
  toast("Reading " + paths.length + " file" + (paths.length > 1 ? "s" : "") + "…");
  S.importSess = await call("import_analyze", { paths });
  render();
};

/* settings */
PAGES.settings = async () => {
  const tabs = [["scoring", "Scoring"], ["ai", "AI assistant"], ["stores", "Stores"], ["sections", "Sections"], ["holidays", "Holidays"], ["leave", "Leave"], ["data", "Data & backup"], ["look", "Appearance"]];
  const t = S.setTab;
  const body = await SETTINGS[t]();
  return `<div class="ph"><div><h1>Settings</h1><p>How scores are calculated, the AI assistant, store and section matching, holidays and leave, and your data.</p></div></div>
    <div class="seg">${tabs.map(([k, l]) => `<button data-act="set-tab" data-tab="${k}" aria-pressed="${t === k}">${l}</button>`).join("")}</div>${body}`;
};
const SETTINGS = {};
SETTINGS.scoring = async () => {
  const s = DATA.settings = await API.call("settings");
  const roles = Object.keys(s.default_weights);
  const parts = Object.keys(s.labels);
  const r = s.rules;
  const rule = (k, l, hint) => `<div class="setting"><div><b>${l}</b><small>${hint}</small></div><div class="row">${r[k].map((v, i) => `<input class="input" style="width:74px" type="number" data-rule="${k}" data-i="${i}" value="${v}">`).join("")}</div></div>`;
  const one = (k, l, hint) => `<div class="setting"><div><b>${l}</b><small>${hint}</small></div><input class="input" style="width:90px" type="number" data-rule1="${k}" value="${r[k]}"></div>`;
  return `<div class="panel"><div class="phd"><h2>Weights by role</h2><small>Each row is shared out by weight; parts with no data are left out and the rest scaled up.</small></div>
    <div class="tbl-wrap"><table class="t"><thead><tr><th>Role</th>${parts.map(p => `<th class="n">${esc(s.labels[p])}</th>`).join("")}<th class="n">Total</th></tr></thead><tbody>
    ${roles.map(ro => `<tr><td><b>${esc(s.role_labels[ro])}</b></td>${parts.map(p => `<td class="n"><input class="input" style="width:64px;text-align:right" type="number" min="0" data-w="${ro}" data-p="${p}" value="${s.weights[ro][p] ?? ""}" placeholder="—"></td>`).join("")}<td class="n"><b data-total="${ro}"></b></td></tr>`).join("")}</tbody></table></div></div>
    <div class="panel"><div class="phd"><h2>Thresholds</h2><small>Results between the points score on a straight line; 7 = target met</small></div>
      ${rule("budget", "Sales vs budget (%)", "Scores 0 / 7 / 10")}${rule("productivity", "Productivity vs target (%)", "Scores 0 / 7 / 10")}
      ${rule("presence", "Presence (% of due days worked)", "Scores 0 / 7 / 10")}${rule("compliance", "Full 9-hour days (% of worked days)", "Scores 0 / 5 / 10")}
      ${one("full_day_minutes", "Full day (minutes)", "The 9-hour golden rule = 540")}${one("grace_minutes", "Grace (minutes)", "A day this much short of 9h still counts as full")}
      ${one("presence_weight", "Presence share of the attendance score (%)", "The rest is 9-hour compliance")}${one("provisional_days", "Provisional until day", "Scores early in the month are marked provisional")}
      ${one("new_joiner_days", "New joiners (days)", "Not scored until they have worked this long")}${one("min_coverage", "Minimum coverage (%)", "Below this share of weighted parts: 'Not enough data'")}
      ${one("outlier_pct", "Flag sales variance beyond (±%)", "Bulk / B2B sales are flagged and capped")}${one("long_absence_days", "Long absence (days in a row)", "Flagged as a possible leaver or long leave")}
      <div class="row" style="justify-content:flex-end"><button class="btn danger" data-act="weights-reset">Restore defaults</button><button class="btn primary" data-act="weights-save">Save scoring</button></div></div>
    ${s.weights_history.length ? `<div class="panel"><div class="phd"><h2>Change history</h2></div>${s.weights_history.slice().reverse().slice(0, 8).map(h => `<small style="color:var(--muted)">${esc(h.at.replace("T", " "))}</small>`).join("<br>")}</div>` : ""}`;
};
SETTINGS.ai = async () => {
  const s = await API.call("agent_status");
  const o = s.offline_status;
  const dl = (o.downloads || []).filter(j => j.status === "running");
  const mode = s.choices.map(c => `<button data-act="ai-mode" data-mode="${c.id}" aria-pressed="${s.mode === c.id}" ${c.ready ? "" : `title="Not set up yet"`}>${esc(c.name)}${c.id !== "auto" && c.id !== "basic" ? `<span class="rdot ${c.ready ? "on" : ""}"></span>` : ""}</button>`).join("");
  const prov = p => `<div class="panel prov ${s.active === p.id ? "live" : ""}"><div class="phd"><h2>${esc(p.name)} <small class="tag">${esc(p.tag)}</small></h2>
      ${s.active === p.id ? '<span class="chip good">Answering now</span>' : p.has_key ? '<span class="chip">Key saved · standby</span>' : '<span class="chip">Not set up</span>'}</div>
      <small style="color:var(--muted)">${esc(p.note)} Get a key at <b>${esc(p.signup)}</b>. Stored encrypted for this Windows user.</small>
      <div class="row"><input class="input" id="key-${p.id}" type="password" autocomplete="off" placeholder="${p.key_masked ? "Saved: " + esc(p.key_masked) : esc(p.hint)}" style="flex:1;min-width:220px">
      <input class="input" id="model-${p.id}" list="models-${p.id}" value="${esc(p.model)}" title="Pick a model or type any model id" style="min-width:230px">
      <datalist id="models-${p.id}">${p.models.map(m => `<option value="${esc(m)}">`).join("")}</datalist></div>
      <div class="row"><button class="btn primary" data-act="prov-save" data-p="${p.id}">Save</button><button class="btn" data-act="prov-test" data-p="${p.id}">Test</button>
      ${p.has_key && s.mode !== p.id ? `<button class="btn ghost" data-act="ai-mode" data-mode="${p.id}">Use ${esc(p.name)} first</button>` : ""}
      ${p.has_key ? `<button class="btn danger" data-act="prov-clear" data-p="${p.id}">Remove key</button>` : ""}
      <small style="color:var(--muted)">${p.live_models ? `${p.models.length} models from ${esc(p.name)}` : "Test the key to load the full model list"}</small></div></div>`;
  return `<div class="panel"><div class="phd"><h2>Which AI answers</h2><span class="chip ${s.active === "basic" ? "" : "good"}">Now: ${esc(s.label)}</span></div>
    <div class="seg">${mode}</div>
    <small style="color:var(--muted)">Auto uses the first AI that is set up, in this order: Groq → Gemini → OpenRouter → Offline AI → built-in. Picking one puts it first; if it fails (wrong key, free limit used up, no internet) P&amp;O switches to the next one on the spot and says so in the answer. You can also switch from the chat box.</small></div>
    ${s.providers.map(prov).join("")}
    <div class="panel"><div class="phd"><h2>Privacy</h2></div>
      <div class="setting"><div><b>Send employee codes instead of names</b><small>Online AIs then never see names; P&amp;O puts the names back on your screen.</small></div><label class="switch"><input type="checkbox" id="anon" ${s.anonymise ? "checked" : ""}><span></span></label></div>
      <small style="color:var(--muted)">With an online AI (Groq, Gemini or OpenRouter), each question and the figures needed to answer it are sent to that service. Files you drop into the chat stay on this PC (only column names and 5 sample rows are shown to the AI to work out unknown layouts).</small></div>
    <div class="panel"><div class="phd"><h2>Offline AI</h2><small>${esc(o.model_name)} · about ${o.model_gb} GB · runs on this PC, no internet after setup</small></div>
      <div class="setting"><div><b>Runtime</b><small>${o.runtime ? "Installed" : "Not installed (included in the Windows package)"}</small></div>${o.runtime ? '<span class="chip good">Ready</span>' : `<button class="btn" data-act="offline-install" data-what="runtime">Install</button>`}</div>
      <div class="setting"><div><b>Model</b><small>${o.model ? esc(o.model) : "Not downloaded yet"}</small></div><div class="row">${o.model ? '<span class="chip good">Ready</span>' : `<button class="btn primary" data-act="offline-install" data-what="model">Download (${o.model_gb} GB)</button>`}<button class="btn" data-act="offline-pick">Choose a .gguf file</button></div></div>
      ${dl.map(j => `<div><small>${esc(j.name)} · ${j.pct}%</small><div class="progress"><i style="width:${j.pct}%"></i></div></div>`).join("")}
      ${(o.downloads || []).filter(j => j.status === "error").map(j => `<div class="errbox">${esc(j.name)}: ${esc(j.error)}</div>`).join("")}</div>`;
};
SETTINGS.stores = async () => {
  const s = await API.call("store_list");
  const unsure = s.aliases.filter(a => !a.confirmed);
  const opt = sel => s.stores.map(st => `<option value="${st.id}" ${st.id === sel ? "selected" : ""}>${esc(st.name)} · ${esc(st.format_label || "")} · ${esc(st.city_label || "")}</option>`).join("");
  return `${unsure.length ? `<div class="banner">Please confirm ${unsure.length} store name${unsure.length > 1 ? "s" : ""} P&O matched with less certainty.</div>` : ""}
    <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>How each report names the stores</h2><small>Change the store if a name was linked to the wrong one</small></div><div class="tbl-wrap"><table class="t"><thead><tr><th>Name in the report</th><th>From</th><th>Linked to store</th><th></th></tr></thead><tbody>
    ${s.aliases.map(a => `<tr><td><b>${esc(a.raw)}</b></td><td>${esc(a.source)}</td><td><select class="input" data-alias="${esc(a.alias)}">${opt(a.store_id)}</select></td><td class="n">${a.confirmed ? '<span class="chip good">Confirmed</span>' : `<button class="btn sm primary" data-act="alias-ok" data-alias="${esc(a.alias)}" data-store="${a.store_id}">Confirm</button>`} <button class="btn sm ghost" data-act="alias-new" data-alias="${esc(a.alias)}" title="Make this a separate store">Separate</button></td></tr>`).join("")}</tbody></table></div></div>
    <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Stores</h2><small>Head-office units use Saturday + Sunday as weekly offs</small></div><div class="tbl-wrap"><table class="t"><thead><tr><th>Store</th><th>Format</th><th>City</th><th>Code</th><th class="n">Head office</th></tr></thead><tbody>
    ${s.stores.map(st => `<tr><td><input class="input" value="${esc(st.name)}" data-rename="${st.id}"></td><td>${esc(st.format_label || st.format)}</td><td>${esc(st.city_label)}</td><td>${esc(st.code)}</td><td class="n"><label class="switch"><input type="checkbox" data-ho="${st.id}" ${st.is_ho ? "checked" : ""}><span></span></label></td></tr>`).join("")}</tbody></table></div></div>`;
};
SETTINGS.sections = async () => {
  const s = await API.call("section_map");
  const desc = m => m.codes ? "Sections " + m.codes.join(", ") : m.dept ? "Department " + m.dept : m.store ? "Whole store" : m.cco ? "CCO" : m.service ? "Service (attendance only)" : "Not linked";
  return `<div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Roster sections → BO sections</h2><small>Used to find each manager's area. Type codes like S054, S050 to change.</small></div><div class="tbl-wrap"><table class="t"><thead><tr><th>Roster section</th><th>Dept</th><th>Measured on</th><th>Change to</th><th></th></tr></thead><tbody>
  ${s.rows.map(r => `<tr><td><b>${esc(r.section)}</b></td><td>${esc(r.dept)}</td><td>${esc(desc(r.map))} ${r.overridden ? '<span class="chip gold">edited</span>' : ""}</td>
    <td><input class="input" placeholder="S054, S050 or dept 02 or store" data-secmap="${esc(r.key)}" style="width:230px"></td><td class="n">${r.overridden ? `<button class="btn sm ghost" data-act="sec-reset" data-key="${esc(r.key)}">Reset</button>` : ""}</td></tr>`).join("") || `<tr><td colspan="5"><div class="empty">Import a roster first.</div></td></tr>`}</tbody></table></div></div>`;
};
SETTINGS.holidays = async () => {
  const y = (S.month || new Date().toISOString()).slice(0, 4);
  const s = await API.call("holidays", {});
  return `<div class="panel"><div class="phd"><h2>Gazetted holidays</h2><button class="btn" data-act="hol-defaults" data-year="${y}">Add fixed national holidays for ${y}</button></div>
    <small style="color:var(--muted)">Eid, Muharram and other moon-dependent holidays change every year: add them here (or ask P&O AI: "Add 21 March 2027 as Eid holiday").</small>
    <div class="row"><input class="input" type="date" id="hol-day"><input class="input" id="hol-name" placeholder="Holiday name" style="flex:1"><button class="btn primary" data-act="hol-add">Add holiday</button></div>
    <div class="tbl-wrap"><table class="t"><thead><tr><th>Date</th><th>Holiday</th><th></th></tr></thead><tbody>${s.rows.map(h => `<tr><td>${fmtDate(h.day)}</td><td>${esc(h.name)}</td><td class="n"><button class="btn sm ghost danger" data-act="hol-del" data-day="${h.day}">Remove</button></td></tr>`).join("") || `<tr><td colspan="3"><div class="empty">No holidays yet.</div></td></tr>`}</tbody></table></div></div>`;
};
SETTINGS.leave = async () => {
  const s = await API.call("leaves", { month: S.month });
  return `<div class="panel"><div class="phd"><h2>Add leave</h2><small>Booked leave is not counted as absence</small></div>
    <div class="row"><input class="input" id="lv-emp" placeholder="Employee number" style="width:170px"><input class="input" type="date" id="lv-from"><input class="input" type="date" id="lv-to">
    <select class="input" id="lv-type">${["Annual Leave", "Sick Leave", "Casual Leave", "Maternity Leave", "Hajj / Umrah", "Compensatory", "Unpaid Leave", "Other"].map(x => `<option>${x}</option>`).join("")}</select>
    <button class="btn primary" data-act="lv-add">Add leave</button></div><small style="color:var(--muted)">Import a leave register on the Import screen, or drop it into Ask P&O AI in any layout.</small></div>
    <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Leave in ${esc((S.months.find(m => m.value === S.month) || {}).label || "this month")}</h2><small>${s.rows.length} records</small></div><div class="tbl-wrap"><table class="t"><thead><tr><th>Person</th><th>Store</th><th>Type</th><th>From</th><th>To</th><th>Source</th><th></th></tr></thead><tbody>
    ${s.rows.map(l => `<tr><td><b>${esc(l.name)}</b><span class="sub">${esc(l.emp_no)}</span></td><td>${esc(l.store)}</td><td>${esc(l.type)}</td><td>${fmtDate(l.d_from)}</td><td>${fmtDate(l.d_to)}</td><td>${esc(l.source || "file")}</td><td class="n"><button class="btn sm ghost danger" data-act="lv-del" data-id="${l.id}">Remove</button></td></tr>`).join("") || `<tr><td colspan="7"><div class="empty">No leave recorded for this month.</div></td></tr>`}</tbody></table></div></div>`;
};
SETTINGS.data = async () => {
  const s = await API.call("settings");
  const a = await API.call("audit");
  return `<div class="panel"><div class="phd"><h2>Your data</h2></div>
    <div class="setting"><div><b>Database</b><small>${esc(s.db_path)}</small></div></div>
    <div class="setting"><div><b>Back up</b><small>Save a copy of everything (keep it secure: it contains staff data)</small></div><button class="btn" data-act="backup">Back up…</button></div>
    <div class="setting"><div><b>Restore</b><small>Replace the data with a backup (the current data is kept as a safety copy)</small></div><button class="btn danger" data-act="restore">Restore…</button></div>
    <div class="setting"><div><b>Demo data</b><small>Explore P&O with fictional people and stores, in a separate database</small></div>${S.init.demo ? `<button class="btn" data-act="demo-off">Leave demo</button>` : `<button class="btn" data-act="demo-on">Try demo data</button>`}</div></div>
    <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Activity log</h2></div><div class="tbl-wrap" style="max-height:400px"><table class="t"><thead><tr><th>When</th><th>What</th><th>Details</th></tr></thead><tbody>${a.rows.map(r => `<tr><td>${esc(r.ts.replace("T", " "))}</td><td>${esc(r.action)}</td><td>${esc(r.detail || "")}</td></tr>`).join("")}</tbody></table></div></div>`;
};
SETTINGS.look = async () => {
  const s = await API.call("settings");
  return `<div class="panel"><div class="setting"><div><b>Theme</b><small>Follow Windows, or always light / dark</small></div><div class="seg">${[["auto", "Auto"], ["light", "Light"], ["dark", "Dark"]].map(([k, l]) => `<button data-act="theme" data-theme="${k}" aria-pressed="${s.theme === k}">${l}</button>`).join("")}</div></div>
    <div class="setting"><div><b>Hide names</b><small>Show employee codes instead of names everywhere and in exports (for screen-sharing)</small></div><label class="switch"><input type="checkbox" id="hide-names" ${s.hide_names ? "checked" : ""}><span></span></label></div></div>`;
};
AFTER.settings = () => {
  const sum = ro => { const t = $$(`[data-w="${ro}"]`).reduce((a, i) => a + (+i.value || 0), 0); const b = $(`[data-total="${ro}"]`); if (b) b.textContent = t; };
  $$("[data-w]").forEach(i => { i.oninput = () => sum(i.dataset.w); sum(i.dataset.w); });
  const an = $("#anon"); if (an) an.onchange = () => call("agent_settings", { anonymise: an.checked }).then(() => toast("Saved"));
  const hn = $("#hide-names"); if (hn) hn.onchange = () => call("settings_save", { hide_names: hn.checked }).then(() => { S.init.hide_names = hn.checked; toast(hn.checked ? "Names hidden" : "Names shown"); });
  $$("[data-alias]").forEach(s => { if (s.tagName === "SELECT") s.onchange = () => call("store_alias_set", { alias: s.dataset.alias, store_id: +s.value }).then(afterDataChange); });
  $$("[data-rename]").forEach(i => i.onchange = () => call("store_update", { store_id: +i.dataset.rename, name: i.value }).then(() => toast("Store renamed")));
  $$("[data-ho]").forEach(i => i.onchange = () => call("store_update", { store_id: +i.dataset.ho, is_ho: i.checked }).then(() => toast("Saved")));
  $$("[data-secmap]").forEach(i => i.onchange = () => {
    const v = i.value.trim(); if (!v) return;
    const codes = v.toUpperCase().match(/S\d{3}/g), dept = (v.match(/dept\w*\s*(\d{1,2})/i) || [])[1];
    const p = codes ? { codes } : dept ? { dept: dept.padStart(2, "0") } : /store/i.test(v) ? { store: true } : /serv|none/i.test(v) ? { service: true } : null;
    if (!p) return toast("Type section codes like S054, S050, or 'dept 02', or 'store'.", { err: true });
    call("section_map_set", { key: i.dataset.secmap, ...p }).then(() => { toast("Section link saved"); render(); });
  });
  if (S.setTab === "ai") { clearInterval(S.dlTimer); S.dlTimer = setInterval(async () => { if (S.page !== "settings" || S.setTab !== "ai") return clearInterval(S.dlTimer); const d = await API.call("downloads"); if (d.jobs.some(j => j.status === "running") || S.dlWas) { S.dlWas = d.jobs.some(j => j.status === "running"); render(); } }, 2500); }
};

/* ---------------------------------------------------------------- person sheet */
function compRow(c) {
  const col = c.score == null ? "var(--none)" : `var(--${band(c.score)})`;
  return `<div class="comp ${c.available ? "" : "na"}"><div class="lbl"><b>${esc(c.label)}</b><small>${esc(c.display || "No data: left out of the score")}${c.flag ? " · ⚠ " + esc(c.flag) : ""}</small></div>
    <div class="w" title="Weight">${c.weight}${c.share != null && c.share !== c.weight ? `<br><small>→${c.share}%</small>` : ""}</div><div class="bar"><i data-w="${c.score == null ? 0 : c.score * 10}" style="background:${col}"></i></div>
    <div class="sc">${c.score == null ? "—" : c.score.toFixed(1)}</div></div>`;
}
async function openPerson(emp, opts = {}) {
  emp = String(emp);
  let sh = S.sheetEl, scrim = S.scrimEl;
  const reuse = sh && sh.isConnected && !sh.dataset.closing;
  if (!reuse) {
    // a panel that is still sliding out is removed at once; the new one slides in fresh
    if (sh) { sh.remove(); scrim && scrim.remove(); }
    clearTimeout(S.sheetTimer);
    scrim = document.createElement("div"); scrim.className = "scrim"; scrim.onclick = () => closeSheet();
    sh = document.createElement("section"); sh.className = "sheet"; sh.setAttribute("role", "dialog");
    sh.innerHTML = `<div class="sheet-body"><div class="loading"><span class="spin"></span>Loading profile…</div></div>`;
    document.body.append(scrim, sh);
    S.sheetEl = sh; S.scrimEl = scrim; S.sheetStack = [];
    sh.getBoundingClientRect();                       // start the slide from off-screen, every time
    scrim.classList.add("on"); sh.classList.add("on");
  } else {
    if (S.sheet && S.sheet.emp === emp) return;
    if (S.sheet && !opts.back) S.sheetStack.push(S.sheet.emp);
    sh.classList.add("swapping");                     // the open panel stays put; only its content changes
  }
  const token = S.sheetToken = (S.sheetToken || 0) + 1;
  let p;
  try { p = await API.call("person", { emp, month: S.month }); }
  catch (e) {
    if (token !== S.sheetToken || !sh.isConnected) return;
    sh.classList.remove("swapping");
    sh.innerHTML = `<div class="sheet-body"><div class="errbox">${esc(e.message)}</div><button class="btn" data-act="sheet-close">Close</button></div>`;
    return;
  }
  if (token !== S.sheetToken || !sh.isConnected || sh.dataset.closing) return;   // a newer click or a close won
  S.sheet = { emp, tab: reuse && S.sheet ? S.sheet.tab : "overview", p };
  drawSheet();
  sh.classList.remove("swapping");
}
window.openPerson = openPerson;
function drawSheet() {
  const sh = $(".sheet"); if (!sh || !S.sheet) return;
  const { p, tab } = S.sheet;
  const a = p.attendance_detail;
  const tabs = [["overview", "Score"], ["attendance", "Attendance"], ["history", "History"], ["team", `Team (${p.team.length})`], ["leave", "Leave & notes"]];
  let body = "";
  if (tab === "overview") {
    body = `<div class="panel"><div class="phd"><h2>How the score is made</h2><small>Measured on: ${esc(p.domain)}</small></div>${p.components.map(compRow).join("")}
      <small style="color:var(--muted)">Weights are shared out over the parts that have data (→ shows the share used). 7 = target met, 10 = clearly beat it.</small></div>
      ${p.context.length ? `<div class="panel"><div class="phd"><h2>Context</h2><small>Shown for understanding; not scored</small></div><div class="row">${p.context.map(c => `<span class="chip">${esc(c.display)}</span>`).join("")}</div></div>` : ""}
      ${p.flags.length ? `<div class="panel"><div class="phd"><h2>Flags</h2></div><div class="row">${p.flags.map(f => `<span class="chip warn">${esc(f)}</span>`).join("")}</div></div>` : ""}`;
  } else if (tab === "attendance") {
    if (!a) body = `<div class="empty">This person is not in the attendance file for this month.</div>`;
    else {
      const first = new Date(a.calendar[0].day + "T00:00:00").getDay();
      const pad = (first + 6) % 7;
      body = `<div class="kpis"><div class="kpi"><span class="kpi-l">Worked</span><span class="kpi-v">${a.worked}</span><span class="kpi-s">of ${a.due} due days</span></div>
        <div class="kpi"><span class="kpi-l">Unexplained absence</span><span class="kpi-v">${a.absent}</span><span class="kpi-s">System says ${a.sys_absent ?? "—"}</span></div>
        <div class="kpi"><span class="kpi-l">Full 9h days</span><span class="kpi-v">${pct(a.compliance)}</span><span class="kpi-s">Avg ${a.avg_hours || "—"} · ${a.total_hours} h total</span></div>
        <div class="kpi"><span class="kpi-l">To fix</span><span class="kpi-v">${a.fixes}</span><span class="kpi-s">${a.missing_in} no IN · ${a.missing_out} no OUT · ${a.punched_absent} punched-absent</span></div></div>
        <div class="panel"><div class="cal">${["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map(d => `<div class="dh">${d}</div>`).join("")}${"<div></div>".repeat(pad)}
        ${a.calendar.map(c => { const full = c.kind === "worked" && c.minutes >= 540; const fix = ["missing_in", "missing_out", "punched_absent"].includes(c.status);
          const label = c.kind === "worked" ? (c.hours || (fix ? "fix" : "✓")) : c.kind === "absent" ? "Absent" : c.kind === "off" ? "Off" : c.kind === "leave" ? (c.leave || "Leave").split(" ")[0] : (c.holiday || "Holiday").split(" ")[0];
          return `<div class="d k-${full ? "full" : c.kind}${fix ? " k-fix" : ""}" title="${esc(fmtDate(c.day))}${c.t_in ? " · IN " + c.t_in : ""}${c.t_out ? " · OUT " + c.t_out : ""}${fix ? " · punch to fix" : ""}"><b>${+c.day.slice(8)}</b><span>${esc(label)}</span></div>`; }).join("")}</div>
        <div class="legend"><span><i class="k-full"></i>Full 9h</span><span><i class="k-worked"></i>Short day</span><span><i class="k-absent"></i>Absent</span><span><i class="k-off"></i>Weekly off</span><span><i class="k-leave"></i>Leave</span><span><i class="k-holiday"></i>Holiday</span><span><i style="box-shadow:inset 0 0 0 2px var(--warn)"></i>Punch to fix</span></div></div>`;
    }
  } else if (tab === "history") {
    body = `<div class="panel"><div class="phd"><h2>Score by month</h2></div><div id="ch-hist"></div></div>`;
  } else if (tab === "team") {
    body = `<div class="panel"><div class="plist">${p.team.map(t => `<button class="prow" data-person="${t.emp}"><span class="av">${esc(initials(t.name))}</span><span class="who"><b>${esc(t.name)}</b><small>${esc(t.designation)} · ${esc(t.section || t.store)}</small></span>${pill(t.score, t.band_key)}</button>`).join("") || `<div class="empty">No direct reports in the roster.</div>`}</div></div>`;
  } else {
    body = `<div class="panel"><div class="phd"><h2>Leave</h2></div><div class="row"><input class="input" type="date" id="pl-from"><input class="input" type="date" id="pl-to"><select class="input" id="pl-type">${["Annual Leave", "Sick Leave", "Casual Leave", "Maternity Leave", "Hajj / Umrah", "Compensatory", "Unpaid Leave", "Other"].map(x => `<option>${x}</option>`).join("")}</select><button class="btn primary" data-act="pl-add">Add</button></div>
      ${p.leaves.map(l => `<div class="row" style="justify-content:space-between;border-bottom:1px solid var(--line-2);padding:6px 0"><span><b>${esc(l.type)}</b> · ${fmtDate(l.d_from)} – ${fmtDate(l.d_to)}</span><button class="btn sm ghost danger" data-act="pl-del" data-id="${l.id}">Remove</button></div>`).join("") || `<small style="color:var(--muted)">No leave recorded.</small>`}</div>
      <div class="panel"><div class="phd"><h2>Notes</h2></div><div class="row"><input class="input" id="pn-text" placeholder="Add a note (visible only in P&O)" style="flex:1"><button class="btn primary" data-act="pn-add">Add</button></div>
      ${p.notes.map(n => `<div class="row" style="justify-content:space-between;border-bottom:1px solid var(--line-2);padding:6px 0"><span>${esc(n.text)} <small style="color:var(--muted)">· ${esc(n.created_at.slice(0, 10))}</small></span><button class="btn sm ghost danger" data-act="pn-del" data-id="${n.id}">Remove</button></div>`).join("") || `<small style="color:var(--muted)">No notes.</small>`}</div>`;
  }
  const head = `<div class="sheet-head">${S.sheetStack && S.sheetStack.length ? `<button class="close back" data-act="sheet-back" aria-label="Back" title="Back">${ic("back", 16)}</button>` : ""}<span class="av lg">${esc(initials(p.name))}</span><div style="flex:1;min-width:0"><h2>${esc(p.name)}</h2>
      <p>${esc(p.designation)} · ${esc(p.store)} · ${esc(p.role_label)} · <span class="num">${esc(p.emp)}</span></p>
      <p style="font-size:12.5px">${p.chain.length ? "Reports to " + p.chain.map(c => c.emp ? `<a href="#" data-person="${c.emp}" style="color:var(--brand);font-weight:700;text-decoration:none">${esc(c.name)}</a>` : esc(c.name)).join(" › ") : esc(p.manager.name ? "Reports to " + p.manager.name : "")}
      ${p.manager.status === "uncertain" ? ' <span class="chip warn">name matches several people</span>' : ""}</p></div>
      <div style="text-align:center">${Charts.ring(p.score, 92, p.band_key, p.score == null ? "" : "/10")}<div style="margin-top:4px">${p.score == null ? statusChip(p) || '<span class="chip">No score</span>' : `<span class="chip ${p.band_key === "excellent" || p.band_key === "good" ? "good" : p.band_key === "ok" ? "gold" : p.band_key === "warn" ? "warn" : "bad"}">${esc(p.band)}</span>`}${p.provisional ? ' <span class="chip warn">provisional</span>' : ""}</div></div>
      <button class="close" data-act="sheet-close" aria-label="Close">${ic("x", 16)}</button></div>
    <div style="padding:10px 22px 0;display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap"><div class="seg">${tabs.map(([k, l]) => `<button data-act="sheet-tab" data-tab="${k}" aria-pressed="${tab === k}">${l}</button>`).join("")}</div>
      <button class="btn sm" data-act="export" data-pack="scorecard" data-emp="${p.emp}">${ic("export", 14)}Scorecard</button></div>
    `;
  const key = p.emp + "|" + S.month + "|" + (S.sheetStack ? S.sheetStack.length : 0);
  if (sh.dataset.key !== key || !sh.querySelector(".sheet-body")) {
    sh.innerHTML = head + `<div class="sheet-body">${body}</div>`;
    sh.dataset.key = key;
  } else {
    sh.querySelectorAll('[data-act="sheet-tab"]').forEach(b => b.setAttribute("aria-pressed", b.dataset.tab === tab));
    const bd = sh.querySelector(".sheet-body"); bd.innerHTML = body; bd.scrollTop = 0;
  }
  requestAnimationFrame(() => sh.querySelectorAll(".comp .bar i[data-w]").forEach(i => { i.style.width = i.dataset.w + "%"; }));
  if (tab === "history") Charts.line($("#ch-hist"), { labels: p.history.map(h => h.label), series: [{ name: "Score", values: p.history.map(h => h.score) }, { name: "Attendance score", values: p.history.map(h => h.attendance) }], fmt: "score", yMin: 0, yMax: 10, height: 240 });
}
function closeSheet(instant) {
  const sh = S.sheetEl, sc = S.scrimEl;
  S.sheet = null; S.sheetEl = null; S.scrimEl = null; S.sheetStack = [];
  S.sheetToken = (S.sheetToken || 0) + 1;
  if (!sh) return;
  if (instant) { sh.remove(); sc && sc.remove(); return; }
  sh.dataset.closing = "1";
  sh.classList.remove("on"); sc && sc.classList.remove("on");
  setTimeout(() => { sh.remove(); sc && sc.remove(); }, 450);
}

/* ---------------------------------------------------------------- export, modal, menu */
function modal(html) {
  closeModal();
  const sc = document.createElement("div"); sc.className = "scrim"; sc.dataset.modal = 1; sc.onclick = closeModal;
  const m = document.createElement("div"); m.className = "modal"; m.innerHTML = html;
  document.body.append(sc, m);
  requestAnimationFrame(() => { sc.classList.add("on"); m.classList.add("on"); });
  return m;
}
function closeModal() { $$(".modal").forEach(m => m.remove()); $$(".scrim[data-modal]").forEach(s => s.remove()); }
const PACKS = [["director", "Monthly HR Director Pack", "Country / filtered summary, store league, top & bottom, attendance health, trends"],
  ["po", "P&O Review Pack", "Store league, section heatmaps, leaders & leader index, bench strength, turnover, roster gaps (P&O workbook)"],
  ["store", "Store Report", "The selected store: GM scorecard, departments, sections with managers, attendance"],
  ["dept", "Department Comparison", "The selected department across stores, with its managers"],
  ["scorecard", "Manager Scorecards", "One page per manager in the current filters (or one person)"],
  ["attendance", "Attendance Exceptions", "Real vs system absence, long absences, punches to fix, 9-hour compliance"],
  ["people", "People Ranking", "Everyone in the current filters with scores and attendance"]];
function openExport(o = {}) {
  const def = o.pack || { review: "po", talent: "po", retention: "po", shifts: "po", home: "director", people: "people", performance: "scorecard", stores: "director", store: "store", attendance: "attendance" }[S.page] || "director";
  const m = modal(`<h3>Export</h3><p style="color:var(--muted);margin:0 0 12px">Uses the month and filters on screen: <b>${esc($(".crumbs") ? $(".crumbs").textContent.replace(/🇵🇰\s*/, "") : "Pakistan")}</b></p>
    <div style="display:flex;flex-direction:column;gap:6px">${PACKS.map(([k, l, d]) => `<label class="setting" style="cursor:pointer;padding:8px 4px"><span><b>${l}</b><small>${d}</small></span><input type="radio" name="pack" value="${k}" ${k === def ? "checked" : ""}></label>`).join("")}</div>
    <div class="setting"><div><b>Format</b></div><div class="seg" id="fmtseg">${[["pdf", "PDF"], ["pptx", "PowerPoint"], ["xlsx", "Excel"]].map(([k, l], i) => `<button data-fmt="${k}" aria-pressed="${i === 0}">${l}</button>`).join("")}</div></div>
    <div class="setting"><div><b>Hide names</b><small>Employee codes only, for packs going beyond HR</small></div><label class="switch"><input type="checkbox" id="exp-hide" ${S.init.hide_names ? "checked" : ""}><span></span></label></div>
    <div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" data-act="modal-close">Cancel</button><button class="btn primary" id="exp-go">${ic("export", 16)}Export</button></div>`);
  $$("#fmtseg button", m).forEach(b => b.onclick = () => $$("#fmtseg button", m).forEach(x => x.setAttribute("aria-pressed", x === b)));
  $("#exp-go", m).onclick = async () => {
    const pack = $("input[name=pack]:checked", m).value, fmt = $("#fmtseg button[aria-pressed=true]", m).dataset.fmt;
    const btn = $("#exp-go", m); btn.disabled = true; btn.innerHTML = `<span class="spin" style="width:14px;height:14px"></span> Preparing…`;
    try {
      const r = await API.call("export", { pack, fmt, month: S.month, scope: S.scope, emp: o.emp || null, store_id: o.store || S.scope.store_id || null, hide: $("#exp-hide", m).checked });
      closeModal();
      if (!r.cancelled) toast(`Saved ${r.name}`, { action: "Open", onAction: () => API.call("open_path", { path: r.path }), ms: 7000 });
    } catch (e) { btn.disabled = false; btn.innerHTML = "Export"; fail(e); }
  };
}

/* ---------------------------------------------------------------- actions */
const ACT = {
  back: () => { const h = (S.hist || []).pop(); if (h) { closeSheet(); go(h[0], h[1], { back: true }); } },
  "more-filters": () => { S.moreFilters = !S.moreFilters; topbar(); },
  "scope-clear": async () => { S.scope = {}; store.set("scope", S.scope); await refreshOptions(); render(); },
  "scope-up": async b => { const order = ["city", "format", "store_id", "dept", "section"]; for (const k of order.slice(order.indexOf(b.dataset.key) + 1)) delete S.scope[k]; store.set("scope", S.scope); await refreshOptions(); render(); },
  export: b => openExport({ pack: b.dataset.pack, emp: b.dataset.emp, store: b.dataset.store ? +b.dataset.store : null }),
  "modal-close": closeModal,
  present: () => { document.body.classList.toggle("present"); if (document.body.classList.contains("present")) { if (S.page !== "home") go("home"); toast("Presenting · use ↑ ↓ or the buttons · Esc to exit"); } },
  "present-next": () => presentStep(1), "present-prev": () => presentStep(-1),
  alert: b => { const k = b.dataset.key; if (k === "variance") return go("stores"); S.people = { ...S.people, flag: k, band: "", role: "" }; go("people"); },
  "people-sort": b => { S.people = { ...S.people, sort: "score", desc: b.dataset.desc === "1", band: "", flag: "" }; go("people"); },
  role: b => { S.people.role = b.dataset.role; render(); }, band: b => { S.people.band = b.dataset.band; render(); },
  "flag-clear": () => { S.people.flag = ""; render(); },
  sort: b => { const k = b.dataset.key; if (S.people.sort === k) S.people.desc = !S.people.desc; else { S.people.sort = k; S.people.desc = !["name", "store", "role"].includes(k); } render(); },
  compare: () => openCompare(), "perf-role": b => { S.perfRole = b.dataset.role; render(); },
  store: b => go("store", +b.dataset.id), "focus-store": b => { setScope("store_id", +b.dataset.id).then(() => go("home")); },
  "att-tab": b => { S.attTab = b.dataset.tab; render(); },
  "tree-toggle": (b, e) => { e.stopPropagation(); const ul = b.closest("li").querySelector(":scope > ul"); if (ul) { ul.hidden = !ul.hidden; b.textContent = ul.hidden ? "+" : "–"; } },
  "tree-all": () => { $$(".tree ul").forEach(u => u.hidden = false); $$(".tree .tg").forEach(t => t.textContent = "–"); },
  "ask-sugg": b => ask(b.dataset.q || b.textContent), "ask-send": () => ask($("#askq").value), "ask-clear": () => { saveChat(); S.chat = []; S.chatId = null; render(); },
  "ask-attach": async () => { if (window.qt) { const r = await call("agent_attach"); if (r.paths && r.paths.length) { S.attach.push(...r.paths); drawChat(); } } else toast("Drag a file onto this window to attach it."); },
  "att-rm": b => { S.attach.splice(+b.dataset.i, 1); drawChat(); },
  confirm: async b => { const r = await call("agent_confirm", { action_id: b.dataset.id, approve: true }); markAction(b, "ok"); toast(r.message); await afterDataChange(false); },
  cancel: async b => { await call("agent_confirm", { action_id: b.dataset.id, approve: false }); markAction(b, "no"); },
  pick: async () => { if (window.qt) { const r = await call("pick_files"); if (!r.cancelled) { S.importSess = r; render(); } } else $("#filein").click(); },
  paste: () => {
    const m = modal(`<h3>Paste data</h3><p style="color:var(--muted);margin:0 0 10px">Copy the cells in Excel (including the header rows) and paste them here.</p><textarea class="input" id="paste-t" rows="12" style="width:100%;font-family:monospace;font-size:12px"></textarea>
      <div class="row" style="justify-content:flex-end;margin-top:10px"><button class="btn" data-act="modal-close">Cancel</button><button class="btn primary" id="paste-go">Preview</button></div>`);
    $("#paste-go", m).onclick = async () => { const t = $("#paste-t", m).value; if (!t.trim()) return; closeModal(); S.importSess = await call("import_analyze", { text: t, name: "Pasted data" }); render(); };
    setTimeout(() => $("#paste-t", m).focus(), 100);
  },
  "import-cancel": () => { S.importSess = null; render(); },
  "import-commit": async b => {
    const opts = {};
    $$("[data-opt]").forEach(i => { if (!String(i.value || "").trim()) return; (opts[i.dataset.file] = opts[i.dataset.file] || {})[i.dataset.sheet] = { ...((opts[i.dataset.file] || {})[i.dataset.sheet] || {}), [i.dataset.opt]: i.value }; });
    b.disabled = true; b.innerHTML = `<span class="spin" style="width:14px;height:14px"></span> Importing…`;
    try {
      const r = await API.call("import_commit", { token: S.importSess.token, options: opts });
      const lines = r.done.flatMap(f => f.error ? [`${f.file}: ${f.error}`] : f.results.map(x => `${x.kind}: ${x.status === "ok" ? x.rows.toLocaleString("en-US") + " rows" : x.message}`));
      S.importSess = null;
      toast(lines.join(" · "), { ms: 7000 });
      await afterDataChange(true);
    } catch (e) { fail(e); b.disabled = false; b.textContent = "Import"; }
  },
  undo: async b => { await call("import_undo", { import_id: +b.dataset.id }); toast("Import undone", { action: "Restore", onAction: () => call("import_redo", { import_id: +b.dataset.id }).then(() => afterDataChange(true)) }); await afterDataChange(true); },
  redo: async b => { await call("import_redo", { import_id: +b.dataset.id }); toast("Import restored"); await afterDataChange(true); },
  "set-tab": b => { S.setTab = b.dataset.tab; render(); },
  "weights-save": async () => {
    const w = {}; $$("[data-w]").forEach(i => { if (i.value !== "" && +i.value > 0) (w[i.dataset.w] = w[i.dataset.w] || {})[i.dataset.p] = +i.value; });
    const rules = {}; $$("[data-rule]").forEach(i => { (rules[i.dataset.rule] = rules[i.dataset.rule] || [])[+i.dataset.i] = +i.value; }); $$("[data-rule1]").forEach(i => rules[i.dataset.rule1] = +i.value);
    for (const [k, v] of Object.entries(rules)) if (Array.isArray(v) && !(v[0] < v[1] && v[1] < v[2])) return toast(`Thresholds for ${k} must go up from left to right.`, { err: true });
    await call("settings_save", { weights: w, rules }); toast("Scoring saved · scores recalculated"); render();
  },
  "weights-reset": async () => { await call("settings_reset"); toast("Default scoring restored"); render(); },
  "ai-mode": async b => { const st = await setEngine(b.dataset.mode); toast(`Now answering with ${st.label}`); render(); },
  "prov-save": async b => {
    const p = b.dataset.p, k = $("#key-" + p).value.trim(), model = $("#model-" + p).value.trim();
    await call("agent_settings", { provider: p, key: k || null, model: model || null });
    toast(k ? "Key saved · testing it…" : "Saved"); await reinit(); await render();
    if (k) { const r = await API.call("agent_test", { provider: p }); toast(r.message, { err: !r.ok, ms: 7000 }); if (S.page === "settings") render(); }
  },
  "prov-test": async b => {
    const p = b.dataset.p; b.disabled = true;
    try { const r = await API.call("agent_test", { provider: p, key: $("#key-" + p).value.trim() || null, model: $("#model-" + p).value.trim() || null }); toast(r.message, { err: !r.ok, ms: 7000 }); if (r.ok && r.models && r.models.length && S.page === "settings") render(); }
    catch (e) { fail(e); }
    b.disabled = false;
  },
  "prov-clear": async b => { await call("agent_settings", { provider: b.dataset.p, clear_key: true }); toast("Key removed"); await reinit(); render(); },
  "offline-install": async b => { await call("offline_install", { what: b.dataset.what }); toast("Download started"); S.dlWas = true; render(); },
  "offline-pick": async () => { const r = await call("offline_pick_model"); if (!r.cancelled) { toast("Model linked"); await reinit(); render(); } },
  "alias-ok": async b => { await call("store_alias_set", { alias: b.dataset.alias, store_id: +b.dataset.store }); await afterDataChange(false); render(); },
  "alias-new": async b => { await call("store_new", { alias: b.dataset.alias }); toast("Made a separate store"); await afterDataChange(false); render(); },
  "sec-reset": async b => { await call("section_map_set", { key: b.dataset.key, reset: true }); render(); },
  "hol-defaults": async b => { const r = await call("holidays_defaults", { year: +b.dataset.year }); toast(`${r.added} holidays added`); render(); },
  "hol-add": async () => { await call("holiday_add", { day: $("#hol-day").value, name: $("#hol-name").value }); toast("Holiday added"); render(); },
  "hol-del": async b => { await call("holiday_delete", { day: b.dataset.day }); render(); },
  "lv-add": async () => { await call("leave_add", { emp: $("#lv-emp").value.trim(), d_from: $("#lv-from").value, d_to: $("#lv-to").value || $("#lv-from").value, type: $("#lv-type").value }); toast("Leave added"); render(); },
  "lv-del": async b => { await call("leave_delete", { leave_id: +b.dataset.id }); render(); },
  backup: async () => { const r = await call("backup"); if (!r.cancelled) toast("Backup saved: " + r.path, { ms: 7000 }); },
  restore: async () => { if (!confirm("Replace all P&O data with the backup? The current data is kept as a safety copy.")) return; const r = await call("restore"); if (!r.cancelled) { toast("Backup restored"); await afterDataChange(true); } },
  "demo-on": async () => { toast("Loading demo data…"); S.init = await call("demo", { on: true }); S.scope = {}; await boot(true); toast("Demo data: fictional people and stores"); },
  "demo-off": async () => { S.init = await call("demo", { on: false }); S.scope = {}; await boot(true); toast("Back to your data"); },
  theme: async b => { await call("settings_save", { theme: b.dataset.theme }); applyTheme(b.dataset.theme); render(); },
  "sheet-close": () => closeSheet(),
  "sheet-back": () => { const prev = S.sheetStack.pop(); if (prev) openPerson(prev, { back: true }); }, "sheet-tab": b => { S.sheet.tab = b.dataset.tab; drawSheet(); },
  "pl-add": async () => { await call("leave_add", { emp: S.sheet.emp, d_from: $("#pl-from").value, d_to: $("#pl-to").value || $("#pl-from").value, type: $("#pl-type").value }); toast("Leave added · attendance recalculated"); await refreshSheet(); },
  "pl-del": async b => { await call("leave_delete", { leave_id: +b.dataset.id }); await refreshSheet(); },
  "pn-add": async () => { await call("note_add", { emp: S.sheet.emp, text: $("#pn-text").value }); await refreshSheet(); },
  "pn-del": async b => { await call("note_delete", { note_id: +b.dataset.id }); await refreshSheet(); },
};
async function refreshSheet() { if (!S.sheet) return; const tab = S.sheet.tab; if (S.sheetEl) delete S.sheetEl.dataset.key; S.sheet.p = await API.call("person", { emp: S.sheet.emp, month: S.month }); S.sheet.tab = tab; drawSheet(); }
function markAction(b, how) { const m = S.chat[+b.dataset.m]; if (m) (m.actions || []).forEach(a => { if (a.id === b.dataset.id) a.done = how; }); drawChat(); }
async function afterDataChange(full) {
  S.init = await API.call("init");
  S.months = S.init.months;
  if (!S.months.some(m => m.value === S.month)) S.month = S.init.month;
  await refreshOptions();
  shell();
  render();
}
async function reinit() { S.init = await API.call("init"); shell(); }

function presentStep(dir) {
  const v = $("#view"), slides = $$(".slide, .kpis", v);
  const y = v.scrollTop + 5;
  const tops = slides.map(s => s.offsetTop - 20);
  let i = tops.findIndex(t => t > y); if (i < 0) i = tops.length;
  const target = dir > 0 ? tops[i] : tops[Math.max(0, i - 2)];
  if (target != null) v.scrollTo({ top: target, behavior: "smooth" });
}
async function openCompare() {
  const r = await call("compare", { emps: Array.from(S.selected), month: S.month });
  const ps = r.people;
  const parts = Array.from(new Set(ps.flatMap(p => p.components.map(c => c.label))));
  modal(`<h3>Compare</h3><div class="tbl-wrap"><table class="t"><thead><tr><th></th>${ps.map(p => `<th>${esc(p.name)}<span class="sub" style="text-transform:none;letter-spacing:0">${esc(p.designation)} · ${esc(p.store)}</span></th>`).join("")}</tr></thead><tbody>
    <tr><td><b>Score</b></td>${ps.map(p => `<td>${pill(p.score, p.band_key)}</td>`).join("")}</tr>
    ${parts.map(l => `<tr><td>${esc(l)}</td>${ps.map(p => { const c = p.components.find(x => x.label === l); return `<td>${c ? (c.score == null ? "—" : c.score.toFixed(1)) + `<span class="sub">${esc(c.display || "")}</span>` : "·"}</td>`; }).join("")}</tr>`).join("")}
    <tr><td>Attendance</td>${ps.map(p => `<td>${p.attendance_detail ? `${p.attendance_detail.worked} worked · ${p.attendance_detail.absent} absent` : "—"}</td>`).join("")}</tr></tbody></table></div>
    <div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" data-act="clear-sel">Clear selection</button><button class="btn primary" data-act="modal-close">Done</button></div>`).style.width = "min(900px,calc(100vw - 40px))";
}
ACT["clear-sel"] = () => { S.selected.clear(); closeModal(); render(); };

/* ---------------------------------------------------------------- P&O review (ten-tab P&O workbook) */
S.po = { metric: "sales_vs_budget", q: "", store: "", tab: "leaders", leader: null, shiftStore: "" };
const PO_HEAT = [["sales_vs_budget", "Sales vs budget", 100, 92, true, v => v.toFixed(0) + "%"],
  ["growth", "Growth vs LY", 5, 0, true, v => (v > 0 ? "+" : "") + v.toFixed(0) + "%"],
  ["productivity_vs_target", "Productivity vs target", 0, -10, true, v => (v > 0 ? "+" : "") + v.toFixed(0) + "%"],
  ["shrink_variance", "Shrinkage vs budget", 0, -1, true, v => (v > 0 ? "+" : "") + v.toFixed(1)],
  ["stock_days", "Stock days vs budget", 105, 130, false, v => v.toFixed(0) + "%"],
  ["oos", "Out of stock", 8, 15, false, v => v.toFixed(1) + "%"], ["margin", "Net margin", 5, 0, true, v => v.toFixed(1) + "%"]];
const poTone = (v, good, bad, higher = true) => { if (v == null) return ""; let x = v, g = good, b = bad; if (!higher) { x = -v; g = -good; b = -bad; } return x >= g ? "good" : x <= b ? "bad" : "warn"; };
const poCell = (v, good, bad, higher, f) => v == null ? `<td class="n po-h none">—</td>` : `<td class="n po-h ${poTone(v, good, bad, higher)}">${f(v)}</td>`;
const poMoney = v => v == null ? "—" : Math.abs(v) >= 1e9 ? (v / 1e9).toFixed(2) + " bn" : Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(1) + " M" : money(v);
const poSigned = (v, d = 1, s = "%") => v == null ? "—" : (v > 0 ? "+" : "") + (+v).toFixed(d) + s;
const poStatus = s => `<span class="chip ${{ "On track": "good", Watch: "warn", "At risk": "bad" }[s] || ""}">${esc(s)}</span>`;
const poIndex = v => v == null ? "—" : pill(v / 10, band(v / 10));
const poEmpty = () => `<div class="panel"><div class="hero"><div class="logo" style="width:64px;height:64px;font-size:22px;border-radius:18px">P&amp;O</div>
  <h2>Import the P&amp;O workbook</h2><p>Drop the whole workbook on the Import screen. All ten tabs are recognised by their columns: YTD productivity,
  shift roster, performance ratings, store performance (sales), NPS, shrinkage &amp; stock days, time in role, DA, turnover and the Basic Sheet.
  Birth dates, phone numbers, e-mails and marital status are never read.</p>
  <div class="row" style="justify-content:center"><button class="btn primary" data-go="import">${ic("import", 16)}Import the workbook</button></div></div></div>`;

/* period bar: which period the P&O screens show (latest, one month MTD, or a YTD range) and what each tab adds */
const PTYPE = { general: ["General", ""], mtd: ["MTD", "info"], ytd: ["YTD", "gold"] };
function periodBar(p) {
  if (!p || !p.months) return "";
  const v = p.view || { type: "latest" };
  const opt = (sel) => p.months.map(m => `<option value="${m.value}" ${m.value === sel ? "selected" : ""}>${esc(m.label)}</option>`).join("");
  const last = p.default_to || (p.months.length ? p.months[p.months.length - 1].value : "");
  const picks = v.type === "mtd" ? `<label class="pv-l">Month<select class="input sm" data-pv="to">${opt(v.to || last)}</select></label>`
    : v.type === "ytd" ? `<label class="pv-l">From<select class="input sm" data-pv="from">${opt(v.from)}</select></label><label class="pv-l">To<select class="input sm" data-pv="to">${opt(v.to || last)}</select></label>` : "";
  const cov = (p.coverage || []).map(c => `<tr><td>${esc(c.name)}</td><td>${c.type ? `<span class="chip ${PTYPE[c.type] ? PTYPE[c.type][1] : ""}">${esc(PTYPE[c.type] ? PTYPE[c.type][0] : c.type)}</span>` : ""} ${esc(c.label)}</td><td class="n">${c.rows ? c.rows.toLocaleString("en-US") : "—"}</td><td>${c.note ? `<small style="color:var(--warn-ink)">${esc(c.note.split(": ").slice(1).join(": "))}</small>` : ""}</td></tr>`).join("");
  return `<div class="pbar"><span class="pbar-t">${ic("shifts", 15)}Period</span>
      <div class="seg sm">${[["latest", "Latest"], ["mtd", "Month (MTD)"], ["ytd", "Year to date (YTD)"]].map(([k, l]) => `<button data-act="pv-type" data-t="${k}" aria-pressed="${v.type === k}" ${k !== "latest" && !p.months.length ? "disabled" : ""}>${l}</button>`).join("")}</div>
      ${picks}<span class="spacer"></span>
      <details class="pcov"><summary>${esc(p.label)}${p.notes && p.notes.length ? ` <span class="chip warn" title="Tabs without data for exactly this period use the closest one">${p.notes.length} tab${p.notes.length > 1 ? "s" : ""} use nearest period</span>` : ""}</summary>
        <div class="pcov-box"><p>General data (employee master, time in role, ratings) counts for every period. Dated data (turnover, shift roster) is cut to the period. Summary tabs use the file whose period matches; if none does, the closest is used and marked.</p>
        <table class="t"><thead><tr><th>Data</th><th>Covers</th><th class="n">Rows</th><th></th></tr></thead><tbody>${cov}</tbody></table></div></details></div>`;
}
ACT["pv-type"] = b => setView({ type: b.dataset.t });
async function setView(patch) {
  const cur = (DATA.period && DATA.period.view) || { type: "latest" };
  const v = { ...cur, ...patch };
  const p = DATA.period || {};
  const last = p.default_to || (p.months && p.months.length ? p.months[p.months.length - 1].value : null);
  if (v.type !== "latest") v.to = v.to || last;
  if (v.type === "ytd" && (!v.from || patch.to && !patch.from && !cur.from)) v.from = (p.ytd_from || {})[v.to] || (v.to ? v.to.slice(0, 4) + "-01" : null);
  if (v.type === "ytd" && v.from && v.to && v.from > v.to) [v.from, v.to] = [v.to, v.from];
  DATA.period = await API.call("po_view", v);
  render();
}
document.addEventListener("change", e => { const t = e.target.closest && e.target.closest("[data-pv]"); if (t) setView({ [t.dataset.pv]: t.value }); });
PAGES.review = async () => {
  const d = DATA.review = await API.call("po_review", { metric: S.po.metric });
  if (!d.has_data) return poEmpty();
  const h = d.headline;
  const kpi = (l, v, s, go) => `<button class="kpi" ${go ? `data-go="${go}"` : ""}><span class="kpi-l">${esc(l)}</span><span class="kpi-v">${v}</span><span class="kpi-s"><span>${s}</span></span></button>`;
  const high = d.alerts.filter(a => a.severity === "High").length;
  const [, label, good, bad, higher, f] = PO_HEAT.find(m => m[0] === S.po.metric);
  const heat = d.heat.sections.length ? `<div class="tbl-wrap"><table class="t po-heat"><thead><tr><th>Store</th>${d.heat.sections.map(s => `<th class="n">${esc(s.replace("Fruits & Vegetables", "F&V").replace("Light Household", "LHH").replace("Heavy Household", "HHH"))}</th>`).join("")}</tr></thead>
    <tbody>${d.heat.stores.map((st, i) => `<tr><td><b>${esc(st)}</b></td>${d.heat.values[i].map(v => poCell(v, good, bad, higher, f)).join("")}</tr>`).join("")}</tbody></table></div>` : `<div class="empty">No data for this measure.</div>`;
  return `
    <div class="ph slide"><div><h1>Business review · Country</h1><p>${h.stores} stores · ${h.leaders} section leaders · data as of ${fmtDate(h.as_of)}</p></div>
      <div class="row"><button class="btn" data-act="export" data-pack="po">${ic("export", 16)}Export P&amp;O pack</button></div></div>
    <div class="kpis stagger po-kpis">
      ${kpi("Sales · " + (d.period.sales_label || "latest"), poMoney(h.sales), `${pct(h.sales_vs_budget_pct, 1)} of budget`, "stores")}
      ${kpi("Growth vs last year", poSigned(h.growth_pct), "All stores")}
      ${kpi("Productivity vs target", poSigned(h.productivity_vs_target_pct), "Average across stores")}
      ${kpi("Stores on track", `${h.stores_on_track}<small>/${h.stores}</small>`, `${h.stores_at_risk} at risk`)}
      ${kpi("Leavers · " + d.period.leaver_window, h.leavers_12m ?? "—", `${pct(h.voluntary_pct)} voluntary`, "retention")}
      ${kpi("Open alerts", d.alerts.length, `${high} high priority`)}
    </div>
    <div class="panel flush slide"><div class="phd" style="padding:14px 16px 0"><h2>Store league table</h2><small>Status combines sales vs budget, productivity vs target and shrinkage</small></div>
      <div class="tbl-wrap"><table class="t"><thead><tr><th>Store</th><th>Status</th><th class="n">Sales</th><th class="n">vs budget</th><th class="n">Growth</th><th class="n">Prod. vs target</th><th class="n">Shrink vs bud.</th><th class="n">OOS</th><th class="n">Margin</th><th class="n">NPS</th><th class="n">Leavers</th><th class="n">DA</th><th class="n">Leader index</th></tr></thead>
      <tbody>${d.stores.map(c => `<tr class="click" data-act="po-store" data-store="${esc(c.store)}"><td><b>${esc(c.store)}</b><span class="sub">${esc(c.format || "")}</span></td><td>${poStatus(c.status)}</td>
        <td class="n">${poMoney(c.sales)}</td>${poCell(c.sales_vs_budget_pct, 100, 92, true, v => v.toFixed(0) + "%")}${poCell(c.growth_pct, 5, 0, true, v => poSigned(v))}
        ${poCell(c.productivity_vs_target_pct, 0, -10, true, v => poSigned(v, 0))}${poCell(c.shrink_variance_avg, 0, -1, true, v => poSigned(v, 1, " pp"))}
        ${poCell(c.oos_pct, 8, 15, false, v => v.toFixed(1) + "%")}<td class="n">${pct(c.margin_pct, 1)}</td><td class="n">${c.nps == null ? "—" : Math.round(c.nps)}</td>
        ${poCell(c.leavers_12m, 2, 6, false, v => v)}<td class="n">${c.da_cases ?? "—"}</td><td class="n">${poIndex(c.avg_leader_score)}</td></tr>`).join("")}</tbody></table></div></div>
    <div class="panel slide"><div class="phd"><h2>Section heatmap</h2><div class="seg">${PO_HEAT.map(([k, l]) => `<button data-act="po-metric" data-metric="${k}" aria-pressed="${S.po.metric === k}">${l}</button>`).join("")}</div></div>
      <small style="color:var(--muted)">${esc(label)} · stores × sections · green on plan, amber watch, red act · — not in the workbook</small>${heat}</div>
    <div class="grid g2 slide">
      <div class="panel"><div class="phd"><h2>What needs attention</h2><small>${d.alerts.length} alerts from every tab, biggest first</small></div>
        <div style="display:flex;flex-direction:column;gap:8px;max-height:520px;overflow:auto">${d.alerts.slice(0, 30).map(a => `<div class="alert ${a.severity === "High" ? "bad" : a.severity === "Medium" ? "warn" : ""}"><span class="ic">${a.severity === "High" ? "!" : a.severity === "Medium" ? "•" : "i"}</span>
          <span><b>${esc(a.store)}</b> · ${esc(a.message)}<small style="display:block;color:var(--muted)">${esc(a.area)}</small></span></div>`).join("")}</div></div>
      <div class="panel"><div class="phd"><h2>Sales vs budget by store</h2><small>% of budget · click a store for its leaders</small></div><div id="ch-po-sales"></div></div>
    </div>
    <small style="color:var(--muted)">Sources · ${d.sources.map(s => `${esc(s.kind)}: ${esc(s.source)}`).join(" · ")}</small>`;
};
AFTER.review = () => {
  const d = DATA.review; if (!d || !d.has_data || !$("#ch-po-sales")) return;
  const rows = d.stores.filter(c => c.sales_vs_budget_pct != null).sort((a, b) => b.sales_vs_budget_pct - a.sales_vs_budget_pct);
  Charts.hbar($("#ch-po-sales"), { labels: rows.map(r => r.store), values: rows.map(r => r.sales_vs_budget_pct), fmt: "pct0", ref: 100, name: "% of budget",
    colors: rows.map(r => r.sales_vs_budget_pct >= 100 ? "var(--good)" : r.sales_vs_budget_pct >= 92 ? "var(--warn)" : "var(--bad)"),
    onClick: i => { S.po = { ...S.po, store: rows[i].store, q: "", tab: "leaders" }; go("talent"); } });
};

PAGES.talent = async () => {
  const d = DATA.talent = await API.call("po_leaders", { q: S.po.q, store: S.po.store });
  if (!d.has_data) return poEmpty();
  const tab = S.po.tab;
  const tabs = `<div class="seg">${[["leaders", "Leader 360°"], ["grid", "Talent grid"], ["bench", "Bench strength"], ["weights", "Index weights"]].map(([k, l]) => `<button data-act="po-tab" data-tab="${k}" aria-pressed="${tab === k}">${l}</button>`).join("")}</div>`;
  let body = "";
  if (tab === "leaders") {
    if (!S.po.leader || !d.leaders.some(l => l.key === S.po.leader)) S.po.leader = d.leaders.length ? d.leaders[0].key : null;
    body = `<div class="grid po-split">
      <div class="panel flush"><div class="row" style="padding:12px 12px 0;gap:8px"><input class="input" id="po-q" placeholder="Search leader or employee number" value="${esc(S.po.q)}" style="flex:1">
        <select class="input" data-act-change="po-store-filter" id="po-store"><option value="">All stores</option>${d.stores.map(s => `<option ${s === S.po.store ? "selected" : ""}>${esc(s)}</option>`).join("")}</select></div>
        <div class="tbl-wrap" style="max-height:calc(100vh - 300px)"><table class="t"><thead><tr><th>#</th><th>Leader</th><th>Leads</th><th class="n">Index</th><th class="n">Rating</th><th class="n">In role</th></tr></thead><tbody>
        ${d.leaders.map(l => `<tr class="click ${l.key === S.po.leader ? "po-sel" : ""}" data-act="po-leader" data-key="${esc(l.key)}"><td>${l.rank ?? "—"}</td><td><b>${esc(l.name)}</b><span class="sub">${esc(l.role || "Role not on file")}${l.system_role ? ` <span class="chip" title="Title in the HR system">system: ${esc(l.system_role)}</span>` : ""} · ${esc(l.store === "—" ? "Store not on file" : l.store)}</span></td>
          <td>${esc(l.leads)}</td><td class="n">${poIndex(l.score)}</td><td class="n">${l.rating == null ? "—" : l.rating}</td><td class="n">${esc(l.in_role)}</td></tr>`).join("") || `<tr><td colspan="6" class="empty">No leader matches.</td></tr>`}
        </tbody></table></div></div>
      <div class="panel po-profile" id="po-profile"><div class="loading"><span class="spin"></span>Loading…</div></div></div>`;
  } else if (tab === "grid") {
    body = `<div class="panel"><small style="color:var(--muted)">Appraisal rating (rows) against the business results of the area each leader runs (columns). Click a name for their 360°. Leaders need both a rating and section results to be placed.</small>
      <div class="po-grid">${d.talent.map(b => `<div class="po-box r${b.row}c${b.col}"><b>${esc(b.name)} <span class="chip">${b.leaders.length}</span></b>
        ${b.leaders.slice(0, 12).map(l => `<button class="po-name" data-act="po-leader" data-key="${esc(l.key)}">${esc(l.name)}<small>${esc(l.store || "")}</small></button>`).join("")}${b.leaders.length > 12 ? `<small>+${b.leaders.length - 12} more</small>` : ""}</div>`).join("")}</div>
      <div class="po-axis"><span>Results low</span><span>Results on plan</span><span>Results strong</span></div></div>`;
  } else if (tab === "bench") {
    body = `<div class="panel flush"><div class="tbl-wrap" style="max-height:calc(100vh - 260px)"><table class="t"><thead><tr><th>Priority</th><th>Leader</th><th>Store</th><th>Leads</th><th>Why flagged</th></tr></thead><tbody>
      ${d.bench.map(f => `<tr class="click" data-act="po-leader" data-key="${esc(f.key)}"><td><span class="chip ${f.severity === "High" ? "bad" : f.severity === "Medium" ? "warn" : ""}">${f.severity}</span></td><td><b>${esc(f.name)}</b><span class="sub">${esc(f.role || "")}</span></td><td>${esc(f.store)}</td><td>${esc(f.leads)}</td><td>${esc(f.reason)}</td></tr>`).join("") || `<tr><td colspan="5" class="empty">No roles flagged.</td></tr>`}
      </tbody></table></div></div>`;
  } else {
    const w = await API.call("po_weights", {});
    body = `<div class="panel" style="max-width:720px"><div class="phd"><h2>Leader index (out of 10)</h2></div>
      <small style="color:var(--muted)">How much each measure counts. Weights are relative. Each measure comes from the section(s) a leader runs and is scored 0–10; missing measures are left out, never counted as zero; a leader needs 3 measures to get an index.</small>
      ${Object.entries(w.labels).map(([k, l]) => `<label class="setting"><span><b>${esc(l)}</b><small>default ${w.defaults[k]}</small></span><input class="input" type="number" min="0" max="100" step="5" data-po-w="${k}" value="${w.weights[k]}" style="width:90px"></label>`).join("")}
      <div class="row" style="justify-content:flex-end"><button class="btn" data-act="po-w-reset">Reset</button><button class="btn primary" data-act="po-w-save">Save weights</button></div></div>`;
  }
  return `<div class="ph"><div><h1>Leaders &amp; talent</h1><p>${d.total} section leaders · ${d.scored} with a leader index · every leader joined to the results of the area they run</p></div>${tabs}</div>${body}`;
};
AFTER.talent = async () => {
  const q = $("#po-q");
  if (q) q.addEventListener("input", () => { clearTimeout(S.po.t); S.po.t = setTimeout(() => { S.po.q = q.value; render(); }, 280); });
  const sel = $("#po-store");
  if (sel) sel.addEventListener("change", () => { S.po.store = sel.value; render(); });
  const box = $("#po-profile");
  if (box && S.po.leader) {
    try { const r = await API.call("po_leader", { key: S.po.leader }); box.innerHTML = `<div class="po-html">${r.html}</div>`; }
    catch (e) { box.innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
  } else if (box) box.innerHTML = `<div class="empty">No leader selected.</div>`;
  if (q && document.activeElement !== q && S.po.q) { q.focus(); q.setSelectionRange(q.value.length, q.value.length); }
};

PAGES.retention = async () => {
  const d = DATA.retention = await API.call("po_turnover", {});
  if (!d.has_data) return poEmpty();
  const types = Object.fromEntries(d.by_type);
  const kpi = (l, v, s) => `<div class="kpi"><span class="kpi-l">${esc(l)}</span><span class="kpi-v">${v}</span><span class="kpi-s"><span>${esc(s)}</span></span></div>`;
  return `<div class="ph"><div><h1>Turnover &amp; retention</h1><p>${esc(d.window === "last 12 months" ? "Last 12 months to " + fmtDate(d.as_of) : d.window)} · by requested date</p></div></div>
    <div class="kpis po-kpis4">${kpi("Leavers · " + d.window, d.total, `${d.all_time} on file`)}${kpi("Voluntary", pct(d.voluntary_pct), `${types.Resignation || 0} resignations`)}
      ${kpi("Terminations", types.Termination || 0, `${types.Absconding || 0} absconded`)}${kpi("Top reason", `<span class="txt">${esc(d.by_reason.length ? d.by_reason[0][0] : "—")}</span>`, d.by_reason.length ? d.by_reason[0][1] + " leavers" : "")}</div>
    <div class="panel"><div class="phd"><h2>Leavers per month</h2><small>Last 24 months</small></div><div id="ch-po-monthly"></div></div>
    <div class="grid g2"><div class="panel"><div class="phd"><h2>Why people leave</h2><small>${esc(d.window)}</small></div><div id="ch-po-reasons"></div></div>
      <div class="panel"><div class="phd"><h2>Leavers by store</h2><small>${esc(d.window)}</small></div><div id="ch-po-stores"></div></div></div>
    <div class="grid g2"><div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Hotspots</h2><small>store × section</small></div><div class="tbl-wrap"><table class="t"><thead><tr><th>Store</th><th>Section</th><th class="n">Leavers</th></tr></thead>
      <tbody>${d.hotspots.map(([s, sec, n]) => `<tr><td><b>${esc(s)}</b></td><td>${esc(sec)}</td>${poCell(n, 3, 6, false, v => v)}</tr>`).join("")}</tbody></table></div></div>
      <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Most recent leavers</h2></div><div class="tbl-wrap" style="max-height:420px"><table class="t"><thead><tr><th>Date</th><th>Name</th><th>Store</th><th>Section</th><th>Type</th><th>Reason</th></tr></thead>
      <tbody>${d.recent.map(r => `<tr><td>${fmtDate(r.date)}</td><td><b>${esc(r.name)}</b></td><td>${esc(r.store)}</td><td>${esc(r.section)}</td><td>${esc(r.type)}</td><td>${esc(r.reason)}</td></tr>`).join("")}</tbody></table></div></div></div>
    <small style="color:var(--muted)">Many records carry salary period 2025-12 whatever their date; counts use the requested date. Confirm with HR operations which date is the official exit date.</small>`;
};
AFTER.retention = () => {
  const d = DATA.retention; if (!d || !d.has_data || !$("#ch-po-monthly")) return;
  const ml = d.monthly.map(([m]) => new Date(m + "-01T00:00:00").toLocaleDateString("en-GB", { month: "short", year: "2-digit" }));
  Charts.columns($("#ch-po-monthly"), { labels: ml, series: [{ name: "Leavers", values: d.monthly.map(([, n]) => n) }], height: 220 });
  Charts.hbar($("#ch-po-reasons"), { labels: d.by_reason.slice(0, 10).map(r => r[0]), values: d.by_reason.slice(0, 10).map(r => r[1]), name: "Leavers", fmt: "int" });
  Charts.hbar($("#ch-po-stores"), { labels: d.by_store.slice(0, 12).map(r => r[0]), values: d.by_store.slice(0, 12).map(r => r[1]), name: "Leavers", fmt: "int", colors: d.by_store.slice(0, 12).map(() => "var(--s2)") });
};

const PO_SHIFT = { Morning: ["M", "m"], Mid: ["Mid", "d"], Evening: ["E", "e"], Off: ["Off", "o"], Leave: ["AL", "l"], Inventory: ["Inv", "i"], "Not rostered": ["", "n"], Other: ["?", "n"] };
PAGES.shifts = async () => {
  const d = DATA.shifts = await API.call("po_shifts", { store: S.po.shiftStore });
  if (!d.has_data) return poEmpty();
  S.po.shiftStore = d.store;
  const mix = d.mix, worked = (mix.Morning || 0) + (mix.Mid || 0) + (mix.Evening || 0);
  const day = x => new Date(x + "T00:00:00");
  const gaps = d.gaps.filter(g => g.store === d.store);
  return `<div class="ph"><div><h1>Shift roster</h1><p>${d.people} leaders · ${fmtDate(d.days[0])} – ${fmtDate(d.days[d.days.length - 1])} · Morning till 11, Mid till 2, Evening after 2</p></div>
      <select class="input" id="po-shift-store">${d.stores.map(s => `<option ${s === d.store ? "selected" : ""}>${esc(s)}</option>`).join("")}</select></div>
    <div class="kpis po-kpis4"><div class="kpi"><span class="kpi-l">Morning share</span><span class="kpi-v">${pct(worked ? 100 * (mix.Morning || 0) / worked : null)}</span><span class="kpi-s"><span>of worked shifts</span></span></div>
      <div class="kpi"><span class="kpi-l">Mid share</span><span class="kpi-v">${pct(worked ? 100 * (mix.Mid || 0) / worked : null)}</span><span class="kpi-s"><span>of worked shifts</span></span></div>
      <div class="kpi"><span class="kpi-l">Evening share</span><span class="kpi-v">${pct(worked ? 100 * (mix.Evening || 0) / worked : null)}</span><span class="kpi-s"><span>of worked shifts</span></span></div>
      <div class="kpi"><span class="kpi-l">Coverage gaps</span><span class="kpi-v">${d.gaps.length}</span><span class="kpi-s"><span>department-days, all leaders off</span></span></div></div>
    <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>${esc(d.store)}</h2><small>${Object.entries(PO_SHIFT).filter(([k]) => !["Not rostered", "Other"].includes(k)).map(([k, [c, cl]]) => `<span class="po-s ${cl}">${c}</span> ${k}`).join(" &nbsp; ")}</small></div>
      <div class="tbl-wrap"><table class="t po-shifts"><thead><tr><th>Leader</th>${d.days.map(x => `<th class="n">${day(x).getDate()}<br><span class="sub">${day(x).toLocaleDateString("en-GB", { weekday: "short" }).slice(0, 2)}</span></th>`).join("")}</tr></thead>
      <tbody>${d.grid.map(p => `<tr><td><b>${esc(p.name)}</b><span class="sub">${esc(p.section)}</span></td>${p.days.map(s => { const [c, cl] = PO_SHIFT[s] || ["?", "n"]; return `<td class="po-s ${cl}">${c}</td>`; }).join("")}</tr>`).join("")}</tbody></table></div></div>
    <div class="grid g2"><div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Coverage gaps</h2><small>every rostered leader of a department off or on leave</small></div><div class="tbl-wrap" style="max-height:360px"><table class="t"><thead><tr><th>Store</th><th>Department</th><th>Date</th><th class="n">Leaders</th></tr></thead>
      <tbody>${d.gaps.map(g => `<tr><td><b>${esc(g.store)}</b></td><td>${esc(g.department)}</td><td>${fmtDate(g.date)}</td><td class="n">${g.leaders}</td></tr>`).join("") || `<tr><td colspan="4" class="empty">No gaps.</td></tr>`}</tbody></table></div></div>
      <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Leave this month</h2></div><div class="tbl-wrap" style="max-height:360px"><table class="t"><thead><tr><th>Leader</th><th>Store</th><th class="n">Days</th></tr></thead>
      <tbody>${d.leave.map(l => `<tr><td><b>${esc(l.name)}</b></td><td>${esc(l.store)}</td>${poCell(l.days, 3, 6, false, v => v)}</tr>`).join("")}</tbody></table></div></div></div>`;
};
AFTER.shifts = () => { const s = $("#po-shift-store"); if (s) s.addEventListener("change", () => { S.po.shiftStore = s.value; render(); }); };

Object.assign(ACT, {
  "po-metric": b => { S.po.metric = b.dataset.metric; render(); },
  "po-tab": b => { S.po.tab = b.dataset.tab; render(); },
  "po-leader": b => { S.po.leader = b.dataset.key; if (S.po.tab !== "leaders" || S.page !== "talent") { S.po = { ...S.po, tab: "leaders", q: "", store: "" }; go("talent"); } else render(); },
  "po-store": b => { S.po = { ...S.po, store: b.dataset.store, q: "", tab: "leaders", leader: null }; go("talent"); },
  "po-w-save": async () => { const w = {}; $$("[data-po-w]").forEach(i => { w[i.dataset.poW] = +i.value; }); await call("po_weights", { weights: w }); toast("Index weights saved"); render(); },
  "po-w-reset": async () => { await call("po_weights", { reset: true }); toast("Index weights reset"); render(); },
});

/* ---------------------------------------------------------------- Data explorer: any other table, charted and explained */
S.dx = { id: null, group: null, measure: null, agg: null, q: "" };
const dxNum = (v, type) => v == null ? "—" : type === "percent" ? (+v).toFixed(1) + "%" : Math.abs(v) >= 1e9 ? (v / 1e9).toFixed(2) + " bn" : Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(1) + " M" : (+v).toLocaleString("en-US", { maximumFractionDigits: 2 });
PAGES.data = async () => {
  const list = (await API.call("datasets", {})).datasets;
  if (!list.length) return `<div class="ph"><div><h1>Other data</h1><p>Any table P&O does not already know lands here, charted and explained.</p></div></div>
    <div class="panel"><div class="hero"><div class="logo" style="width:64px;height:64px;font-size:20px;border-radius:18px">DATA</div><h2>No other data yet</h2>
    <p>Import or paste any table (a KPI sheet, a training list, a survey, a store checklist…). P&O finds the header, understands the columns
    (stores, sections, people, actual, budget, dates) and shows charts and insights here. Known reports still go to their own screens.</p>
    <div class="row" style="justify-content:center"><button class="btn primary" data-go="import">${ic("import", 16)}Import or paste data</button></div></div></div>`;
  if (!S.dx.id || !list.some(d => d.id === S.dx.id)) S.dx = { id: list[0].id, group: null, measure: null, agg: null, q: "" };
  const v = DATA.data = await API.call("dataset", { import_id: S.dx.id, group: S.dx.group, measure: S.dx.measure, agg: S.dx.agg });
  const groups = v.columns.filter(c => c.type === "text");
  const measures = v.columns.filter(c => c.type === "number" || c.type === "percent");
  const opt = (val, label, cur) => `<option value="${esc(val)}" ${val === cur ? "selected" : ""}>${esc(label)}</option>`;
  const cols = v.columns.filter(c => !c.name.startsWith("_"));
  const kpis = [`<div class="kpi"><span class="kpi-l">Rows</span><span class="kpi-v">${v.rows.toLocaleString("en-US")}</span><span class="kpi-s"><span>${v.columns.length} columns</span></span></div>`]
    .concat(v.totals.slice(0, 4).map(t => `<div class="kpi"><span class="kpi-l">${esc(t.name)}</span><span class="kpi-v">${dxNum(t.value, t.type)}</span><span class="kpi-s"><span>${t.agg === "avg" ? "average" : "total"}</span></span></div>`)).join("");
  return `<div class="ph"><div><h1>${esc(v.title)}${v.period ? ` <span class="chip ${/^YTD/.test(v.period) ? "gold" : /^MTD/.test(v.period) ? "info" : ""}" style="vertical-align:middle;font-size:12px">${esc(v.period === "General" ? "General · every period" : v.period)}</span>` : ""}</h1><p>${esc(v.description || "From " + (v.file || "imported data"))} · ${v.rows.toLocaleString("en-US")} rows</p></div>
      <select class="input" id="dx-pick">${list.map(d => opt(String(d.id), (d.ai_title || d.title) + (d.period ? " · " + d.period : "") + " · " + d.rows + " rows", String(S.dx.id))).join("")}</select></div>
    <div class="kpis po-kpis4 dx-kpis">${kpis}</div>
    <div class="panel"><div class="phd"><h2>Explore</h2><div class="row" style="gap:8px">
        <label class="dx-l">Group by<select class="input" id="dx-group">${opt("", "Nothing (all rows)", v.group || "")}${groups.map(c => opt(c.name, c.label, v.group)).join("")}</select></label>
        <label class="dx-l">Measure<select class="input" id="dx-measure">${opt("__count", "Number of rows", v.measure || "__count")}${measures.map(c => opt(c.name, c.label, v.measure)).join("")}</select></label>
        <label class="dx-l">As<select class="input" id="dx-agg">${[["sum", "Total"], ["avg", "Average"], ["max", "Highest"], ["min", "Lowest"], ["count", "Count"]].map(([k, l]) => opt(k, l, v.agg)).join("")}</select></label></div></div>
      <div id="ch-dx"></div>${v.series_count > 40 ? `<small style="color:var(--muted)">Showing the top 40 of ${v.series_count}.</small>` : ""}</div>
    ${v.trend.length >= 2 ? `<div class="panel"><div class="phd"><h2>Over time</h2><small>${esc(v.date)}</small></div><div id="ch-dx-t"></div></div>` : ""}
    <div class="grid g2">
      <div class="panel"><div class="phd"><h2>Insights</h2><small>calculated from the data</small></div><div class="dx-ins">${v.insights.map(i => `<p>${md(i)}</p>`).join("")}</div></div>
      <div class="panel"><div class="phd"><h2>AI analyst</h2><button class="btn sm primary" data-act="dx-ai">${ic("spark", 14)}Analyse with AI</button></div>
        <div id="dx-ai" class="dx-ins">${v.ai_insights ? md(v.ai_insights) : `<p style="color:var(--muted)">The AI reads the summaries above (not the raw file) and writes what a P&amp;O director should act on. Uses the AI chosen in Settings → AI (Groq, Gemini, OpenRouter or offline).</p>`}</div></div>
    </div>
    <div class="panel flush"><div class="row" style="padding:12px 14px 0;justify-content:space-between"><h2 style="margin:0">Data</h2><input class="input" id="dx-q" placeholder="Filter rows" value="${esc(S.dx.q)}" style="width:260px"></div>
      <div class="tbl-wrap" style="max-height:520px"><table class="t" id="dx-table"><thead><tr>${cols.map(c => `<th class="${c.type === "number" || c.type === "percent" ? "n" : ""}">${esc(c.name)}${c.role ? `<span class="sub">${esc(c.role.replace("_", " "))}</span>` : ""}</th>`).join("")}</tr></thead>
      <tbody>${v.table.slice(0, 500).map(r => `<tr>${cols.map(c => `<td class="${c.type === "number" || c.type === "percent" ? "n" : ""}">${c.type === "number" || c.type === "percent" ? dxNum(r[c.name], c.type) : esc(r[c.name] ?? "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div></div>
    ${v.warnings.length ? `<small style="color:var(--muted)">${v.warnings.map(esc).join(" · ")}</small>` : ""}`;
};
AFTER.data = () => {
  const v = DATA.data; if (!v || !$("#ch-dx")) return;
  const mcol = v.columns.find(c => c.name === v.measure);
  const fmt = mcol && mcol.type === "percent" ? "pct" : "num";
  const s = v.series.slice(0, 25);
  if (s.length) Charts.hbar($("#ch-dx"), { labels: s.map(x => x[0]), values: s.map(x => x[1]), name: v.measure || "Rows", fmt });
  if ($("#ch-dx-t")) Charts.line($("#ch-dx-t"), { labels: v.trend.map(x => x[0]), series: [{ name: v.measure || "Rows", values: v.trend.map(x => x[1]) }], height: 220, area: true, fmt });
  const on = (id, f) => { const el = $(id); if (el) el.addEventListener("change", f); };
  on("#dx-pick", e => { S.dx = { id: +e.target.value, group: null, measure: null, agg: null, q: "" }; render(); });
  on("#dx-group", e => { S.dx.group = e.target.value || "__none"; render(); });
  on("#dx-measure", e => { S.dx.measure = e.target.value; S.dx.agg = null; render(); });
  on("#dx-agg", e => { S.dx.agg = e.target.value; render(); });
  const q = $("#dx-q");
  if (q) {
    const apply = () => { const t = q.value.toLowerCase(); S.dx.q = q.value; $$("#dx-table tbody tr").forEach(tr => { tr.style.display = !t || tr.textContent.toLowerCase().includes(t) ? "" : "none"; }); };
    q.addEventListener("input", apply); apply();
  }
};
ACT["dx-ai"] = async b => {
  b.disabled = true; const box = $("#dx-ai"); box.innerHTML = `<div class="loading"><span class="spin"></span>The AI is reading the summaries…</div>`;
  try {
    const r = await call("dataset_ai", { import_id: S.dx.id });
    box.innerHTML = r.text ? md(r.text) + `<small style="color:var(--muted)">${esc({ groq: "Groq", gemini: "Gemini", openrouter: "OpenRouter", offline: "Offline AI" }[r.engine] || "")}</small>` : `<p style="color:var(--muted)">${esc(r.note || "")}</p>`;
  } catch (e) { box.innerHTML = ""; } finally { b.disabled = false; }
};

/* ---------------------------------------------------------------- Customer NPS */
S.nps = { city: "" };
const npsTone = v => v == null ? "none" : v >= 50 ? "good" : v >= 20 ? "warn" : "bad";
const npsTxt = v => v == null ? "—" : (v > 0 ? "+" : "") + Math.round(v);
PAGES.nps = async () => {
  const d = DATA.nps = await API.call("po_nps", { city: S.nps.city });
  if (!d.has_data) return `<div class="panel"><div class="hero"><h2>No NPS data yet</h2><p>Import the NPS sheet (Details · Section · Product Influence · NPS). It is recognised automatically.</p>
    <div class="row" style="justify-content:center"><button class="btn primary" data-go="import">${ic("import", 16)}Import data</button></div></div></div>`;
  const kpi = (l, v, s, cls = "") => `<div class="kpi"><span class="kpi-l">${esc(l)}</span><span class="kpi-v ${cls}">${v}</span><span class="kpi-s"><span>${s}</span></span></div>`;
  const delta = d.overall != null && d.overall_prev != null ? d.overall - d.overall_prev : null;
  const list = (items, key) => items.length ? items.map(c => `<div class="nps-row"><span>${esc(c.category)}<small>${esc(c.section)}</small></span><b class="t-${npsTone(c.nps)}">${key === "change" ? npsTxt(c.change) : npsTxt(c.nps)}</b></div>`).join("") : `<div class="empty">—</div>`;
  return `<div class="ph"><div><h1>Customer NPS</h1><p>Net Promoter Score by city, section and product · ${d.latest}${d.prev ? ` vs ${d.prev}` : ""} · −100 to +100</p></div>
      <div class="seg"><button data-act="nps-city" data-city="" aria-pressed="${!d.city}">All cities</button>${d.cities.map(c => `<button data-act="nps-city" data-city="${esc(c)}" aria-pressed="${d.city === c}">${esc(c)}</button>`).join("")}</div></div>
    <div class="kpis po-kpis4">${kpi(`NPS ${d.latest}`, npsTxt(d.overall), d.city || "All cities", "t-" + npsTone(d.overall))}
      ${kpi("Change vs last year", delta == null ? "—" : npsTxt(delta), d.prev ? `vs ${d.prev}: ${npsTxt(d.overall_prev)}` : "one year only")}
      ${kpi("Best category", d.best.length ? esc(d.best[0].category) : "—", d.best.length ? npsTxt(d.best[0].nps) : "", "txt")}
      ${kpi("Needs work", d.worst.length ? `<span class="clamp3" title="${esc(d.worst[0].category)}">${esc(d.worst[0].category)}</span>` : "—", d.worst.length ? npsTxt(d.worst[0].nps) : "", "txt")}</div>
    <div class="panel"><div class="phd"><h2>What it says</h2></div><div class="dx-ins">${d.insights.map(i => `<p>${md(i)}</p>`).join("")}</div></div>
    <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>City × section · ${d.latest}</h2><small>green ≥ +50 · amber +20 to +49 · red below +20 · small number = change vs ${d.prev || "last year"}</small></div>
      <div class="tbl-wrap"><table class="t po-heat"><thead><tr><th>City</th>${d.sections.map(s => `<th class="n">${esc(s.replace("Fruits & Vegetables", "F&V").replace("Light Household", "LHH").replace("Heavy Household", "HHH"))}</th>`).join("")}</tr></thead>
      <tbody>${d.cities.map((c, i) => `<tr><td><b>${esc(c)}</b></td>${d.matrix[i].map((v, j) => `<td class="n po-h ${npsTone(v)}">${npsTxt(v)}${d.change[i][j] != null ? `<span class="sub">${npsTxt(d.change[i][j])}</span>` : ""}</td>`).join("")}</tr>`).join("")}</tbody></table></div></div>
    <div class="grid g2"><div class="panel"><div class="phd"><h2>Every category · ${d.latest}</h2></div><div id="ch-nps"></div></div>
      <div class="panel"><div class="phd"><h2>Moved most since ${d.prev || "last year"}</h2></div><div class="grid g2" style="gap:12px">
        <div><small class="nps-h">Biggest gains</small>${list(d.gains, "change")}</div><div><small class="nps-h">Biggest drops</small>${list(d.drops, "change")}</div></div></div></div>`;
};
AFTER.nps = () => {
  const d = DATA.nps; if (!d || !d.has_data || !$("#ch-nps")) return;
  const c = d.categories.filter(x => x.nps != null).sort((a, b) => b.nps - a.nps);
  Charts.hbar($("#ch-nps"), { labels: c.map(x => x.category.replace(/\s*\(.*\)$/, "")), values: c.map(x => x.nps), name: "NPS", fmt: "int",
    colors: c.map(x => `var(--${x.nps >= 50 ? "good" : x.nps >= 20 ? "warn" : "bad"})`) });
};
ACT["nps-city"] = b => { S.nps.city = b.dataset.city; render(); };

Object.assign(ACT, CHAT_ACTS);
document.addEventListener("click", e => {
  if (!e.target.closest(".menu-wrap")) document.querySelectorAll(".cmenu:not([hidden])").forEach(m => { m.hidden = true; });
  const g = e.target.closest("[data-go]");
  if (g && !e.target.closest("[data-act]")) { if (g.dataset.tab) S.setTab = g.dataset.tab; closeSheet(); return go(g.dataset.go); }
  const a = e.target.closest("[data-act]");
  if (a && ACT[a.dataset.act]) {
    e.preventDefault();
    // an action that fails has already told the user (toast); keep it from surfacing as a screen error
    return Promise.resolve().then(() => ACT[a.dataset.act](a, e)).catch(err => { if (!err || !err.shown) fail(err); });
  }
  const p = e.target.closest("[data-person]");
  if (p && !e.target.closest("input")) { e.preventDefault(); openPerson(p.dataset.person); }
});
document.addEventListener("keydown", e => {
  if (e.altKey && e.key === "ArrowLeft") { e.preventDefault(); ACT.back(); return; }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); const q = $("#q"); if (q) q.focus(); }
  if (e.key === "Escape") { if ($(".modal")) closeModal(); else if ($(".sheet")) closeSheet(); else if (document.body.classList.contains("present")) document.body.classList.remove("present"); }
  if (document.body.classList.contains("present") && ["ArrowDown", "PageDown", "ArrowRight", " "].includes(e.key)) { e.preventDefault(); presentStep(1); }
  if (document.body.classList.contains("present") && ["ArrowUp", "PageUp", "ArrowLeft"].includes(e.key)) { e.preventDefault(); presentStep(-1); }
});
window.addEventListener("resize", () => { clearTimeout(S.rz); S.rz = setTimeout(() => { const f = AFTER[S.page]; if (f && !["ask", "import", "settings", "people", "org"].includes(S.page)) f(); }, 200); });
document.addEventListener("dragover", e => e.preventDefault());
window.addEventListener("mouseup", e => { if (e.button === 3) { e.preventDefault(); ACT.back(); } });
document.addEventListener("drop", e => { e.preventDefault(); if (!window.qt && e.dataTransfer && e.dataTransfer.files.length && !e.target.closest("#drop")) { if (S.page !== "import") go("import"); uploadFiles(e.dataTransfer.files); } });

function applyTheme(t) { if (t === "light" || t === "dark") document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme; }

async function boot(keepPage) {
  if (!keepPage || !S.init) S.init = await API.call("init");
  applyTheme(S.init.theme);
  S.months = S.init.months;
  S.month = S.init.month;
  if (!keepPage) S.page = store.get("page", "home");
  if (!S.init.has_data && !keepPage) S.page = "home";
  shell();
  await refreshOptions();
  render();
  if (S.init.notice) toast(S.init.notice, { ms: 15000 });
  window.PNO_ready = true;
}
boot(false).catch(e => { $("#app").innerHTML = `<div class="errbox" style="margin:40px">P&O could not start: ${esc(e.message || e)}</div>`; });
})();
