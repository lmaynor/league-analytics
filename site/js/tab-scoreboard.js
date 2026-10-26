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
  const c = lm?.cats.find((x) => x.id === id);
  return c ? `<span class="st">${STATE[c.state]} · ${pct(Math.max(c.p_home, c.p_away))}</span>` : "";
}

/* Phones: a strip of matchup tiles over a swipe-and-snap row of cards, like a native scoreboard. */
const isPhone = () => window.matchMedia("(max-width: 700px)").matches;
function tiles(list) {
  return `<div class="tiles" id="tiles" style="--n:${list.length}">${list.map((x, i) => `<button class="tile${i === 0 ? " on" : ""}" onclick="goCard(${i})" aria-label="${esc(x.h)} versus ${esc(x.a)}">
    <span class="tt">${esc(x.h)}</span><b>${x.hw}–${x.aw}${x.t ? `–${x.t}` : ""}</b><span class="tt">${esc(x.a)}</span></button>`).join("")}</div>`;
}
window.goCard = (i) => {
  const deck = $("#deck"), card = deck?.children[i];
  if (!card) return;
  haptic(); S.quiet = true; setTimeout(() => { S.quiet = false; }, 700);
  if (isPhone()) { deck.scrollTo({ left: card.offsetLeft - 12, behavior: "smooth" }); window.scrollTo({ top: Math.max(0, deck.getBoundingClientRect().top + scrollY - 70), behavior: "smooth" }); }
  else card.scrollIntoView({ behavior: "smooth", block: "start" });
};
let deckRO, deckScroll;
function wireDeck() {
  deckRO?.disconnect();
  const deck = $("#deck");
  if (deckScroll && deckScroll.el) deckScroll.el.removeEventListener("scroll", deckScroll.fn);
  if (!deck || !isPhone()) { if (deck) deck.style.height = ""; return; }
  const cards = [...deck.children], tl = [...document.querySelectorAll("#tiles .tile")];
  const fit = (card) => { deck.style.height = card.offsetHeight + "px"; };
  const show = (i) => {
    if (i === S.cardIx && deck.style.height) return;
    if (S.cardIx >= 0 && !S.quiet) haptic();  // a swipe landed on a new card
    S.cardIx = i;
    tl.forEach((t, k) => t.classList.toggle("on", k === i));
    tl[i]?.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" });
    fit(cards[i]);
  };
  const nearest = () => { const step = cards[0].offsetWidth + 12; return Math.max(0, Math.min(cards.length - 1, Math.round(deck.scrollLeft / step))); };
  const fn = () => show(nearest());
  deck.addEventListener("scroll", fn, { passive: true });
  deckScroll = { el: deck, fn };
  deckRO = new ResizeObserver(() => fit(cards[S.cardIx || 0]));
  cards.forEach((c) => deckRO.observe(c));
  const start = Math.min(S.cardIx || 0, cards.length - 1);
  S.cardIx = -1; show(start);
  if (start) deck.scrollTo({ left: cards[start].offsetLeft - 12 });
}

function scoreCard(m, d, lm) {
  const rev = Object.fromEntries(d.cats.map((c) => [c.id, c.reverse]));
  const lead = (c) => { const h = m.hs[c], a = m.as[c]; if (h == null || a == null || h === a) return 0; return (rev[c] ? h < a : h > a) ? 1 : -1; };
  const h = d.teams[m.home], a = d.teams[m.away];
  const tag = m.tier !== "NONE" ? (m.tier.startsWith("WINNERS") ? "Playoffs" : "Consolation") : lm ? "Live" : "Final";
  const odds = lm ? `<div class="wp"><div class="h" style="width:${lm.p_home_win * 100}%">${lm.p_home_win >= .12 ? pct(lm.p_home_win) : ""}</div>${lm.p_tie >= .03 ? `<div class="t" style="width:${lm.p_tie * 100}%"></div>` : ""}<div class="a" style="width:${lm.p_away_win * 100}%">${lm.p_away_win >= .12 ? pct(lm.p_away_win) : ""}</div></div>
    <div class="sub" style="margin-top:4px">Win chance${lm.p_tie > 0.03 ? ` (tie ${pct(lm.p_tie)})` : ""}</div>` : "";
  return `<div class="card mu">
    <div class="mu-head"><div class="teams">
      <div class="tm h ${m.hw > m.aw ? "" : "dim"}">${esc(h.name)}<small>${esc(h.owner_name)}</small></div>
      <div class="score">${m.hw}–${m.aw}${m.t ? `–${m.t}` : ""}<small>${tag}</small></div>
      <div class="tm a ${m.aw > m.hw ? "" : "dim"}">${esc(a.name)}<small>${esc(a.owner_name)}</small></div></div>${odds}</div>
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
  const full = isLive && detailMode(L) === "full";
  const seg = isLive ? `<div class="seg">${[["auto", "Auto"], ["compact", "Compact"], ["full", "Full"]].map(([k, l]) => `<button class="${pref === k ? "on" : ""}" onclick="setDetail('${k}')">${l}</button>`).join("")}</div>` : "";
  const weekName = (w) => `Week ${w.mp}${w.matchups[0]?.tier?.startsWith("WINNERS") ? " (Playoffs)" : ""}${w.mp === d.current_mp ? (L?.active && L.mp === w.mp ? " (Live)" : " (Current)") : ""}`;
  const picker = `<label class="wksel">Week <select onchange="S.week=+this.value;scoreboard()" aria-label="Choose a week">${[...d.weeks].reverse().map((w) => `<option value="${w.mp}"${w.mp === S.week ? " selected" : ""}>${weekName(w)}</option>`).join("")}</select></label>`;
  const toggle = `<div class="toolbar">${seg}${picker}</div>`;
  let body;
  if (full) {
    const list = L.matchups.map((m) => ({ h: m.home_owner, a: m.away_owner, hw: m.now.hw, aw: m.now.aw, t: m.now.t }));
    body = `${oddsHeader(L)}${tiles(list)}<div class="grid deck" id="deck">${L.matchups.map((m, i) => oddsCard({ ...m, i })).join("")}</div>`;
  } else {
    const live = (m) => (isLive ? L.matchups.find((x) => x.home === m.home) : null);
    const list = w.matchups.map((m) => ({ h: d.teams[m.home].owner_name, a: d.teams[m.away].owner_name, hw: m.hw, aw: m.aw, t: m.t }));
    body = `${tiles(list)}<div class="grid deck" id="deck" style="margin-top:12px">${w.matchups.map((m) => scoreCard(m, d, live(m))).join("")}</div>`;
  }
  $("#view").innerHTML = `${toggle}<h1>Week ${S.week} ${full ? "Sweat Board" : "Scoreboard"}</h1>
    <div class="sub">${isLive ? "Live snapshot as of the last refresh." : S.week === d.current_mp ? "Current week." : "Final."}</div>${body}`;
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
