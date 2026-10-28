"""Trade Analyzer: 15-tier letter grading, probabilistic category simulation,
replacement-level roster modeling, and classification catalog for fantasy basketball trades.
"""
import math
from typing import Any, Dict, List, Optional, Tuple

# All 15 supported grades in strictly descending order
GRADES: List[str] = [
    "A+", "A", "A-",
    "B+", "B", "B-",
    "C+", "C", "C-",
    "D+", "D", "D-",
    "F+", "F", "F-"
]

# Monotonic rank: 14 for A+ down to 0 for F-
GRADE_RANKS: Dict[str, int] = {g: len(GRADES) - 1 - i for i, g in enumerate(GRADES)}

# Numerical boundaries for marginal impact: delta expected categories won per weekly matchup (ΔxCat)
# Typical weekly range for 9-cat league is -1.5 to +1.5 cats/week.
# A shift of +0.80 cats/week is massive (~18% of a matchup), warranting A+.
GRADE_THRESHOLDS: List[Tuple[str, float]] = [
    ("A+", 0.80),
    ("A",  0.60),
    ("A-", 0.45),
    ("B+", 0.32),
    ("B",  0.20),
    ("B-", 0.10),
    ("C+", 0.04),
    ("C",  -0.03),
    ("C-", -0.09),
    ("D+", -0.19),
    ("D",  -0.31),
    ("D-", -0.44),
    ("F+", -0.59),
    ("F",  -0.79),
    ("F-", -float("inf")),
]

GRADE_DESCRIPTIONS: Dict[str, str] = {
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
    "F-": "All-time blunder candidate. Lopsided destruction of franchise championship equity.",
}

# Empirical standard deviations of matchup margin differences in 9-cat H2H
CAT_SIGMAS: Dict[int, float] = {
    0: 75.0,    # PTS
    6: 30.0,    # REB
    3: 28.0,    # AST
    2: 9.0,     # STL
    1: 8.5,     # BLK
    17: 16.0,   # 3PM
    19: 0.055,  # FG% (fraction)
    20: 0.085,  # FT% (fraction)
    11: 12.5,   # TO (turnovers, reverse)
}

CAT_IDS = [0, 6, 3, 2, 1, 17, 19, 20, 11]
CAT_LABELS: Dict[int, str] = {
    0: "PTS", 6: "REB", 3: "AST", 2: "STL", 1: "BLK",
    17: "3PM", 19: "FG%", 20: "FT%", 11: "TO"
}
STAT_KEYS: Dict[int, str] = {
    0: "pts", 6: "reb", 3: "ast", 2: "stl", 1: "blk",
    17: "tpm", 11: "to"
}
GP_WEEK = 3.25

# Baseline 10-team league waiver / replacement-level contribution (per game)
DEFAULT_REPLACEMENT: Dict[str, float] = {
    "pts": 8.5, "reb": 5.2, "ast": 2.4, "stl": 0.85, "blk": 0.8,
    "tpm": 0.7, "fg_pct": 0.465, "ft_pct": 0.680, "to": 1.5,
    "fgm": 3.3, "fga": 7.1, "ftm": 1.2, "fta": 1.8
}


def norm_cdf(z: float) -> float:
    """Standard normal cumulative distribution function."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def score_to_grade(score: float) -> str:
    """Map a continuous marginal ΔxCat score to a 15-tier letter grade."""
    for grade, thresh in GRADE_THRESHOLDS:
        if score >= thresh:
            return grade
    return "F-"


def compare_grades(g1: str, g2: str) -> int:
    """Return 1 if g1 > g2, -1 if g1 < g2, 0 if g1 == g2."""
    r1, r2 = GRADE_RANKS.get(g1, 0), GRADE_RANKS.get(g2, 0)
    if r1 > r2:
        return 1
    if r1 < r2:
        return -1
    return 0


def compute_replacement_player(rosters: Optional[Dict[str, List[Dict[str, Any]]]]) -> Dict[str, float]:
    """Dynamically determine replacement-level player stats from bottom of rosters."""
    if not rosters:
        return dict(DEFAULT_REPLACEMENT)
    bottom = []
    for team_players in rosters.values():
        if team_players:
            sorted_p = sorted(team_players, key=lambda x: x.get("pts", 0))
            bottom.extend(sorted_p[:3])
    if len(bottom) < 10:
        return dict(DEFAULT_REPLACEMENT)
    rep = {}
    for k in ["pts", "reb", "ast", "stl", "blk", "tpm", "fg_pct", "ft_pct", "to", "fgm", "fga", "ftm", "fta"]:
        rep[k] = round(sum(p.get(k, 0.0) for p in bottom) / len(bottom), 3)
    return rep


def simulate_expected_cats_won(team_id: int, team_strength: Dict[str, float], all_teams: List[Dict[str, Any]]) -> float:
    """Simulate expected category wins (out of 9.0) in a typical weekly matchup against the league."""
    opponents = [t for t in all_teams if t.get("id") != team_id]
    if not opponents:
        return 4.5
    total = 0.0
    for opp in opponents:
        opp_str = opp.get("strength", {})
        for cid in CAT_IDS:
            v_t = float(team_strength.get(str(cid), 0.0))
            v_o = float(opp_str.get(str(cid), 0.0))
            # For turnovers (cid 11), lower is better
            diff = (v_o - v_t) if cid == 11 else (v_t - v_o)
            sigma = CAT_SIGMAS.get(cid, 20.0)
            total += norm_cdf(diff / sigma)
    return round(total / len(opponents), 3)


def calculate_package_deltas(
    sent_players: List[Dict[str, Any]],
    recv_players: List[Dict[str, Any]],
    rep_player: Dict[str, float]
) -> Tuple[Dict[int, float], int]:
    """Calculate raw category deltas for a team, including replacement level for vacated roster spots."""
    deltas = {}
    n_sent, n_recv = len(sent_players), len(recv_players)
    vacated_slots = n_sent - n_recv  # Positive means team freed up roster spots (gains waiver players)

    for cid in [0, 6, 3, 2, 1, 17, 11]:
        k = STAT_KEYS[cid]
        incoming_val = sum(p.get(k, 0.0) for p in recv_players)
        outgoing_val = sum(p.get(k, 0.0) for p in sent_players)

        # Apply replacement waiver contributions for vacated roster spots
        if vacated_slots > 0:
            incoming_val += vacated_slots * rep_player.get(k, 0.0)
        elif vacated_slots < 0:
            outgoing_val += abs(vacated_slots) * rep_player.get(k, 0.0)

        deltas[cid] = round((incoming_val - outgoing_val) * GP_WEEK, 1)

    # Volume-weighted FG% and FT%
    fgm_in = sum(p.get("fgm", 0.0) for p in recv_players)
    fga_in = sum(p.get("fga", 0.0) for p in recv_players)
    fgm_out = sum(p.get("fgm", 0.0) for p in sent_players)
    fga_out = sum(p.get("fga", 0.0) for p in sent_players)

    ftm_in = sum(p.get("ftm", 0.0) for p in recv_players)
    fta_in = sum(p.get("fta", 0.0) for p in recv_players)
    ftm_out = sum(p.get("ftm", 0.0) for p in sent_players)
    fta_out = sum(p.get("fta", 0.0) for p in sent_players)

    if vacated_slots > 0:
        fgm_in += vacated_slots * rep_player.get("fgm", 0.0)
        fga_in += vacated_slots * rep_player.get("fga", 0.0)
        ftm_in += vacated_slots * rep_player.get("ftm", 0.0)
        fta_in += vacated_slots * rep_player.get("fta", 0.0)
    elif vacated_slots < 0:
        fgm_out += abs(vacated_slots) * rep_player.get("fgm", 0.0)
        fga_out += abs(vacated_slots) * rep_player.get("fga", 0.0)
        ftm_out += abs(vacated_slots) * rep_player.get("ftm", 0.0)
        fta_out += abs(vacated_slots) * rep_player.get("fta", 0.0)

    # Net percentage swings (scaled to typical team weekly volume ~300 FGA, 90 FTA)
    net_fgm = (fgm_in - fgm_out) * GP_WEEK
    net_fga = (fga_in - fga_out) * GP_WEEK
    base_fga = 300.0
    base_fgm = base_fga * 0.465
    post_fg_pct = (base_fgm + net_fgm) / max(1.0, base_fga + net_fga)
    deltas[19] = round(post_fg_pct - 0.465, 4)

    net_ftm = (ftm_in - ftm_out) * GP_WEEK
    net_fta = (fta_in - fta_out) * GP_WEEK
    base_fta = 90.0
    base_ftm = base_fta * 0.770
    post_ft_pct = (base_ftm + net_ftm) / max(1.0, base_fta + net_fta)
    deltas[20] = round(post_ft_pct - 0.770, 4)

    return deltas, vacated_slots


def analyze_manager_grade(
    team: Dict[str, Any],
    deltas: Dict[int, float],
    all_teams: List[Dict[str, Any]],
    sent_players: List[Dict[str, Any]],
    recv_players: List[Dict[str, Any]],
    vacated_slots: int
) -> Dict[str, Any]:
    """Calculate individual manager grade, expected category shift, and roster fit details."""
    team_id = team.get("id", 0)
    base_str = dict(team.get("strength") or {})

    # Ensure all category keys exist in base
    for cid in CAT_IDS:
        base_str.setdefault(str(cid), 300.0 if cid == 0 else 0.465 if cid == 19 else 0.770 if cid == 20 else 50.0)

    post_str = dict(base_str)
    for cid in CAT_IDS:
        d = deltas.get(cid, 0.0)
        post_str[str(cid)] = post_str.get(str(cid), 0.0) + d

    x_pre = simulate_expected_cats_won(team_id, base_str, all_teams)
    x_post = simulate_expected_cats_won(team_id, post_str, all_teams)
    delta_x = round(x_post - x_pre, 3)

    grade = score_to_grade(delta_x)
    grade_desc = GRADE_DESCRIPTIONS.get(grade, "")

    gained_cats = []
    lost_cats = []
    for cid in CAT_IDS:
        val = deltas.get(cid, 0.0)
        lbl = CAT_LABELS[cid]
        is_good = val < 0 if cid == 11 else val > 0
        if is_good and abs(val) > (0.002 if cid in (19, 20) else 0.5):
            gained_cats.append(lbl)
        elif not is_good and abs(val) > (0.002 if cid in (19, 20) else 0.5):
            lost_cats.append(lbl)

    # Identify biggest category gain and concession
    best_cat, worst_cat = None, None
    best_impact, worst_impact = -1e9, 1e9
    for cid in CAT_IDS:
        val = deltas.get(cid, 0.0)
        norm_impact = (-val if cid == 11 else val) / CAT_SIGMAS[cid]
        if norm_impact > best_impact:
            best_impact = norm_impact
            best_cat = CAT_LABELS[cid]
        if norm_impact < worst_impact:
            worst_impact = norm_impact
            worst_cat = CAT_LABELS[cid]

    # Fit benefits & risk analysis
    benefit_parts = []
    if gained_cats:
        benefit_parts.append(f"Notable gains in {', '.join(gained_cats[:3])}")
    if vacated_slots > 0:
        benefit_parts.append(f"Opened {vacated_slots} streaming/waiver spot{'s' if vacated_slots > 1 else ''}")
    fit_benefit = "; ".join(benefit_parts) if benefit_parts else "Maintains existing roster balance"

    risk_parts = []
    if lost_cats:
        risk_parts.append(f"Concessions in {', '.join(lost_cats[:3])}")
    injured_in = [p.get("name") for p in recv_players if p.get("inj")]
    if injured_in:
        risk_parts.append(f"Health risk on incoming {', '.join(injured_in)}")
    if vacated_slots < 0:
        risk_parts.append(f"Roster crunch: required dropping {abs(vacated_slots)} player{'s' if abs(vacated_slots) > 1 else ''}")
    cost_risk = "; ".join(risk_parts) if risk_parts else "Low structural risk"

    # Confidence assessment
    has_inj = any(p.get("inj") for p in sent_players + recv_players)
    low_gp = any(p.get("gp", 0) < 5 for p in sent_players + recv_players)
    if has_inj or low_gp:
        confidence = "Medium"
        confidence_reason = "Elevated uncertainty due to active injuries or small early-season sample"
    else:
        confidence = "High"
        confidence_reason = "Stable baseline player projections and established volume"

    return {
        "grade": grade,
        "score": delta_x,
        "delta_cats": delta_x,
        "x_pre": x_pre,
        "x_post": x_post,
        "description": grade_desc,
        "desc": grade_desc,
        "gained_cats": gained_cats,
        "lost_cats": lost_cats,
        "best_cat": best_cat,
        "worst_cat": worst_cat,
        "fit_benefit": fit_benefit,
        "cost_risk": cost_risk,
        "confidence": confidence,
        "confidence_reason": confidence_reason,
        "vacated_slots": vacated_slots,
    }


def determine_trade_verdict(
    grade_a: Dict[str, Any],
    grade_b: Dict[str, Any],
    team_a: Dict[str, Any],
    team_b: Dict[str, Any],
    incomplete: bool = False
) -> Dict[str, Any]:
    """Separate individual grades from overall trade outcome (Clear Win, Win-Win, Fair, etc.)."""
    if incomplete:
        return {
            "outcome": "incomplete",
            "outcome_label": "Incomplete Evaluation",
            "winner_id": None,
            "winner_name": None,
            "margin_str": "Data quality insufficient",
            "net_delta": 0.0,
            "diff_signed": 0.0,
            "reason": "Insufficient game or health data available to produce a defensible probabilistic verdict.",
        }

    s_a = grade_a["score"]
    s_b = grade_b["score"]
    diff = round(s_a - s_b, 3)
    abs_diff = abs(diff)

    # 1. Win-Win: Both teams meaningfully improve their outlook
    if s_a >= 0.12 and s_b >= 0.12:
        outcome = "win_win"
        outcome_label = "Win-Win"
        winner_id = None
        winner_name = None
        margin_str = f"Mutual upgrade (+{s_a:.2f} / +{s_b:.2f} cats/wk)"
        reason = "Both front offices addressed complementary category needs and increased their expected weekly win rate."

    # 2. Lose-Lose: Both teams' outlooks deteriorate
    elif s_a <= -0.12 and s_b <= -0.12:
        outcome = "lose_lose"
        outcome_label = "Lose-Lose"
        winner_id = None
        winner_name = None
        margin_str = f"Mutual regression ({s_a:.2f} / {s_b:.2f} cats/wk)"
        reason = "Both rosters surrendered critical category strengths without receiving adequate compensating value."

    # 3. Clear Win: One side gains materially more than the other
    elif abs_diff >= 0.40:
        outcome = "clear_win"
        outcome_label = "Clear Win"
        if s_a > s_b:
            winner_id = team_a.get("id")
            winner_name = team_a.get("name")
        else:
            winner_id = team_b.get("id")
            winner_name = team_b.get("name")
        margin_str = f"+{abs_diff:.2f} cats/wk advantage"
        reason = f"{winner_name} captured decisive category equity while limiting return concessions."

    # 4. Slight Edge: Modest advantage
    elif abs_diff >= 0.14:
        outcome = "slight_edge"
        outcome_label = "Slight Edge"
        if s_a > s_b:
            winner_id = team_a.get("id")
            winner_name = team_a.get("name")
        else:
            winner_id = team_b.get("id")
            winner_name = team_b.get("name")
        margin_str = f"+{abs_diff:.2f} cats/wk lean"
        reason = f"{winner_name} extracted a modest category edge in an otherwise competitive exchange."

    # 5. Too Close to Call: Margin within statistical noise (< 0.04)
    elif abs_diff < 0.04:
        outcome = "too_close_to_call"
        outcome_label = "Too Close to Call"
        winner_id = None
        winner_name = None
        margin_str = "Dead heat (split advantage)"
        reason = "Marginal category shifts are too evenly matched to declare a definitive winner."

    # 6. Fair Trade: Minimal net difference between teams
    else:
        outcome = "fair_trade"
        outcome_label = "Fair Trade"
        winner_id = None
        winner_name = None
        margin_str = "Even balance (within 0.1 cats/wk)"
        reason = "A highly equitable exchange where neither manager gained an outsized statistical advantage."
        winner_name = None
        margin_str = "Dead heat (split advantage)"
        reason = "Marginal category shifts are too evenly matched to declare a definitive winner."

    return {
        "outcome": outcome,
        "outcome_label": outcome_label,
        "winner_id": winner_id,
        "winner_name": winner_name,
        "margin_str": margin_str,
        "net_delta": abs_diff,
        "diff_signed": diff,
        "reason": reason,
    }


# ============================================================================
# Classification Catalog (Deterministic Rules, Priority & Entertaining Copy)
# ============================================================================

class TradeClassification:
    def __init__(self, id_str: str, name: str, desc: str, priority: int, tags: List[str], condition_fn, headline_fn, roast_fn):
        self.id = id_str
        self.name = name
        self.desc = desc
        self.priority = priority
        self.tags = tags
        self.condition = condition_fn
        self.headline = headline_fn
        self.roast = roast_fn


def build_classification_catalog() -> List[TradeClassification]:
    catalog = []

    # 1. Generational Heist
    catalog.append(TradeClassification(
        "generational_heist",
        "Generational Heist",
        "An extreme outlier victory where one manager pulls off a franchise-altering robbery.",
        100,
        ["All-Time Heist", "Franchise-Altering"],
        lambda ctx: (ctx["winner_score"] >= 0.80 and ctx["loser_score"] <= -0.40) or ctx["net_delta"] >= 1.20,
        lambda ctx: f"A generational heist: {ctx['winner_name']} reshapes the championship race.",
        lambda ctx: f"Call the league office and pull the security tapes. {ctx['winner_name']} just fleeced {ctx['loser_name']} for franchise-altering equity without leaving a trace."
    ))

    # 2. Robbery in Broad Daylight
    catalog.append(TradeClassification(
        "robbery",
        "Robbery in Broad Daylight",
        "A devastating, lopsided victory where one side completely exploits the other.",
        95,
        ["Fleece", "Lopsided"],
        lambda ctx: (ctx["winner_score"] >= 0.60 and ctx["loser_score"] <= -0.30) or ctx["net_delta"] >= 0.90,
        lambda ctx: f"Larceny on the wire: {ctx['winner_name']} executes a broad daylight heist.",
        lambda ctx: f"There is no spin doctor on earth who can save this deal. {ctx['winner_name']} walked away with gold while {ctx['loser_name']} surrendered the keys to the kingdom."
    ))

    # 3. Highway Robbery
    catalog.append(TradeClassification(
        "highway_robbery",
        "Highway Robbery",
        "A substantial, decisive advantage with few compensating benefits for the loser.",
        90,
        ["Decisive Win", "Fleece Alert"],
        lambda ctx: ctx["winner_score"] >= 0.45 and ctx["loser_score"] <= -0.20 and ctx["net_delta"] >= 0.70,
        lambda ctx: f"{ctx['winner_name']} pulls off highway robbery at {ctx['loser_name']}'s expense.",
        lambda ctx: f"A ruthless extraction. {ctx['winner_name']} identified an eager trade partner and capitalized with surgical precision."
    ))

    # 4. Fleece Alert
    catalog.append(TradeClassification(
        "fleece_alert",
        "Fleece Alert",
        "A clear, one-sided trade advantage that sparks immediate debate.",
        85,
        ["Fleece Alert", "Group Chat Heated"],
        lambda ctx: ctx["winner_score"] >= 0.32 and ctx["loser_score"] <= -0.19 and ctx["net_delta"] >= 0.50,
        lambda ctx: f"Fleece alert triggered: {ctx['winner_name']} gains an outsized edge.",
        lambda ctx: f"The group chat won't let this one slide. {ctx['winner_name']} exploited an urgent need and took {ctx['loser_name']} to the cleaners."
    ))

    # 5. Generational Bag Fumble
    catalog.append(TradeClassification(
        "bag_fumble",
        "Generational Bag Fumble",
        "A catastrophic self-inflicted roster mistake with extreme negative impact.",
        92,
        ["Disasterclass", "Self-Inflicted"],
        lambda ctx: ctx["loser_score"] <= -0.60,
        lambda ctx: f"Generational bag fumble: {ctx['loser_name']}'s trade backfires spectacularly.",
        lambda ctx: f"Frame the receipt. {ctx['loser_name']} just committed an unforced front-office error that will echo through the fantasy playoffs."
    ))

    # 6. Disasterclass
    catalog.append(TradeClassification(
        "disasterclass",
        "Disasterclass",
        "A major negative trade outcome with multiple core category losses.",
        88,
        ["Disasterclass"],
        lambda ctx: ctx["loser_score"] <= -0.44,
        lambda ctx: f"Total disasterclass: {ctx['loser_name']}'s roster math unravels.",
        lambda ctx: f"A severe miscalculation. {ctx['loser_name']} surrendered elite category anchors and got pennies on the dollar in return."
    ))

    # 7. A Donation to the League
    catalog.append(TradeClassification(
        "donation",
        "A Donation to the League",
        "An inexplicable giveaway where one side offers premium stats for negligible return.",
        87,
        ["Charity", "One-Sided"],
        lambda ctx: ctx["loser_score"] <= -0.32 and ctx["winner_score"] >= 0.20,
        lambda ctx: f"{ctx['loser_name']} makes a generous charitable donation to {ctx['winner_name']}.",
        lambda ctx: f"Tax write-offs don't apply to fantasy basketball, but {ctx['loser_name']} just operated like a 501(c)(3) nonprofit."
    ))

    # 8. Win-Win Negotiation
    catalog.append(TradeClassification(
        "win_win",
        "Win-Win Negotiation",
        "The rare trade where both managers genuinely improve their expected matchup win rates.",
        86,
        ["Win-Win", "Mutual Upgrade"],
        lambda ctx: ctx["score_a"] >= 0.12 and ctx["score_b"] >= 0.12,
        lambda ctx: "The rare competent negotiation: both rosters genuinely improve.",
        lambda ctx: f"Nobody needs to delete their messages. Both {ctx['team_a']['name']} and {ctx['team_b']['name']} addressed real category needs and walk away stronger."
    ))

    # 9. Mutual Upgrade
    catalog.append(TradeClassification(
        "mutual_upgrade",
        "Mutual Upgrade",
        "A solid, functional trade that improves both teams' overall competitive balance.",
        78,
        ["Balanced", "Roster Fit"],
        lambda ctx: ctx["score_a"] >= 0.04 and ctx["score_b"] >= 0.04,
        lambda ctx: "A clean mutual upgrade: both front offices find their missing puzzle pieces.",
        lambda ctx: f"A textbook category swap. {ctx['team_a']['name']} and {ctx['team_b']['name']} trade surplus for scarcity with zero remorse."
    ))

    # 10. Fair and Square
    catalog.append(TradeClassification(
        "fair_and_square",
        "Fair and Square",
        "An equitable exchange with negligible net category tilt.",
        70,
        ["Even Value", "Clean Business"],
        lambda ctx: ctx["net_delta"] < 0.10 and abs(ctx["score_a"]) < 0.15 and abs(ctx["score_b"]) < 0.15,
        lambda ctx: "Fair and square: an equitable exchange with negligible net shift.",
        lambda ctx: "As balanced as a laboratory scale. Neither manager was fleeced, neither manager gloats, and the standings will barely flinch."
    ))

    # 11. Front Office Masterstroke
    catalog.append(TradeClassification(
        "masterclass",
        "Front Office Masterstroke",
        "A brilliant move where the winner identifies hidden category synergies.",
        82,
        ["Masterclass", "Tactical"],
        lambda ctx: ctx["winner_score"] >= 0.45 and ctx["loser_score"] >= -0.15,
        lambda ctx: f"{ctx['winner_name']} operates on another frequency with a tactical masterstroke.",
        lambda ctx: f"Executive wizardry: {ctx['winner_name']} engineered a massive category boost without provoking a league office panic."
    ))

    # 12. Sneaky Win
    catalog.append(TradeClassification(
        "sneaky_win",
        "Sneaky Win",
        "A trade that looks innocent on player names but delivers a distinct category advantage.",
        76,
        ["Under the Radar", "Category Math"],
        lambda ctx: ctx["net_delta"] >= 0.30 and ctx["winner_score"] >= 0.20 and ctx["loser_score"] >= -0.20,
        lambda ctx: f"{ctx['winner_name']} secures a sneaky, under-the-radar victory.",
        lambda ctx: f"Casual observers will look at the player names and nod. The underlying category distributions tell a far more lopsided story in favor of {ctx['winner_name']}."
    ))

    # 13. The 2-for-1 Tax
    catalog.append(TradeClassification(
        "two_for_one_tax",
        "The 2-for-1 Tax",
        "Depth proves to be an illusion after accounting for replacement waiver production.",
        83,
        ["Roster Math", "Waiver Value"],
        lambda ctx: ctx["has_imbalance"] and ctx["consolidator_won"],
        lambda ctx: f"The 2-for-1 tax strikes: {ctx['winner_name']} proves star power beats depth.",
        lambda ctx: f"Trading a dollar for two quarters rarely works in a 10-team league. Once replacement waiver stats are factored in, {ctx['winner_name']} walks away as the clear winner."
    ))

    # 14. Consolidation Masterclass
    catalog.append(TradeClassification(
        "consolidation_masterclass",
        "Consolidation Masterclass",
        "Cashing in depth for the best single player in the deal to open a valuable waiver slot.",
        84,
        ["Star Power", "Consolidation"],
        lambda ctx: ctx["has_imbalance"] and ctx["consolidator_score"] >= 0.30,
        lambda ctx: f"Consolidation masterclass: {ctx['winner_name']} turns surplus depth into elite star power.",
        lambda ctx: f"In competitive fantasy basketball, top-10 talent rules supreme. {ctx['winner_name']} paid with interchangeable parts and acquired the undisputed crown jewel."
    ))

    # 15. The Group Chat Is Going to Be Loud
    catalog.append(TradeClassification(
        "group_chat_loud",
        "The Group Chat Is Going to Be Loud",
        "A monster multi-player blockbuster with high-profile stars on both sides.",
        85,
        ["Blockbuster", "Mega-Deal"],
        lambda ctx: ctx["total_players"] >= 6 or (ctx["total_players"] >= 4 and ctx["has_top_star"]),
        lambda ctx: "Earthquake on the wire: the group chat is going to be loud.",
        lambda ctx: "Mute your notifications immediately. A franchise-altering blockbuster just landed, and the hot takes will take days to cool off."
    ))

    # 16. The Category Flip
    catalog.append(TradeClassification(
        "category_flip",
        "The Category Flip",
        "A massive pivot that completely reverses the team's weekly category profile.",
        79,
        ["Category Pivot", "Identity Shift"],
        lambda ctx: ctx["has_major_flip"],
        lambda ctx: "The category flip: rosters completely pivot their competitive identity.",
        lambda ctx: "Out with the old strengths, in with the new. Both teams radically transformed their category blueprints in a single transaction."
    ))

    # 17. Punt Architect
    catalog.append(TradeClassification(
        "punt_architect",
        "Punt Architect",
        "Intentionally punting one or two categories to lock down dominance in four others.",
        77,
        ["Punt Strategy", "Surgical"],
        lambda ctx: ctx["has_punt_profile"],
        lambda ctx: f"{ctx['winner_name']} executes the punt playbook with architectural precision.",
        lambda ctx: f"Conceding a category you were already losing to guarantee victories in four others is pure tactical genius."
    ))

    # 18. Guard-Room Overhaul
    catalog.append(TradeClassification(
        "guard_room_overhaul",
        "Guard-Room Overhaul",
        "A dramatic shift toward perimeter scoring, playmaking, and perimeter defense.",
        74,
        ["Perimeter Firepower", "Assists & Threes"],
        lambda ctx: ctx["guard_heavy"],
        lambda ctx: "Backcourt explosion: a dramatic overhaul in perimeter firepower.",
        lambda ctx: "Playmaking, spacing, and perimeter steals. This deal floods the backcourt with ball-handling dynamism."
    ))

    # 19. Big-Man Consolidation
    catalog.append(TradeClassification(
        "big_man_consolidation",
        "Big-Man Consolidation",
        "Cornering the market on rebounds, blocks, and field goal percentage.",
        74,
        ["Paint Dominance", "Frontcourt Muscle"],
        lambda ctx: ctx["big_man_heavy"],
        lambda ctx: "Paint dominance secured: frontcourt muscle locked in.",
        lambda ctx: "Old-school bully ball is alive and well. Trading finesse for rim protection, boards, and interior efficiency."
    ))

    # 20. Turnover Cleanup
    catalog.append(TradeClassification(
        "turnover_cleanup",
        "Turnover Cleanup",
        "A targeted upgrade to stop giving away the turnover category on Sunday nights.",
        71,
        ["Ball Security", "Discipline"],
        lambda ctx: ctx["to_cleanup"],
        lambda ctx: "Ball security prioritized: cleaning up the turnover bleed.",
        lambda ctx: "Tired of kicking away close Sunday matchups on reckless passes, ball security was made the top priority."
    ))

    # 21. Efficiency Play
    catalog.append(TradeClassification(
        "efficiency_play",
        "Efficiency Play",
        "Targeting elite shooting percentages to win the highest-margin categories in fantasy.",
        72,
        ["True Shooting", "Efficiency"],
        lambda ctx: ctx["efficiency_edge"],
        lambda ctx: "True shooting masterclass: cashing in on elite shooting efficiency.",
        lambda ctx: "Counting stats get the headlines; shooting splits win championships. A high-margin acquisition of pure efficiency."
    ))

    # 22. Injury Roulette
    catalog.append(TradeClassification(
        "injury_roulette",
        "Injury Roulette",
        "A high-stakes gamble involving currently injured or historically fragile players.",
        80,
        ["Injury Risk", "High Stakes"],
        lambda ctx: ctx["has_injured_player"],
        lambda ctx: "Playing injury roulette: rolling the medical dice.",
        lambda ctx: "If they stay on the hardwood, it is a masterstroke. If they live on the injury report, this trade will be discussed in therapy."
    ))

    # 23. The Rich Get Richer
    catalog.append(TradeClassification(
        "rich_get_richer",
        "The Rich Get Richer",
        "A top-standing contender solidifies their championship advantage.",
        75,
        ["Contender Move", "Title Equity"],
        lambda ctx: ctx["top_seed_won"],
        lambda ctx: f"The rich get richer: {ctx['winner_name']} consolidates dominance.",
        lambda ctx: f"Because a top contender didn't have enough advantages already, the rest of the league just let them get even stronger."
    ))

    # 24. Solving a Problem Nobody Had
    catalog.append(TradeClassification(
        "redundant_production",
        "Solving a Problem Nobody Had",
        "Adding excessive stats in already dominant categories while bleeding bubble categories.",
        73,
        ["Diminishing Returns", "Redundant"],
        lambda ctx: ctx["is_redundant"],
        lambda ctx: f"Redundant firepower: {ctx['loser_name']} solves a problem nobody had.",
        lambda ctx: "Winning a category by 60 points awards the exact same 1-0 as winning by 1 point. Surplus value was stockpiled where it was least needed."
    ))

    # 25. The Screenshot Will Be Saved
    catalog.append(TradeClassification(
        "screenshot_saved",
        "The Screenshot Will Be Saved",
        "A polarizing trade where both managers feel confident today, setting up future receipts.",
        68,
        ["Receipts Pending", "Debatable"],
        lambda ctx: ctx["is_debatable"],
        lambda ctx: "The screenshot will be saved: trade receipts filed for future reference.",
        lambda ctx: "Both managers feel smug today. By week 18, one of these trade receipts will be weaponized in the group chat."
    ))

    # 26. Clean Business (Default Fallback)
    catalog.append(TradeClassification(
        "clean_business",
        "Clean Business",
        "A standard, professional trade executed without drama.",
        10,
        ["Standard Trade"],
        lambda ctx: True,
        lambda ctx: f"Clean business: {ctx['winner_name'] or 'both teams'} move forward with updated rosters.",
        lambda ctx: "A straightforward exchange of talent. The numbers have shifted, the rosters are set, and the league moves on."
    ))

    return catalog


def classify_trade(
    team_a: Dict[str, Any],
    team_b: Dict[str, Any],
    players_a: List[Dict[str, Any]],
    players_b: List[Dict[str, Any]],
    grade_a: Dict[str, Any],
    grade_b: Dict[str, Any],
    verdict: Dict[str, Any],
    deltas_a: Dict[int, float],
    deltas_b: Dict[int, float]
) -> Dict[str, Any]:
    """Evaluate context against the classification catalog and return the highest-priority match."""
    score_a = grade_a["score"]
    score_b = grade_b["score"]
    winner_score = max(score_a, score_b)
    loser_score = min(score_a, score_b)
    winner_name = team_a["name"] if score_a >= score_b else team_b["name"]
    loser_name = team_b["name"] if score_a >= score_b else team_a["name"]

    n_a = len(players_a)
    n_b = len(players_b)
    total_players = n_a + n_b
    has_imbalance = n_a != n_b

    # Consolidator is the manager who gave up more players to get fewer (consolidating into fewer slots)
    consolidator_won = (n_a > n_b and score_b > score_a) or (n_b > n_a and score_a > score_b)
    consolidator_score = score_b if n_a > n_b else score_a if n_b > n_a else 0.0

    all_players = players_a + players_b
    has_injured_player = any(p.get("inj") for p in all_players)
    has_top_star = any(p.get("pts", 0) >= 28 or p.get("ast", 0) >= 8 or p.get("reb", 0) >= 10 for p in all_players)

    # Check for category flips
    has_major_flip = (abs(deltas_a.get(0, 0)) >= 30.0 and abs(deltas_a.get(6, 0)) >= 10.0) or \
                     (abs(deltas_a.get(17, 0)) >= 12.0 and abs(deltas_a.get(1, 0)) >= 6.0)

    # Punt profile: losing 1-2 categories heavily while gaining 3+ others
    has_punt_profile = (len(grade_a["lost_cats"]) <= 2 and len(grade_a["gained_cats"]) >= 3 and score_a >= 0.15) or \
                       (len(grade_b["lost_cats"]) <= 2 and len(grade_b["gained_cats"]) >= 3 and score_b >= 0.15)

    guard_heavy = (abs(deltas_a.get(3, 0)) + abs(deltas_a.get(17, 0))) >= 15.0
    big_man_heavy = (abs(deltas_a.get(6, 0)) + abs(deltas_a.get(1, 0))) >= 15.0
    to_cleanup = deltas_a.get(11, 0) <= -12.0 or deltas_b.get(11, 0) <= -12.0
    efficiency_edge = abs(deltas_a.get(19, 0)) >= 0.035 or abs(deltas_a.get(20, 0)) >= 0.045

    top_seed_won = (winner_name == team_a["name"] and team_a.get("rank", 10) <= 3 and score_a >= 0.20) or \
                   (winner_name == team_b["name"] and team_b.get("rank", 10) <= 3 and score_b >= 0.20)

    is_redundant = (score_a <= -0.15 and len(grade_a["gained_cats"]) >= 1) or \
                   (score_b <= -0.15 and len(grade_b["gained_cats"]) >= 1)

    is_debatable = 0.10 <= verdict["net_delta"] <= 0.35

    ctx = {
        "team_a": team_a,
        "team_b": team_b,
        "players_a": players_a,
        "players_b": players_b,
        "score_a": score_a,
        "score_b": score_b,
        "winner_score": winner_score,
        "loser_score": loser_score,
        "winner_name": winner_name,
        "loser_name": loser_name,
        "net_delta": verdict["net_delta"],
        "total_players": total_players,
        "has_imbalance": has_imbalance,
        "consolidator_won": consolidator_won,
        "consolidator_score": consolidator_score,
        "has_injured_player": has_injured_player,
        "has_top_star": has_top_star,
        "has_major_flip": has_major_flip,
        "has_punt_profile": has_punt_profile,
        "guard_heavy": guard_heavy,
        "big_man_heavy": big_man_heavy,
        "to_cleanup": to_cleanup,
        "efficiency_edge": efficiency_edge,
        "top_seed_won": top_seed_won,
        "is_redundant": is_redundant,
        "is_debatable": is_debatable,
    }

    catalog = build_classification_catalog()
    catalog.sort(key=lambda c: -c.priority)

    matched = None
    for item in catalog:
        try:
            if item.condition(ctx):
                matched = item
                break
        except Exception:
            continue

    if not matched:
        matched = catalog[-1]  # clean_business fallback

    secondary_tags = [t for t in matched.tags if t != matched.name][:2]

    # Add secondary context tags
    if has_injured_player and "Injury Risk" not in secondary_tags:
        secondary_tags.append("Injury Risk")
    elif has_imbalance and "Roster Math" not in secondary_tags:
        secondary_tags.append(f"{max(n_a, n_b)}-for-{min(n_a, n_b)}")

    return {
        "id": matched.id,
        "name": matched.name,
        "desc": matched.desc,
        "priority": matched.priority,
        "tags": secondary_tags[:2],
        "headline": matched.headline(ctx),
        "roast": matched.roast(ctx),
    }


def analyze_trade(
    team_a: Dict[str, Any],
    team_b: Dict[str, Any],
    players_to_a: List[Dict[str, Any]],
    players_to_b: List[Dict[str, Any]],
    all_teams: List[Dict[str, Any]],
    rep_player: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    """Complete trade analysis engine: computes deltas, manager grades, verdict, and classifications."""
    if rep_player is None:
        rep_player = dict(DEFAULT_REPLACEMENT)

    # In terms of transfer: players_to_a are sent by B to A; players_to_b are sent by A to B
    deltas_a, vac_a = calculate_package_deltas(players_to_b, players_to_a, rep_player)
    deltas_b, vac_b = calculate_package_deltas(players_to_a, players_to_b, rep_player)

    grade_a = analyze_manager_grade(team_a, deltas_a, all_teams, players_to_b, players_to_a, vac_a)
    grade_b = analyze_manager_grade(team_b, deltas_b, all_teams, players_to_a, players_to_b, vac_b)

    verdict = determine_trade_verdict(grade_a, grade_b, team_a, team_b)

    classification = classify_trade(
        team_a, team_b, players_to_a, players_to_b,
        grade_a, grade_b, verdict, deltas_a, deltas_b
    )

    # Supporting package head-to-head comparison
    pkg_score_a, pkg_score_b = 0.0, 0.0
    for cid in CAT_IDS:
        dA = deltas_a[cid]
        dB = deltas_b[cid]
        good_a = dA < 0 if cid == 11 else dA > 0
        good_b = dB < 0 if cid == 11 else dB > 0
        if good_a and not good_b:
            pkg_score_a += 1.0
        elif good_b and not good_a:
            pkg_score_b += 1.0
        else:
            pkg_score_a += 0.5
            pkg_score_b += 0.5

    return {
        "verdict": {
            "outcome": verdict["outcome"],
            "outcome_label": verdict["outcome_label"],
            "winner_id": verdict["winner_id"],
            "winner_name": verdict["winner_name"],
            "margin_str": verdict["margin_str"],
            "net_delta": verdict["net_delta"],
            "reason": verdict["reason"],
            "classification": classification,
        },
        "grade_a": grade_a,
        "grade_b": grade_b,
        "deltas_a": deltas_a,
        "deltas_b": deltas_b,
        "package_comparison": {
            "score_a": pkg_score_a,
            "score_b": pkg_score_b,
            "winner_id": team_a["id"] if pkg_score_a > pkg_score_b else team_b["id"] if pkg_score_b > pkg_score_a else None,
        },
        "roster_adjustment": {
            "vacated_slots_a": vac_a,
            "vacated_slots_b": vac_b,
            "replacement_level": rep_player,
        },
        "assumptions": {
            "gp_week": GP_WEEK,
            "model_version": "v2.0-probabilistic",
            "eval_horizon": "weekly_matchup",
        }
    }
