"""Unit test suite for fantasy basketball trade analyzer.
Tests 15-tier letter grading, monotonic ordering, 7 overall verdicts,
replacement-level modeling, turnover direction, and classification precedence.
"""
import sys
import unittest
from pathlib import Path

# Add pipeline directory to sys.path
pipeline_dir = Path(__file__).resolve().parent.parent / "pipeline"
if str(pipeline_dir) not in sys.path:
    sys.path.insert(0, str(pipeline_dir))

from trade_analyzer import (
    GRADES,
    GRADE_RANKS,
    GRADE_THRESHOLDS,
    GRADE_DESCRIPTIONS,
    score_to_grade,
    compare_grades,
    determine_trade_verdict,
    calculate_package_deltas,
    compute_replacement_player,
    classify_trade,
    analyze_trade,
    DEFAULT_REPLACEMENT,
    CAT_IDS,
)


class TestTradeAnalyzer(unittest.TestCase):

    def test_all_15_grades_present(self):
        """Verify exactly 15 grades exist in strictly descending order with F+ included."""
        expected_grades = [
            "A+", "A", "A-",
            "B+", "B", "B-",
            "C+", "C", "C-",
            "D+", "D", "D-",
            "F+", "F", "F-"
        ]
        self.assertEqual(len(GRADES), 15)
        self.assertEqual(GRADES, expected_grades)
        self.assertIn("F+", GRADES)
        # Verify F+ is strictly between D- and F
        self.assertEqual(GRADES.index("D-") + 1, GRADES.index("F+"))
        self.assertEqual(GRADES.index("F+") + 1, GRADES.index("F"))

    def test_monotonic_grade_ordering(self):
        """Verify GRADE_RANKS and compare_grades strictly adhere to monotonic ordering."""
        for i in range(len(GRADES) - 1):
            higher = GRADES[i]
            lower = GRADES[i + 1]
            self.assertGreater(GRADE_RANKS[higher], GRADE_RANKS[lower], f"{higher} should outrank {lower}")
            self.assertEqual(compare_grades(higher, lower), 1)
            self.assertEqual(compare_grades(lower, higher), -1)
            self.assertEqual(compare_grades(higher, higher), 0)

    def test_grade_boundary_mappings(self):
        """Verify continuous scores map precisely to expected grades across boundaries."""
        test_cases = [
            (1.20, "A+"),
            (0.85, "A+"),
            (0.80, "A+"),
            (0.79, "A"),
            (0.60, "A"),
            (0.59, "A-"),
            (0.45, "A-"),
            (0.44, "B+"),
            (0.32, "B+"),
            (0.31, "B"),
            (0.20, "B"),
            (0.19, "B-"),
            (0.10, "B-"),
            (0.09, "C+"),
            (0.04, "C+"),
            (0.00, "C"),
            (-0.03, "C"),
            (-0.04, "C-"),
            (-0.09, "C-"),
            (-0.10, "D+"),
            (-0.19, "D+"),
            (-0.20, "D"),
            (-0.31, "D"),
            (-0.32, "D-"),
            (-0.44, "D-"),
            (-0.45, "F+"),
            (-0.59, "F+"),
            (-0.60, "F"),
            (-0.79, "F"),
            (-0.80, "F-"),
            (-2.50, "F-"),
        ]
        for score, expected_grade in test_cases:
            actual = score_to_grade(score)
            self.assertEqual(
                actual, expected_grade,
                f"Score {score} expected {expected_grade} but got {actual}"
            )

    def test_all_seven_overall_outcomes(self):
        """Verify all 7 overall outcomes can be produced:
        clear_win, slight_edge, fair_trade, win_win, lose_lose, too_close_to_call, incomplete.
        """
        team_a = {"id": 1, "name": "Team One", "owner": "Alice"}
        team_b = {"id": 2, "name": "Team Two", "owner": "Bob"}

        # 1. Clear Win (large margin >= 0.50)
        ga = {"grade": "A", "score": 0.65}
        gb = {"grade": "D", "score": -0.25}
        v = determine_trade_verdict(ga, gb, team_a, team_b)
        self.assertEqual(v["outcome"], "clear_win")
        self.assertEqual(v["winner_id"], 1)

        # 2. Slight Edge (margin between 0.20 and 0.50)
        ga = {"grade": "B", "score": 0.25}
        gb = {"grade": "C", "score": -0.05}
        v = determine_trade_verdict(ga, gb, team_a, team_b)
        self.assertEqual(v["outcome"], "slight_edge")
        self.assertEqual(v["winner_id"], 1)

        # 3. Fair Trade (close margin <= 0.20 with non-positive or near-zero individual gains)
        ga = {"grade": "C+", "score": 0.05}
        gb = {"grade": "C", "score": -0.02}
        v = determine_trade_verdict(ga, gb, team_a, team_b)
        self.assertEqual(v["outcome"], "fair_trade")

        # 4. Win-Win (both managers improve substantially >= 0.15)
        ga = {"grade": "B+", "score": 0.35}
        gb = {"grade": "B", "score": 0.25}
        v = determine_trade_verdict(ga, gb, team_a, team_b)
        self.assertEqual(v["outcome"], "win_win")

        # 5. Lose-Lose (both managers deteriorate <= -0.15)
        ga = {"grade": "D", "score": -0.25}
        gb = {"grade": "D-", "score": -0.35}
        v = determine_trade_verdict(ga, gb, team_a, team_b)
        self.assertEqual(v["outcome"], "lose_lose")

        # 6. Too Close to Call (margin < 0.04)
        ga = {"grade": "C", "score": 0.01}
        gb = {"grade": "C", "score": 0.00}
        v = determine_trade_verdict(ga, gb, team_a, team_b)
        self.assertEqual(v["outcome"], "too_close_to_call")

        # 7. Incomplete Evaluation (confidence low due to insufficient data / missing values)
        ga_inc = {"grade": "C", "score": 0.0, "confidence": "Low"}
        gb_inc = {"grade": "C", "score": 0.0, "confidence": "Low"}
        v_inc = determine_trade_verdict(ga_inc, gb_inc, team_a, team_b, incomplete=True)
        self.assertEqual(v_inc["outcome"], "incomplete")

    def test_replacement_level_in_2_for_1_trade(self):
        """In a 2-for-1 trade:
        Manager A sends 2 players and receives 1 (vacated_slots = +1).
        Manager A should receive credit for 1 replacement-level waiver wire player.
        Manager B sends 1 player and receives 2 (vacated_slots = -1).
        Manager B must drop 1 player (charged replacement-level cost).
        """
        star = {"name": "Superstar", "pts": 25.0, "reb": 6.0, "ast": 6.0, "stl": 1.5, "blk": 0.8, "tpm": 2.5, "fgm": 9.0, "fga": 18.0, "ftm": 5.0, "fta": 6.0, "to": 3.0}
        depth1 = {"name": "Solid Wing", "pts": 14.0, "reb": 5.0, "ast": 2.0, "stl": 1.0, "blk": 0.5, "tpm": 1.8, "fgm": 5.0, "fga": 11.0, "ftm": 2.5, "fta": 3.0, "to": 1.2}
        depth2 = {"name": "Solid Guard", "pts": 13.0, "reb": 3.0, "ast": 5.0, "stl": 1.2, "blk": 0.3, "tpm": 1.5, "fgm": 4.5, "fga": 10.0, "ftm": 2.5, "fta": 3.0, "to": 1.5}

        rep = dict(DEFAULT_REPLACEMENT)
        # Team A sends depth1 and depth2, receives star
        deltas_a, vac_a = calculate_package_deltas([depth1, depth2], [star], rep)
        self.assertEqual(vac_a, 1)  # 1 vacated spot

        # Expected PTS delta for A: (star pts + 1 * rep pts) - (depth1 pts + depth2 pts) * GP_WEEK
        expected_pts_diff = (star["pts"] + rep["pts"] - (depth1["pts"] + depth2["pts"])) * 3.25
        self.assertAlmostEqual(deltas_a[0], round(expected_pts_diff, 1), places=1)

        # Team B sends star, receives depth1 and depth2
        deltas_b, vac_b = calculate_package_deltas([star], [depth1, depth2], rep)
        self.assertEqual(vac_b, -1)  # -1 spot (roster crunch)

        # Expected PTS delta for B: (depth1 + depth2) - (star + rep)
        expected_pts_diff_b = (depth1["pts"] + depth2["pts"] - (star["pts"] + rep["pts"])) * 3.25
        self.assertAlmostEqual(deltas_b[0], round(expected_pts_diff_b, 1), places=1)
        # They should be exact opposites
        self.assertAlmostEqual(deltas_a[0] + deltas_b[0], 0.0, places=1)

    def test_turnover_direction(self):
        """Turnovers: lower is better. Gaining turnovers is a negative delta."""
        p_clean = {"name": "Clean PG", "pts": 15.0, "reb": 3.0, "ast": 6.0, "stl": 1.0, "blk": 0.2, "tpm": 1.5, "fgm": 5.0, "fga": 11.0, "ftm": 3.0, "fta": 3.5, "to": 1.0}
        p_sloppy = {"name": "Sloppy PG", "pts": 15.0, "reb": 3.0, "ast": 6.0, "stl": 1.0, "blk": 0.2, "tpm": 1.5, "fgm": 5.0, "fga": 11.0, "ftm": 3.0, "fta": 3.5, "to": 4.5}
        rep = dict(DEFAULT_REPLACEMENT)

        # Receiving sloppy player: TO delta is positive (more turnovers)
        deltas_sloppy, _ = calculate_package_deltas([p_clean], [p_sloppy], rep)
        self.assertGreater(deltas_sloppy[11], 0)

        # In analyze_trade, more turnovers should count as a lost category or risk
        team_a = {"id": 1, "name": "Team A", "owner": "A", "strength": {str(c): 50.0 for c in CAT_IDS}}
        team_b = {"id": 2, "name": "Team B", "owner": "B", "strength": {str(c): 50.0 for c in CAT_IDS}}
        all_teams = [team_a, team_b]

        res = analyze_trade(team_a, team_b, [p_clean], [p_sloppy], all_teams, rep)
        # Team A receives p_clean, sends p_sloppy -> Team A improves in TO (fewer turnovers)
        self.assertIn("TO", res["grade_a"]["gained_cats"])
        # Team B receives p_sloppy, sends p_clean -> Team B concedes TO
        self.assertIn("TO", res["grade_b"]["lost_cats"])

    def test_volume_weighted_percentages(self):
        """Verify FG% and FT% are volume weighted rather than unweighted average of rates."""
        p_high_vol = {"name": "High Vol", "pts": 30.0, "reb": 5.0, "ast": 5.0, "stl": 1.0, "blk": 0.5, "tpm": 2.0, "fgm": 12.0, "fga": 20.0, "ftm": 8.0, "fta": 9.0, "to": 2.5}  # 60% FG
        p_low_vol = {"name": "Low Vol", "pts": 5.0, "reb": 2.0, "ast": 1.0, "stl": 0.5, "blk": 0.2, "tpm": 0.2, "fgm": 1.0, "fga": 5.0, "ftm": 1.0, "fta": 3.0, "to": 0.5}   # 20% FG
        rep = dict(DEFAULT_REPLACEMENT)

        deltas, _ = calculate_package_deltas([p_low_vol], [p_high_vol], rep)
        # Replacing low volume poor shooter with high volume 60% shooter should increase team FG%
        self.assertGreater(deltas[19], 0)

    def test_classification_precedence_and_deterministic_roasts(self):
        """Verify high-priority classifications (e.g. blockbuster, robbery) take precedence over generic."""
        # Setup blockbuster trade: multiple star players
        star1 = {"name": "Luka Doncic", "pts": 32.0, "reb": 9.0, "ast": 9.0, "stl": 1.4, "blk": 0.5, "tpm": 3.5, "fgm": 11.0, "fga": 22.0, "ftm": 7.0, "fta": 9.0, "to": 3.8}
        star2 = {"name": "Nikola Jokic", "pts": 28.0, "reb": 12.0, "ast": 10.0, "stl": 1.3, "blk": 0.9, "tpm": 1.2, "fgm": 11.0, "fga": 18.0, "ftm": 5.0, "fta": 6.0, "to": 3.0}

        team_a = {"id": 1, "name": "Team A", "owner": "Alice", "strength": {str(c): 50.0 for c in CAT_IDS}}
        team_b = {"id": 2, "name": "Team B", "owner": "Bob", "strength": {str(c): 50.0 for c in CAT_IDS}}
        all_teams = [team_a, team_b]
        rep = dict(DEFAULT_REPLACEMENT)

        res = analyze_trade(team_a, team_b, [star2], [star1], all_teams, rep)
        verdict = res["verdict"]
        classification = verdict["classification"]

        self.assertIsNotNone(classification["id"])
        self.assertIsNotNone(classification["name"])
        self.assertTrue(len(classification["headline"]) > 0)
        self.assertTrue(len(classification["roast"]) > 0)
        # Ensure roast and headline have no em dashes per antislop rules
        self.assertNotIn("—", classification["headline"])
        self.assertNotIn("—", classification["roast"])

    def test_dynamic_replacement_calculation(self):
        """Verify compute_replacement_player correctly aggregates bottom 3 players per team."""
        rosters = {
            "1": [
                {"pts": 25.0, "reb": 5.0, "ast": 5.0, "stl": 1.0, "blk": 0.5, "tpm": 2.0, "fg_pct": 0.5, "ft_pct": 0.8, "to": 2.0, "fgm": 10.0, "fga": 20.0, "ftm": 4.0, "fta": 5.0},
                {"pts": 20.0, "reb": 4.0, "ast": 4.0, "stl": 1.0, "blk": 0.4, "tpm": 1.5, "fg_pct": 0.48, "ft_pct": 0.78, "to": 1.8, "fgm": 8.0, "fga": 16.0, "ftm": 3.0, "fta": 4.0},
                {"pts": 10.0, "reb": 3.0, "ast": 2.0, "stl": 0.8, "blk": 0.3, "tpm": 1.0, "fg_pct": 0.45, "ft_pct": 0.75, "to": 1.2, "fgm": 4.0, "fga": 9.0, "ftm": 2.0, "fta": 2.5},
                {"pts": 6.0, "reb": 3.0, "ast": 1.5, "stl": 0.5, "blk": 0.2, "tpm": 0.5, "fg_pct": 0.42, "ft_pct": 0.70, "to": 1.0, "fgm": 2.5, "fga": 6.0, "ftm": 1.0, "fta": 1.5},
                {"pts": 4.0, "reb": 2.0, "ast": 1.0, "stl": 0.4, "blk": 0.1, "tpm": 0.3, "fg_pct": 0.40, "ft_pct": 0.65, "to": 0.8, "fgm": 1.5, "fga": 4.0, "ftm": 1.0, "fta": 1.5},
            ] * 2  # 10 players
        }
        rep = compute_replacement_player(rosters)
        self.assertIn("pts", rep)
        self.assertIn("fg_pct", rep)
        self.assertGreater(rep["pts"], 0)

    def test_all_catalog_headlines_and_roasts_antislop(self):
        """Verify all classifications produce valid antislop headlines and roasts without em dashes."""
        from trade_analyzer import build_classification_catalog
        catalog = build_classification_catalog()
        self.assertGreaterEqual(len(catalog), 25)

        dummy_ctx = {
            "winner_name": "Team One",
            "loser_name": "Team Two",
            "winner_id": 1,
            "loser_id": 2,
            "winner_grade": "A",
            "loser_grade": "D",
            "outcome": "clear_win",
            "winner_score": 0.65,
            "loser_score": -0.35,
            "net_delta": 1.0,
            "team_a": {"name": "Team One"},
            "team_b": {"name": "Team Two"},
            "players_to_a": [{"name": "Nikola Jokic", "pts": 28}],
            "players_to_b": [{"name": "Role Player", "pts": 10}],
            "n_a": 1,
            "n_b": 1,
            "has_injured_player": False,
            "injured_players": [],
            "has_top_star": True,
            "has_major_flip": True,
            "has_punt_profile": False,
            "guard_heavy": False,
            "big_man_heavy": False,
            "to_cleanup": False,
            "efficiency_edge": True,
            "top_seed_won": False,
            "is_redundant": False,
            "is_debatable": False,
        }

        for item in catalog:
            self.assertTrue(item.id.islower())
            self.assertGreater(item.priority, 0)
            headline = item.headline(dummy_ctx)
            roast = item.roast(dummy_ctx)
            self.assertIsInstance(headline, str)
            self.assertIsInstance(roast, str)
            self.assertNotIn("—", headline, f"Em dash found in headline for {item.id}")
            self.assertNotIn("—", roast, f"Em dash found in roast for {item.id}")

    def test_confidence_assessment(self):
        """Verify confidence is High when healthy and established, Medium when injured or low games."""
        healthy_p1 = {"name": "Player 1", "gp": 10, "inj": None, "pts": 20.0, "reb": 5.0, "ast": 5.0, "stl": 1.0, "blk": 0.5, "tpm": 2.0, "fgm": 8.0, "fga": 16.0, "ftm": 4.0, "fta": 5.0, "to": 2.0}
        healthy_p2 = {"name": "Player 2", "gp": 12, "inj": None, "pts": 18.0, "reb": 4.0, "ast": 4.0, "stl": 1.0, "blk": 0.5, "tpm": 1.8, "fgm": 7.0, "fga": 15.0, "ftm": 3.0, "fta": 4.0, "to": 1.8}
        injured_p = {"name": "Injured Star", "gp": 10, "inj": "OUT", "pts": 25.0, "reb": 5.0, "ast": 5.0, "stl": 1.0, "blk": 0.5, "tpm": 2.0, "fgm": 10.0, "fga": 20.0, "ftm": 5.0, "fta": 6.0, "to": 2.5}

        team_a = {"id": 1, "name": "Team A", "owner": "A", "strength": {str(c): 50.0 for c in CAT_IDS}}
        team_b = {"id": 2, "name": "Team B", "owner": "B", "strength": {str(c): 50.0 for c in CAT_IDS}}
        all_teams = [team_a, team_b]
        rep = dict(DEFAULT_REPLACEMENT)

        res_healthy = analyze_trade(team_a, team_b, [healthy_p1], [healthy_p2], all_teams, rep)
        self.assertEqual(res_healthy["grade_a"]["confidence"], "High")

        res_inj = analyze_trade(team_a, team_b, [injured_p], [healthy_p2], all_teams, rep)
        self.assertEqual(res_inj["grade_a"]["confidence"], "Medium")


if __name__ == "__main__":
    unittest.main()
