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
  const CHANGE = /(^|_)(add|make|open|advance|delete|commit|save|set|update|create|undo|remove|apply|import|close|restore|build|assign|move|lock|clear|rename|merge|pin)(_|$)/;
  const inflight = new Map();
  async function call(method, params = {}) {
    if (CHANGE.test(method) && !params._idem && !/^(import|hire_add|hire_upload|policy_add|survey_add|agent)/.test(method)) {
      const key = method + JSON.stringify(params);          // the same change sent twice while the first is running: one request
      if (inflight.has(key)) return inflight.get(key);
      const p = raw(method, { ...params, _idem: method + "-" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8) });
      inflight.set(key, p); p.finally(() => inflight.delete(key)).catch(() => {});
      return p;
    }
    return raw(method, params);
  }
  async function raw(method, params) {
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
  hiring: '<rect x="3" y="7" width="18" height="13" rx="2.5"/><path d="M8.5 7V5.5A2 2 0 0 1 10.5 3.5h3a2 2 0 0 1 2 2V7M3 12.5h18M10.5 12.5v1.5h3v-1.5"/>',
  learning: '<path d="M2.5 8.5 12 4l9.5 4.5L12 13z"/><path d="M6 10.5V16c0 1.4 2.7 3 6 3s6-1.6 6-3v-5.5M21.5 8.5v6"/>',
  manpower: '<circle cx="8" cy="7" r="3"/><circle cx="17" cy="9" r="2.4"/><path d="M2.5 20c.5-3.6 2.8-5.6 5.5-5.6s5 2 5.5 5.6M14.5 15c2.6-.4 5.6 1 6.5 4.5"/><path d="M19 3v3M17.5 4.5h3"/>',
  engagement: '<path d="M12 20.5s-7.5-4.4-7.5-10A4.3 4.3 0 0 1 12 7.6a4.3 4.3 0 0 1 7.5 2.9c0 5.6-7.5 10-7.5 10z"/><path d="M8 12h2l1.2-2 1.6 4 1.2-2h2"/>',
  recognition: '<circle cx="12" cy="9" r="5.5"/><path d="M8.5 13.3 7 21l5-2.6 5 2.6-1.5-7.7"/>',
  calendar: '<rect x="3" y="4.5" width="18" height="16" rx="2.5"/><path d="M3 9.5h18M8 2.5v4M16 2.5v4M7.5 13.5h2M11 13.5h2M14.5 13.5h2M7.5 17h2M11 17h2"/>',
  brief: '<path d="M6 3h9l4 4v14H6z"/><path d="M14.5 3v4.5H19M9 12h7M9 15.5h7M9 9h3"/>',
  insights: '<path d="M3 3v18h18"/><path d="M7 15l4-4 3 3 5-6"/><circle cx="19" cy="8" r="1.5"/>',
  relations: '<path d="M12 3v18M5 7h14M5 7l-2.5 6a3 3 0 0 0 5 0zM19 7l-2.5 6a3 3 0 0 0 5 0zM8 21h8"/>',
  brain: '<circle cx="6" cy="7" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="12" cy="17" r="2.8"/><circle cx="19" cy="15" r="1.8"/><path d="M8.3 8.2 10.6 15M15.7 7.2 13 14.5M8.4 7.3l7.2-1M14.7 16.4l2.6-.9"/>',
  forecast: '<path d="M3.5 19.5h17M5 15l4-4 3.5 3 6.5-7"/><path d="M15 7h4v4"/>',
  goals: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.2"/>',
  notes: '<path d="M5 4h10l4 4v12H5z"/><path d="M15 4v4h4M8.5 12h7M8.5 15.5h5"/>',
  policies: '<path d="M12 3l7.5 3v5.5c0 4.6-3.2 8.2-7.5 9.5-4.3-1.3-7.5-4.9-7.5-9.5V6z"/><path d="M8.8 12l2.2 2.2 4.2-4.4"/>',
  organisation: '<rect x="9" y="2.5" width="6" height="5" rx="1.2"/><rect x="2.5" y="16.5" width="6" height="5" rx="1.2"/><rect x="15.5" y="16.5" width="6" height="5" rx="1.2"/><path d="M12 7.5V12M5.5 16.5V12h13v4.5"/>',
  actions: '<rect x="4" y="3.5" width="16" height="17" rx="2.5"/><path d="m8 9 1.8 1.8L13 7.6M8 15.5l1.8 1.8 3.2-3.2M15.5 9.5H17M15.5 16H17"/>',
  health: '<path d="M12 3 4.5 6v5.5c0 4.6 3.2 8.3 7.5 9.5 4.3-1.2 7.5-4.9 7.5-9.5V6z"/><path d="m8.5 12 2.5 2.5 4.5-5"/>',
  spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8"/>',
};
const ic = (n, s = 19) => `<svg viewBox="0 0 24 24" width="${s}" height="${s}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICON[n] || ""}</svg>`;
const NAV_FULL = [["home", "Overview", "home"], ["review", "Business review", "review"], ["stores", "Stores", "stores"],
  ["people", "People", "people"], ["brain", "People Brain", "brain"], ["talent", "Leaders & talent", "talent"], ["attendance", "Attendance", "att"],
  ["insights", "People insights", "insights"], ["retention", "Turnover", "retention"], ["nps", "Customer NPS", "nps"], ["shifts", "Shift roster", "shifts"], ["data", "Other data", "data"],
  ["hiring", "Hiring", "hiring"], ["learning", "Learning Studio", "learning"], ["manpower", "Manpower", "manpower"], ["forecast", "Workforce plan", "forecast"], ["organisation", "Organisation", "organisation"], ["goals", "Goals", "goals"], ["notes", "1:1s & visits", "notes"], ["relations", "Employee relations", "relations"], ["calendar", "HR calendar", "calendar"], ["brief", "Weekly brief", "brief"], ["engagement", "Engagement", "engagement"], ["recognition", "Recognition", "recognition"], ["ask", "Ask P&O AI", "ask"], ["policies", "Policy assistant", "policies"], ["actions", "Actions", "actions"], ["import", "Import data", "import"], ["health", "Data health", "health"], ["settings", "Settings", "settings"]];
const NAV_SIMPLE = [["rv", "Review", "review"], ["ask", "Ask P&O AI", "ask"], ["import", "Data", "import"]];
const DATA_PAGES = ["import", "health", "brain"];
const dataTabs = page => `<div class="seg datatabs">${[["import", "Import & history"], ["health", "Data health"], ["brain", "People records & corrections"]].map(([k, l]) => `<button data-go="${k}" aria-pressed="${page === k}">${l}</button>`).join("")}</div>`;
let NAV = NAV_SIMPLE;
let ALLOWED = new Set(["rv", "ask", "settings", "import", "health", "brain"]);
// the full toolkit (every 2.x/3.x module) stays in the app, switched off; Settings → Appearance turns it on
function applyMode() {
  const full = !!(S.init && S.init.full_mode);
  NAV = full ? [["rv", "Review", "review"]].concat(NAV_FULL) : NAV_SIMPLE;
  NAV_GROUP = full ? NAV_GROUP_FULL : {};
  ALLOWED = full ? null : new Set(["rv", "ask", "settings", ...DATA_PAGES]);
}
let NAV_GROUP = {};
const NAV_GROUP_FULL = { insights: "Insights", hiring: "Talent", ask: "Tools" };
const FILTER_PAGES = new Set(["home", "people", "performance", "stores", "store", "attendance", "org"]);
const PAGE_TITLE = { home: "Overview", review: "Business review", stores: "Stores", store: "Store", people: "People", performance: "Performance",
  talent: "Leaders & talent", attendance: "Attendance", org: "Org chart", retention: "Turnover", nps: "Customer NPS", shifts: "Shift roster",
  rv: "Review", data: "Other data", ask: "Ask P&O AI", import: "Import data", health: "Data health", hiring: "Hiring", learning: "Learning Studio", manpower: "Manpower", actions: "Action tracker", organisation: "Organisation", forecast: "Workforce plan", brain: "People Brain", relations: "Employee relations", insights: "People insights", calendar: "HR calendar", brief: "Weekly brief", goals: "Goals", notes: "1:1s & visits", engagement: "Engagement", recognition: "Recognition", policies: "Policy assistant", settings: "Settings" };
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
      `<button data-go="${k}" ${KEY_OF[k] ? `title="${esc(l)}  ·  G then ${KEY_OF[k].toUpperCase()}"` : ""} ${S.page === k || (S.page === "store" && k === "stores") ? 'aria-current="page"' : ""}>${ic(i)}<span>${l}</span>${k === "settings" && S.init && S.init.unsure_stores ? `<span class="badge">${S.init.unsure_stores}</span>` : ""}</button>`).join("")}</nav>
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
  if (S.init && S.init.full_mode && !["rv", "ask", "settings"].includes(S.page)) return topbarFull();
  const back = S.page === "settings" ? `<button class="btn back" data-go="rv">${ic("back", 16)}Review</button>` : "";
  $("#top").innerHTML = `<div class="top-row">${back}<div class="crumbs"><span class="ptitle">${esc(PAGE_TITLE[S.page] || "")}</span></div><div class="spacer"></div>
    <button class="btn hide-present" data-act="rv-update">${ic("import", 16)}Update data</button>
    ${S.page === "rv" ? `<button class="btn gold hide-present" data-act="present">${ic("play", 14)}Present</button>` : ""}
    <button class="btn ghost hide-present" data-act="rv-settings" title="Settings">⚙</button></div>`;
}
function topbarFull() {
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
      <div class="search hide-present">${ic("search", 16)}<input id="q" placeholder="Search people, stores or commands" autocomplete="off"><kbd>Ctrl K</kbd><div id="sugg"></div></div>
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
      if (!v) return close();
      const lv = v.replace(/^>\s*/, "").toLowerCase();
      const cmds = COMMANDS().filter(c => !lv || c.a.toLowerCase().includes(lv) || c.b.toLowerCase().includes(lv)).slice(0, v.startsWith(">") ? 20 : 5);
      let r = { people: [], stores: [] };
      if (v.length >= 2 && !v.startsWith(">")) { try { r = await API.call("search", { q: v, month: S.month }); } catch (e) { /* commands still shown */ } }
      items = [...cmds, ...r.people.map(p => ({ k: "p", id: p.emp, a: p.name, b: p.sub })), ...r.stores.map(s => ({ k: "s", id: s.store_id, a: s.name, b: s.sub }))];
      box.innerHTML = items.length ? `<div class="sugg">${items.map((x, i) => (i === 0 || items[i - 1].k !== x.k ? `<div class="sh">${{ c: "Go to and do", p: "People", s: "Stores" }[x.k]}</div>` : "") +
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
  const pick = x => { close(); q.value = ""; q.blur(); if (!x) return; if (x.k === "c") x.run(); else if (x.k === "p") openPerson(x.id); else go("store", x.id); };
}


/* ---------------------------------------------------------------- polish: counting numbers, export on every table */
function countUp(root) {
  return;                                   // 3.0.1: numbers appear at once (animation cost too much on office PCs)
  if (matchMedia("(prefers-reduced-motion: reduce)").matches || document.body.classList.contains("present")) return;
  $$(".kpi-v", root).forEach(el => {
    const node = [...el.childNodes].find(n => n.nodeType === 3 && /\d/.test(n.textContent));
    if (!node || el.dataset.counted) return;
    const m = node.textContent.match(/^([^\d−-]*)([−-]?[\d,]*\.?\d+)(.*)$/s);
    if (!m) return;
    const target = parseFloat(m[2].replace(/,/g, "").replace("−", "-")), dec = (m[2].split(".")[1] || "").length, comma = m[2].includes(",");
    if (!isFinite(target) || Math.abs(target) < 2) return;
    el.dataset.counted = 1;
    const t0 = performance.now(), dur = 750;
    const step = now => { const k = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - k, 3), v = target * e;
      node.textContent = m[1] + (comma ? v.toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec }) : v.toFixed(dec)) + m[3];
      if (k < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  });
}
function decorateTables(root) {
  $$(".panel", root).forEach(p => {
    const t = p.querySelector("table.t");
    if (!t || p.querySelector(":scope > .tx, :scope .phd .tx") || p.closest(".modal, .hdraw, .pcov-box")) return;
    const b = document.createElement("button");
    b.className = "tx"; b.title = "Export this table"; b.dataset.act = "tbl-export";
    b.innerHTML = ic("export", 14);
    const hd = p.querySelector(":scope > .phd, :scope > .row");
    if (hd) hd.append(b); else { p.style.position = "relative"; b.classList.add("abs"); p.prepend(b); }
  });
}
function polish(root) { try { countUp(root); decorateTables(root); explainKpis(root); } catch (e) { /* cosmetic only */ } }
function tableData(t) {
  const head = $$("thead th", t).map(th => th.innerText.replace(/\s+/g, " ").trim());
  const rows = $$("tbody tr", t).filter(tr => !(tr.children.length === 1 && tr.querySelector(".empty"))).map(tr => $$("td", tr).map(td => {
    const sel = td.querySelector("select"), inp = td.querySelector("input:not([type=checkbox])");
    if (sel) return sel.options[sel.selectedIndex] ? sel.options[sel.selectedIndex].text : "";
    if (inp) return inp.value;
    return td.innerText.replace(/\s*\n\s*/g, " · ").replace(/\s+/g, " ").trim();
  }));
  const keep = head.map((h, i) => h || rows.some(r => (r[i] || "").trim())).map((k, i) => k ? i : -1).filter(i => i >= 0);
  return { columns: keep.map(i => head[i] || " "), rows: rows.map(r => keep.map(i => r[i] || "")) };
}
const POLISH_ACTS = {};
POLISH_ACTS["tbl-export"] = b => {
  const p = b.closest(".panel"), t = p.querySelector("table.t");
  const title = (p.querySelector("h2") || {}).innerText || ($(".ph h1") || {}).innerText || "Table";
  const m = modal(`<h3>Export table</h3><p style="color:var(--muted);margin:0 0 12px"><b>${esc(title)}</b> · ${$$("tbody tr", t).length} rows, as on screen</p>
    <div class="row" style="gap:8px">${[["xlsx", "Excel", "sort and filter"], ["pdf", "PDF", "to print or send"], ["docx", "Word", "to edit"]].map(([f, l, d]) => `<button class="btn txf" data-f="${f}"><b>${l}</b><small style="display:block;color:var(--muted);font-weight:500">${d}</small></button>`).join("")}</div>`);
  $$(".txf", m).forEach(x => x.onclick = async () => { closeModal();
    const d = tableData(t); const r = await call("export_table", { title, columns: d.columns, rows: d.rows, fmt: x.dataset.f, scope: ($(".ph p") || {}).innerText || "" });
    if (!r.cancelled) toast(`Saved ${r.name}`, { action: "Open", onAction: () => API.call("open_path", { path: r.path }), ms: 7000 }); });
};

/* ---------------------------------------------------------------- command palette (Ctrl+K): pages and actions as well as people and stores */
const COMMANDS = () => [
  ...NAV.map(([k, l]) => ({ k: "c", a: "Go to " + l, b: "Screen", run: () => go(k) })),
  { k: "c", a: "New vacancy", b: "Hiring", run: () => { S.hire.tab = "vac"; S.hire.vid = null; go("hiring"); setTimeout(() => ACT["h-new"](), 400); } },
  { k: "c", a: "New course", b: "Learning Studio", run: () => { S.learn.cid = null; go("learning"); setTimeout(() => ACT["l-new"](), 500); } },
  { k: "c", a: "Export a report pack", b: "PDF, Word, PowerPoint or Excel", run: () => openExport() },
  { k: "c", a: "Import files", b: "Import data", run: () => go("import") },
  { k: "c", a: "Check data health", b: "Is the month ready?", run: () => go("health") },
  { k: "c", a: "Ask P&O AI", b: "Chat", run: () => go("ask") },
  { k: "c", a: "Switch light / dark theme", b: "Appearance", run: () => { const d = document.documentElement.dataset.theme === "dark"; applyTheme(d ? "light" : "dark"); API.call("settings_save", { theme: d ? "light" : "dark" }).catch(() => {}); } },
];

/* ---------------------------------------------------------------- routing */
function go(page, arg = null, opts = {}) {
  if (ALLOWED && !ALLOWED.has(page)) page = "rv";
  if (!opts.back && S.page && (S.page !== page || S.arg !== arg)) { S.hist = (S.hist || []).concat([[S.page, S.arg]]).slice(-30); }
  S.page = page; S.arg = arg;
  topbar();
  $$("#nav button").forEach(b => b.toggleAttribute("aria-current", b.dataset.go === (page === "store" ? "stores" : (DATA_PAGES.includes(page) && !(S.init && S.init.full_mode)) ? "import" : page)));
  $$("#nav button[aria-current]").forEach(b => b.setAttribute("aria-current", "page"));
  store.set("page", page === "store" ? "stores" : page);
  render();
}
window.go = go;

const PERIOD_PAGES = ["review", "talent", "retention", "shifts", "nps", "rv"];
async function render() {
  const view = $("#view");
  if (!view) return;
  const token = ++S.busy;
  const page = S.page, arg = S.arg;
  const cur = view.firstElementChild;
  const same = cur && cur.dataset.page === page && S.shownArg === arg;   // a refresh of the screen already shown
  // keep what is on screen while the data loads; only a slow load shows a spinner (no blank flash)
  const snapKey = `${page}|${arg ?? ""}|${S.month}|${JSON.stringify(S.scope || {})}`;
  flushDeletes();
  if (cur) cur.classList.add("stale");
  const slow = setTimeout(() => { if (token === S.busy && !same) view.innerHTML = `<div class="page"><div class="skel"><div class="sk sk-h"></div><div class="sk sk-p"></div><div class="sk-row">${"<div class='sk sk-k'></div>".repeat(5)}</div><div class="sk-row"><div class="sk sk-c"></div><div class="sk sk-c sm"></div></div></div></div>`; }, 260);
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
    if (DATA_PAGES.includes(page) && !(S.init && S.init.full_mode)) html = dataTabs(page) + html;
    view.innerHTML = `<div class="page" data-page="${page}" data-snap="${esc(snapKey)}">${html}</div>`;
    if (pd && pd.period) {
      const pg = view.firstElementChild, ph = pg.querySelector(":scope > .ph");
      if (ph) ph.insertAdjacentHTML("afterend", periodBar(pd.period)); else pg.insertAdjacentHTML("afterbegin", periodBar(pd.period));
    }
    if (!same) view.scrollTop = 0;
    S.shownArg = arg;
    const after = AFTER[page]; if (after) Promise.resolve(after()).then(() => polish(view)); else polish(view);
  } catch (e) {
    if (token !== S.busy) return;
    view.innerHTML = `<div class="page" data-page="${page}"><div class="errbox">${esc(e.message || e)}</div></div>`;
  } finally {
    clearTimeout(slow);
  }
}

/* ---------------------------------------------------------------- snapshots, pre-render, undo */
const SNAP = new Map();
const SNAP_OK = ["home", "review", "stores", "people", "performance", "attendance", "talent", "retention", "nps", "shifts", "insights", "relations",
  "brain", "organisation", "forecast", "goals", "notes", "engagement", "recognition", "policies", "manpower", "actions", "hiring", "learning"];
// pre-render: hovering a menu item warms that screen's data so the click opens it instantly
let warmT = null; const warmed = new Map();
// read-only requests each screen starts with: warming them fills the server caches without touching what is on screen
const WARM_CALL = { home: "dashboard", people: "people", stores: "stores", attendance: "attendance", insights: "people_insights", relations: "er_cases", brain: "brain_graph", organisation: "organisation", goals: "goals", forecast: "forecast" };
const WARM = Object.keys(WARM_CALL);
false && document.addEventListener("pointerover", e => {      // 3.0.1: off; it competed with real clicks for the CPU
  const b = e.target.closest && e.target.closest("#nav [data-go]"); if (!b) return;
  const k = b.dataset.go; clearTimeout(warmT);
  if (k === S.page || !WARM.includes(k) || (warmed.get(k) || 0) > Date.now() - 60000) return;
  warmT = setTimeout(() => { warmed.set(k, Date.now()); API.call(WARM_CALL[k], ["home", "people", "stores", "attendance"].includes(k) ? req() : {}).catch(() => {}); }, 140);
});
// undo toasts: a delete hides the item at once and only happens after the toast is gone
const PENDING = new Map();
function softDelete(label, el, run, after) {
  const id = Math.random().toString(36).slice(2);
  const rows = [].concat(el || []).filter(Boolean); rows.forEach(r => r.classList.add("gone"));
  const t = setTimeout(() => doIt(), 5200);
  const doIt = async () => { clearTimeout(t); if (!PENDING.has(id)) return; PENDING.delete(id); try { await run(); SNAP.clear(); after && after(); } catch (e) { rows.forEach(r => r.classList.remove("gone")); fail(e); } };
  PENDING.set(id, doIt);
  toast(`${label} deleted`, { action: "Undo", ms: 5000, onAction: () => { clearTimeout(t); PENDING.delete(id); rows.forEach(r => r.classList.remove("gone")); toast("Restored"); } });
}
function flushDeletes() { for (const f of [...PENDING.values()]) f(); }
window.addEventListener("beforeunload", flushDeletes);

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
    <div class="panel today-p slide"><div class="phd"><h2>What needs you today</h2><small>From every screen: alerts, data, actions, flight risk, hiring and training</small></div><div id="today" class="today"><div class="sk" style="height:46px"></div></div></div>
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
    </div>
    <div class="grid g2 slide stagger">
      <div class="panel"><div class="phd"><h2>Sales bridge</h2><small>From total budget to actual: what each store adds or loses</small></div><div id="ch-bridge"></div></div>
      <div class="panel"><div class="phd"><h2>Where the people are</h2><small>Headcount by store · click to focus</small></div><div id="ch-tree"></div></div>
    </div>
    ${(d.pins || []).length ? `<div class="panel slide"><div class="phd"><h2>📌 Pinned insights</h2><small>Answers you pinned from P&amp;O AI</small></div><div class="pins">${d.pins.map((p, i) => `<div class="pin"><button class="btn sm ghost pinx" data-act="pin-del" data-i="${i}" title="Unpin">${ic("x", 13)}</button><span class="pq">${esc(p.q || "Insight")} · ${esc((p.at || "").slice(0, 10))}</span><div class="md">${md(p.text || "")}</div></div>`).join("")}</div></div>` : ""}
    <div class="panel slide"><div class="phd"><h2>Productivity against target</h2><small>Bar = actual (% of target) · black mark = target · green on or above target</small></div><div id="ch-bullet"></div></div>`;
};
AFTER.home = () => {
  drawToday();
  const d = DATA.home;
  if (!d || !$("#ch-league")) return;
  const withSales = d.league.filter(r => r.sales != null && r.sales_pct);
  if ($("#ch-bridge")) {
    if (withSales.length) {
      const budget = withSales.reduce((a, r) => a + r.sales / (r.sales_pct / 100), 0);
      const gaps = withSales.map(r => ({ l: r.store, v: r.sales - r.sales / (r.sales_pct / 100) })).sort((a, b) => b.v - a.v);
      const keep = gaps.length > 8 ? [...gaps.slice(0, 4), { l: `${gaps.length - 7} others`, v: gaps.slice(4, -3).reduce((a, g) => a + g.v, 0) }, ...gaps.slice(-3)] : gaps;
      let run = budget, lo = budget, hi = budget; keep.forEach(g => { run += g.v; lo = Math.min(lo, run); hi = Math.max(hi, run); });
      const floor = Math.max(0, lo - Math.max(hi - lo, budget * 0.004) * 1.2);
      Charts.waterfall($("#ch-bridge"), { labels: keep.map(g => g.l.replace(/^(LAH|KCH|ISL|FAI|GUJ|RWP|MUL) /, "")), values: keep.map(g => g.v), start: budget, startLabel: "Budget", endLabel: "Actual", fmt: "money", floor });
      $("#ch-bridge").insertAdjacentHTML("beforeend", `<small style="color:var(--muted)">Axis starts at ${Charts.fmtv(floor, "money")} to show the differences</small>`);
    } else $("#ch-bridge").innerHTML = `<div class="empty">Import BO sales to see the bridge.</div>`;
  }
  if ($("#ch-tree")) { const lp = d.league.filter(r => r.people); Charts.treemap($("#ch-tree"), { labels: lp.map(r => r.store), values: lp.map(r => r.people), subs: lp.map(r => `average score ${scoreTxt(r.score)}`), onClick: i => setScope("store_id", lp[i].store_id) }); }
  if ($("#ch-bullet")) { const pr = d.league.filter(r => r.prod_pct != null); Charts.bullet($("#ch-bullet"), { items: pr.map(r => ({ label: r.store, value: r.prod_pct, target: 100, max: Math.max(130, ...pr.map(x => x.prod_pct)), fmt: "pct0" })) });
    if (!pr.length) $("#ch-bullet").innerHTML = `<div class="empty">Import productivity to compare against target.</div>`; }
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
  return `<div class="ph"><div><button class="btn sm ghost" data-go="stores">${ic("back", 14)} Stores</button><h1 style="margin-top:6px">${esc(d.store)} <span class="fmt">${esc(d.format)}</span> <button class="btn sm" data-act="visit-new" data-store="${esc(d.store)}">📋 Visit checklist</button></h1>
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
  ["📊", "How is CG doing at country level?", "Scorecard, what's strong, what's weak, focus"],
  ["🏬", "What should we focus on in Fresh Food at Fortress?", "One store, one department"],
  ["👥", "Show the department heads for LHH", "Every criterion and score, not ranked"],
  ["🥖", "How is Bakery doing across the country?", "One section in every store"],
  ["🧑‍💼", "Tell me about Arslan Arshad", "One person's full data sheet"],
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
    ${(m.followups || []).length && i === S.chat.length - 1 ? `<div class="fups">${m.followups.map(f => `<button class="fup" data-act="ask-sugg" data-q="${esc(f)}">${esc(f)}</button>`).join("")}</div>` : ""}
    <div class="ameta"><button class="mbtn" data-act="msg-copy" data-m="${i}" title="Copy">⧉ Copy</button><button class="mbtn" data-act="msg-retry" data-m="${i}" title="Ask again">↻ Retry</button>
    <button class="mbtn" data-act="msg-export" data-m="${i}" data-f="pdf" title="Save as a PDF report">⤓ PDF</button><button class="mbtn" data-act="msg-export" data-m="${i}" data-f="docx" title="Save as a Word document">⤓ Word</button>
    <button class="mbtn" data-act="msg-pin" data-m="${i}" title="Pin to the Overview">📌 Pin</button><button class="mbtn" data-act="msg-actions" data-m="${i}" title="Add the recommended actions to the tracker">→ Actions</button>
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
    S.chat[S.chat.length - 1] = { role: "assistant", content: r.answer, blocks: r.blocks, actions: r.actions, engine_label: r.engine_label, seconds: r.seconds, q: text, followups: r.followups || [] };
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
  "msg-export": async b => { const m = S.chat[+b.dataset.m]; if (!m) return;
    const r = await call("export_answer", { title: (m.q || "P&O AI answer").slice(0, 90), text: m.content || "", blocks: m.blocks || [], fmt: b.dataset.f });
    if (!r.cancelled) toast(`Saved ${r.name}`, { action: "Open", onAction: () => API.call("open_path", { path: r.path }), ms: 7000 }); },
  "msg-pin": async b => { const m = S.chat[+b.dataset.m]; if (!m) return; await call("pins", { add: { q: m.q || "", text: m.content || "", blocks: (m.blocks || []).slice(0, 3) } }); toast("Pinned to the Overview"); },
};

/* data health: is everything in for the month, and can the numbers be trusted? */
const HSTAT = { ok: ["In", "good"], derived: ["Worked out", "info"], older: ["Older period only", "warn"], stale: ["Old", "warn"], missing: ["Missing", "bad"] };
PAGES.health = async () => {
  const d = DATA.health = await API.call("data_health", { month: S.healthMonth || null });
  S.healthMonth = d.month;
  const ring = (v) => { const r = 34, c = 2 * Math.PI * r, tone = v >= 85 ? "var(--good)" : v >= 60 ? "var(--warn)" : "var(--bad)";
    return `<svg class="hring" viewBox="0 0 84 84" width="96" height="96"><circle cx="42" cy="42" r="${r}" fill="none" stroke="var(--bg-2)" stroke-width="9"/>
      <circle cx="42" cy="42" r="${r}" fill="none" stroke="${tone}" stroke-width="9" stroke-linecap="round" stroke-dasharray="${c}" stroke-dashoffset="${c * (1 - v / 100)}" transform="rotate(-90 42 42)" class="hring-arc"/>
      <text x="42" y="47" text-anchor="middle" font-size="22" font-weight="800" fill="var(--ink)">${v}</text></svg>`; };
  const lvl = { bad: ["!", "bad"], warn: ["•", "warn"], info: ["i", ""] };
  const months = d.months.length ? d.months : [{ value: d.month, label: d.month_label }];
  return `<div class="ph"><div><h1>Data health</h1><p>Is everything for the month in, and can the numbers be trusted? Fix what is listed here before presenting.</p></div>
      <div class="row"><label class="pv-l">Month<select class="input sm" id="h-month">${months.map(m => `<option value="${m.value}" ${m.value === d.month ? "selected" : ""}>${esc(m.label)}</option>`).join("")}</select></label>
      <button class="btn ${d.locked ? "" : "ghost"}" data-act="h-lock" data-locked="${d.locked ? 0 : 1}" title="A locked month cannot be changed by later imports">${d.locked ? "🔒 Locked · unlock" : "🔓 Lock month"}</button></div></div>
    <div class="grid hgrid">
      <div class="panel hhealth"><div class="row" style="gap:18px;align-items:center">${ring(d.score)}<div><span class="kpi-l">Data health · ${esc(d.month_label)}</span>
        <h2 style="margin:4px 0">${esc(d.verdict)}</h2><small style="color:var(--muted)">${d.ready} of ${d.expected} reports in · ${d.checks.length} thing${d.checks.length === 1 ? "" : "s"} to check</small></div></div></div>
      <div class="panel"><div class="phd"><h2>Monthly checklist</h2><div class="row"><button class="btn sm" data-act="h-request">✉ Ask for missing reports</button><button class="btn sm" data-act="month-close">✓ Close the month</button><button class="btn sm primary" data-go="import">${ic("import", 14)}Import missing</button></div></div>
        <div class="hlist">${d.checklist.map(c => `<div class="hrow"><span class="chip ${HSTAT[c.status][1]}">${HSTAT[c.status][0]}</span><b>${esc(c.name)}</b>
          <small>${esc(c.label || "")}${c.detail && c.detail !== "latest is " + c.label ? ` · ${esc(c.detail)}` : ""}</small></div>`).join("")}</div></div></div>
    <div class="panel"><div class="phd"><h2>Checks</h2><small>Reconciliation across tabs, store names, conflicting files, totals and outliers</small></div>
      ${d.checks.length ? d.checks.map((c, i) => `<details class="hcheck ${lvl[c.level][1]}"><summary><span class="ic">${lvl[c.level][0]}</span><span><b>${esc(c.area)}</b> · ${esc(c.message)}</span>
        ${c.go ? `<button class="btn sm" data-go="${c.go}" ${c.tab ? `data-tab="${c.tab}"` : ""}>Open</button>` : ""}</summary>
        ${c.items.length ? `<ul>${c.items.map(x => `<li>${esc(x)}</li>`).join("")}${c.count > c.items.length ? `<li style="color:var(--muted)">… and ${c.count - c.items.length} more</li>` : ""}</ul>` : ""}</details>`).join("")
        : `<div class="empty">✓ Nothing to fix. The data agrees across every tab.</div>`}</div>
    <details class="panel hdict"><summary><h2 style="margin:0;display:inline">Measure dictionary</h2> <small style="color:var(--muted)">what every figure means, where it comes from and how it works across MTD and YTD</small></summary>
      <div class="tbl-wrap" style="margin-top:10px"><table class="t"><thead><tr><th>Measure</th><th>How it is worked out</th><th>From</th><th>Across periods</th></tr></thead>
      <tbody>${d.measures.map(m => `<tr><td><b>${esc(m.name)}</b></td><td>${esc(m.formula)}</td><td>${esc(m.source)}</td><td><small>${esc(m.periods)}</small></td></tr>`).join("")}</tbody></table></div></details>`;
};
AFTER.health = () => { const m = $("#h-month"); if (m) m.onchange = () => { S.healthMonth = m.value; render(); }; };
const HEALTH_ACTS = {};
HEALTH_ACTS["h-request"] = async () => {
  const r = await call("data_request", { month: S.healthMonth, lang: "en" });
  if (!r.missing.length) return toast("Nothing is missing for this month.");
  const m = modal(`<h3>Ask for the missing reports</h3><p style="color:var(--muted);margin:0 0 10px">${r.missing.length} report${r.missing.length > 1 ? "s" : ""} to request. Copy into WhatsApp or email.</p>
    <div class="seg" style="margin-bottom:8px"><button data-l="en" aria-pressed="true">English</button><button data-l="ur" aria-pressed="false">اردو</button></div>
    <textarea class="input" id="dr-t" rows="12" style="width:100%">${esc(r.text)}</textarea>
    <div class="row" style="justify-content:flex-end;margin-top:10px"><button class="btn" data-act="modal-close">Close</button><button class="btn primary" id="dr-copy">Copy</button></div>`);
  $$(".seg button", m).forEach(b => b.onclick = async () => { $$(".seg button", m).forEach(x => x.setAttribute("aria-pressed", x === b)); const t = await call("data_request", { month: S.healthMonth, lang: b.dataset.l }); $("#dr-t", m).value = t.text; $("#dr-t", m).dir = b.dataset.l === "ur" ? "rtl" : "ltr"; });
  $("#dr-copy", m).onclick = () => { const t = $("#dr-t", m); try { navigator.clipboard.writeText(t.value); } catch (e) { t.select(); document.execCommand("copy"); } toast("Copied"); };
};
HEALTH_ACTS["h-lock"] = async b => { await call("lock_month", { month: S.healthMonth, locked: b.dataset.locked === "1" }); toast(b.dataset.locked === "1" ? "Month locked" : "Month unlocked"); render(); };

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
const KIND_ICON = { roster: "👥", attendance: "🕘", productivity: "📈", sales: "🧾", leave: "🏖️", po_rating: "⭐", po_role: "🪪", po_shift: "🗓️", po_turnover: "🚪", po_da: "⚖️", po_nps: "💬", po_shrink: "📦", dataset: "📊" };
const IMP_STATUS = { ok: ["In", "good"], derived: ["Worked out", "good"], older: ["Older period only", "warn"], stale: ["Old copy", "warn"], missing: ["Needed", "bad"] };
function impSheetCard(f, r, sess) {
  const a = `data-file="${esc(f.file)}" data-sheet="${esc(r.sheet)}"`;
  const conf = Math.round((r.confidence || 0) * 100);
  const issues = r.issues || [];
  const lvl = { bad: "bad", warn: "warn", info: "info" };
  return `<div class="isheet ${r.kind === "dataset" ? "other" : ""}">
    <div class="isheet-h"><span class="isheet-ic">${KIND_ICON[r.kind] || "📄"}</span><div style="flex:1;min-width:0"><b>${esc(r.label)}</b><span class="sub">${esc(f.file)} · sheet “${esc(r.sheet)}” · ${r.rows.toLocaleString("en-US")} rows</span></div>
      ${r.kind === "dataset" ? `<span class="chip">Not a standard report</span>` : `<span class="conf ${conf >= 85 ? "hi" : conf >= 60 ? "mid" : "lo"}" title="How sure P&O is about what this sheet is"><i style="width:${conf}%"></i><b>${conf}% sure</b></span>`}
      ${r.remembered ? `<span class="chip gold" title="Set up the way you imported it last time">✓ remembered</span>` : ""}</div>
    <small style="color:var(--muted)">${esc(r.summary)}</small>
    ${r.smart ? `<div class="imap"><small><b>Smart Import read the columns:</b></small> ${r.mapping.map(m => `<span class="mchip ${m.score >= 0.7 ? "" : "weak"}" title="${esc((m.examples || []).join(" · "))}">${esc(m.header || "(no title)")} → <b>${esc(m.label)}</b></span>`).join("")}</div>` : ""}
    <div class="imp-opts">
      <label class="dx-l">This sheet is<select class="input" data-imp-kind ${a}>${(f.kinds || []).map(k => `<option value="${k.value}" ${k.value === (r.kind_hint || r.kind) ? "selected" : ""}>${esc(k.label)}</option>`).join("")}</select></label>
      ${impPeriod(f, r, sess)}
      ${["roster"].includes(r.kind) ? `<label class="dx-l">Roster as of<input class="input" type="date" data-opt="as_of" ${a} value="${esc(r.as_of || new Date().toISOString().slice(0, 10))}"></label>` : ""}
      <div class="row" style="align-self:end;gap:6px"><button class="btn sm" data-act="imp-map" ${a}>⚙ Check columns</button>${S.init.ai && S.init.ai.active && S.init.ai.active !== "basic" ? `<button class="btn sm ghost" data-act="imp-ai" ${a}>✨ Ask AI to read it</button>` : ""}</div>
      ${r.kind === "dataset" ? `<details class="imp-more"><summary>Name and description (optional)</summary><div class="imp-more-b">
        <label class="dx-l">Name<input class="input" data-opt="title" ${a} placeholder="${esc(r.sheet)}"></label>
        <label class="dx-l imp-note">What is this sheet about?<textarea class="input" rows="2" data-opt="note" ${a} placeholder="e.g. Weekly footfall by store from Ops, week 41"></textarea></label></div></details>` : ""}
    </div>
    ${issues.length ? `<div class="iissues">${issues.map(i => `<div class="iiss ${lvl[i.level] || "info"}"><span>${i.level === "bad" ? "✕" : i.level === "warn" ? "!" : "i"}</span><div>${esc(i.text)}${i.examples && i.examples.length ? `<small>${esc(i.examples.slice(0, 5).join(" · "))}${i.examples.length > 5 ? " …" : ""}</small>` : ""}</div></div>`).join("")}</div>` : `<div class="iiss good"><span>✓</span><div>No problems found in this sheet.</div></div>`}
    ${r.warnings.filter(w => !/Read by Smart Import|Choose the month/.test(w)).map(w => `<small style="color:var(--warn-ink)">⚠ ${esc(w)}</small>`).join("")}
    ${r.preview && r.preview.length ? `<details><summary class="imp-prev">Preview the first rows</summary><div class="tbl-wrap" style="max-height:220px;margin-top:6px"><table class="t"><thead><tr>${Object.keys(r.preview[0]).filter(k => typeof r.preview[0][k] !== "object").map(k => `<th>${esc(k)}</th>`).join("")}</tr></thead><tbody>${r.preview.map(p => `<tr>${Object.keys(r.preview[0]).filter(k => typeof r.preview[0][k] !== "object").map(k => `<td>${esc(p[k] ?? "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div></details>` : ""}
  </div>`;
}
PAGES.import = async () => {
  const yr = S.impYear || +(S.impMonth || S.month || new Date().toISOString()).slice(0, 4);
  const [h, cal] = await Promise.all([API.call("imports"), API.call("import_calendar", { year: yr })]);
  DATA.cal = cal;
  const cur = cal.today;
  S.impMonth = S.impMonth || (S.month && S.month.slice(0, 4) == yr ? S.month : cal.months.filter(m => !m.future).slice(-1)[0]?.month) || cur;
  const mon = cal.months.find(m => m.month === S.impMonth) || cal.months[0];
  const sess = S.importSess;
  const found = new Set(sess ? sess.files.flatMap(f => f.results.map(r => r.kind_hint || r.kind)) : []);
  const tiles = cal.months.map(m => { const pct = m.total ? m.ok / m.total : 0; const cls = m.future ? "fut" : pct >= 0.99 ? "full" : pct >= 0.5 ? "part" : pct > 0 ? "low" : "none";
    return `<button class="mtile ${cls} ${m.month === S.impMonth ? "on" : ""}" data-act="imp-month" data-m="${m.month}" ${m.future ? "disabled" : ""}><b>${m.short}</b><span class="mring" style="--p:${Math.round(pct * 100)}"></span><small>${m.future ? "—" : `${m.ok}/${m.total}`}</small>${m.locked ? `<i title="Locked">🔒</i>` : ""}</button>`; }).join("");
  const slots = mon.items.map(it => { const st = found.has(it.kind) ? ["Ready to save", "info"] : IMP_STATUS[it.status] || ["", ""];
    return `<div class="slot ${found.has(it.kind) ? "found" : it.status}"><div class="slot-ic">${KIND_ICON[it.kind] || "📄"}</div><div class="slot-b"><b>${esc(it.name)}</b><small>${esc(it.status === "missing" && !found.has(it.kind) ? (cal.guide[it.kind] || "") : (it.label || it.detail || ""))}</small></div><span class="chip ${st[1]}">${st[0]}</span></div>`; }).join("");
  const nres = sess ? sess.files.reduce((a, f) => a + f.results.length, 0) : 0;
  return `<div class="ph"><div><h1>Import data</h1><p>Pick the month, then drop every file you have for it: any report, any layout, any file name. Smart Import works out what each sheet is from its columns, checks it for problems and shows you before anything is saved.</p></div></div>
    ${S.init.unsure_stores ? `<div class="banner">🏬 ${S.init.unsure_stores} store name${S.init.unsure_stores > 1 ? "s were" : " was"} matched with less certainty. <button class="btn sm" data-go="settings" data-tab="stores">Check store names</button></div>` : ""}
    <div class="panel icald"><div class="phd"><h2>1 · Which month are you loading?</h2><div class="row"><button class="btn sm ghost" data-act="imp-year" data-y="${yr - 1}">‹ ${yr - 1}</button><b>${yr}</b><button class="btn sm ghost" data-act="imp-year" data-y="${yr + 1}" ${yr + 1 > +cur.slice(0, 4) ? "disabled" : ""}>${yr + 1} ›</button></div></div>
      <div class="mtiles">${tiles}</div></div>
    <div class="grid g2 imp-grid">
      <div class="panel"><div class="phd"><h2>2 · What ${esc(mon.label)} needs</h2><small>${mon.ok} of ${mon.total} in${found.size ? ` · ${found.size} in this upload` : ""}</small></div><div class="slots">${slots}</div></div>
      <div class="drop big" id="drop"><div class="ic">${ic("import", 30)}</div><h3>3 · Drop all the files for ${esc(mon.label)}</h3><p style="margin:0;color:var(--muted)">Excel, CSV, text or HTML exports · any number · any names · several sheets in one workbook are fine</p>
        <div class="row" style="justify-content:center"><button class="btn primary" data-act="pick">${ic("file", 16)}Choose files</button><button class="btn" data-act="paste">${ic("paste", 16)}Paste cells</button></div>
        <small style="color:var(--muted)">Files stay on this computer. Nothing is saved until you press Save.</small>
        <input type="file" id="filein" multiple hidden accept=".xlsx,.xls,.xlsm,.xlsb,.ods,.csv,.txt,.tsv,.htm,.html"></div></div>
    ${sess ? `<div class="panel"><div class="phd"><h2>4 · Check and save</h2><div class="tools"><button class="btn" data-act="import-cancel">Cancel</button><button class="btn primary" data-act="import-commit" ${nres ? "" : "disabled"}>Save ${nres} table${nres === 1 ? "" : "s"}</button></div></div>
      <div class="isheets">${sess.files.map(f => f.results.length ? f.results.map(r => impSheetCard(f, r, sess)).join("") : `<div class="iiss bad"><span>✕</span><div><b>${esc(f.file)}</b>: no table could be read.${f.skipped.length ? ` <small>${esc(f.skipped.join(", "))}</small>` : ""}</div></div>`).join("")}</div>
      ${(sess.errors || []).map(e => `<div class="errbox">${esc(e.file)}: ${esc(e.error)}</div>`).join("")}</div>` : ""}
    <details class="panel flush" open><summary class="phd" style="padding:14px 16px;cursor:pointer"><h2 style="display:inline">Import history</h2> <small>Undo removes an import's data; Restore brings it back</small></summary><div class="tbl-wrap" style="max-height:520px"><table class="t"><thead><tr><th>When</th><th>Type</th><th>File</th><th>Period</th><th class="n">Rows</th><th>Summary</th><th></th></tr></thead>
    <tbody>${h.rows.map(r => `<tr style="${r.active ? "" : "opacity:.5"}"><td>${esc(r.created_at.replace("T", " ").slice(0, 16))}</td><td><span class="chip">${KIND_ICON[r.kind] || ""} ${esc(r.kind_label || r.kind)}</span></td><td>${esc(r.file_name)}<span class="sub">${esc(r.source)}</span></td>
      <td class="nw">${r.period_label ? `<span class="chip ${r.period_type === "ytd" ? "gold" : r.period_type === "mtd" ? "info" : ""}">${esc(r.period_label)}</span>` : esc(r.as_of || r.month || "")}</td><td class="n">${r.rows.toLocaleString("en-US")}</td><td>${esc(r.summary)}${r.warnings.length ? `<span class="sub">⚠ ${esc(r.warnings[0])}</span>` : ""}</td>
      <td class="n">${r.active ? `<button class="btn sm" data-act="undo" data-id="${r.id}">${ic("undo", 13)}Undo</button>` : `<button class="btn sm" data-act="redo" data-id="${r.id}">Restore</button>`}</td></tr>`).join("") || `<tr><td colspan="7"><div class="empty">Nothing imported yet.</div></td></tr>`}</tbody></table></div></details>`;
};
function impReplace(file) {
  const s = S.importSess; if (!s) return;
  const i = s.files.findIndex(f => f.file === file.file);
  if (i >= 0) s.files[i] = { ...s.files[i], ...file };
  render();
}
function impMapForm(file, sheet) {
  const f = S.importSess.files.find(x => x.file === file), r = f.results.find(x => x.sheet === sheet);
  const cur = {}; (r.mapping || []).forEach(m => { cur[m.column] = m.field; });
  const cols = r.columns && r.columns.length ? r.columns : (r.mapping || []).map(m => ({ index: m.column, header: m.header, examples: m.examples }));
  const fields = f.fields || [];
  const m = modal(`<h3>Which column is which?</h3><p style="color:var(--muted);margin:0 0 10px">Sheet “${esc(sheet)}”. Set what each column holds, or “Ignore”. P&O remembers this for next month's file.</p>
    <label class="dx-l" style="max-width:320px">This sheet is<select class="input" id="mf-kind">${f.kinds.map(k => `<option value="${k.value}" ${k.value === r.kind ? "selected" : ""}>${esc(k.label)}</option>`).join("")}</select></label>
    <div class="tbl-wrap" style="max-height:52vh;margin-top:10px"><table class="t"><thead><tr><th>Column in the file</th><th>Example values</th><th>Holds</th></tr></thead><tbody>
    ${cols.map(c => `<tr><td><b>${esc(c.header || "(no title)")}</b><span class="sub">column ${String.fromCharCode(65 + (c.index % 26))}${c.index >= 26 ? Math.floor(c.index / 26) : ""}</span></td><td><small>${esc((c.examples || []).join(" · "))}</small></td>
      <td><select class="input sm" data-mfcol="${c.index}"><option value="">Ignore</option>${fields.map(x => `<option value="${x.value}" ${cur[c.index] === x.value ? "selected" : ""}>${esc(x.label)}</option>`).join("")}</select></td></tr>`).join("")}</tbody></table></div>
    <div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" data-act="modal-close">Cancel</button><button class="btn primary" id="mf-go">Read it again</button></div>`);
  $("#mf-go", m).onclick = async () => {
    const mapping = {}; $$("[data-mfcol]", m).forEach(s => { if (s.value) mapping[s.value] = +s.dataset.mfcol; });
    const b = $("#mf-go", m); b.disabled = true; b.innerHTML = `<span class="spin" style="width:13px;height:13px"></span> Reading…`;
    try { const res = await call("import_remap", { token: S.importSess.token, file, sheet, kind: $("#mf-kind", m).value, mapping }); closeModal(); impReplace(res.file); toast("Read again with your column matches"); }
    catch (e) { b.disabled = false; b.textContent = "Read it again"; }
  };
}
const IMP_ACTS = {
  "imp-month": b => { S.impMonth = b.dataset.m; if (S.importSess) toast(`Files in this upload will be saved for ${b.dataset.m}. Re-add them if they belong to another month.`); render(); },
  "imp-year": b => { S.impYear = +b.dataset.y; S.impMonth = null; render(); },
  "imp-map": b => impMapForm(b.dataset.file, b.dataset.sheet),
  "imp-ai": async b => { b.disabled = true; b.innerHTML = `<span class="spin" style="width:13px;height:13px"></span> Reading…`;
    try { const r = await call("import_ai", { token: S.importSess.token, file: b.dataset.file, sheet: b.dataset.sheet }); impReplace(r.file); toast(`AI: ${r.why || "columns matched"}`, { ms: 7000 }); }
    catch (e) { b.disabled = false; b.textContent = "✨ Ask AI to read it"; } },
};
document.addEventListener("change", async e => {
  const k = e.target.closest && e.target.closest("[data-imp-kind]");
  if (!k || !S.importSess) return;
  try { const r = await call("import_remap", { token: S.importSess.token, file: k.dataset.file, sheet: k.dataset.sheet, kind: k.value }); impReplace(r.file); toast("Read again as " + k.options[k.selectedIndex].text); }
  catch (err) { render(); }
});
AFTER.import = () => {
  const drop = $("#drop"), fi = $("#filein"), page = $(".page");
  if (!drop) return;
  [drop, page].forEach(el => { if (!el) return;
    ["dragenter", "dragover"].forEach(ev => el.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
    ["dragleave", "drop"].forEach(ev => el.addEventListener(ev, () => drop.classList.remove("over")));
    el.addEventListener("drop", e => { e.preventDefault(); e.stopPropagation(); if (e.dataTransfer.files.length && !window.qt) uploadFiles(e.dataTransfer.files); }); });
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
  toast(`Reading ${files.length} file${files.length > 1 ? "s" : ""}…`);
  S.importSess = await call("import_upload", { files, month: S.impMonth || null });
  render();
}
window.PNO_drop = async paths => {
  if (S.page === "ask") { S.attach.push(...paths); drawChat(); return; }
  if (S.page === "hiring" && S.hire.vid) { toast(`Reading ${paths.length} CV${paths.length > 1 ? "s" : ""}…`); hireAfterAdd(await call("hire_add_paths", { paths, vacancy_id: S.hire.vid })); return; }
  if (S.page !== "import") { S.page = "import"; $$("#nav button").forEach(b => b.toggleAttribute("aria-current", b.dataset.go === "import")); }
  toast("Reading " + paths.length + " file" + (paths.length > 1 ? "s" : "") + "…");
  S.importSess = await call("import_analyze", { paths, month: S.impMonth || null });
  render();
};

/* settings */
PAGES.settings = async () => {
  const tabs = S.init.full_mode
    ? [["bench", "Criteria"], ["scoring", "Scoring"], ["ai", "AI assistant"], ["stores", "Stores"], ["sections", "Sections"], ["holidays", "Holidays"], ["leave", "Leave"], ["data", "Data & backup"], ["backups", "Backups & columns"], ["look", "Appearance"]]
    : [["bench", "Criteria"], ["ai", "AI"], ["stores", "Stores"], ["backups", "Backups & columns"], ["data", "Data"], ["look", "Appearance"]];
  if (!tabs.some(x => x[0] === S.setTab)) S.setTab = S.init.full_mode ? "scoring" : "bench";
  const t = S.setTab;
  const body = await SETTINGS[t]();
  return `<div class="ph"><div><h1>Settings</h1><p>Benchmarks for the colours, which AI answers, store matching, backups and your data.</p></div></div>
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
    <div class="panel"><div class="phd"><h2>Which AI does which job</h2><small>For example: courses on Gemini, anything with names on the offline AI. If the chosen AI fails, the next one answers and says so.</small></div>
      <div class="routes">${(s.tasks || []).map(t => `<div class="setting"><div><b>${esc(t.label)}</b></div><select class="input sm" data-route="${t.id}">${[["auto", "Same as above (" + esc(s.label) + ")"], ...s.choices.filter(c => c.id !== "auto").map(c => [c.id, c.name + (c.ready ? "" : " · not set up")])].map(([v, l]) => `<option value="${v}" ${v === t.engine ? "selected" : ""}>${l}</option>`).join("")}</select></div>`).join("")}</div></div>
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
  const tp = (await API.call("import_templates")).templates;
  const tpl = `<div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Remembered import layouts</h2><small>P&O remembers how each recurring file was read (type and period) and applies it next time</small></div>
    <div class="tbl-wrap" style="max-height:300px"><table class="t"><thead><tr><th>File pattern</th><th>Read as</th><th>Period</th><th>Last used</th><th></th></tr></thead><tbody>
    ${tp.map(t => `<tr><td><b>${esc(t.key)}</b>${t.example ? `<span class="sub">${esc(t.example)}</span>` : ""}</td><td>${esc(t.kind_label || t.kind || "")}</td><td>${esc((t.period_type || "").toUpperCase())}</td><td class="nw">${esc((t.used || "").slice(0, 10))}</td>
      <td><button class="btn sm ghost" data-act="tpl-forget" data-k="${esc(t.key)}">Forget</button></td></tr>`).join("") || `<tr><td colspan="5"><div class="empty">Nothing yet: layouts are remembered after your first import.</div></td></tr>`}</tbody></table></div></div>`;
  return tpl + `<div class="panel"><div class="phd"><h2>Your data</h2></div>
    <div class="setting"><div><b>Database</b><small>${esc(s.db_path)}</small></div></div>
    <div class="setting"><div><b>Back up</b><small>Save a copy of everything (keep it secure: it contains staff data)</small></div><button class="btn" data-act="backup">Back up…</button></div>
    <div class="setting"><div><b>Restore</b><small>Replace the data with a backup (the current data is kept as a safety copy)</small></div><button class="btn danger" data-act="restore">Restore…</button></div>
    <div class="setting"><div><b>Demo data</b><small>Explore P&O with fictional people and stores, in a separate database</small></div>${S.init.demo ? `<button class="btn" data-act="demo-off">Leave demo</button>` : `<button class="btn" data-act="demo-on">Try demo data</button>`}</div></div>
    <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Activity log</h2></div><div class="tbl-wrap" style="max-height:400px"><table class="t"><thead><tr><th>When</th><th>What</th><th>Details</th></tr></thead><tbody>${a.rows.map(r => `<tr><td>${esc(r.ts.replace("T", " "))}</td><td>${esc(r.action)}</td><td>${esc(r.detail || "")}</td></tr>`).join("")}</tbody></table></div></div>`;
};
SETTINGS.look = async () => {
  const s = await API.call("settings");
  return `<div class="panel"><div class="setting"><div><b>Theme</b><small>Follow Windows, or always light / dark</small></div><div class="seg">${[["auto", "Auto"], ["light", "Light"], ["dark", "Dark"]].map(([k, l]) => `<button data-act="theme" data-theme="${k}" aria-pressed="${s.theme === k}">${l}</button>`).join("")}</div></div>
    <div class="setting"><div><b>Full P&amp;O toolkit</b><small>Show every module (hiring, learning, relations, People Brain…) as well as the Review</small></div><label class="switch"><input type="checkbox" id="full-mode" ${S.init.full_mode ? "checked" : ""}><span></span></label></div>
    <div class="setting"><div><b>Hide names</b><small>Show employee codes instead of names everywhere and in exports (for screen-sharing)</small></div><label class="switch"><input type="checkbox" id="hide-names" ${s.hide_names ? "checked" : ""}><span></span></label></div><div class="setting"><div><b>App lock</b><small>${S.init.lock && S.init.lock.enabled ? `On: asks for your PIN when P&O opens and after ${S.init.lock.minutes} minutes idle` : "Ask for a PIN when P&O opens and after it is left idle"}</small></div><button class="btn" data-act="lock-set">${S.init.lock && S.init.lock.enabled ? "Change PIN…" : "Set a PIN…"}</button></div>
    </div>`;
};
AFTER.settings = () => {
  $$("[data-route]").forEach(sel => sel.onchange = async () => { await call("agent_settings", { routes: { [sel.dataset.route]: sel.value } }); toast("Saved: " + sel.closest(".setting").querySelector("b").textContent + " → " + sel.options[sel.selectedIndex].text); });
  const sum = ro => { const t = $$(`[data-w="${ro}"]`).reduce((a, i) => a + (+i.value || 0), 0); const b = $(`[data-total="${ro}"]`); if (b) b.textContent = t; };
  $$("[data-w]").forEach(i => { i.oninput = () => sum(i.dataset.w); sum(i.dataset.w); });
  const an = $("#anon"); if (an) an.onchange = () => call("agent_settings", { anonymise: an.checked }).then(() => toast("Saved"));
  const fm = $("#full-mode"); if (fm) fm.onchange = async () => { await call("full_mode", { on: fm.checked }); S.init.full_mode = fm.checked; applyMode(); shell(); updateSide(); toast(fm.checked ? "All modules shown" : "Review and Ask only"); };
  const bk = $("#bk-auto"); if (bk) bk.onchange = () => call("backup_auto", { on: bk.checked }).then(() => toast(bk.checked ? "Daily backups on" : "Daily backups off"));
  $$("[data-syn]").forEach(i => i.onchange = () => call("synonyms_save", { field: i.dataset.syn, words: i.value.split(",") }).then(() => toast("Smart Import will recognise these names")));
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
    <div class="setting"><div><b>Format</b></div><div class="seg" id="fmtseg">${[["pdf", "PDF"], ["docx", "Word"], ["pptx", "PowerPoint"], ["xlsx", "Excel"]].map(([k, l], i) => `<button data-fmt="${k}" aria-pressed="${i === 0}">${l}</button>`).join("")}</div></div>
    <div class="setting"><div><b>Hide names</b><small>Employee codes only, for packs going beyond HR</small></div><label class="switch"><input type="checkbox" id="exp-hide" ${S.init.hide_names ? "checked" : ""}><span></span></label></div>
    <div class="setting"><div><b>One file per store</b><small>The chosen report for every store (Store Report, Attendance Exceptions or People Ranking), zipped, ready to send to each store manager</small></div><label class="switch"><input type="checkbox" id="exp-batch"><span></span></label></div>
    <div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" data-act="modal-close">Cancel</button><button class="btn primary" id="exp-go">${ic("export", 16)}Export</button></div>`);
  $$("#fmtseg button", m).forEach(b => b.onclick = () => $$("#fmtseg button", m).forEach(x => x.setAttribute("aria-pressed", x === b)));
  $("#exp-go", m).onclick = async () => {
    const pack = $("input[name=pack]:checked", m).value, fmt = $("#fmtseg button[aria-pressed=true]", m).dataset.fmt;
    const btn = $("#exp-go", m); btn.disabled = true; btn.innerHTML = `<span class="spin" style="width:14px;height:14px"></span> Preparing…`;
    try {
      const r = $("#exp-batch", m).checked ? await API.call("export_batch", { pack: ["store", "attendance", "people"].includes(pack) ? pack : "store", fmt, month: S.month, hide: $("#exp-hide", m).checked })
        : await API.call("export", { pack, fmt, month: S.month, scope: S.scope, emp: o.emp || null, store_id: o.store || S.scope.store_id || null, hide: $("#exp-hide", m).checked });
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
  present: () => { document.body.classList.toggle("present"); if (document.body.classList.contains("present")) { if (S.page !== "rv") go("rv"); toast("Presenting · use ↑ ↓ or the buttons · Esc to exit"); } },
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
  pick: async () => { if (window.qt) { const r = await call("pick_files", { month: S.impMonth || null }); if (!r.cancelled) { S.importSess = r; render(); } } else $("#filein").click(); },
  paste: () => {
    const m = modal(`<h3>Paste data</h3><p style="color:var(--muted);margin:0 0 10px">Copy the cells in Excel (including the header rows) and paste them here.</p><textarea class="input" id="paste-t" rows="12" style="width:100%;font-family:monospace;font-size:12px"></textarea>
      <div class="row" style="justify-content:flex-end;margin-top:10px"><button class="btn" data-act="modal-close">Cancel</button><button class="btn primary" id="paste-go">Preview</button></div>`);
    $("#paste-go", m).onclick = async () => { const t = $("#paste-t", m).value; if (!t.trim()) return; closeModal(); S.importSess = await call("import_analyze", { text: t, name: "Pasted data", month: S.impMonth || null }); render(); };
    setTimeout(() => $("#paste-t", m).focus(), 100);
  },
  "import-cancel": () => { S.importSess = null; render(); },
  "import-commit": async b => {
    const opts = {};
    $$("[data-opt]").forEach(i => { if (!String(i.value || "").trim()) return; (opts[i.dataset.file] = opts[i.dataset.file] || {})[i.dataset.sheet] = { ...((opts[i.dataset.file] || {})[i.dataset.sheet] || {}), [i.dataset.opt]: i.value }; });
    b.disabled = true; b.innerHTML = `<span class="spin" style="width:14px;height:14px"></span> Importing…`;
    try {
      const r = await API.call("import_commit", { token: S.importSess.token, options: opts });
      const lab = {}; (S.importSess.files[0]?.kinds || []).forEach(k => lab[k.value] = k.label);
      const ok = r.done.flatMap(f => (f.results || []).filter(x => x.status === "ok"));
      const bad = r.done.flatMap(f => f.error ? [`${f.file}: ${f.error}`] : (f.results || []).filter(x => x.status !== "ok").map(x => `${lab[x.kind] || x.kind}: ${x.message}`));
      const lines = [`Saved ${ok.length} table${ok.length === 1 ? "" : "s"}: ` + ok.map(x => `${lab[x.kind] || x.kind} (${x.rows.toLocaleString("en-US")} rows${x.period ? ", " + x.period : ""})`).join(", "), ...bad];
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
  const cov = (p.coverage || []).map(c => `<tr><td>${esc(c.name)}</td><td>${c.type ? `<span class="chip ${PTYPE[c.type] ? PTYPE[c.type][1] : ""}">${esc(PTYPE[c.type] ? PTYPE[c.type][0] : c.type)}</span>` : ""} ${esc(c.label)}</td><td class="n">${c.rows ? c.rows.toLocaleString("en-US") : "—"}${c.age != null ? `<span class="sub">${c.age === 0 ? "today" : c.age + "d ago"}</span>` : ""}</td><td>${c.note ? `<small style="color:var(--warn-ink)">${esc(c.note.split(": ").slice(1).join(": "))}</small>` : c.how ? `<small style="color:var(--good-ink, var(--good))">✓ ${esc(c.how)}</small>` : ""}</td></tr>`).join("");
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
          <span style="flex:1"><b>${esc(a.store)}</b> · ${esc(a.message)}<small style="display:block;color:var(--muted)">${esc(a.area)}</small></span>
          <button class="btn sm ghost" data-act="act-quick" data-title="${esc(a.area + ": " + a.message)}" data-store="${esc(a.store)}" data-area="${esc(a.area)}" data-source="Business review" title="Make this an action">+ Action</button></div>`).join("")}</div></div>
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
  const tabs = `<div class="seg">${[["leaders", "Leader 360°"], ["grid", "Talent grid"], ["risk", "Flight risk"], ["succ", "Succession"], ["bench", "Bench strength"], ["weights", "Index weights"]].map(([k, l]) => `<button data-act="po-tab" data-tab="${k}" aria-pressed="${tab === k}">${l}</button>`).join("")}</div>`;
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
  } else if (tab === "risk") {
    const r = DATA.risk = await API.call("po_risk");
    const n = b => r.risk.filter(x => x.band === b).length;
    body = `<div class="kpis k5"><div class="kpi"><span class="kpi-l">High risk</span><span class="kpi-v t-bad">${n("High")}</span><span class="kpi-s"><span>score 55+</span></span></div>
        <div class="kpi"><span class="kpi-l">Medium</span><span class="kpi-v">${n("Medium")}</span><span class="kpi-s"><span>35–54</span></span></div><div class="kpi"><span class="kpi-l">Low</span><span class="kpi-v">${n("Low")}</span><span class="kpi-s"><span>below 35</span></span></div>
        <div class="kpi"><span class="kpi-l">Leaders checked</span><span class="kpi-v">${r.risk.length}</span><span class="kpi-s"><span>leavers window: ${esc(r.window)}</span></span></div>
        <div class="kpi"><span class="kpi-l">Top reason</span><span class="kpi-v txt">${esc((() => { const c = {}; r.risk.forEach(x => x.reasons.forEach(y => { const k = y.replace(/[\d.]+/g, "#").split("(")[0].trim(); c[k] = (c[k] || 0) + 1; })); return Object.entries(c).sort((a, b) => b[1] - a[1])[0]?.[0] || "—"; })())}</span><span class="kpi-s"><span>most common signal</span></span></div></div>
      <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Who might leave, and why</h2><small>Points for each signal in the data: new joiners, years without a move, low or missing ratings, leavers and DA in their area, acting without the title, heavy evening rosters, store turnover. A prompt for a stay conversation, not a verdict.</small></div>
      <div class="tbl-wrap" style="max-height:calc(100vh - 330px)"><table class="t"><thead><tr><th>Risk</th><th>Leader</th><th>Store</th><th>Leads</th><th>Why</th><th class="n">In role</th><th></th></tr></thead><tbody>
      ${r.risk.map(x => `<tr><td><div class="hbarw"><div class="hbarv ${x.band === "High" ? "no" : x.band === "Medium" ? "weak" : "strong"}" style="width:${Math.max(3, x.score)}px"></div><b>${x.score}</b></div></td>
        <td class="click" data-act="po-leader-open" data-key="${esc(x.key)}"><b>${esc(x.name)}</b><span class="sub">${esc(x.role)}</span></td><td>${esc(x.store)}</td><td>${esc(x.leads)}</td>
        <td><small>${x.reasons.map(esc).join(" · ")}</small></td><td class="n">${x.in_role_months == null ? "—" : Math.floor(x.in_role_months / 12) + "y " + (x.in_role_months % 12) + "m"}</td>
        <td class="n">${x.band !== "Low" ? `<button class="btn sm" data-act="act-quick" data-title="${esc("Stay conversation with " + x.name)}" data-store="${esc(x.store)}" data-area="Retention" data-detail="${esc(x.reasons.join("; "))}">+ Action</button>` : ""}</td></tr>`).join("")}</tbody></table></div></div>`;
  } else if (tab === "succ") {
    const r = DATA.risk = await API.call("po_risk");
    const sc = r.succession;
    const tone = { "Ready now": "good", "Ready in a year": "warn", "No successor": "bad", "No one in role": "" };
    body = `<div class="kpis">${Object.entries(tone).map(([k, t]) => `<div class="kpi"><span class="kpi-l">${k}</span><span class="kpi-v ${t ? "t-" + t : ""}">${sc.summary[k] || 0}</span><span class="kpi-s"><span>roles</span></span></div>`).join("")}</div>
      <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Succession board</h2><small>Each store's leadership roles and the best people one level below. Hover a cell for the names.</small></div>
      <div class="tbl-wrap"><table class="t succ"><thead><tr><th>Store</th>${sc.roles.map(x => `<th>${esc(x)}</th>`).join("")}</tr></thead><tbody>
      ${sc.stores.map(st => `<tr><td><b>${esc(st)}</b></td>${sc.roles.map(role => { const c = sc.cells.find(x => x.store === st && x.role === role) || {}; return `<td class="succ-c ${tone[c.status] || ""}" title="${esc((c.successors || []).map(x => `${x.name} (${x.ready})`).join(", "))}">
        <span class="chip ${tone[c.status] || ""}">${esc(c.status || "—")}</span><small>${esc((c.holders || []).join(", ") || "role holder not on file")}</small>${(c.successors || []).slice(0, 2).map(x => `<small>→ ${esc(x.name)} · ${esc(x.ready.toLowerCase())}</small>`).join("")}</td>`; }).join("")}</tr>`).join("")}
      </tbody></table></div></div>`;
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
    try { const r = await API.call("po_leader", { key: S.po.leader }); box.innerHTML = `<div class="row" style="justify-content:flex-end;margin-bottom:6px;gap:6px"><button class="btn sm" data-act="br-open" data-emp="${esc(r.emp || "")}">🧠 People Brain</button><button class="btn sm" data-act="note-new" data-subject="${esc(r.name || "")}" data-key="${esc(S.po.leader)}" data-store="${esc(r.store || "")}">✎ Log 1:1</button><button class="btn sm" data-act="l-devpack" data-key="${esc(S.po.leader)}">${ic("learning", 14)}Make development pack</button></div><div class="po-html">${r.html}</div>`; }
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
    <div class="kpis k5">${kpi("Leavers · " + d.window, d.total, d.window_months && d.window_months !== 12 ? `≈ ${d.annualised} a year at this pace` : `${d.all_time} on file`)}${kpi("Voluntary", pct(d.voluntary_pct), `${types.Resignation || 0} resignations`)}
      ${kpi("Turnover rate · yearly", d.rate_annualised == null ? "—" : d.rate_annualised.toFixed(1) + "%", d.headcount ? `${d.rate_leavers} leavers on ${d.headcount.toLocaleString("en-US")} people · ${d.rate_scope}` : "import the Basic Sheet for a rate")}${kpi("Terminations", types.Termination || 0, `${types.Absconding || 0} absconded`)}${kpi("Top reason", `<span class="txt">${esc(d.by_reason.length ? d.by_reason[0][0] : "—")}</span>`, d.by_reason.length ? d.by_reason[0][1] + " leavers" : "")}</div>
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

Object.assign(ACT, CHAT_ACTS, HEALTH_ACTS);
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
const GO_KEYS_FULL = { c: "calendar", w: "brief", h: "home", r: "review", s: "stores", p: "people", b: "brain", t: "talent", a: "attendance", i: "insights", e: "relations", n: "hiring", l: "learning", d: "import", k: "ask", o: "organisation", g: "goals", x: "settings" };
const GO_KEYS = { r: "rv", a: "ask" };
const KEY_OF = Object.fromEntries(Object.entries(GO_KEYS).map(([k, v]) => [v, k]));
let gArmed = 0;
function shortcutHelp() {
  const rows = [["Ctrl K", "Search people, stores and commands"], ["?", "This list"], ["Esc", "Close a window"], ["Alt ←", "Back"], ["Ctrl Z", "Undo the last delete (while its message shows)"]]
    .concat(Object.entries(GO_KEYS).map(([k, v]) => [`G ${k.toUpperCase()}`, "Go to " + (PAGE_TITLE[v] || v)]));
  modal(`<div class="row" style="justify-content:space-between"><h3>Keyboard shortcuts</h3><button class="btn sm" data-act="tour" onclick="this.closest('.modal-bg,.modal') && document.querySelector('[data-act=modal-close]').click()">Take the tour again</button></div><div class="kbgrid">${rows.map(([k, l]) => `<div><span>${k.split(" ").map(x => `<kbd>${esc(x)}</kbd>`).join(" ")}</span><small>${esc(l)}</small></div>`).join("")}</div>
    <div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" data-act="modal-close">Close</button></div>`);
}
document.addEventListener("keydown", e => {
  const typing = /INPUT|TEXTAREA|SELECT/.test((e.target.tagName || "")) || e.target.isContentEditable;
  if (!typing && !e.ctrlKey && !e.metaKey && !e.altKey) {
    if (e.key === "?") { e.preventDefault(); shortcutHelp(); return; }
    if (gArmed > Date.now() - 900 && GO_KEYS[e.key.toLowerCase()]) { e.preventDefault(); gArmed = 0; closeModal && $(".modal") && closeModal(); go(GO_KEYS[e.key.toLowerCase()]); return; }
    if (e.key.toLowerCase() === "g") { gArmed = Date.now(); return; }
  }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && !typing) { const u = [...document.querySelectorAll(".toast button")].find(b => b.textContent === "Undo"); if (u) { e.preventDefault(); u.click(); return; } }
  if (e.altKey && e.key === "ArrowLeft") { e.preventDefault(); ACT.back(); return; }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); const q = $("#q"); if (q) q.focus(); }
  if (e.key === "Escape") { if ($(".modal")) closeModal(); else if ($(".sheet")) closeSheet(); else if (document.body.classList.contains("present")) document.body.classList.remove("present"); }
  if (document.body.classList.contains("present") && ["ArrowDown", "PageDown", "ArrowRight", " "].includes(e.key)) { e.preventDefault(); presentStep(1); }
  if (document.body.classList.contains("present") && ["ArrowUp", "PageUp", "ArrowLeft"].includes(e.key)) { e.preventDefault(); presentStep(-1); }
});
window.addEventListener("resize", () => { clearTimeout(S.rz); S.rz = setTimeout(() => { const f = AFTER[S.page]; if (f && !["ask", "import", "settings", "people", "org"].includes(S.page)) f(); }, 200); });
document.addEventListener("dragover", e => e.preventDefault());
window.addEventListener("mouseup", e => { if (e.button === 3) { e.preventDefault(); ACT.back(); } });
document.addEventListener("drop", e => { e.preventDefault(); if (!window.qt && S.page === "hiring" && S.hire.vid && e.dataTransfer && e.dataTransfer.files.length) { hireAddFiles(e.dataTransfer.files); return; }
  if (!window.qt && e.dataTransfer && e.dataTransfer.files.length && !e.target.closest("#drop")) { if (S.page !== "import") go("import"); uploadFiles(e.dataTransfer.files); } });

/* ============================================================== Hiring: vacancies, CV screening, pipeline, talent bank */
const HBAND = { strong: ["Strong", "good"], possible: ["Possible", "info"], weak: ["Weak", "warn"], no: ["Not suitable", "bad"] };
const HSTAGE = { applied: "Applied", screened: "Screened", interview1: "Interview 1", interview2: "Interview 2", offer: "Offer", joined: "Joined", rejected: "Not selected", withdrawn: "Withdrew" };
S.hire = { tab: "vac", vid: null, blind: false, cand: null, ctab: "assess", q: "", skill: "", city: "", years: "", sel: new Set() };
const HLEVELS = [[1, "Associate"], [2, "Team leader / supervisor"], [3, "Section manager"], [4, "Department head"], [5, "Deputy / assistant SM"], [6, "Store manager"]];
const HEDU = [[0, "Any"], [2, "Matric"], [3, "Intermediate"], [4, "Bachelor's"], [5, "Master's"]];
const hBand = b => `<span class="chip ${(HBAND[b] || ["", ""])[1]}">${esc((HBAND[b] || ["—"])[0])}</span>`;
const hBar = (v, b) => `<div class="hbarw"><div class="hbarv ${b}" style="width:${Math.max(2, Math.min(100, v || 0))}%"></div><b>${v == null ? "—" : Math.round(v)}</b></div>`;
async function filesToB64(fileList) {
  const files = [];
  for (const f of fileList) {
    const bytes = new Uint8Array(await f.arrayBuffer()); let bin = "";
    for (let i = 0; i < bytes.length; i += 32768) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 32768));
    files.push({ name: f.name, b64: btoa(bin) });
  }
  return files;
}
async function hireAddFiles(fileList) {
  toast(`Reading ${fileList.length} CV${fileList.length > 1 ? "s" : ""}…`);
  const r = await call("hire_upload", { files: await filesToB64(fileList), vacancy_id: S.hire.vid });
  hireAfterAdd(r);
}
function hireAfterAdd(r) {
  if (r.cancelled) return;
  const msg = [`${r.added.length} new`, r.updated.length ? `${r.updated.length} updated (same person)` : "", r.failed.length ? `${r.failed.length} could not be read` : ""].filter(Boolean).join(" · ");
  toast("CVs: " + msg, { ms: 7000, err: !r.added.length && !r.updated.length });
  if (r.failed.length) modal(`<h3>Some CVs could not be read</h3>${r.failed.map(f => `<p><b>${esc(f.file)}</b><br><small style="color:var(--muted)">${esc(f.error)}</small></p>`).join("")}<div class="row" style="justify-content:flex-end"><button class="btn primary" data-act="modal-close">OK</button></div>`);
  render();
}

PAGES.hiring = async () => {
  const H = S.hire;
  const tabs = `<div class="seg">${[["vac", "Vacancies"], ["pipe", "Pipeline"], ["bank", "Talent bank"], ["stats", "Hiring analytics"]].map(([k, l]) => `<button data-act="h-tab" data-tab="${k}" aria-pressed="${H.tab === k}">${l}</button>`).join("")}</div>`;
  const head = (title, sub, right = "") => `<div class="ph"><div><h1>${title}</h1><p>${sub}</p></div><div class="row">${right}${tabs}</div></div>`;
  if (H.tab === "vac" && H.vid) return hireVacancy(head);
  if (H.tab === "pipe") return hirePipeline(head);
  if (H.tab === "bank") return hireBank(head);
  if (H.tab === "stats") return hireStats(head);
  const d = DATA.hiring = await API.call("hire_list");
  const card = v => `<button class="hcard" data-act="h-open" data-id="${v.id}"><div class="row" style="justify-content:space-between;gap:8px"><b>${esc(v.title)}</b><span class="chip ${v.status === "open" ? "good" : v.status === "filled" ? "info" : ""}">${esc(v.status)}</span></div>
      <small>${esc([v.store, v.section].filter(Boolean).join(" · ") || "Any store")} · ${v.headcount} post${v.headcount > 1 ? "s" : ""}${v.days_open != null ? ` · open ${v.days_open} day${v.days_open === 1 ? "" : "s"}` : ""}</small>
      <div class="hstats"><span><b>${v.cvs}</b>CVs</span><span><b class="t-good">${v.strong}</b>strong</span><span><b>${v.possible}</b>possible</span><span><b>${v.interview}</b>interview</span><span><b>${v.joined}</b>joined</span></div>
      <div class="hprog"><i style="width:${v.cvs ? Math.round(100 * (v.strong + v.possible) / v.cvs) : 0}%"></i></div></button>`;
  return head("Hiring", `Post a vacancy, drop in CVs and P&O ranks them against the job, with the evidence for every point. ${d.bank.toLocaleString("en-US")} people in the talent bank.`,
      `<button class="btn primary" data-act="h-new">${ic("spark", 15)}New vacancy</button>`) +
    (d.rows.length ? `<div class="hcards stagger">${d.rows.map(card).join("")}</div>`
      : `<div class="panel"><div class="hero"><div class="logo" style="width:64px;height:64px;font-size:26px;border-radius:18px">👤</div><h2>No vacancies yet</h2>
        <p>Create a vacancy from a ready-made role (Associate, Cashier, Team Leader, Section Manager, Department Head, Store Manager) or paste your JD.
        Then drop in CVs, even hundreds at once (PDF, Word or text).</p><div class="row" style="justify-content:center"><button class="btn primary" data-act="h-new">${ic("spark", 15)}Create the first vacancy</button></div></div></div>`);
};

function hireForm(v) {
  const t = DATA.hiring || {};
  const roles = (t.roles || []).map(r => `<option value="${r.key}" ${r.key === v.role ? "selected" : ""}>${esc(r.title)}</option>`).join("");
  const cats = ["", ...(t.categories || [])].map(c => `<option ${c === (v.category || "") ? "selected" : ""} value="${esc(c)}">${esc(c || "Any area")}</option>`).join("");
  const rub = v.rubric || { criteria: [], knockouts: {} };
  const skillsC = rub.criteria.find(c => c.type === "skills") || { items: [] };
  const cityC = rub.criteria.find(c => c.type === "city") || { items: [] };
  const crit = rub.criteria.filter(c => c.type !== "skills" && c.type !== "city").map(c => `<tr><td>${esc(c.label)}</td>
      <td>${c.type === "level" ? `<select class="input sm" data-rc="${c.key}" data-f="target">${HLEVELS.map(([n, l]) => `<option value="${n}" ${+c.target === n ? "selected" : ""}>${l}</option>`).join("")}</select>`
        : c.type === "education" ? `<select class="input sm" data-rc="${c.key}" data-f="target">${HEDU.map(([n, l]) => `<option value="${n}" ${+c.target === n ? "selected" : ""}>${l}</option>`).join("")}</select>`
        : `<input class="input sm" type="number" step="0.5" min="0" data-rc="${c.key}" data-f="target" value="${c.target ?? ""}" style="width:80px"> <small style="color:var(--muted)">${c.type === "team" ? "people" : "years"}</small>`}</td>
      <td><input class="input sm" type="range" min="0" max="40" data-rc="${c.key}" data-f="weight" value="${c.weight}"><span class="wv">${c.weight}</span></td></tr>`).join("");
  return `<h3>${v.id ? "Edit vacancy" : "New vacancy"}</h3><p style="color:var(--muted);margin:0 0 12px">Pick a role to start from: the job description and the scoring rubric fill in, and you can change anything.</p>
    <div class="hform">
      <label class="dx-l">Job title<input class="input" id="hv-title" value="${esc(v.title || "")}" placeholder="e.g. Section Manager · Fresh Food"></label>
      <label class="dx-l">Start from role<select class="input" id="hv-role">${roles}</select></label>
      <label class="dx-l">Area<select class="input" id="hv-cat">${cats}</select></label>
      <label class="dx-l">Store<input class="input" id="hv-store" list="hv-stores" value="${esc(v.store || "")}"><datalist id="hv-stores">${(t.stores || []).map(s => `<option value="${esc(s)}">`).join("")}</datalist></label>
      <label class="dx-l">Section<input class="input" id="hv-section" value="${esc(v.section || "")}" placeholder="e.g. Bakery"></label>
      <label class="dx-l">Posts<input class="input" id="hv-head" type="number" min="1" value="${v.headcount || 1}"></label>
      <label class="dx-l">Hiring manager<input class="input" id="hv-mgr" value="${esc(v.manager || "")}"></label>
      <label class="dx-l">Fill by<input class="input" id="hv-date" type="date" value="${esc(v.target_date || "")}"></label>
      ${v.id ? `<label class="dx-l">Status<select class="input" id="hv-status">${["open", "on hold", "filled", "closed"].map(s => `<option ${s === v.status ? "selected" : ""}>${s}</option>`).join("")}</select></label>` : ""}
    </div>
    <div class="row" style="margin:12px 0 6px;justify-content:space-between"><b>Job description</b><span class="row"><button class="btn sm" data-act="h-draft">Fill from role</button><button class="btn sm" data-act="h-aijd">${ic("spark", 13)}Write with AI</button></span></div>
    <textarea class="input" id="hv-jd" rows="9" style="width:100%;font-size:13px">${esc(v.jd || "")}</textarea>
    <details class="hrub" open><summary><b>How CVs are scored</b> <small style="color:var(--muted)">targets and weights; age, gender, marital status and religion are never scored</small></summary>
      <table class="t"><thead><tr><th>Criterion</th><th>Asks for</th><th>Weight</th></tr></thead><tbody>${crit}</tbody></table>
      <div style="margin-top:10px"><div class="row" style="gap:8px"><b style="font-size:12.5px">Skills to look for</b><small style="color:var(--muted)">weight</small>
        <input class="input sm" type="number" min="0" max="40" data-rc="skills" data-f="weight" value="${skillsC.weight || 0}" style="width:64px"></div>
        <div class="hskills">${(t.skills || []).map(s => `<label class="hsk"><input type="checkbox" data-hskill value="${esc(s)}" ${skillsC.items.includes(s) ? "checked" : ""}><span>${esc(s)}</span></label>`).join("")}</div></div>
      <div class="hform" style="margin-top:8px">
        <label class="dx-l">Prefer candidates in (cities, comma separated)<input class="input" id="hv-cities" value="${esc((cityC.items || []).join(", "))}" placeholder="e.g. Lahore"></label>
        <label class="dx-l">City weight<input class="input" type="number" min="0" max="40" data-rc="city" data-f="weight" value="${cityC.weight || 0}"></label>
        <label class="dx-l">Must have at least (years)<input class="input" id="hv-ko-years" type="number" min="0" step="0.5" value="${rub.knockouts.min_years || 0}"></label>
        <label class="dx-l">Only these cities (knock-out)<input class="input" id="hv-ko-cities" value="${esc((rub.knockouts.cities || []).join(", "))}"></label>
      </div></details>
    <div class="row" style="justify-content:flex-end;margin-top:14px">${v.id ? `<button class="btn ghost danger" data-act="h-del" data-id="${v.id}">Delete</button><span class="spacer"></span>` : ""}<button class="btn" data-act="modal-close">Cancel</button><button class="btn primary" data-act="h-save" data-id="${v.id || ""}">${v.id ? "Save and re-score" : "Create vacancy"}</button></div>`;
}
function hireRubricFromForm(base) {
  const rub = JSON.parse(JSON.stringify(base || { criteria: [], knockouts: {} }));
  $$("[data-rc]").forEach(i => { const c = rub.criteria.find(x => x.key === i.dataset.rc); if (c && i.value !== "") c[i.dataset.f] = +i.value; });
  const sk = rub.criteria.find(c => c.type === "skills"); if (sk) sk.items = $$("[data-hskill]").filter(i => i.checked).map(i => i.value);
  const ct = rub.criteria.find(c => c.type === "city"); if (ct) ct.items = $("#hv-cities").value.split(",").map(s => s.trim()).filter(Boolean);
  rub.knockouts = { ...(rub.knockouts || {}), min_years: +$("#hv-ko-years").value || 0, cities: $("#hv-ko-cities").value.split(",").map(s => s.trim()).filter(Boolean), must_skills: (rub.knockouts || {}).must_skills || [] };
  return rub;
}
function hireOpenForm(v) {
  S.hire.form = v;
  const m = modal(hireForm(v)); m.classList.add("wide");
  m.addEventListener("input", e => { if (e.target.type === "range") { const w = e.target.parentElement.querySelector(".wv"); if (w) w.textContent = e.target.value; } });
  const role = $("#hv-role", m); role.onchange = () => ACT["h-draft"]();
}

/* ============================================================== 2.6 Internal talent first */
function intCard(c, i) {
  const bf = c.backfill || {};
  const risk = { Low: "good", Medium: "warn", High: "bad" }[bf.risk] || "";
  const ring = Math.round(c.recommend);
  const steps = (bf.steps || []).map(s => `<div class="cstep ${s.how}"><small>${esc(s.seat)}</small><b>${s.by ? esc(s.by) : "Hire from outside"}</b>${s.by ? `<span class="chip ${s.ready === "Ready now" ? "good" : s.ready === "Ready in a year" ? "warn" : "bad"}">${esc(s.ready || "")}</span>` : `<span class="chip">external</span>`}</div>`).join(`<span class="carrow">→</span>`);
  return `<div class="icand ${i === 0 ? "top" : ""}">
    <div class="icand-h"><div class="iring" style="--p:${ring}"><b>${ring}</b><small>/100</small></div>
      <div style="flex:1;min-width:0"><div class="row" style="gap:8px;flex-wrap:wrap"><b class="iname">${esc(c.name)}</b><span class="chip ${c.move === "Promotion" ? "good" : "info"}">${esc(c.move)}</span>${i === 0 ? `<span class="chip gold">Best option</span>` : ""}${c.flight_risk === "High" ? `<span class="chip warn" title="Flight risk">at risk of leaving</span>` : ""}</div>
        <span class="sub">${esc(c.designation)} · ${esc(c.leads || "")} · ${esc(c.store)}${c.emp ? ` · #${esc(c.emp)}` : ""}</span></div>
      <div class="row" style="gap:6px">${c.in_pipeline ? `<span class="chip good">In the pipeline</span>` : `<button class="btn sm primary" data-act="int-add" data-key="${esc(c.key)}">+ Shortlist</button>`}<button class="btn sm ghost" data-act="int-more" data-i="${i}">Profile</button></div></div>
    <div class="icand-b"><div class="iparts">${c.parts.map(p => `<div><small>${esc(p.label)} <i>${p.weight}%</i></small><div class="ibar"><i style="width:${p.score}%"></i></div><b>${p.score}</b></div>`).join("")}</div>
      <div class="iwhy">${c.why.map(w => `<div class="g">✓ ${esc(w)}</div>`).join("")}${c.watch.map(w => `<div class="w">! ${esc(w)}</div>`).join("")}</div></div>
    <div class="iback"><div class="row" style="justify-content:space-between;gap:8px"><small><b>If ${esc(c.name.split(" ")[0])} moves:</b> ${esc(bf.summary || "")}</small><span class="chip ${risk}">${esc(bf.risk || "")} risk to ${esc(c.store)}</span></div>
      ${steps ? `<div class="chainv">${steps}</div>` : ""}</div></div>`;
}
async function drawInternal() {
  const box = $("#h-internal"); if (!box) return;
  try {
    const r = DATA.hint = await API.call("hire_internal", { vacancy_id: S.hire.vid });
    const vcls = { internal: "good", internal_backfill: "gold", develop: "warn", external: "info" }[r.verdict.decision] || "";
    box.innerHTML = `<div class="iverdict ${vcls}"><div class="iv-ic">${r.verdict.decision === "external" ? "🌐" : r.verdict.decision === "develop" ? "🌱" : "🏆"}</div><div><small>P&O recommends</small><h3>${esc(r.verdict.title)}</h3><p>${esc(r.verdict.text)}</p></div>
        <div class="iv-act">${r.verdict.decision !== "internal" ? `<button class="btn primary" data-act="h-vtab" data-t="external">Start external search →</button>` : `<button class="btn" data-act="h-vtab" data-t="external">Also screen outside CVs</button>`}</div></div>
      ${(r.notes || []).map(n => `<div class="banner">ℹ ${esc(n)}</div>`).join("")}
      <div class="row" style="justify-content:space-between;margin:10px 0 6px"><small style="color:var(--muted)">${r.candidates.length} internal option${r.candidates.length === 1 ? "" : "s"} from ${r.pool.leaders} leaders${r.pool.staff ? ` and ${r.pool.staff} staff` : ""} · ${esc(r.method)}</small></div>
      <div class="icands">${r.candidates.map(intCard).join("") || `<div class="empty">No internal candidates at the right level.</div>`}</div>
      <div class="panel" style="margin-top:14px"><div class="phd"><h2>Outside the company</h2><small>${r.external_pipeline} CVs screened for this vacancy</small></div>
        ${r.bank.length ? `<div class="hint-list">${r.bank.map(b => `<div><b>${esc(b.name)}</b><small>${esc(b.city || "")} · past applicant · ${b.score}/100 · ${esc(b.band_label)}</small></div>`).join("")}</div>` : `<small style="color:var(--muted)">No strong past applicants in the talent bank.</small>`}
        <div class="row" style="margin-top:8px"><button class="btn" data-act="h-vtab" data-t="external">Screen CVs</button><button class="btn ghost" data-act="h-matchbank">Add talent bank matches</button></div></div>`;
  } catch (e) { box.innerHTML = `<div class="errbox">${esc(e.message)}</div>`; }
}
function intProfile(c) {
  const comp = Object.entries(c.components || {});
  modal(`<div class="row" style="gap:14px;align-items:center"><div class="iring" style="--p:${Math.round(c.recommend)}"><b>${Math.round(c.recommend)}</b><small>/100</small></div><div><h3 style="margin:0">${esc(c.name)}</h3><small style="color:var(--muted)">${esc(c.designation)} · ${esc(c.leads || "")} · ${esc(c.store)}</small></div></div>
    <div class="grid g2" style="margin-top:12px"><div><h4>Profile</h4><table class="t"><tbody>
      ${[["Employee number", c.emp], ["Store", c.store], ["City", c.city], ["Leads", c.leads], ["Grade", c.grade], ["Reports to", c.manager], ["Joined", c.joined ? fmtDate(c.joined) : ""],
         ["With Carrefour", c.service_months != null ? `${Math.floor(c.service_months / 12)} yr ${c.service_months % 12} mo` : ""], ["In this role since", c.role_since ? fmtDate(c.role_since) : ""],
         ["Leader index", c.index != null ? (c.index / 10).toFixed(1) + " / 10" : ""], ["Flight risk", c.flight_risk || ""], ["1:1 notes", c.notes || ""]].filter(x => x[1]).map(([k, v]) => `<tr><td><small>${k}</small></td><td><b>${esc(v)}</b></td></tr>`).join("")}</tbody></table></div>
      <div><h4>Ratings</h4>${c.ratings.length ? `<table class="t"><tbody>${c.ratings.map(r => `<tr><td>${esc(r.cycle || "")}</td><td><b>${r.rating ?? "—"}</b></td><td><small>${esc(r.label || "")}</small></td></tr>`).join("")}</tbody></table>` : `<small style="color:var(--muted)">No ratings on file</small>`}
        ${comp.length ? `<h4>Results of their area (/10)</h4><div class="iparts">${comp.map(([k, v]) => `<div><small>${esc(k.replace("_", " "))}</small><div class="ibar"><i style="width:${v * 10}%"></i></div><b>${v}</b></div>`).join("")}</div>` : ""}
        ${c.training.length ? `<h4>Training</h4>${c.training.map(t => `<div><small>${esc(t)}</small></div>`).join("")}` : ""}</div></div>
    <div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" data-act="modal-close">Close</button>${c.in_pipeline ? "" : `<button class="btn primary" data-act="int-add" data-key="${esc(c.key)}">+ Shortlist</button>`}</div>`).classList.add("wide");
}
const INT_ACTS = {
  "h-vtab": b => { S.hire.vtab = b.dataset.t; render(); },
  "int-add": async b => { b.disabled = true; await call("hire_internal_add", { vacancy_id: S.hire.vid, key: b.dataset.key }); closeModal(); toast("Added to the pipeline as an internal candidate"); drawInternal(); },
  "int-more": b => intProfile(DATA.hint.candidates[+b.dataset.i]),
};

/* ============================================================== 2.7 People Brain */
S.brain = S.brain || { tab: "people", emp: null, store: "", q: "", level: "", left: false, gstore: "" };
const LVL_COLOR = ["#8C8279", "#7A9E7E", "#3A7CA5", "#6C5CE7", "#C2410C", "#B45309", "#9A3412"];
const yrs = m => m == null ? "—" : `${Math.floor(m / 12)}y ${m % 12}m`;
PAGES.brain = async () => {
  const B = S.brain;
  const tabs = `<div class="seg">${[["people", "People"], ["graph", "Graph"], ["corrections", "Corrections"]].map(([k, l]) => `<button data-act="br-tab" data-t="${k}" aria-pressed="${B.tab === k}">${l}</button>`).join("")}</div>`;
  const head = `<div class="ph"><div><h1>People Brain</h1><p>Every person, store and section in one place, linked together, with the source of every fact. Corrections you make here win over the imported files.</p></div>${tabs}</div>`;
  if (B.tab === "graph") return head + `<div class="panel brg"><div class="row" style="gap:8px;margin-bottom:8px"><select class="input sm" id="brg-store"><option value="">All stores</option>${(DATA.brs?.stores || []).map(s => `<option ${s === B.gstore ? "selected" : ""}>${esc(s)}</option>`).join("")}</select>
      <small style="color:var(--muted)">Drag to move · scroll to zoom · click a person to open their page</small><span class="spacer"></span><span class="glegend"><i style="background:#B8860B"></i>Store <i style="background:#0F8B8D"></i>Section <i style="background:#C2410C"></i>Leader <i style="background:#3A7CA5"></i>Team</span></div>
      <canvas id="brg" height="640"></canvas><div class="gtip" id="gtip" hidden></div></div>`;
  if (B.tab === "corrections") {
    const c = await API.call("corrections");
    return head + `<div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Corrections</h2><small>What P&O changed and why · they win over every import until undone</small></div><div class="tbl-wrap"><table class="t"><thead><tr><th>When</th><th>Person</th><th>What</th><th>Was</th><th>Now</th><th>How</th><th></th></tr></thead><tbody>
      ${c.rows.map(r => `<tr style="${r.active ? "" : "opacity:.45"}"><td class="nw">${esc(r.created_at.slice(0, 16).replace("T", " "))}</td><td><button class="lnk" data-act="br-open" data-emp="${esc(r.emp)}">${esc(r.name || r.emp)}</button></td><td>${esc(r.label)}</td><td>${esc(r.old_value ?? "—")}</td><td><b>${esc(r.value)}</b></td><td><span class="chip">${esc(r.source === "chat" ? "Ask P&O AI" : "By hand")}</span>${r.note ? `<span class="sub">${esc(r.note)}</span>` : ""}</td>
        <td class="n">${r.active ? `<button class="btn sm ghost" data-act="br-undo" data-id="${r.id}">Undo</button>` : `<small>undone</small>`}</td></tr>`).join("") || `<tr><td colspan="7"><div class="empty">No corrections yet. Fix anything from a person's page (✎) or just tell Ask P&O AI.</div></td></tr>`}</tbody></table></div></div>`;
  }
  const lst = DATA.brs = await API.call("brain_search", { q: B.q, store: B.store, level: B.level === "" ? null : +B.level, include_left: B.left });
  if (!B.emp && lst.rows.length) B.emp = lst.rows[0].emp;
  const list = `<div class="brlist"><input class="input" id="br-q" placeholder="Search name, number, role, store…" value="${esc(B.q)}">
      <div class="row" style="gap:6px"><select class="input sm" id="br-store"><option value="">All stores</option>${lst.stores.map(s => `<option ${s === B.store ? "selected" : ""}>${esc(s)}</option>`).join("")}</select>
      <select class="input sm" id="br-level"><option value="">Everyone</option><option value="2" ${B.level === "2" ? "selected" : ""}>Leaders</option><option value="4" ${B.level === "4" ? "selected" : ""}>Dept head +</option></select></div>
      <label class="switch-l"><input type="checkbox" id="br-left" ${B.left ? "checked" : ""}> Include people who left</label>
      <small style="color:var(--muted)">${lst.total.toLocaleString("en-US")} of ${lst.people.toLocaleString("en-US")} people</small>
      <div class="brl">${lst.rows.map(r => `<button class="bri ${r.emp === B.emp ? "on" : ""} ${r.left ? "left" : ""}" data-act="br-open" data-emp="${esc(r.emp)}"><span class="av sm" style="--c:${LVL_COLOR[Math.min(6, r.level || 0)]}">${esc(initials(r.name))}</span><span><b>${esc(r.name)}</b><small>${esc(r.designation || "—")} · ${esc(r.store || "")}</small></span>${r.index != null ? `<i class="idx">${(r.index / 10).toFixed(1)}</i>` : ""}</button>`).join("") || `<div class="empty">Nobody found.</div>`}</div></div>`;
  return head + `<div class="brwrap">${list}<div id="br-page"><div class="skel" style="height:260px"></div></div></div>`;
};
async function drawBrainPerson() {
  const box = $("#br-page"); if (!box || !S.brain.emp) { if (box) box.innerHTML = `<div class="empty">Choose a person.</div>`; return; }
  let p;
  try { p = DATA.brp = await API.call("brain_person", { emp: S.brain.emp }); } catch (e) { box.innerHTML = `<div class="errbox">${esc(e.message)}</div>`; return; }
  const k = (l, v, s, cls = "") => `<div class="kpi"><span class="kpi-l">${esc(l)}</span><span class="kpi-v ${cls}">${v}</span><span class="kpi-s"><span>${esc(s)}</span></span></div>`;
  const rated = p.ratings.filter(r => r.rating != null), last = rated[rated.length - 1];
  const ins = p.insights || {};
  const tlIcon = { join: "🎉", role: "🪪", rating: "⭐", left: "🚪", note: "💬", training: "🎓", case: "⚖️", letter: "✉️" };
  box.innerHTML = `<div class="brhead"><div class="av lg" style="--c:${LVL_COLOR[Math.min(6, p.level || 0)]}">${esc(initials(p.name))}</div>
      <div style="flex:1;min-width:0"><h2>${esc(p.name)}</h2><div class="sub">${esc(p.designation || "—")}${p.leads ? ` · leads ${esc(p.leads)}` : ""} · <button class="lnk" data-act="br-store" data-s="${esc(p.store)}">${esc(p.store || "—")}</button> · #${esc(p.emp)}</div>
        <div class="row" style="gap:6px;margin-top:6px;flex-wrap:wrap">${p.left ? `<span class="chip bad">Left ${esc(p.left.date || "")}</span>` : `<span class="chip good">Active</span>`}${p.acting ? `<span class="chip warn">Acting in a bigger role</span>` : ""}${ins.flight_risk ? `<span class="chip ${ins.flight_risk === "High" ? "bad" : ins.flight_risk === "Medium" ? "warn" : "good"}">Flight risk: ${esc(ins.flight_risk)}</span>` : ""}${p.corrections.some(c => c.active) ? `<span class="chip gold">✎ corrected</span>` : ""}${p.sources.map(s => `<span class="chip">${esc(s)}</span>`).join("")}</div></div>
      <div class="row" style="gap:6px;align-self:start"><button class="btn sm" data-act="note-new" data-subject="${esc(p.name)}" data-key="${esc(p.emp)}" data-store="${esc(p.store || "")}">✎ Log 1:1</button><button class="btn sm" data-act="lt-new" data-k="experience" data-emp="${esc(p.emp)}">✉️ Letter</button><button class="btn sm primary" data-act="br-export">${ic("export", 14)}Profile sheet</button></div></div>
    <div class="kpis k5">${k("With Carrefour", yrs(p.service_months), p.facts.find(f => f.field === "joining_date") ? "since " + fmtDate(p.facts.find(f => f.field === "joining_date").value) : "")}${k("In current role", yrs(p.in_role_months), p.facts.find(f => f.field === "role_since") ? "since " + fmtDate(p.facts.find(f => f.field === "role_since").value) : "")}
      ${k("Leader index", p.index != null ? (p.index / 10).toFixed(1) + "<small>/10</small>" : "—", p.index_percentile != null ? `better than ${p.index_percentile}% of ${p.peers} peers` : "", p.index == null ? "" : p.index >= 70 ? "t-good" : p.index < 50 ? "t-bad" : "")}
      ${k(last ? `${last.cycle} rating` : "Rating", last ? last.rating + "<small>/5</small>" : "—", last ? last.label || "" : "no rating on file", last ? (last.rating >= 4 ? "t-good" : last.rating <= 2 ? "t-bad" : "") : "")}
      ${k("Attendance", p.attendance && p.attendance.presence != null ? Math.round(p.attendance.presence) + "%" : "—", p.attendance ? `${p.attendance.absent || 0} absent · ${p.attendance.fixes || 0} punches to fix` : "no attendance imported")}</div>
    <div class="grid g2"><div class="panel"><div class="phd"><h2>Profile</h2><small>Where each fact comes from · ✎ to correct</small></div>
        <table class="t facts"><tbody>${p.facts.map(f => `<tr><td><small>${esc(f.label)}</small></td><td><b>${f.field.match(/date|since/) ? fmtDate(f.value) : f.field === "manager_name" && p.manager_emp ? `<button class="lnk" data-act="br-open" data-emp="${esc(p.manager_emp)}">${esc(f.value)}</button>` : esc(f.value)}</b></td>
          <td><span class="src ${f.corrected ? "corr" : ""}">${esc(f.source)}</span></td><td class="n"><button class="btn sm ghost" data-act="br-fix" data-f="${esc(f.field)}" title="Correct">✎</button></td></tr>`).join("")}
          <tr><td colspan="4"><button class="btn sm ghost" data-act="br-fix" data-f="">+ Correct something else (status, rating, leaving date…)</button></td></tr></tbody></table></div>
      <div class="panel"><div class="phd"><h2>Insights</h2><small>Worked out from the data</small></div>
        ${ins.strengths?.length ? `<h4 class="ih good">Strengths</h4>${ins.strengths.map(x => `<div class="il good">✓ ${esc(x)}</div>`).join("")}` : ""}
        ${ins.risks?.length ? `<h4 class="ih bad">Watch-outs</h4>${ins.risks.map(x => `<div class="il bad">! ${esc(x)}</div>`).join("")}` : ""}
        ${ins.next_steps?.length ? `<h4 class="ih">Next steps</h4>${ins.next_steps.map(x => `<div class="il">→ ${esc(x)}</div>`).join("")}` : ""}
        ${!ins.strengths?.length && !ins.risks?.length ? `<div class="empty">Not enough data for insights yet.</div>` : ""}</div></div>
    ${rated.length || Object.keys(p.components).length ? `<div class="grid g2">${rated.length ? `<div class="panel"><div class="phd"><h2>Ratings by year</h2></div><div id="br-rat"></div></div>` : ""}${Object.keys(p.components).length ? `<div class="panel"><div class="phd"><h2>Results of their area</h2><small>out of 10 · ${esc(p.leads || "")}</small></div><div id="br-comp"></div></div>` : ""}</div>` : ""}
    <div class="grid g2"><div class="panel"><div class="phd"><h2>Timeline</h2><small>${p.timeline.length} event${p.timeline.length === 1 ? "" : "s"}</small></div><div class="tline">${p.timeline.slice().reverse().map(t => `<div class="tl ${t.kind}"><span class="tl-ic">${tlIcon[t.kind] || "•"}</span><div><small>${t.date ? fmtDate(String(t.date).slice(0, 10)) : ""}</small><div>${esc(t.what)}</div></div></div>`).join("") || `<div class="empty">No events yet.</div>`}</div></div>
      <div class="panel"><div class="phd"><h2>Connections</h2></div>
        ${p.manager ? `<h4 class="ih">Reports to</h4><div class="chips">${p.manager_emp ? `<button class="pchip" data-act="br-open" data-emp="${esc(p.manager_emp)}">${esc(p.manager)}</button>` : `<span class="pchip">${esc(p.manager)}</span>`}</div>` : ""}
        ${p.reports.length ? `<h4 class="ih">Direct reports (${p.reports.length})</h4><div class="chips">${p.reports.map(r => `<button class="pchip" data-act="br-open" data-emp="${esc(r.emp)}" title="${esc(r.designation)}">${esc(r.name)}</button>`).join("")}</div>` : ""}
        ${p.team.length ? `<h4 class="ih">Same section, same store</h4><div class="chips">${p.team.map(r => `<button class="pchip" data-act="br-open" data-emp="${esc(r.emp)}">${esc(r.name)}</button>`).join("")}</div>` : ""}
        <h4 class="ih">Store</h4><div class="chips"><button class="pchip store" data-act="br-store" data-s="${esc(p.store)}">🏬 ${esc(p.store || "—")}</button>${p.section ? `<span class="pchip sec">${esc(p.section)}</span>` : ""}</div>
        ${[["training", "Training", t => `${esc(t.title)} · ${esc(t.status)}`], ["goals", "Goals", g => `${esc(g.title)} · ${g.current ?? "—"} / ${g.target ?? "—"}`], ["actions", "Actions", a => `${esc(a.title)} · ${esc(a.status)}`], ["cases", "Employee relations", c => `${esc(c.kind)}: ${esc(c.category)} · ${esc(c.outcome || c.stage)}`], ["hiring", "Internal applications", h => `${esc(h.title)} · ${esc(h.stage)}`]].filter(([key]) => (p[key] || []).length).map(([key, l, f]) => `<h4 class="ih">${l}</h4>${p[key].map(x => `<div class="il">${f(x)}</div>`).join("")}`).join("")}</div></div>
    ${p.corrections.length ? `<div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Corrections for ${esc(p.name.split(" ")[0])}</h2></div><div class="tbl-wrap"><table class="t"><tbody>${p.corrections.map(c => `<tr style="${c.active ? "" : "opacity:.45"}"><td class="nw">${esc(c.created_at.slice(0, 10))}</td><td>${esc(c.label)}</td><td>${esc(c.old_value ?? "—")} → <b>${esc(c.value)}</b></td><td><small>${esc(c.note || "")}</small></td><td class="n">${c.active ? `<button class="btn sm ghost" data-act="br-undo" data-id="${c.id}">Undo</button>` : "undone"}</td></tr>`).join("")}</tbody></table></div></div>` : ""}`;
  if ($("#br-rat")) Charts.line($("#br-rat"), { labels: rated.map(r => String(r.cycle)), series: [{ name: "Rating", values: rated.map(r => r.rating) }], height: 190 });
  const cn = { sales: "Sales vs budget", productivity: "Productivity", shrink: "Shrinkage", stock_days: "Stock days", rating: "Rating", retention: "Keeping people", nps: "NPS" };
  const sc = v => v >= 7 ? "#16A34A" : v >= 5 ? "#F59E0B" : "#DC2626";
  if ($("#br-comp")) Charts.hbar($("#br-comp"), { labels: Object.keys(p.components).map(x => cn[x] || x), values: Object.values(p.components), max: 10, fmt: "score", colors: Object.values(p.components).map(sc), ref: 7 });
}
async function drawBrainStore(store) {
  const box = $("#br-page"); if (!box) return;
  const d = await API.call("brain_store", { store });
  const c = d.card || {};
  const k = (l, v, s, cls = "") => `<div class="kpi"><span class="kpi-l">${esc(l)}</span><span class="kpi-v ${cls}">${v}</span><span class="kpi-s"><span>${esc(s)}</span></span></div>`;
  box.innerHTML = `<div class="brhead"><div class="av lg" style="--c:#B8860B">🏬</div><div style="flex:1"><h2>${esc(store)}</h2><div class="sub">${esc(d.format || "")} · ${esc(d.city || "")} · ${d.people.length} people known</div></div></div>
    <div class="kpis k5">${k("Sales vs budget", c.sales_vs_budget_pct != null ? Math.round(c.sales_vs_budget_pct) + "%" : "—", c.growth_pct != null ? `${c.growth_pct > 0 ? "+" : ""}${c.growth_pct}% vs LY` : "", c.sales_vs_budget_pct >= 100 ? "t-good" : c.sales_vs_budget_pct < 95 ? "t-bad" : "")}${k("Productivity vs target", c.productivity_vs_target_pct != null ? (c.productivity_vs_target_pct > 0 ? "+" : "") + Math.round(c.productivity_vs_target_pct) + "%" : "—", "")}${k("Leaders", c.leaders ?? "—", c.avg_leader_score != null ? `avg index ${(c.avg_leader_score / 10).toFixed(1)}` : "")}${k("Leavers", d.leavers.length, "on record")}${k("Open vacancies", d.vacancies.length, "")}</div>
    <div class="secgrid">${Object.entries(d.sections).map(([sec, ppl]) => `<div class="panel secc"><div class="phd"><h2>${esc(sec)}</h2><small>${ppl.length}</small></div><div class="chips">${ppl.map(r => `<button class="pchip" data-act="br-open" data-emp="${esc(r.emp)}" style="--c:${LVL_COLOR[Math.min(6, r.level || 0)]}"><i class="dot"></i>${esc(r.name)}<small>${esc(r.designation)}</small></button>`).join("")}</div></div>`).join("")}</div>`;
}
function drawBrainGraph() {
  const cv = $("#brg"); if (!cv) return;
  API.call("brain_graph", { store: S.brain.gstore }).then(g => {
    const W = cv.width = cv.clientWidth * devicePixelRatio, H = cv.height = 640 * devicePixelRatio; cv.style.height = "640px";
    const ctx = cv.getContext("2d"), dpr = devicePixelRatio;
    const col = n => n.kind === "store" ? "#B8860B" : n.kind === "section" ? "#0F8B8D" : (n.level || 0) >= 3 ? "#C2410C" : "#3A7CA5";
    const rad = n => (n.kind === "store" ? 16 : n.kind === "section" ? 8 : 5 + Math.min(5, n.level || 0)) * dpr;
    const storesL = g.nodes.filter(n => n.kind === "store"), home = {};
    storesL.forEach((n, i) => { const a = i / Math.max(1, storesL.length) * Math.PI * 2; home[n.id] = { x: W / 2 + Math.cos(a) * W * 0.32, y: H / 2 + Math.sin(a) * H * 0.34 }; });
    const parent = {}; g.edges.forEach(e => { if (e.kind === "in") parent[e.a] = e.b; if (e.kind === "works") parent[e.a] = e.b; });
    const anchor = id => { let p = id, k = 0; while (parent[p] && k++ < 3) p = parent[p]; return home[p] || { x: W / 2, y: H / 2 }; };
    const N = g.nodes.map((n, i) => { const h = n.kind === "store" ? home[n.id] : anchor(n.id); return { ...n, hx: h.x, hy: h.y, x: h.x + Math.cos(i * 2.4) * (30 + i % 60) * dpr, y: h.y + Math.sin(i * 2.4) * (30 + i % 60) * dpr, vx: 0, vy: 0 }; });
    const idx = Object.fromEntries(N.map((n, i) => [n.id, i]));
    const E = g.edges.map(e => [idx[e.a], idx[e.b], e.kind]).filter(e => e[0] != null && e[1] != null);
    let view = { s: 1, x: 0, y: 0 }, drag = null, hover = null, tick = 0;
    function step() {
      for (let i = 0; i < N.length; i++) for (let j = i + 1; j < N.length; j++) {
        const a = N[i], b = N[j]; let dx = a.x - b.x, dy = a.y - b.y; const d2 = dx * dx + dy * dy + 0.01;
        if (d2 > 250000 * dpr * dpr) continue; const f = 900 * dpr * dpr / d2; dx *= f / Math.sqrt(d2); dy *= f / Math.sqrt(d2); a.vx += dx; a.vy += dy; b.vx -= dx; b.vy -= dy; }
      for (const [a, b, k] of E) { const A = N[a], Bn = N[b]; const dx = Bn.x - A.x, dy = Bn.y - A.y, d = Math.sqrt(dx * dx + dy * dy) + 0.01; const L = (k === "in" ? 120 : k === "reports" ? 70 : 50) * dpr; const f = (d - L) * 0.02; A.vx += dx / d * f; A.vy += dy / d * f; Bn.vx -= dx / d * f; Bn.vy -= dy / d * f; }
      for (const n of N) { const pull = n.kind === "store" ? 0.02 : 0.004; n.vx += (n.hx - n.x) * pull; n.vy += (n.hy - n.y) * pull; if (n !== drag) { n.x += n.vx * 0.5; n.y += n.vy * 0.5; } n.vx *= 0.6; n.vy *= 0.6; }
    }
    function draw() {
      ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, W, H);
      ctx.setTransform(view.s, 0, 0, view.s, view.x, view.y);
      for (const [a, b, k] of E) { ctx.strokeStyle = k === "reports" ? "rgba(194,65,12,.45)" : "rgba(120,110,100,.25)"; ctx.lineWidth = (k === "reports" ? 1.4 : 1) * dpr; ctx.beginPath(); ctx.moveTo(N[a].x, N[a].y); ctx.lineTo(N[b].x, N[b].y); ctx.stroke(); }
      for (const n of N) { ctx.beginPath(); ctx.arc(n.x, n.y, rad(n), 0, 7); ctx.fillStyle = col(n); ctx.globalAlpha = hover && hover !== n ? 0.55 : 1; ctx.fill(); ctx.globalAlpha = 1;
        if (n.kind === "store" || n === hover || (n.kind === "section" && view.s > 1.3) || view.s > 2) { ctx.font = `${n.kind === "store" ? "700 " : ""}${(n.kind === "store" ? 13 : 10.5) * dpr}px Inter, Segoe UI, sans-serif`; ctx.fillStyle = getComputedStyle(document.body).getPropertyValue("--ink") || "#222"; ctx.fillText(n.label, n.x + rad(n) + 3 * dpr, n.y + 4 * dpr); } }
    }
    function loop() { if (!document.body.contains(cv)) return; if (tick++ < 320 || drag) step(); draw(); requestAnimationFrame(loop); }
    const pt = e => { const r = cv.getBoundingClientRect(); return { x: ((e.clientX - r.left) * dpr - view.x) / view.s, y: ((e.clientY - r.top) * dpr - view.y) / view.s }; };
    const hit = q => N.find(n => (n.x - q.x) ** 2 + (n.y - q.y) ** 2 < (rad(n) + 4 * dpr) ** 2);
    let pan = null, moved = false;
    cv.onmousedown = e => { const q = pt(e); drag = hit(q); moved = false; if (!drag) pan = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y }; };
    cv.onmousemove = e => { const q = pt(e); if (drag) { drag.x = q.x; drag.y = q.y; moved = true; tick = 200; } else if (pan) { view.x = pan.vx + (e.clientX - pan.x) * dpr; view.y = pan.vy + (e.clientY - pan.y) * dpr; moved = true; }
      const h = hit(q); hover = h || null; const tip = $("#gtip"); if (h && tip) { tip.hidden = false; tip.style.left = e.offsetX + 14 + "px"; tip.style.top = e.offsetY + 10 + "px"; tip.innerHTML = `<b>${esc(h.label)}</b>${h.role ? `<br><small>${esc(h.role)}${h.index != null ? " · index " + (h.index / 10).toFixed(1) : ""}</small>` : `<br><small>${h.kind}</small>`}`; } else if (tip) tip.hidden = true; cv.style.cursor = h ? "pointer" : "grab"; };
    cv.onmouseup = () => { if (drag && !moved && drag.kind === "person") { S.brain.tab = "people"; S.brain.emp = drag.emp; render(); } else if (drag && !moved && drag.kind === "store") { S.brain.gstore = drag.label; render(); } drag = null; pan = null; };
    cv.onwheel = e => { e.preventDefault(); const f = e.deltaY < 0 ? 1.15 : 1 / 1.15; const r = cv.getBoundingClientRect(); const mx = (e.clientX - r.left) * dpr, my = (e.clientY - r.top) * dpr; view.x = mx - (mx - view.x) * f; view.y = my - (my - view.y) * f; view.s *= f; };
    loop();
  });
}
function brainFix(field) {
  const p = DATA.brp, F = { designation: "Designation", store: "Store", section: "Section", department: "Department", manager_name: "Reports to", grade: "Grade", joining_date: "Joining date", role_since: "In current role since", status: "Employment status", left_on: "Leaving date", rating: "Performance rating", employee_name: "Name" };
  const cur = (p.facts.find(f => f.field === field) || {}).value;
  const m = modal(`<h3>Correct ${esc(p.name)}</h3><p style="color:var(--muted);margin:0 0 10px">The correction wins over the imported files on every screen and in later imports. You can undo it any time.</p>
    <div class="hform"><label class="dx-l">What<select class="input" id="bf-f">${Object.entries(F).map(([k, l]) => `<option value="${k}" ${k === field ? "selected" : ""}>${l}</option>`).join("")}</select></label>
    <label class="dx-l">Right value<input class="input" id="bf-v" value="${esc(cur ?? "")}" placeholder="e.g. Section Manager, LAH Fortress, 2024-03-01, left"></label>
    <label class="dx-l" id="bf-cyc-l" ${field === "rating" ? "" : "hidden"}>Appraisal year<input class="input" id="bf-cyc" type="number" value="${new Date().getFullYear() - 1}"></label>
    <label class="dx-l" style="grid-column:1/-1">Why (optional)<input class="input" id="bf-n" placeholder="e.g. promoted in September, HRIS not updated yet"></label></div>
    <div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" data-act="modal-close">Cancel</button><button class="btn primary" id="bf-go">Save correction</button></div>`);
  $("#bf-f", m).onchange = () => { $("#bf-cyc-l", m).hidden = $("#bf-f", m).value !== "rating"; const c = (p.facts.find(f => f.field === $("#bf-f", m).value) || {}).value; $("#bf-v", m).value = c ?? ""; };
  $("#bf-go", m).onclick = async () => { await call("correction_add", { emp: p.emp, field: $("#bf-f", m).value, value: $("#bf-v", m).value, note: $("#bf-n", m).value, cycle: $("#bf-f", m).value === "rating" ? +$("#bf-cyc", m).value : null }); closeModal(); if (RV_AFTER_FIX) { const [e0, k0] = RV_AFTER_FIX; RV_AFTER_FIX = null; render(); setTimeout(() => rvPerson(e0, k0, "profile"), 300); } toast("Corrected · every screen now uses the new value"); render(); };
}
AFTER.brain = () => {
  const B = S.brain;
  const q = $("#br-q"); if (q) q.oninput = () => { clearTimeout(B.t); B.t = setTimeout(() => { B.q = q.value; B.emp = null; B.view = "person"; render(); }, 260); };
  if (q && B.q && document.activeElement !== q) { q.focus(); q.setSelectionRange(q.value.length, q.value.length); }
  const st = $("#br-store"); if (st) st.onchange = () => { B.store = st.value; B.emp = null; render(); };
  const lv = $("#br-level"); if (lv) lv.onchange = () => { B.level = lv.value; B.emp = null; render(); };
  const lf = $("#br-left"); if (lf) lf.onchange = () => { B.left = lf.checked; render(); };
  const gs = $("#brg-store"); if (gs) gs.onchange = () => { B.gstore = gs.value; render(); };
  if (B.tab === "people") { if (B.view === "store" && B.storeName) drawBrainStore(B.storeName); else drawBrainPerson(); }
  if (B.tab === "graph") drawBrainGraph();
};
const BRAIN_ACTS = {
  "br-tab": b => { S.brain.tab = b.dataset.t; render(); },
  "br-open": b => { closeModal(); S.brain.tab = "people"; S.brain.view = "person"; S.brain.emp = b.dataset.emp; if (S.page !== "brain") go("brain"); else render(); },
  "br-store": b => { S.brain.view = "store"; S.brain.storeName = b.dataset.s; drawBrainStore(b.dataset.s); },
  "br-fix": b => brainFix(b.dataset.f),
  "br-undo": async b => { await call("correction_undo", { correction_id: +b.dataset.id }); toast("Correction undone"); render(); },
  "br-export": () => { const p = DATA.brp; const m = modal(`<h3>Profile sheet · ${esc(p.name)}</h3><p style="color:var(--muted);margin:0 0 10px">A complete, shareable profile: role, career, ratings, results vs peers, attendance, insights and next steps.</p>
      <div class="seg" id="pe-f">${[["pdf", "PDF"], ["docx", "Word"]].map(([v, l], i) => `<button data-v="${v}" aria-pressed="${i === 0}">${l}</button>`).join("")}</div>
      <div class="setting"><div><b>Include 1:1 notes</b><small>Private notes stay out unless you tick this</small></div><label class="switch"><input type="checkbox" id="pe-n"><span></span></label></div>
      <div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" data-act="modal-close">Cancel</button><button class="btn primary" id="pe-go">Export</button></div>`);
    let f = "pdf"; $$("#pe-f button", m).forEach(b => b.onclick = () => { f = b.dataset.v; $$("#pe-f button", m).forEach(x => x.setAttribute("aria-pressed", x === b)); });
    $("#pe-go", m).onclick = async () => { const r = await call("profile_export", { emp: p.emp, fmt: f, include_notes: $("#pe-n", m).checked }); closeModal(); if (!r.cancelled) toast("Profile sheet saved"); }; },
};

/* ============================================================== 2.8 Employee relations */
S.er = S.er || { tab: "cases", status: "open", cid: null };
function personPicker(m, id, onPick) {
  const inp = $("#" + id, m), box = $("#" + id + "-r", m);
  let t;
  inp.oninput = () => { clearTimeout(t); t = setTimeout(async () => { const r = await API.call("people_pick", { q: inp.value });
    box.innerHTML = r.rows.map(p => `<button type="button" data-emp="${esc(p.emp)}" data-name="${esc(p.name)}"><b>${esc(p.name)}</b><small>${esc(p.designation || "")} · ${esc(p.store || "")} · #${esc(p.emp)}</small></button>`).join("") || `<small style="padding:6px">Nobody found: type the name as it should appear.</small>`;
    box.hidden = false; $$("button", box).forEach(b => b.onclick = () => { inp.value = b.dataset.name; inp.dataset.emp = b.dataset.emp; box.hidden = true; onPick && onPick(b.dataset.emp, b.dataset.name); }); }, 220); };
}
const pickerHtml = (id, label, val = "") => `<label class="dx-l ppick">${label}<input class="input" id="${id}" autocomplete="off" placeholder="Name or employee number" value="${esc(val)}"><div class="ppick-r" id="${id}-r" hidden></div></label>`;
PAGES.relations = async () => {
  const E = S.er;
  const tabs = `<div class="seg">${[["cases", "Cases"], ["letters", "HR letters"], ["exits", "Exit interviews"]].map(([k, l]) => `<button data-act="er-tab" data-t="${k}" aria-pressed="${E.tab === k}">${l}</button>`).join("")}</div>`;
  const head = (p, right = "") => `<div class="ph"><div><h1>Employee relations</h1><p>${p}</p></div><div class="row">${right}${tabs}</div></div>`;
  const k = (l, v, s, cls = "") => `<div class="kpi"><span class="kpi-l">${esc(l)}</span><span class="kpi-v ${cls}">${v}</span><span class="kpi-s"><span>${esc(s)}</span></span></div>`;
  if (E.tab === "letters") {
    const d = DATA.lt = await API.call("letter_types");
    const icons = { offer: "📨", appointment: "📝", confirmation: "✅", probation_extension: "⏳", transfer: "🔁", promotion: "🚀", show_cause: "❗", warning: "⚠️", experience: "🎓", relieving: "👋" };
    return head("Every standard HR letter, filled in from the person's record, numbered and filed on their page.") +
      `<div class="ltypes">${d.types.map(t => `<button class="ltype" data-act="lt-new" data-k="${t.kind}"><span>${icons[t.kind] || "✉️"}</span><b>${esc(t.title)}</b><small>${t.fields.length} details to check</small></button>`).join("")}</div>
      <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Letters issued</h2><small>${d.letters.length}</small></div><div class="tbl-wrap"><table class="t"><thead><tr><th>Date</th><th>Reference</th><th>Letter</th><th>To</th><th></th></tr></thead><tbody>
      ${d.letters.map(l => `<tr><td class="nw">${esc(l.created_at.slice(0, 10))}</td><td><code>${esc(l.ref)}</code></td><td>${esc((d.types.find(t => t.kind === l.kind) || {}).title || l.kind)}</td><td><button class="lnk" data-act="br-open" data-emp="${esc(l.emp)}">${esc(l.name)}</button></td><td>${l.case_id ? `<span class="chip">case #${l.case_id}</span>` : ""}</td></tr>`).join("") || `<tr><td colspan="5"><div class="empty">No letters yet.</div></td></tr>`}</tbody></table></div></div>`;
  }
  if (E.tab === "exits") {
    const d = DATA.ex = await API.call("exits");
    return head("Why people leave, in their own words: reasons, how they rate their manager, pay, culture and growth, and who we should not have lost.", `<button class="btn primary" data-act="ex-new">+ Exit interview</button>`) +
      `<div class="kpis k5">${k("Interviews", d.n, "recorded")}${k("Top reason", d.main.length ? `<span class="txt">${esc(d.main[0][0])}</span>` : "—", d.main.length ? d.main[0][1] + " people" : "")}${k("Would come back", d.would_return == null ? "—" : d.would_return + "%", "of those asked", d.would_return >= 50 ? "t-good" : "")}
        ${k("Leaver eNPS", d.enps == null ? "—" : (d.enps > 0 ? "+" : "") + d.enps, "would recommend us", d.enps == null ? "" : d.enps >= 0 ? "t-good" : "t-bad")}${k("Regrettable", d.regrettable.length, "strong performers who left", d.regrettable.length ? "t-bad" : "")}</div>
      ${d.n ? `<div class="grid g2"><div class="panel"><div class="phd"><h2>Why they left</h2><small>main and other reasons</small></div><div id="ch-exr"></div></div><div class="panel"><div class="phd"><h2>How leavers rate us</h2><small>1-5</small></div><div id="ch-exs"></div></div></div>` : ""}
      ${d.regrettable.length ? `<div class="panel"><div class="phd"><h2>Regrettable leavers</h2><small>rated 4+ or leader index 7+</small></div>${d.regrettable.map(r => `<div class="il bad">${esc(r.name)} · ${esc(r.store || "")} · ${esc(r.why)} · left for: <b>${esc(r.reason)}</b></div>`).join("")}</div>` : ""}
      <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Interviews</h2></div><div class="tbl-wrap"><table class="t"><thead><tr><th>Left</th><th>Name</th><th>Store</th><th>Main reason</th><th class="n">Manager</th><th class="n">Pay</th><th class="n">Growth</th><th class="n">Recommend</th><th>Comments</th></tr></thead><tbody>
      ${d.rows.map(r => `<tr><td class="nw">${r.leave_date ? fmtDate(r.leave_date) : ""}</td><td><button class="lnk" data-act="br-open" data-emp="${esc(r.emp)}">${esc(r.name)}</button><span class="sub">${esc(r.designation || "")}</span></td><td>${esc(r.store || "")}</td><td><span class="chip">${esc(r.main_reason)}</span></td><td class="n">${r.manager_score ?? "—"}</td><td class="n">${r.pay_score ?? "—"}</td><td class="n">${r.growth_score ?? "—"}</td><td class="n">${r.recommend ?? "—"}</td><td><small>${esc((r.comments || "").slice(0, 120))}</small></td></tr>`).join("") || `<tr><td colspan="9"><div class="empty">No exit interviews yet.</div></td></tr>`}</tbody></table></div></div>`;
  }
  const d = DATA.er = await API.call("er_cases", { status: E.status });
  return head("Disciplinary cases, grievances, investigations and improvement plans: every step with its deadline, letters attached, consistent outcomes.", `<button class="btn primary" data-act="er-new">+ New case</button>`) +
    `<div class="kpis k5">${k("Open cases", d.open, "in progress")}${k("Overdue steps", d.overdue, "past their deadline", d.overdue ? "t-bad" : "")}${k("Closed", d.closed, "all time")}${k("Days to close", d.avg_days_to_close ?? "—", "average")}${k("Most common", d.by_category.length ? `<span class="txt">${esc(d.by_category[0][0])}</span>` : "—", d.by_category.length ? d.by_category[0][1] + " cases" : "")}</div>
    <div class="grid g2" style="grid-template-columns:1.6fr 1fr"><div class="panel flush"><div class="row" style="padding:12px 14px 0"><div class="seg">${[["open", "Open"], ["overdue", "Overdue"], ["closed", "Closed"], ["all", "All"]].map(([v, l]) => `<button data-act="er-status" data-s="${v}" aria-pressed="${E.status === v}">${l}</button>`).join("")}</div></div>
      <div class="tbl-wrap"><table class="t"><thead><tr><th>#</th><th>Person</th><th>Type</th><th>Step</th><th>Next due</th><th>Outcome</th></tr></thead><tbody>
      ${d.rows.map(r => `<tr class="click ${r.overdue ? "row-bad" : ""}" data-act="er-open" data-id="${r.id}"><td>${r.id}</td><td><b>${esc(r.confidential ? "Confidential case" : r.name)}</b><span class="sub">${esc(r.designation || "")} · ${esc(r.store || "")}</span></td><td>${esc(r.kind)}<span class="sub">${esc(r.category)}</span></td><td><span class="chip ${r.stage === "Closed" ? "" : "info"}">${esc(r.stage)}</span></td><td class="nw ${r.overdue ? "t-bad" : ""}">${r.stage_due ? fmtDate(r.stage_due) : "—"}</td><td>${esc(r.outcome || "")}</td></tr>`).join("") || `<tr><td colspan="6"><div class="empty">No cases here.</div></td></tr>`}</tbody></table></div></div>
      <div class="panel"><div class="phd"><h2>By category</h2></div>${d.by_category.length ? `<div id="ch-erc"></div>` : `<div class="empty">No cases yet.</div>`}${d.by_outcome.length ? `<h4 class="ih">Outcomes</h4><div id="ch-ero"></div>` : ""}</div></div>`;
};
AFTER.relations = () => {
  const E = S.er;
  if (E.tab === "cases" && DATA.er) { const d = DATA.er;
    if ($("#ch-erc")) Charts.hbar($("#ch-erc"), { labels: d.by_category.map(x => x[0]), values: d.by_category.map(x => x[1]), colors: d.by_category.map((_, i) => Charts.PAL[i % Charts.PAL.length]) });
    if ($("#ch-ero")) Charts.hbar($("#ch-ero"), { labels: d.by_outcome.map(x => x[0]), values: d.by_outcome.map(x => x[1]), color: "#7A5C9E" }); }
  if (E.tab === "exits" && DATA.ex && DATA.ex.n) { const d = DATA.ex;
    Charts.hbar($("#ch-exr"), { labels: d.reasons.map(x => x[0]), values: d.reasons.map(x => x[1]), colors: d.reasons.map((_, i) => Charts.PAL[i % Charts.PAL.length]) });
    const sc = Object.entries(d.scores).filter(([, v]) => v != null);
    Charts.hbar($("#ch-exs"), { labels: sc.map(x => x[0]), values: sc.map(x => x[1]), max: 5, fmt: "score", colors: sc.map(([, v]) => v >= 4 ? "#16A34A" : v >= 3 ? "#F59E0B" : "#DC2626"), ref: 3 }); }
};
async function erDrawer(id) {
  const c = await call("er_case", { case_id: id });
  const i = c.steps.indexOf(c.stage), next = c.steps[i + 1];
  const m = modal(`<div class="row" style="justify-content:space-between;align-items:flex-start"><div><h3 style="margin:0">${esc(c.kind)} case #${c.id} · ${esc(c.name)}</h3><small style="color:var(--muted)">${esc(c.designation || "")} · ${esc(c.store || "")} · ${esc(c.category)} · opened ${fmtDate(c.opened_on)}</small></div>${c.overdue ? `<span class="chip bad">Step overdue</span>` : ""}</div>
    <div class="stepper">${c.steps.map((s, j) => `<div class="stp ${j < i ? "done" : j === i ? "now" : ""}"><i>${j < i ? "✓" : j + 1}</i><small>${esc(s)}</small></div>`).join("")}</div>
    ${c.description ? `<div class="il">${esc(c.description)}</div>` : ""}
    ${c.suggest ? `<div class="banner">⚖️ <b>Consistent next step: ${esc(c.suggest.outcome)}</b><br><small>${esc(c.suggest.why)}</small></div>` : ""}
    ${c.prior.length ? `<h4 class="ih">Earlier cases (12 months)</h4>${c.prior.map(p => `<div class="il">#${p.id} · ${fmtDate(p.opened_on)} · ${esc(p.category)} · ${esc(p.outcome || p.stage)}</div>`).join("")}` : ""}
    <h4 class="ih">History</h4><div class="tline" style="max-height:200px">${c.history.slice().reverse().map(h => `<div class="tl"><span class="tl-ic">•</span><div><small>${esc(h.at.slice(0, 16).replace("T", " "))}</small><div><b>${esc(h.stage)}</b>${h.outcome ? " · " + esc(h.outcome) : ""}${h.note ? " · " + esc(h.note) : ""}</div></div></div>`).join("")}</div>
    ${c.letters.length ? `<h4 class="ih">Letters</h4>${c.letters.map(l => `<div class="il">✉️ ${esc(l.kind)} · <code>${esc(l.ref)}</code></div>`).join("")}` : ""}
    ${c.stage !== "Closed" ? `<div class="hform" style="margin-top:10px"><label class="dx-l">Move to<select class="input" id="ec-st">${c.steps.slice(i + 1).map(s => `<option ${s === next ? "selected" : ""}>${esc(s)}</option>`).join("")}</select></label>
      <label class="dx-l">Outcome<select class="input" id="ec-out"><option value="">—</option>${DATA.er.outcomes.map(o => `<option ${o === c.outcome ? "selected" : ""}>${esc(o)}</option>`).join("")}</select></label>
      <label class="dx-l" style="grid-column:1/-1">Note<input class="input" id="ec-note" placeholder="What happened at this step"></label></div>` : ""}
    <div class="row" style="justify-content:space-between;margin-top:12px"><div class="row" style="gap:6px">${c.kind === "Disciplinary" ? `<button class="btn sm" data-act="lt-new" data-k="show_cause" data-emp="${esc(c.emp)}" data-case="${c.id}">❗ Show cause letter</button><button class="btn sm" data-act="lt-new" data-k="warning" data-emp="${esc(c.emp)}" data-case="${c.id}">⚠️ Warning letter</button>` : ""}<button class="btn sm ghost" data-act="br-open" data-emp="${esc(c.emp)}">🧠 Profile</button></div>
      <div class="row" style="gap:6px"><button class="btn" data-act="modal-close">Close</button>${c.stage !== "Closed" ? `<button class="btn primary" id="ec-go">Save step</button>` : ""}</div></div>`);
  m.classList.add("wide");
  const go = $("#ec-go", m); if (go) go.onclick = async () => { await call("er_advance", { case_id: c.id, stage: $("#ec-st", m).value, outcome: $("#ec-out", m).value || null, note: $("#ec-note", m).value }); closeModal(); toast("Case updated"); render(); };
}
function erNew() {
  const d = DATA.er;
  const m = modal(`<h3>New case</h3><div class="hform">${pickerHtml("en-p", "Employee")}
    <label class="dx-l">Type<select class="input" id="en-k">${d.kinds.map(x => `<option>${esc(x)}</option>`).join("")}</select></label>
    <label class="dx-l">Category<select class="input" id="en-c">${d.categories.map(x => `<option>${esc(x)}</option>`).join("")}</select></label>
    <label class="dx-l">Date of incident / complaint<input class="input" type="date" id="en-d" value="${new Date().toISOString().slice(0, 10)}"></label>
    <label class="dx-l" style="grid-column:1/-1">What happened<textarea class="input" id="en-t" rows="4" style="width:100%" placeholder="Facts only: what, when, where, who saw it"></textarea></label></div>
    <div class="setting"><div><b>Confidential</b><small>Shows as 'Confidential case' in lists (e.g. harassment)</small></div><label class="switch"><input type="checkbox" id="en-x"><span></span></label></div>
    <div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" data-act="modal-close">Cancel</button><button class="btn primary" id="en-go">Open case</button></div>`);
  personPicker(m, "en-p");
  $("#en-go", m).onclick = async () => { const p = $("#en-p", m); if (!p.value.trim()) return toast("Who is the case about?", { err: true });
    const c = await call("er_open", { kind: $("#en-k", m).value, emp: p.dataset.emp || "", name: p.value, category: $("#en-c", m).value, description: $("#en-t", m).value, opened_on: $("#en-d", m).value, confidential: $("#en-x", m).checked });
    closeModal(); toast(`Case #${c.id} opened · next step due ${fmtDate(c.stage_due)}`); render(); };
}
async function letterForm(kind, emp = "", caseId = null) {
  const types = (DATA.lt || await API.call("letter_types")).types, t = types.find(x => x.kind === kind);
  const m = modal(`<h3>${esc(t.title)}</h3><div class="hform">${pickerHtml("lf-p", "Employee")}<div id="lf-f" style="display:contents"></div></div>
    <div class="row" style="justify-content:space-between;margin-top:12px"><div class="seg" id="lf-fmt"><button data-v="docx" aria-pressed="true">Word</button><button data-v="pdf" aria-pressed="false">PDF</button></div>
    <div class="row" style="gap:6px"><button class="btn" data-act="modal-close">Cancel</button><button class="btn primary" id="lf-go">Create letter</button></div></div>`);
  m.classList.add("wide");
  let fmt = "docx", cur = null;
  $$("#lf-fmt button", m).forEach(b => b.onclick = () => { fmt = b.dataset.v; $$("#lf-fmt button", m).forEach(x => x.setAttribute("aria-pressed", x === b)); });
  const fill = async e => { cur = await API.call("letter_defaults", { kind, emp: e, case_id: caseId });
    $("#lf-p", m).value = cur.name; $("#lf-p", m).dataset.emp = e;
    $("#lf-f", m).innerHTML = Object.entries(cur.fields).map(([k, v]) => `<label class="dx-l ${["allegation", "areas", "expected"].includes(k) ? "wide2" : ""}">${esc(k.replace(/_/g, " ").replace(/^./, c => c.toUpperCase()))}<input class="input" data-lf="${k}" value="${esc(v)}"></label>`).join("") + `<small style="grid-column:1/-1;color:var(--muted)">Reference ${esc(cur.ref)} · filed on the person's page</small>`; };
  personPicker(m, "lf-p", (e) => fill(e));
  if (emp) fill(emp); else $("#lf-f", m).innerHTML = `<small style="grid-column:1/-1;color:var(--muted)">Choose the employee to fill in the letter.</small>`;
  $("#lf-go", m).onclick = async () => { if (!cur) return toast("Choose the employee first.", { err: true });
    const f = {}; $$("[data-lf]", m).forEach(i => f[i.dataset.lf] = i.value);
    const r = await call("letter_make", { kind, emp: $("#lf-p", m).dataset.emp || "", name: $("#lf-p", m).value, fields: f, fmt, case_id: caseId });
    if (r.cancelled) return; closeModal(); toast(`Letter ${r.ref} created`); if (S.page === "relations") render(); };
}
function exitForm() {
  const d = DATA.ex;
  const sc = (id, l) => `<label class="dx-l">${l}<div class="seg sc5" id="${id}">${[1, 2, 3, 4, 5].map(n => `<button type="button" data-v="${n}" aria-pressed="false">${n}</button>`).join("")}</div></label>`;
  const m = modal(`<h3>Exit interview</h3><div class="hform">${pickerHtml("xf-p", "Employee leaving")}<label class="dx-l">Last day<input class="input" type="date" id="xf-d"></label>
    <label class="dx-l">Main reason<select class="input" id="xf-r">${d.reasons_all.map(x => `<option>${esc(x)}</option>`).join("")}</select></label>
    <label class="dx-l">Other reasons<select class="input" id="xf-o" multiple size="4">${d.reasons_all.map(x => `<option>${esc(x)}</option>`).join("")}</select></label>
    ${sc("xf-m", "Their manager (1-5)")}${sc("xf-c", "Culture & team (1-5)")}${sc("xf-pay", "Pay & benefits (1-5)")}${sc("xf-g", "Growth & training (1-5)")}
    <label class="dx-l">Would they come back?<select class="input" id="xf-w"><option value="">—</option><option value="1">Yes</option><option value="0">No</option></select></label>
    <label class="dx-l">Recommend us to a friend (0-10)<input class="input" type="number" min="0" max="10" id="xf-n"></label>
    <label class="dx-l" style="grid-column:1/-1">In their words<textarea class="input" id="xf-t" rows="3" style="width:100%"></textarea></label></div>
    <div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" data-act="modal-close">Cancel</button><button class="btn primary" id="xf-go">Save</button></div>`);
  m.classList.add("wide"); personPicker(m, "xf-p");
  const v = {}; $$(".sc5", m).forEach(g => $$("button", g).forEach(b => b.onclick = () => { v[g.id] = +b.dataset.v; $$("button", g).forEach(x => x.setAttribute("aria-pressed", x === b)); }));
  $("#xf-go", m).onclick = async () => { const p = $("#xf-p", m); if (!p.value.trim()) return toast("Who is leaving?", { err: true });
    await call("exit_add", { emp: p.dataset.emp || "", name: p.value, leave_date: $("#xf-d", m).value || null, main_reason: $("#xf-r", m).value, reasons: [...$("#xf-o", m).selectedOptions].map(o => o.value),
      manager_score: v["xf-m"] || null, culture_score: v["xf-c"] || null, pay_score: v["xf-pay"] || null, growth_score: v["xf-g"] || null,
      would_return: $("#xf-w", m).value === "" ? null : $("#xf-w", m).value === "1", recommend: $("#xf-n", m).value === "" ? null : +$("#xf-n", m).value, comments: $("#xf-t", m).value });
    closeModal(); toast("Exit interview saved"); render(); };
}
const ER_ACTS = {
  "er-tab": b => { S.er.tab = b.dataset.t; render(); },
  "er-status": b => { S.er.status = b.dataset.s; render(); },
  "er-new": () => erNew(),
  "er-open": b => erDrawer(+b.dataset.id),
  "lt-new": b => { closeModal(); letterForm(b.dataset.k, b.dataset.emp || "", b.dataset.case ? +b.dataset.case : null); },
  "ex-new": () => exitForm(),
};

/* ============================================================== 2.8 People insights */
PAGES.insights = async () => {
  const d = DATA.pi = await API.call("people_insights");
  const A = d.absence || {}, W = d.wellbeing || {}, T = d.attrition || {}, G = d.gender || {}, K = d.week || {}, R = d.drivers || {};
  const k = (l, v, s, cls = "") => `<div class="kpi"><span class="kpi-l">${esc(l)}</span><span class="kpi-v ${cls}">${v}</span><span class="kpi-s"><span>${esc(s)}</span></span></div>`;
  const none = msg => `<div class="empty" style="padding:22px">${esc(msg)}</div>`;
  const who = r => `<button class="lnk" data-act="br-open" data-emp="${esc(r.emp)}">${esc(r.name)}</button><span class="sub">${esc(r.designation || "")}${r.store ? " · " + esc(r.store) : ""}</span>`;
  return `<div class="ph"><div><h1>People insights</h1><p>Patterns behind the numbers: when people are absent, who is overworked, who leaves early, who we should not have lost, and what moves with turnover.</p></div></div>
  <div class="kpis k5">${k("Absence rate", A.available ? A.average + "%" : "—", A.month ? "of scheduled days · " + A.month : "needs attendance", A.average > 5 ? "t-bad" : "")}
    ${k("Pattern absence", A.available ? A.bradford_high : "—", "Bradford score 125+", A.bradford_high ? "t-bad" : "")}
    ${k("Overworked", W.available ? W.n : "—", "long days or no rest", W.n ? "t-warn" : "")}
    ${k("Leave in 90 days", T.early_pct != null ? T.early_pct + "%" : "—", T.early_pct != null ? `${T.early} of ${T.known_tenure} leavers` : "needs joining dates", T.early_pct >= 20 ? "t-bad" : "")}
    ${k("Women in leadership", G.leaders_women_pct != null ? G.leaders_women_pct + "%" : "—", G.women_pct != null ? `${G.women_pct}% of all staff` : "needs gender in roster")}</div>
  <div class="grid g2">
    <div class="panel"><div class="phd"><h2>This week</h2><small>${K.from ? fmtDate(K.from) + " – " + fmtDate(K.to) : ""}</small></div>
      <h4 class="ih">🎉 Work anniversaries</h4>${(K.anniversaries || []).length ? K.anniversaries.slice(0, 8).map(a => `<div class="il ${a.milestone ? "good" : ""}"><b>${a.years} year${a.years > 1 ? "s" : ""}</b> · ${esc(a.name)} · ${esc(a.designation || "")} · ${esc(a.store || "")} · ${fmtDate(a.on)}${a.milestone ? " · milestone" : ""}</div>`).join("") : `<small class="muted">None in the next 7 days (or no joining dates).</small>`}
      <h4 class="ih">🌴 Away on leave</h4>${(K.off || []).length ? K.off.slice(0, 10).map(o => `<div class="il ${o.level >= 3 ? "warn" : ""}">${esc(o.name)} · ${esc(o.designation || "")} · ${esc(o.store || "")} · ${esc(o.type)} ${fmtDate(o.from)} – ${fmtDate(o.to)}</div>`).join("") : `<small class="muted">Nobody on recorded leave this week.</small>`}</div>
    <div class="panel"><div class="phd"><h2>When people are absent</h2><small>% of scheduled days, by weekday</small></div>
      ${A.available && Object.keys(A.by_weekday).length ? `<div id="ch-wd"></div>${A.peak ? `<div class="banner">📅 <b>${esc(A.peak.day)}</b> absence is ${A.peak.x}× the average (${A.peak.rate}% vs ${A.average}%). Check rosters and leave approvals for that day.</div>` : ""}${A.next_to_off_share != null ? `<small class="muted">${A.next_to_off_share}% of absences sit right next to a day off or holiday.</small>` : ""}` : none("Import attendance to see absence patterns.")}</div></div>
  <div class="grid g2">
    <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Pattern absence</h2><small>Bradford factor = spells² × days</small></div>
      ${(A.bradford || []).length ? `<div class="tbl-wrap"><table class="t"><thead><tr><th>Person</th><th class="n">Days</th><th class="n">Spells</th><th class="n">Next to off</th><th class="n">Bradford</th></tr></thead><tbody>
      ${A.bradford.slice(0, 12).map(r => `<tr><td>${who(r)}</td><td class="n">${r.days}</td><td class="n">${r.spells}</td><td class="n">${r.next_to_off}</td><td class="n"><span class="chip ${r.bradford >= 250 ? "bad" : r.bradford >= 125 ? "warn" : ""}">${r.bradford}</span></td></tr>`).join("")}</tbody></table></div>
      <small class="muted" style="display:block;padding:8px 16px 14px">Many short absences disrupt a store more than one long one. 125+ deserves a return-to-work talk; 250+ a formal review.</small>` : none("No absences recorded.")}</div>
    <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Wellbeing watch</h2><small>11h+ days, 12+ days without rest, 40h+ over</small></div>
      ${(W.rows || []).length ? `<div class="tbl-wrap"><table class="t"><thead><tr><th>Person</th><th class="n">Avg day</th><th class="n">11h+ days</th><th class="n">Longest run</th><th>Why</th></tr></thead><tbody>
      ${W.rows.slice(0, 12).map(r => `<tr><td>${who(r)}</td><td class="n">${r.avg_h}h</td><td class="n">${r.long_days}</td><td class="n">${r.streak}</td><td><small>${esc(r.flags.join(" · "))}</small></td></tr>`).join("")}</tbody></table></div>` : none(W.available ? "Nobody is working unusually long hours or without rest. 👍" : "Import attendance with punch times to check working hours.")}</div></div>
  <div class="grid g2">
    <div class="panel"><div class="phd"><h2>How long leavers stayed</h2><small>${T.known_tenure || 0} of ${T.n || 0} with a joining date</small></div>
      ${T.known_tenure ? `<div id="ch-ten"></div>${T.early_by_store.length ? `<h4 class="ih">Early leavers by store</h4><div id="ch-early"></div>` : ""}` : none(T.available ? "Leavers' joining dates are missing. Add a 'Joining Date' column to the turnover sheet, or import the Basic Sheet with past employees." : "Import the turnover sheet.")}</div>
    <div class="panel"><div class="phd"><h2>Regrettable losses</h2><small>${T.regrettable_n || 0} strong performers left · ${T.regrettable_voluntary || 0} resigned</small></div>
      ${(T.regrettable || []).length ? T.regrettable.slice(0, 10).map(r => `<div class="il bad">${esc(r.name)} · ${esc(r.store || "")} · ${esc(r.section || "")} · ${r.date ? fmtDate(r.date) : ""} · ${esc(r.regrettable)}${r.reason ? ` · <b>${esc(r.reason)}</b>` : ""}</div>`).join("") : none("No leaver had a rating of 4+ or a leader index of 7+.")}</div></div>
  <div class="grid g2">
    <div class="panel"><div class="phd"><h2>Gender mix by level</h2><small>current staff · groups under ${G.min_group || 5} not split</small></div>
      ${(G.rows || []).length ? `<div class="gmix">${G.rows.map(r => r.women_pct == null ? `<div class="gm"><span>${esc(r.band)}</span><div class="gbar"><i style="width:100%;background:var(--line-2)"></i></div><small>${r.n} people</small></div>`
        : `<div class="gm"><span>${esc(r.band)}</span><div class="gbar"><i class="w" style="width:${r.women_pct}%"></i><i class="m" style="width:${100 - r.women_pct}%"></i></div><small><b>${r.women_pct}%</b> women · ${r.n}</small></div>`).join("")}
        <div class="legend"><span><i style="background:#C2410C"></i>Women</span><span><i style="background:#1E3A8A"></i>Men</span></div></div>${G.note ? `<div class="banner">⚖️ ${esc(G.note)}</div>` : ""}` : none("Gender is not in the imported roster.")}</div>
    <div class="panel"><div class="phd"><h2>What moves together across stores</h2><small>${R.stores || 0} stores · links, not causes</small></div>
      ${(R.drivers || []).length ? R.drivers.map(x => `<div class="drv"><div class="drv-r ${x.r > 0 ? "pos" : "neg"}"><i style="width:${Math.abs(x.r) * 100}%"></i></div><div><b>${x.r > 0 ? "+" : ""}${x.r.toFixed(2)}</b> ${esc(x.text)}</div></div>`).join("") + `<small class="muted">Correlation across stores: a lead to look into, not proof. A strong link with only a few stores can be chance.</small>` : none("No strong links between turnover, absence, leadership, sales and NPS across stores yet.")}</div></div>`;
};
AFTER.insights = () => {
  const d = DATA.pi; if (!d) return;
  const A = d.absence || {}, T = d.attrition || {};
  if ($("#ch-wd")) { const L = Object.keys(A.by_weekday), V = L.map(x => A.by_weekday[x]);
    Charts.columns($("#ch-wd"), { labels: L.map(x => x.slice(0, 3)), tipLabels: L, series: [{ name: "Absence %", values: V, colors: V.map(v => v >= A.average * 1.25 ? "#DC2626" : v >= A.average ? "#F59E0B" : "#16A34A") }], fmt: "pct" }); }
  if ($("#ch-ten")) Charts.columns($("#ch-ten"), { labels: T.tenure_bands.map(x => x[0]), series: [{ name: "Leavers", values: T.tenure_bands.map(x => x[1]), colors: ["#DC2626", "#F59E0B", "#0EA5E9", "#16A34A"] }] });
  if ($("#ch-early")) Charts.hbar($("#ch-early"), { labels: T.early_by_store.map(x => x[0]), values: T.early_by_store.map(x => x[1]), color: "#DC2626" });
};

/* ============================================================== 3.0 HR calendar */
const EVK = { anniversary: ["🎉", "Anniversary", "#16A34A"], probation: ["⏳", "Probation ends", "#F59E0B"], leave: ["🌴", "Leave", "#0EA5E9"], er: ["⚖️", "ER step due", "#DC2626"],
  goal: ["🎯", "Goal due", "#7A5C9E"], action: ["✅", "Action due", "#94481A"], followup: ["💬", "1:1 follow-up", "#C2410C"], holiday: ["🏖️", "Holiday", "#B8860B"], training: ["🎓", "Training due", "#1E3A8A"] };
PAGES.calendar = async () => {
  const m = S.calMonth || new Date().toISOString().slice(0, 7);
  const d = DATA.cal = await API.call("hr_calendar", { month: m });
  const shift = n => { const [y, mo] = m.split("-").map(Number); const t = new Date(y, mo - 1 + n, 1); return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}`; };
  const today = new Date().toISOString().slice(0, 10), f = S.calKind || "all";
  const cells = Array(d.first_weekday).fill(`<div class="cd empty"></div>`).concat(d.days.map(x => {
    const ev = x.events.filter(e => f === "all" || e.kind === f);
    return `<div class="cd ${x.day === today ? "today" : ""} ${ev.length ? "has" : ""}" ${ev.length ? `data-act="cal-day" data-d="${x.day}"` : ""}><b>${+x.day.slice(8)}</b>
      ${ev.slice(0, 3).map(e => `<span class="ce" style="--c:${EVK[e.kind][2]}" title="${esc(e.text)}">${EVK[e.kind][0]} ${esc(e.text)}</span>`).join("")}${ev.length > 3 ? `<small>+${ev.length - 3} more</small>` : ""}</div>`; }));
  return `<div class="ph"><div><h1>HR calendar</h1><p>Every date that matters in one place: anniversaries, probation ends, leave, case deadlines, goals, actions, follow-ups, training and holidays.</p></div>
    <div class="row"><button class="btn sm" data-act="cal-m" data-m="${shift(-1)}">‹</button><b style="min-width:130px;text-align:center">${esc(d.label)}</b><button class="btn sm" data-act="cal-m" data-m="${shift(1)}">›</button><button class="btn sm ghost" data-act="cal-m" data-m="">Today</button></div></div>
    <div class="chips cal-f"><button class="chip ${f === "all" ? "on" : ""}" data-act="cal-k" data-k="all">All</button>${Object.entries(EVK).map(([k, [i, l, c]]) => `<button class="chip ${f === k ? "on" : ""}" data-act="cal-k" data-k="${k}" style="--c:${c}">${i} ${l} <b>${d.counts[k] || 0}</b></button>`).join("")}</div>
    <div class="panel hrcal"><div class="hc-h">${["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map(x => `<span>${x}</span>`).join("")}</div><div class="hc-g">${cells.join("")}</div></div>`;
};
function calDay(day) {
  const x = DATA.cal.days.find(d => d.day === day);
  modal(`<h3>${fmtDate(day)}</h3>${x.events.map(e => `<div class="il" style="border-left:3px solid ${EVK[e.kind][2]};padding-left:10px">${EVK[e.kind][0]} <b>${EVK[e.kind][1]}</b> · ${esc(e.text)}
    ${e.go ? ` <button class="lnk" ${e.emp && e.go === "brain" ? `data-act="br-open" data-emp="${esc(e.emp)}"` : `data-go="${e.go}"`}>Open</button>` : ""}</div>`).join("")}
    <div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" data-act="modal-close">Close</button></div>`);
}

/* ============================================================== 3.0 Weekly brief */
PAGES.brief = async () => {
  const b = DATA.brief = await API.call("weekly_brief");
  const IC = { "The numbers": ["📊", "#B8860B"], "Stores that need attention": ["🏬", "#DC2626"], "Leaders": ["⭐", "#0EA5E9"], "Needs you this week": ["📌", "#C2410C"], "People": ["👥", "#16A34A"], "Coming up": ["📅", "#7A5C9E"] };
  return `<div class="ph"><div><h1>Weekly brief</h1><p>${esc(b.title)}. Built from everything in P&O, ready to send to your line manager or the store managers.</p></div>
    <div class="row"><button class="btn" data-act="brief-copy">Copy text</button><button class="btn" data-act="brief-x" data-f="docx">Word</button><button class="btn primary" data-act="brief-x" data-f="pdf">PDF</button></div></div>
    <div class="brief">${b.sections.map(s => `<div class="panel bsec" style="--c:${(IC[s.title] || ["", "#94481A"])[1]}"><h2>${(IC[s.title] || ["•"])[0]} ${esc(s.title)}</h2><ul>${s.items.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>`).join("") || `<div class="panel"><div class="empty">Import data to build the brief.</div></div>`}</div>`;
};

/* ============================================================== 3.0 Store visit checklist */
async function visitForm(store) {
  const t = await call("visit_template", { store });
  const ans = {};
  const m = modal(`<h3>Store visit · ${esc(store)}</h3>${t.facts.length ? `<div class="banner">📍 <b>Check while you're there:</b> ${t.facts.map(esc).join(" · ")}</div>` : ""}
    <div class="vlist">${Object.entries(t.sections).map(([sec, items]) => `<h4 class="ih">${esc(sec)}</h4>${items.map(it => `<div class="vi"><span>${esc(it)}</span><div class="seg sm" data-vi="${esc(it)}"><button data-v="ok">✓ OK</button><button data-v="issue">✗ Issue</button><button data-v="na">N/A</button></div></div>`).join("")}`).join("")}</div>
    <label class="dx-l" style="margin-top:10px">Notes<textarea class="input" id="vf-n" rows="3" style="width:100%" placeholder="What you saw, who you spoke to"></textarea></label>
    <label class="dx-l">Actions (one per line, each becomes a tracked action for ${esc(store)})<textarea class="input" id="vf-a" rows="3" style="width:100%"></textarea></label>
    <div class="row" style="justify-content:space-between;margin-top:12px"><small id="vf-s" class="muted">0 checked</small><div class="row" style="gap:6px"><button class="btn" data-act="modal-close">Cancel</button><button class="btn primary" id="vf-go">Save visit</button></div></div>`);
  m.classList.add("wide");
  const upd = () => { const v = Object.values(ans), ok = v.filter(x => x === "ok").length, is = v.filter(x => x === "issue").length; $("#vf-s", m).textContent = `${v.length} checked · ${ok} OK · ${is} issue${is === 1 ? "" : "s"}${ok + is ? ` · ${Math.round(100 * ok / (ok + is))}%` : ""}`; };
  $$("[data-vi]", m).forEach(g => $$("button", g).forEach(b => b.onclick = () => { ans[g.dataset.vi] = b.dataset.v; $$("button", g).forEach(x => x.setAttribute("aria-pressed", x === b)); upd(); }));
  $("#vf-go", m).onclick = async () => { const r = await call("visit_save", { store, answers: ans, notes: $("#vf-n", m).value, actions: $("#vf-a", m).value.split("\n") });
    closeModal(); SNAP.clear(); toast(`Visit saved${r.score != null ? ` · ${r.score}%` : ""}${r.actions ? ` · ${r.actions} action${r.actions > 1 ? "s" : ""} created` : ""}`); if (S.page === "notes") render(); };
}
async function visitPick() {
  const st = (await call("visit_template", { store: "" })).stores || [];
  const m = modal(`<h3>Which store are you visiting?</h3><div class="vpick">${st.map(s => `<button class="btn" data-n="${esc(s)}">${esc(s)}</button>`).join("") || `<div class="empty">Import data first.</div>`}</div>`);
  $$(".vpick button", m).forEach(b => b.onclick = () => { closeModal(); visitForm(b.dataset.n); });
}

/* ============================================================== 3.0 Explain this number */
let GLOSS = null;
async function explainKpis(root) {
  if (!GLOSS) { try { GLOSS = (await API.call("glossary")).terms; } catch (_) { GLOSS = []; } }
  const alias = ["index", "leavers", "turnover", "retention", "absence", "presence", "nps", "sales", "shrink", "stock days", "rating", "bradford", "pattern", "enps", "data health", "productivity"];
  $$(".kpi", root).forEach(k => {
    if (k.querySelector(".kx")) return;
    const l = (k.querySelector(".kpi-l") || {}).textContent || "";
    const t = l.toLowerCase();
    if (!GLOSS.some(g => t.includes(g)) && !alias.some(a => t.includes(a))) return;
    k.insertAdjacentHTML("beforeend", `<span class="kx" data-act="explain" data-t="${esc(l)}" title="How is this calculated?" role="button" tabindex="0">?</span>`);
  });
}
async function explainPop(el, term) {
  const r = await API.call("explain", { term });
  $$(".xpop").forEach(x => x.remove());
  if (!r.what) return toast("No definition yet for " + term);
  const p = document.createElement("div"); p.className = "xpop";
  p.innerHTML = `<b>${esc(term)}</b><p>${esc(r.what)}</p>${r.source ? `<small><b>Comes from</b> ${esc(r.source)}</small>` : ""}${r.good ? `<small><b>Good looks like</b> ${esc(r.good)}</small>` : ""}`;
  document.body.appendChild(p);
  const b = el.getBoundingClientRect(); p.style.top = Math.min(innerHeight - p.offsetHeight - 10, b.bottom + 6) + "px"; p.style.left = Math.max(10, Math.min(innerWidth - p.offsetWidth - 10, b.left - 140)) + "px";
  setTimeout(() => document.addEventListener("click", function off(e) { if (!p.contains(e.target)) { p.remove(); document.removeEventListener("click", off); } }), 0);
}

/* ============================================================== 3.0 Welcome tour */
const TOUR = [
  ["#nav", "Everything in one menu", "Business review, stores, people, the People Brain, insights, hiring, learning and more. Hover a menu item and it starts loading before you click."],
  ["#q", "Find anything", "Search a person, a store or a command. Ctrl K jumps here from anywhere; press ? for all keyboard shortcuts."],
  ["[data-go=import]", "Bring in your reports", "Any Excel, CSV or PDF. P&O works out what each sheet is, checks it and tells you what doesn't add up. Pick the month on the calendar."],
  [".ai-pill", "Ask P&O AI", "Ask in plain words, in English or Urdu. Choose which AI handles which kind of job in Settings → AI; confidential work can stay offline."],
  ["[data-go=insights]", "Look beyond the numbers", "People insights, the HR calendar and the weekly brief turn the data into what needs you this week."],
];
function tour(i = 0) {
  $$(".tour,.tour-hl").forEach(x => x.remove());
  if (i >= TOUR.length) { API.call("tour_done", { done: true }).catch(() => {}); if (S.init) S.init.tour_done = true; return; }
  const [sel, h, p] = TOUR[i], el = $(sel);
  if (!el) return tour(i + 1);
  if (sel !== "#nav") el.scrollIntoView({ block: "center" });
  const r = el.getBoundingClientRect();
  const hl = document.createElement("div"); hl.className = "tour-hl";
  Object.assign(hl.style, { top: r.top - 6 + "px", left: r.left - 6 + "px", width: r.width + 12 + "px", height: Math.min(r.height, innerHeight - r.top - 20) + 12 + "px" });
  const c = document.createElement("div"); c.className = "tour";
  c.innerHTML = `<small>${i + 1} of ${TOUR.length}</small><b>${esc(h)}</b><p>${esc(p)}</p><div class="row" style="justify-content:space-between"><button class="btn sm ghost" data-t="end">Skip tour</button><button class="btn sm primary" data-t="next">${i === TOUR.length - 1 ? "Done" : "Next →"}</button></div>`;
  document.body.append(hl, c);
  const below = r.bottom + 190 < innerHeight;
  Object.assign(c.style, { top: (below ? Math.min(r.bottom + 14, innerHeight - 200) : Math.max(10, r.top - 180)) + "px", left: Math.min(innerWidth - 340, Math.max(10, r.right > innerWidth / 2 ? r.left - 330 : r.right + 14)) + "px" });
  if (sel === "#nav") c.style.top = "120px";
  c.querySelector("[data-t=next]").onclick = () => tour(i + 1);
  c.querySelector("[data-t=end]").onclick = () => tour(TOUR.length);
}

/* ============================================================== 3.0 Settings: backups and column names */
SETTINGS.backups = async () => {
  const b = await API.call("backups"), sy = await API.call("synonyms");
  return `<div class="panel"><div class="phd"><h2>Automatic backups</h2><small>one copy a day, last 14 kept · ${esc(b.folder)}</small></div>
    <div class="setting"><div><b>Back up automatically</b><small>${b.last ? "Last automatic copy: " + fmtDate(b.last) : "Runs when P&O opens"}</small></div><label class="switch"><input type="checkbox" id="bk-auto" ${b.auto ? "checked" : ""}><span></span></label></div>
    <div class="setting"><div><b>Back up now</b><small>Make a copy in the backups folder</small></div><button class="btn" data-act="bk-now">Back up now</button></div>
    <div class="tbl-wrap" style="max-height:260px"><table class="t"><thead><tr><th>Copy</th><th>Made</th><th class="n">Size</th><th></th></tr></thead><tbody>
    ${b.rows.map(r => `<tr><td>${esc(r.name)}</td><td class="nw">${esc(r.at.replace("T", " "))}</td><td class="n">${r.size_kb.toLocaleString()} KB</td><td><button class="btn sm ghost" data-act="bk-restore" data-n="${esc(r.name)}">Restore</button></td></tr>`).join("") || `<tr><td colspan="4"><div class="empty">No copies yet.</div></td></tr>`}</tbody></table></div></div>
    <div class="panel"><div class="phd"><h2>Teach Smart Import your column names</h2><small>names your HR system uses, comma separated; they count like the built-in ones</small></div>
    <div class="syn">${sy.fields.map(f => `<label class="dx-l"><span>${esc(f.label)} <small class="muted" title="${esc(f.builtin.join(", "))}">already knows ${f.builtin.length}+</small></span><input class="input" data-syn="${f.field}" value="${esc(f.extra.join(", "))}" placeholder="${esc(f.builtin.slice(0, 3).join(", "))}…"></label>`).join("")}</div></div>`;
};
const V3_ACTS = {
  "cal-m": b => { S.calMonth = b.dataset.m || null; render(); },
  "cal-k": b => { S.calKind = b.dataset.k; render(); },
  "cal-day": b => calDay(b.dataset.d),
  "brief-copy": async () => { try { await navigator.clipboard.writeText(DATA.brief.title + "\n\n" + DATA.brief.text); toast("Brief copied"); } catch (_) { toast("Couldn't copy here: use Word or PDF", { err: true }); } },
  "brief-x": async b => { const r = await call("weekly_brief_export", { fmt: b.dataset.f }); if (!r.cancelled) toast("Brief saved"); },
  "visit-new": b => b.dataset.store ? visitForm(b.dataset.store) : visitPick(),
  "explain": b => explainPop(b, b.dataset.t),
  "tour": () => tour(0),
  "bk-now": async () => { await call("backup_now"); toast("Backup made"); render(); },
  "bk-restore": async b => { if (!confirm(`Replace all P&O data with ${b.dataset.n}? The current data is kept as a safety copy.`)) return; await call("restore_backup", { name: b.dataset.n }); toast("Backup restored"); await afterDataChange(true); },
};

/* ============================================================== 4.0 Review: the one screen */
S.rv = S.rv || { store: "", dept: "", section: "", role: "", sort: null, desc: false };
const RVF = (k, v) => {
  if (v == null) return `<span class="na">—</span>`;
  const f = (DATA.rv && DATA.rv.criteria[k] || {}).fmt;
  return f === "pct0" ? `${v.toFixed(0)}%` : f === "pct1" ? `${v.toFixed(1)}%` : f === "pct1s" ? `${v > 0 ? "+" : ""}${v.toFixed(1)}%`
    : f === "pp2s" ? `${v > 0 ? "+" : ""}${v.toFixed(2)}` : f === "dec1" ? v.toFixed(1) : String(Math.round(v));
};
const rvBench = (k, unit) => { const c = DATA.rv.criteria[k]; if (c.green == null) return "No benchmark: shown for information";
  if (unit && ["leavers", "da"].includes(k)) return "Total for the group · each person is judged on their own";
  const u = { pct0: "%", pct1: "%", pct1s: "%", pp2s: " pts" }[c.fmt] || "";
  return c.better === "up" ? `Green ${c.green}${u} or more · amber ${c.amber}${u} or more` : `Green ${c.green}${u} or less · amber ${c.amber}${u} or less`; };
PAGES.rv = async () => {
  const F = S.rv;
  const d = DATA.rv = await API.call("review", { store: F.store, dept: F.dept, section: F.section, role: F.role });
  if (d.empty) return `<div class="panel"><div class="hero"><div class="logo maf big"><img src="maf-logo.png" alt=""></div><h2>Department Review</h2>
    <p>Add this week's reports to see the review: sales, productivity, shrinkage and stock days, out of stock, attendance, leavers and NPS.</p>
    <div class="row" style="justify-content:center"><button class="btn primary" data-act="rv-update">Update data</button><button class="btn" data-act="demo-on">Try with demo data</button></div></div></div>`;
  const o = d.options, C = d.criteria;
  const chip = (act, val, label, on) => `<button class="rchip ${on ? "on" : ""}" data-act="${act}" data-v="${esc(val)}">${esc(label)}</button>`;
  const crumbs = [["Country", { store: "", dept: "", section: "" }]];
  if (F.store) crumbs.push([F.store, { dept: "", section: "" }]);
  if (F.dept) crumbs.push([(o.depts.find(x => x[0] === F.dept) || [0, F.dept])[1], { section: "" }]);
  if (F.section) crumbs.push([F.section, {}]);
  const tile = t => `<div class="rtile ${t.status}" title="${esc(rvBench(t.key))}"><span class="rt-l">${esc(t.label)}</span><span class="rt-v">${RVF(t.key, t.value)}</span><span class="rt-b">${esc(rvBench(t.key, true).split(" · ")[0])}</span></div>`;
  const cell = c => `<td class="n rc ${c.status}">${RVF(c.key, c.value)}</td>`;
  const head = keys => keys.map(k => `<th class="n" title="${esc(C[k].label + " · " + rvBench(k))}">${esc(C[k].short)}</th>`).join("");
  // people: sortable, never ranked
  let ppl = d.people.slice();
  if (F.sort) { const i = d.people.length ? d.people[0].cells.findIndex(c => c.key === F.sort) : -1;
    if (i >= 0) ppl.sort((a, b) => { const x = a.cells[i].value, y = b.cells[i].value; if (x == null) return 1; if (y == null) return -1; return F.desc ? y - x : x - y; }); }
  const pk = d.people_keys;
  return `<div class="rhead">
      <div><div class="rcrumbs">${crumbs.map((c, i) => i === crumbs.length - 1 ? `<b>${esc(c[0])}</b>` : `<button data-act="rv-crumb" data-i="${i}">${esc(c[0])}</button><span>›</span>`).join("")}</div>
        <h1>${esc(d.label)}</h1><p class="muted">Data as of ${fmtDate(d.as_of)}${d.period_label ? " · " + esc(d.period_label) : ""}</p></div></div>
    <div class="rfilters four">
      <div class="rf"><label>Store</label><select id="rv-store" class="input"><option value="">All stores</option>${o.stores.map(x => `<option ${x === F.store ? "selected" : ""}>${esc(x)}</option>`).join("")}</select></div>
      <div class="rf"><label>Department</label><select id="rv-dept" class="input"><option value="">All departments</option>${o.depts.map(([k, l]) => `<option value="${esc(k)}" ${F.dept === k ? "selected" : ""}>${esc(l === k ? k : l + " · " + k)}</option>`).join("")}</select></div>
      <div class="rf"><label>Section</label><select id="rv-sec" class="input"><option value="">All sections</option>${o.section_groups.filter(([, d]) => !F.dept || F.dept === d || (F.dept === "Non Food" && ["Light Household", "Heavy Household", "Textile"].includes(d)))
        .map(([l, d, secs]) => `<optgroup label="${esc(l)}">${secs.map(x => `<option value="${esc(x)}" data-d="${esc(d)}" ${F.section === x ? "selected" : ""}>${esc(x)}</option>`).join("")}</optgroup>`).join("")}</select></div>
      <div class="rf"><label>People</label><select id="rv-role" class="input"><option value="">All leaders</option>${o.roles.map(([k, l]) => `<option value="${k}" ${F.role === k ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></div>
      ${F.store || F.dept || F.section || F.role ? `<button class="btn sm ghost" data-act="rv-clear">Clear</button>` : ""}
    </div>
    <div class="rtiles">${d.tiles.map(tile).join("")}</div>
    <div class="rnotes">
      <div class="rnote good"><h3>What's strong</h3><ul>${d.notes.strong.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>
      <div class="rnote bad"><h3>What's weak</h3><ul>${d.notes.weak.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>
      <div class="rnote focus"><h3>Focus this week</h3><ol>${d.notes.focus.map(x => `<li>${esc(x)}</li>`).join("")}</ol></div>
    </div>
    ${d.grid.length ? `<div class="panel flush rpanel"><div class="phd"><h2>By ${esc(d.grid_kind.replace(/s$/, ""))}</h2><small>click a row to look inside</small></div>
      <div class="tbl-wrap"><table class="t rtable"><thead><tr><th>${esc(d.grid_kind.replace(/^./, c => c.toUpperCase()).replace(/s$/, ""))}</th>${head(d.grid_keys)}</tr></thead><tbody>
      ${d.grid.map((g, i) => `<tr class="click" data-act="rv-drill" data-i="${i}"><td><b>${esc(g.name)}</b></td>${g.cells.filter(c => d.grid_keys.includes(c.key)).map(cell).join("")}</tr>`).join("")}</tbody></table></div></div>` : ""}
    <div class="panel flush rpanel"><div class="phd"><h2>People benchmark</h2><small>${ppl.length} leader${ppl.length === 1 ? "" : "s"} · every criterion shown · click a column to sort · click a name for the full sheet</small></div>
      ${ppl.length ? `<div class="tbl-wrap"><table class="t rtable"><thead><tr><th>Person</th>${pk.map(k => `<th class="n sortable ${F.sort === k ? "sorted" : ""} ${k === "score" ? "rscore-h" : ""}" data-act="rv-sort" data-k="${k}" title="${esc(C[k].label + " · " + rvBench(k))}">${esc(C[k].short)}${F.sort === k ? (F.desc ? " ↓" : " ↑") : ""}</th>`).join("")}</tr></thead><tbody>
      ${ppl.map(p => `<tr class="click" data-act="rv-person" data-emp="${esc(p.emp)}" data-key="${esc(p.key)}"><td class="rwho"><b>${esc(p.name)}</b>${p.acting ? ` <span class="chip">acting</span>` : ""}<span class="sub">${esc(p.role)} · ${esc(p.area)}${F.store ? "" : " · " + esc(p.store)}</span></td>
        ${p.cells.filter(c => pk.includes(c.key)).map(c => c.key === "score" ? `<td class="n rc rscore ${c.status}">${RVF(c.key, c.value)}</td>` : cell(c)).join("")}</tr>`).join("")}</tbody></table></div>
      <div class="rlegend"><span class="good">On or above benchmark</span><span class="warn">Close</span><span class="bad">Below benchmark</span><span class="na">— not measured for this role</span></div>`
      : `<div class="empty">No leaders in this view.</div>`}</div>`;
};
AFTER.rv = () => {
  const on = (id, f) => { const e = $(id); if (e) e.onchange = () => { f(e); render(); }; };
  on("#rv-store", e => { S.rv.store = e.value; });
  on("#rv-dept", e => Object.assign(S.rv, { dept: e.value, section: "", sort: null }));
  on("#rv-sec", e => { const o = e.selectedOptions[0]; S.rv.section = e.value; if (e.value && o && o.dataset.d && S.rv.dept !== "Non Food") S.rv.dept = o.dataset.d; });
  on("#rv-role", e => { S.rv.role = e.value; });
};
async function rvPerson(emp, key, tab = "results") {
  const p = DATA.rvp = await call("review_person", { emp, key }), C = p.criteria, r = p.row, R = p.record || {};
  const sc = r.cells.find(c => c.key === "score") || {};
  const rows = r.cells.filter(c => c.key !== "score" && (c.value != null || p.peer_median[c.key] != null)).map(c => {
    const part = p.components.find(x => x.key === c.key);
    return `<tr><td>${esc(C[c.key].label)}</td><td class="n rc ${c.status}">${RVF(c.key, c.value)}</td><td class="n">${C[c.key].green == null ? "—" : RVF(c.key, C[c.key].green)}</td>
      <td class="n">${RVF(c.key, p.peer_median[c.key])}</td><td class="n">${part ? part.value.toFixed(1) : "—"}</td><td class="n">${part ? part.share + "%" : "—"}</td></tr>`; }).join("");
  const tabs = [["results", "Results"], ["profile", "Profile"], ["history", "History"]].concat(R.attendance ? [["att", "Attendance"]] : []);
  const factRows = (R.facts || []).map(f => `<tr><td>${esc(f.label)}</td><td><b>${esc(String(f.value ?? ""))}</b>${f.corrected ? ` <span class="chip good">corrected</span>` : ""}</td><td><small class="muted">${esc(f.source || "")}${f.when ? " · " + esc(String(f.when).slice(0, 10)) : ""}</small></td></tr>`).join("");
  const att = R.attendance || {};
  const body = {
    results: `<div class="grid pgrid"><div class="tbl-wrap"><table class="t rtable"><thead><tr><th>Criterion</th><th class="n">Result</th><th class="n">Green from</th><th class="n">Peers</th><th class="n">Points</th><th class="n">Weight</th></tr></thead><tbody>${rows}</tbody></table>
        <small class="muted">Peers: median of the ${p.peers} leaders at the same level. Points: 0-10 against the criterion's lines.</small></div>
      <div><h4 class="ih">What the score is made of</h4><div id="pp-comp"></div>${p.remarks ? `<h4 class="ih">Remarks</h4><div class="il">${esc(p.remarks)}</div>` : ""}
        ${(R.insights || []).length ? `<h4 class="ih">Observations</h4>${R.insights.slice(0, 6).map(i => `<div class="il">${esc(typeof i === "string" ? i : i.text || "")}</div>`).join("")}` : ""}</div></div>`,
    profile: `<div class="grid g2" style="gap:16px"><div><table class="t"><thead><tr><th>Detail</th><th>Value</th><th>Source</th></tr></thead><tbody>${factRows || `<tr><td colspan="3"><div class="empty">No details recorded.</div></td></tr>`}</tbody></table>
        ${r.emp ? `<button class="btn sm" style="margin-top:8px" data-act="rv-fix">Correct a detail…</button>` : ""}</div>
      <div>${(R.reports || []).length ? `<h4 class="ih">Reports to them (${R.reports.length})</h4>${R.reports.slice(0, 12).map(x => `<div class="il">${esc(x.name)} · ${esc(x.designation || "")}</div>`).join("")}` : ""}
        ${(R.corrections || []).length ? `<h4 class="ih">Corrections made</h4>${R.corrections.map(c => `<div class="il">${esc(c.label || c.field)}: ${esc(String(c.old_value ?? "—"))} → <b>${esc(String(c.value ?? ""))}</b> <small class="muted">${esc((c.created_at || "").slice(0, 10))}</small></div>`).join("")}` : ""}
        <h4 class="ih">Sources</h4><small class="muted">${esc((R.sources || []).join(" · ") || "—")}</small></div></div>`,
    history: `<div class="grid g2" style="gap:16px"><div><h4 class="ih">Ratings over time${p.trend ? ` · <span class="${p.trend === "improving" ? "t-good" : p.trend === "slipping" ? "t-bad" : ""}">${esc(p.trend)}</span>` : ""}</h4>${p.ratings.length ? `<div id="pp-rat"></div>` : `<small class="muted">No ratings recorded.</small>`}</div>
      <div><h4 class="ih">Timeline</h4>${(R.timeline || []).length ? `<div class="tline">${R.timeline.slice().reverse().map(t => `<div class="tl"><span class="tl-ic">•</span><div><small>${esc(String(t.date || "").slice(0, 10))}</small><div>${esc(t.what)}</div></div></div>`).join("")}</div>` : `<small class="muted">Nothing recorded yet.</small>`}</div></div>`,
    att: `<div class="pfacts">${[["Presence", att.presence != null ? att.presence + "%" : "—"], ["Days worked", att.worked ?? "—"], ["Absent", att.absent ?? "—"], ["Leave", att.leave ?? "—"], ["Avg. hours", att.avg_hours ?? (att.avg_minutes ? (att.avg_minutes / 60).toFixed(1) : "—")], ["Longest absence", att.longest_absence ?? "—"], ["Punch fixes", att.fixes ?? "—"], ["Month", att.month || "—"]].map(([k, v]) => `<div><small>${k}</small><b>${esc(String(v))}</b></div>`).join("")}</div>`,
  };
  const m = modal(`<div class="row" style="justify-content:space-between;align-items:flex-start"><div><h3 style="margin:0">${esc(r.name)}</h3><small class="muted">${esc(r.role)} · ${esc(r.area)} · ${esc(r.store)}</small></div>
      <div class="pscore ${sc.status}"><b>${RVF("score", sc.value)}</b><small>score / 10</small></div></div>
    <div class="pfacts">${Object.entries(p.facts).map(([k, v]) => `<div><small>${esc(k)}</small><b>${esc(String(v ?? "—"))}</b></div>`).join("")}</div>
    <div class="seg ptabs">${tabs.map(([k, l]) => `<button data-act="rv-ptab" data-t="${k}" aria-pressed="${tab === k}">${l}</button>`).join("")}</div>
    <div class="pbody">${body[tab]}</div>
    <div class="row" style="justify-content:flex-end;margin-top:12px;gap:6px">${r.emp ? `<button class="btn" data-act="rv-pdf" data-emp="${esc(r.emp)}">Data sheet PDF</button>` : ""}<button class="btn primary" data-act="modal-close">Close</button></div>`);
  m.classList.add("wide", "xwide"); m.dataset.emp = emp; m.dataset.key = key;
  const cp = $("#pp-comp", m);
  if (cp) { if (p.components.length) Charts.hbar(cp, { labels: p.components.map(c => `${c.label} (${c.share}%)`), values: p.components.map(c => c.value), max: 10, fmt: "score",
      colors: p.components.map(c => c.value >= 7 ? "#16A34A" : c.value >= 5 ? "#F59E0B" : "#DC2626") });
    else cp.innerHTML = `<small class="muted">Fewer than three criteria measured: no score yet.</small>`; }
  const rt = $("#pp-rat", m);
  if (rt) Charts.columns(rt, { labels: p.ratings.map(x => x.cycle || ""), series: [{ name: "Rating", values: p.ratings.map(x => x.rating), colors: p.ratings.map(x => x.rating >= 4 ? "#16A34A" : x.rating >= 3 ? "#F59E0B" : "#DC2626") }], height: 170, fmt: "score" });
}
async function rvUpdate() {
  let sess;
  if (window.qt) { sess = await call("pick_files", { month: null }); if (sess.cancelled) return; }
  else { const fi = document.createElement("input"); fi.type = "file"; fi.multiple = true;
    const files = await new Promise(res => { fi.onchange = () => res(fi.files); fi.click(); }); if (!files || !files.length) return;
    const out = []; for (const f of files) { const b = new Uint8Array(await f.arrayBuffer()); let bin = ""; for (let i = 0; i < b.length; i += 32768) bin += String.fromCharCode.apply(null, b.subarray(i, i + 32768)); out.push({ name: f.name, b64: btoa(bin) }); }
    sess = await call("import_upload", { files: out, month: null }); }
  rvConfirm(sess);
}
window.PNO_drop = async paths => { if (S.page === "ask") { S.attach.push(...paths); drawChat(); return; } toast(`Reading ${paths.length} file${paths.length > 1 ? "s" : ""}…`); rvConfirm(await call("import_analyze", { paths, month: null })); };
let PENDING_SESS = null, RV_AFTER_FIX = null;
function rvConfirm(sess) {
  PENDING_SESS = sess;
  const sheets = []; (sess.files || []).forEach(f => (f.sheets || f.results || []).forEach(s => sheets.push({ file: f.file || f.name, ...s })));
  // the month the reports themselves carry wins over today's date
  const own = r => (r.period && r.period.sure && r.period.to) || (r.as_of || "").slice(0, 7) || null;    // a month the sheet itself shows
  const seen = {}; (sess.files || []).forEach(f => (f.results || []).forEach(r => { const m0 = own(r); if (m0) seen[m0] = (seen[m0] || 0) + 1; }));
  const best = Object.entries(seen).sort((a, b) => b[1] - a[1])[0];
  const month = (best && best[0]) || sess.suggested_month || sess.month || new Date().toISOString().slice(0, 7);
  const m = modal(`<h3>Update data</h3><p class="muted" style="margin:0 0 10px">P&amp;O read these files. Check the month, then save.</p>
    <div class="ulist">${sheets.map(s => `<div class="uitem"><b>${esc(s.label || s.kind_label || s.kind || "Sheet")}${own(s) ? ` <span class="chip">${esc(own(s))}</span>` : ""}</b><small>${esc(s.file || "")} · ${esc(s.sheet || "")}${s.summary ? " · " + esc(s.summary) : ""}</small>
      ${(s.warnings || []).filter(w => !(own(s) && /no date inside it|choose the month/i.test(w))).slice(0, 2).map(w => `<small class="t-warn">⚠ ${esc(w)}</small>`).join("")}</div>`).join("") || `<div class="empty">Nothing usable in these files.</div>`}</div>
    ${(sess.errors || []).map(e => `<div class="il bad">${esc(e.file || "")}: ${esc(e.error || e)}</div>`).join("")}
    <div class="row" style="justify-content:space-between;margin-top:12px"><label class="dx-l" style="margin:0">Month for files with no date<input class="input" type="month" id="u-m" value="${esc(month)}"></label>
      <div class="row" style="gap:6px"><button class="btn" data-act="modal-close">Cancel</button><button class="btn" data-act="rv-detail" title="Change a file's month, period or type, fix columns, see every warning">Check in detail…</button><button class="btn primary" id="u-go" ${sheets.length ? "" : "disabled"}>Save</button></div></div>`);
  m.classList.add("wide");
  $("#u-go", m).onclick = async () => { const b = $("#u-go", m); b.disabled = true; b.textContent = "Saving…";
    try { const mo = $("#u-m", m).value, opts = {};
      (sess.files || []).forEach(f => (f.results || []).forEach(r => { if (!r.month || (r.needs || []).includes("month")) ((opts[f.file] = opts[f.file] || {})[r.sheet] = { month: own(r) || mo }); }));
      await API.call("import_commit", { token: sess.token, options: opts });
      closeModal(); toast("Data updated"); await afterDataChange(true); go("rv"); } catch (e) { b.disabled = false; b.textContent = "Save"; fail(e); } };
}
const RV_ACTS = {
  "rv-dept": b => { Object.assign(S.rv, { dept: b.dataset.v, section: "", sort: null }); render(); },
  "rv-sec": b => { S.rv.section = b.dataset.v; render(); },
  "rv-role": b => { S.rv.role = b.dataset.v; render(); },
  "rv-crumb": b => { const i = +b.dataset.i; if (i === 0) Object.assign(S.rv, { store: "", dept: "", section: "" }); else if (i === 1 && S.rv.store) Object.assign(S.rv, { dept: "", section: "" }); else S.rv.section = ""; render(); },
  "rv-drill": b => { Object.assign(S.rv, DATA.rv.grid[+b.dataset.i].go); render(); },
  "rv-sort": b => { const k = b.dataset.k; if (S.rv.sort === k) { if (S.rv.desc) S.rv.sort = null; else S.rv.desc = true; } else { S.rv.sort = k; S.rv.desc = false; } render(); },
  "rv-person": b => rvPerson(b.dataset.emp, b.dataset.key),
  "rv-fix": b => { const p = DATA.rvp, m = b.closest(".modal"); DATA.brp = { name: p.row.name, emp: p.row.emp, facts: (p.record || {}).facts || [] };
    closeModal(); brainFix("designation"); RV_AFTER_FIX = [m.dataset.emp, m.dataset.key]; },
  "rv-ptab": b => { const m = b.closest(".modal"); closeModal(); rvPerson(m.dataset.emp, m.dataset.key, b.dataset.t); },
  "rv-pdf": async b => { const r = await call("profile_export", { emp: b.dataset.emp, fmt: "pdf" }); if (!r.cancelled) toast("Data sheet saved"); },
  "rv-update": () => rvUpdate(),
  "rv-clear": () => { Object.assign(S.rv, { store: "", dept: "", section: "", role: "", sort: null }); render(); },
  "rv-detail": () => { S.importSess = PENDING_SESS; closeModal(); go("import"); },
  "rv-settings": () => go("settings"),
};
SETTINGS.bench = async () => {
  const t = DATA.crit = await API.call("review_criteria", {});
  const u = r => ({ pct0: "%", pct1: "%", pct1s: "%", pp2s: " pts" }[r.fmt] || "");
  return `<div class="panel"><div class="phd"><h2>Criteria</h2><small>what the Review shows, how much each counts in the score, and where the colours start</small></div>
    <p class="muted" style="margin:0 0 12px">Each result becomes points out of 10 against its own lines: at the amber line it earns 5, at the green line 7, and 10 once it is as far past green as amber is below it (none at all for leavers and cases).
      The score is the weighted average of those points. A weight of 0 shows the criterion without counting it; switch it off to hide it everywhere.</p>
    <div class="tbl-wrap"><table class="t crit"><thead><tr><th>Criterion</th><th>Show</th><th class="n">Weight</th><th class="n">Share of score</th><th>Better when</th><th class="n">Green from</th><th class="n">Amber from</th></tr></thead><tbody>
    ${t.rows.map(r => `<tr data-ck="${r.key}"><td><b>${esc(r.label)}</b>${r.count ? `<span class="sub">per person; store and country totals are shown without colour</span>` : ""}</td>
      <td><label class="switch"><input type="checkbox" data-cf="show" ${r.show ? "checked" : ""}><span></span></label></td>
      <td class="n"><input class="input sm num" type="number" min="0" max="100" step="1" data-cf="weight" value="${r.weight}"></td>
      <td class="n"><div class="share"><i style="width:${r.share}%"></i><b>${r.share}%</b></div></td>
      <td>${r.better === "up" ? "Higher" : "Lower"}</td>
      <td class="n"><input class="input sm num" type="number" step="any" data-cf="green" value="${r.green ?? ""}"><small>${u(r)}</small></td>
      <td class="n"><input class="input sm num" type="number" step="any" data-cf="amber" value="${r.amber ?? ""}"><small>${u(r)}</small></td></tr>`).join("")}</tbody></table></div>
    <div class="row" style="justify-content:space-between;margin-top:12px"><small class="muted">Total weight ${t.total}. Score colours: green from ${t.score.green}, amber from ${t.score.amber}.</small>
      <div class="row" style="gap:6px"><button class="btn" data-act="tg-reset">Reset to defaults</button><button class="btn primary" data-act="crit-save">Save criteria</button></div></div></div>`;
};
Object.assign(RV_ACTS, {
  "tg-reset": async () => { await call("review_criteria", { reset: true }); toast("Criteria reset to defaults"); render(); },
  "crit-save": async () => {
    const rows = $$("tr[data-ck]").map(tr => ({ key: tr.dataset.ck, show: $("[data-cf=show]", tr).checked, weight: +$("[data-cf=weight]", tr).value || 0,
      green: $("[data-cf=green]", tr).value, amber: $("[data-cf=amber]", tr).value }));
    await call("review_criteria", { rows }); toast("Criteria saved: the Review and every score use them now"); render(); },
});

async function hireVacancy(head) {
  const H = S.hire;
  const v = DATA.hvac = await API.call("hire_vacancy", { vacancy_id: H.vid, blind: H.blind });
  const b = v.bands;
  const rows = v.apps.map((a, i) => `<tr class="click" data-act="h-cand" data-id="${a.candidate_id}">
      <td class="n">${i + 1}</td><td><b>${esc(a.name)}</b>${a.source === "Internal" ? ` <span class="chip gold">Internal</span>` : ""}<span class="sub">${esc(a.level || "level not found")}${a.retailers.length ? " · " + esc(a.retailers.join(", ")) : ""}</span></td>
      <td style="min-width:130px">${hBar(a.score, a.band)}</td><td>${hBand(a.band)}</td>
      <td class="n">${a.years ?? "—"}</td><td class="n">${a.retail_years ?? "—"}</td><td>${esc(a.city || "—")}</td>
      <td>${a.knockouts.length ? `<span class="chip bad" title="${esc(a.knockouts.join("; "))}">knock-out</span>` : ""}${a.flags.length ? `<span class="chip warn" title="${esc(a.flags.join("; "))}">${a.flags.length} to ask</span>` : ""}${a.tags.length ? `<span class="chip info" title="${esc(a.tags.join("; "))}">history</span>` : ""}</td>
      <td><select class="input sm" data-hstage="${a.id}">${Object.entries(HSTAGE).map(([k, l]) => `<option value="${k}" ${k === a.stage ? "selected" : ""}>${l}</option>`).join("")}</select></td>
      <td class="n">${a.panel == null ? "" : a.panel.toFixed(1) + "/5"}</td></tr>`).join("");
  const internal = v.internal.length ? `<div class="panel"><div class="phd"><h2>Already in the business</h2><small>People one level below in the same area who could step up</small></div>
      <div class="hint-list">${v.internal.slice(0, 6).map(p => `<div><b>${esc(p.name)}</b><small>${esc(p.role)} · ${esc(p.store)} · ${esc(p.leads)}${p.index != null ? ` · index ${(p.index / 10).toFixed(1)}` : ""}${p.rating != null ? ` · rating ${p.rating}` : ""}</small></div>`).join("")}</div></div>` : "";
  return head(esc(v.title), `${esc([v.store, v.section].filter(Boolean).join(" · ") || "Any store")} · ${v.headcount} post${v.headcount > 1 ? "s" : ""} · open ${v.days_open ?? 0} days · ${v.apps.length} CVs`,
      `<button class="btn ghost" data-act="h-back">${ic("back", 15)}All vacancies</button><label class="switch-l" title="Hide names and contact details while reviewing"><input type="checkbox" id="h-blind" ${H.blind ? "checked" : ""}> Blind review</label>
       <button class="btn" data-act="h-edit">Edit</button><div class="menu-wrap"><button class="btn" data-act="h-expmenu">${ic("export", 15)}Export ▾</button><div class="cmenu" id="h-exp" hidden>
       <button data-act="h-export" data-fmt="pdf"><b>Shortlist PDF</b><small>ranked list and the top 6 profiles with evidence</small></button><button data-act="h-export" data-fmt="pptx"><b>PowerPoint</b><small>for the hiring meeting</small></button><button data-act="h-export" data-fmt="xlsx"><b>Excel</b><small>every candidate and score</small></button></div></div>`) +
    `<div class="seg vtabs"><button data-act="h-vtab" data-t="internal" aria-pressed="${(H.vtab || "internal") === "internal"}">🏢 Internal talent first</button><button data-act="h-vtab" data-t="external" aria-pressed="${H.vtab === "external"}">🌐 Candidates (${v.apps.length})</button></div>
    ${(H.vtab || "internal") === "internal" ? `<div id="h-internal"><div class="skel" style="height:180px"></div></div>` : `<div class="kpis k5">
      <div class="kpi"><span class="kpi-l">CVs screened</span><span class="kpi-v">${v.apps.length}</span><span class="kpi-s"><span>${v.funnel.find(f => f.stage === "interview1").count} in interview</span></span></div>
      <div class="kpi"><span class="kpi-l">Strong · interview</span><span class="kpi-v t-good">${b.strong}</span><span class="kpi-s"><span>score 75+</span></span></div>
      <div class="kpi"><span class="kpi-l">Possible · phone screen</span><span class="kpi-v">${b.possible}</span><span class="kpi-s"><span>55–74</span></span></div>
      <div class="kpi"><span class="kpi-l">Weak · hold</span><span class="kpi-v">${b.weak}</span><span class="kpi-s"><span>35–54</span></span></div>
      <div class="kpi"><span class="kpi-l">Not suitable</span><span class="kpi-v">${b.no}</span><span class="kpi-s"><span>below 35 or knock-out</span></span></div></div>
    <div class="drop hdrop" id="hdrop"><div class="row" style="gap:14px;align-items:center;justify-content:center"><div class="ic">${ic("attach", 22)}</div>
      <div style="text-align:left"><b>Drop CVs here</b><br><small style="color:var(--muted)">PDF, Word or text · hundreds at once · the same person twice is merged</small></div>
      <button class="btn primary" data-act="h-pick">${ic("file", 15)}Choose CVs</button><button class="btn" data-act="h-matchbank">Find in talent bank</button></div>
      <input type="file" id="hfile" multiple hidden accept=".pdf,.docx,.doc,.txt,.rtf"></div>
    <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Ranked candidates</h2><small>Click a candidate for the score breakdown, interview kit and messages</small></div>
      <div class="tbl-wrap"><table class="t"><thead><tr><th class="n">#</th><th>Candidate</th><th>Match</th><th>Recommendation</th><th class="n">Years</th><th class="n">Retail</th><th>City</th><th>Checks</th><th>Stage</th><th class="n">Panel</th></tr></thead>
      <tbody>${rows || `<tr><td colspan="10"><div class="empty">No CVs yet. Drop them above.</div></td></tr>`}</tbody></table></div></div>
`}
    <details class="panel"><summary style="cursor:pointer"><h2 style="display:inline;margin:0">Job description</h2></summary><div class="md">${md(v.jd || "")}</div></details>`;
}

async function hireCandidate(cid) {
  const H = S.hire;
  H.cand = cid;
  const c = DATA.hcand = await API.call("hire_candidate", { candidate_id: cid, vacancy_id: H.vid, blind: H.blind });
  const app = c.applications.find(a => a.vacancy_id === H.vid) || c.applications[0];
  const p = c.parsed || {};
  const r = app ? app.result : null;
  const tabs = [["assess", "Assessment"], ["interview", "Interview"], ["msg", "Messages"], ["onboard", "Onboarding"], ["cv", "CV"], ["notes", "Notes"]];
  let body = "";
  if (!app) body = `<div class="empty">Not applied to a vacancy yet.</div>`;
  else if (H.ctab === "assess") {
    body = `<table class="t hparts"><thead><tr><th>Criterion</th><th class="n">Points</th><th>Finding</th></tr></thead><tbody>${r.parts.map(x => `<tr><td><b>${esc(x.label)}</b></td>
        <td class="n"><div class="hbarw"><div class="hbarv ${x.value >= 0.99 ? "strong" : x.value >= 0.5 ? "possible" : "weak"}" style="width:${Math.max(2, 100 * x.value)}px"></div><b>${x.points.toFixed(0)}<small style="display:inline;color:var(--muted)">/${x.max.toFixed(0)}</small></b></div></td>
        <td>${esc(x.why)}${x.evidence ? `<span class="sub">“${esc(x.evidence)}”</span>` : ""}</td></tr>`).join("")}</tbody></table>
      <div class="grid g2" style="margin-top:12px"><div><h4>Strengths</h4>${(r.strengths || []).map(s => `<div class="alert good"><span class="ic">✓</span><span>${esc(s)}</span></div>`).join("") || "<small>—</small>"}</div>
      <div><h4>Gaps and checks</h4>${[...(r.knockouts || []).map(x => ["bad", x]), ...(r.gaps || []).map(x => ["warn", x]), ...(r.flags || []).map(x => ["warn", "Ask: " + x]), ...(r.tags || []).map(x => ["", x])].map(([k, x]) => `<div class="alert ${k}"><span class="ic">${k === "bad" ? "!" : "•"}</span><span>${esc(x)}</span></div>`).join("") || "<small>—</small>"}</div></div>
      <div class="panel" style="margin-top:12px"><div class="phd"><h2>AI assessment</h2><button class="btn sm primary" data-act="h-ai" data-app="${app.id}">${ic("spark", 13)}${app.ai && app.ai.text ? "Ask again" : "Assess with AI"}</button></div>
        <div class="md" id="h-ai-box">${app.ai && app.ai.text ? md(app.ai.text) : `<small style="color:var(--muted)">The AI reads the CV with personal details removed and the JD, then writes a verdict, strengths, concerns and what to ask.</small>`}</div></div>`;
  } else if (H.ctab === "interview") {
    const kit = app.kit;
    const comps = kit ? kit.competencies : [];
    body = `<div class="row" style="justify-content:space-between"><b>Interview kit</b><button class="btn sm primary" data-act="h-kit" data-app="${app.id}">${ic("spark", 13)}${kit ? "Make again" : "Make interview kit"}</button></div>
      ${kit ? `<ol class="hq">${kit.questions.map(q => `<li><span class="chip ${q.type === "gap" ? "warn" : q.type === "flag" ? "bad" : q.type === "ai" ? "info" : ""}">${esc(q.area)}</span> ${esc(q.q)}</li>`).join("")}</ol>` : `<p style="color:var(--muted)">Questions for the role's competencies, the gaps in this CV and anything to check.</p>`}
      <h4 style="margin-top:16px">Panel scorecard</h4>
      ${app.panel.map(pn => `<div class="hpanel"><b>${esc(pn.interviewer)}</b> · ${Object.entries(pn.scores).map(([k, v]) => `${esc(k)} <b>${v}</b>`).join(" · ")}${pn.decision ? ` · <span class="chip">${esc(pn.decision)}</span>` : ""}${pn.note ? `<br><small>${esc(pn.note)}</small>` : ""}</div>`).join("")}
      ${app.panel_avg != null ? `<p><b>Panel average: ${app.panel_avg.toFixed(2)} / 5</b></p>` : ""}
      <div class="hform" style="margin-top:8px"><label class="dx-l">Interviewer<input class="input" id="hp-who" placeholder="Your name"></label>
        ${(comps.length ? comps : ["Overall fit", "Experience", "Communication"]).map(cn => `<label class="dx-l">${esc(cn)}<select class="input" data-hp="${esc(cn)}"><option value="">—</option>${[1, 2, 3, 4, 5].map(n => `<option>${n}</option>`).join("")}</select></label>`).join("")}
        <label class="dx-l">Decision<select class="input" id="hp-dec"><option value="">—</option><option>Hire</option><option>Second interview</option><option>Hold</option><option>Do not hire</option></select></label></div>
      <textarea class="input" id="hp-note" rows="2" placeholder="Notes" style="width:100%;margin-top:6px"></textarea>
      <div class="row" style="justify-content:flex-end"><button class="btn primary" data-act="h-panel" data-app="${app.id}">Save scores</button></div>`;
  } else if (H.ctab === "msg") {
    body = `<div class="hform"><label class="dx-l">Message<select class="input" id="hm-kind"><option value="invite">Interview invitation</option><option value="offer">Offer</option><option value="regret">Regret (not selected)</option></select></label>
        <label class="dx-l">Language<select class="input" id="hm-lang"><option value="en">English</option><option value="ur">اردو Urdu</option></select></label>
        <label class="dx-l">Date and time<input class="input" id="hm-when" placeholder="e.g. Tuesday 3 Nov, 11:00"></label><label class="dx-l">Place<input class="input" id="hm-place" placeholder="${esc(DATA.hvac ? DATA.hvac.store || "" : "")}"></label></div>
      <div class="row" style="justify-content:flex-end"><button class="btn primary" data-act="h-msg" data-app="${app.id}">Write message</button></div>
      <textarea class="input" id="hm-text" rows="10" style="width:100%;margin-top:8px"></textarea>
      <div class="row" style="justify-content:flex-end"><button class="btn" data-act="h-copy">Copy</button></div>`;
  } else if (H.ctab === "onboard") {
    const ob = app.onboarding || {};
    body = `<p style="color:var(--muted)">Track joining paperwork and first-week steps. Document numbers are never stored, only whether each step is done.</p>
      <div class="hlist">${app.checklist.map(it => `<label class="hrow" style="cursor:pointer"><input type="checkbox" data-hob="${esc(it)}" data-app="${app.id}" ${ob[it] ? "checked" : ""}><b>${esc(it)}</b><small>${ob[it] ? "done " + ob[it] : ""}</small></label>`).join("")}</div>`;
  } else if (H.ctab === "cv") {
    body = `<p style="color:var(--muted)">CV text as stored: age, marital status, religion, CNIC and similar details are removed.</p><pre class="hcv">${esc(c.text || "(anonymised)")}</pre>`;
  } else {
    body = `<textarea class="input" id="hc-notes" rows="8" style="width:100%" placeholder="Notes about this candidate">${esc(c.notes)}</textarea>
      <label class="switch-l" style="margin:10px 0"><input type="checkbox" id="hc-bank" ${c.bank ? "checked" : ""}> Keep in the talent bank for future roles</label>
      <div class="row" style="justify-content:space-between"><button class="btn ghost danger" data-act="h-cdel" data-id="${c.id}">Delete candidate and CV</button><button class="btn primary" data-act="h-cnotes" data-id="${c.id}">Save</button></div>`;
  }
  const facts = [p.top_level_label, p.years_total != null ? `${p.years_total} yrs` : "", p.years_retail ? `${p.years_retail} yrs retail` : "", p.education, c.city].filter(Boolean);
  const html = `<div class="hdraw-h"><button class="btn sm ghost" data-act="h-cclose">${ic("x", 15)}</button>
      <div class="row" style="gap:14px;align-items:center">${app ? `<div class="hscore ${app.band}">${Math.round(app.score)}</div>` : ""}<div><h2 style="margin:0">${esc(c.name)}</h2>
      <small style="color:var(--muted)">${esc(facts.join(" · "))}</small>${!H.blind && (c.email || c.phone) ? `<br><small>${esc([c.email, c.phone].filter(Boolean).join(" · "))}</small>` : ""}</div></div>
      ${app ? `<div class="row" style="margin-top:8px">${hBand(app.band)}<select class="input sm" data-hstage="${app.id}">${Object.entries(HSTAGE).map(([k, l]) => `<option value="${k}" ${k === app.stage ? "selected" : ""}>${l}</option>`).join("")}</select>
        ${(p.retailers || []).map(x => `<span class="chip">${esc(x)}</span>`).join("")}</div>` : ""}
      <div class="seg" style="margin-top:12px">${tabs.map(([k, l]) => `<button data-act="h-ctab" data-tab="${k}" aria-pressed="${H.ctab === k}">${l}</button>`).join("")}</div></div>
    <div class="hdraw-b">${body}</div>`;
  let d = $("#hdraw");
  if (!d) { d = document.createElement("aside"); d.id = "hdraw"; d.className = "hdraw"; document.body.append(d); requestAnimationFrame(() => d.classList.add("on")); }
  d.innerHTML = html;
}
function hireCloseCand() { const d = $("#hdraw"); if (d) { d.classList.remove("on"); setTimeout(() => d.remove(), 250); } S.hire.cand = null; }

async function hirePipeline(head) {
  const H = S.hire;
  const list = (DATA.hiring && DATA.hiring.rows) || (await API.call("hire_list")).rows;
  if (!H.vid && list.length) H.vid = (list.find(v => v.status === "open") || list[0]).id;
  if (!H.vid) return head("Pipeline", "Create a vacancy first.") + `<div class="empty">No vacancies yet.</div>`;
  const v = DATA.hvac = await API.call("hire_vacancy", { vacancy_id: H.vid, blind: H.blind });
  const cols = ["applied", "screened", "interview1", "interview2", "offer", "joined", "rejected"];
  return head("Pipeline", "Drag candidates between stages. Every move is kept in their history.",
      `<select class="input" id="h-pv">${list.map(x => `<option value="${x.id}" ${x.id === H.vid ? "selected" : ""}>${esc(x.title)}${x.store ? " · " + esc(x.store) : ""}</option>`).join("")}</select>`) +
    `<div class="hboard">${cols.map(st => { const cs = v.apps.filter(a => a.stage === st || (st === "rejected" && a.stage === "withdrawn"));
      return `<div class="hcol" data-hdrop="${st}"><div class="hcol-h"><b>${HSTAGE[st]}</b><span class="chip">${cs.length}</span></div>
        ${cs.map(a => `<div class="hpcard" draggable="true" data-hdrag="${a.id}" data-act="h-cand" data-id="${a.candidate_id}"><div class="row" style="justify-content:space-between"><b>${esc(a.name)}</b><span class="hmini ${a.band}">${Math.round(a.score)}</span></div>
          <small>${esc(a.level || "")}${a.years != null ? " · " + a.years + " yrs" : ""}</small>${a.panel != null ? `<small>panel ${a.panel.toFixed(1)}/5</small>` : ""}</div>`).join("") || `<div class="hcol-e">—</div>`}</div>`; }).join("")}</div>`;
}

async function hireBank(head) {
  const H = S.hire;
  const d = await API.call("hire_bank", { q: H.q, skill: H.skill, city: H.city, min_years: +H.years || 0 });
  const vacs = ((DATA.hiring && DATA.hiring.rows) || (await API.call("hire_list")).rows).filter(v => v.status === "open");
  return head("Talent bank", `${d.total.toLocaleString("en-US")} people from every CV ever added. Search by skill, city or experience and add them to an open vacancy.`) +
    `<div class="panel"><div class="row" style="gap:8px;flex-wrap:wrap"><input class="input" id="hb-q" placeholder="Search names, employers, anything in the CV" value="${esc(H.q)}" style="flex:1;min-width:220px">
      <select class="input" id="hb-skill"><option value="">Any skill</option>${d.skills.map(s => `<option ${s === H.skill ? "selected" : ""}>${esc(s)}</option>`).join("")}</select>
      <select class="input" id="hb-city"><option value="">Any city</option>${d.cities.map(s => `<option ${s === H.city ? "selected" : ""}>${esc(s)}</option>`).join("")}</select>
      <select class="input" id="hb-years"><option value="">Any experience</option>${[1, 2, 3, 5, 8, 10].map(n => `<option value="${n}" ${String(n) === String(H.years) ? "selected" : ""}>${n}+ years</option>`).join("")}</select></div>
      ${vacs.length ? `<div class="row" style="margin-top:10px"><small style="color:var(--muted)">Selected: <b id="hb-n">${H.sel.size}</b></small><select class="input sm" id="hb-vac">${vacs.map(v => `<option value="${v.id}">${esc(v.title)}</option>`).join("")}</select><button class="btn sm primary" data-act="hb-add">Add selected to vacancy</button></div>` : ""}</div>
    <div class="panel flush"><div class="tbl-wrap"><table class="t"><thead><tr><th></th><th>Name</th><th>Highest role</th><th class="n">Years</th><th class="n">Retail</th><th>City</th><th>Skills</th><th>Applied for</th><th>Added</th></tr></thead><tbody>
    ${d.rows.map(r => `<tr><td><input type="checkbox" data-hbsel="${r.id}" ${H.sel.has(r.id) ? "checked" : ""}></td><td class="click" data-act="h-cand" data-id="${r.id}"><b>${esc(r.name)}</b>${r.bank ? "" : `<span class="sub">not kept in bank</span>`}</td><td>${esc(r.level || "—")}</td><td class="n">${r.years ?? "—"}</td><td class="n">${r.retail_years ?? "—"}</td>
      <td>${esc(r.city || "—")}</td><td><small>${esc(r.skills.join(", "))}</small></td><td><small>${esc(r.applied.join(" · ") || "—")}</small></td><td class="nw">${esc(r.added)}</td></tr>`).join("") || `<tr><td colspan="9"><div class="empty">Nobody matches.</div></td></tr>`}</tbody></table></div></div>`;
}

async function hireStats(head) {
  const d = DATA.hstats = await API.call("hire_analytics");
  const set = await API.call("hire_settings", {});
  const k = (l, v, s) => `<div class="kpi"><span class="kpi-l">${esc(l)}</span><span class="kpi-v">${v}</span><span class="kpi-s"><span>${esc(s)}</span></span></div>`;
  return head("Hiring analytics", "How fast roles are filled, where good candidates come from and how the funnel converts.") +
    `<div class="kpis k5">${k("Open vacancies", d.open, d.avg_days_open != null ? `open ${d.avg_days_open} days on average` : "none open")}${k("Time to hire", d.time_to_hire != null ? d.time_to_hire + "<small> days</small>" : "—", "vacancy opened → joined")}
      ${k("Offer acceptance", d.offer_acceptance != null ? d.offer_acceptance.toFixed(0) + "%" : "—", d.offers_pending ? `${d.offers_pending} offer${d.offers_pending > 1 ? "s" : ""} still open` : "decided offers that joined")}${k("Hires", d.hires, `${d.filled} vacancies filled`)}${k("Talent bank", d.bank.toLocaleString("en-US"), "people on file")}</div>
    <div class="grid g2"><div class="panel"><div class="phd"><h2>Funnel</h2><small>every CV ever added to a vacancy</small></div><div id="ch-hfunnel"></div></div>
      <div class="panel"><div class="phd"><h2>Recommendations</h2><small>bands across all CVs</small></div><div id="ch-hbands"></div></div></div>
    <div class="grid g2"><div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Sources</h2><small>which source brings people who get hired</small></div><div class="tbl-wrap"><table class="t"><thead><tr><th>Source</th><th class="n">CVs</th><th class="n">Interviewed</th><th class="n">Joined</th></tr></thead><tbody>
      ${d.sources.map(s => `<tr><td>${esc(s.source)}</td><td class="n">${s.cvs}</td><td class="n">${s.interviewed}</td><td class="n">${s.joined}</td></tr>`).join("") || `<tr><td colspan="4"><div class="empty">—</div></td></tr>`}</tbody></table></div></div>
      <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Longest open</h2></div><div class="tbl-wrap"><table class="t"><thead><tr><th>Vacancy</th><th>Store</th><th class="n">Days open</th></tr></thead><tbody>
      ${d.oldest.map(o => `<tr><td>${esc(o.title)}</td><td>${esc(o.store || "—")}</td><td class="n">${o.days}</td></tr>`).join("") || `<tr><td colspan="3"><div class="empty">No open vacancies.</div></td></tr>`}</tbody></table></div></div></div>
    <div class="panel"><div class="phd"><h2>Candidate data</h2></div><div class="setting"><div><b>Keep CVs of people not in the talent bank for</b><small>After this, their CV file is deleted and their record is anonymised. People kept in the talent bank stay.</small></div>
      <div class="row"><input class="input sm" type="number" min="1" id="h-keep" value="${set.keep_months}" style="width:70px"> months <button class="btn sm" data-act="h-keep">Save</button></div></div></div>`;
}
AFTER.hiring = () => {
  if (S.hire.tab === "vac" && S.hire.vid && (S.hire.vtab || "internal") === "internal") drawInternal();
  const H = S.hire;
  const bl = $("#h-blind"); if (bl) bl.onchange = () => { H.blind = bl.checked; render(); };
  const fi = $("#hfile"), dz = $("#hdrop");
  if (fi) fi.onchange = () => { if (fi.files.length) hireAddFiles(fi.files); };
  if (dz) {
    ["dragenter", "dragover"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add("over"); }));
    ["dragleave", "drop"].forEach(ev => dz.addEventListener(ev, () => dz.classList.remove("over")));
    dz.addEventListener("drop", e => { e.preventDefault(); e.stopPropagation(); if (e.dataTransfer.files.length && !window.qt) hireAddFiles(e.dataTransfer.files); });
  }
  const pv = $("#h-pv"); if (pv) pv.onchange = () => { H.vid = +pv.value; render(); };
  $$("[data-hdrag]").forEach(c => c.addEventListener("dragstart", e => { e.dataTransfer.setData("text/plain", c.dataset.hdrag); c.classList.add("dragging"); }));
  $$("[data-hdrop]").forEach(col => {
    col.addEventListener("dragover", e => { e.preventDefault(); col.classList.add("over"); });
    col.addEventListener("dragleave", () => col.classList.remove("over"));
    col.addEventListener("drop", async e => { e.preventDefault(); e.stopPropagation(); col.classList.remove("over"); const id = e.dataTransfer.getData("text/plain"); if (!id) return;
      await call("hire_stage", { app_id: +id, stage: col.dataset.hdrop }); toast("Moved to " + HSTAGE[col.dataset.hdrop]); render(); });
  });
  const q = $("#hb-q"); if (q) q.addEventListener("input", () => { clearTimeout(H.t); H.t = setTimeout(() => { H.q = q.value; render(); }, 300); });
  [["hb-skill", "skill"], ["hb-city", "city"], ["hb-years", "years"]].forEach(([id, k]) => { const el = $("#" + id); if (el) el.onchange = () => { H[k] = el.value; render(); }; });
  if (DATA.hstats && $("#ch-hfunnel")) {
    const f = DATA.hstats.funnel; Charts.funnel($("#ch-hfunnel"), { labels: f.map(x => x.label), values: f.map(x => x.count) });
    const b = DATA.hstats.bands; if (Charts.donut) Charts.donut($("#ch-hbands"), { labels: ["Strong", "Possible", "Weak", "Not suitable"], values: [b.strong, b.possible, b.weak, b.no], colors: ["#2E7D4F", "#3A6EA5", "#C9821F", "#B3261E"] });
  }
  if (H.cand && S.page === "hiring" && !$("#hdraw")) hireCandidate(H.cand);
};
document.addEventListener("change", async e => {
  const st = e.target.closest && e.target.closest("[data-hstage]");
  if (st) { await call("hire_stage", { app_id: +st.dataset.hstage, stage: st.value }); toast("Stage: " + HSTAGE[st.value]); if (S.page === "hiring") { const keep = S.hire.cand; await render(); if (keep) hireCandidate(keep); } return; }
  const ob = e.target.closest && e.target.closest("[data-hob]");
  if (ob) { await call("hire_onboarding", { app_id: +ob.dataset.app, item: ob.dataset.hob, done: ob.checked }); hireCandidate(S.hire.cand); return; }
  const sel = e.target.closest && e.target.closest("[data-hbsel]");
  if (sel) { const id = +sel.dataset.hbsel; sel.checked ? S.hire.sel.add(id) : S.hire.sel.delete(id); const n = $("#hb-n"); if (n) n.textContent = S.hire.sel.size; }
});
const HIRE_ACTS = {
  "h-tab": b => { S.hire.tab = b.dataset.tab; if (b.dataset.tab === "vac") S.hire.vid = null; hireCloseCand(); render(); },
  "h-open": b => { S.hire.vid = +b.dataset.id; S.hire.tab = "vac"; render(); },
  "h-back": () => { S.hire.vid = null; hireCloseCand(); render(); },
  "h-new": async () => { if (!DATA.hiring) DATA.hiring = await API.call("hire_list"); const d = await call("hire_draft", { role: "section_manager" }); hireOpenForm({ ...d, title: "", headcount: 1 }); },
  "h-edit": () => hireOpenForm(DATA.hvac),
  "h-draft": async () => {
    const d = await call("hire_draft", { title: $("#hv-title").value, role: $("#hv-role").value, store: $("#hv-store").value, section: $("#hv-section").value, category: $("#hv-cat").value });
    if (!$("#hv-title").value) $("#hv-title").value = d.title;
    $("#hv-jd").value = d.jd; S.hire.form = { ...S.hire.form, rubric: d.rubric, role: d.role };
    const keep = { title: $("#hv-title").value, role: d.role, category: $("#hv-cat").value, store: $("#hv-store").value, section: $("#hv-section").value, headcount: +$("#hv-head").value, manager: $("#hv-mgr").value, target_date: $("#hv-date").value, jd: d.jd, rubric: d.rubric, id: S.hire.form.id, status: S.hire.form.status };
    hireOpenForm(keep);
  },
  "h-aijd": async b => { b.disabled = true; b.innerHTML = `<span class="spin" style="width:13px;height:13px"></span> Writing…`;
    try { const d = await call("hire_ai_jd", { title: $("#hv-title").value || "Section Manager", store: $("#hv-store").value, section: $("#hv-section").value, notes: $("#hv-jd").value.slice(0, 1500) });
      $("#hv-jd").value = d.jd; toast(d.note || "JD written by " + (d.engine || "AI"), { err: !!d.note }); } finally { b.disabled = false; b.innerHTML = `${ic("spark", 13)}Write with AI`; } },
  "h-save": async b => {
    const f = S.hire.form || {};
    const v = { id: b.dataset.id ? +b.dataset.id : null, title: $("#hv-title").value.trim(), role: $("#hv-role").value, category: $("#hv-cat").value, store: $("#hv-store").value.trim(),
      section: $("#hv-section").value.trim(), headcount: +$("#hv-head").value || 1, manager: $("#hv-mgr").value.trim(), target_date: $("#hv-date").value || null,
      jd: $("#hv-jd").value, rubric: hireRubricFromForm(f.rubric), status: $("#hv-status") ? $("#hv-status").value : "open" };
    if (!v.title) return toast("Give the vacancy a title.", { err: true });
    const r = await call("hire_save", v); closeModal(); toast(v.id ? "Saved · CVs re-scored" : "Vacancy created · now drop in CVs"); S.hire.vid = r.id; S.hire.tab = "vac"; render();
  },
  "h-del": async b => { if (!confirm("Delete this vacancy? Candidates stay in the talent bank.")) return; await call("hire_delete", { vacancy_id: +b.dataset.id }); closeModal(); S.hire.vid = null; render(); },
  "h-pick": async () => { if (window.qt) { const r = await call("hire_pick", { vacancy_id: S.hire.vid }); hireAfterAdd(r); } else $("#hfile").click(); },
  "h-matchbank": async () => {
    const r = await call("hire_match_bank", { vacancy_id: S.hire.vid });
    const m = modal(`<h3>From the talent bank</h3><p style="color:var(--muted);margin:0 0 10px">People who applied before and fit this vacancy (strong or possible).</p>
      ${r.rows.length ? `<div class="tbl-wrap" style="max-height:360px"><table class="t"><tbody>${r.rows.map(x => `<tr><td><input type="checkbox" data-mb="${x.id}" checked></td><td><b>${esc(x.name)}</b><span class="sub">${esc(x.city)}</span></td><td>${hBar(x.score, x.band)}</td><td>${hBand(x.band)}</td></tr>`).join("")}</tbody></table></div>` : `<div class="empty">Nobody in the bank fits yet.</div>`}
      <div class="row" style="justify-content:flex-end;margin-top:10px"><button class="btn" data-act="modal-close">Close</button>${r.rows.length ? `<button class="btn primary" id="mb-add">Add to vacancy</button>` : ""}</div>`);
    const btn = $("#mb-add", m); if (btn) btn.onclick = async () => { const ids = $$("[data-mb]", m).filter(i => i.checked).map(i => +i.dataset.mb); await call("hire_apply", { vacancy_id: S.hire.vid, candidate_ids: ids }); closeModal(); toast(ids.length + " added"); render(); };
  },
  "h-cand": b => { S.hire.ctab = S.hire.ctab || "assess"; hireCandidate(+b.dataset.id); },
  "h-cclose": () => hireCloseCand(),
  "h-ctab": b => { S.hire.ctab = b.dataset.tab; hireCandidate(S.hire.cand); },
  "h-ai": async b => { b.disabled = true; $("#h-ai-box").innerHTML = `<div class="loading"><span class="spin"></span>The AI is reading the CV…</div>`;
    const r = await call("hire_ai", { app_id: +b.dataset.app }); if (!r.ok) { toast(r.message, { err: true }); } hireCandidate(S.hire.cand); },
  "h-kit": async b => { b.disabled = true; b.innerHTML = `<span class="spin" style="width:13px;height:13px"></span> Preparing…`; await call("hire_kit", { app_id: +b.dataset.app }); hireCandidate(S.hire.cand); },
  "h-panel": async b => {
    const scores = {}; $$("[data-hp]").forEach(s => { if (s.value) scores[s.dataset.hp] = +s.value; });
    if (!Object.keys(scores).length) return toast("Score at least one competency.", { err: true });
    await call("hire_panel", { app_id: +b.dataset.app, interviewer: $("#hp-who").value || "Interviewer", scores, note: $("#hp-note").value, decision: $("#hp-dec").value });
    toast("Scores saved"); hireCandidate(S.hire.cand);
  },
  "h-msg": async b => { const r = await call("hire_message", { app_id: +b.dataset.app, kind: $("#hm-kind").value, lang: $("#hm-lang").value, when: $("#hm-when").value, place: $("#hm-place").value });
    const t = $("#hm-text"); t.value = r.text; t.dir = $("#hm-lang").value === "ur" ? "rtl" : "ltr"; },
  "h-copy": () => { const t = $("#hm-text"); try { navigator.clipboard.writeText(t.value); toast("Copied: paste into WhatsApp or email"); } catch (e) { t.select(); document.execCommand("copy"); toast("Copied"); } },
  "h-cnotes": async b => { await call("hire_candidate_update", { candidate_id: +b.dataset.id, notes: $("#hc-notes").value, bank: $("#hc-bank").checked }); toast("Saved"); },
  "h-cdel": async b => { if (!confirm("Delete this candidate and their CV file? This cannot be undone.")) return; await call("hire_candidate_delete", { candidate_id: +b.dataset.id }); hireCloseCand(); render(); },
  "h-expmenu": () => { const m = $("#h-exp"); if (m) m.hidden = !m.hidden; },
  "h-export": async b => { $("#h-exp").hidden = true; const r = await call("export", { pack: "hiring", fmt: b.dataset.fmt, emp: S.hire.vid, hide: S.hire.blind }); if (r.ok) toast("Saved " + r.name); },
  "hb-add": async () => { if (!S.hire.sel.size) return toast("Tick people first.", { err: true }); await call("hire_apply", { vacancy_id: +$("#hb-vac").value, candidate_ids: [...S.hire.sel] }); toast(S.hire.sel.size + " added to the vacancy"); S.hire.sel.clear(); render(); },
  "h-keep": async () => { const r = await call("hire_settings", { keep_months: +$("#h-keep").value }); toast(`Saved${r.anonymised ? ` · ${r.anonymised} old candidate records anonymised` : ""}`); },
};

Object.assign(ACT, HIRE_ACTS, POLISH_ACTS);
POLISH_ACTS["pin-del"] = async b => { await call("pins", { remove: +b.dataset.i }); render(); };
ACT["pin-del"] = POLISH_ACTS["pin-del"];

/* ============================================================== Learning Studio: courses, lessons, quizzes, packs, tracking */
S.learn = { tab: "courses", cid: null, mod: 0, les: 0, view: "lesson", answers: {}, present: false };
const LLEVEL = { 1: "Associate", 2: "Team leader / supervisor", 3: "Section manager", 4: "Department head", 6: "Store manager" };
function lessonBlock(b, key) {
  const t = b.type;
  if (t === "para") return `<p class="lp">${esc(b.text)}</p>`;
  if (t === "points") return `${b.title ? `<h4 class="lh">${esc(b.title)}</h4>` : ""}<ul class="lpts">${b.items.map(i => `<li>${esc(i)}</li>`).join("")}</ul>`;
  if (t === "formula") return `<div class="lformula"><span class="lk">Formula</span><b class="lfn">${esc(b.name)}</b><div class="lfx">${esc(b.name)} = <span>${esc(b.expr)}</span></div>
      ${(b.where || []).length ? `<ul>${b.where.map(w => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}${b.example ? `<div class="lfe">Example · ${esc(b.example)}</div>` : ""}</div>`;
  if (t === "example") return `<div class="lex"><span class="lk">Worked example${b.title ? " · " + esc(b.title) : ""}</span>${b.lines.map(l => `<p>${esc(l)}</p>`).join("")}</div>`;
  if (t === "callout") return `<div class="lcall ${esc(b.kind || "key")}"><span class="lk">${{ warn: "Watch out", tip: "Tip" }[b.kind] || "Key point"}</span><p>${esc(b.text)}</p></div>`;
  if (t === "chart") return `<div class="lchart"><b>${esc(b.title || "")}</b>${b.unit ? ` <small>(${esc(b.unit)})</small>` : ""}<div class="lch" data-lchart="${key}"></div><small class="lnote">Example figures for learning</small></div>`;
  if (t === "kpis") return `<div class="kpis lkpis">${b.items.map(i => `<div class="kpi"><span class="kpi-l">${esc(i.label)}</span><span class="kpi-v">${esc(i.value)}</span><span class="kpi-s"><span>${esc(i.sub || "")}</span></span></div>`).join("")}</div>`;
  if (t === "steps") return `<div class="lsteps"><b>${esc(b.title || "")}</b><div class="lflow">${b.items.map((s, i) => `<div class="lstep"><span>${i + 1}</span><p>${esc(s)}</p></div>`).join(`<i class="larrow"></i>`)}</div></div>`;
  if (t === "table") return `<div class="ltable"><b>${esc(b.title || "")}</b><div class="tbl-wrap"><table class="t"><thead><tr>${b.columns.map(c => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${b.rows.map(r => `<tr>${r.map(v => `<td>${esc(v)}</td>`).join("")}</tr>`).join("")}</tbody></table></div></div>`;
  if (t === "dodont") return `<div class="ldd"><div class="ldo"><span class="lk">Do</span>${b.do.map(x => `<p>✓ ${esc(x)}</p>`).join("")}</div><div class="ldont"><span class="lk">Don't</span>${b.dont.map(x => `<p>✗ ${esc(x)}</p>`).join("")}</div></div>`;
  return "";
}
function quizHtml(qs, prefix) {
  const A = S.learn.answers;
  let right = 0, done = 0;
  const items = qs.map((q, i) => {
    const k = `${prefix}-${i}`, picked = A[k];
    const show = picked !== undefined;
    if (show) { done++; if (q.options ? picked === q.answer : true) right += q.options ? 1 : 0; }
    const body = q.options ? `<div class="lopts">${q.options.map((o, oi) => `<button class="lopt ${show ? (oi === q.answer ? "ok" : oi === picked ? "no" : "") : ""}" data-act="l-pick" data-k="${k}" data-i="${oi}" ${show ? "disabled" : ""}><b>${"ABCDEFGH"[oi]}</b>${esc(o)}</button>`).join("")}</div>`
      : `<textarea class="input" rows="2" placeholder="Your answer" style="width:100%"></textarea><button class="btn sm" data-act="l-pick" data-k="${k}" data-i="-1" ${show ? "disabled" : ""}>Show model answer</button>`;
    return `<div class="lq"><div class="lqh"><span class="chip">${{ mcq: "Multiple choice", tf: "True or false", calc: "Calculation", scenario: "Scenario" }[q.type]}</span><b>${i + 1}. ${esc(q.q)}</b></div>${body}
      ${show ? `<div class="lans ${q.options && picked !== q.answer ? "no" : ""}"><b>${q.options ? (picked === q.answer ? "Correct." : "Not quite.") : "Model answer:"}</b> ${q.options ? "" : esc(q.answer) + ". "}${esc(q.explain || "")}</div>` : ""}</div>`;
  }).join("");
  const mc = qs.filter(q => q.options).length;
  return `${items}<div class="lscore">${done ? `Score so far: <b>${right} / ${mc}</b> multiple-choice correct` : "Pick an answer to check it."} <button class="btn sm ghost" data-act="l-reset" data-p="${prefix}">Reset</button></div>`;
}

PAGES.learning = async () => {
  const L = S.learn;
  const tabs = `<div class="seg">${[["courses", "Courses"], ["needs", "Training needs"], ["track", "Tracking"], ["paths", "Learning paths"]].map(([k, l]) => `<button data-act="l-tab" data-tab="${k}" aria-pressed="${L.tab === k && !L.cid}">${l}</button>`).join("")}</div>`;
  if (L.cid) return learnCourse(tabs);
  const d = DATA.learn = await API.call("learn_list");
  const head = (t, p, right = "") => `<div class="ph"><div><h1>${t}</h1><p>${p}</p></div><div class="row">${right}${tabs}</div></div>`;
  if (L.tab === "needs") return trainingNeedsHtml(head);
  if (L.tab === "track") {
    const st = d.stats;
    const k = (l, v, s) => `<div class="kpi"><span class="kpi-l">${esc(l)}</span><span class="kpi-v">${v}</span><span class="kpi-s"><span>${esc(s)}</span></span></div>`;
    return head("Training tracking", "Who has been assigned which course, completion and scores by store.") +
      `<div class="kpis k5">${k("Courses", st.courses, "in the library")}${k("Assigned", st.assigned, "people × courses")}${k("Completed", st.completed, st.assigned ? Math.round(100 * st.completed / st.assigned) + "% completion" : "—")}
        ${k("Average score", st.avg_score != null ? st.avg_score + "%" : "—", `${st.passed} passed`)}${k("Overdue", st.overdue, "past due date, not completed")}</div>
      <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>By store</h2></div><div class="tbl-wrap"><table class="t"><thead><tr><th>Store</th><th class="n">Assigned</th><th class="n">Completed</th><th class="n">Completion</th><th class="n">Avg score</th></tr></thead><tbody>
      ${st.by_store.map(r => `<tr><td>${esc(r.store || "—")}</td><td class="n">${r.assigned}</td><td class="n">${r.completed || 0}</td><td class="n">${r.assigned ? Math.round(100 * (r.completed || 0) / r.assigned) + "%" : "—"}</td><td class="n">${r.avg_score ?? "—"}</td></tr>`).join("") || `<tr><td colspan="5"><div class="empty">Assign a course to see progress here.</div></td></tr>`}</tbody></table></div></div>
      <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>By course</h2></div><div class="tbl-wrap"><table class="t"><thead><tr><th>Course</th><th class="n">Assigned</th><th class="n">Completed</th><th class="n">Avg score</th></tr></thead><tbody>
      ${d.rows.map(c => `<tr class="click" data-act="l-open" data-id="${c.id}"><td><b>${esc(c.title)}</b></td><td class="n">${c.assigned}</td><td class="n">${c.completed}</td><td class="n">${c.avg_score ?? "—"}</td></tr>`).join("")}</tbody></table></div></div>`;
  }
  if (L.tab === "paths") {
    return head("Learning paths", "A path is the set of courses for a role, in order: for example Associate → Team Leader → Section Manager.",
      `<button class="btn primary" data-act="l-path-new">New path</button>`) +
      (d.paths.length ? `<div class="hcards">${d.paths.map(p => `<div class="hcard" style="cursor:default"><div class="row" style="justify-content:space-between"><b>${esc(p.name)}</b><span class="chip">${esc(LLEVEL[p.role_level] || "")}</span></div>
        <ol class="lpath">${p.course_ids.map(id => { const c = d.rows.find(x => x.id === id); return c ? `<li><button class="linkbtn" data-act="l-open" data-id="${c.id}">${esc(c.title)}</button> <small>${c.hours} h</small></li>` : ""; }).join("")}</ol>
        <div class="row"><button class="btn sm ghost danger" data-act="l-path-del" data-id="${p.id}">Delete</button></div></div>`).join("")}</div>`
        : `<div class="panel"><div class="empty">No paths yet. Create courses first, then group them into a path for each role.</div></div>`);
  }
  const card = c => `<button class="hcard lcard" data-act="l-open" data-id="${c.id}"><div class="row" style="justify-content:space-between;gap:8px"><b>${esc(c.title)}</b><span class="chip ${c.source.includes("AI") ? "info" : ""}">${esc(c.source)}</span></div>
      <small>${esc(c.audience || "")} · ${c.hours} h · ${c.lecture_min}-min lectures</small>
      <div class="hstats"><span><b>${c.modules}</b>modules</span><span><b>${c.lessons}</b>lessons</span><span><b>${c.questions}</b>questions</span><span><b>${c.assigned}</b>assigned</span><span><b>${c.completed}</b>done</span></div></button>`;
  return head("Learning Studio", "Make complete retail courses for any role in minutes: lectures with formulas, charts and diagrams, quizzes and a final assessment. Export as PDF, PowerPoint, Word or Excel.",
      `<button class="btn primary" data-act="l-new">${ic("spark", 15)}New course</button>`) +
    `<div class="panel"><div class="phd"><h2>Topic library</h2><small>${d.topics.length} retail topics written for Carrefour stores · pick any when you make a course</small></div>
      <div class="ltopics">${d.topics.map(t => `<div class="ltopic"><b>${esc(t.title)}</b><small>${esc(t.summary)}</small><small class="lmeta">${t.lessons} lessons · ${t.minutes} min</small></div>`).join("")}</div></div>` +
    (d.rows.length ? `<div class="hcards stagger">${d.rows.map(card).join("")}</div>` : `<div class="panel"><div class="empty">No courses yet. Click <b>New course</b>: choose the role, topics and hours.</div></div>`);
};

function learnForm() {
  const d = DATA.learn || { topics: [] };
  return `<h3>New course</h3><p style="color:var(--muted);margin:0 0 12px">Choose who it is for and how long it runs. Pick topics, or describe what people need to learn (or paste a JD) and P&amp;O picks them.</p>
    <div class="hform"><label class="dx-l">Course title (optional)<input class="input" id="lf-title" placeholder="Made from the topics if left empty"></label>
      <label class="dx-l">For<select class="input" id="lf-level">${Object.entries(LLEVEL).map(([k, v]) => `<option value="${k}" ${k === "2" ? "selected" : ""}>${v}</option>`).join("")}</select></label>
      <label class="dx-l">Total hours<input class="input" id="lf-hours" type="number" min="0.5" max="40" step="0.5" value="4"></label>
      <label class="dx-l">Lecture length (min)<input class="input" id="lf-lec" type="number" min="10" max="90" step="5" value="25"></label></div>
    <div style="margin-top:10px"><b style="font-size:12.5px">Topics</b> <small style="color:var(--muted)">leave empty to use the standard set for the role</small>
      <div class="hskills">${d.topics.map(t => `<label class="hsk"><input type="checkbox" data-ltopic value="${t.key}"><span>${esc(t.title)}</span></label>`).join("")}</div></div>
    <label class="dx-l" style="margin-top:10px">Or describe what to learn, or paste a JD<textarea class="input" id="lf-focus" rows="3" placeholder="e.g. New cashiers who need to handle cash, refunds and angry customers"></textarea></label>
    <label class="switch-l" style="margin-top:10px"><input type="checkbox" id="lf-ai"> Also write extra lessons with AI (Settings → AI). Topics not in the library always use AI when it is set up.</label>
    <div class="row" style="justify-content:flex-end;margin-top:14px"><button class="btn" data-act="modal-close">Cancel</button><button class="btn primary" data-act="l-build">${ic("spark", 14)}Make course</button></div>`;
}

async function learnCourse(tabs) {
  const L = S.learn;
  const c = DATA.lcourse = await API.call("learn_course", { course_id: L.cid });
  const ct = c.content;
  const mods = ct.modules;
  L.mod = Math.min(L.mod, mods.length - 1);
  const m = mods[L.mod] || { lessons: [] };
  L.les = Math.min(L.les, Math.max(0, m.lessons.length - 1));
  const toc = mods.map((mm, mi) => `<div class="ltoc-m"><span>Module ${mi + 1}</span><b>${esc(mm.title)}</b></div>${mm.lessons.map((l, li) => `<button class="ltoc-l" data-act="l-go" data-m="${mi}" data-l="${li}" aria-current="${L.view === "lesson" && mi === L.mod && li === L.les}">
      <span>${mi + 1}.${li + 1}</span>${esc(l.title)}<small>${l.minutes} min${l.source === "AI" ? " · AI" : ""}</small></button>`).join("")}
      ${mm.quiz && mm.quiz.length ? `<button class="ltoc-l" data-act="l-quiz" data-m="${mi}" aria-current="${L.view === "quiz" && mi === L.mod}"><span>✎</span>Module check<small>${mm.quiz.length} questions</small></button>` : ""}`).join("") +
    `<button class="ltoc-l" data-act="l-exam" aria-current="${L.view === "exam"}"><span>★</span>Final assessment<small>${ct.exam.length} questions · pass ${ct.pass_mark}%</small></button>
     <button class="ltoc-l" data-act="l-people" aria-current="${L.view === "people"}"><span>👥</span>Assigned people<small>${c.assignments.length} assigned</small></button>`;
  let body = "";
  if (L.view === "lesson") {
    const l = m.lessons[L.les];
    const flat = mods.flatMap((mm, mi) => mm.lessons.map((_, li) => [mi, li]));
    const pos = flat.findIndex(([a, b]) => a === L.mod && b === L.les);
    body = `<div class="lhead"><span class="lk">Module ${L.mod + 1} · ${esc(m.title)} · lesson ${L.les + 1} of ${m.lessons.length}</span><h2>${esc(l.title)}</h2>
        <div class="row"><span class="chip">${l.minutes} min</span>${l.source === "AI" ? `<span class="chip info">Written by AI</span>` : ""}<span class="spacer"></span>
        <div class="menu-wrap"><button class="btn sm" data-act="l-aimenu">${ic("spark", 13)}Rewrite ▾</button><div class="cmenu" id="l-aim" hidden>
          ${[["simpler", "Simpler", "shorter sentences for frontline staff"], ["detail", "More detail", "another example and visual"], ["examples", "More store examples", "Pakistani hypermarket cases"], ["urdu", "Urdu", "translate this lesson"]].map(([k, t, s]) => `<button data-act="l-rewrite" data-how="${k}"><b>${t}</b><small>${s}</small></button>`).join("")}</div></div>
        <button class="btn sm" data-act="l-edit">Edit text</button></div></div>
      ${l.objectives && l.objectives.length ? `<div class="lobj"><span class="lk">Objectives</span>${l.objectives.map(o => `<p>→ ${esc(o)}</p>`).join("")}</div>` : ""}
      <div class="lbody" ${/[؀-ۿ]/.test(JSON.stringify(l.blocks).slice(0, 400)) ? 'dir="rtl"' : ""}>${l.blocks.map((b, bi) => lessonBlock(b, `${L.mod}-${L.les}-${bi}`)).join("")}</div>
      <div class="lnav"><button class="btn" data-act="l-step" data-d="-1" ${pos <= 0 ? "disabled" : ""}>${ic("back", 14)}Previous</button><span class="lprog"><i style="width:${Math.round(100 * (pos + 1) / flat.length)}%"></i></span><button class="btn primary" data-act="l-step" data-d="1" ${pos >= flat.length - 1 ? "disabled" : ""}>Next lesson</button></div>`;
  } else if (L.view === "quiz") {
    body = `<div class="lhead"><span class="lk">Module ${L.mod + 1} · ${esc(m.title)}</span><h2>Module check</h2></div>${quizHtml(m.quiz, "m" + L.mod)}
      ${m.activity ? `<div class="lcall tip"><span class="lk">On the floor</span><p>${esc(m.activity)}</p></div>` : ""}`;
  } else if (L.view === "exam") {
    body = `<div class="lhead"><span class="lk">Final assessment · pass mark ${ct.pass_mark}%</span><h2>${esc(ct.title)}</h2></div>${quizHtml(ct.exam, "exam")}`;
  } else {
    body = `<div class="lhead"><span class="lk">Assignments</span><h2>Assigned people</h2></div>
      <div class="row" style="gap:8px;margin-bottom:10px"><input class="input" id="la-q" list="la-people" placeholder="Type a name to assign" style="flex:1"><datalist id="la-people"></datalist>
        <input class="input" type="date" id="la-due" title="Due date"><button class="btn primary" data-act="l-assign">Assign</button></div>
      <div class="tbl-wrap"><table class="t"><thead><tr><th>Name</th><th>Store</th><th>Assigned</th><th>Due</th><th>Status</th><th class="n">Score %</th><th></th></tr></thead><tbody>
      ${c.assignments.map(a => `<tr><td><b>${esc(a.person_name || a.person)}</b></td><td>${esc(a.store || "—")}</td><td class="nw">${esc((a.assigned_at || "").slice(0, 10))}</td><td class="nw">${esc(a.due || "—")}</td>
        <td><select class="input sm" data-lstatus="${a.id}">${["assigned", "in progress", "completed"].map(s => `<option ${s === a.status ? "selected" : ""}>${s}</option>`).join("")}</select></td>
        <td class="n"><input class="input sm" type="number" min="0" max="100" data-lscore="${a.id}" value="${a.score ?? ""}" style="width:70px"></td>
        <td class="n">${a.status === "completed" ? `<button class="btn sm" data-act="l-cert" data-id="${a.id}">Certificate</button>` : ""}<button class="btn sm ghost danger" data-act="l-unassign" data-id="${a.id}">Remove</button></td></tr>`).join("") || `<tr><td colspan="7"><div class="empty">Nobody assigned yet.</div></td></tr>`}</tbody></table></div>`;
  }
  const exp = [["pdf", "Learner book (PDF)", "cover, contents, lessons, visuals, quizzes"], ["answers", "Answer key (PDF)", "for trainers"], ["pptx", "Trainer deck (PowerPoint)", "slides with speaker notes"],
    ["docx", "Editable (Word)", "change anything"], ["xlsx", "Quiz bank + tracker (Excel)", "every question, assignment tracker"], ["zip", "Full learning pack (zip)", "all of the above, ready to email"]];
  return `<div class="ph"><div><h1>${esc(ct.title)}</h1><p>${esc(ct.audience)} · ${esc(ct.summary)}</p>${ct.for ? `<p><span class="chip gold">For ${esc(ct.for.name)}</span> <small style="color:var(--muted)">focus: ${esc(ct.for.why.join(", "))}</small></p>` : ""}${(ct.notes || []).map(n => `<p><small style="color:var(--warn-ink)">⚠ ${esc(n)}</small></p>`).join("")}</div>
      <div class="row"><button class="btn ghost" data-act="l-back">${ic("back", 15)}All courses</button><button class="btn" data-act="l-present">${ic("play", 14)}Present</button>
      <div class="menu-wrap"><button class="btn primary" data-act="l-expmenu">${ic("export", 15)}Export ▾</button><div class="cmenu" id="l-exp" hidden>${exp.map(([k, t, s]) => `<button data-act="l-export" data-fmt="${k}"><b>${t}</b><small>${s}</small></button>`).join("")}</div></div>
      <div class="menu-wrap"><button class="btn ghost" data-act="l-more">⋯</button><div class="cmenu" id="l-more" hidden><button data-act="l-dup"><b>Duplicate</b><small>copy to change for another group</small></button><button data-act="l-del"><b>Delete course</b><small>and its assignments</small></button></div></div></div></div>
    <div class="lwrap"><aside class="ltoc">${toc}</aside><article class="lmain panel">${body}</article></div>`;
}
function learnDrawCharts() {
  const c = DATA.lcourse; if (!c) return;
  $$("[data-lchart]").forEach(el => {
    const [mi, li, bi] = el.dataset.lchart.split("-").map(Number);
    const b = c.content.modules[mi].lessons[li].blocks[bi];
    if (b && !el.dataset.drawn) { el.dataset.drawn = 1; drawChartSpec(el, { ...b, kind: b.kind === "hbar" && b.series[0].values.some(v => v < 0) ? "hbar" : b.kind, tone: b.series[0].values.some(v => v < 0) ? "signed" : "" }); }
  });
}
AFTER.learning = async () => {
  const thr = $("#tn-thr"); if (thr) thr.onchange = () => { S.tnThr = +thr.value; render(); };
  learnDrawCharts();
  const q = $("#la-q");
  if (q) {
    const p = DATA.lpeople || (DATA.lpeople = (await API.call("learn_people")).people);
    $("#la-people").innerHTML = p.slice(0, 2000).map(x => `<option value="${esc(x.name)}">${esc([x.role, x.store].filter(Boolean).join(" · "))}</option>`).join("");
  }
};
document.addEventListener("change", async e => {
  const st = e.target.closest && e.target.closest("[data-lstatus]");
  if (st) { await call("learn_result", { assignment_id: +st.dataset.lstatus, status: st.value }); toast("Saved"); render(); return; }
  const sc = e.target.closest && e.target.closest("[data-lscore]");
  if (sc) { await call("learn_result", { assignment_id: +sc.dataset.lscore, score: sc.value === "" ? null : +sc.value }); toast("Score saved"); }
});
function learnPresent() {
  const c = DATA.lcourse; if (!c) return;
  const slides = [];
  slides.push(`<div class="lsl-cover"><span class="lk">${esc(c.content.audience)}</span><h1>${esc(c.content.title)}</h1><p>${esc(c.content.summary)}</p></div>`);
  c.content.modules.forEach((m, mi) => {
    slides.push(`<div class="lsl-mod"><span class="lk">Module ${mi + 1}</span><h1>${esc(m.title)}</h1><p>${esc(m.summary || "")}</p></div>`);
    m.lessons.forEach((l, li) => {
      slides.push(`<div><span class="lk">${mi + 1}.${li + 1} · ${l.minutes} min</span><h1>${esc(l.title)}</h1>${(l.objectives || []).map(o => `<p class="lsl-o">→ ${esc(o)}</p>`).join("")}</div>`);
      l.blocks.forEach((b, bi) => { if (b.type !== "para") slides.push(`<div class="lbody">${lessonBlock(b, `${mi}-${li}-${bi}`)}</div>`); });
    });
  });
  let i = 0, t0 = Date.now();
  const ov = document.createElement("div"); ov.className = "lpresent"; document.body.append(ov);
  const draw = () => { ov.innerHTML = `<div class="lsl">${slides[i]}</div><div class="lsl-bar"><span>${i + 1} / ${slides.length}</span><span id="lsl-t"></span><span>← → to move · Esc to close</span></div>`; learnDrawCharts(); };
  const tick = setInterval(() => { const el = $("#lsl-t"); if (el) { const s = Math.floor((Date.now() - t0) / 1000); el.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; } }, 1000);
  const key = e => { if (["ArrowRight", "PageDown", " "].includes(e.key)) { i = Math.min(slides.length - 1, i + 1); draw(); } else if (["ArrowLeft", "PageUp"].includes(e.key)) { i = Math.max(0, i - 1); draw(); }
    else if (e.key === "Escape") { clearInterval(tick); document.removeEventListener("keydown", key, true); ov.remove(); } e.stopPropagation(); };
  document.addEventListener("keydown", key, true);
  ov.addEventListener("click", e => { if (!e.target.closest(".lsl-bar")) { i = Math.min(slides.length - 1, i + 1); draw(); } });
  draw();
}
const lTop = async () => { await render(); const v = $("#view"); if (v) v.scrollTo({ top: 0, behavior: "smooth" }); };
const LEARN_ACTS = {
  "l-tab": b => { S.learn.tab = b.dataset.tab; S.learn.cid = null; render(); },
  "l-new": () => { const m = modal(learnForm()); m.classList.add("wide"); },
  "l-build": async b => {
    const topics = $$("[data-ltopic]").filter(i => i.checked).map(i => i.value);
    b.disabled = true; b.innerHTML = `<span class="spin" style="width:14px;height:14px"></span> Writing the course…`;
    try {
      const c = await call("learn_build", { title: $("#lf-title").value, level: +$("#lf-level").value, topics, hours: +$("#lf-hours").value || 4, lecture_min: +$("#lf-lec").value || 25,
        focus: $("#lf-focus").value, use_ai: $("#lf-ai").checked });
      closeModal(); S.learn.cid = c.id; S.learn.mod = 0; S.learn.les = 0; S.learn.view = "lesson"; toast("Course ready: " + c.content.summary); render();
    } catch (e) { b.disabled = false; b.textContent = "Make course"; }
  },
  "l-open": b => { S.learn.cid = +b.dataset.id; S.learn.mod = 0; S.learn.les = 0; S.learn.view = "lesson"; render(); },
  "l-back": () => { S.learn.cid = null; render(); },
  "l-go": b => { S.learn.mod = +b.dataset.m; S.learn.les = +b.dataset.l; S.learn.view = "lesson"; lTop(); },
  "l-quiz": b => { S.learn.mod = +b.dataset.m; S.learn.view = "quiz"; lTop(); },
  "l-exam": () => { S.learn.view = "exam"; lTop(); },
  "l-people": () => { S.learn.view = "people"; lTop(); },
  "l-step": b => { const mods = DATA.lcourse.content.modules; const flat = mods.flatMap((mm, mi) => mm.lessons.map((_, li) => [mi, li]));
    const pos = flat.findIndex(([a, c]) => a === S.learn.mod && c === S.learn.les) + +b.dataset.d; if (flat[pos]) { [S.learn.mod, S.learn.les] = flat[pos]; lTop(); } },
  "l-pick": b => { S.learn.answers[b.dataset.k] = +b.dataset.i; render(); },
  "l-reset": b => { Object.keys(S.learn.answers).filter(k => k.startsWith(b.dataset.p + "-")).forEach(k => delete S.learn.answers[k]); render(); },
  "l-expmenu": () => { const m = $("#l-exp"); if (m) m.hidden = !m.hidden; },
  "l-more": () => { const m = $("#l-more"); if (m) m.hidden = !m.hidden; },
  "l-export": async b => { $("#l-exp").hidden = true; toast("Preparing " + b.querySelector("b").textContent + "…"); const r = await call("learn_export", { course_id: S.learn.cid, fmt: b.dataset.fmt }); if (r.ok) toast("Saved " + r.name); },
  "l-aimenu": () => { const m = $("#l-aim"); if (m) m.hidden = !m.hidden; },
  "l-rewrite": async b => { $("#l-aim").hidden = true; toast("The AI is rewriting this lesson…", { ms: 6000 });
    await call("learn_rewrite", { course_id: S.learn.cid, module: S.learn.mod, lesson: S.learn.les, how: b.dataset.how }); toast("Lesson rewritten"); render(); },
  "l-edit": () => {
    const c = DATA.lcourse, l = c.content.modules[S.learn.mod].lessons[S.learn.les];
    const fields = l.blocks.map((b, i) => b.type === "para" ? `<label class="dx-l">Paragraph<textarea class="input" rows="3" data-le="${i}" data-f="text">${esc(b.text)}</textarea></label>`
      : b.type === "points" ? `<label class="dx-l">${esc(b.title || "Points")} (one per line)<textarea class="input" rows="${b.items.length + 1}" data-le="${i}" data-f="items">${esc(b.items.join("\n"))}</textarea></label>`
      : b.type === "callout" ? `<label class="dx-l">Callout<textarea class="input" rows="2" data-le="${i}" data-f="text">${esc(b.text)}</textarea></label>` : "").join("");
    const m = modal(`<h3>Edit lesson</h3><label class="dx-l">Title<input class="input" id="le-title" value="${esc(l.title)}"></label><div class="ledit">${fields}</div>
      <div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" data-act="modal-close">Cancel</button><button class="btn primary" id="le-save">Save</button></div>`); m.classList.add("wide");
    $("#le-save", m).onclick = async () => {
      l.title = $("#le-title", m).value;
      $$("[data-le]", m).forEach(t => { const b = l.blocks[+t.dataset.le]; if (t.dataset.f === "items") b.items = t.value.split("\n").map(x => x.trim()).filter(Boolean); else b.text = t.value; });
      await call("learn_edit", { course_id: S.learn.cid, content: c.content }); closeModal(); toast("Lesson saved"); render();
    };
  },
  "l-present": () => learnPresent(),
  "l-dup": async () => { const c = await call("learn_duplicate", { course_id: S.learn.cid }); S.learn.cid = c.id; toast("Copy made"); render(); },
  "l-del": async () => { if (!confirm("Delete this course and its assignments?")) return; await call("learn_delete", { course_id: S.learn.cid }); S.learn.cid = null; render(); },
  "l-assign": async () => {
    const name = $("#la-q").value.trim(); if (!name) return toast("Type a name.", { err: true });
    const p = (DATA.lpeople || []).find(x => x.name.toLowerCase() === name.toLowerCase()) || { person: name, name, store: "" };
    await call("learn_assign", { course_id: S.learn.cid, people: [p], due: $("#la-due").value || null }); toast(name + " assigned"); render();
  },
  "l-unassign": async b => { await call("learn_unassign", { assignment_id: +b.dataset.id }); render(); },
  "l-cert": async b => { const r = await call("learn_certificate", { assignment_id: +b.dataset.id }); if (r.ok) toast("Saved " + r.name); },
  "l-path-new": () => {
    const d = DATA.learn;
    const m = modal(`<h3>New learning path</h3><div class="hform"><label class="dx-l">Name<input class="input" id="lp-name" placeholder="e.g. Team Leader path"></label>
      <label class="dx-l">For<select class="input" id="lp-level">${Object.entries(LLEVEL).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></label></div>
      <p style="color:var(--muted)">Tick the courses in the order they should be taken.</p><div class="ledit">${d.rows.map(c => `<label class="hsk" style="border-radius:10px"><input type="checkbox" data-lpc="${c.id}"><span>${esc(c.title)} · ${c.hours} h</span></label>`).join("") || "<div class='empty'>Make courses first.</div>"}</div>
      <div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" data-act="modal-close">Cancel</button><button class="btn primary" id="lp-save">Save path</button></div>`);
    const order = []; m.addEventListener("change", e => { const id = +e.target.dataset.lpc; if (!id) return; if (e.target.checked) order.push(id); else order.splice(order.indexOf(id), 1); });
    $("#lp-save", m).onclick = async () => { if (!$("#lp-name", m).value.trim() || !order.length) return toast("Name the path and tick courses.", { err: true });
      await call("learn_path_save", { name: $("#lp-name", m).value.trim(), level: +$("#lp-level", m).value, course_ids: order }); closeModal(); render(); };
  },
  "l-devpack": async b => { b.disabled = true; b.innerHTML = `<span class="spin" style="width:13px;height:13px"></span> Building…`;
    try { const c = await call("learn_for_person", { key: b.dataset.key }); toast("Development pack ready and assigned"); S.learn = { ...S.learn, cid: c.id, mod: 0, les: 0, view: "lesson" }; go("learning"); }
    catch (e) { b.disabled = false; b.textContent = "Make development pack"; } },
  "l-path-del": async b => { await call("learn_path_delete", { path_id: +b.dataset.id }); render(); },
};
Object.assign(ACT, LEARN_ACTS);


/* ============================================================== Action tracker */
PAGES.actions = async () => {
  const d = DATA.actions = await API.call("actions");
  const F = S.actFilter || "active";
  const rows = d.rows.filter(r => F === "all" || (F === "active" ? ["open", "in progress"].includes(r.status) : F === "overdue" ? r.overdue : r.status === F));
  const k = (l, v, s, cls = "") => `<div class="kpi"><span class="kpi-l">${esc(l)}</span><span class="kpi-v ${cls}">${v}</span><span class="kpi-s"><span>${esc(s)}</span></span></div>`;
  return `<div class="ph"><div><h1>Action tracker</h1><p>Every decision turned into an owner and a date: from alerts, AI answers, flight-risk reviews and meetings.</p></div>
      <div class="row"><button class="btn primary" data-act="act-new">+ New action</button></div></div>
    <div class="kpis k5">${k("Open", d.counts.open, "not started")}${k("In progress", d.counts["in progress"], "being worked on")}${k("Overdue", d.overdue, "past the due date", d.overdue ? "t-bad" : "")}${k("Done · 30 days", d.done_30d, "closed this month")}
      ${k("Busiest owner", d.by_owner.length ? `<span class="txt">${esc(d.by_owner[0][0])}</span>` : "—", d.by_owner.length ? d.by_owner[0][1] + " open" : "")}</div>
    <div class="panel flush"><div class="row" style="padding:12px 14px 0;justify-content:space-between"><div class="seg">${[["active", "Active"], ["overdue", "Overdue"], ["done", "Done"], ["all", "All"]].map(([v, l]) => `<button data-act="act-filter" data-f="${v}" aria-pressed="${F === v}">${l}</button>`).join("")}</div></div>
      <div class="tbl-wrap"><table class="t"><thead><tr><th>Action</th><th>Owner</th><th>Store</th><th>Area</th><th>Due</th><th>Priority</th><th>Status</th><th>Source</th><th></th></tr></thead><tbody>
      ${rows.map(r => `<tr class="${r.overdue ? "row-bad" : ""}"><td><b>${esc(r.title)}</b>${r.detail ? `<span class="sub">${esc(r.detail.slice(0, 160))}</span>` : ""}${r.history.length > 1 ? `<span class="sub">${esc(r.history[r.history.length - 1].note || "")}</span>` : ""}</td>
        <td><input class="input sm" data-actf="owner" data-id="${r.id}" value="${esc(r.owner || "")}" placeholder="Owner" style="width:120px"></td><td>${esc(r.store || "—")}</td><td>${esc(r.area || "—")}</td>
        <td><input class="input sm" type="date" data-actf="due" data-id="${r.id}" value="${esc(r.due || "")}"></td>
        <td><select class="input sm" data-actf="priority" data-id="${r.id}">${["High", "Medium", "Low"].map(p => `<option ${p === r.priority ? "selected" : ""}>${p}</option>`).join("")}</select></td>
        <td><select class="input sm" data-actf="status" data-id="${r.id}">${d.statuses.map(st => `<option ${st === r.status ? "selected" : ""}>${st}</option>`).join("")}</select></td>
        <td><span class="chip">${esc(r.source || "")}</span></td><td class="n"><button class="btn sm ghost" data-act="act-note" data-id="${r.id}">Note</button><button class="btn sm ghost danger" data-act="act-del" data-id="${r.id}">×</button></td></tr>`).join("") || `<tr><td colspan="9"><div class="empty">Nothing here. Add actions from alerts (Business review), AI answers (→ Actions) or Flight risk.</div></td></tr>`}</tbody></table></div></div>`;
};
function actionForm(o = {}) {
  const m = modal(`<h3>New action</h3><div class="hform"><label class="dx-l" style="grid-column:1/-1">What needs to be done<input class="input" id="af-title" value="${esc(o.title || "")}"></label>
    <label class="dx-l">Owner<input class="input" id="af-owner" value="${esc(o.owner || "")}" placeholder="Name or role"></label><label class="dx-l">Store<input class="input" id="af-store" value="${esc(o.store || "")}"></label>
    <label class="dx-l">Area<input class="input" id="af-area" value="${esc(o.area || "")}" placeholder="e.g. Turnover, Shrinkage"></label><label class="dx-l">Due<input class="input" type="date" id="af-due" value="${esc(o.due || "")}"></label>
    <label class="dx-l">Priority<select class="input" id="af-pri"><option>High</option><option selected>Medium</option><option>Low</option></select></label></div>
    <label class="dx-l" style="margin-top:8px">Details<textarea class="input" id="af-detail" rows="3" style="width:100%">${esc(o.detail || "")}</textarea></label>
    <div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" data-act="modal-close">Cancel</button><button class="btn primary" id="af-save">Add action</button></div>`);
  $("#af-save", m).onclick = async () => { if (!$("#af-title", m).value.trim()) return toast("Write the action.", { err: true });
    await call("action_add", { title: $("#af-title", m).value, owner: $("#af-owner", m).value, store: $("#af-store", m).value, area: $("#af-area", m).value,
      due: $("#af-due", m).value || null, priority: $("#af-pri", m).value, source: o.source || "Manual", detail: $("#af-detail", m).value });
    closeModal(); toast("Action added", { action: "Open tracker", onAction: () => go("actions") }); if (S.page === "actions") render(); };
}
document.addEventListener("change", async e => {
  const f = e.target.closest && e.target.closest("[data-actf]");
  if (!f) return;
  await call("action_update", { action_id: +f.dataset.id, [f.dataset.actf]: f.value }); toast("Saved"); if (f.dataset.actf === "status") render();
});

/* ============================================================== Manpower: approved vs actual */
PAGES.manpower = async () => {
  const d = DATA.manpower = await API.call("manpower");
  const k = (l, v, s, cls = "") => `<div class="kpi"><span class="kpi-l">${esc(l)}</span><span class="kpi-v ${cls}">${v}</span><span class="kpi-s"><span>${esc(s)}</span></span></div>`;
  return `<div class="ph"><div><h1>Manpower</h1><p>Approved heads against people on the Basic Sheet, by store and department, with open vacancies from Hiring.</p></div>
      <div class="row"><button class="btn primary" data-act="mp-paste">Paste approved manning</button></div></div>
    ${d.has_plan ? "" : `<div class="banner">No approved manning yet. Paste it from Excel (Store · Department · Approved heads) or type it in the table below. Until then, actual headcount is shown.</div>`}
    <div class="kpis k5">${k("Headcount", d.headcount.toLocaleString("en-US"), "on the Basic Sheet")}${k("Approved", d.has_plan ? d.approved.toLocaleString("en-US") : "—", "stores with a plan")}
      ${k("Vacant positions", d.has_plan ? d.vacant : "—", "below approved", d.vacant ? "t-bad" : "")}${k("Over plan", d.has_plan ? d.over : "—", "above approved", d.over ? "t-warn" : "")}${k("Open vacancies", d.open_vacancies, "in Hiring")}</div>
    ${d.has_plan ? `<div class="panel"><div class="phd"><h2>Fill rate by store</h2><small>Actual ÷ approved · black mark = 100%</small></div><div id="ch-mp"></div></div>` : ""}
    <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>By store and department</h2><small>Type an approved number to set the plan</small></div><div class="tbl-wrap"><table class="t"><thead><tr><th>Store</th><th>Department</th><th class="n">Approved</th><th class="n">Actual</th><th class="n">Gap</th><th class="n">Fill</th><th class="n">Open vacancies</th></tr></thead><tbody>
    ${d.rows.map(r => `<tr><td>${esc(r.store)}</td><td>${esc(r.department)}</td><td class="n"><input class="input sm" type="number" min="0" data-mp-store="${esc(r.store)}" data-mp-dept="${esc(r.department)}" value="${r.approved ?? ""}" style="width:80px"></td>
      <td class="n">${r.actual}</td><td class="n ${r.gap == null ? "" : r.gap < 0 ? "t-bad" : r.gap > 0 ? "t-warn" : "t-good"}">${r.gap == null ? "—" : (r.gap > 0 ? "+" : "") + r.gap}</td><td class="n">${r.fill_pct == null ? "—" : r.fill_pct + "%"}</td><td class="n">${r.open_vacancies || ""}</td></tr>`).join("") || `<tr><td colspan="7"><div class="empty">Import the Basic Sheet to see headcount.</div></td></tr>`}</tbody></table></div></div>`;
};
AFTER.manpower = () => {
  const d = DATA.manpower;
  if (d && $("#ch-mp")) { const st = d.stores.filter(s => s.has_plan); Charts.bullet($("#ch-mp"), { items: st.map(s => ({ label: s.store, value: s.fill_pct || 0, target: 100, max: Math.max(120, ...st.map(x => x.fill_pct || 0)), fmt: "pct0" })) }); }
};
document.addEventListener("change", async e => {
  const i = e.target.closest && e.target.closest("[data-mp-store]");
  if (!i) return;
  await call("manpower_save", { rows: [{ store: i.dataset.mpStore, department: i.dataset.mpDept, approved: i.value === "" ? null : +i.value }] }); toast("Plan saved"); render();
});

/* ============================================================== What needs you today (Overview) */
async function drawToday() {
  const box = $("#today"); if (!box) return;
  try {
    const t = await API.call("today");
    box.innerHTML = t.items.length ? t.items.map(i => `<button class="today-i ${i.level}" data-go="${i.go}" ${i.tab ? `data-tab="${i.tab}"` : ""}><span class="ic">${i.level === "bad" ? "!" : i.level === "warn" ? "•" : "i"}</span><span><b>${esc(i.area)}</b> · ${esc(i.text)}</span><span class="go">›</span></button>`).join("")
      : `<div class="empty" style="padding:10px">All clear: nothing urgent today 🎉</div>`;
  } catch (e) { box.innerHTML = ""; }
}
const MORE_ACTS = {
  "act-new": () => actionForm(),
  "act-quick": b => actionForm({ title: b.dataset.title, store: b.dataset.store, area: b.dataset.area, detail: b.dataset.detail, source: b.dataset.source || "Flight risk" }),
  "act-filter": b => { S.actFilter = b.dataset.f; render(); },
  "act-del": async b => { await call("action_delete", { action_id: +b.dataset.id }); render(); },
  "act-note": b => { const n = prompt("Add a note (progress, blocker, decision):"); if (n) call("action_update", { action_id: +b.dataset.id, note: n }).then(() => { toast("Note added"); render(); }); },
  "msg-actions": async b => { const m = S.chat[+b.dataset.m]; const r = await call("actions_from_answer", { text: m.content || "" });
    toast(r.added ? `${r.added} action${r.added > 1 ? "s" : ""} added to the tracker` : "No 'Recommended actions' list in this answer", { err: !r.added, action: r.added ? "Open" : null, onAction: () => go("actions") }); },
  "mp-paste": () => {
    const m = modal(`<h3>Paste approved manning</h3><p style="color:var(--muted);margin:0 0 10px">Copy three columns from Excel: <b>Store · Department · Approved heads</b>. Store and department names are matched automatically.</p>
      <textarea class="input" id="mp-t" rows="10" style="width:100%;font-family:monospace;font-size:12px" placeholder="LAH Fortress\tFresh Food\t42"></textarea>
      <div class="row" style="justify-content:flex-end;margin-top:10px"><button class="btn" data-act="modal-close">Cancel</button><button class="btn primary" id="mp-go">Save plan</button></div>`);
    $("#mp-go", m).onclick = async () => { const r = await call("manpower_save", { paste: $("#mp-t", m).value }); closeModal(); toast(`${r.saved} rows saved`); render(); };
  },
  "po-leader-open": b => { S.po.tab = "leaders"; S.po.leader = b.dataset.key; render(); },
};
Object.assign(ACT, MORE_ACTS);
Object.assign(ACT, IMP_ACTS);
Object.assign(ACT, INT_ACTS);
Object.assign(ACT, BRAIN_ACTS);
Object.assign(ACT, ER_ACTS);
Object.assign(ACT, V3_ACTS);
Object.assign(ACT, RV_ACTS);
ACT["tpl-forget"] = async b => { await call("import_templates", { forget: b.dataset.k }); toast("Forgotten"); render(); };

/* ============================================================== 2.2 Policy assistant */
PAGES.policies = async () => {
  const d = DATA.pol = await API.call("policies");
  const a = S.polAns;
  return `<div class="ph"><div><h1>Policy assistant</h1><p>Add the HR policy manual and handbooks once; ask any question and get the exact clause, with the AI's short answer when one is set up.</p></div>
      <div class="row"><button class="btn" data-act="pol-paste">Paste text</button><button class="btn primary" data-act="pol-add">${ic("import", 14)}Add policies</button></div></div>
    <div class="panel pol-ask"><form id="pol-f" class="row" style="gap:10px"><input class="input" id="pol-q" placeholder="e.g. How many days of sick leave? What happens after three late arrivals?" value="${esc(S.polQ || "")}" style="flex:1;font-size:15px;padding:12px 14px">
      <button class="btn primary" type="submit">Ask</button></form>
      <div class="row" style="gap:6px;margin-top:10px;flex-wrap:wrap">${["Annual leave entitlement", "Sick leave and medical certificate", "Late arrival rules", "Notice period on resignation", "Overtime", "Maternity leave"].map(x => `<button class="chip-btn" data-act="pol-try" data-q="${esc(x)}">${esc(x)}</button>`).join("")}</div>
      ${a ? `<div class="pol-ans"><div class="md">${md(a.answer)}</div><small style="color:var(--muted)">${a.engine === "search" ? "Found by search in your policies" : "Answered by " + esc(a.engine) + " from the passages below only"}</small>
        ${a.sources.length ? `<div class="pol-src">${a.sources.map((s, i) => `<details ${i === 0 ? "open" : ""}><summary><b>[${i + 1}] ${esc(s.policy)}</b>${s.heading ? ` · ${esc(s.heading)}` : ""}</summary><div class="pol-txt">${esc(s.text).replace(/\n/g, "<br>")}</div></details>`).join("")}</div>` : ""}</div>` : ""}</div>
    <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Policy library</h2><small>${d.policies.length} document${d.policies.length === 1 ? "" : "s"} · kept on this computer only</small></div>
      <div class="tbl-wrap"><table class="t"><thead><tr><th>Policy</th><th>File</th><th class="n">Passages</th><th class="n">Words</th><th>Added</th><th></th></tr></thead><tbody>
      ${d.policies.map(p => `<tr><td><b>${esc(p.title)}</b></td><td><small>${esc(p.file_name || "pasted")}</small></td><td class="n">${p.passages}</td><td class="n">${p.words.toLocaleString("en-US")}</td><td class="nw">${esc((p.added_at || "").slice(0, 10))}</td>
        <td class="n"><button class="btn sm ghost" data-act="pol-view" data-id="${p.id}">Read</button><button class="btn sm ghost danger" data-act="pol-del" data-id="${p.id}">×</button></td></tr>`).join("")
        || `<tr><td colspan="6"><div class="empty drop-hint">No policies yet. Add the HR manual, leave policy, code of conduct… as PDF, Word or text (or drop the files here).</div></td></tr>`}</tbody></table></div></div>`;
};
AFTER.policies = () => {
  const f = $("#pol-f");
  if (f) f.onsubmit = async e => { e.preventDefault(); const q = $("#pol-q").value.trim(); if (!q) return; S.polQ = q;
    const b = f.querySelector("button"); b.disabled = true; b.innerHTML = `<span class="spin" style="width:13px;height:13px"></span>`;
    try { S.polAns = await call("policy_ask", { question: q }); } finally { render(); } };
  const page = $(".page");
  if (page) { page.ondragover = e => { e.preventDefault(); }; page.ondrop = async e => { e.preventDefault(); if (!e.dataTransfer.files.length) return; polAfter(await call("policy_upload", { files: await filesToB64(e.dataTransfer.files) })); }; }
};
function polAfter(r) {
  if (!r || r.cancelled) return;
  if (r.added.length) toast(`Added ${r.added.length} polic${r.added.length > 1 ? "ies" : "y"}`);
  r.failed.forEach(f => toast(`${f.file}: ${f.error}`, { err: true }));
  render();
}

/* ============================================================== 2.2 Goals */
PAGES.goals = async () => {
  const d = DATA.goals = await API.call("goals");
  const k = (l, v, s, cls = "") => `<div class="kpi"><span class="kpi-l">${esc(l)}</span><span class="kpi-v ${cls}">${v}</span><span class="kpi-s"><span>${esc(s)}</span></span></div>`;
  const C = d.counts, cls = { "on track": "good", achieved: "good", "at risk": "warn", "off track": "bad", missed: "bad", "no update": "", done: "good", dropped: "" };
  return `<div class="ph"><div><h1>Goals</h1><p>Store and department goals with a baseline, a target and a date. Update the number as it moves; P&O tells you if it is on track for the date.</p></div>
      <div class="row"><button class="btn primary" data-act="goal-new">+ New goal</button></div></div>
    <div class="kpis k5">${k("Open goals", d.open, "being tracked")}${k("On track", (C["on track"] || 0) + (C.achieved || 0), "incl. achieved")}${k("At risk", C["at risk"] || 0, "behind the time elapsed", C["at risk"] ? "t-warn" : "")}
      ${k("Off track or missed", (C["off track"] || 0) + (C.missed || 0), "need a decision", (C["off track"] || C.missed) ? "t-bad" : "")}${k("Average progress", d.avg_progress == null ? "—" : d.avg_progress + "%", "of open goals")}</div>
    <div class="goal-grid">${d.rows.map(g => `<div class="goal ${cls[g.state] || ""}"><div class="row" style="justify-content:space-between;align-items:flex-start"><div><b>${esc(g.title)}</b><span class="sub">${esc([g.level, g.store, g.owner].filter(Boolean).join(" · "))}</span></div><span class="chip ${cls[g.state] || ""}">${esc(g.state)}</span></div>
        <div class="goal-nums"><span><small>Baseline</small>${g.baseline ?? "—"}${esc(g.unit || "")}</span><span class="cur"><small>${esc(g.metric || "Now")}</small>${g.current ?? "—"}${esc(g.unit || "")}</span><span><small>Target</small>${g.target ?? "—"}${esc(g.unit || "")}</span></div>
        <div class="goal-bar"><i style="width:${Math.min(100, g.progress || 0)}%"></i></div>
        <div class="row" style="justify-content:space-between"><small>${g.progress == null ? "No numbers yet" : g.progress + "% of the way"} · due ${fmtDate(g.due)}</small>
          <span><button class="btn sm" data-act="goal-upd" data-id="${g.id}">Update</button>${g.status === "open" ? `<button class="btn sm ghost" data-act="goal-done" data-id="${g.id}">Close</button>` : ""}<button class="btn sm ghost danger" data-act="goal-del" data-id="${g.id}">×</button></span></div>
        ${g.history.length > 1 ? `<div class="goal-spark" data-spark="${esc(JSON.stringify(g.history.filter(h => h.value != null).map(h => h.value)))}"></div>` : ""}
        ${g.history.length && g.history[g.history.length - 1].note ? `<small class="sub">“${esc(g.history[g.history.length - 1].note)}”</small>` : ""}</div>`).join("")
      || `<div class="panel"><div class="empty">No goals yet. Start from a template:<div class="row" style="justify-content:center;gap:6px;margin-top:10px;flex-wrap:wrap">${d.templates.map((t, i) => `<button class="chip-btn" data-act="goal-new" data-t="${i}">${esc(t.title)}</button>`).join("")}</div></div></div>`}</div>`;
};
AFTER.goals = () => {
  $$(".goal-spark").forEach(el => { const v = JSON.parse(el.dataset.spark || "[]"); el.innerHTML = Charts.spark(v, { w: 260, h: 28, color: "var(--brand)" }); });
};
function goalForm(t = {}) {
  const m = modal(`<h3>New goal</h3><div class="hform"><label class="dx-l" style="grid-column:1/-1">Goal<input class="input" id="gf-title" value="${esc(t.title || "")}" placeholder="e.g. Cut leavers at Lucky One"></label>
    <label class="dx-l">Measure<input class="input" id="gf-metric" value="${esc(t.metric || "")}" placeholder="e.g. Leavers per month"></label><label class="dx-l">Unit<input class="input" id="gf-unit" value="${esc(t.unit || "")}" placeholder="%, PKR, pts"></label>
    <label class="dx-l">Baseline (now)<input class="input" id="gf-base" type="number" step="any"></label><label class="dx-l">Target<input class="input" id="gf-target" type="number" step="any"></label>
    <label class="dx-l">Store<input class="input" id="gf-store" list="gf-stores"><datalist id="gf-stores">${((S.init.options && S.init.options.stores) || []).map(s => `<option value="${esc(s.name || s.label || s)}">`).join("")}</datalist></label><label class="dx-l">Owner<input class="input" id="gf-owner"></label>
    <label class="dx-l">Level<select class="input" id="gf-level">${["Country", "Store", "Department", "Section", "Person"].map(l => `<option ${l === (t.level || "Store") ? "selected" : ""}>${l}</option>`).join("")}</select></label><label class="dx-l">Due<input class="input" type="date" id="gf-due"></label></div>
    <div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" data-act="modal-close">Cancel</button><button class="btn primary" id="gf-save">Add goal</button></div>`);
  $("#gf-save", m).onclick = async () => { const v = id => $(id, m).value; if (!v("#gf-title").trim()) return toast("Write the goal.", { err: true });
    await call("goal_add", { title: v("#gf-title"), metric: v("#gf-metric"), unit: v("#gf-unit"), baseline: v("#gf-base"), target: v("#gf-target"), store: v("#gf-store"), owner: v("#gf-owner"), level: v("#gf-level"), due: v("#gf-due") || null });
    closeModal(); toast("Goal added"); render(); };
}

/* ============================================================== 2.2 1:1s and visits */
PAGES.notes = async () => {
  const d = DATA.notes = await API.call("meetings");
  const k = (l, v, s, cls = "") => `<div class="kpi"><span class="kpi-l">${esc(l)}</span><span class="kpi-v ${cls}">${v}</span><span class="kpi-s"><span>${esc(s)}</span></span></div>`;
  const f = S.noteKind || "all", rows = d.rows.filter(r => f === "all" || r.kind === f);
  const moods = ["", "😟", "🙁", "😐", "🙂", "😄"];
  return `<div class="ph"><div><h1>1:1s & visits</h1><p>Notes from one-to-ones, store visits and coaching. A follow-up becomes an action with an owner and date.</p></div>
      <div class="row"><button class="btn" data-act="visit-new">📋 Store visit checklist</button><button class="btn primary" data-act="note-new">+ New note</button></div></div>
    <div class="kpis">${k("Notes", d.rows.length, "all time")}${k("People met", d.people, "with at least one note")}${k("Open follow-ups", d.open_follow_ups, "in the action tracker", d.open_follow_ups ? "t-warn" : "")}${k("No 1:1 in 45 days", d.overdue_1to1.length, "leaders", d.overdue_1to1.length ? "t-warn" : "")}</div>
    <div class="grid g2" style="grid-template-columns:2fr 1fr">
      <div class="panel flush"><div class="row" style="padding:12px 14px 0"><div class="seg">${["all", ...d.kinds].map(x => `<button data-act="note-kind" data-k="${esc(x)}" aria-pressed="${f === x}">${x === "all" ? "All" : esc(x)}</button>`).join("")}</div></div>
        <div class="note-list">${rows.map(r => `<div class="note"><div class="row" style="justify-content:space-between"><div><b>${esc(r.subject)}</b> <span class="chip">${esc(r.kind)}</span> ${r.mood ? `<span title="Mood">${moods[r.mood]}</span>` : ""}<span class="sub">${esc(r.store || "")} · ${fmtDate(r.met_on)}</span></div><button class="btn sm ghost danger" data-act="note-del" data-id="${r.id}">×</button></div>
          ${r.body ? `<div class="note-b">${esc(r.body).replace(/\n/g, "<br>")}</div>` : ""}${r.follow_up ? `<div class="note-f">→ ${esc(r.follow_up)}${r.follow_due ? ` · by ${fmtDate(r.follow_due)}` : ""} <span class="chip ${r.action_status === "done" ? "good" : "warn"}">${esc(r.action_status || "")}</span></div>` : ""}</div>`).join("") || `<div class="empty">No notes yet.</div>`}</div></div>
      <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Due a 1:1</h2><small>No 1:1 note in 45 days</small></div><div class="tbl-wrap" style="max-height:520px"><table class="t"><tbody>
        ${d.overdue_1to1.map(x => `<tr><td><b>${esc(x.name)}</b><span class="sub">${esc(x.role || "")} · ${esc(x.store || "")}${x.last ? " · last " + fmtDate(x.last) : " · never"}</span></td><td class="n"><button class="btn sm" data-act="note-new" data-subject="${esc(x.name)}" data-key="${esc(x.key)}" data-store="${esc(x.store || "")}">Log 1:1</button></td></tr>`).join("") || `<tr><td><div class="empty">Everyone is up to date.</div></td></tr>`}</tbody></table></div></div></div>`;
};
function noteForm(o = {}) {
  const m = modal(`<h3>${o.subject ? "1:1 with " + esc(o.subject) : "New note"}</h3><div class="hform">
    <label class="dx-l">Person or store<input class="input" id="nf-sub" value="${esc(o.subject || "")}"></label><label class="dx-l">Type<select class="input" id="nf-kind">${(DATA.notes?.kinds || ["1:1", "Store visit", "Feedback", "Coaching", "Concern", "Recognition"]).map(x => `<option>${esc(x)}</option>`).join("")}</select></label>
    <label class="dx-l">Store<input class="input" id="nf-store" value="${esc(o.store || "")}"></label><label class="dx-l">Date<input class="input" type="date" id="nf-when" value="${new Date().toISOString().slice(0, 10)}"></label></div>
    <label class="dx-l" style="margin-top:8px">What was discussed<textarea class="input" id="nf-body" rows="5" style="width:100%" placeholder="Wins, concerns, support needed, career…"></textarea></label>
    <div class="hform" style="margin-top:8px"><label class="dx-l" style="grid-column:1/-1">Follow-up (becomes an action)<input class="input" id="nf-fu" placeholder="Optional"></label><label class="dx-l">Follow-up by<input class="input" type="date" id="nf-due"></label>
    <label class="dx-l">Mood<div class="seg" id="nf-mood">${["😟", "🙁", "😐", "🙂", "😄"].map((x, i) => `<button type="button" data-v="${i + 1}" aria-pressed="false">${x}</button>`).join("")}</div></label></div>
    <div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" data-act="modal-close">Cancel</button><button class="btn primary" id="nf-save">Save note</button></div>`);
  let mood = null;
  $$("#nf-mood button", m).forEach(b => b.onclick = () => { mood = +b.dataset.v; $$("#nf-mood button", m).forEach(x => x.setAttribute("aria-pressed", x === b)); });
  $("#nf-save", m).onclick = async () => { const v = id => $(id, m).value; if (!v("#nf-sub").trim()) return toast("Who is the note about?", { err: true });
    await call("meeting_add", { subject: v("#nf-sub"), subject_key: o.key || "", kind: v("#nf-kind"), store: v("#nf-store"), when: v("#nf-when"), body: v("#nf-body"), follow_up: v("#nf-fu"), follow_due: v("#nf-due") || null, mood });
    closeModal(); toast("Note saved"); if (["notes", "talent"].includes(S.page)) render(); };
}

const WORK_ACTS = {
  "pol-add": async () => polAfter(await call("policy_pick")),
  "pol-paste": () => { const m = modal(`<h3>Paste a policy</h3><label class="dx-l">Title<input class="input" id="pp-t" placeholder="e.g. Leave Policy 2026"></label><label class="dx-l" style="margin-top:8px">Text<textarea class="input" id="pp-x" rows="14" style="width:100%"></textarea></label>
      <div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" data-act="modal-close">Cancel</button><button class="btn primary" id="pp-save">Add</button></div>`);
    $("#pp-save", m).onclick = async () => { await call("policy_paste", { title: $("#pp-t", m).value, text: $("#pp-x", m).value }); closeModal(); toast("Policy added"); render(); }; },
  "pol-try": b => { S.polQ = b.dataset.q; const i = $("#pol-q"); if (i) { i.value = b.dataset.q; $("#pol-f").requestSubmit(); } },
  "pol-del": b => softDelete("Policy", b.closest("tr,.panel,.pol,li,.card"), () => API.call("policy_delete", { policy_id: +b.dataset.id }), render),
  "pol-view": async b => { const p = await call("policy_view", { policy_id: +b.dataset.id });
    modal(`<h3>${esc(p.title)}</h3><div class="pol-read">${p.passages.map(c => `${c.heading ? `<h4>${esc(c.heading)}</h4>` : ""}<p>${esc(c.text).replace(/\n/g, "<br>")}</p>`).join("")}</div><div class="row" style="justify-content:flex-end;margin-top:10px"><button class="btn" data-act="modal-close">Close</button></div>`); },
  "goal-new": b => goalForm(b.dataset.t != null ? DATA.goals.templates[+b.dataset.t] : {}),
  "goal-upd": b => { const g = DATA.goals.rows.find(x => x.id === +b.dataset.id);
    const m = modal(`<h3>Update: ${esc(g.title)}</h3><div class="hform"><label class="dx-l">${esc(g.metric || "Value")} now<input class="input" id="gu-v" type="number" step="any" value="${g.current ?? ""}"></label><label class="dx-l">Due<input class="input" type="date" id="gu-due" value="${esc(g.due || "")}"></label></div>
      <label class="dx-l" style="margin-top:8px">Note<input class="input" id="gu-n" placeholder="What changed?"></label><div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" data-act="modal-close">Cancel</button><button class="btn primary" id="gu-save">Save</button></div>`);
    $("#gu-save", m).onclick = async () => { await call("goal_update", { goal_id: g.id, value: $("#gu-v", m).value, note: $("#gu-n", m).value, due: $("#gu-due", m).value || null }); closeModal(); toast("Goal updated"); render(); }; },
  "goal-done": b => { const row = b.closest("tr,.goal,.card,li"); if (row) row.classList.add("opt-done"); b.disabled = true; b.textContent = "✓ Done";   // optimistic
    API.call("goal_update", { goal_id: +b.dataset.id, status: "done" }).then(() => { SNAP.clear(); render(); }, e => { if (row) row.classList.remove("opt-done"); b.disabled = false; b.textContent = "Done"; fail(e); }); },
  "goal-del": b => softDelete("Goal", b.closest("tr,.goal,.card,li"), () => API.call("goal_delete", { goal_id: +b.dataset.id }), render),
  "note-new": b => noteForm({ subject: b.dataset.subject, key: b.dataset.key, store: b.dataset.store }),
  "note-kind": b => { S.noteKind = b.dataset.k; render(); },
  "note-del": b => softDelete("Note", b.closest("tr,.note,.card,li,.tl"), () => API.call("meeting_delete", { note_id: +b.dataset.id }), render),
};
Object.assign(ACT, WORK_ACTS);

/* ============================================================== 2.3 Engagement pulse surveys */
PAGES.engagement = async () => {
  const d = DATA.eng = await API.call("engagement", { survey_id: S.engSurvey || null });
  const k = (l, v, s, cls = "") => `<div class="kpi"><span class="kpi-l">${esc(l)}</span><span class="kpi-v ${cls}">${v}</span><span class="kpi-s"><span>${esc(s)}</span></span></div>`;
  const head = `<div class="ph"><div><h1>Engagement</h1><p>Anonymous pulse surveys: how people feel about their work, manager, schedule, pay and future, by store, with eNPS and comment themes.</p></div>
      <div class="row"><button class="btn" data-act="eng-template">${ic("export", 14)}Survey template</button>${d.has_data ? `<button class="btn" data-act="eng-export">Export</button>` : ""}<button class="btn primary" data-act="eng-import">${ic("import", 14)}Import results</button></div></div>`;
  if (!d.has_data) return head + `<div class="panel"><div class="empty" style="padding:30px"><b>No survey results yet.</b><br>1. Download the survey template (English + Urdu, 12 questions + eNPS).<br>2. Collect answers on paper, Google Forms or MS Forms (no names).<br>3. Import the results file here. Results for a group are only shown when ${d.min_group}+ people answered.</div></div>`;
  const fcls = v => v == null ? "" : v >= 70 ? "t-good" : v >= 50 ? "" : "t-bad";
  const heat = v => v == null ? "var(--line-2)" : `hsl(${Math.round(v * 1.2)}, 55%, ${88 - v * 0.25}%)`;
  return head + `<div class="row" style="margin-bottom:10px;gap:8px"><small>Survey</small><select class="input sm" id="eng-s">${d.surveys.map(s => `<option value="${s.id}" ${s.id === d.survey.id ? "selected" : ""}>${esc(s.title)} · ${esc(s.wave)} · ${s.n} answers</option>`).join("")}</select>
      <button class="btn sm ghost danger" data-act="eng-del" data-id="${d.survey.id}">Remove survey</button></div>
    <div class="kpis k5">${k("Answers", d.survey.n, `${d.response_counts.with_comment} with a comment`)}${k("Favourable", d.favourable == null ? "—" : d.favourable + "%", "agree or strongly agree", fcls(d.favourable))}
      ${k("eNPS", d.enps == null ? "—" : (d.enps > 0 ? "+" : "") + d.enps, "promoters − detractors", d.enps == null ? "" : d.enps >= 10 ? "t-good" : d.enps < 0 ? "t-bad" : "")}
      ${k("Strongest", d.strengths[0] ? d.strengths[0].favourable + "%" : "—", d.strengths[0] ? d.strengths[0].question.slice(0, 48) : "")}${k("Weakest", d.concerns[0] ? d.concerns[0].favourable + "%" : "—", d.concerns[0] ? d.concerns[0].question.slice(0, 48) : "", "t-bad")}</div>
    <div class="grid g2" style="grid-template-columns:1.4fr 1fr">
      <div class="panel"><div class="phd"><h2>By question</h2><small>Share answering 4–5 (favourable)</small></div><div id="ch-engq"></div></div>
      <div class="panel"><div class="phd"><h2>Trend</h2><small>${d.trend.length} survey${d.trend.length > 1 ? "s" : ""}</small></div>${d.trend.length > 1 ? `<div id="ch-engt"></div>` : `<div class="empty">Import the next survey to see the trend.</div>`}
        <h4 style="margin-top:14px">What comments are about</h4>${d.themes.length ? `<div id="ch-ength"></div>` : `<div class="empty">No comments.</div>`}</div></div>
    <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Heatmap by store</h2><small>Favourable % per question · groups under ${d.min_group} answers are hidden to protect anonymity</small></div>
      <div class="tbl-wrap"><table class="t heat"><thead><tr><th>Store</th><th class="n">Answers</th><th class="n">eNPS</th>${d.questions.map((q, i) => `<th class="n" title="${esc(q.question)}">Q${i + 1}</th>`).join("")}</tr></thead><tbody>
      ${d.stores.map(s => s.hidden ? `<tr><td>${esc(s.name)}</td><td class="n">${s.n}</td><td colspan="${d.questions.length + 1}"><small style="color:var(--muted)">Too few answers to show (protects anonymity)</small></td></tr>`
        : `<tr><td><b>${esc(s.name)}</b></td><td class="n">${s.n}</td><td class="n">${s.enps ?? "—"}</td>${s.by_q.map(v => `<td class="n" style="background:${heat(v)}">${v ?? "—"}</td>`).join("")}</tr>`).join("") || `<tr><td colspan="${d.questions.length + 3}"><div class="empty">The file had no Store column.</div></td></tr>`}
      </tbody></table></div><div style="padding:8px 16px 14px">${d.questions.map((q, i) => `<small style="display:inline-block;margin-right:14px"><b>Q${i + 1}</b> ${esc(q.question)}</small>`).join("")}</div></div>
    <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Comments</h2><small>${d.comments.length} · never linked to a person</small></div><div class="note-list" style="max-height:420px">
      ${d.comments.map(c => `<div class="note"><div class="note-b" style="margin:0">“${esc(c.text)}”</div><div>${c.themes.map(t => `<span class="chip">${esc(t)}</span>`).join(" ")}</div></div>`).join("") || `<div class="empty">No comments.</div>`}</div></div>`;
};
AFTER.engagement = () => {
  const d = DATA.eng; if (!d || !d.has_data) { engDrop(); return; }
  const s = $("#eng-s"); if (s) s.onchange = () => { S.engSurvey = +s.value; render(); };
  if ($("#ch-engq")) Charts.hbar($("#ch-engq"), { labels: d.questions.map((q, i) => `Q${i + 1} ${q.question.slice(0, 44)}${q.question.length > 44 ? "…" : ""}`), values: d.questions.map(q => q.favourable), fmt: "pct0", max: 100 });
  if ($("#ch-engt")) Charts.line($("#ch-engt"), { labels: d.trend.map(t => t.wave), series: [{ name: "Favourable %", values: d.trend.map(t => t.favourable) }, { name: "eNPS", values: d.trend.map(t => t.enps) }], height: 180 });
  if ($("#ch-ength")) Charts.hbar($("#ch-ength"), { labels: d.themes.map(t => t[0]), values: d.themes.map(t => t[1]) });
  engDrop();
};
function engDrop() { const page = $(".page"); if (page) { page.ondragover = e => e.preventDefault(); page.ondrop = async e => { e.preventDefault(); if (e.dataTransfer.files.length) engAfter(await call("survey_upload", { files: await filesToB64(e.dataTransfer.files) })); }; } }
function engAfter(r) { if (!r || r.cancelled) return; if (r.added) { toast(`Survey imported: ${r.survey.n} answers`); S.engSurvey = r.survey.id; } (r.failed || []).forEach(f => toast(`${f.file}: ${f.error}`, { err: true })); render(); }

/* ============================================================== 2.3 Recognition */
PAGES.recognition = async () => {
  const d = DATA.stars = await API.call("stars", { month: S.month });
  S.starSel = S.starSel || new Set(d.stars.map((_, i) => i).filter(i => i < 15));
  const icon = a => a.startsWith("Country") ? "🏆" : a === "Perfect attendance" ? "⏱" : "⭐";
  return `<div class="ph"><div><h1>Recognition</h1><p>Stars of the month picked from the data: best leader in every store, the country's top three, perfect attendance. Print certificates in one click.</p></div>
      <div class="row"><button class="btn primary" data-act="star-cert">${ic("export", 14)}Certificates for selected</button></div></div>
    <div class="star-grid">${d.stars.map((s, i) => `<label class="star ${S.starSel.has(i) ? "on" : ""}"><input type="checkbox" data-star="${i}" ${S.starSel.has(i) ? "checked" : ""}><span class="star-i">${icon(s.award)}</span>
      <span><small>${esc(s.award)}</small><b>${esc(s.name)}</b><span class="sub">${esc([s.role, s.store].filter(Boolean).join(" · "))}</span><span class="why">${esc(s.why)}</span></span></label>`).join("") || `<div class="panel"><div class="empty">Import the P&O workbook (leaders) or attendance to pick stars.</div></div>`}</div>`;
};
AFTER.recognition = () => { $$("[data-star]").forEach(c => c.onchange = () => { const i = +c.dataset.star; c.checked ? S.starSel.add(i) : S.starSel.delete(i); c.closest(".star").classList.toggle("on", c.checked); }); };

/* ============================================================== 2.3 Month close */
function monthCloseForm() {
  const m = modal(`<h3>Close ${esc(((S.months || []).find(x => x.value === (S.healthMonth || S.month)) || {}).label || S.healthMonth || S.month || "")}</h3><p style="color:var(--muted);margin:0 0 10px">One zip with everything for the month, then the month is locked so its numbers can't change by accident.</p>
    <ul class="mc-list"><li>Monthly HR Director Pack (PDF)</li><li>P&O Review Pack (PDF)</li><li>People Ranking and Attendance Exceptions (Excel)</li><li>One Store Report per store (PDF)</li><li>Data health checklist (PDF)</li></ul>
    <div class="setting"><div><b>Lock the month</b><small>You can unlock it on Data health</small></div><label class="switch"><input type="checkbox" id="mc-lock" checked><span></span></label></div>
    <div class="setting"><div><b>Hide names</b><small>Employee codes only</small></div><label class="switch"><input type="checkbox" id="mc-hide" ${S.init.hide_names ? "checked" : ""}><span></span></label></div>
    <div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" data-act="modal-close">Cancel</button><button class="btn primary" id="mc-go">Close the month</button></div>`);
  $("#mc-go", m).onclick = async () => { const b = $("#mc-go", m); b.disabled = true; b.innerHTML = `<span class="spin" style="width:13px;height:13px"></span> Building…`;
    try { const r = await call("month_close", { month: S.healthMonth || S.month, lock: $("#mc-lock", m).checked, hide: $("#mc-hide", m).checked });
      closeModal(); if (r.cancelled) return; toast(`Month closed: ${r.files.length} files${r.skipped.length ? `, ${r.skipped.length} skipped` : ""}`, { ms: 8000 }); render(); }
    catch (e) { b.disabled = false; b.textContent = "Close the month"; } };
}

/* ============================================================== 2.3 App lock */
function showLock() {
  if ($("#lockscr")) return;
  const el = document.createElement("div"); el.id = "lockscr";
  el.innerHTML = `<div class="lock-box"><div class="lock-logo">${ic("policies", 30)}</div><h2>P&O is locked</h2><p>Enter your PIN</p>
    <input class="input" id="lock-pin" type="password" inputmode="numeric" maxlength="8" autocomplete="off"><div class="lock-err" id="lock-err"></div><button class="btn primary" id="lock-go">Unlock</button></div>`;
  document.body.appendChild(el);
  const pin = $("#lock-pin", el); setTimeout(() => pin.focus(), 50);
  const go = async () => { try { const r = await API.call("unlock", { pin: pin.value }); if (r.ok) { el.remove(); S.lastActive = Date.now(); } else { $("#lock-err", el).textContent = `Wrong PIN (${r.left} tries left)`; pin.value = ""; el.querySelector(".lock-box").classList.add("shake"); setTimeout(() => el.querySelector(".lock-box").classList.remove("shake"), 400); } }
    catch (e) { $("#lock-err", el).textContent = e.message; } };
  $("#lock-go", el).onclick = go; pin.onkeydown = e => { if (e.key === "Enter") go(); };
}
function lockWatch() {
  S.lastActive = Date.now();
  ["mousemove", "keydown", "click", "wheel"].forEach(ev => document.addEventListener(ev, () => { S.lastActive = Date.now(); }, { passive: true }));
  setInterval(() => { const l = S.init && S.init.lock; if (l && l.enabled && Date.now() - S.lastActive > l.minutes * 60000) showLock(); }, 15000);
}
function lockForm() {
  const on = S.init.lock && S.init.lock.enabled;
  const m = modal(`<h3>${on ? "Change PIN" : "Set a PIN"}</h3><p style="color:var(--muted);margin:0 0 10px">P&O asks for the PIN when it opens and after it has been idle. (It locks the screen; keep Windows locked too.)</p>
    <div class="hform">${on ? `<label class="dx-l" style="grid-column:1/-1">Current PIN<input class="input" id="lk-old" type="password" inputmode="numeric" maxlength="8"></label>` : ""}
    <label class="dx-l">New PIN (4–8 digits)<input class="input" id="lk-pin" type="password" inputmode="numeric" maxlength="8"></label><label class="dx-l">Lock after idle (minutes)<input class="input" id="lk-min" type="number" min="1" max="240" value="${(S.init.lock && S.init.lock.minutes) || 10}"></label></div>
    <div class="row" style="justify-content:flex-end;margin-top:12px">${on ? `<button class="btn danger" id="lk-off">Turn off</button>` : ""}<button class="btn" data-act="modal-close">Cancel</button><button class="btn primary" id="lk-save">Save</button></div>`);
  $("#lk-save", m).onclick = async () => { S.init.lock = await call("lock_set", { pin: $("#lk-pin", m).value, minutes: +$("#lk-min", m).value, old_pin: on ? $("#lk-old", m).value : "" }); closeModal(); toast("PIN saved"); render(); };
  if (on) $("#lk-off", m).onclick = async () => { S.init.lock = await call("lock_off", { pin: $("#lk-old", m).value }); closeModal(); toast("App lock turned off"); render(); };
}

const ENG_ACTS = {
  "eng-import": async () => engAfter(await call("survey_pick")),
  "eng-template": async () => { const r = await call("survey_template"); if (!r.cancelled) toast("Survey template saved"); },
  "eng-export": () => { const m = modal(`<h3>Export survey results</h3><div class="seg" id="ee-f">${[["pdf", "PDF"], ["docx", "Word"], ["pptx", "PowerPoint"], ["xlsx", "Excel"]].map(([v, l], i) => `<button data-v="${v}" aria-pressed="${i === 0}">${l}</button>`).join("")}</div>
      <div class="row" style="justify-content:flex-end;margin-top:12px"><button class="btn" data-act="modal-close">Cancel</button><button class="btn primary" id="ee-go">Export</button></div>`);
    let f = "pdf"; $$("#ee-f button", m).forEach(b => b.onclick = () => { f = b.dataset.v; $$("#ee-f button", m).forEach(x => x.setAttribute("aria-pressed", x === b)); });
    $("#ee-go", m).onclick = async () => { const r = await call("engagement_export", { survey_id: DATA.eng.survey.id, fmt: f }); closeModal(); if (!r.cancelled) toast("Exported"); }; },
  "eng-del": b => { const el = $(".page"); S.engSurvey = null; softDelete("Survey", null, () => API.call("survey_delete", { survey_id: +b.dataset.id }), render); render(); },
  "star-cert": async () => { const ppl = DATA.stars.stars.filter((_, i) => S.starSel.has(i)); if (!ppl.length) return toast("Select at least one person.", { err: true });
    const r = await call("certificates", { people: ppl }); if (!r.cancelled) toast(`${r.n} certificates ready`); },
  "month-close": () => monthCloseForm(),
  "lock-set": () => lockForm(),
};
Object.assign(ACT, ENG_ACTS);

/* ============================================================== 2.4 Workforce plan: forecast and what-if */
S.fc = S.fc || { months: 6, turnover_change: 0, hires_per_month: "", growth_heads: 0, replacement_cost: "" };
PAGES.forecast = async () => {
  const p = S.fc;
  const d = DATA.fc = await API.call("forecast", { months: p.months, turnover_change: p.turnover_change, hires_per_month: p.hires_per_month === "" ? null : +p.hires_per_month,
    growth_heads: p.growth_heads, replacement_cost: p.replacement_cost === "" ? null : +p.replacement_cost });
  const b = d.baseline, pk = v => "PKR " + Math.round(v).toLocaleString("en-US");
  const k = (l, v, s, cls = "") => `<div class="kpi"><span class="kpi-l">${esc(l)}</span><span class="kpi-v ${cls}">${v}</span><span class="kpi-s"><span>${esc(s)}</span></span></div>`;
  const last = a => a[a.length - 1];
  return `<div class="ph"><div><h1>Workforce plan</h1><p>Where headcount is heading at today's leaver rate, and what changes if turnover falls, hiring speeds up or new heads are added.</p></div></div>
    <div class="kpis k5">${k("Headcount now", b.headcount.toLocaleString("en-US"), b.approved ? `${b.approved.toLocaleString("en-US")} approved` : "no approved manning yet")}
      ${k("Leavers a month", b.leavers_per_month, `last 12 months · ${b.voluntary_share}% resigned`)}${k("Yearly turnover", b.annual_rate == null ? "—" : b.annual_rate + "%", "leavers ÷ headcount")}
      ${k(`Headcount in ${d.labels.length} months`, last(d.series.scenario).toLocaleString("en-US"), `today's trend: ${last(d.series.today).toLocaleString("en-US")}`, last(d.series.scenario) < last(d.series.today) ? "t-warn" : "")}
      ${k("Saving from scenario", d.cost.saving > 0 ? pk(d.cost.saving) : "—", `${d.leavers.today - d.leavers.scenario} fewer leavers × ${pk(b.replacement_cost)}`, d.cost.saving > 0 ? "t-good" : "")}</div>
    <div class="grid g2" style="grid-template-columns:320px 1fr">
      <div class="panel fc-ctl"><div class="phd"><h2>What if…</h2></div>
        <label class="dx-l">Months ahead <b id="fc-mv">${p.months}</b><input type="range" min="3" max="18" step="1" value="${p.months}" data-fc="months"></label>
        <label class="dx-l">Turnover change <b id="fc-tv">${p.turnover_change > 0 ? "+" : ""}${p.turnover_change}%</b><input type="range" min="-60" max="60" step="5" value="${p.turnover_change}" data-fc="turnover_change"></label>
        <label class="dx-l">Hires a month<input class="input" type="number" min="0" step="1" placeholder="Replace leavers (${d.scenario.leavers_per_month})" value="${esc(p.hires_per_month)}" data-fc="hires_per_month"></label>
        <label class="dx-l">New heads to add (store openings, growth)<input class="input" type="number" min="0" step="5" value="${p.growth_heads}" data-fc="growth_heads"></label>
        <label class="dx-l">Cost to replace one leaver (PKR)<input class="input" type="number" min="0" step="5000" placeholder="${b.replacement_cost}" value="${esc(p.replacement_cost)}" data-fc="replacement_cost"><small>Hiring, onboarding and training time</small></label>
        <button class="btn sm ghost" data-act="fc-reset">Reset</button></div>
      <div class="panel"><div class="phd"><h2>Headcount projection</h2><small>${d.scenario.leavers_per_month} leavers and ${d.scenario.hires_per_month} hires a month in the scenario</small></div><div id="ch-fc"></div>
        <div class="fc-sum">${[["Leavers over the period", `${d.leavers.scenario}`, `today's rate: ${d.leavers.today}`], ["Cost of turnover", pk(d.cost.scenario), `today's rate: ${pk(d.cost.today)}`],
          ["Hires needed", d.hires_needed, `${d.hires_per_month_needed} a month to stay at plan`], ["Open vacancies", b.open_vacancies, "in Hiring"]].map(([l, v, s]) => `<div><small>${l}</small><b>${v}</b><span>${esc(s)}</span></div>`).join("")}</div></div></div>
    ${b.monthly.length ? `<div class="panel"><div class="phd"><h2>Leavers by month</h2><small>the base for the forecast</small></div><div id="ch-fcm"></div></div>` : ""}`;
};
AFTER.forecast = () => {
  const d = DATA.fc; if (!d) return;
  const s = [{ name: "Today's trend", values: d.series.today }, { name: "Scenario", values: d.series.scenario }];
  if (d.series.target) s.push({ name: "Plan with new heads", values: d.series.target });
  Charts.line($("#ch-fc"), { labels: d.labels, series: s, height: 260 });
  if ($("#ch-fcm")) Charts.columns($("#ch-fcm"), { labels: d.baseline.monthly.map(m => m.month), series: [{ name: "Leavers", values: d.baseline.monthly.map(m => m.leavers) }], height: 180 });
  $$("[data-fc]").forEach(i => {
    const set = () => { S.fc[i.dataset.fc] = i.type === "range" ? +i.value : i.value; if (i.dataset.fc === "months") $("#fc-mv").textContent = i.value; if (i.dataset.fc === "turnover_change") $("#fc-tv").textContent = (+i.value > 0 ? "+" : "") + i.value + "%"; };
    i.oninput = set; i.onchange = () => { set(); render(); };
  });
};

/* ============================================================== 2.4 Training needs */
async function trainingNeedsHtml(head) {
  const d = DATA.tn = await API.call("training_needs", { threshold: S.tnThr || 60 });
  const k = (l, v, s, cls = "") => `<div class="kpi"><span class="kpi-l">${esc(l)}</span><span class="kpi-v ${cls}">${v}</span><span class="kpi-s"><span>${esc(s)}</span></span></div>`;
  const stc = { "not assigned": "bad", assigned: "warn", "in progress": "warn", completed: "good" };
  return head("Training needs", "Every leader's weak measures from the P&O review, matched to a course. Build one targeted course per topic and assign it to everyone who needs it.") +
    (d.empty ? `<div class="panel"><div class="empty">Import the P&O workbook to see training needs.</div></div>` :
    `<div class="row" style="margin-bottom:10px;gap:8px"><small>A measure is weak below</small><select class="input sm" id="tn-thr">${[50, 60, 70].map(v => `<option value="${v}" ${v === (S.tnThr || 60) ? "selected" : ""}>${v / 10}/10</option>`).join("")}</select></div>
    <div class="kpis">${k("Leaders with a need", d.leaders_with_needs, "at least one weak measure")}${k("Needs not covered", d.open_needs, "no course assigned", d.open_needs ? "t-warn" : "")}${k("Already covered", d.covered, "course assigned or done", "t-good")}${k("Topics", d.topics.length, "to build")}</div>
    <div class="tn-topics">${d.topics.map(t => `<div class="tn-t"><div><b>${esc(t.title)}</b><span class="sub">${t.n} leader${t.n > 1 ? "s" : ""} · ${esc(t.stores.slice(0, 4).join(", "))}${t.stores.length > 4 ? "…" : ""}</span></div>
      <button class="btn sm primary" data-act="tn-build" data-t="${esc(t.topic)}">Build & assign</button></div>`).join("") || `<div class="panel"><div class="empty">Every need is covered by an assigned course. 🎉</div></div>`}</div>
    <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>By leader</h2></div><div class="tbl-wrap" style="max-height:560px"><table class="t"><thead><tr><th>Leader</th><th>Store</th><th class="n">Index</th><th>Weak measures → course</th></tr></thead><tbody>
      ${d.rows.map(r => `<tr><td><b>${esc(r.name)}</b><span class="sub">${esc(r.role)}</span></td><td>${esc(r.store)}</td><td class="n">${r.index == null ? "—" : (r.index / 10).toFixed(1)}</td>
        <td>${r.needs.map(n => `<div class="tn-n"><span>${esc(n.measure)} <b>${n.score}</b> → ${esc(n.topic_title)}</span><span class="chip ${stc[n.status] || ""}">${esc(n.status)}</span></div>`).join("")}</td></tr>`).join("")}</tbody></table></div></div>`);
}
Object.assign(ACT, {
  "fc-reset": () => { S.fc = { months: 6, turnover_change: 0, hires_per_month: "", growth_heads: 0, replacement_cost: "" }; render(); },
  "tn-build": async b => { const t = DATA.tn.topics.find(x => x.topic === b.dataset.t); if (!confirm(`Build "${t.title}" (about 3 hours) and assign it to ${t.n} leader${t.n > 1 ? "s" : ""}?`)) return;
    b.disabled = true; b.innerHTML = `<span class="spin" style="width:13px;height:13px"></span>`;
    const r = await call("training_build", { topic: t.topic, hours: 3, threshold: S.tnThr || 60 }); toast(`Course built and assigned to ${r.assigned}`, { action: "Open course", onAction: () => { S.learn = { ...S.learn, cid: r.course_id, mod: 0, les: 0, view: "lesson" }; render(); } }); render(); },
});

/* ============================================================== Organisation health */
PAGES.organisation = async () => {
  const d = DATA.org = await API.call("organisation", {});
  const ch = d.changes, sp = d.span, pr = d.probation, ca = d.calibration;
  const k = (l, v, s, cls = "") => `<div class="kpi"><span class="kpi-l">${esc(l)}</span><span class="kpi-v ${cls}">${v}</span><span class="kpi-s"><span>${esc(s)}</span></span></div>`;
  const list = (title, rows, f, empty) => `<div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>${title}</h2><small>${rows.length}</small></div><div class="tbl-wrap" style="max-height:320px"><table class="t"><tbody>${rows.map(f).join("") || `<tr><td><div class="empty">${empty}</div></td></tr>`}</tbody></table></div></div>`;
  return `<div class="ph"><div><h1>Organisation</h1><p>Who joined, left, moved and got promoted; span of control; probation; and whether ratings are calibrated and fair.</p></div></div>
    <div class="kpis k5">${k("Headcount", d.headcount.toLocaleString("en-US"), "Basic Sheet")}${k("Joiners", ch.has_data ? ch.joiners.length : "—", ch.has_data ? "since " + ch.from_date : "no comparison yet")}
      ${k("Leavers", ch.has_data ? ch.leavers.length : "—", ch.has_data ? `${ch.unexplained_leavers.length} not on the turnover tab` : "")}${k("Probation ending", pr.due_30, `${pr.overdue} past the end date`, pr.overdue ? "t-warn" : "")}
      ${k("Span of control", sp.avg ?? "—", `${sp.too_wide} managers with 15+ reports`)}</div>
    <div class="panel"><div class="phd"><h2>Changes since the last Basic Sheet</h2><small>${ch.has_data ? `${esc(ch.from)} → ${esc(ch.to)}` : ""}</small></div>
      ${ch.has_data ? `<div class="grid g3">
        ${list("Joined", ch.joiners, r => `<tr><td><b>${esc(r.name)}</b><span class="sub">${esc(r.role || "")} · ${esc(r.store || "")}</span></td></tr>`, "Nobody new")}
        ${list("Left", ch.leavers, r => `<tr><td><b>${esc(r.name)}</b><span class="sub">${esc(r.role || "")} · ${esc(r.store || "")}${ch.unexplained_leavers.some(u => u.id === r.id) ? ` · <span class="t-warn">not on the turnover tab</span>` : ""}</span></td></tr>`, "Nobody left")}
        ${list("Moved or changed role", [...ch.roles.map(r => ({ ...r, t: "role" })), ...ch.transfers.map(r => ({ ...r, t: "move" }))], r => `<tr><td><b>${esc(r.name)}</b><span class="sub">${r.t === "role" ? `${esc(r.from || "—")} → <b>${esc(r.to)}</b>${r.promotion ? " ⬆ promotion" : ""}` : `${esc(r.from || "—")} → <b>${esc(r.to)}</b> (transfer)`}</span></td></tr>`, "No moves")}
      </div>${ch.managers.length ? `<small style="color:var(--muted)">${ch.managers.length} people now report to a different manager.</small>` : ""}` : `<div class="empty">${esc(ch.note)}</div>`}</div>
    <div class="grid g2">
      <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Probation</h2><div class="row"><small>length</small><select class="input sm" id="org-prob">${[3, 6].map(n => `<option value="${n}" ${n === pr.months ? "selected" : ""}>${n} months</option>`).join("")}</select></div></div>
        <div class="tbl-wrap" style="max-height:360px"><table class="t"><thead><tr><th>Name</th><th>Store</th><th>Joined</th><th>Ends</th><th>Status</th></tr></thead><tbody>
        ${pr.rows.map(r => `<tr><td><b>${esc(r.name)}</b><span class="sub">${esc(r.role || "")}</span></td><td>${esc(r.store || "")}</td><td class="nw">${fmtDate(r.joined)}</td><td class="nw">${fmtDate(r.ends)}</td>
          <td><span class="chip ${r.days < 0 ? "bad" : r.days <= 30 ? "warn" : ""}">${esc(r.status)}</span></td></tr>`).join("") || `<tr><td colspan="5"><div class="empty">Nobody near the end of probation (needs joining dates on the Basic Sheet).</div></td></tr>`}</tbody></table></div></div>
      <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Span of control</h2><small>Direct reports per manager (from the Basic Sheet)</small></div>
        <div class="tbl-wrap" style="max-height:360px"><table class="t"><thead><tr><th>Manager</th><th>Store</th><th class="n">Direct reports</th><th></th></tr></thead><tbody>
        ${sp.rows.map(r => `<tr><td><b>${esc(r.manager)}</b><span class="sub">${esc(r.role)}</span></td><td>${esc(r.store)}</td><td class="n">${r.direct_reports}</td><td>${r.flag ? `<span class="chip ${r.flag === "Too wide" ? "warn" : ""}">${r.flag}</span>` : ""}</td></tr>`).join("") || `<tr><td colspan="4"><div class="empty">Needs manager names on the Basic Sheet.</div></td></tr>`}</tbody></table></div></div>
    </div>
    <div class="panel flush"><div class="phd" style="padding:14px 16px 0"><h2>Manager effectiveness</h2><small>How each manager's team is doing: leader index 45% · team rating 25% · people leaving 20% · discipline 10%</small></div>
      <div class="tbl-wrap" style="max-height:420px"><table class="t"><thead><tr><th>Manager</th><th>Store</th><th class="n">Team</th><th class="n">Team index</th><th class="n">Team rating</th><th class="n">Leavers</th><th class="n">DA</th><th>Effectiveness</th><th>Watch</th></tr></thead><tbody>
      ${d.managers.rows.map(r => `<tr><td><b>${esc(r.manager)}</b><span class="sub">${esc(r.role || "")}</span></td><td>${esc(r.store)}</td><td class="n">${r.team}</td><td class="n">${r.team_index ?? "—"}</td><td class="n">${r.team_rating ?? "—"}</td><td class="n">${r.leavers || ""}</td><td class="n">${r.da || ""}</td>
        <td><div class="hbarw"><div class="hbarv ${r.band === "Strong" ? "strong" : r.band === "Steady" ? "possible" : "weak"}" style="width:${Math.max(2, r.score)}%"></div><b>${Math.round(r.score)}</b></div></td><td><small>${esc(r.why.join(" · ") || "—")}</small></td></tr>`).join("") || `<tr><td colspan="9"><div class="empty">Needs manager names on the Basic Sheet.</div></td></tr>`}</tbody></table></div></div>
    <div class="panel"><div class="phd"><h2>Rating calibration and fairness</h2><small>${ca.has_data ? `${ca.n} rated · average ${ca.avg} · ${ca.top_share}% rated 4–5` : "Import Performance Rating to check calibration"}</small></div>
      ${ca.has_data ? `${ca.flags.map(f => `<div class="alert warn"><span class="ic">•</span><span>${esc(f)}</span></div>`).join("") || `<div class="alert good"><span class="ic">✓</span><span>No calibration or fairness flags.</span></div>`}
      <div class="grid g3" style="margin-top:10px"><div><h4>Distribution</h4><div id="ch-cal"></div></div>
        <div><h4>By store</h4><table class="t"><tbody>${ca.by_store.map(x => `<tr><td>${esc(x.name)}</td><td class="n">${x.avg}</td><td class="n"><small>${x.n} rated</small></td></tr>`).join("")}</tbody></table></div>
        <div><h4>By gender</h4><table class="t"><tbody>${ca.by_gender.map(x => `<tr><td>${esc(x.name)}</td><td class="n">${x.avg}</td><td class="n"><small>${x.n} rated · ${x.share_top}% top</small></td></tr>`).join("") || `<tr><td><small>Gender not on file</small></td></tr>`}</tbody></table>
        ${ca.by_manager.length ? `<h4>By manager (3+ rated)</h4><table class="t"><tbody>${ca.by_manager.slice(0, 8).map(x => `<tr><td>${esc(x.name)}</td><td class="n">${x.avg}</td><td class="n ${Math.abs(x.gap) >= 0.6 ? "t-warn" : ""}">${x.gap > 0 ? "+" : ""}${x.gap}</td></tr>`).join("")}</tbody></table>` : ""}</div></div>` : ""}</div>`;
};
AFTER.organisation = () => {
  const d = DATA.org;
  const sel = $("#org-prob"); if (sel) sel.onchange = async () => { await call("organisation", { probation_months: +sel.value }); render(); };
  if (d && d.calibration.has_data && $("#ch-cal")) Charts.columns($("#ch-cal"), { labels: d.calibration.distribution.map(x => "Rating " + x.rating), series: [{ name: "People", values: d.calibration.distribution.map(x => x.count) }], height: 180 });
};
function applyTheme(t) { if (t === "light" || t === "dark") document.documentElement.dataset.theme = t; else delete document.documentElement.dataset.theme; }

async function boot(keepPage) {
  if (!keepPage || !S.init) S.init = await API.call("init");
  applyTheme(S.init.theme);
  applyMode();
  S.months = S.init.months;
  S.month = S.init.month;
  if (!keepPage) S.page = store.get("page", S.init.full_mode ? "home" : "rv");
  if (ALLOWED && !ALLOWED.has(S.page)) S.page = "rv";
  shell();
  await refreshOptions();
  render();
  if (S.init.notice) toast(S.init.notice, { ms: 15000 });
  if (!S.init.tour_done && !keepPage && !navigator.webdriver) setTimeout(() => tour(0), 900);
  if (!S.lockWatching) { S.lockWatching = true; lockWatch(); if (S.init.lock && S.init.lock.enabled) showLock(); }
  window.PNO_ready = true;
}
boot(false).catch(e => { $("#app").innerHTML = `<div class="errbox" style="margin:40px">P&O could not start: ${esc(e.message || e)}</div>`; });
})();
