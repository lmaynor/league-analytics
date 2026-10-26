/* History: all-time owners, records, head to head */
function history() {
  const H = S.history, owners = H.owners;
  S.hview = S.hview || "owners";
  const seg = `<div class="toolbar"><div class="seg">${[["owners", "Owners"], ["records", "Records"], ["h2h", "Head to Head"]].map(([k, l]) => `<button class="${S.hview === k ? "on" : ""}" onclick="S.hview='${k}';history()">${l}</button>`).join("")}</div></div>`;
  const body = { owners: histOwners, records: histRecords, h2h: histH2H }[S.hview](H, owners);
  $("#view").innerHTML = `<h1>All-Time</h1><div class="sub">${owners.length} owners across ${H.owners.flatMap((o) => o.seasons).map((s) => s.season).filter((v, i, a) => a.indexOf(v) === i).length} seasons</div>${seg}${body}`;
  markSortable($("#view"), ["Finish by Season"]);
}

function histOwners(H, owners) {
  const seasons = [...new Set(owners.flatMap((o) => o.seasons.map((s) => s.season)))].sort();
  const cell = (x) => !x ? `<td class="fin"></td>` : x.champion ? `<td class="fin champ" title="${x.season}: champion">1</td>`
    : `<td class="fin ${(x.final_rank || x.seed) <= 3 ? "podium" : ""}" title="${x.season}: ${esc(x.team)}">${x.final_rank || x.seed}</td>`;
  return `<div class="card tbl-wrap"><table class="sortable">
    <tr><th class="l">Owner</th><th>Titles</th><th>Win %</th><th>Cat %</th><th class="l">Finish by Season</th></tr>
    ${owners.map((o) => { const g = o.w + o.l + o.t, c = o.cw + o.cl + o.ct;
      return `<tr><td class="l"><b>${esc(o.name)}</b><span class="sub">${o.seasons.length} season${o.seasons.length === 1 ? "" : "s"} · ${o.w}-${o.l}-${o.t}</span></td>
      <td>${o.titles || ""}</td><td>${((o.w + o.t / 2) / g * 100).toFixed(1)}</td><td>${((o.cw + o.ct / 2) / c * 100).toFixed(1)}</td>
      <td class="l"><table class="strip"><tr>${seasons.map((s) => cell(o.seasons.find((y) => y.season === s))).join("")}</tr></table></td></tr>`; }).join("")}
    <tr class="nosort"><td></td><td></td><td></td><td></td><td class="l"><table class="strip"><tr>${seasons.map((s) => `<td class="fin yr">${String(s).slice(2)}</td>`).join("")}</tr></table></td></tr>
  </table></div><div class="sub" style="margin-top:6px">Finish strip: final place each season. Filled = champion, tinted = top three.</div>`;
}

function histRecords(H) {
  const ties = Object.values(H.tied_cats).reduce((a, b) => a + b, 0);
  const card = (r) => `<div class="card rec${r.new ? " new" : ""}">${r.new ? '<span class="newtag">New this season</span>' : ""}<div class="rt">${esc(r.title)}</div><div class="rv">${esc(r.value)}</div>
    <div class="rw"><b>${esc(r.who)}</b>${r.team ? ` <span class="sub">${esc(r.team)}</span>` : ""}</div>
    <div class="sub">${esc(r.when)}${r.vs ? ` vs ${esc(r.vs)}` : ""}</div><div class="sub rb">${esc(r.blurb)}</div></div>`;
  const group = (g, title, note) => { const rs = (S.records?.records || []).filter((r) => r.group === g); return rs.length ? `<h2>${title}</h2><div class="sub">${note}</div><div class="grid recs">${rs.map(card).join("")}</div>` : ""; };
  return group("fame", "Hall of Fame", "Single-week records skip All-Star breaks and two-week finals.")
    + group("shame", "Hall of Shame", "Everything the league would rather forget.")
    + group("fun", "Strange but True", "")
    + `<h2>Closest Category Finishes</h2>
    <div class="sub">Exact ties are excluded. They have happened ${ties} times, most often in ${Object.entries(H.tied_cats).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([k, v]) => `${k} (${v})`).join(", ")}.</div>
    <div class="card tbl-wrap" style="margin-top:8px"><table class="sortable"><tr><th class="l">When</th><th class="l">Matchup</th><th>Cat</th><th>Final</th></tr>
      ${H.closest_cats.slice(0, 8).map((c) => `<tr><td class="l">${c.season} wk ${c.mp}</td><td class="l">${esc(c.home)} vs ${esc(c.away)}</td><td>${c.cat}</td><td>${fmt(c.hv, c.cid)} – ${fmt(c.av, c.cid)}</td></tr>`).join("")}</table></div>
    <h2>9-0 Sweeps</h2>
    <div class="card tbl-wrap"><table><tr><th class="l">When</th><th class="l">Winner</th><th class="l">Victim</th></tr>
      ${H.sweeps.slice(-8).reverse().map((s) => `<tr><td class="l">${s.season} wk ${s.mp}</td><td class="l">${esc(s.winner)}</td><td class="l">${esc(s.loser)}</td></tr>`).join("") || '<tr><td class="l" colspan="3">None yet</td></tr>'}</table></div>`;
}

function histH2H(H, owners) {
  const me = S.h2hOwner || owners[0].owner;
  const rows = owners.filter((o) => o.owner !== me).map((o) => { const r = H.h2h[me]?.[o.owner]; return r ? { o, w: r[0], l: r[1], t: r[2] } : null; }).filter(Boolean)
    .sort((a, b) => (b.w - b.l) - (a.w - a.l));
  const mx = Math.max(...rows.map((r) => r.w + r.l + r.t), 1);
  return `<div class="toolbar"><span class="sub">Record for</span><select onchange="S.h2hOwner=this.value;history()">${owners.map((o) => `<option value="${o.owner}" ${o.owner === me ? "selected" : ""}>${esc(o.name)}</option>`).join("")}</select></div>
    <div class="card">${rows.map((r) => { const n = r.w + r.l + r.t; return `<div class="h2h"><span class="nm">${esc(r.o.name)}</span>
      <span class="bar" style="width:${n / mx * 100}%"><i class="w" style="flex:${r.w}"></i><i class="t" style="flex:${r.t}"></i><i class="l" style="flex:${r.l}"></i></span>
      <span class="rec ${r.w > r.l ? "pos" : r.w < r.l ? "neg" : ""}">${r.w}-${r.l}${r.t ? `-${r.t}` : ""}</span></div>`; }).join("")}</div>
    <div class="sub" style="margin-top:6px">Matchup record against each owner, all seasons including playoffs. Cobalt = wins, grey = losses.</div>`;
}
TABS.history = history;
window.history_ = history;
