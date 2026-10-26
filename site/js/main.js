/* Boot: load data files, then route to the first tab. Loaded after every tab file. */
async function init() {
  const [meta, live, hist, recs, reg] = await Promise.all([j("data/meta.json"), j("data/live.json"), j("data/history.json"), j("data/records.json"), j("data/cheerios.json")]);
  S.meta = meta; S.live = live; S.history = hist; S.records = recs; S.cheerios = reg;
  $("#league-name").textContent = meta.league_name;
  document.title = meta.league_name + " · Analytics";
  S.season = meta.current;
  $("#season").innerHTML = [...meta.seasons].reverse().map((s) => `<option ${s === S.season ? "selected" : ""}>${s}</option>`).join("");
  $("#season").onchange = async (e) => { S.season = +e.target.value; S.week = null; await loadSeason(); render(); };
  document.querySelectorAll("#tabs button, #tabbar button").forEach((b) => (b.onclick = () => { if (b.closest("#tabbar")) haptic(); go(b.dataset.tab); }));
  await loadSeason();
  // old links (#sweat, #scores, #cats) still work
  const alias = { sweat: ["scoreboard", "full"], scores: ["scoreboard", "compact"], cats: ["standings", "categories"], regret: ["cheerios", ""], absences: ["cheerios", ""] };
  let [h0, h1] = location.hash.slice(1).split("/");
  if (alias[h0]) [h0, h1] = alias[h0];
  if (h0 === "history" && h1) S.hview = h1;
  else if (h0 === "scoreboard" && ["auto", "compact", "full"].includes(h1)) store.set("detail", h1);
  else if (h0 && h1) S.sub[h0] = h1;
  S.tab = TABS[h0] ? h0 : "scoreboard";
  go(S.tab);
}

/* pull down at the top of the page to reload the data, like a native list */
async function refreshData() {
  const t = Date.now(), fresh = (u) => j(u + "?t=" + t);
  const [meta, live, hist, recs, che] = await Promise.all([fresh("data/meta.json"), fresh("data/live.json"), fresh("data/history.json"), fresh("data/records.json"), fresh("data/cheerios.json")]);
  Object.assign(S, { meta, live, history: hist, records: recs, cheerios: che, seasons: {} });
  await loadSeason();
  render();
}
(function pullToRefresh() {
  const ptr = $("#ptr");
  let y0 = null, dy = 0, armed = false;
  const say = (txt, show) => { ptr.textContent = txt; ptr.classList.toggle("show", show); };
  addEventListener("touchstart", (e) => { y0 = window.scrollY <= 0 && e.touches.length === 1 ? e.touches[0].clientY : null; dy = 0; armed = false; }, { passive: true });
  addEventListener("touchmove", (e) => {
    if (y0 == null) return;
    dy = e.touches[0].clientY - y0;
    if (dy > 12) say(dy > 90 ? "Release to refresh" : "Pull to refresh", true);
    if (dy > 90 && !armed) { armed = true; haptic(); }
  }, { passive: true });
  addEventListener("touchend", async () => {
    if (y0 != null && dy > 90) { say("Updating", true); await refreshData(); say("Up to date", true); setTimeout(() => say("", false), 900); }
    else say("", false);
    y0 = null;
  });
})();

init();
