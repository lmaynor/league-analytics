/* Trade Analyzer: 9-category trade simulation, package comparison, and rank shift modeling */
const CAT_IDS = [0, 6, 3, 2, 1, 17, 19, 20, 11];
const CAT_LABELS = { 0: "PTS", 6: "REB", 3: "AST", 2: "STL", 1: "BLK", 17: "3PM", 19: "FG%", 20: "FT%", 11: "TO" };
const STAT_KEYS = { 0: "pts", 6: "reb", 3: "ast", 2: "stl", 1: "blk", 17: "tpm", 11: "to" };
const GP_WEEK = 3.25;  // typical weekly games per starter

function initTradeState(teams) {
  if (!S.trade) S.trade = {};
  const ids = teams.map((t) => t.id);
  if (!S.trade.teamA || !ids.includes(S.trade.teamA)) S.trade.teamA = ids[0];
  if (!S.trade.teamB || !ids.includes(S.trade.teamB) || S.trade.teamB === S.trade.teamA) {
    S.trade.teamB = ids.find((id) => id !== S.trade.teamA) || ids[1];
  }
  if (!S.trade.sendA) S.trade.sendA = new Set();
  if (!S.trade.sendB) S.trade.sendB = new Set();
}

function trades() {
  const d = D();
  const teams = [...d.standings].sort((a, b) => a.name.localeCompare(b.name));
  initTradeState(teams);
  const rosters = S.rosters || {};

  const tA = d.teams[S.trade.teamA] || teams[0];
  const tB = d.teams[S.trade.teamB] || teams[1];
  const rA = rosters[String(tA.id)] || [];
  const rB = rosters[String(tB.id)] || [];

  const teamSelect = (id, cur, otherId, onchange) => `
    <select onchange="${onchange}(+this.value)">
      ${teams.map((t) => `<option value="${t.id}" ${t.id === cur ? "selected" : ""} ${t.id === otherId ? "disabled" : ""}>${esc(t.name)} (${esc(t.owner_name)})</option>`).join("")}
    </select>`;

  const playerRow = (p, teamKey) => {
    const isChecked = S.trade[teamKey].has(p.id);
    return `<label class="tr-player${isChecked ? " on" : ""}">
      <input type="checkbox" ${isChecked ? "checked" : ""} onchange="toggleTradePlayer('${teamKey}', ${p.id})">
      <span class="tr-pos">${p.pos || "UTIL"}</span>
      <span class="tr-name"><b>${esc(p.name)}</b>${p.inj ? ` <span class="inj">${p.inj}</span>` : ""}</span>
      <span class="tr-stat">${p.pts.toFixed(0)}p / ${p.reb.toFixed(0)}r / ${p.ast.toFixed(0)}a</span>
    </label>`;
  };

  const selA = rA.filter((p) => S.trade.sendA.has(p.id));
  const selB = rB.filter((p) => S.trade.sendB.has(p.id));
  const hasSelection = selA.length > 0 || selB.length > 0;

  panel().innerHTML = `<h1>Trade Analyzer</h1>
    <div class="sub">Simulate a head-to-head trade between two teams. Evaluates 9-category weekly stat deltas and league rank shifts.</div>
    <div class="trade-cols" style="margin-top:14px">
      <div class="card tr-side">
        <div class="tr-head">
          <label class="tr-label">Team A ${teamSelect(tA.id, tA.id, tB.id, "setTradeA")}</label>
          <div class="sub">${selA.length} player${selA.length === 1 ? "" : "s"} selected</div>
        </div>
        <div class="tr-list">${rA.length ? rA.map((p) => playerRow(p, "sendA")).join("") : '<div class="sub" style="padding:12px">No roster data available.</div>'}</div>
      </div>
      <div class="card tr-side">
        <div class="tr-head">
          <label class="tr-label">Team B ${teamSelect(tB.id, tB.id, tA.id, "setTradeB")}</label>
          <div class="sub">${selB.length} player${selB.length === 1 ? "" : "s"} selected</div>
        </div>
        <div class="tr-list">${rB.length ? rB.map((p) => playerRow(p, "sendB")).join("") : '<div class="sub" style="padding:12px">No roster data available.</div>'}</div>
      </div>
    </div>
    ${hasSelection ? renderTradeImpact(tA, tB, selA, selB, d) : `
      <div class="card empty" style="margin-top:14px">
        <h3>Select players above</h3>
        <p class="sub">Check the players being traded to calculate net category movement and projected league standings shift.</p>
      </div>`}`;
}

window.setTradeA = (id) => {
  S.trade.teamA = id;
  S.trade.sendA.clear();
  trades();
};

window.setTradeB = (id) => {
  S.trade.teamB = id;
  S.trade.sendB.clear();
  trades();
};

window.toggleTradePlayer = (teamKey, pid) => {
  if (S.trade[teamKey].has(pid)) S.trade[teamKey].delete(pid);
  else S.trade[teamKey].add(pid);
  trades();
};

function renderTradeImpact(tA, tB, selA, selB, d) {
  // Compute deltas for Team A (receiving selB, giving selA)
  // Team B is the exact inverse
  const deltasA = {};
  for (const cid of [0, 6, 3, 2, 1, 17, 11]) {
    const key = STAT_KEYS[cid];
    const incoming = selB.reduce((sum, p) => sum + (p[key] || 0), 0);
    const outgoing = selA.reduce((sum, p) => sum + (p[key] || 0), 0);
    deltasA[cid] = (incoming - outgoing) * GP_WEEK;
  }

  // Percentage stats estimation (FG%, FT%)
  const sumStat = (list, key) => list.reduce((sum, p) => sum + (p[key] || 0), 0);
  const fgmA = (sumStat(selB, "fgm") - sumStat(selA, "fgm")) * GP_WEEK;
  const fgaA = (sumStat(selB, "fga") - sumStat(selA, "fga")) * GP_WEEK;
  const ftmA = (sumStat(selB, "ftm") - sumStat(selA, "ftm")) * GP_WEEK;
  const ftaA = (sumStat(selB, "fta") - sumStat(selA, "fta")) * GP_WEEK;

  const currentA = d.standings.find((t) => t.id === tA.id);
  const currentB = d.standings.find((t) => t.id === tB.id);

  // Derive baseline weekly attempts from current strength:
  // e.g. PTS ~ 2*FGM + 3PM + FTM
  const baseFgaA = Math.max(100, (currentA?.strength?.[0] || 300) * 0.95);
  const baseFgmA = baseFgaA * (currentA?.strength?.[19] || 0.46);
  const newFgPctA = (baseFgmA + fgmA) / Math.max(1, baseFgaA + fgaA);
  deltasA[19] = newFgPctA - (currentA?.strength?.[19] || 0.46);

  const baseFtaA = Math.max(50, (currentA?.strength?.[0] || 300) * 0.3);
  const baseFtmA = baseFtaA * (currentA?.strength?.[20] || 0.77);
  const newFtPctA = (baseFtmA + ftmA) / Math.max(1, baseFtaA + ftaA);
  deltasA[20] = newFtPctA - (currentA?.strength?.[20] || 0.77);

  // Calculate new ranks for each team across all 10 teams
  const rankShift = (cid, teamId, delta) => {
    const isRev = cid === 11;
    const scores = d.standings.map((t) => {
      let val = t.strength?.[cid] || 0;
      if (t.id === teamId) val += delta;
      return { id: t.id, val };
    });
    scores.sort((a, b) => (isRev ? a.val - b.val : b.val - a.val));
    const newRank = scores.findIndex((s) => s.id === teamId) + 1;
    const oldRank = (d.standings.find((t) => t.id === teamId)?.cat_rank?.[cid]?.rank) || 5;
    return { oldRank, newRank, shift: oldRank - newRank }; // positive shift = moved up
  };

  const fmtDelta = (cid, v) => {
    if (cid === 19 || cid === 20) {
      const s = (v * 100).toFixed(1);
      return v > 0 ? `+${s}%` : `${s}%`;
    }
    const s = v.toFixed(1);
    return v > 0 ? `+${s}` : s;
  };

  const rows = CAT_IDS.map((cid) => {
    const dA = deltasA[cid];
    const dB = -dA;
    const rA = rankShift(cid, tA.id, dA);
    const rB = rankShift(cid, tB.id, dB);
    const isRev = cid === 11;
    const goodA = isRev ? dA < 0 : dA > 0;
    const goodB = isRev ? dB < 0 : dB > 0;
    const shiftClass = (s) => (s > 0 ? "pos" : s < 0 ? "neg" : "");
    const shiftTxt = (r) => (r.shift === 0 ? `#${r.newRank}` : `#${r.oldRank} → #${r.newRank} (${r.shift > 0 ? `+${r.shift}` : r.shift})`);

    return `<tr>
      <td class="l"><b>${CAT_LABELS[cid]}</b></td>
      <td class="${goodA ? "pos" : dA === 0 ? "" : "neg"}">${fmtDelta(cid, dA)}</td>
      <td class="${shiftClass(rA.shift)}">${shiftTxt(rA)}</td>
      <td class="${goodB ? "pos" : dB === 0 ? "" : "neg"}">${fmtDelta(cid, dB)}</td>
      <td class="${shiftClass(rB.shift)}">${shiftTxt(rB)}</td>
    </tr>`;
  }).join("");

  const summaryPill = (txt, isGood) => `<span class="pill" style="${isGood ? "background:var(--color-accent-wash);color:var(--color-accent-deep)" : ""}">${esc(txt)}</span>`;
  const gainsA = CAT_IDS.filter((cid) => (cid === 11 ? deltasA[cid] < -0.5 : deltasA[cid] > 0.5)).map((c) => CAT_LABELS[c]);
  const lossesA = CAT_IDS.filter((cid) => (cid === 11 ? deltasA[cid] > 0.5 : deltasA[cid] < -0.5)).map((c) => CAT_LABELS[c]);

  return `
    <h2 style="margin-top:24px">Projected 9-Category Trade Impact</h2>
    <div class="sub">Estimated weekly stat deltas and projected category rank movements based on a 3.25 game/week starter baseline.</div>
    <div class="card tbl-wrap" style="margin-top:10px">
      <table class="sortable">
        <tr>
          <th class="l">Category</th>
          <th>${esc(tA.name)} Δ</th>
          <th>${esc(tA.name)} Rank</th>
          <th>${esc(tB.name)} Δ</th>
          <th>${esc(tB.name)} Rank</th>
        </tr>
        ${rows}
      </table>
    </div>
    <div class="trade-cols" style="margin-top:14px">
      <div class="card">
        <h4>${esc(tA.name)} Strategy Summary</h4>
        <div style="margin-top:6px;font-size:13px"><b>Strengthens:</b> ${gainsA.length ? gainsA.map((g) => summaryPill(g, true)).join(" ") : "None"}</div>
        <div style="margin-top:6px;font-size:13px"><b>Sacrifices:</b> ${lossesA.length ? lossesA.map((l) => summaryPill(l, false)).join(" ") : "None"}</div>
      </div>
      <div class="card">
        <h4>${esc(tB.name)} Strategy Summary</h4>
        <div style="margin-top:6px;font-size:13px"><b>Strengthens:</b> ${lossesA.length ? lossesA.map((l) => summaryPill(l, true)).join(" ") : "None"}</div>
        <div style="margin-top:6px;font-size:13px"><b>Sacrifices:</b> ${gainsA.length ? gainsA.map((g) => summaryPill(g, false)).join(" ") : "None"}</div>
      </div>
    </div>`;
}
