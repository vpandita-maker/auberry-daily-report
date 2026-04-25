import unittest

from analyzer.outlet_ranking import (
    calculate_gap,
    compute_outlet_metrics,
    filter_reviews_by_date,
    get_outlet_ranking,
)


def review(review_id, outlet_id, timestamp, rating, sentiment):
    return {
        "review_id": review_id,
        "outlet_id": outlet_id,
        "timestamp": timestamp,
        "rating": rating,
        "sentiment": sentiment,
    }


class OutletRankingTests(unittest.TestCase):
    def test_ranks_outlets_and_calculates_gap(self):
        data = [
            review("a1", "Banjara Hills", "2026-04-23T10:00:00+05:30", 5, "positive"),
            review("a2", "Banjara Hills", "2026-04-23T11:00:00+05:30", 4, "positive"),
            review("a3", "Banjara Hills", "2026-04-23T12:00:00+05:30", 4, "neutral"),
            review("b1", "Kondapur", "2026-04-23T10:00:00+05:30", 3, "neutral"),
            review("b2", "Kondapur", "2026-04-23T11:00:00+05:30", 4, "positive"),
            review("b3", "Kondapur", "2026-04-23T12:00:00+05:30", 2, "negative"),
        ]

        result = get_outlet_ranking(data, "2026-04-23")

        self.assertEqual(result["ranked_outlets"][0]["outlet_id"], "Banjara Hills")
        self.assertEqual(result["ranked_outlets"][0]["rank"], 1)
        self.assertEqual(result["ranked_outlets"][0]["avg_rating"], 4.33)
        self.assertEqual(result["ranked_outlets"][0]["positive_ratio"], 0.67)
        self.assertEqual(result["ranked_outlets"][0]["score"], 3.93)
        self.assertEqual(result["summary"]["best_outlet"], "Banjara Hills")
        self.assertEqual(result["summary"]["worst_outlet"], "Kondapur")
        self.assertEqual(result["summary"]["rating_gap"], 1.33)
        self.assertEqual(result["summary"]["score_gap"], 1.47)

    def test_falls_back_to_last_available_day_on_or_before_selected_date(self):
        data = [
            review("old", "Kondapur", "2026-04-21T10:00:00+05:30", 3, "neutral"),
            review("latest", "Madhapur", "2026-04-22T10:00:00+05:30", 5, "positive"),
        ]

        filtered = filter_reviews_by_date(data, "2026-04-23")

        self.assertEqual(filtered["review_id"].tolist(), ["latest"])

    def test_uses_ist_date_conversion(self):
        data = [
            review("late", "Kondapur", "2026-04-22T20:00:00Z", 5, "positive"),
        ]

        filtered = filter_reviews_by_date(data, "2026-04-23")

        self.assertEqual(filtered["review_id"].tolist(), ["late"])

    def test_marks_low_confidence_for_under_three_reviews(self):
        data = [
            review("one", "Kondapur", "2026-04-23T10:00:00+05:30", 5, "positive"),
            review("two", "Kondapur", "2026-04-23T11:00:00+05:30", 4, "positive"),
        ]

        result = get_outlet_ranking(data, "2026-04-23")

        self.assertTrue(result["ranked_outlets"][0]["low_confidence"])

    def test_status_labels_top_and_underperforming_groups(self):
        data = []
        for index in range(5):
            outlet = f"Outlet {index + 1}"
            rating = 5 - index
            for review_index in range(3):
                data.append(
                    review(
                        f"{outlet}-{review_index}",
                        outlet,
                        "2026-04-23T10:00:00+05:30",
                        rating,
                        "positive" if index < 2 else "negative",
                    )
                )

        result = get_outlet_ranking(data, "2026-04-23")

        self.assertEqual(result["ranked_outlets"][0]["status"], "top")
        self.assertEqual(result["ranked_outlets"][-1]["status"], "underperforming")

    def test_empty_data_returns_empty_ranking_and_summary(self):
        result = get_outlet_ranking([], "2026-04-23")

        self.assertEqual(result["ranked_outlets"], [])
        self.assertEqual(
            result["summary"],
            {
                "best_outlet": None,
                "worst_outlet": None,
                "rating_gap": 0.0,
                "score_gap": 0.0,
            },
        )

    def test_compute_metrics_counts_positive_ratio(self):
        filtered = [
            review("one", "Kondapur", "2026-04-23T10:00:00+05:30", 5, "positive"),
            review("two", "Kondapur", "2026-04-23T11:00:00+05:30", 3, "negative"),
        ]

        metrics = compute_outlet_metrics(filtered)

        self.assertEqual(metrics.iloc[0]["review_count"], 2)
        self.assertEqual(metrics.iloc[0]["positive_ratio"], 0.5)


if __name__ == "__main__":
    unittest.main()
