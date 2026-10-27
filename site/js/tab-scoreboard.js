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
  $("#view").innerHTML = `${toggle}<h1>Week ${S.week} ${full ? "Sweat Board" : "Scoreboard"}</h1>
    <div class="sub">${isLive ? "Live snapshot as of the last refresh." : S.week === d.current_mp ? "Current week." : "Final."}</div>${awardHtml}${dramaHtml}${body}`;
  wireDeck();
}
TABS.scoreboard = scoreboard;

/* Bench Regret: swaps that would be flipping the matchup if a benched player had started instead */
function swapsBlock(m, h, a) {
  const sw = S.swaps?.matchups?.find((x) => x.home === m.home);
  if (!sw) return "";
  const rec = (r) => `${r[0]}-${r[1]}${r[2] ? `-${r[2]}` : ""}`;
  const line = (list, t) => list.map((x) => `<div class="rl"><b>${esc(t.name)}</b>: start <b>${esc(x.in)}</b> over ${esc(x.out)} this week and it's ${rec(x.to)} instead of ${rec(x.from)}.</div>`).join("");
  const body = line(sw.home_swaps, h) + line(sw.away_swaps, a);
  return body ? `<div class="cheerios swaps"><h4>Bench Regret</h4>${body}</div>` : "";
}

/* Red Cheerios for the week so far: who missed starts and what a healthy lineup would have meant */
function cheeriosBlock(m, h, a) {
  const live = S.cheerios?.seasons?.[S.meta.current]?.live?.find((x) => x.home === m.home);
  if (!live) return "";
  const rec = (r) => `${r[0]}-${r[1]}${r[2] ? `-${r[2]}` : ""}`;
  const line = (side, t) => {
    if (!side.games) return "";
    const names = side.missed.map((p) => `${esc(p.name)}${p.games > 1 ? ` (${p.games})` : ""}`).join(", ");
    const gain = side.cats_lost ? `, +${side.cats_lost} categor${side.cats_lost === 1 ? "y" : "ies"}` : "";
    return `<div class="rl"><b>${esc(t.name)}</b> missed ${side.games} starter game${side.games === 1 ? "" : "s"}: ${names}.
      Healthy: <b>${rec(side.healthy)}</b>${gain}${side.flips ? ' <span class="flip">Would have flipped the matchup</span>' : ""}</div>`;
  };
  const body = line(live.home_side, h) + line(live.away_side, a);
  return `<div class="cheerios"><h4>Red Cheerios, So Far This Week</h4>${body || '<div class="sub">Every starter who was supposed to play has played.</div>'}</div>`;
}
