/* Standings: one tab, three views (Standings | Power | Categories) sharing the season picker */
function standings() {
  const d = D();
  const rows = d.standings;
  panel().innerHTML = `<h1>${d.season} Standings${d.complete ? "" : " (live)"}</h1>
    <div class="sub">Regular season. xWin is the matchups your weekly totals would win against every team. Luck is actual wins minus xWin.</div>
    <div class="card tbl-wrap" style="margin-top:12px"><table class="sortable">
      <tr><th class="rank">#</th><th class="l">Team</th><th>W-L-T</th><th>Cats</th><th>Cat %</th><th>Last 4</th><th>xWin</th><th>Luck</th><th>1-Cat W</th><th>1-Cat L</th><th>9-0s</th></tr>
      ${rows.map((r) => `<tr><td class="rank">${r.seed}</td><td class="l"><b>${esc(r.name)}</b><span class="sub">${esc(r.owner_name)}</span></td>
        <td data-v="${r.win_pct}">${r.w}-${r.l}-${r.t}</td><td data-v="${r.cat_pct}">${r.cw}-${r.cl}-${r.ct}</td><td>${(r.cat_pct * 100).toFixed(1)}</td><td>${(r.recent_cat_pct * 100).toFixed(0)}</td>
        <td>${r.xw.toFixed(1)}</td><td class="${r.luck > 0 ? "pos" : r.luck < 0 ? "neg" : ""}">${r.luck > 0 ? "+" : r.luck < 0 ? "−" : ""}${Math.abs(r.luck).toFixed(1)}</td>
        <td>${r.one_cat_w}</td><td>${r.one_cat_l}</td><td>${r.sweeps}</td></tr>`).join("")}
    </table></div>`;
}

function power() {
  const d = D();
  const rows = [...d.standings].sort((a, b) => a.power - b.power);
  panel().innerHTML = `<h1>${d.season} Power Ranking</h1>
    <div class="sub">60% season category win rate plus 40% last four weeks. It counts categories won, not just matchups.</div>
    <div class="card tbl-wrap" style="margin-top:12px"><table class="sortable">
      <tr><th class="rank">#</th><th class="l">Team</th><th>Score</th><th>Season Cat %</th><th>Last 4 Cat %</th><th>Standings</th></tr>
      ${rows.map((r) => `<tr><td class="rank">${r.power}</td><td class="l"><b>${esc(r.name)}</b><span class="sub">${esc(r.owner_name)}</span></td>
        <td>${((0.6 * r.cat_pct + 0.4 * r.recent_cat_pct) * 100).toFixed(1)}</td><td>${(r.cat_pct * 100).toFixed(1)}</td><td>${(r.recent_cat_pct * 100).toFixed(1)}</td>
        <td data-v="${-r.seed}">#${r.seed}</td></tr>`).join("")}
    </table></div>`;
}

function standingsTab() {
  $("#view").innerHTML = subnav("standings", [["table", "Standings"], ["power", "Power"], ["race", "Race for Last"], ["categories", "Categories"]]);
  ({ table: standings, power, race, categories: cats }[subTab("standings", "table")] || standings)();
}
TABS.standings = standingsTab;
