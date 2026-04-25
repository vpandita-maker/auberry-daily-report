from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd


IST = ZoneInfo("Asia/Kolkata")
LOW_CONFIDENCE_THRESHOLD = 3


def _empty_reviews_frame():
    return pd.DataFrame(
        columns=[
            "review_id",
            "outlet_id",
            "timestamp",
            "rating",
            "sentiment",
            "date",
        ]
    )


def _empty_metrics_frame():
    return pd.DataFrame(
        columns=[
            "outlet_id",
            "avg_rating",
            "review_count",
            "positive_ratio",
            "low_confidence",
        ]
    )


def _normalize_selected_date(date):
    if date is None:
        return (datetime.now(IST) - timedelta(days=1)).date()
    return pd.Timestamp(date).tz_localize(None).date()


def _normalize_reviews(data):
    frame = pd.DataFrame(data)
    if frame.empty:
        return _empty_reviews_frame()

    required_columns = {"review_id", "outlet_id", "timestamp", "rating", "sentiment"}
    missing_columns = required_columns - set(frame.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Missing required review fields: {missing}")

    frame = frame.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    frame["rating"] = pd.to_numeric(frame["rating"], errors="coerce")
    frame["sentiment"] = frame["sentiment"].astype(str).str.strip().str.lower()
    frame = frame.dropna(subset=["timestamp", "rating"])
    frame["date"] = frame["timestamp"].dt.tz_convert(IST).dt.date
    return frame


def filter_reviews_by_date(data, date=None):
    reviews = _normalize_reviews(data)
    if reviews.empty:
        return _empty_reviews_frame()

    selected_date = _normalize_selected_date(date)
    filtered = reviews[reviews["date"] == selected_date].copy()
    if not filtered.empty:
        return filtered

    available_dates = reviews.loc[reviews["date"] <= selected_date, "date"]
    if available_dates.empty:
        available_dates = reviews["date"]
    fallback_date = available_dates.max()
    return reviews[reviews["date"] == fallback_date].copy()


def compute_outlet_metrics(filtered_data):
    reviews = pd.DataFrame(filtered_data)
    if reviews.empty:
        return _empty_metrics_frame()

    metrics = (
        reviews.groupby("outlet_id")
        .agg(
            avg_rating=("rating", "mean"),
            review_count=("review_id", "count"),
            positive_reviews=("sentiment", lambda series: (series == "positive").sum()),
        )
        .reset_index()
    )
    metrics["positive_ratio"] = metrics["positive_reviews"] / metrics["review_count"]
    metrics["low_confidence"] = metrics["review_count"] < LOW_CONFIDENCE_THRESHOLD
    return metrics.drop(columns=["positive_reviews"])


def compute_scores(metrics):
    if metrics.empty:
        scored = _empty_metrics_frame()
        scored["score"] = pd.Series(dtype="float64")
        return scored

    scored = metrics.copy()
    positive_ratio_normalized = scored["positive_ratio"] * 5
    scored["score"] = (0.6 * scored["avg_rating"]) + (0.4 * positive_ratio_normalized)
    return scored


def rank_outlets(metrics):
    if metrics.empty:
        ranked = compute_scores(metrics)
        ranked["rank"] = pd.Series(dtype="int64")
        ranked["status"] = pd.Series(dtype="object")
        return ranked

    ranked = compute_scores(metrics).sort_values(
        ["score", "avg_rating", "positive_ratio", "review_count", "outlet_id"],
        ascending=[False, False, False, False, True],
    )
    ranked["rank"] = range(1, len(ranked) + 1)
    ranked["status"] = "middle"

    group_size = len(ranked)
    status_size = max(1, int(group_size * 0.2))
    ranked.loc[ranked["rank"] <= status_size, "status"] = "top"
    ranked.loc[ranked["rank"] > group_size - status_size, "status"] = "underperforming"
    if group_size == 1:
        ranked["status"] = "top"

    return ranked.reset_index(drop=True)


def calculate_gap(ranked_outlets):
    if ranked_outlets.empty:
        return {
            "best_outlet": None,
            "worst_outlet": None,
            "rating_gap": 0.0,
            "score_gap": 0.0,
        }

    ranked = ranked_outlets.sort_values("rank")
    best = ranked.iloc[0]
    worst = ranked.iloc[-1]
    return {
        "best_outlet": best["outlet_id"],
        "worst_outlet": worst["outlet_id"],
        "rating_gap": round(float(best["avg_rating"] - worst["avg_rating"]), 2),
        "score_gap": round(float(best["score"] - worst["score"]), 2),
    }


def _format_ranked_outlets(ranked_outlets):
    records = []
    for row in ranked_outlets.sort_values("rank").itertuples(index=False):
        records.append(
            {
                "outlet_id": row.outlet_id,
                "avg_rating": round(float(row.avg_rating), 2),
                "review_count": int(row.review_count),
                "positive_ratio": round(float(row.positive_ratio), 2),
                "score": round(float(row.score), 2),
                "rank": int(row.rank),
                "low_confidence": bool(row.low_confidence),
                "status": row.status,
            }
        )
    return records


def get_outlet_ranking(data, date=None):
    filtered_reviews = filter_reviews_by_date(data, date)
    metrics = compute_outlet_metrics(filtered_reviews)
    ranked_outlets = rank_outlets(metrics)
    return {
        "ranked_outlets": _format_ranked_outlets(ranked_outlets),
        "summary": calculate_gap(ranked_outlets),
    }
