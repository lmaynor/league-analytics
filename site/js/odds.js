/* Odds: per-category win probabilities, the biggest-swings strip and tonight's players.
   Shared by the Scoreboard's Full view. */
function oddsHeader(L) {
  const asof = new Date(L.asof_ms).toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" });
  const top = L.sweat.slice(0, 8);
  return `<div class="sub">Odds as of ${asof} · ${L.sims.toLocaleString()} simulations of the rest of the week</div>
    <div class="banner">${L.final_day ? "Final Day of the Week" : `Week ends ${new Date(L.end_date + "T12:00").toLocaleDateString([], { weekday: "long" })}`}
      <small>${L.games_left} lineup player-games left across the league</small></div>
    ${top.length ? `<h2>Biggest Category Swings</h2>
    <div class="sweatlist">${top.map((s, k) => swingChip(s, k)).join("")}</div>` : ""}
    <div class="toolbar"><span class="sub">Sort categories</span>
      <div class="seg"><button class="${S.sort === "sweat" ? "on" : ""}" onclick="setSort('sweat')">Closest first</button><button class="${S.sort === "std" ? "on" : ""}" onclick="setSort('std')">Standard order</button></div></div>`;
}
function swingChip(s, k) {
  const homeFav = s.p_home >= 1 - s.p_home - s.p_tie;
  const label = s.state === "toss-up" ? "Toss-up" : `${pct(homeFav ? s.p_home : 1 - s.p_home - s.p_tie)} ${esc(homeFav ? s.home_name : s.away_name)}`;
  return `<div class="sw" role="button" tabindex="0" onclick="jump(${s.matchup})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();jump(${s.matchup})}">
    <div><span class="rk">${k + 1}</span><b>${s.label}</b> <span class="pill">${label}</span></div>
    <div class="nm">${fmt(s.hv, s.cat)} vs ${fmt(s.av, s.cat)}</div>
    <div class="nm">${esc(s.home_name)}: <b>${s.win_if_home != null ? pct(s.win_if_home) : "–"}</b> if they win it, <b>${s.win_if_away != null ? pct(s.win_if_away) : "–"}</b> if not</div></div>`;
}
window.setSort = (v) => { S.sort = v; scoreboard(); };
window.jump = (i) => goCard(i);
window.toggle = (key) => { S.open.has(key) ? S.open.delete(key) : S.open.add(key); scoreboard(); };

/* Rolling win chance for this matchup, day by day (only shown once its odds are public) */
function rollChart(m) {
  const daily = S.race?.seasons?.[S.meta.current]?.matchup_daily?.[m.home] || [];
  const pts = [...daily, m.p_home_win].filter((v) => v != null);
  if (pts.length < 2 || m.hidden) return "";
  const W = 300, H = 72, P = 8;
  const x = (i) => P + (i / (pts.length - 1)) * (W - 2 * P);
  const y = (p) => P + (1 - p) * (H - 2 * P);
  const path = pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p).toFixed(1)}`).join(" ");
  const last = pts[pts.length - 1];
  return `<div class="roll"><div class="roll-head"><span>${esc(m.home_name)} win chance, day by day</span><b>${pct(last)}</b></div>
    <svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" role="img" aria-label="${esc(m.home_name)} win chance by day">
      <line x1="${P}" x2="${W - P}" y1="${y(0.5)}" y2="${y(0.5)}" class="roll-mid"/>
      <path d="${path}" fill="none" stroke="var(--color-accent)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
      <circle cx="${x(pts.length - 1).toFixed(1)}" cy="${y(last).toFixed(1)}" r="3.5" fill="var(--color-accent)"/></svg></div>`;
}

function oddsCard(m) {
  const cats = [...m.cats];
  if (S.sort === "sweat") cats.sort((a, b) => (b.sweat - a.sweat) || (Math.abs(a.p_home - 0.5) - Math.abs(b.p_home - 0.5)));
  const ph = m.p_home_win, pa = m.p_away_win, pt = m.p_tie;
  const maxSweat = Math.max(...m.cats.map((c) => c.sweat));
  return `<div class="card mu" id="mu${m.i}">
    <div class="mu-head">
      <div class="teams">
        <div class="tm h">${esc(m.home_name)}<small>${esc(m.home_owner)}</small></div>
        <div class="score">${m.now.hw}–${m.now.aw}${m.now.t ? `–${m.now.t}` : ""}<small>now</small></div>
        <div class="tm a">${esc(m.away_name)}<small>${esc(m.away_owner)}</small></div>
      </div>
      <div class="wp"><div class="h" style="width:${ph * 100}%">${ph >= .12 ? pct(ph) : ""}</div>${pt >= .03 ? `<div class="t" style="width:${pt * 100}%">${pt >= .08 ? "tie" : ""}</div>` : ""}<div class="a" style="width:${pa * 100}%">${pa >= .12 ? pct(pa) : ""}</div></div>
      <div class="sub" style="margin-top:4px">Projected finish ${m.exp_home_cats.toFixed(1)} – ${m.exp_away_cats.toFixed(1)} categories</div>
    </div>
    ${rollChart(m)}
    <div class="cats">${cats.map((c) => catRow(m, c, maxSweat)).join("")}</div>
    <div class="tonight">${side(m.home_side, m.home_name, "h")}${side(m.away_side, m.away_name, "a")}</div>
    ${cheeriosBlock({ home: m.home }, { name: m.home_name }, { name: m.away_name })}
    ${swapsBlock({ home: m.home }, { name: m.home_name }, { name: m.away_name })}
  </div>`;
}

const STATE = { "locked-home": "Locked", "locked-away": "Locked", "lean-home": "Leaning", "lean-away": "Leaning", "edge-home": "Slight edge", "edge-away": "Slight edge", "toss-up": "Toss-up" };
function catRow(m, c, maxSweat) {
  const p = c.p_home + c.p_tie / 2;
  const dev = Math.abs(p - 0.5) * 2; // 0 toss-up .. 1 locked
  const winH = c.reverse ? c.hv < c.av : c.hv > c.av, winA = c.reverse ? c.av < c.hv : c.av > c.hv;
  const hot = c.sweat >= 0.08 && c.sweat >= maxSweat * 0.5;
  const key = `${m.home}-${c.id}`;
  const open = S.open.has(key);
  const side = p >= 0.5 ? "h" : "a";
  const fill = c.state === "toss-up" ? "toss" : side;
  return `<div class="cat ${hot ? "sweatrow" : ""}" role="button" tabindex="0" aria-expanded="${open}" onclick="toggle('${key}')" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();toggle('${key}')}">
    <div class="v h ${winH ? "win" : winA ? "lose" : ""}">${fmt(c.hv, c.id)}</div>
    <div class="mid"><div class="lab">${hot ? '<span class="flame">SWEAT</span>' : ""}${c.label}<span class="st">${STATE[c.state]} · ${pct(Math.max(c.p_home, c.p_away))}${c.p_tie > 0.04 ? ` · tie ${pct(c.p_tie)}` : ""}</span></div>
      <div class="meter"><i class="${fill}" style="width:${dev * 50}%"></i></div></div>
    <div class="v a ${winA ? "win" : winH ? "lose" : ""}">${fmt(c.av, c.id)}</div>
    ${open ? detail(m, c) : ""}
  </div>`;
}

function detail(m, c) {
  const names = (a) => a.length ? a.map((x) => esc(x.name)).join(", ") : "nobody left";
  const nowGap = (c.hv ?? 0) - (c.av ?? 0);
  const ahead = (c.reverse ? nowGap < 0 : nowGap > 0) ? m.home_name : m.away_name;
  const behind = ahead === m.home_name ? m.away_name : m.home_name;
  const marg = PCT.has(c.id) ? `${(Math.abs(nowGap) * 100).toFixed(1)} pts` : Math.abs(Math.round(nowGap));
  const projGap = PCT.has(c.id) ? `${(Math.abs(c.gap_mean) * 100).toFixed(1)} pts` : Math.abs(c.gap_mean).toFixed(1);
  const sd = PCT.has(c.id) ? `${(c.gap_sd * 100).toFixed(1)} pts` : c.gap_sd.toFixed(1);
  const leaderProj = (c.reverse ? c.gap_mean < 0 : c.gap_mean > 0) ? m.home_name : m.away_name;
  const watchLabel = PCT.has(c.id) ? "most shots left" : "most to add";
  return `<div class="detail" onclick="event.stopPropagation()">
    <div><b>${esc(ahead)}</b> leads ${c.label} by ${marg}. Projected final margin: <b>${esc(leaderProj)}</b> by ${projGap} (typical swing ±${sd}).</div>
    <div>Winning this category moves the matchup by <b>${Math.round(c.swing * 100)} pts</b> of win probability${c.swing < 0.05 ? " (barely matters)" : ""}.</div>
    <div>${esc(m.home_name)}, ${watchLabel}: ${names(c.watch_h)}</div>
    <div>${esc(m.away_name)}, ${watchLabel}: ${names(c.watch_a)}</div></div>`;
}

/* "Shai Gilgeous-Alexander" -> "S. Gilgeous-Alexander"; suffixes like Jr. stay put */
const initialed = (n) => { const w = n.trim().split(/\s+/); return w.length > 1 ? `${w[0][0]}. ${w.slice(1).join(" ")}` : n; };

function side(s, name, cls) {
  const chips = s.tonight.slice(0, 12).map((p) => {
    const t = p.status === "upcoming" ? new Date(p.t).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }) : "";
    return `<span class="chip" title="${esc(p.name)}: ${p.pro} v ${p.opp}"><span class="dot ${p.status}"></span><span class="nm">${esc(initialed(p.name))}</span>${t ? `<em>${t}</em>` : ""}</span>`;
  }).join("");
  return `<div><h4 class="${cls}">${esc(name)} · ${s.player_games_left} player-games left</h4><div class="chips">${chips || '<span class="sub">No lineup players have a game today</span>'}</div></div>`;
}
