/* Red Cheerios: what each week would have looked like if no starter had missed a game */
function cheerios() {
  const A = S.cheerios?.seasons || {};
  const years = Object.keys(A).sort();
  if (!years.length) { panel().innerHTML = `<div class="empty"><h1>No Red Cheerios Yet</h1><p>This needs daily rosters. Run <code>pipeline/build.py --fetch</code> to pull them.</p></div>`; return; }
  if (S.season && A[String(S.season)]) S.regYear = String(S.season);
  if (!S.regYear || !A[S.regYear]) S.regYear = A[String(S.meta.current)] ? String(S.meta.current) : years[years.length - 1];
  const a = A[S.regYear];
  const rec = (r) => `${r[0]}-${r[1]}${r[2] ? `-${r[2]}` : ""}`;
  const seg = `<div class="toolbar"><div class="seg">${[...years].reverse().map((y) => `<button class="${y === S.regYear ? "on" : ""}" onclick="S.regYear='${y}';cheerios()">${y}</button>`).join("")}</div></div>`;
  panel().innerHTML = `<h1>Red Cheerios</h1>
    <div class="sub">Starters who sat out a game their NBA team played, hurt or resting. Healthy adds each missed game's usual production back and re-scores the week against the opponent's real totals. ${a.complete ? "" : "Includes the week in progress, so it can still change."}</div>${seg}
    <div class="card tbl-wrap" style="margin-top:6px"><table class="sortable">
      <tr><th class="l">Team</th><th>Games Missed</th><th>Wins Lost</th><th>Wins Gifted</th><th>Record</th><th>Healthy</th><th class="l mm-head">Most Missed</th></tr>
      ${a.teams.map((t) => `<tr><td class="l"><b>${esc(t.team)}</b><span class="sub">${esc(t.owner)}</span>${t.most_missed.length ? `<div class="mm mm-phone">${t.most_missed.map((m) => `<span class="mchip" title="${esc(m.name)}">${esc(initialed(m.name))} <b>${m.games}</b></span>`).join("")}</div>` : ""}</td><td>${t.games_missed}</td>
        <td class="${t.wins_lost > 0 ? "pos" : ""}">${t.wins_lost}</td><td>${t.wins_gifted}</td><td data-v="${t.record[0]}">${rec(t.record)}</td><td data-v="${t.healthy_record[0]}">${rec(t.healthy_record)}</td>
        <td class="l mm-cell">${t.most_missed.length ? `<div class="mm">${t.most_missed.map((m) => `<span class="mchip" title="${esc(m.name)}">${esc(initialed(m.name))} <b>${m.games}</b></span>`).join("")}</div>` : '<span class="sub">None</span>'}</td></tr>`).join("")}
    </table></div>
    <div class="sub" style="margin-top:6px">Wins lost: matchups that would have flipped in the team's favor, ties counting half. Wins gifted: wins that would have slipped away if the opponent's absences hadn't happened.</div>
    ${a.ouch.length ? `<h2>Biggest Hits</h2><div class="card tbl-wrap"><table class="sortable">
      <tr><th class="l">When</th><th class="l">Team</th><th class="l">Opponent</th><th>Actual</th><th>Healthy</th><th>Games Missed</th><th class="l">Biggest Absences</th></tr>
      ${a.ouch.map((o) => `<tr><td class="l">${o.season} wk ${o.mp}${o.playoff ? " (playoffs)" : ""}</td><td class="l"><b>${esc(o.team)}</b></td><td class="l">${esc(o.opp)}</td><td>${o.actual}</td><td>${o.healthy}</td><td>${o.games}</td><td class="l sub">${o.players.map(esc).join(", ")}</td></tr>`).join("")}
    </table></div>` : ""}
    ${a.players.length ? `<h2>Most Starter Games Missed</h2><div class="card tbl-wrap"><table class="sortable">
      <tr><th class="l">Player</th><th class="l">Team</th><th>Games Missed</th><th class="l">Hurts Most In</th></tr>
      ${a.players.map((p) => `<tr><td class="l"><b>${esc(p.name)}</b></td><td class="l">${esc(p.team)}</td><td>${p.games}</td><td class="l">${p.hits.map((h) => h.lost ? `${h.cat} −${h.lost}` : h.cat).join(", ")}</td></tr>`).join("")}
    </table></div>` : ""}`;
}
TABS.cheerios = () => { S.sub.teams = "cheerios"; go("teams"); };
