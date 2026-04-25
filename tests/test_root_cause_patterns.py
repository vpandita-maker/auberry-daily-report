import unittest

from analyzer.root_cause_patterns import get_root_cause_patterns


def review(review_id, outlet_id, timestamp, text, categories=None):
    return {
        "review_id": review_id,
        "outlet_id": outlet_id,
        "timestamp": timestamp,
        "sentiment": "negative",
        "categories": categories or ["service"],
        "text": text,
    }


class RootCausePatternTests(unittest.TestCase):
    def test_detects_time_outlet_category_and_item_patterns(self):
        data = [
            review("one", "Kondapur", "2026-04-24 07:00 UTC", "Slow service and stale paneer tikka", ["service", "food_quality"]),
            review("two", "Kondapur", "2026-04-24 07:30 UTC", "Bad service, paneer tikka was cold", ["service", "food_quality"]),
        ]

        patterns = get_root_cause_patterns(data)
        messages = [pattern["message"] for pattern in patterns]

        self.assertIn("Negative reviews cluster around 12:00-14:00 at Kondapur.", messages)
        self.assertIn("Paneer Tikka was mentioned negatively 2 times.", messages)
        self.assertIn("Service complaints repeat at Kondapur.", messages)

    def test_returns_empty_when_no_negative_reviews(self):
        patterns = get_root_cause_patterns(
            [
                {
                    "review_id": "one",
                    "outlet_id": "Kondapur",
                    "timestamp": "2026-04-24T10:00:00+05:30",
                    "sentiment": "positive",
                    "categories": ["service"],
                    "text": "Great service",
                }
            ]
        )

        self.assertEqual(patterns, [])


if __name__ == "__main__":
    unittest.main()
