/* Red Cheerios: what each week would have looked like if no starter had missed a game */
function cheerios() {
  const A = S.cheerios?.seasons || {};
  const years = Object.keys(A).sort();
  if (!years.length) { $("#view").innerHTML = `<div class="empty"><h1>No Red Cheerios Yet</h1><p>This needs daily rosters. Run <code>pipeline/build.py --fetch</code> to pull them.</p></div>`; return; }
  if (!S.regYear || !A[S.regYear]) S.regYear = A[String(S.meta.current)] ? String(S.meta.current) : years[years.length - 1];
  const a = A[S.regYear];
  const rec = (r) => `${r[0]}-${r[1]}${r[2] ? `-${r[2]}` : ""}`;
  const seg = `<div class="toolbar"><div class="seg">${[...years].reverse().map((y) => `<button class="${y === S.regYear ? "on" : ""}" onclick="S.regYear='${y}';cheerios()">${y}</button>`).join("")}</div></div>`;
  $("#view").innerHTML = `<h1>Red Cheerios</h1>
    <div class="sub">ESPN marks a player who is Out with a red O, and the league calls them Red Cheerios. These are starters who sat in an active slot on a day their NBA team played, and didn't play. A lone one-game absence with no injury flag counts as rest and is ignored. "Healthy" adds each one's usual per-game production back and re-scores the week against the opponent's real totals. ${a.complete ? "" : "Includes the week in progress, so it can still change."}</div>${seg}
    <div class="card tbl-wrap" style="margin-top:6px"><table class="sortable">
      <tr><th class="l">Team</th><th>Games Missed</th><th>Wins Lost</th><th>Wins Gifted</th><th>Record</th><th>Healthy</th><th class="l">Most Missed</th></tr>
      ${a.teams.map((t) => `<tr><td class="l"><b>${esc(t.team)}</b><span class="sub">${esc(t.owner)}</span></td><td>${t.games_missed}</td>
        <td class="${t.wins_lost > 0 ? "pos" : ""}">${t.wins_lost}</td><td>${t.wins_gifted}</td><td data-v="${t.record[0]}">${rec(t.record)}</td><td data-v="${t.healthy_record[0]}">${rec(t.healthy_record)}</td>
        <td class="l sub">${t.most_missed.map((m) => `${esc(m.name)} (${m.games})`).join(", ") || "none"}</td></tr>`).join("")}
    </table></div>
    <div class="sub" style="margin-top:6px">Wins lost: matchups that would have flipped in the team's favor, ties counting half. Wins gifted: wins that would have slipped away if the opponent's absences hadn't happened.</div>
    ${a.ouch.length ? `<h2>Biggest Hits</h2><div class="card tbl-wrap"><table class="sortable">
      <tr><th class="l">When</th><th class="l">Team</th><th class="l">Opponent</th><th>Actual</th><th>Healthy</th><th>Games Missed</th><th class="l">Biggest Absences</th></tr>
      ${a.ouch.map((o) => `<tr><td class="l">${o.season} wk ${o.mp}${o.playoff ? " (playoffs)" : ""}</td><td class="l"><b>${esc(o.team)}</b></td><td class="l">${esc(o.opp)}</td><td>${o.actual}</td><td>${o.healthy}</td><td>${o.games}</td><td class="l sub">${o.players.map(esc).join(", ")}</td></tr>`).join("")}
    </table></div>` : ""}
    ${a.players.length ? `<h2>Most Starter Games Missed</h2><div class="card tbl-wrap"><table class="sortable">
      <tr><th class="l">Player</th><th class="l">Team</th><th>Games Missed</th><th>Usual Pts</th></tr>
      ${a.players.map((p) => `<tr><td class="l"><b>${esc(p.name)}</b></td><td class="l">${esc(p.team)}</td><td>${p.games}</td><td>${p.pts}</td></tr>`).join("")}
    </table></div>` : ""}`;
}
TABS.cheerios = cheerios;
