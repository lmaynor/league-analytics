/* Race for Last: who is on pace for the bottom, with a weekly trail of each team's chance */
const ordinal = (n) => `${n}${["th", "st", "nd", "rd"][(n % 100 >> 3) ^ 1 && n % 10 < 4 ? n % 10 : 0]}`;

function spark(trail) {
  const w = 84, h = 24, top = Math.max(0.15, ...trail);
  const pts = trail.map((p, i) => [trail.length < 2 ? w / 2 : (i / (trail.length - 1)) * (w - 6) + 3, h - 3 - (p / top) * (h - 6)]);
  const last = pts[pts.length - 1];
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="Chance of last, week by week">
    <polyline points="${pts.map((p) => p.map((v) => v.toFixed(1)).join(",")).join(" ")}" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
    <circle cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="2.6" fill="currentColor"/></svg>`;
}

function race() {
  const d = S.race?.seasons?.[S.season];
  if (!d) { panel().innerHTML = `<h1>${S.season} Race for Last</h1><div class="sub">The race covers the current season and the one before it.</div>`; return; }
  const pctTxt = (p) => (p >= 0.995 ? "100%" : p < 0.005 ? "0%" : p < 0.1 ? `${(p * 100).toFixed(1)}%` : `${Math.round(p * 100)}%`);
  const rec = (r) => `${r[0]}-${r[1]}${r[2] ? `-${r[2]}` : ""}`;
  const finish = (t) => (t.rank_p10 === t.rank_p90 ? ordinal(t.rank_med) : `${ordinal(t.rank_p10)} to ${ordinal(t.rank_p90)}`);
  panel().innerHTML = `<h1>${d.season} Race for Last</h1>
    <div class="sub">${d.complete ? "Final standings. The trail shows how each team's chance of finishing last moved week by week." : `The rest of the regular season, simulated 10,000 times from each team's category strength and the real schedule. ${d.live ? "This week's matchups use the live odds. " : ""}Chance of Last is how often a team finishes at the bottom.`}</div>
    <div class="card tbl-wrap" style="margin-top:12px"><table class="sortable">
      <tr><th class="l">Team</th><th class="hide-sm">Record</th><th class="hide-sm">Left</th><th class="hide-sm">Proj. Wins</th><th class="l">Chance of Last</th><th class="hide-sm">Bottom 3</th><th class="hide-sm">Likely Finish</th><th>Trail</th></tr>
      ${d.teams.map((t) => `<tr><td class="l"><b>${esc(t.name)}</b><span class="sub">${esc(t.owner)}<span class="show-sm"> · ${rec(t.record)}</span></span></td>
        <td class="hide-sm" data-v="${t.record[0]}">${rec(t.record)}</td><td class="hide-sm">${t.games_left}</td><td class="hide-sm">${t.proj_wins.toFixed(1)}</td>
        <td class="l" data-v="${t.p_last}"><div class="rbar"><i style="width:${Math.max(t.p_last * 100, t.p_last > 0 ? 2 : 0)}%"></i><span>${pctTxt(t.p_last)}</span></div></td>
        <td class="hide-sm" data-v="${t.p_bottom3}">${pctTxt(t.p_bottom3)}</td><td class="hide-sm" data-v="${t.rank_med}">${finish(t)}</td><td class="trail" data-v="${t.trail[t.trail.length - 1]}">${spark(t.trail)}</td></tr>`).join("")}
    </table></div>
    <div class="sub" style="margin-top:6px">Trail: chance of last at the start of the season and after each week. Likely Finish is the range most simulations land in.</div>`;
}
