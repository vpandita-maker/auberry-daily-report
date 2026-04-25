import unittest

from analyzer.complaint_spikes import (
    compute_daily_counts,
    compute_rolling_average,
    get_complaint_spikes,
)


def review(review_id, outlet_id, timestamp, sentiment="negative", categories=None):
    return {
        "review_id": review_id,
        "outlet_id": outlet_id,
        "timestamp": timestamp,
        "sentiment": sentiment,
        "categories": ["service"] if categories is None else categories,
    }


class ComplaintSpikeTests(unittest.TestCase):
    def test_detects_spike_against_previous_seven_day_average(self):
        data = []
        for day in range(1, 8):
            for item in range(2):
                data.append(review(f"history-{day}-{item}", "Kondapur", f"2026-04-{day:02d}T10:00:00+05:30"))
        for item in range(6):
            data.append(review(f"today-{item}", "Kondapur", "2026-04-08T10:00:00+05:30"))

        spikes = get_complaint_spikes(data)

        self.assertEqual(len(spikes), 1)
        self.assertEqual(spikes[0]["outlet_id"], "Kondapur")
        self.assertEqual(spikes[0]["category"], "service")
        self.assertEqual(spikes[0]["today_count"], 6)
        self.assertEqual(spikes[0]["baseline_avg"], 2.0)
        self.assertEqual(spikes[0]["spike_percent"], 200.0)
        self.assertEqual(spikes[0]["severity"], "medium")
        self.assertEqual(spikes[0]["trend"], "increasing")

    def test_handles_missing_days_as_zero_counts(self):
        data = [
            review("one", "Kondapur", "2026-04-01T10:00:00+05:30"),
            review("two", "Kondapur", "2026-04-03T10:00:00+05:30"),
        ]

        counts = compute_daily_counts(data)

        self.assertEqual(counts["daily_negative_count"].tolist(), [1, 0, 1])

    def test_triggers_zero_baseline_spike_at_minimum_count(self):
        data = [
            review("one", "Madhapur", "2026-04-05T23:00:00Z", categories=["food_quality"]),
            review("two", "Madhapur", "2026-04-05T23:15:00Z", categories=["food_quality"]),
            review("three", "Madhapur", "2026-04-05T23:30:00Z", categories=["food_quality"]),
        ]

        spikes = get_complaint_spikes(data)

        self.assertEqual(len(spikes), 1)
        self.assertEqual(spikes[0]["date"], "2026-04-06")
        self.assertEqual(spikes[0]["baseline_avg"], 0.0)
        self.assertEqual(spikes[0]["severity"], "high")

    def test_ignores_positive_reviews_and_empty_categories(self):
        data = [
            review("one", "Kondapur", "2026-04-01T10:00:00+05:30", sentiment="positive"),
            review("two", "Kondapur", "2026-04-01T10:00:00+05:30", categories=[]),
        ]

        counts = compute_daily_counts(data)
        rolling = compute_rolling_average(counts)

        self.assertTrue(counts.empty)
        self.assertTrue(rolling.empty)


if __name__ == "__main__":
    unittest.main()
