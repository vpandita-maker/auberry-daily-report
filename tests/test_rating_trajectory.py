import unittest

from analyzer.rating_trajectory import generate_rating_trajectory


class RatingTrajectoryTests(unittest.TestCase):
    def test_declining_trajectory_estimates_rating_and_loss(self):
        data = [
            {"date": "2026-04-10", "avg_rating": 4.2},
            {"date": "2026-04-11", "avg_rating": 4.1},
            {"date": "2026-04-12", "avg_rating": 4.1},
            {"date": "2026-04-13", "avg_rating": 4.0},
            {"date": "2026-04-14", "avg_rating": 3.9},
            {"date": "2026-04-15", "avg_rating": 3.9},
            {"date": "2026-04-16", "avg_rating": 3.8},
        ]

        result = generate_rating_trajectory(data)

        self.assertEqual(result["trend"], "declining")
        self.assertEqual(result["current_rating"], 3.8)
        self.assertEqual(result["predicted_rating_7d"], 3.33)
        self.assertEqual(result["days_forward"], 7)
        self.assertEqual(result["rating_change"], -0.47)
        self.assertEqual(result["revenue_impact_percent"], -9.33)
        self.assertEqual(result["estimated_revenue_loss"], 32667)
        self.assertEqual(result["confidence"], "medium")

    def test_stable_trajectory_has_low_confidence_and_no_loss(self):
        data = [
            {"date": "2026-04-10", "avg_rating": 4.0},
            {"date": "2026-04-11", "avg_rating": 4.0},
            {"date": "2026-04-12", "avg_rating": 4.0},
            {"date": "2026-04-13", "avg_rating": 4.0},
            {"date": "2026-04-14", "avg_rating": 4.0},
            {"date": "2026-04-15", "avg_rating": 4.0},
            {"date": "2026-04-16", "avg_rating": 4.0},
        ]

        result = generate_rating_trajectory(data)

        self.assertEqual(result["trend"], "stable")
        self.assertEqual(result["confidence"], "low")
        self.assertEqual(result["estimated_revenue_loss"], 0)

    def test_improving_trajectory_has_no_revenue_loss(self):
        data = [
            {"date": "2026-04-10", "avg_rating": 3.5},
            {"date": "2026-04-11", "avg_rating": 3.6},
            {"date": "2026-04-12", "avg_rating": 3.7},
            {"date": "2026-04-13", "avg_rating": 3.8},
            {"date": "2026-04-14", "avg_rating": 3.9},
            {"date": "2026-04-15", "avg_rating": 4.0},
            {"date": "2026-04-16", "avg_rating": 4.1},
        ]

        result = generate_rating_trajectory(data)

        self.assertEqual(result["trend"], "improving")
        self.assertGreater(result["revenue_impact_percent"], 0)
        self.assertEqual(result["estimated_revenue_loss"], 0)

    def test_less_than_seven_points_sets_low_confidence(self):
        data = [
            {"date": "2026-04-15", "avg_rating": 4.0},
            {"date": "2026-04-16", "avg_rating": 3.8},
        ]

        result = generate_rating_trajectory(data)

        self.assertEqual(result["trend"], "declining")
        self.assertEqual(result["confidence"], "low")

    def test_prediction_is_clamped_between_one_and_five(self):
        data = [
            {"date": "2026-04-10", "avg_rating": 1.4},
            {"date": "2026-04-11", "avg_rating": 1.3},
            {"date": "2026-04-12", "avg_rating": 1.2},
            {"date": "2026-04-13", "avg_rating": 1.1},
            {"date": "2026-04-14", "avg_rating": 1.0},
            {"date": "2026-04-15", "avg_rating": 1.0},
            {"date": "2026-04-16", "avg_rating": 1.0},
        ]

        result = generate_rating_trajectory(data)

        self.assertEqual(result["predicted_rating_7d"], 1.0)

    def test_custom_revenue_baseline_is_used(self):
        data = [
            {"date": "2026-04-10", "avg_rating": 4.0},
            {"date": "2026-04-11", "avg_rating": 3.9},
            {"date": "2026-04-12", "avg_rating": 3.8},
            {"date": "2026-04-13", "avg_rating": 3.7},
            {"date": "2026-04-14", "avg_rating": 3.6},
            {"date": "2026-04-15", "avg_rating": 3.5},
            {"date": "2026-04-16", "avg_rating": 3.4},
        ]

        result = generate_rating_trajectory(data, baseline_daily_revenue=100000)

        self.assertEqual(result["estimated_revenue_loss"], 98000)

    def test_empty_input_returns_low_confidence_empty_prediction(self):
        result = generate_rating_trajectory([])

        self.assertEqual(result["trend"], "stable")
        self.assertIsNone(result["current_rating"])
        self.assertIsNone(result["predicted_rating_7d"])
        self.assertEqual(result["estimated_revenue_loss"], 0)
        self.assertEqual(result["confidence"], "low")


if __name__ == "__main__":
    unittest.main()
