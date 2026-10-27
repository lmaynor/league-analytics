/* Categories: team strength heatmap */
function cats() {
  const d = D();
  const rows = [...d.standings].sort((a, b) => a.power - b.power);
  const color = (z) => {
    const a = Math.min(Math.abs(z) / 2, 1) * 0.55;
    return z >= 0 ? `color-mix(in oklch, var(--heat-good) ${a * 100}%, transparent)` : `color-mix(in oklch, var(--heat-bad) ${a * 80}%, transparent)`;
  };
  panel().innerHTML = `<h1>${d.season} Category Strength</h1>
    <div class="sub">Per-week average for each category, with league rank. Color shows how far above or below the league average (turnovers are flipped: low is good).</div>
    <div class="card tbl-wrap" style="margin-top:12px"><table class="catgrid">
      <tr><th class="l team">Team</th>${d.cats.map((c) => `<th class="c">${c.label}</th>`).join("")}</tr>
      ${rows.map((r) => `<tr><td class="l team"><b>${esc(r.name)}</b><span class="sub">${esc(r.owner_name)}</span></td>${d.cats.map((c) => {
        const x = r.cat_rank[c.id]; const v = r.strength[c.id];
        return `<td class="heat" data-v="${x.z}" style="background:${color(x.z)}">${fmt(v, c.id)}<small>#${x.rank}</small></td>`;
      }).join("")}</tr>`).join("")}
    </table></div>`;
}

function teamsTab() {
  $("#view").innerHTML = subnav("teams", [["categories", "Categories"], ["cheerios", "Red Cheerios"], ["trades", "Trade Analyzer"]]);
  ({ categories: cats, cheerios, trades }[subTab("teams", "categories")] || cats)();
}
TABS.teams = teamsTab;
TABS.categories = () => { S.sub.teams = "categories"; go("teams"); };
