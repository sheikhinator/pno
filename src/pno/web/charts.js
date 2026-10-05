/* PNO charts: small, dependency-free SVG charts with hover tooltips and gentle animation.
   Marks: 2px lines, ≥8px markers with a surface ring, bars ≤24px with 4px rounded data-ends, hairline grids.
   Series colours come from CSS tokens (--s1 brown, --s2 blue, --s3 gold), validated for colour-blind separation. */
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const SER = ["var(--s1)", "var(--s2)", "var(--s3)"];
  const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  function tip(html, ev) {
    const t = document.getElementById("tip");
    if (!t) return;
    if (!html) { t.classList.remove("on"); return; }
    t.innerHTML = html;
    t.classList.add("on");
    const r = t.getBoundingClientRect();
    let x = ev.clientX + 14, y = ev.clientY + 14;
    if (x + r.width > innerWidth - 8) x = ev.clientX - r.width - 14;
    if (y + r.height > innerHeight - 8) y = ev.clientY - r.height - 14;
    t.style.left = x + "px"; t.style.top = y + "px";
  }

  function nice(max, min = 0, ticks = 4) {
    const span = Math.max(1e-9, max - min);
    const raw = span / ticks, mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw) || raw;
    const lo = Math.floor(min / step) * step, hi = Math.ceil(max / step) * step;
    const out = [];
    for (let v = lo; v <= hi + step / 2; v += step) out.push(+v.toFixed(10));
    return out;
  }

  function fmtv(v, fmt) {
    if (v == null || isNaN(v)) return "—";
    if (fmt === "pct") return v.toFixed(1) + "%";
    if (fmt === "pct0") return Math.round(v) + "%";
    if (fmt === "score") return v.toFixed(1);
    if (fmt === "int") return Math.round(v).toLocaleString("en-US");
    if (fmt === "money") return Math.abs(v) >= 1e6 ? (v / 1e6).toFixed(1) + "M" : Math.abs(v) >= 1e3 ? (v / 1e3).toFixed(0) + "K" : Math.round(v) + "";
    return Math.abs(v) >= 100 ? Math.round(v).toLocaleString("en-US") : (+v.toFixed(1)).toString();
  }

  function legend(series) {
    if (series.length < 2) return "";
    return `<div class="legend" style="margin-top:6px">${series.map((s, i) =>
      `<span><i class="line" style="background:${s.color || SER[i % 3]};height:3px"></i>${esc(s.name)}</span>`).join("")}</div>`;
  }

  /* ---------------- line ---------------- */
  function line(el, o) {
    const W = o.width || Math.max(320, el.clientWidth || 600), H = o.height || 220;
    const P = { l: 44, r: 18, t: 14, b: 28 };
    const labels = o.labels || [], series = (o.series || []).filter(s => s.values && s.values.some(v => v != null));
    if (!labels.length || !series.length) { el.innerHTML = `<div class="empty" style="padding:30px">No data yet</div>`; return; }
    const vals = series.flatMap(s => s.values.filter(v => v != null));
    let lo = o.yMin != null ? o.yMin : Math.min(...vals), hi = o.yMax != null ? o.yMax : Math.max(...vals);
    if (o.ref != null) { lo = Math.min(lo, o.ref); hi = Math.max(hi, o.ref); }
    if (lo === hi) { lo -= 1; hi += 1; }
    const pad = (hi - lo) * 0.12;
    const ticks = nice(hi + pad, o.yMin != null ? lo : lo - pad);
    const y0 = ticks[0], y1 = ticks[ticks.length - 1];
    const x = i => P.l + (labels.length === 1 ? (W - P.l - P.r) / 2 : i * (W - P.l - P.r) / (labels.length - 1));
    const y = v => P.t + (H - P.t - P.b) * (1 - (v - y0) / (y1 - y0));
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.title || "line chart")}">`;
    ticks.forEach(t => s += `<line class="grid-l" x1="${P.l}" x2="${W - P.r}" y1="${y(t)}" y2="${y(t)}"/><text class="ax" x="${P.l - 8}" y="${y(t) + 4}" text-anchor="end">${fmtv(t, o.fmt === "money" ? "money" : o.axisFmt)}</text>`);
    if (o.ref != null) s += `<line class="ref-l" x1="${P.l}" x2="${W - P.r}" y1="${y(o.ref)}" y2="${y(o.ref)}"/><text class="ax" x="${W - P.r}" y="${y(o.ref) - 5}" text-anchor="end">${esc(o.refLabel || "")}</text>`;
    const every = Math.ceil(labels.length / Math.max(2, Math.floor((W - P.l - P.r) / 56)));
    labels.forEach((l, i) => { if (i % every === 0 || i === labels.length - 1) s += `<text class="ax" x="${x(i)}" y="${H - 8}" text-anchor="middle">${esc(l)}</text>`; });
    series.forEach((se, k) => {
      const c = se.color || SER[k % 3];
      let d = "", len = 0, prev = null;
      se.values.forEach((v, i) => {
        if (v == null) { prev = null; return; }
        const px = x(i), py = y(v);
        d += (prev ? "L" : "M") + px.toFixed(1) + " " + py.toFixed(1) + " ";
        if (prev) len += Math.hypot(px - prev[0], py - prev[1]);
        prev = [px, py];
      });
      if (o.area && series.length === 1) {
        const pts = se.values.map((v, i) => v == null ? null : [x(i), y(v)]).filter(Boolean);
        if (pts.length > 1) s += `<path d="M${pts[0][0]} ${y(y0)} ${pts.map(p => "L" + p[0] + " " + p[1]).join(" ")} L${pts[pts.length - 1][0]} ${y(y0)}Z" fill="${c}" opacity=".1"/>`;
      }
      s += `<path d="${d}" fill="none" stroke="${c}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" class="draw" style="--len:${Math.ceil(len) + 2}"/>`;
      se.values.forEach((v, i) => { if (v != null && (labels.length <= 14 || i === se.values.length - 1)) s += `<circle cx="${x(i)}" cy="${y(v)}" r="4" fill="${c}" stroke="var(--card)" stroke-width="2"/>`; });
      const li = se.values.map((v, i) => v == null ? -1 : i).filter(i => i >= 0).pop();
      if (li != null && li >= 0 && o.endLabel !== false) s += `<text class="val" x="${x(li) + 8}" y="${y(se.values[li]) + 4}">${fmtv(se.values[li], o.fmt)}</text>`;
    });
    s += `<line id="xh" x1="0" x2="0" y1="${P.t}" y2="${H - P.b}" stroke="var(--muted)" stroke-width="1" opacity="0"/>`;
    const bw = labels.length > 1 ? (W - P.l - P.r) / (labels.length - 1) : W - P.l - P.r;
    labels.forEach((l, i) => s += `<rect class="hit" data-i="${i}" x="${x(i) - bw / 2}" y="${P.t}" width="${bw}" height="${H - P.t - P.b}"/>`);
    s += `</svg>`;
    el.innerHTML = `<div class="chart">${s}</div>${legend(series)}`;
    const svg = el.querySelector("svg"), xh = svg.querySelector("#xh");
    svg.querySelectorAll(".hit").forEach(r => {
      const i = +r.dataset.i;
      r.addEventListener("mousemove", ev => {
        xh.setAttribute("x1", x(i)); xh.setAttribute("x2", x(i)); xh.setAttribute("opacity", ".5");
        tip(`<b>${esc(labels[i])}</b>` + series.map((se, k) => `<span style="display:flex;gap:6px;align-items:center"><i style="width:9px;height:3px;background:${se.color || SER[k % 3]};display:inline-block"></i>${esc(se.name)}: <b style="display:inline">${fmtv(se.values[i], o.fmt)}</b></span>`).join(""), ev);
      });
      r.addEventListener("mouseleave", () => { tip(null); xh.setAttribute("opacity", "0"); });
      if (o.onClick) r.addEventListener("click", () => o.onClick(i));
    });
  }

  /* ---------------- horizontal bars ---------------- */
  function hbar(el, o) {
    const labels = o.labels || [], vals = o.values || [];
    if (!labels.length) { el.innerHTML = `<div class="empty" style="padding:30px">No data yet</div>`; return; }
    const W = o.width || Math.max(320, el.clientWidth || 600);
    const row = 30, P = { l: Math.min(190, Math.max(90, Math.max(...labels.map(l => String(l).length)) * 6.6 + 10)), r: 56, t: 6, b: 6 };
    const H = P.t + P.b + row * labels.length;
    const max = o.max != null ? o.max : Math.max(1e-9, ...vals.filter(v => v != null));
    const xw = v => Math.max(0, (W - P.l - P.r) * (v || 0) / max);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.title || "bar chart")}">`;
    if (o.ref != null && o.ref <= max) s += `<line class="ref-l" x1="${P.l + xw(o.ref)}" x2="${P.l + xw(o.ref)}" y1="0" y2="${H}"/>`;
    labels.forEach((l, i) => {
      const yy = P.t + i * row, v = vals[i], bh = Math.min(18, row - 10), w = xw(v);
      const c = (o.colors && o.colors[i]) || o.color || SER[0];
      s += `<rect class="hit" data-i="${i}" x="0" y="${yy}" width="${W}" height="${row}" rx="6"/>`;
      s += `<text class="ax-lbl" x="${P.l - 10}" y="${yy + row / 2 + 4}" text-anchor="end">${esc(String(l).length > 28 ? String(l).slice(0, 27) + "…" : l)}</text>`;
      if (v != null && w > 0) {
        const r = Math.min(4, w / 2);
        s += `<path class="grow" style="transform-origin:${P.l}px 0;animation-delay:${i * 25}ms" d="M${P.l} ${yy + (row - bh) / 2} h${w - r} a${r} ${r} 0 0 1 ${r} ${r} v${bh - 2 * r} a${r} ${r} 0 0 1 -${r} ${r} h-${w - r}Z" fill="${c}" pointer-events="none"/>`;
      }
      s += `<text class="val" x="${P.l + w + 7}" y="${yy + row / 2 + 4}" pointer-events="none">${fmtv(v, o.fmt)}</text>`;
    });
    s += `</svg>`;
    el.innerHTML = `<div class="chart">${s}</div>`;
    el.querySelectorAll(".hit").forEach(r => {
      const i = +r.dataset.i;
      r.addEventListener("mousemove", ev => tip(`<b>${esc(labels[i])}</b>${esc(o.name || "")} ${fmtv(vals[i], o.fmt)}${o.tips ? "<br>" + esc(o.tips[i] || "") : ""}`, ev));
      r.addEventListener("mouseleave", () => tip(null));
      if (o.onClick) r.addEventListener("click", () => { tip(null); o.onClick(i); });
    });
  }

  /* ---------------- columns (single or stacked) ---------------- */
  function columns(el, o) {
    const labels = o.labels || [], series = o.series || [];
    if (!labels.length) { el.innerHTML = `<div class="empty" style="padding:30px">No data yet</div>`; return; }
    const W = o.width || Math.max(320, el.clientWidth || 600), H = o.height || 210;
    const P = { l: 40, r: 10, t: 18, b: 26 };
    const tot = labels.map((_, i) => series.reduce((a, se) => a + (se.values[i] || 0), 0));
    const ticks = nice(Math.max(1, ...tot));
    const top = ticks[ticks.length - 1];
    const slot = (W - P.l - P.r) / labels.length, bw = Math.min(o.barMax || 24, slot * 0.62);
    const y = v => P.t + (H - P.t - P.b) * (1 - v / top);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.title || "column chart")}">`;
    ticks.forEach(t => s += `<line class="grid-l" x1="${P.l}" x2="${W - P.r}" y1="${y(t)}" y2="${y(t)}"/><text class="ax" x="${P.l - 8}" y="${y(t) + 4}" text-anchor="end">${fmtv(t, "int")}</text>`);
    const every = Math.ceil(labels.length / Math.max(2, Math.floor((W - P.l - P.r) / 40)));
    labels.forEach((l, i) => {
      const cx = P.l + slot * i + slot / 2;
      let acc = 0;
      series.forEach((se, k) => {
        const v = se.values[i] || 0;
        if (v <= 0) return;
        const y1 = y(acc + v), y2 = y(acc), isTop = series.slice(k + 1).every(s2 => !(s2.values[i] > 0));
        const h = Math.max(0, y2 - y1 - (acc > 0 ? 2 : 0));
        const r = isTop ? Math.min(4, bw / 2, h) : 0;
        const c = (se.colors && se.colors[i]) || se.color || SER[k % 3];
        s += `<path class="growy" style="animation-delay:${i * 18}ms" d="M${cx - bw / 2} ${y1 + h} v-${h - r} a${r} ${r} 0 0 1 ${r} -${r} h${bw - 2 * r} a${r} ${r} 0 0 1 ${r} ${r} v${h - r}Z" fill="${c}"/>`;
        acc += v;
      });
      if (o.valueLabels !== false && series.length === 1 && tot[i]) s += `<text class="val" x="${cx}" y="${y(tot[i]) - 6}" text-anchor="middle">${fmtv(tot[i], o.fmt || "int")}</text>`;
      if (i % every === 0) s += `<text class="ax" x="${cx}" y="${H - 8}" text-anchor="middle">${esc(l)}</text>`;
      s += `<rect class="hit" data-i="${i}" x="${P.l + slot * i}" y="${P.t}" width="${slot}" height="${H - P.t - P.b}"/>`;
    });
    s += `</svg>`;
    el.innerHTML = `<div class="chart">${s}</div>${series.length > 1 ? `<div class="legend" style="margin-top:6px">${series.map((se, k) => `<span><i style="background:${se.color || SER[k % 3]}"></i>${esc(se.name)}</span>`).join("")}</div>` : ""}`;
    el.querySelectorAll(".hit").forEach(r => {
      const i = +r.dataset.i;
      r.addEventListener("mousemove", ev => tip(`<b>${esc((o.tipLabels || labels)[i])}</b>` + series.map(se => `${esc(se.name)}: <b style="display:inline">${fmtv(se.values[i], o.fmt || "int")}</b>`).join("<br>"), ev));
      r.addEventListener("mouseleave", () => tip(null));
      if (o.onClick) r.addEventListener("click", () => { tip(null); o.onClick(i); });
    });
  }

  /* ---------------- score ring ---------------- */
  function ring(score, size = 76, band = "none", label = "") {
    const r = size / 2 - 6, C = 2 * Math.PI * r, v = score == null ? 0 : Math.max(0, Math.min(10, score)) / 10;
    const col = `var(--${band === "none" ? "none" : band})`;
    const id = "r" + Math.random().toString(36).slice(2, 8);
    setTimeout(() => { const e = document.getElementById(id); if (e) e.style.strokeDashoffset = C * (1 - v); }, 60);
    return `<div class="ring" style="width:${size}px;height:${size}px"><svg width="${size}" height="${size}"><circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="var(--line-2)" stroke-width="7"/><circle id="${id}" class="arc" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${col}" stroke-width="7" stroke-linecap="round" stroke-dasharray="${C}" stroke-dashoffset="${C}"/></svg><div class="rv" style="font-size:${size / 3.4}px">${score == null ? "—" : score.toFixed(1)}${label ? `<small>${esc(label)}</small>` : ""}</div></div>`;
  }

  window.Charts = { line, hbar, columns, ring, tip, fmtv, esc };
})();
