/* Trade Machine: 15-tier letter grading, probabilistic 9-cat simulation,
   replacement-level roster modeling, deterministic classifications, and trade receipts. */

const CAT_IDS = [0, 6, 3, 2, 1, 17, 19, 20, 11];
const CAT_LABELS = { 0: "PTS", 6: "REB", 3: "AST", 2: "STL", 1: "BLK", 17: "3PM", 19: "FG%", 20: "FT%", 11: "TO" };
const STAT_KEYS = { 0: "pts", 6: "reb", 3: "ast", 2: "stl", 1: "blk", 17: "tpm", 11: "to" };
const GP_WEEK = 3.25;

const GRADES = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F+", "F", "F-"];

const GRADE_THRESHOLDS = [
  ["A+", 0.80],
  ["A",  0.60],
  ["A-", 0.45],
  ["B+", 0.32],
  ["B",  0.20],
  ["B-", 0.10],
  ["C+", 0.04],
  ["C", -0.03],
  ["C-", -0.09],
  ["D+", -0.19],
  ["D", -0.31],
  ["D-", -0.44],
  ["F+", -0.59],
  ["F", -0.79],
  ["F-", -Infinity]
];

const GRADE_DESCRIPTIONS = {
  "A+": "Franchise-altering win. Massive projected improvement across multiple categories.",
  "A":  "Excellent trade. Substantial, decisive advantage for this manager.",
  "A-": "Strong win. Notable edge with minimal meaningful downside.",
  "B+": "Very good deal. Meaningful improvement in category fit and weekly win rate.",
  "B":  "Good deal. Clear positive outcome and positive roster trajectory.",
  "B-": "Slight win. Modest net improvement with manageable trade-offs.",
  "C+": "Solid deal. Defensible value where both sides find reasonable utility.",
  "C":  "Fair trade. Balanced value or near-zero marginal change in outlook.",
  "C-": "Slight loss. Surrendered modest expected value, but damage is limited.",
  "D+": "Disappointing deal. The roster outlook deteriorates with questionable returns.",
  "D":  "Bad trade. Clear negative impact on weekly category competitiveness.",
  "D-": "Major miscalculation. Substantial decline across core category strengths.",
  "F+": "Near-disaster. Severe value destruction, saved only by residual depth.",
  "F":  "Disasterclass. Devastating loss of category equity with few compensating benefits.",
  "F-": "All-time blunder candidate. Lopsided destruction of franchise championship equity."
};

const CAT_SIGMAS = {
  0: 75.0, 6: 30.0, 3: 28.0, 2: 9.0, 1: 8.5,
  17: 16.0, 19: 0.055, 20: 0.085, 11: 12.5
};

const DEFAULT_REPLACEMENT = {
  pts: 8.5, reb: 5.2, ast: 2.4, stl: 0.85, blk: 0.8,
  tpm: 0.7, fg_pct: 0.465, ft_pct: 0.680, to: 1.5,
  fgm: 3.3, fga: 7.1, ftm: 1.2, fta: 1.8
};

function scoreToGrade(score) {
  for (const [grade, thresh] of GRADE_THRESHOLDS) {
    if (score >= thresh) return grade;
  }
  return "F-";
}

function gradeClass(grade) {
  if (!grade) return "grade-c";
  const letter = grade.charAt(0).toLowerCase();
  return `grade-${letter}`;
}

// Polyfill Math.erf if needed
if (!Math.erf) {
  Math.erf = function(x) {
    const sign = x >= 0 ? 1 : -1;
    x = Math.abs(x);
    const a1 = 0.254829592, a2 = -0.284496736, a3 = 1.421413741, a4 = -1.453152027, a5 = 1.061405429, p = 0.3275911;
    const t = 1.0 / (1.0 + p * x);
    const y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-x * x);
    return sign * y;
  };
}

function normCdf(z) {
  return 0.5 * (1.0 + Math.erf(z / Math.SQRT2));
}

function getReplacementPlayer(rosters) {
  if (!rosters) return DEFAULT_REPLACEMENT;
  const bottom = [];
  for (const teamPlayers of Object.values(rosters)) {
    if (teamPlayers && teamPlayers.length) {
      const sorted = [...teamPlayers].sort((a, b) => (a.pts || 0) - (b.pts || 0));
      bottom.push(...sorted.slice(0, 3));
    }
  }
  if (bottom.length < 10) return DEFAULT_REPLACEMENT;
  const rep = {};
  for (const k of ["pts", "reb", "ast", "stl", "blk", "tpm", "fg_pct", "ft_pct", "to", "fgm", "fga", "ftm", "fta"]) {
    rep[k] = +(bottom.reduce((sum, p) => sum + (p[k] || 0), 0) / bottom.length).toFixed(3);
  }
  return rep;
}

function simulateExpectedCatsWon(teamId, teamStrength, allTeams) {
  const opponents = allTeams.filter((t) => t.id !== teamId);
  if (!opponents.length) return 4.5;
  let total = 0.0;
  for (const opp of opponents) {
    const oppStr = opp.strength || {};
    for (const cid of CAT_IDS) {
      const vT = teamStrength[cid] || 0;
      const vO = oppStr[cid] || 0;
      const diff = cid === 11 ? (vO - vT) : (vT - vO);
      const sigma = CAT_SIGMAS[cid] || 20.0;
      total += normCdf(diff / sigma);
    }
  }
  return +(total / opponents.length).toFixed(3);
}

function initTradeState(teams) {
  if (!S.trade) S.trade = {};
  const ids = teams.map((t) => t.id);
  if (!S.trade.teamA || !ids.includes(S.trade.teamA)) S.trade.teamA = ids[0];
  if (!S.trade.teamB || !ids.includes(S.trade.teamB) || S.trade.teamB === S.trade.teamA) {
    S.trade.teamB = ids.find((id) => id !== S.trade.teamA) || ids[1];
  }
  if (!S.trade.sendA) S.trade.sendA = new Set();
  if (!S.trade.sendB) S.trade.sendB = new Set();

  if (!S.trade.initialized && S.trades?.completed?.length) {
    const trId = S.initQuery?.get("trade");
    if (trId) {
      const match = S.trades.completed.find((t) => t.id === trId);
      if (match) {
        S.trade.teamA = match.team_a.id;
        S.trade.teamB = match.team_b.id;
        S.trade.sendA = new Set(match.players_b.map((p) => p.id));
        S.trade.sendB = new Set(match.players_a.map((p) => p.id));
      }
    }
    S.trade.initialized = true;
  }
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
      <span class="tr-stat">${(p.pts || 0).toFixed(0)}p · ${(p.reb || 0).toFixed(0)}r · ${(p.ast || 0).toFixed(0)}a</span>
    </label>`;
  };

  const selA = rA.filter((p) => S.trade.sendA.has(p.id));
  const selB = rB.filter((p) => S.trade.sendB.has(p.id));
  const hasSelection = selA.length > 0 || selB.length > 0;

  panel().innerHTML = `<h1>Trade Machine</h1>
    <div class="sub">15-tier letter grades, probabilistic 9-cat simulation, replacement-level waiver math, and shareable trade receipts.</div>
    <div class="trade-cols" style="margin-top:14px">
      <div class="card tr-side">
        <div class="tr-head">
          <label class="tr-label">Team A ${teamSelect(tA.id, tA.id, tB.id, "setTradeA")}</label>
          <span class="pill">${selA.length} selected</span>
        </div>
        <div class="tr-list">${rA.length ? rA.map((p) => playerRow(p, "sendA")).join("") : '<div class="sub" style="padding:12px">No roster data available.</div>'}</div>
      </div>
      <div class="card tr-side">
        <div class="tr-head">
          <label class="tr-label">Team B ${teamSelect(tB.id, tB.id, tA.id, "setTradeB")}</label>
          <span class="pill">${selB.length} selected</span>
        </div>
        <div class="tr-list">${rB.length ? rB.map((p) => playerRow(p, "sendB")).join("") : '<div class="sub" style="padding:12px">No roster data available.</div>'}</div>
      </div>
    </div>
    ${hasSelection ? renderTradeImpact(tA, tB, selA, selB, d, rosters) : `
      <div class="card empty" style="margin-top:14px">
        <h3>Select Players to Simulate</h3>
        <p class="sub">Choose players on one or both sides to simulate marginal category shifts, letter grades, and deterministic trade verdicts.</p>
      </div>`}
    <h2 style="margin-top:32px">Completed Trades & Trade Receipts</h2>
    ${renderCompletedTradesList()}`;
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

window.loadTradeInMachine = (teamAId, teamBId, pAIds, pBIds) => {
  if (!S.trade) S.trade = {};
  S.trade.teamA = teamAId;
  S.trade.teamB = teamBId;
  // Team A sent the players received by Team B
  S.trade.sendA = new Set(pBIds || []);
  // Team B sent the players received by Team A
  S.trade.sendB = new Set(pAIds || []);
  setSub("teams", "trades");
  go("teams");
};

function renderTradeImpact(tA, tB, selA, selB, d, rosters) {
  const rep = getReplacementPlayer(rosters);
  const nA = selA.length;
  const nB = selB.length;
  const vacA = nA - nB; // Positive: A freed spots and gains replacement waiver production
  const vacB = nB - nA; // Positive: B freed spots

  const deltasA = {};
  const deltasB = {};

  for (const cid of [0, 6, 3, 2, 1, 17, 11]) {
    const key = STAT_KEYS[cid];
    let inValA = selB.reduce((sum, p) => sum + (p[key] || 0), 0);
    let outValA = selA.reduce((sum, p) => sum + (p[key] || 0), 0);

    if (vacA > 0) inValA += vacA * (rep[key] || 0);
    else if (vacA < 0) outValA += Math.abs(vacA) * (rep[key] || 0);

    deltasA[cid] = (inValA - outValA) * GP_WEEK;
    deltasB[cid] = -deltasA[cid];
  }

  // Volume-weighted percentages
  const sumStat = (list, key) => list.reduce((sum, p) => sum + (p[key] || 0), 0);

  let fgmInA = sumStat(selB, "fgm");
  let fgaInA = sumStat(selB, "fga");
  let fgmOutA = sumStat(selA, "fgm");
  let fgaOutA = sumStat(selA, "fga");

  let ftmInA = sumStat(selB, "ftm");
  let ftaInA = sumStat(selB, "fta");
  let ftmOutA = sumStat(selA, "ftm");
  let ftaOutA = sumStat(selA, "fta");

  if (vacA > 0) {
    fgmInA += vacA * rep.fgm; fgaInA += vacA * rep.fga;
    ftmInA += vacA * rep.ftm; ftaInA += vacA * rep.fta;
  } else if (vacA < 0) {
    fgmOutA += Math.abs(vacA) * rep.fgm; fgaOutA += Math.abs(vacA) * rep.fga;
    ftmOutA += Math.abs(vacA) * rep.ftm; ftaOutA += Math.abs(vacA) * rep.fta;
  }

  const netFgmA = (fgmInA - fgmOutA) * GP_WEEK;
  const netFgaA = (fgaInA - fgaOutA) * GP_WEEK;
  const baseFga = 300.0;
  const baseFgm = baseFga * 0.465;
  deltasA[19] = (baseFgm + netFgmA) / Math.max(1.0, baseFga + netFgaA) - 0.465;
  deltasB[19] = -deltasA[19];

  const netFtmA = (ftmInA - ftmOutA) * GP_WEEK;
  const netFtaA = (ftaInA - ftaOutA) * GP_WEEK;
  const baseFta = 90.0;
  const baseFtm = baseFta * 0.770;
  deltasA[20] = (baseFtm + netFtmA) / Math.max(1.0, baseFta + netFtaA) - 0.770;
  deltasB[20] = -deltasA[20];

  // Opponents simulation
  const allTeams = d.standings.map((t) => ({
    id: t.id,
    name: t.name,
    strength: t.strength || {}
  }));

  const currentA = d.standings.find((t) => t.id === tA.id);
  const currentB = d.standings.find((t) => t.id === tB.id);

  const baseStrA = { ...(currentA?.strength || {}) };
  const baseStrB = { ...(currentB?.strength || {}) };
  const postStrA = { ...baseStrA };
  const postStrB = { ...baseStrB };

  for (const cid of CAT_IDS) {
    postStrA[cid] = (baseStrA[cid] || 0) + deltasA[cid];
    postStrB[cid] = (baseStrB[cid] || 0) + deltasB[cid];
  }

  const xPreA = simulateExpectedCatsWon(tA.id, baseStrA, allTeams);
  const xPostA = simulateExpectedCatsWon(tA.id, postStrA, allTeams);
  const deltaXA = +(xPostA - xPreA).toFixed(3);

  const xPreB = simulateExpectedCatsWon(tB.id, baseStrB, allTeams);
  const xPostB = simulateExpectedCatsWon(tB.id, postStrB, allTeams);
  const deltaXB = +(xPostB - xPreB).toFixed(3);

  const gradeA = scoreToGrade(deltaXA);
  const gradeB = scoreToGrade(deltaXB);

  // Determine overall outcome
  const diff = +(deltaXA - deltaXB).toFixed(3);
  const absDiff = Math.abs(diff);
  let outcome = "fair_trade";
  let outcomeLabel = "Fair Trade";
  let winner = null;
  let marginStr = "Even balance (within 0.1 cats/wk)";
  let verdictReason = "A balanced exchange with negligible net shift across weekly matchups.";

  if (deltaXA >= 0.12 && deltaXB >= 0.12) {
    outcome = "win_win";
    outcomeLabel = "Win-Win";
    marginStr = `Mutual upgrade (+${deltaXA.toFixed(2)} / +${deltaXB.toFixed(2)} cats/wk)`;
    verdictReason = "Both front offices addressed complementary category needs and improved expected weekly win rates.";
  } else if (deltaXA <= -0.12 && deltaXB <= -0.12) {
    outcome = "lose_lose";
    outcomeLabel = "Lose-Lose";
    marginStr = `Mutual regression (${deltaXA.toFixed(2)} / ${deltaXB.toFixed(2)} cats/wk)`;
    verdictReason = "Both rosters surrendered critical strengths without receiving adequate compensating value.";
  } else if (absDiff >= 0.40) {
    outcome = "clear_win";
    outcomeLabel = "Clear Win";
    winner = deltaXA > deltaXB ? tA : tB;
    marginStr = `+${absDiff.toFixed(2)} cats/wk advantage`;
    verdictReason = `${winner.name} captured decisive category equity while limiting return concessions.`;
  } else if (absDiff >= 0.14) {
    outcome = "slight_edge";
    outcomeLabel = "Slight Edge";
    winner = deltaXA > deltaXB ? tA : tB;
    marginStr = `+${absDiff.toFixed(2)} cats/wk lean`;
    verdictReason = `${winner.name} extracted a modest category edge in an otherwise competitive exchange.`;
  } else if (absDiff < 0.04) {
    outcome = "too_close_to_call";
    outcomeLabel = "Too Close to Call";
    marginStr = "Dead heat (split advantage)";
    verdictReason = "Marginal category shifts are too evenly matched to declare a definitive winner.";
  }

  // Classification heuristics
  let clsName = "Clean Business";
  let clsHeadline = "Fair and square: an equitable exchange with negligible net shift.";
  let clsRoast = "As balanced as a laboratory scale. Neither manager was fleeced, neither manager gloats, and the standings will barely flinch.";
  const clsTags = [];

  const allPlayers = [...selA, ...selB];
  const hasStar = allPlayers.some((p) => (p.pts || 0) >= 24 || ((p.pts || 0) >= 20 && (p.ast || 0) >= 6));
  const hasInj = allPlayers.some((p) => p.inj);
  const isImbalanced = Math.abs(nA - nB) > 0;

  if (outcome === "clear_win" && absDiff >= 0.70) {
    clsName = "Highway Robbery";
    clsHeadline = `Highway robbery: ${winner.name} extracted a lopsided heist.`;
    clsRoast = `The league office has questions, the commissioner is sweating, and the group chat is drafting grievance petitions.`;
    clsTags.push("Lopsided", "Fleece Alert");
  } else if (allPlayers.length >= 4 && hasStar) {
    clsName = "The Group Chat Is Going to Be Loud";
    clsHeadline = "Earthquake on the wire: the group chat is going to be loud.";
    clsRoast = "Mute your notifications immediately. A franchise-altering blockbuster just landed, and the hot takes will take days to cool off.";
    clsTags.push("Blockbuster", "Mega-Deal");
  } else if (outcome === "win_win") {
    clsName = "Win-Win";
    clsHeadline = "Two front offices cooking: a rare mutually beneficial deal.";
    clsRoast = "No fleece, no panic. Both managers identified acute roster deficiencies and negotiated like seasoned basketball executives.";
    clsTags.push("Mutual Upgrade", "Roster Fit");
  } else if (isImbalanced && Math.abs(nA - nB) >= 1) {
    clsName = "The 2-for-1 Tax";
    clsHeadline = "Consolidation masterclass: quality traded for quantity.";
    clsRoast = "Never underestimate the roster-spot tax. Unlocking waiver flexibility and consolidating points of attack changes the math.";
    clsTags.push(`${Math.max(nA, nB)}-for-${Math.min(nA, nB)}`, "Depth Math");
  } else if (hasInj) {
    clsName = "Injury Roulette";
    clsHeadline = "The medical staff is sweating: high-stakes health gamble.";
    clsRoast = "Trading for active injury designations is fantasy parkour. If the joints hold up, it looks genius; if not, disasterclass.";
    clsTags.push("Injury Risk", "Volatility");
  } else if (outcome === "clear_win") {
    clsName = "Front Office Masterstroke";
    clsHeadline = `Front office masterstroke: ${winner.name} won the margins.`;
    clsRoast = `A clean, decisive negotiation win without triggering a league veto referendum.`;
    clsTags.push("Edge", "Decisive");
  }

  // Identify category gains / concessions
  const gainedCatsA = [];
  const lostCatsA = [];
  for (const cid of CAT_IDS) {
    const val = deltasA[cid];
    const isGood = cid === 11 ? val < 0 : val > 0;
    const thresh = (cid === 19 || cid === 20) ? 0.002 : 0.4;
    if (isGood && Math.abs(val) > thresh) gainedCatsA.push(CAT_LABELS[cid]);
    else if (!isGood && Math.abs(val) > thresh) lostCatsA.push(CAT_LABELS[cid]);
  }

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
    return { oldRank, newRank, shift: oldRank - newRank };
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
    const dB = deltasB[cid];
    const rA = rankShift(cid, tA.id, dA);
    const rB = rankShift(cid, tB.id, dB);
    const isRev = cid === 11;
    const goodA = isRev ? dA < 0 : dA > 0;
    const goodB = isRev ? dB < 0 : dB > 0;

    const rankPill = (r) => {
      if (r.shift === 0) return `<span class="rk-badge">#${r.newRank}</span>`;
      const up = r.shift > 0;
      return `<span class="rk-badge ${up ? "pos" : "neg"}">${up ? `▲` : `▼`} #${r.newRank}</span>`;
    };

    return `<div class="tr-cat-row">
      <div class="v-left">
        ${rankPill(rA)}
        <b class="${goodA ? "pos" : Math.abs(dA) < 0.0001 ? "" : "neg"}">${fmtDelta(cid, dA)}</b>
      </div>
      <div class="tr-cat-mid">
        <i class="tr-dot ${goodA ? "on" : ""}"></i>
        <span class="pill">${CAT_LABELS[cid]}</span>
        <i class="tr-dot ${goodB ? "on" : ""}"></i>
      </div>
      <div class="v-right">
        <b class="${goodB ? "pos" : Math.abs(dB) < 0.0001 ? "" : "neg"}">${fmtDelta(cid, dB)}</b>
        ${rankPill(rB)}
      </div>
    </div>`;
  }).join("");

  return `
    ${vacA !== 0 ? `
      <div class="receipt-waiver-notice" style="margin-top:14px">
        <span>ℹ️</span>
        <div>
          <b>${Math.max(nA, nB)}-for-${Math.min(nA, nB)} Deal Structure:</b>
          ${vacA > 0 ? `${esc(tA.name)} frees up ${vacA} roster spot${vacA > 1 ? "s" : ""} (adds waiver baseline: ${(rep.pts * vacA).toFixed(1)}p / ${(rep.reb * vacA).toFixed(1)}r). ${esc(tB.name)} absorbs drop cost.` : `${esc(tB.name)} frees up ${vacB} roster spot${vacB > 1 ? "s" : ""} (adds waiver baseline). ${esc(tA.name)} absorbs drop cost.`}
        </div>
      </div>` : ""}

    <div class="trade-receipt" style="margin-top:14px">
      <div class="receipt-top">
        <div class="receipt-meta">
          <span class="outcome-pill ${outcome}">${esc(outcomeLabel)}</span>
          <b>${esc(clsName)}</b>
          ${clsTags.map((tag) => `<span class="pill">${esc(tag)}</span>`).join(" ")}
        </div>
        <span class="pill" style="font-weight:600;color:var(--color-ink)">${marginStr}</span>
      </div>

      <div class="receipt-quote-box">
        <div class="receipt-headline">${esc(clsHeadline)}</div>
        <div class="receipt-roast">${esc(clsRoast)}</div>
      </div>

      <div class="receipt-sides">
        <div class="receipt-mgr-card">
          <div class="receipt-mgr-head">
            <div class="receipt-mgr-info">
              <span class="receipt-mgr-name">${esc(tA.name)}</span>
              <span class="receipt-mgr-owner">${esc(tA.owner_name || "")}</span>
            </div>
            <span class="grade-badge lg ${gradeClass(gradeA)}">${gradeA}</span>
          </div>
          <div style="font-size:12px;color:var(--muted);margin-top:2px">
            ${GRADE_DESCRIPTIONS[gradeA] || ""}
          </div>
          <div style="font-size:12px;color:var(--color-ink);display:flex;justify-content:space-between;flex-wrap:wrap;gap:4px;margin-top:4px">
            <span>Marginal Impact: <b>${deltaXA > 0 ? `+${deltaXA.toFixed(2)}` : deltaXA.toFixed(2)} cats/wk</b></span>
            <span>Confidence: <b>${hasInj ? "Medium" : "High"}</b></span>
          </div>
          <div style="font-size:11.5px;color:var(--color-ink-2);margin-top:4px">
            <b>Key Gains:</b> ${gainedCatsA.length ? gainedCatsA.slice(0, 3).join(", ") : "None notable"}
          </div>
          <div style="font-size:11.5px;color:var(--muted)">
            <b>Concessions:</b> ${lostCatsA.length ? lostCatsA.slice(0, 3).join(", ") : "None notable"}
          </div>
        </div>

        <div class="receipt-mgr-card">
          <div class="receipt-mgr-head">
            <div class="receipt-mgr-info">
              <span class="receipt-mgr-name">${esc(tB.name)}</span>
              <span class="receipt-mgr-owner">${esc(tB.owner_name || "")}</span>
            </div>
            <span class="grade-badge lg ${gradeClass(gradeB)}">${gradeB}</span>
          </div>
          <div style="font-size:12px;color:var(--muted);margin-top:2px">
            ${GRADE_DESCRIPTIONS[gradeB] || ""}
          </div>
          <div style="font-size:12px;color:var(--color-ink);display:flex;justify-content:space-between;flex-wrap:wrap;gap:4px;margin-top:4px">
            <span>Marginal Impact: <b>${deltaXB > 0 ? `+${deltaXB.toFixed(2)}` : deltaXB.toFixed(2)} cats/wk</b></span>
            <span>Confidence: <b>${hasInj ? "Medium" : "High"}</b></span>
          </div>
          <div style="font-size:11.5px;color:var(--color-ink-2);margin-top:4px">
            <b>Key Gains:</b> ${lostCatsA.length ? lostCatsA.slice(0, 3).join(", ") : "None notable"}
          </div>
          <div style="font-size:11.5px;color:var(--muted)">
            <b>Concessions:</b> ${gainedCatsA.length ? gainedCatsA.slice(0, 3).join(", ") : "None notable"}
          </div>
        </div>
      </div>
    </div>

    <div class="tr-cats">${rows}</div>`;
}

function renderCompletedTradesList() {
  const completed = S.trades?.completed || [];
  if (!completed.length) {
    return `<div class="card empty" style="margin-top:10px">
      <h3>No Executed Trades Yet</h3>
      <p class="sub">Completed deals in this league will automatically appear here with full letter grades and roasted trade receipts.</p>
    </div>`;
  }

  return completed.map((t) => {
    const v = t.verdict || {};
    const cls = v.classification || {};
    const ga = t.grade_a || {};
    const gb = t.grade_b || {};
    const pA = t.players_a.map((p) => p.name).join(", ");
    const pB = t.players_b.map((p) => p.name).join(", ");
    const pAIds = JSON.stringify(t.players_a.map((p) => p.id));
    const pBIds = JSON.stringify(t.players_b.map((p) => p.id));
    const outcome = v.outcome || "fair_trade";
    const outcomeLabel = v.outcome_label || "Fair Trade";

    const tagsHtml = (cls.tags || []).map((tag) => `<span class="pill">${esc(tag)}</span>`).join(" ");

    return `<div class="trade-receipt">
      <div class="receipt-top">
        <div class="receipt-meta">
          <span class="outcome-pill ${outcome}">${esc(outcomeLabel)}</span>
          <span class="pill">Week ${t.mp}</span>
          <b>${esc(cls.name || "Trade Receipt")}</b>
          ${tagsHtml}
        </div>
        <button class="pill" style="cursor:pointer;padding:4px 10px;font-size:12px;background:var(--color-key-face);border:1px solid var(--color-rule-2);color:var(--text)" onclick='loadTradeInMachine(${t.team_a.id}, ${t.team_b.id}, ${pAIds}, ${pBIds})'>Load in Simulator →</button>
      </div>

      ${cls.roast ? `
        <div class="receipt-quote-box">
          <div class="receipt-headline">${esc(cls.headline || "")}</div>
          <div class="receipt-roast">${esc(cls.roast)}</div>
        </div>` : ""}

      <div class="receipt-sides">
        <div class="receipt-mgr-card">
          <div class="receipt-mgr-head">
            <div class="receipt-mgr-info">
              <span class="receipt-mgr-name">${esc(t.team_a.name)}</span>
              <span class="receipt-mgr-owner">${esc(t.team_a.owner || "")}</span>
            </div>
            <span class="grade-badge ${gradeClass(ga.grade)}">${ga.grade || "C"}</span>
          </div>
          <div class="receipt-players-box">
            <b>Acquired:</b> ${esc(pA)}
          </div>
          <div style="font-size:12px;color:var(--muted);display:flex;justify-content:space-between;flex-wrap:wrap;gap:4px;margin-top:2px">
            <span>Weekly Net: <b>${ga.score !== undefined ? (ga.score > 0 ? `+${ga.score.toFixed(2)}` : ga.score.toFixed(2)) : "0.00"} cats/wk</b></span>
            <span>Confidence: <b>${ga.confidence || "High"}</b></span>
          </div>
          ${ga.fit_benefit ? `<div style="font-size:11.5px;color:var(--color-ink-2);margin-top:2px"><b>Fit:</b> ${esc(ga.fit_benefit)}</div>` : ""}
          ${ga.cost_risk ? `<div style="font-size:11.5px;color:var(--muted)"><b>Risk:</b> ${esc(ga.cost_risk)}</div>` : ""}
        </div>

        <div class="receipt-mgr-card">
          <div class="receipt-mgr-head">
            <div class="receipt-mgr-info">
              <span class="receipt-mgr-name">${esc(t.team_b.name)}</span>
              <span class="receipt-mgr-owner">${esc(t.team_b.owner || "")}</span>
            </div>
            <span class="grade-badge ${gradeClass(gb.grade)}">${gb.grade || "C"}</span>
          </div>
          <div class="receipt-players-box">
            <b>Acquired:</b> ${esc(pB)}
          </div>
          <div style="font-size:12px;color:var(--muted);display:flex;justify-content:space-between;flex-wrap:wrap;gap:4px;margin-top:2px">
            <span>Weekly Net: <b>${gb.score !== undefined ? (gb.score > 0 ? `+${gb.score.toFixed(2)}` : gb.score.toFixed(2)) : "0.00"} cats/wk</b></span>
            <span>Confidence: <b>${gb.confidence || "High"}</b></span>
          </div>
          ${gb.fit_benefit ? `<div style="font-size:11.5px;color:var(--color-ink-2);margin-top:2px"><b>Fit:</b> ${esc(gb.fit_benefit)}</div>` : ""}
          ${gb.cost_risk ? `<div style="font-size:11.5px;color:var(--muted)"><b>Risk:</b> ${esc(gb.cost_risk)}</div>` : ""}
        </div>
      </div>
    </div>`;
  }).join("");
}
