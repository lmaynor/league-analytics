/* Boot: load data files, then route to the first tab. Loaded after every tab file. */
async function init() {
  const [meta, live, hist, recs, reg, sup, rac, swp, lup, col, ros] = await Promise.all([j("data/meta.json"), j("data/live.json"), j("data/history.json"), j("data/records.json"), j("data/cheerios.json"), j("data/superlatives.json"), j("data/race.json"), j("data/swaps.json"), j("data/lineup.json"), j("data/collapse.json"), j("data/rosters.json")]);
  S.meta = meta; S.live = live; S.history = hist; S.records = recs; S.cheerios = reg; S.supers = sup; S.race = rac; S.swaps = swp; S.lineup = lup; S.collapse = col; S.rosters = ros;
  $("#league-name").textContent = meta.league_name;
  document.title = meta.league_name + " · Analytics";
  S.season = meta.current;
  $("#season").innerHTML = [...meta.seasons].reverse().map((s) => `<option ${s === S.season ? "selected" : ""}>${s}</option>`).join("");
  $("#season").onchange = async (e) => { S.season = +e.target.value; S.week = null; await loadSeason(); render(); };
  document.querySelectorAll("#tabs button, #tabbar button").forEach((b) => (b.onclick = () => { if (b.closest("#tabbar")) haptic(); go(b.dataset.tab); }));
  const tb = $("#theme");
  setTheme(document.documentElement.dataset.theme || "light");
  tb.onclick = () => { haptic(); setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"); };
  await loadSeason();
  // backwards compatible routing aliases
  const alias = {
    scoreboard: ["matchups", "scoreboard"], scores: ["matchups", "scoreboard"], sweat: ["matchups", "scoreboard"], recap: ["matchups", "recap"],
    standings: ["season", "standings"], power: ["season", "power"], race: ["season", "projections"], projections: ["season", "projections"],
    categories: ["teams", "categories"], cats: ["teams", "categories"], cheerios: ["teams", "cheerios"], absences: ["teams", "cheerios"], regret: ["matchups", "recap"],
    trades: ["teams", "trades"], trade: ["teams", "trades"],
    owners: ["history", "owners"], records: ["history", "records"], supers: ["history", "supers"], h2h: ["history", "h2h"],
  };
  let [h0, h1] = location.hash.slice(1).split("/");
  if (alias[h0]) {
    const [tgtTab, tgtSub] = alias[h0];
    h0 = tgtTab;
    if (!h1) h1 = tgtSub;
  }
  if (h0 === "matchups" && ["auto", "compact", "full"].includes(h1)) {
    store.set("detail", h1);
    h1 = "scoreboard";
  }
  if (h0 && h1) S.sub[h0] = h1;
  S.tab = TABS[h0] ? h0 : "matchups";
  go(S.tab);
}

/* pull down at the top of the page to reload the data, like a native list */
/* the small status pill: pull hints sit at the top (the page opens up as you pull); results sit above the tab bar, clear of the header */
let toastTimer;
const toast = (txt, show, top = false) => {
  const p = $("#ptr");
  clearTimeout(toastTimer);
  p.textContent = txt;
  p.classList.toggle("top", top);
  if (show) {
    p.style.display = "block";
    void p.offsetWidth;  // let the browser paint the start state so the slide-in animates
    p.classList.add("show");
  } else {
    p.classList.remove("show");
    // fully remove it afterwards: iOS tints the status bar from fixed elements at the top edge, even invisible ones
    toastTimer = setTimeout(() => { p.style.display = "none"; }, 260);
  }
};

/* if the page itself was redeployed, reload it so the new scripts and styles load too */
async function pageIsStale() {
  try {
    const html = await (await fetch("index.html?t=" + Date.now(), { cache: "no-store" })).text();
    const hashes = (t) => [...t.matchAll(/(?:src|href)="((?:js\/|img\/|style)[^"]*\?v=\w+)"/g)].map((x) => x[1]).sort().join();
    return hashes(html) !== hashes(document.documentElement.outerHTML);
  } catch { return false; }
}

async function refreshData() {
  if (await pageIsStale()) { location.reload(); return; }
  const t = Date.now(), fresh = (u) => j(u + "?t=" + t);
  const [meta, live, hist, recs, che, sup, rac, swp, lup, col, ros] = await Promise.all([fresh("data/meta.json"), fresh("data/live.json"), fresh("data/history.json"), fresh("data/records.json"), fresh("data/cheerios.json"), fresh("data/superlatives.json"), fresh("data/race.json"), fresh("data/swaps.json"), fresh("data/lineup.json"), fresh("data/collapse.json"), fresh("data/rosters.json")]);
  Object.assign(S, { meta, live, history: hist, records: recs, cheerios: che, supers: sup, race: rac, swaps: swp, lineup: lup, collapse: col, rosters: ros, seasons: {} });
  await loadSeason();
  render();
}
(function pullToRefresh() {
  let y0 = null, dy = 0, armed = false;
  const say = toast;
  addEventListener("touchstart", (e) => { y0 = window.scrollY <= 0 && e.touches.length === 1 ? e.touches[0].clientY : null; dy = 0; armed = false; }, { passive: true });
  addEventListener("touchmove", (e) => {
    if (y0 == null) return;
    dy = e.touches[0].clientY - y0;
    if (dy > 12) say(dy > 90 ? "Release to refresh" : "Pull to refresh", true, true);
    if (dy > 90 && !armed) { armed = true; haptic(); }
  }, { passive: true });
  addEventListener("touchend", async () => {
    if (y0 != null && dy > 90) { say("Updating", true); await refreshData(); say("Up to date", true); setTimeout(() => say("", false), 900); }
    else say("", false);
    y0 = null;
  });
})();

/* refresh button in the header: the same reload as pulling down, for when the gesture is not handy */
$("#refresh").onclick = async () => {
  const b = $("#refresh");
  if (b.classList.contains("spin")) return;
  haptic(); b.classList.add("spin"); toast("Updating", true);
  await refreshData();
  b.classList.remove("spin"); toast("Up to date", true); setTimeout(() => toast("", false), 1200);
};

init();
