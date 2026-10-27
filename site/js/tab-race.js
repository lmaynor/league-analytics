/* Season Projections & Prediction Markets */
const ordinal = (n) => `${n}${["th", "st", "nd", "rd"][(n % 100 >> 3) ^ 1 && n % 10 < 4 ? n % 10 : 0]}`;
const pctTxt = (p) => (p == null ? "–" : p >= 0.995 ? "100%" : p < 0.005 ? (p > 0 ? "<1%" : "0%") : p < 0.1 ? `${(p * 100).toFixed(1)}%` : `${Math.round(p * 100)}%`);
const recTxt = (r) => `${r[0]}-${r[1]}${r[2] ? `-${r[2]}` : ""}`;
const lbl = (l) => (l === 0 ? "Start" : l === "live" || (typeof l === "string" && l[0] === "d") ? "Live" : `Wk ${l}`);

function spark(trail, isOrdinal = false) {
  if (!trail || !trail.length) return "";
  const w = 84, h = 24;
  if (isOrdinal) {
    const pts = trail.map((p, i) => [
      trail.length < 2 ? w / 2 : (i / (trail.length - 1)) * (w - 6) + 3,
      3 + ((Math.max(1, Math.min(10, p)) - 1) / 9) * (h - 6),
    ]);
    const last = pts[pts.length - 1];
    return `<svg class="spark" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="Position trail">
      <polyline points="${pts.map((p) => p.map((v) => v.toFixed(1)).join(",")).join(" ")}" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
      <circle cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="2.6" fill="currentColor"/></svg>`;
  }
  const top = Math.max(0.15, ...trail);
  const pts = trail.map((p, i) => [
    trail.length < 2 ? w / 2 : (i / (trail.length - 1)) * (w - 6) + 3,
    h - 3 - (p / top) * (h - 6),
  ]);
  const last = pts[pts.length - 1];
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="Probability trail">
    <polyline points="${pts.map((p) => p.map((v) => v.toFixed(1)).join(",")).join(" ")}" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="2.6" fill="currentColor"/></svg>`;
}

const MARKETS = {
  title: {
    key: "title",
    label: "Title Odds",
    title: "Championship Odds",
    desc: "Market-implied probability of finishing 1st (regular season champion / #1 seed).",
    series: (t) => t.trail_title || (t.finish ? [t.finish[0]] : [t.p_title || 0]),
    current: (t) => t.p_title ?? (t.finish ? t.finish[0] : 0),
    sort: (a, b) => (b.p_title ?? 0) - (a.p_title ?? 0) || b.proj_wins - a.proj_wins,
    format: pctTxt,
    isOrdinal: false,
  },
  playoffs: {
    key: "playoffs",
    label: "Playoffs (Top 4)",
    title: "Playoff Odds (Top 4)",
    desc: "Simulated probability of clinching a top-4 playoff berth. 50% is the bubble cutoff.",
    series: (t) => t.trail_playoffs || (t.finish ? [t.finish.slice(0, 4).reduce((a, b) => a + b, 0)] : [t.p_playoffs || 0]),
    current: (t) => t.p_playoffs ?? (t.finish ? t.finish.slice(0, 4).reduce((a, b) => a + b, 0) : 0),
    sort: (a, b) => (b.p_playoffs ?? 0) - (a.p_playoffs ?? 0) || b.proj_wins - a.proj_wins,
    format: pctTxt,
    isOrdinal: false,
  },
  last: {
    key: "last",
    label: "Chance of Last",
    title: "Odds of Finishing Last",
    desc: "Simulated likelihood of landing in 10th place (Sacko / Last Place punishment spot).",
    series: (t) => t.trail_last || t.trail || [t.p_last || 0],
    current: (t) => t.p_last ?? 0,
    sort: (a, b) => (b.p_last ?? 0) - (a.p_last ?? 0) || a.proj_wins - b.proj_wins,
    format: pctTxt,
    isOrdinal: false,
  },
  finish: {
    key: "finish",
    label: "Final Position",
    title: "Projected Final Position",
    desc: "Projected finish position ladder (1st through 10th place), 1st at the top.",
    series: (t) => t.expect,
    current: (t) => t.expect[t.expect.length - 1],
    sort: (a, b) => a.expect[a.expect.length - 1] - b.expect[b.expect.length - 1],
    format: (v) => ordinal(v),
    isOrdinal: true,
  },
};

function drawMarket(d) {
  const box = $("#market");
  if (!box) return;
  const mode = S.raceMode && MARKETS[S.raceMode] ? S.raceMode : "title";
  const mkt = MARKETS[mode];
  const ids = d.teams.map((t) => t.id).sort((a, b) => a - b);
  const color = (t) => `var(--m${ids.indexOf(t.id) % 10})`;
  const n = d.trail_labels.length, focus = S.raceFocus, T = d.teams.length;

  const modeButtons = Object.values(MARKETS).map((m) =>
    `<button class="${m.key === mode ? "on" : ""}" data-mode="${m.key}">${esc(m.label)}</button>`
  ).join("");

  const legendTeams = [...d.teams].sort(mkt.sort);
  const legend = legendTeams.map((t) => {
    const s = mkt.series(t);
    const cur = s[n - 1] ?? mkt.current(t);
    const prev = n > 1 ? s[n - 2] : cur;
    const dl = mkt.isOrdinal ? prev - cur : Math.round((cur - prev) * 100);
    const dlTxt = dl === 0 ? "" : dl > 0 ? `+${dl}${mkt.isOrdinal ? "" : "%"}` : `−${Math.abs(dl)}${mkt.isOrdinal ? "" : "%"}`;
    return `<button class="mk-row${focus === t.id ? " on" : ""}${focus != null && focus !== t.id ? " dim" : ""}" data-id="${t.id}" aria-pressed="${focus === t.id}">
      <i style="background:${color(t)}"></i><span class="mk-name" title="${esc(t.name)}">${esc(t.owner)}</span>
      <b>${mkt.format(cur)}</b><em>${dlTxt}</em></button>`;
  }).join("");

  box.innerHTML = `
    <div class="mk-top">
      <div class="mk-info">
        <h2 class="mk-title">${esc(mkt.title)}</h2>
        <div class="mk-desc">${esc(mkt.desc)}</div>
      </div>
      <div class="seg mk-mode" role="tablist">${modeButtons}</div>
    </div>
    <div class="mk-body">
      <div class="mk-plot">
        <svg id="mk-svg"></svg>
        <div class="mk-tip" id="mk-tip"></div>
      </div>
      <div class="mk-legend">${legend}</div>
    </div>`;

  box.querySelectorAll(".mk-mode button").forEach((b) => {
    b.onclick = () => {
      S.raceMode = b.dataset.mode;
      drawMarket(d);
      updateRaceTable(d);
    };
  });

  box.querySelectorAll(".mk-row").forEach((b) => {
    b.onclick = () => {
      S.raceFocus = S.raceFocus === +b.dataset.id ? null : +b.dataset.id;
      drawMarket(d);
    };
  });

  const plot = box.querySelector(".mk-plot"), svg = box.querySelector("#mk-svg");
  if (!plot || !svg) return;
  const W = Math.max(260, plot.clientWidth || (box.clientWidth ? box.clientWidth - 32 : 360));
  const H = 270, L = 42, R = 26, T0 = 12, B = 28;
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);

  const series = (t) => mkt.series(t);
  const top = Math.max(0.12, ...d.teams.flatMap((t) => series(t)));
  const step = top > 0.6 ? 0.25 : top > 0.3 ? 0.1 : 0.05;
  const max = Math.min(1, Math.ceil(top / step) * step);

  const x = (i) => L + (n < 2 ? (W - L - R) / 2 : (i / (n - 1)) * (W - L - R));
  const y = (p) => (!mkt.isOrdinal
    ? T0 + (1 - Math.max(0, p) / max) * (H - T0 - B)
    : T0 + ((p - 1) / Math.max(1, T - 1)) * (H - T0 - B));

  let g = "";
  if (!mkt.isOrdinal) {
    for (let v = 0; v <= max + 1e-9; v += step) {
      g += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" class="mk-grid"/><text x="${L - 6}" y="${y(v) + 4}" class="mk-ax" text-anchor="end">${Math.round(v * 100)}%</text>`;
    }
    if (mode === "playoffs" && max >= 0.5) {
      g += `<line x1="${L}" x2="${W - R}" y1="${y(0.5)}" y2="${y(0.5)}" class="mk-cutoff"/><text x="${W - R}" y="${y(0.5) - 4}" class="mk-cutoff-text" text-anchor="end">50% Bubble Cutoff</text>`;
    }
  } else {
    for (let k = 1; k <= T; k++) {
      g += `<line x1="${L}" x2="${W - R}" y1="${y(k)}" y2="${y(k)}" class="mk-grid"/><text x="${L - 6}" y="${y(k) + 4}" class="mk-ax" text-anchor="end">${k}</text>`;
    }
  }

  const every = Math.ceil(n / Math.max(2, Math.floor((W - L - R) / 50)));
  const shown = [];
  for (let i = 0; i < n; i += every) shown.push(i);
  if (shown[shown.length - 1] !== n - 1) {
    if (n - 1 - shown[shown.length - 1] < every * 0.7 && shown.length > 1) {
      shown[shown.length - 1] = n - 1;
    } else {
      shown.push(n - 1);
    }
  }
  shown.forEach((i) => {
    g += `<line x1="${x(i).toFixed(1)}" x2="${x(i).toFixed(1)}" y1="${H - B}" y2="${H - B + 4}" class="mk-grid"/>
      <text x="${x(i).toFixed(1)}" y="${H - 10}" class="mk-ax" text-anchor="middle">${lbl(d.trail_labels[i])}</text>`;
  });

  const order = [...d.teams].sort((a, b) => (focus === a.id) - (focus === b.id));
  g += order.map((t) => {
    const s = series(t);
    const pts = s.map((p, i) => `${x(i).toFixed(1)},${y(p).toFixed(1)}`).join(" ");
    const dim = focus != null && focus !== t.id, w = focus === t.id ? 3.2 : 1.8;
    const lastY = y(s[n - 1] ?? 0);
    return `<g style="opacity:${dim ? 0.16 : 1}"><polyline points="${pts}" fill="none" stroke="${color(t)}" stroke-width="${w}" stroke-linejoin="round" stroke-linecap="round"/>
      <circle cx="${x(n - 1).toFixed(1)}" cy="${lastY.toFixed(1)}" r="${focus === t.id ? 4.5 : 3.2}" fill="${color(t)}"/></g>`;
  }).join("");

  g += `<line id="mk-x" y1="${T0}" y2="${H - B}" class="mk-cross" style="display:none"/>`;
  svg.innerHTML = g;

  const tip = box.querySelector("#mk-tip"), cross = svg.querySelector("#mk-x");
  const show = (ev) => {
    const r = svg.getBoundingClientRect();
    const i = Math.max(0, Math.min(n - 1, Math.round(((ev.clientX - r.left - L) / Math.max(1, W - L - R)) * (n - 1))));
    cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.style.display = "";
    const sorted = [...d.teams].sort((a, b) => (!mkt.isOrdinal ? (series(b)[i] ?? 0) - (series(a)[i] ?? 0) : (series(a)[i] ?? 10) - (series(b)[i] ?? 10))).slice(0, 5);
    const rows = sorted.map((t) => `<div><i style="background:${color(t)}"></i>${esc(t.owner)}<b>${mkt.format(series(t)[i])}</b></div>`).join("");
    const tipLabel = (l) => (l === 0 ? "Preseason" : l === "live" || (typeof l === "string" && l[0] === "d") ? `Week ${d.weeks_done + 1 || 2} (Live)` : `Week ${l}`);
    tip.innerHTML = `<strong>${tipLabel(d.trail_labels[i])}</strong>${rows}`;
    tip.style.display = "block";
    const tw = tip.offsetWidth, px = x(i);
    tip.style.left = `${Math.max(4, Math.min(W - tw - 4, px + 12 > W - tw ? px - tw - 12 : px + 12))}px`;
  };
  const hide = () => { cross.style.display = "none"; tip.style.display = "none"; };
  svg.addEventListener("pointermove", show); svg.addEventListener("pointerdown", show);
  svg.addEventListener("pointerleave", hide); svg.addEventListener("pointercancel", hide);
}

function updateRaceTable(d) {
  const wrap = $("#race-table-wrap");
  if (!wrap) return;
  const mode = S.raceMode && MARKETS[S.raceMode] ? S.raceMode : "title";
  const mkt = MARKETS[mode];
  const finish = (t) => (t.rank_p10 === t.rank_p90 ? ordinal(t.rank_med) : `${ordinal(t.rank_p10)} to ${ordinal(t.rank_p90)}`);

  const teams = [...d.teams].sort(mkt.sort);

  wrap.innerHTML = `<table class="sortable">
    <thead>
      <tr>
        <th class="l">Team</th>
        <th class="hide-sm">Record</th>
        <th class="hide-sm">Proj. Wins</th>
        <th class="${mode === "title" ? "mk-col-active" : ""}">Title Odds</th>
        <th class="${mode === "playoffs" ? "mk-col-active" : ""}">Playoffs</th>
        <th class="${mode === "last" ? "mk-col-active" : ""}">Last Place</th>
        <th class="hide-sm ${mode === "finish" ? "mk-col-active" : ""}">Likely Finish</th>
        <th>Trail</th>
      </tr>
    </thead>
    <tbody>
      ${teams.map((t) => {
        const s = mkt.series(t);
        const cellBar = (p, isActive) => isActive
          ? `<div class="rbar"><i style="width:${Math.max(p * 100, p > 0 ? 2 : 0)}%"></i><span>${pctTxt(p)}</span></div>`
          : pctTxt(p);
        return `<tr>
          <td class="l"><b>${esc(t.name)}</b><span class="sub">${esc(t.owner)}<span class="show-sm"> · ${recTxt(t.record)}</span></span></td>
          <td class="hide-sm" data-v="${t.record[0]}">${recTxt(t.record)}</td>
          <td class="hide-sm" data-v="${t.proj_wins}">${t.proj_wins.toFixed(1)}</td>
          <td data-v="${t.p_title ?? 0}" class="${mode === "title" ? "mk-col-active" : ""}">${cellBar(t.p_title ?? 0, mode === "title")}</td>
          <td data-v="${t.p_playoffs ?? 0}" class="${mode === "playoffs" ? "mk-col-active" : ""}">${cellBar(t.p_playoffs ?? 0, mode === "playoffs")}</td>
          <td data-v="${t.p_last ?? 0}" class="${mode === "last" ? "mk-col-active" : ""}">${cellBar(t.p_last ?? 0, mode === "last")}</td>
          <td class="hide-sm ${mode === "finish" ? "mk-col-active" : ""}" data-v="${t.rank_med}">${finish(t)}</td>
          <td class="trail" data-v="${s[s.length - 1] ?? 0}">${spark(s, mkt.isOrdinal)}</td>
        </tr>`;
      }).join("")}
    </tbody>
  </table>`;

  markSortable(wrap);
}

let marketResize;
addEventListener("resize", () => {
  clearTimeout(marketResize);
  marketResize = setTimeout(() => {
    const d = S.race?.seasons?.[S.season];
    if ((S.tab === "season" || S.tab === "standings") && $("#market") && d) {
      drawMarket(d);
    }
  }, 120);
});

function race() {
  const d = S.race?.seasons?.[S.season];
  if (!d) {
    panel().innerHTML = `<h1>${S.season} Projections</h1><div class="sub">Projections cover the current season and recent historical seasons.</div>`;
    return;
  }
  if (!S.raceMode) S.raceMode = "title";

  // Identify market leaders and the 50% playoff bubble cutoff team
  const titleFav = [...d.teams].sort((a, b) => (b.p_title ?? 0) - (a.p_title ?? 0))[0] || d.teams[0];
  const lastFav = [...d.teams].sort((a, b) => (b.p_last ?? 0) - (a.p_last ?? 0))[0] || d.teams[0];
  const topSeedFav = [...d.teams].sort((a, b) => b.proj_wins - a.proj_wins)[0] || d.teams[0];
  const bubbleTeam = [...d.teams].sort((a, b) => Math.abs((a.p_playoffs ?? 0) - 0.5) - Math.abs((b.p_playoffs ?? 0) - 0.5))[0] || d.teams[0];

  panel().innerHTML = `
    <h1>${d.season} Season Projections</h1>
    <div class="sub">${d.complete ? "Final season outcome. Line trails track each team's probability progression week by week." : `Regular season simulated 10,000 times based on category strengths and remaining schedule. ${d.live ? "Current week reflects live matchup win probabilities." : ""}`}</div>

    <div class="mk-summary-grid">
      <div class="mk-stat-card">
        <div class="mk-stat-label">Title Favorite</div>
        <div class="mk-stat-val"><span>${esc(titleFav.owner)}</span> <b>${pctTxt(titleFav.p_title)}</b></div>
        <div class="mk-stat-sub">${esc(titleFav.name)}</div>
      </div>
      <div class="mk-stat-card">
        <div class="mk-stat-label">Playoff Bubble</div>
        <div class="mk-stat-val"><span>${esc(bubbleTeam.owner)}</span> <b>${pctTxt(bubbleTeam.p_playoffs)}</b></div>
        <div class="mk-stat-sub">Rank #${bubbleTeam.rank_med} · 4-team cutoff</div>
      </div>
      <div class="mk-stat-card">
        <div class="mk-stat-label">Last Place Risk</div>
        <div class="mk-stat-val"><span>${esc(lastFav.owner)}</span> <b>${pctTxt(lastFav.p_last)}</b></div>
        <div class="mk-stat-sub">${esc(lastFav.name)}</div>
      </div>
      <div class="mk-stat-card">
        <div class="mk-stat-label">Projected Top Seed</div>
        <div class="mk-stat-val"><span>${esc(topSeedFav.owner)}</span> <b>${topSeedFav.proj_wins.toFixed(1)} W</b></div>
        <div class="mk-stat-sub">${recTxt(topSeedFav.record)} actual record</div>
      </div>
    </div>

    <div class="card market" id="market" style="margin-top:14px"></div>

    <div class="card tbl-wrap" id="race-table-wrap" style="margin-top:14px"></div>
    <div class="sub" style="margin-top:8px">Trail sparklines track movement over time for the active prediction market above. Click any column header to sort.</div>
  `;

  S.raceFocus = null;
  drawMarket(d);
  updateRaceTable(d);
}
