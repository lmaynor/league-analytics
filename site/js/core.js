/* Shared state, helpers, router and sortable tables. Each tab registers itself in TABS. */
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const store = {
  get(k, d) { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch {} },
};

const S = { meta: null, live: null, history: null, seasons: {}, tab: "scoreboard", sub: {}, season: null, sort: "sweat", week: null, open: new Set() };
const PCT = new Set([19, 20]);
const fmt = (v, id) => (v == null ? "–" : PCT.has(id) ? v.toFixed(3).replace(/^0/, "") : Math.round(v).toString());
const pct = (p) => `${Math.round(p * 100)}%`;
const j = (u) => fetch(u).then((r) => (r.ok ? r.json() : null)).catch(() => null);

const TABS = {};

/* Light haptic tick on touch devices. Android vibrates; iOS Safari has no vibrate API, but toggling a
   hidden switch checkbox from a tap gives the system tick (iOS 17.4+). Off when reduced motion is set. */
const canTick = matchMedia("(pointer: coarse)").matches && !matchMedia("(prefers-reduced-motion: reduce)").matches;
function haptic() {
  if (!canTick) return;
  if (navigator.vibrate) { navigator.vibrate(8); return; }
  let hx = document.getElementById("hx");
  if (!hx) {
    hx = document.createElement("label");
    hx.id = "hx"; hx.setAttribute("aria-hidden", "true");
    hx.style.cssText = "position:fixed;left:-99px;top:-99px;opacity:0;pointer-events:none";
    hx.innerHTML = '<input type="checkbox" switch tabindex="-1">';
    document.body.appendChild(hx);
  }
  hx.click();
}
const NO_SEASON = ["scoreboard", "history", "cheerios"];

/* a tab can have several views (Scoreboard: Scores | Sweat). Each view renders into #panel. */
const panel = () => $("#panel") || $("#view");
const subTab = (tab, fallback) => S.sub[tab] || store.get("sub-" + tab, fallback);
function subnav(tab, items) {
  const cur = subTab(tab, items[0][0]);
  return `<div class="toolbar"><div class="seg">${items.map(([k, l]) => `<button class="${k === cur ? "on" : ""}" onclick="setSub('${tab}','${k}')">${l}</button>`).join("")}</div></div><div id="panel"></div>`;
}
window.setSub = (tab, sub) => { S.sub[tab] = sub; store.set("sub-" + tab, sub); location.hash = tab + "/" + sub; render(); };

async function loadSeason() {
  if (!S.seasons[S.season]) S.seasons[S.season] = await j(`data/season_${S.season}.json`);
}
const D = () => S.seasons[S.season];

function go(tab) {
  S.tab = tab; location.hash = tab;
  document.querySelectorAll("#tabs button, #tabbar button").forEach((b) => b.classList.toggle("on", b.dataset.tab === tab));
  window.scrollTo(0, 0);
  $("#season").parentElement.style.display = NO_SEASON.includes(tab) ? "none" : "";
  render();
}
function render() { (TABS[S.tab] || TABS.scoreboard)(); markSortable($("#view"), ["Finish by Season", "#"]); }
const teamBy = (id) => S.seasons[S.meta.current]?.teams[id];


/* click a header on any table.sortable to sort by that column */
$("#view").addEventListener("click", (e) => sortBy(e.target.closest("table.sortable th")));
$("#view").addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { const th = e.target.closest("table.sortable th"); if (th) { e.preventDefault(); sortBy(th); } } });
function sortBy(th) {
  if (!th) return;
  const table = th.closest("table"), idx = [...th.parentElement.children].indexOf(th);
  const body = [...table.querySelectorAll("tr")].filter((r) => r !== th.parentElement && !r.classList.contains("nosort"));
  const val = (r) => { const c = r.children[idx]; const raw = c.dataset.v ?? (c.querySelector("b")?.textContent || c.textContent).trim();
    const n = parseFloat(String(raw).replace("−", "-").replace(/[^0-9.+-]/g, "")); return /^[\s+−-]?\.?\d/.test(String(raw)) && !isNaN(n) ? n : String(raw).toLowerCase(); };
  const text = typeof val(body[0]) === "string";
  const dir = th.dataset.dir === "desc" ? "asc" : th.dataset.dir === "asc" ? "desc" : (text ? "asc" : "desc");
  table.querySelectorAll("th").forEach((h) => { delete h.dataset.dir; h.removeAttribute("aria-sort"); });
  th.dataset.dir = dir; th.setAttribute("aria-sort", dir === "asc" ? "ascending" : "descending");
  body.sort((a, b) => { const x = val(a), y = val(b); const r = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y)); return dir === "asc" ? r : -r; });
  const parent = body[0].parentElement; body.forEach((r) => parent.insertBefore(r, parent.querySelector("tr.nosort") || null));
}
function markSortable(root, skip = []) {
  root.querySelectorAll("table.sortable").forEach((t) => t.querySelector("tr").querySelectorAll("th").forEach((th, i) => { if (!skip.includes(th.textContent.trim())) { th.tabIndex = 0; th.classList.add("sth"); th.title = "Sort"; } }));
}
