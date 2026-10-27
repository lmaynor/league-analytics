/* Race for Last: who is on pace for the bottom, with a weekly trail of each team's chance */
const ordinal = (n) => `${n}${["th", "st", "nd", "rd"][(n % 100 >> 3) ^ 1 && n % 10 < 4 ? n % 10 : 0]}`;

function spark(trail) {
  const w = 84, h = 24, top = Math.max(0.15, ...trail);
  const pts = trail.map((p, i) => [trail.length < 2 ? w / 2 : (i / (trail.length - 1)) * (w - 6) + 3, h - 3 - (p / top) * (h - 6)]);
  const last = pts[pts.length - 1];
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="Chance of last, week by week">
    <polyline points="${pts.map((p) => p.map((v) => v.toFixed(1)).join(",")).join(" ")}" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="2.6" fill="currentColor"/></svg>`;
}

/* Prediction-market style chart: one line per team for its chance of finishing last, week by week.
   Colors are stable per team (ordered by id) so they match between the legend and the lines. */
const lbl = (l) => (l === 0 ? "Start" : l === "live" ? "Live" : `Wk ${l}`);

function drawMarket(d) {
  const box = $("#market");
  if (!box) return;
  const ids = d.teams.map((t) => t.id).sort((a, b) => a - b);
  const color = (t) => `var(--m${ids.indexOf(t.id) % 10})`;
  const n = d.trail_labels.length, focus = S.raceFocus, T = d.teams.length;
  const mode = S.raceMode || "last";
  const series = (t) => (mode === "last" ? t.trail : t.expect);  // odds of last, or expected finish (1 = best)
  const top = Math.max(0.1, ...d.teams.flatMap(series));
  const step = top > 0.6 ? 0.25 : top > 0.3 ? 0.1 : 0.05;
  const max = Math.min(1, Math.ceil(top / step) * step);
  const val = (t, i) => (mode === "last" ? `${Math.round(t.trail[i] * 100)}%` : t.expect[i].toFixed(1));
  const legend = d.teams.map((t) => {
    const cur = series(t)[n - 1], prev = n > 1 ? series(t)[n - 2] : cur;
    const dl = mode === "last" ? Math.round((cur - prev) * 100) : Math.round((prev - cur) * 10) / 10;  // finish: positive = moved up
    const txt = mode === "last" ? (cur >= 0.995 ? "100%" : cur < 0.005 ? "0%" : `${Math.round(cur * 100)}%`) : cur.toFixed(1);
    return `<button class="mk-row${focus === t.id ? " on" : ""}${focus != null && focus !== t.id ? " dim" : ""}" data-id="${t.id}" aria-pressed="${focus === t.id}">
      <i style="background:${color(t)}"></i><span class="mk-name" title="${esc(t.name)}">${esc(t.owner)}</span>
      <b>${txt}</b><em>${dl === 0 ? "" : dl > 0 ? `+${dl}` : `−${Math.abs(dl)}`}</em></button>`;
  }).join("");
  const toggle = `<div class="seg mk-mode"><button class="${mode === "last" ? "on" : ""}" data-mode="last">Chance of Last</button><button class="${mode === "finish" ? "on" : ""}" data-mode="finish">Final Position</button></div>`;
  box.innerHTML = `${toggle}<div class="mk-plot"><svg id="mk-svg"></svg><div class="mk-tip" id="mk-tip"></div></div><div class="mk-legend">${legend}</div>`;
  box.querySelectorAll(".mk-mode button").forEach((b) => (b.onclick = () => {
    S.raceMode = b.dataset.mode;
    const h = document.querySelector(".mk-title");
    if (h) h.textContent = S.raceMode === "finish" ? "Expected Final Position" : "Odds of Finishing Last";
    drawMarket(d);
  }));
  const plot = box.querySelector(".mk-plot"), svg = box.querySelector("#mk-svg");
  const W = Math.max(260, plot.clientWidth), H = 250, L = 34, R = 10, T0 = 10, B = 26;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("width", W); svg.setAttribute("height", H);
  const x = (i) => L + (n < 2 ? (W - L - R) / 2 : (i / (n - 1)) * (W - L - R));
  const y = (p) => (mode === "last" ? T0 + (1 - p / max) * (H - T0 - B) : T0 + ((p - 1) / Math.max(1, T - 1)) * (H - T0 - B));  // finish mode: 1st at the top
  let g = "";
  if (mode === "last") for (let v = 0; v <= max + 1e-9; v += step) g += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" class="mk-grid"/><text x="${L - 6}" y="${y(v) + 4}" class="mk-ax" text-anchor="end">${Math.round(v * 100)}%</text>`;
  else for (let k = 1; k <= T; k++) g += `<line x1="${L}" x2="${W - R}" y1="${y(k)}" y2="${y(k)}" class="mk-grid"/><text x="${L - 6}" y="${y(k) + 4}" class="mk-ax" text-anchor="end">${k}</text>`;
  const every = Math.ceil(n / Math.max(2, Math.floor((W - L) / 46)));
  const shown = d.trail_labels.map((_, i) => i).filter((i) => i % every === 0);
  if (shown[shown.length - 1] !== n - 1) {  // always label the latest point; drop a neighbor that would collide with it
    if (n - 1 - shown[shown.length - 1] < every * 0.7) shown.pop();
    shown.push(n - 1);
  }
  shown.forEach((i) => { g += `<text x="${x(i)}" y="${H - 8}" class="mk-ax" text-anchor="${i === 0 ? "start" : i === n - 1 ? "end" : "middle"}">${lbl(d.trail_labels[i])}</text>`; });
  const order = [...d.teams].sort((a, b) => (focus === a.id) - (focus === b.id));
  g += order.map((t) => {
    const pts = series(t).map((p, i) => `${x(i).toFixed(1)},${y(p).toFixed(1)}`).join(" ");
    const dim = focus != null && focus !== t.id, w = focus === t.id ? 3 : 1.8;
    return `<g style="opacity:${dim ? 0.18 : 1}"><polyline points="${pts}" fill="none" stroke="${color(t)}" stroke-width="${w}" stroke-linejoin="round" stroke-linecap="round"/>
      <circle cx="${x(n - 1).toFixed(1)}" cy="${y(series(t)[n - 1]).toFixed(1)}" r="${focus === t.id ? 4.5 : 3.2}" fill="${color(t)}"/></g>`;
  }).join("");
  g += `<line id="mk-x" y1="${T0}" y2="${H - B}" class="mk-cross" style="display:none"/>`;
  svg.innerHTML = g;
  const tip = box.querySelector("#mk-tip"), cross = svg.querySelector("#mk-x");
  const show = (ev) => {
    const r = svg.getBoundingClientRect();
    const i = Math.max(0, Math.min(n - 1, Math.round(((ev.clientX - r.left - L) / (W - L - R)) * (n - 1))));
    cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.style.display = "";
    const rows = [...d.teams].sort((a, b) => (mode === "last" ? b.trail[i] - a.trail[i] : a.expect[i] - b.expect[i])).slice(0, 5)
      .map((t) => `<div><i style="background:${color(t)}"></i>${esc(t.owner)}<b>${val(t, i)}</b></div>`).join("");
    tip.innerHTML = `<strong>${lbl(d.trail_labels[i])}</strong>${rows}`;
    tip.style.display = "block";
    const tw = tip.offsetWidth, px = x(i);
    tip.style.left = `${Math.max(4, Math.min(W - tw - 4, px + 12 > W - tw ? px - tw - 12 : px + 12))}px`;
  };
  const hide = () => { cross.style.display = "none"; tip.style.display = "none"; };
  svg.addEventListener("pointermove", show); svg.addEventListener("pointerdown", show);
  svg.addEventListener("pointerleave", hide); svg.addEventListener("pointercancel", hide);
  box.querySelectorAll(".mk-row").forEach((b) => (b.onclick = () => { S.raceFocus = S.raceFocus === +b.dataset.id ? null : +b.dataset.id; drawMarket(d); }));
}
let marketResize;
addEventListener("resize", () => { clearTimeout(marketResize); marketResize = setTimeout(() => { const d = S.race?.seasons?.[S.season]; if (S.tab === "standings" && $("#market") && d) drawMarket(d); }, 150); });

function race() {
  const d = S.race?.seasons?.[S.season];
  if (!d) { panel().innerHTML = `<h1>${S.season} Race for Last</h1><div class="sub">The race covers the current season and the one before it.</div>`; return; }
  const pctTxt = (p) => (p >= 0.995 ? "100%" : p < 0.005 ? "0%" : p < 0.1 ? `${(p * 100).toFixed(1)}%` : `${Math.round(p * 100)}%`);
  const rec = (r) => `${r[0]}-${r[1]}${r[2] ? `-${r[2]}` : ""}`;
  const finish = (t) => (t.rank_p10 === t.rank_p90 ? ordinal(t.rank_med) : `${ordinal(t.rank_p10)} to ${ordinal(t.rank_p90)}`);
  panel().innerHTML = `<h1>${d.season} Race for Last</h1>
    <h2 class="mk-title">${S.raceMode === "finish" ? "Expected Final Position" : "Odds of Finishing Last"}</h2>
    <div class="sub">${d.complete ? "Final standings. Lines show how each team's odds moved week by week." : `The rest of the regular season, simulated 10,000 times from each team's category strength and the real schedule. ${d.live ? "This week's matchups use the live odds. " : ""}Final Position shows each team's expected finish, 1st at the top.`}</div>
    <div class="card market" id="market" style="margin-top:12px"></div>
    <div class="card tbl-wrap" style="margin-top:12px"><table class="sortable">
      <tr><th class="l">Team</th><th class="hide-sm">Record</th><th class="hide-sm">Left</th><th class="hide-sm">Proj. Wins</th><th class="l">Chance of Last</th><th class="hide-sm">Bottom 3</th><th class="hide-sm">Likely Finish</th><th>Trail</th></tr>
      ${d.teams.map((t) => `<tr><td class="l"><b>${esc(t.name)}</b><span class="sub">${esc(t.owner)}<span class="show-sm"> · ${rec(t.record)}</span></span></td>
        <td class="hide-sm" data-v="${t.record[0]}">${rec(t.record)}</td><td class="hide-sm">${t.games_left}</td><td class="hide-sm">${t.proj_wins.toFixed(1)}</td>
        <td class="l" data-v="${t.p_last}"><div class="rbar"><i style="width:${Math.max(t.p_last * 100, t.p_last > 0 ? 2 : 0)}%"></i><span>${pctTxt(t.p_last)}</span></div></td>
        <td class="hide-sm" data-v="${t.p_bottom3}">${pctTxt(t.p_bottom3)}</td><td class="hide-sm" data-v="${t.rank_med}">${finish(t)}</td><td class="trail" data-v="${t.trail[t.trail.length - 1]}">${spark(t.trail)}</td></tr>`).join("")}
    </table></div>
    <div class="sub" style="margin-top:6px">Trail: chance of last at the start of the season and after each week. Likely Finish is the range most simulations land in.</div>`;
  S.raceFocus = null;
  drawMarket(d);
}
