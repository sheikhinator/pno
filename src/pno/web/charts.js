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

  function tickFmt(ticks, fmt) {
    const step = ticks.length > 1 ? Math.abs(ticks[1] - ticks[0]) : 1;
    if (fmt === "money" || step >= 1) return t => fmtv(t, fmt === "money" ? "money" : fmt === "score" || fmt === "pct" ? (step >= 1 ? "int" : fmt) : fmt);
    const dec = Math.min(3, Math.max(1, Math.ceil(-Math.log10(step))));
    return t => t.toFixed(dec) + (fmt === "pct" ? "%" : "");
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
    const y0 = ticks[0], y1 = ticks[ticks.length - 1], tf = tickFmt(ticks, o.fmt === "money" ? "money" : o.axisFmt || o.fmt);
    const x = i => P.l + (labels.length === 1 ? (W - P.l - P.r) / 2 : i * (W - P.l - P.r) / (labels.length - 1));
    const y = v => P.t + (H - P.t - P.b) * (1 - (v - y0) / (y1 - y0));
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.title || "line chart")}">`;
    ticks.forEach(t => s += `<line class="grid-l" x1="${P.l}" x2="${W - P.r}" y1="${y(t)}" y2="${y(t)}"/><text class="ax" x="${P.l - 8}" y="${y(t) + 4}" text-anchor="end">${tf(t)}</text>`);
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
    const min = Math.min(0, ...vals.filter(v => v != null));             // negative values (e.g. NPS) draw left of zero
    const span = Math.max(1e-9, max - min), x0 = P.l + (W - P.l - P.r) * (-min) / span;
    const xw = v => Math.max(0, (W - P.l - P.r) * Math.abs(v || 0) / span);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.title || "bar chart")}">`;
    if (min < 0) s += `<line class="ref-l" x1="${x0}" x2="${x0}" y1="0" y2="${H}"/>`;
    if (o.ref != null && o.ref <= max) s += `<line class="ref-l" x1="${x0 + xw(o.ref)}" x2="${x0 + xw(o.ref)}" y1="0" y2="${H}"/>`;
    labels.forEach((l, i) => {
      const yy = P.t + i * row, v = vals[i], bh = Math.min(18, row - 10), w = xw(v), neg = v != null && v < 0;
      const c = (o.colors && o.colors[i]) || o.color || SER[0];
      s += `<rect class="hit" data-i="${i}" x="0" y="${yy}" width="${W}" height="${row}" rx="6"/>`;
      s += `<text class="ax-lbl" x="${P.l - 10}" y="${yy + row / 2 + 4}" text-anchor="end">${esc(String(l).length > 28 ? String(l).slice(0, 27) + "…" : l)}</text>`;
      if (v != null && w > 0) {
        const xs = neg ? x0 - w : x0;
        s += `<rect class="grow" style="transform-origin:${x0}px 0;animation-delay:${i * 25}ms" x="${xs}" y="${yy + (row - bh) / 2}" width="${w}" height="${bh}" rx="${Math.min(4, w / 2)}" fill="${c}" pointer-events="none"/>`;
      }
      s += neg ? `<text class="val" x="${x0 - w - 7}" y="${yy + row / 2 + 4}" text-anchor="end" pointer-events="none">${fmtv(v, o.fmt)}</text>`
        : `<text class="val" x="${x0 + w + 7}" y="${yy + row / 2 + 4}" pointer-events="none">${fmtv(v, o.fmt)}</text>`;
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

  /* ---------------- donut (shares) ---------------- */
  const PAL = ["#B8860B", "#94481A", "#2E7D4F", "#3B6EA8", "#D9822B", "#7A5C9E", "#5B9A63", "#B3261E", "#8C7B6B", "#2A9D8F"];
  function donut(el, o) {
    const labels = o.labels || [], vals = (o.values || []).map(v => Math.max(0, +v || 0));
    const tot = vals.reduce((a, b) => a + b, 0);
    if (!labels.length || !tot) { el.innerHTML = `<div class="empty" style="padding:30px">No data yet</div>`; return; }
    const S = o.size || 190, R = S / 2 - 8, r = R * 0.62, cx = S / 2, cy = S / 2;
    let a0 = -Math.PI / 2, paths = "";
    vals.forEach((v, i) => {
      const a1 = a0 + 2 * Math.PI * v / tot, big = a1 - a0 > Math.PI ? 1 : 0, c = (o.colors && o.colors[i]) || PAL[i % PAL.length];
      const p = (ang, rad) => `${cx + rad * Math.cos(ang)} ${cy + rad * Math.sin(ang)}`;
      if (v / tot > 0.9999) paths += `<circle cx="${cx}" cy="${cy}" r="${(R + r) / 2}" fill="none" stroke="${c}" stroke-width="${R - r}"/>`;
      else paths += `<path class="hit-d" data-i="${i}" d="M${p(a0, R)} A${R} ${R} 0 ${big} 1 ${p(a1, R)} L${p(a1, r)} A${r} ${r} 0 ${big} 0 ${p(a0, r)}Z" fill="${c}"/>`;
      a0 = a1;
    });
    const legend = labels.map((l, i) => `<div class="dl"><i style="background:${(o.colors && o.colors[i]) || PAL[i % PAL.length]}"></i><span>${esc(l)}</span><b>${fmtv(vals[i], o.fmt)}</b><small>${(100 * vals[i] / tot).toFixed(0)}%</small></div>`).join("");
    el.innerHTML = `<div class="donut"><svg viewBox="0 0 ${S} ${S}" width="${S}" height="${S}">${paths}<text x="${cx}" y="${cy - 2}" text-anchor="middle" class="dv">${fmtv(tot, o.fmt)}</text><text x="${cx}" y="${cy + 16}" text-anchor="middle" class="dlab">${esc(o.center || "total")}</text></svg><div class="dlegend">${legend}</div></div>`;
    el.querySelectorAll(".hit-d").forEach(pth => { const i = +pth.dataset.i; pth.addEventListener("mousemove", ev => tip(`<b>${esc(labels[i])}</b>${fmtv(vals[i], o.fmt)} · ${(100 * vals[i] / tot).toFixed(1)}%`, ev)); pth.addEventListener("mouseleave", () => tip(null)); });
  }


  /* ---------------- waterfall: start → contributions → end (e.g. budget → actual by store) ---------------- */
  function waterfall(el, o) {
    const labels = o.labels || [], vals = o.values || [];
    if (!labels.length) { el.innerHTML = `<div class="empty" style="padding:30px">No data yet</div>`; return; }
    const W = o.width || Math.max(360, el.clientWidth || 640), H = o.height || 260, P = { l: 52, r: 12, t: 20, b: 46 };
    const steps = [{ label: o.startLabel || "Start", v: o.start || 0, kind: "total" }];
    let run = o.start || 0;
    labels.forEach((l, i) => { steps.push({ label: l, v: vals[i] || 0, from: run, kind: (vals[i] || 0) >= 0 ? "up" : "down" }); run += vals[i] || 0; });
    steps.push({ label: o.endLabel || "End", v: run, kind: "total" });
    const tops = steps.map(s => s.kind === "total" ? s.v : Math.max(s.from, s.from + s.v)), bots = steps.map(s => s.kind === "total" ? 0 : Math.min(s.from, s.from + s.v));
    const lo = o.floor != null ? o.floor : Math.min(0, ...bots), top = Math.max(...tops), hi = o.floor != null ? top + (top - lo) * 0.16 : top * 1.04;
    const ticks = nice(hi, lo);
    const y = v => P.t + (H - P.t - P.b) * (1 - (v - ticks[0]) / (ticks[ticks.length - 1] - ticks[0]));
    const bw = Math.min(46, (W - P.l - P.r) / steps.length * 0.62), gx = i => P.l + (i + 0.5) * (W - P.l - P.r) / steps.length;
    let svg = `<svg viewBox="0 0 ${W} ${H}" role="img">`;
    const tf = tickFmt(ticks, o.fmt);
    ticks.forEach(t => { svg += `<line class="grid" x1="${P.l}" x2="${W - P.r}" y1="${y(t)}" y2="${y(t)}"/><text class="ax" x="${P.l - 8}" y="${y(t) + 4}" text-anchor="end">${tf(t)}</text>`; });
    steps.forEach((st, i) => {
      const top = st.kind === "total" ? st.v : Math.max(st.from, st.from + st.v), bot = st.kind === "total" ? ticks[0] : Math.min(st.from, st.from + st.v);
      if (st.kind !== "total" && Math.abs(st.v) < 1e-9) return;
      const c = st.kind === "total" ? "var(--s1)" : st.kind === "up" ? "var(--good)" : "var(--bad)";
      const x = gx(i) - bw / 2, h = Math.max(1.5, y(bot) - y(top));
      svg += `<rect class="hit" data-i="${i}" x="${gx(i) - bw}" y="${P.t}" width="${bw * 2}" height="${H - P.t - P.b}"/>`;
      svg += `<rect class="growy" style="animation-delay:${i * 45}ms;transform-origin:0 ${y(bot)}px" x="${x}" y="${y(top)}" width="${bw}" height="${h}" rx="3" fill="${c}" pointer-events="none"/>`;
      if (i < steps.length - 1) { const nxt = st.kind === "total" ? st.v : st.from + st.v; svg += `<line class="ref-l" x1="${x + bw}" x2="${gx(i + 1) - bw / 2}" y1="${y(nxt)}" y2="${y(nxt)}"/>`; }
      svg += `<text class="val" x="${gx(i)}" y="${y(top) - 6}" text-anchor="middle" pointer-events="none">${st.kind === "total" ? fmtv(st.v, o.fmt) : (st.v >= 0 ? "+" : "") + fmtv(st.v, o.fmt)}</text>`;
      const lab = String(st.label), room = Math.max(6, Math.floor((W - P.l - P.r) / steps.length / 6.2));
      svg += `<text class="ax-lbl" x="${gx(i)}" y="${H - P.b + 16}" text-anchor="middle">${esc(lab.length > room ? lab.slice(0, room - 1) + "…" : lab)}</text>`;
    });
    svg += `</svg>`;
    el.innerHTML = `<div class="chart">${svg}</div>`;
    el.querySelectorAll(".hit").forEach(r => { const st = steps[+r.dataset.i];
      r.addEventListener("mousemove", ev => tip(`<b>${esc(st.label)}</b>${st.kind === "total" ? fmtv(st.v, o.fmt) : (st.v >= 0 ? "+" : "") + fmtv(st.v, o.fmt)}`, ev)); r.addEventListener("mouseleave", () => tip(null)); });
  }

  /* ---------------- funnel ---------------- */
  function funnel(el, o) {
    const labels = o.labels || [], vals = o.values || [];
    if (!labels.length || !vals[0]) { el.innerHTML = `<div class="empty" style="padding:30px">No data yet</div>`; return; }
    const W = o.width || Math.max(320, el.clientWidth || 560), row = 44, H = row * labels.length + 8, max = vals[0];
    let svg = `<svg viewBox="0 0 ${W} ${H}" role="img">`;
    labels.forEach((l, i) => {
      const w = Math.max(40, (W - 170) * (vals[i] / max)), x = (W - 170 - w) / 2 + 10, yy = i * row + 4;
      const nw = i < labels.length - 1 ? Math.max(40, (W - 170) * (vals[i + 1] / max)) : w * 0.9, nx = (W - 170 - nw) / 2 + 10;
      svg += `<path class="growx" style="animation-delay:${i * 70}ms" d="M${x} ${yy} H${x + w} L${nx + nw} ${yy + row - 6} H${nx} Z" fill="${PAL[i % PAL.length]}" opacity="${1 - i * 0.08}"/>`;
      svg += `<text x="${10 + (W - 170) / 2}" y="${yy + row / 2 + 2}" text-anchor="middle" class="fv">${fmtv(vals[i], o.fmt || "int")}</text>`;
      svg += `<text class="ax-lbl" x="${W - 150}" y="${yy + row / 2 - 2}">${esc(l)}</text>`;
      if (i) svg += `<text class="ax" x="${W - 150}" y="${yy + row / 2 + 13}">${(100 * vals[i] / (vals[i - 1] || 1)).toFixed(0)}% of previous</text>`;
    });
    el.innerHTML = `<div class="chart">${svg}</svg></div>`;
  }

  /* ---------------- treemap (squarified, one level) ---------------- */
  function treemap(el, o) {
    const items = (o.labels || []).map((l, i) => ({ l, v: Math.max(0, o.values[i] || 0), s: (o.subs || [])[i] || "", i })).filter(x => x.v > 0).sort((a, b) => b.v - a.v);
    if (!items.length) { el.innerHTML = `<div class="empty" style="padding:30px">No data yet</div>`; return; }
    const W = o.width || Math.max(320, el.clientWidth || 600), H = o.height || 280, tot = items.reduce((a, b) => a + b.v, 0);
    const rects = [];
    (function lay(list, x, y, w, h) {
      if (!list.length) return;
      if (list.length === 1) { rects.push({ ...list[0], x, y, w, h }); return; }
      const sum = list.reduce((a, b) => a + b.v, 0);
      let acc = 0, k = 0; while (k < list.length - 1 && (acc + list[k].v) / sum <= 0.5) { acc += list[k].v; k++; }
      if (k === 0) { acc = list[0].v; k = 1; }
      const a = list.slice(0, k), b = list.slice(k), f = acc / sum;
      if (w >= h) { lay(a, x, y, w * f, h); lay(b, x + w * f, y, w * (1 - f), h); } else { lay(a, x, y, w, h * f); lay(b, x, y + h * f, w, h * (1 - f)); }
    })(items, 0, 0, W, H);
    let svg = `<svg viewBox="0 0 ${W} ${H}" role="img">`;
    rects.forEach((r, n) => {
      svg += `<g class="tm" data-n="${n}"><rect class="fadein" style="animation-delay:${n * 30}ms" x="${r.x + 1.5}" y="${r.y + 1.5}" width="${Math.max(0, r.w - 3)}" height="${Math.max(0, r.h - 3)}" rx="8" fill="${(o.colors && o.colors[r.i]) || PAL[n % PAL.length]}" opacity="${0.95 - Math.min(0.45, n * 0.035)}"/>`;
      if (r.w > 64 && r.h > 34) svg += `<text x="${r.x + 10}" y="${r.y + 20}" class="tml">${esc(String(r.l).slice(0, Math.floor(r.w / 7.2)))}</text><text x="${r.x + 10}" y="${r.y + 37}" class="tmv">${fmtv(r.v, o.fmt || "int")} · ${(100 * r.v / tot).toFixed(0)}%</text>`;
      svg += `</g>`;
    });
    el.innerHTML = `<div class="chart">${svg}</svg></div>`;
    el.querySelectorAll(".tm").forEach(g => { const r = rects[+g.dataset.n];
      g.addEventListener("mousemove", ev => tip(`<b>${esc(r.l)}</b>${fmtv(r.v, o.fmt || "int")} · ${(100 * r.v / tot).toFixed(1)}%${r.s ? "<br>" + esc(r.s) : ""}`, ev)); g.addEventListener("mouseleave", () => tip(null));
      if (o.onClick) g.addEventListener("click", () => { tip(null); o.onClick(r.i); }); });
  }

  /* ---------------- bullet: value against target with good / ok / poor bands ---------------- */
  function bullet(el, o) {
    const items = o.items || [];
    if (!items.length) { el.innerHTML = `<div class="empty" style="padding:30px">No data yet</div>`; return; }
    const W = o.width || Math.max(320, el.clientWidth || 600), row = 40, L = 150, R = 70, H = row * items.length;
    let svg = `<svg viewBox="0 0 ${W} ${H}" role="img">`;
    items.forEach((it, i) => {
      const max = it.max || Math.max(it.value || 0, it.target || 0) * 1.25 || 1, sx = v => L + (W - L - R) * Math.max(0, Math.min(1, (v || 0) / max)), yy = i * row + 8;
      const good = it.higher === false ? (it.value || 0) <= (it.target || 0) : (it.value || 0) >= (it.target || 0);
      svg += `<text class="ax-lbl" x="${L - 10}" y="${yy + 15}" text-anchor="end">${esc(it.label)}</text>`;
      [[1, "var(--bg-2)"], [0.8, "color-mix(in srgb,var(--bg-2) 60%,var(--line))"], [0.6, "var(--line)"]].forEach(([f, c]) => { svg += `<rect x="${L}" y="${yy}" width="${(W - L - R) * f}" height="22" rx="4" fill="${c}"/>`; });
      svg += `<rect class="grow" style="transform-origin:${L}px 0;animation-delay:${i * 50}ms" x="${L}" y="${yy + 7}" width="${Math.max(2, sx(it.value) - L)}" height="8" rx="3" fill="${good ? "var(--good)" : "var(--bad)"}"/>`;
      if (it.target != null) svg += `<rect x="${sx(it.target) - 1.5}" y="${yy - 2}" width="3" height="26" rx="1.5" fill="var(--ink)"/>`;
      svg += `<text class="val" x="${W - R + 8}" y="${yy + 15}">${fmtv(it.value, it.fmt || o.fmt)}</text>`;
    });
    el.innerHTML = `<div class="chart">${svg}</svg></div>`;
  }

  /* ---------------- sparkline (inline, for tables) ---------------- */
  function spark(vals, o = {}) {
    const v = (vals || []).filter(x => x != null);
    if (v.length < 2) return "";
    const W = o.w || 84, H = o.h || 22, lo = Math.min(...v), hi = Math.max(...v), sp = hi - lo || 1;
    const pts = v.map((x, i) => `${(i * (W - 4) / (v.length - 1) + 2).toFixed(1)},${(H - 3 - (x - lo) / sp * (H - 6)).toFixed(1)}`).join(" ");
    const up = v[v.length - 1] >= v[0];
    const c = o.color || (o.higherBetter === false ? (up ? "var(--bad)" : "var(--good)") : (up ? "var(--good)" : "var(--bad)"));
    const [lx, ly] = pts.split(" ").pop().split(",");
    return `<svg class="spark" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}"><polyline points="${pts}" fill="none" stroke="${c}" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/><circle cx="${lx}" cy="${ly}" r="2.4" fill="${c}"/></svg>`;
  }

  window.Charts = { line, hbar, columns, ring, donut, tip, fmtv, esc, PAL, waterfall, funnel, treemap, bullet, spark };
})();
