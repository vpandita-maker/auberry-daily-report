from datetime import date


DEFAULT_DAYS_FORWARD = 7
DEFAULT_BASELINE_DAILY_REVENUE = 50000
MIN_RATING = 1.0
MAX_RATING = 5.0
TREND_THRESHOLD = 0.02


def _clamp_rating(value):
    return max(MIN_RATING, min(MAX_RATING, value))


def _parse_date(value):
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _normalize_timeseries(outlet_timeseries_data):
    rows = []
    for row in outlet_timeseries_data or []:
        if "date" not in row or "avg_rating" not in row:
            raise ValueError("Each timeseries row must include date and avg_rating")
        rows.append(
            {
                "date": _parse_date(row["date"]),
                "avg_rating": float(row["avg_rating"]),
            }
        )
    return sorted(rows, key=lambda item: item["date"])


def _calculate_slope(rows):
    if len(rows) < 2:
        return 0.0

    first = rows[0]
    last = rows[-1]
    elapsed_days = (last["date"] - first["date"]).days
    if elapsed_days <= 0:
        elapsed_days = len(rows) - 1
    if elapsed_days <= 0:
        return 0.0

    return (last["avg_rating"] - first["avg_rating"]) / elapsed_days


def _detect_trend(slope):
    if slope < -TREND_THRESHOLD:
        return "declining"
    if slope > TREND_THRESHOLD:
        return "improving"
    return "stable"


def _calculate_confidence(rows, slope):
    if len(rows) < 7:
        return "low"
    if abs(slope) < TREND_THRESHOLD:
        return "low"
    return "medium"


def generate_rating_trajectory(
    outlet_timeseries_data,
    days_forward=DEFAULT_DAYS_FORWARD,
    baseline_daily_revenue=DEFAULT_BASELINE_DAILY_REVENUE,
):
    rows = _normalize_timeseries(outlet_timeseries_data)
    if not rows:
        return {
            "trend": "stable",
            "current_rating": None,
            "predicted_rating_7d": None,
            "days_forward": days_forward,
            "rating_change": 0.0,
            "revenue_impact_percent": 0.0,
            "estimated_revenue_loss": 0,
            "confidence": "low",
        }

    current_rating = _clamp_rating(rows[-1]["avg_rating"])
    slope = _calculate_slope(rows)
    predicted_rating = _clamp_rating(current_rating + (slope * days_forward))
    rating_change = predicted_rating - current_rating
    revenue_impact_percent = rating_change * 20
    projected_revenue_delta = baseline_daily_revenue * (revenue_impact_percent / 100) * days_forward
    estimated_revenue_loss = max(0, abs(projected_revenue_delta)) if projected_revenue_delta < 0 else 0

    return {
        "trend": _detect_trend(slope),
        "current_rating": round(current_rating, 2),
        "predicted_rating_7d": round(predicted_rating, 2),
        "days_forward": days_forward,
        "rating_change": round(rating_change, 2),
        "revenue_impact_percent": round(revenue_impact_percent, 2),
        "estimated_revenue_loss": round(estimated_revenue_loss),
        "confidence": _calculate_confidence(rows, slope),
    }
