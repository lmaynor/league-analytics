/* Scoreboard: the current matchup week. Compact shows scores; Full adds live odds, the closest
   categories and who plays tonight. Auto picks Full on the final day of the week. */
const todayET = () => new Date().toLocaleDateString("en-CA", { timeZone: "America/New_York" });
const isFinalDay = (L) => !!(L?.active && (L.final_day || L.end_date === todayET()));
function detailMode(L) {
  const pref = store.get("detail", "auto");
  return pref === "auto" ? (isFinalDay(L) ? "full" : "compact") : pref;
}
window.setDetail = (v) => { store.set("detail", v); scoreboard(); };

/* per-category odds under each score: "Locked 100%", "Toss-up 52%" */
function odds_(lm, id) {
  if (lm?.hidden) return "";
  const c = lm?.cats.find((x) => x.id === id);
  return c ? `<span class="st">${STATE[c.state]} · ${pct(Math.max(c.p_home, c.p_away))}</span>` : "";
}

/* Phones: a strip of matchup tiles over a swipe-and-snap row of cards, like a native scoreboard. */
const isPhone = () => window.matchMedia("(max-width: 700px)").matches;
function tiles(list) {
  return `<div class="tiles" id="tiles" style="--n:${list.length}">${list.map((x, i) => `<button class="tile${i === 0 ? " on" : ""}" onclick="goCard(${i})" aria-label="${esc(x.h)} versus ${esc(x.a)}">
    <span class="tt">${esc(x.h)}</span><b>${x.hw}–${x.aw}${x.t ? `–${x.t}` : ""}</b><span class="tt">${esc(x.a)}</span></button>`).join("")}</div>`;
}
const deckStep = (deck) => deck.firstElementChild.offsetWidth + 12;  // card width plus the gap
window.goCard = (i) => {
  const deck = $("#deck");
  if (!deck) return;
  haptic(); S.quiet = true; setTimeout(() => { S.quiet = false; }, 700);
  if (isPhone()) {
    const shift = deck.querySelector(":scope > [data-clone]") ? 1 : 0;
    deck.scrollTo({ left: deckStep(deck) * (i + shift), behavior: "smooth" });
    window.scrollTo({ top: Math.max(0, deck.getBoundingClientRect().top + scrollY - 70), behavior: "smooth" });
  } else deck.children[i]?.scrollIntoView({ behavior: "smooth", block: "start" });
};
let deckRO, deckScroll;
function wireDeck() {
  deckRO?.disconnect();
  const deck = $("#deck");
  if (deckScroll?.el) { deckScroll.el.removeEventListener("scroll", deckScroll.fn); deckScroll.el.removeEventListener("scrollend", deckScroll.end); }
  if (!deck || !isPhone()) { if (deck) deck.style.height = ""; return; }
  const real = [...deck.children], n = real.length, tl = [...document.querySelectorAll("#tiles .tile")];
  if (n > 1) {  // a copy of the last card before the first and of the first after the last makes the swipe loop
    const copy = (c) => { const k = c.cloneNode(true); k.removeAttribute("id"); k.dataset.clone = "1"; k.setAttribute("aria-hidden", "true"); k.inert = true; return k; };
    deck.insertBefore(copy(real[n - 1]), real[0]);
    deck.appendChild(copy(real[0]));
  }
  const shift = n > 1 ? 1 : 0, step = deckStep(deck);
  const fit = (i) => { deck.style.height = real[i].offsetHeight + "px"; };
  const mark = (i) => {  // i is the real card index
    if (i === S.cardIx) return;
    if (S.cardIx >= 0 && !S.quiet) haptic();  // a swipe landed on a new card
    S.cardIx = i;
    tl.forEach((t, k) => t.classList.toggle("on", k === i));
  };
  const domIndex = () => Math.max(0, Math.min(n - 1 + 2 * shift, Math.round(deck.scrollLeft / step)));
  const realOf = (k) => (n < 2 ? 0 : k === 0 ? n - 1 : k === n + 1 ? 0 : k - 1);
  const jump = (k) => { deck.style.scrollSnapType = "none"; deck.scrollLeft = step * k; setTimeout(() => { deck.style.scrollSnapType = ""; }, 60); };
  // Resizing the deck while a swipe is still gliding can cancel the snap, so heights and the loop jump wait until it stops.
  const settle = () => {
    const k = domIndex(), i = realOf(k);
    if (n > 1 && (k === 0 || k === n + 1)) jump(i + shift);
    mark(i); fit(i);
  };
  let timer;
  const onScroll = () => { mark(realOf(domIndex())); clearTimeout(timer); timer = setTimeout(settle, 140); };
  deck.addEventListener("scroll", onScroll, { passive: true });
  deck.addEventListener("scrollend", settle);
  deckScroll = { el: deck, fn: onScroll, end: settle };
  deckRO = new ResizeObserver(() => fit(S.cardIx >= 0 ? S.cardIx : 0));
  real.forEach((c) => deckRO.observe(c));
  const start = Math.min(Math.max(S.cardIx ?? 0, 0), n - 1);
  S.cardIx = -1; mark(start); fit(start); jump(start + shift);
}
matchMedia("(max-width: 700px)").addEventListener("change", () => { if (S.tab === "scoreboard") scoreboard(); });  // rebuild the deck (or drop its copies) when the width crosses the phone breakpoint

function scoreCard(m, d, lm) {
  const rev = Object.fromEntries(d.cats.map((c) => [c.id, c.reverse]));
  const lead = (c) => { const h = m.hs[c], a = m.as[c]; if (h == null || a == null || h === a) return 0; return (rev[c] ? h < a : h > a) ? 1 : -1; };
  const h = d.teams[m.home], a = d.teams[m.away];
  const tag = m.tier !== "NONE" ? (m.tier.startsWith("WINNERS") ? "Playoffs" : "Consolation") : lm ? "Live" : "Final";
  const lockNote = lm?.hidden ? `<div class="sub" style="margin-top:6px">Odds unlock when every starter has tipped off (${lm.lock.home[0] + lm.lock.away[0]} of ${lm.lock.home[1] + lm.lock.away[1]} locked).</div>` : "";
  const odds = lm && !lm.hidden ? `<div class="wp"><div class="h" style="width:${lm.p_home_win * 100}%">${lm.p_home_win >= .12 ? pct(lm.p_home_win) : ""}</div>${lm.p_tie >= .03 ? `<div class="t" style="width:${lm.p_tie * 100}%"></div>` : ""}<div class="a" style="width:${lm.p_away_win * 100}%">${lm.p_away_win >= .12 ? pct(lm.p_away_win) : ""}</div></div>
    <div class="sub" style="margin-top:4px">Win chance${lm.p_tie > 0.03 ? ` (tie ${pct(lm.p_tie)})` : ""}</div>` : "";
  return `<div class="card mu">
    <div class="mu-head"><div class="teams">
      <div class="tm h ${m.hw > m.aw ? "" : "dim"}">${esc(h.name)}<small>${esc(h.owner_name)}</small></div>
      <div class="score">${m.hw}–${m.aw}${m.t ? `–${m.t}` : ""}<small>${tag}</small></div>
      <div class="tm a ${m.aw > m.hw ? "" : "dim"}">${esc(a.name)}<small>${esc(a.owner_name)}</small></div></div>${odds}${lockNote}</div>
    <div class="cats">${d.cats.map((c) => { const l = lead(c.id);
      return `<div class="cat sb" style="cursor:default"><div class="v h ${l > 0 ? "win" : l < 0 ? "lose" : ""}">${fmt(m.hs[c.id], c.id)}</div>
        <div class="mid"><div class="lab">${c.label}${odds_(lm, c.id)}</div></div><div class="v a ${l < 0 ? "win" : l > 0 ? "lose" : ""}">${fmt(m.as[c.id], c.id)}</div></div>`; }).join("")}</div>${cheeriosBlock(m, h, a)}${swapsBlock(m, h, a)}</div>`;
}

function scoreboard() {
  const d = S.seasons[S.meta.current] || D();
  const L = S.live;
  const weeks = d.weeks.map((w) => w.mp);
  if (S.week == null || !weeks.includes(S.week)) S.week = d.current_mp && weeks.includes(d.current_mp) ? d.current_mp : weeks[weeks.length - 1];
  const w = d.weeks.find((x) => x.mp === S.week);
  const isLive = !!(L?.active && L.mp === S.week);
  const pref = store.get("detail", "auto");
  const full = isLive && detailMode(L) === "full" && L.matchups.some((m) => !m.hidden);  // nothing to show in Full until a matchup's odds unlock
  const seg = isLive ? `<div class="seg">${[["auto", "Auto"], ["compact", "Compact"], ["full", "Full"]].map(([k, l]) => `<button class="${pref === k ? "on" : ""}" onclick="setDetail('${k}')">${l}</button>`).join("")}</div>` : "";
  const weekName = (w) => `Week ${w.mp}${w.matchups[0]?.tier?.startsWith("WINNERS") ? " (Playoffs)" : ""}${w.mp === d.current_mp ? (L?.active && L.mp === w.mp ? " (Live)" : " (Current)") : ""}`;
  const picker = `<label class="wksel">Week <select onchange="S.week=+this.value;scoreboard()" aria-label="Choose a week">${[...d.weeks].reverse().map((w) => `<option value="${w.mp}"${w.mp === S.week ? " selected" : ""}>${weekName(w)}</option>`).join("")}</select></label>`;
  const toggle = `<div class="toolbar">${seg}${picker}</div>`;
  let body;
  if (full) {
    const list = L.matchups.map((m) => ({ h: m.home_owner, a: m.away_owner, hw: m.now.hw, aw: m.now.aw, t: m.now.t }));
    const byHome = Object.fromEntries(w.matchups.map((x) => [x.home, x]));
    body = `${oddsHeader(L)}${tiles(list)}<div class="grid deck" id="deck">${L.matchups.map((m, i) => (m.hidden ? scoreCard(byHome[m.home], d, m) : oddsCard({ ...m, i }))).join("")}</div>`;
  } else {
    const live = (m) => (isLive ? L.matchups.find((x) => x.home === m.home) : null);
    const list = w.matchups.map((m) => ({ h: d.teams[m.home].owner_name, a: d.teams[m.away].owner_name, hw: m.hw, aw: m.aw, t: m.t }));
    body = `${tiles(list)}<div class="grid deck" id="deck" style="margin-top:12px">${w.matchups.map((m) => scoreCard(m, d, live(m))).join("")}</div>`;
  }
  const award = S.lineup?.seasons?.[S.season]?.[String(S.week)];  // completed weeks only
  const awardHtml = award ? `<div class="award"><span class="award-tag">Worst Healthy Starter</span><b>${esc(award.name)}</b>
    <span class="sub">${esc(award.owner)} · ${esc(award.team)} · ${award.starts} starts · ${award.score.toFixed(1)}</span></div>` : "";
  const drama = S.collapse?.seasons?.[S.season]?.[String(S.week)];
  const dramaHtml = drama ? `<div class="award"><span class="award-tag">Biggest Throw</span><b>${esc(drama.team)}</b>
    <span class="sub">${esc(drama.owner)} · had a ${Math.round(drama.peak * 100)}% chance at one point, fell ${Math.round(drama.drop * 100)} points, lost ${drama.final}–${drama.final_opp}${drama.ties ? `–${drama.ties}` : ""} to ${esc(drama.opp)}</span></div>` : "";
  panel().innerHTML = `${toggle}<h1>Week ${S.week} ${full ? "Sweat Board" : "Scoreboard"}</h1>
    <div class="sub">${isLive ? "Live snapshot as of the last refresh." : S.week === d.current_mp ? "Current week." : "Final."}</div>${awardHtml}${dramaHtml}${body}`;
  wireDeck();
}

function makeAwardCard({ badge, badgeClass = "", metric, title, subtitle, narrative }) {
  return `<div class="award-card">
    <div class="award-card-top">
      <span class="award-badge ${badgeClass}">${badge}</span>
      <span class="award-metric">${metric}</span>
    </div>
    <div class="award-card-main">
      <div class="award-title">${esc(title)}</div>
      <div class="award-subtitle">${esc(subtitle)}</div>
    </div>
    <div class="award-narrative">${narrative}</div>
  </div>`;
}

function weeklyRecap() {
  const d = S.seasons[S.meta.current] || D();
  const L = S.live;
  const weeks = d.weeks.map((w) => w.mp);
  if (S.week == null || !weeks.includes(S.week)) {
    const completedWeeks = d.weeks.filter((w) => !w.matchups.some((m) => m.live)).map((w) => w.mp);
    S.week = completedWeeks.length ? completedWeeks[completedWeeks.length - 1] : (d.current_mp || weeks[weeks.length - 1]);
  }
  const w = d.weeks.find((x) => x.mp === S.week);
  const isLive = !!(L?.active && L.mp === S.week);
  const weekName = (wk) => `Week ${wk.mp}${wk.matchups[0]?.tier?.startsWith("WINNERS") ? " (Playoffs)" : ""}${wk.mp === d.current_mp ? (L?.active && L.mp === wk.mp ? " (Live)" : " (Current)") : ""}`;
  const picker = `<label class="wksel">Week <select onchange="S.week=+this.value;weeklyRecap()" aria-label="Choose a week">${[...d.weeks].reverse().map((wk) => `<option value="${wk.mp}"${wk.mp === S.week ? " selected" : ""}>${weekName(wk)}</option>`).join("")}</select></label>`;

  const currSeason = String(S.season || S.meta.current);
  const awardObj = S.lineup?.seasons?.[currSeason]?.[String(S.week)];
  const worst = awardObj?.worst || awardObj;
  const mvp = awardObj?.best;

  const cards = [];

  // Weekly MVP: highest player score among starters
  if (mvp) {
    cards.push(makeAwardCard({
      badge: "👑 Weekly MVP",
      badgeClass: "good",
      metric: `+${mvp.score.toFixed(1)} Rating`,
      title: mvp.name,
      subtitle: `${mvp.owner} · ${mvp.team}`,
      narrative: `Started ${mvp.starts} games, setting the league high-water mark for weekly player performance.`
    }));
  }

  // Cardboard Starter: lowest score by a healthy starter
  if (worst) {
    cards.push(makeAwardCard({
      badge: "🗑️ Cardboard Starter",
      badgeClass: "bad",
      metric: `${worst.score.toFixed(1)} Rating`,
      title: worst.name,
      subtitle: `${worst.owner} · ${worst.team}`,
      narrative: `Started ${worst.starts} healthy games and bottomed out with the lowest starter score in the league.`
    }));
  }

  // Biggest Throw: largest win-probability drop
  const drama = S.collapse?.seasons?.[currSeason]?.[String(S.week)];
  if (drama) {
    cards.push(makeAwardCard({
      badge: "🪓 Biggest Throw",
      badgeClass: "drama",
      metric: `Peaked at ${Math.round(drama.peak * 100)}%`,
      title: drama.team,
      subtitle: `${drama.owner} vs ${drama.opp}`,
      narrative: `Held a commanding ${Math.round(drama.peak * 100)}% win chance before choking away the lead to lose ${drama.final}–${drama.final_opp}.`
    }));
  }

  // Bench Regret: optimal bench-to-starter swap
  const swapsWeek = S.swaps?.weeks?.[String(S.week)] || [];
  let bestSwap = null, swapTeam = null;
  for (const sw of swapsWeek) {
    const h = d.teams[sw.home], a = d.teams[sw.away];
    for (const [list, tm] of [[sw.home_swaps, h], [sw.away_swaps, a]]) {
      for (const s of (list || [])) {
        if (!bestSwap || s.cats > bestSwap.cats || (s.to[0] > s.to[1] && bestSwap.to[0] <= bestSwap.to[1])) {
          bestSwap = s;
          swapTeam = tm;
        }
      }
    }
  }
  if (bestSwap && swapTeam) {
    const flipped = bestSwap.to[0] > bestSwap.to[1] && bestSwap.from[0] <= bestSwap.from[1];
    cards.push(makeAwardCard({
      badge: "🤦 Bench Regret",
      badgeClass: "bad",
      metric: flipped ? "Flipped Matchup (L)" : `Cost ${bestSwap.cats} Cat${bestSwap.cats === 1 ? "" : "s"}`,
      title: swapTeam.name,
      subtitle: `${swapTeam.owner_name} · Start ${bestSwap.in} over ${bestSwap.out}`,
      narrative: `Leaving <b>${esc(bestSwap.in)}</b> on the pine turned a ${bestSwap.to[0]}–${bestSwap.to[1]} win into a ${bestSwap.from[0]}–${bestSwap.from[1]} loss.`
    }));
  }

  // Weekly xWin Analysis: schedule fortune and misfortune
  const finished = w.matchups.filter((m) => m.hw + m.aw + m.t > 0);
  if (finished.length && !isLive) {
    const rev = Object.fromEntries(d.cats.map((c) => [c.id, c.reverse]));
    const teamStats = {};
    for (const m of finished) {
      teamStats[m.home] = { won: m.hw > m.aw, score: `${m.hw}–${m.aw}${m.t ? `–${m.t}` : ""}`, stats: m.hs, team: d.teams[m.home] };
      teamStats[m.away] = { won: m.aw > m.hw, score: `${m.aw}–${m.hw}${m.t ? `–${m.t}` : ""}`, stats: m.as, team: d.teams[m.away] };
    }
    const tids = Object.keys(teamStats);
    const xWins = {};
    for (const tid of tids) {
      let xw = 0;
      for (const oid of tids) {
        if (oid === tid) continue;
        let cw = 0, cl = 0;
        for (const c of d.cats) {
          const vT = teamStats[tid].stats[c.id], vO = teamStats[oid].stats[c.id];
          if (vT == null || vO == null || vT === vO) continue;
          if (rev[c.id] ? vT < vO : vT > vO) cw++;
          else cl++;
        }
        if (cw > cl) xw += 1;
        else if (cw === cl) xw += 0.5;
      }
      xWins[tid] = xw;
    }

    // Won with lowest xWin
    const winners = tids.filter((t) => teamStats[t].won).sort((a, b) => xWins[a] - xWins[b]);
    if (winners.length && xWins[winners[0]] <= 4.0) {
      const lucky = teamStats[winners[0]];
      const xwVal = xWins[winners[0]];
      cards.push(makeAwardCard({
        badge: "🍀 Lucky Bastard",
        badgeClass: "lucky",
        metric: `${xwVal.toFixed(1)}/9 xWins`,
        title: lucky.team.name,
        subtitle: `${lucky.team.owner_name} · Won ${lucky.score}`,
        narrative: `Escaped with a ${lucky.score} victory despite a ${xwVal.toFixed(1)}/9 xWin performance (would have lost to ${9 - Math.floor(xwVal)} other teams).`
      }));
    }

    // Lost with highest xWin
    const losers = tids.filter((t) => !teamStats[t].won).sort((a, b) => xWins[b] - xWins[a]);
    if (losers.length && xWins[losers[0]] >= 5.0) {
      const unlucky = teamStats[losers[0]];
      const xwVal = xWins[losers[0]];
      cards.push(makeAwardCard({
        badge: "⚡ Tough Luck",
        badgeClass: "drama",
        metric: `${xwVal.toFixed(1)}/9 xWins`,
        title: unlucky.team.name,
        subtitle: `${unlucky.team.owner_name} · Lost ${unlucky.score}`,
        narrative: `Put up a dominant ${xwVal.toFixed(1)}/9 xWin performance that would have beaten ${Math.floor(xwVal)} other teams, but caught the wrong opponent.`
      }));
    }

    // Closest and most lopsided margins
    const sortedByMargin = [...finished].sort((a, b) => Math.abs(a.hw - a.aw) - Math.abs(b.hw - b.aw));
    const closest = sortedByMargin[0];
    if (closest && Math.abs(closest.hw - closest.aw) <= 1) {
      const h = d.teams[closest.home], a = d.teams[closest.away];
      cards.push(makeAwardCard({
        badge: "🍿 Nailbiter",
        badgeClass: "drama",
        metric: "1 Cat Margin",
        title: `${h.name} vs ${a.name}`,
        subtitle: `Final: ${closest.hw}–${closest.aw}${closest.t ? `–${closest.t}` : ""}`,
        narrative: "A down-to-the-wire cardiac sweat that was decided by the skin of their teeth on Sunday night."
      }));
    }

    const biggest = sortedByMargin[sortedByMargin.length - 1];
    if (biggest && Math.abs(biggest.hw - biggest.aw) >= 3) {
      const winner = biggest.hw > biggest.aw ? d.teams[biggest.home] : d.teams[biggest.away];
      const loser = biggest.hw > biggest.aw ? d.teams[biggest.away] : d.teams[biggest.home];
      cards.push(makeAwardCard({
        badge: "🚜 Beatdown",
        badgeClass: "good",
        metric: `+${Math.abs(biggest.hw - biggest.aw)} Cat Victory`,
        title: `${winner.name} over ${loser.name}`,
        subtitle: `Final: ${Math.max(biggest.hw, biggest.aw)}–${Math.min(biggest.hw, biggest.aw)}`,
        narrative: "A ruthless, lopsided statement win that completely dismantled the opponent from day one."
      }));
    }
  }

  // ICU Ward: team with the most starter absences
  const cheeriosWeek = S.cheerios?.seasons?.[currSeason]?.weeks?.[String(S.week)] || [];
  let maxAbsences = 0, icuTeam = null, icuNames = [];
  for (const ch of cheeriosWeek) {
    const h = d.teams[ch.home], a = d.teams[ch.away];
    for (const [side, tm] of [[ch.home_side, h], [ch.away_side, a]]) {
      if (side && side.games > maxAbsences) {
        maxAbsences = side.games;
        icuTeam = tm;
        icuNames = side.missed.map((p) => p.name);
      }
    }
  }
  if (icuTeam && maxAbsences >= 2) {
    cards.push(makeAwardCard({
      badge: "🩹 ICU Ward",
      badgeClass: "bad",
      metric: `${maxAbsences} Missed Starts`,
      title: icuTeam.name,
      subtitle: `${icuTeam.owner_name} · Injury Ward`,
      narrative: `Hit hardest by the injury bug with ${maxAbsences} missed starter games (${icuNames.slice(0, 3).join(", ")}).`
    }));
  }

  const debriefs = w.matchups.map((m) => {
    const h = d.teams[m.home], a = d.teams[m.away];
    const sw = swapsBlock(m, h, a, S.week);
    const ch = cheeriosBlock(m, h, a, S.week);
    return `<div class="card" style="margin-top:12px">
      <div style="display:flex;justify-content:space-between;align-items:baseline;padding-bottom:8px;border-bottom:1px solid var(--color-rule)">
        <div><b>${esc(h.name)}</b> <span class="sub" style="display:inline">(${esc(h.owner_name)})</span> vs <b>${esc(a.name)}</b> <span class="sub" style="display:inline">(${esc(a.owner_name)})</span></div>
        <div style="font-weight:600;font-family:var(--font-display);font-size:16px">${m.hw}–${m.aw}${m.t ? `–${m.t}` : ""}</div>
      </div>
      ${sw || '<div class="sub" style="margin-top:8px">No bench regrets this week.</div>'}
      ${ch}
    </div>`;
  }).join("");

  panel().innerHTML = `<div class="toolbar">${picker}</div>
    <h1>Week ${S.week} Recap</h1>
    <div class="sub">${isLive ? "In-progress week. Awards finalize when all games finish." : "Weekly awards, hindsight blunders, and category debriefs."}</div>
    <div class="awards-grid">
      ${cards.join("")}
    </div>
    <h2 style="margin-top:28px">Trades Debrief</h2>
    ${tradesDebrief(S.week)}
    <h2 style="margin-top:28px">Matchup Debriefs</h2>
    ${debriefs}`;
}

function tradesDebrief(mp) {
  const weekTrades = S.trades?.weeks?.[String(mp)] || [];
  if (!weekTrades.length) {
    return `<div class="card" style="margin-top:10px;padding:12px 14px;display:flex;flex-wrap:wrap;gap:8px;justify-content:space-between;align-items:center">
      <div>
        <b>No trades completed in Week ${mp}</b>
        <div class="sub">Simulate prospective player swaps and 9-category impact in the Trade Machine.</div>
      </div>
      <button class="pill" style="cursor:pointer;padding:5px 12px;font-size:12px;background:var(--color-key-face);border:1px solid var(--color-rule-2);color:var(--text)" onclick="setSub('teams','trades');go('teams')">Trade Machine →</button>
    </div>`;
  }

  return weekTrades.map((t) => {
    const pA = t.players_a.map((p) => p.name).join(", ");
    const pB = t.players_b.map((p) => p.name).join(", ");
    const winnerName = t.winner_id ? (t.winner_id === t.team_a.id ? t.team_a.name : t.team_b.name) : "Even Trade";
    return `<div class="card" style="margin-top:10px">
      <div style="display:flex;justify-content:space-between;align-items:baseline;padding-bottom:8px;border-bottom:1px solid var(--color-rule)">
        <div><b>${esc(t.team_a.name)}</b> ⇄ <b>${esc(t.team_b.name)}</b></div>
        <span class="pill" style="font-weight:600;color:var(--color-accent-deep);background:var(--color-accent-wash)">Winner: ${esc(winnerName)} (${t.margin})</span>
      </div>
      <div style="margin-top:8px;display:grid;grid-template-columns:repeat(auto-fit, minmax(200px, 1fr));gap:8px;font-size:13px">
        <div><b>${esc(t.team_a.name)} got:</b> <span class="sub" style="display:inline">${esc(pA)}</span></div>
        <div><b>${esc(t.team_b.name)} got:</b> <span class="sub" style="display:inline">${esc(pB)}</span></div>
      </div>
    </div>`;
  }).join("");
}

function matchupsTab() {
  $("#view").innerHTML = subnav("matchups", [["scoreboard", "Scoreboard"], ["recap", "Weekly Recap"]]);
  ({ scoreboard, recap: weeklyRecap }[subTab("matchups", "scoreboard")] || scoreboard)();
}
TABS.matchups = matchupsTab;
TABS.scoreboard = () => go("matchups");

/* Bench Regret: swaps that would be flipping the matchup if a benched player had started instead */
function swapsBlock(m, h, a, wk) {
  const currentWeek = wk || S.week;
  const weekList = S.swaps?.weeks?.[String(currentWeek)] || S.swaps?.matchups || [];
  const sw = weekList.find((x) => x.home === m.home);
  if (!sw) return "";
  const rec = (r) => `${r[0]}-${r[1]}${r[2] ? `-${r[2]}` : ""}`;
  const line = (list, t) => (list || []).map((x) => `<div class="rl"><b>${esc(t.name)}</b>: start <b>${esc(x.in)}</b> over ${esc(x.out)} this week and it's ${rec(x.to)} instead of ${rec(x.from)}.</div>`).join("");
  const body = line(sw.home_swaps, h) + line(sw.away_swaps, a);
  return body ? `<div class="cheerios swaps"><h4>Bench Regret</h4>${body}</div>` : "";
}

/* Red Cheerios: who missed starts and what a healthy lineup would have meant */
function cheeriosBlock(m, h, a, wk) {
  const currSeason = String(S.season || S.meta.current);
  const currentWeek = wk || S.week;
  const weekMatches = S.cheerios?.seasons?.[currSeason]?.weeks?.[String(currentWeek)] || S.cheerios?.seasons?.[currSeason]?.live || [];
  const entry = weekMatches.find((x) => x.home === m.home);
  if (!entry) return "";
  const rec = (r) => `${r[0]}-${r[1]}${r[2] ? `-${r[2]}` : ""}`;
  const line = (side, t) => {
    if (!side || !side.games) return "";
    const names = side.missed.map((p) => `${esc(p.name)}${p.games > 1 ? ` (${p.games})` : ""}`).join(", ");
    const gain = side.cats_lost ? `, +${side.cats_lost} categor${side.cats_lost === 1 ? "y" : "ies"}` : "";
    return `<div class="rl"><b>${esc(t.name)}</b> missed ${side.games} starter game${side.games === 1 ? "" : "s"}: ${names}.
      Healthy: <b>${rec(side.healthy)}</b>${gain}${side.flips ? ' <span class="flip">Would have flipped the matchup</span>' : ""}</div>`;
  };
  const body = line(entry.home_side, h) + line(entry.away_side, a);
  return `<div class="cheerios"><h4>Red Cheerios, Absences</h4>${body || '<div class="sub">Every starter who was supposed to play has played.</div>'}</div>`;
}
