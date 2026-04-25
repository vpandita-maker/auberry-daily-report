from zoneinfo import ZoneInfo

import pandas as pd


IST = ZoneInfo("Asia/Kolkata")
SPIKE_MIN_COUNT = 3


def _empty_counts_frame():
    return pd.DataFrame(
        columns=[
            "outlet_id",
            "category",
            "date",
            "daily_negative_count",
        ]
    )


def _empty_rolling_frame():
    frame = _empty_counts_frame()
    frame["baseline_avg"] = pd.Series(dtype="float64")
    frame["previous_day_count"] = pd.Series(dtype="int64")
    frame["trend"] = pd.Series(dtype="object")
    return frame


def _normalize_reviews(data):
    frame = pd.DataFrame(data)
    if frame.empty:
        return frame

    required_columns = {"outlet_id", "timestamp", "sentiment", "categories"}
    missing_columns = required_columns - set(frame.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Missing required review fields: {missing}")

    frame = frame.copy()
    frame["sentiment"] = frame["sentiment"].astype(str).str.strip().str.lower()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["timestamp"])
    frame["date"] = frame["timestamp"].dt.tz_convert(IST).dt.normalize()
    return frame


def compute_daily_counts(data):
    reviews = _normalize_reviews(data)
    if reviews.empty:
        return _empty_counts_frame()

    negative_reviews = reviews[reviews["sentiment"] == "negative"].copy()
    if negative_reviews.empty:
        return _empty_counts_frame()

    negative_reviews["categories"] = negative_reviews["categories"].apply(
        lambda value: value if isinstance(value, list) else []
    )
    negative_reviews = negative_reviews.explode("categories")
    negative_reviews = negative_reviews.dropna(subset=["categories"])
    negative_reviews["category"] = negative_reviews["categories"].astype(str).str.strip()
    negative_reviews = negative_reviews[negative_reviews["category"] != ""]

    if negative_reviews.empty:
        return _empty_counts_frame()

    grouped = (
        negative_reviews.groupby(["outlet_id", "category", "date"], as_index=False)
        .size()
        .rename(columns={"size": "daily_negative_count"})
    )

    filled_groups = []
    for (outlet_id, category), group in grouped.groupby(["outlet_id", "category"], sort=False):
        dates = pd.date_range(group["date"].min(), group["date"].max(), freq="D", tz=IST)
        filled = (
            group.set_index("date")[["daily_negative_count"]]
            .reindex(dates, fill_value=0)
            .rename_axis("date")
            .reset_index()
        )
        filled["outlet_id"] = outlet_id
        filled["category"] = category
        filled["daily_negative_count"] = filled["daily_negative_count"].astype(int)
        filled_groups.append(filled[["outlet_id", "category", "date", "daily_negative_count"]])

    return pd.concat(filled_groups, ignore_index=True).sort_values(
        ["outlet_id", "category", "date"]
    )


def compute_rolling_average(counts, window=7):
    if counts.empty:
        return _empty_rolling_frame()

    rolling = counts.copy().sort_values(["outlet_id", "category", "date"])
    grouped = rolling.groupby(["outlet_id", "category"])["daily_negative_count"]
    rolling["baseline_avg"] = grouped.transform(
        lambda series: series.shift(1).rolling(window=window, min_periods=1).mean().fillna(0)
    )
    rolling["previous_day_count"] = grouped.shift(1).fillna(0).astype(int)
    rolling["trend"] = "stable"
    rolling.loc[rolling["daily_negative_count"] > rolling["previous_day_count"], "trend"] = "increasing"
    rolling.loc[rolling["daily_negative_count"] < rolling["previous_day_count"], "trend"] = "decreasing"
    return rolling


def detect_spikes(counts, rolling_avg):
    if counts.empty or rolling_avg.empty:
        return rolling_avg.iloc[0:0].copy()

    spikes = rolling_avg.copy()
    ratio_rule = spikes["daily_negative_count"] >= (2 * spikes["baseline_avg"])
    zero_baseline_rule = (spikes["baseline_avg"] == 0) & (
        spikes["daily_negative_count"] >= SPIKE_MIN_COUNT
    )
    minimum_count_rule = spikes["daily_negative_count"] >= SPIKE_MIN_COUNT
    spikes = spikes[(minimum_count_rule & ratio_rule) | zero_baseline_rule].copy()

    spikes["spike_percent"] = 0.0
    non_zero_baseline = spikes["baseline_avg"] > 0
    spikes.loc[non_zero_baseline, "spike_percent"] = (
        (spikes.loc[non_zero_baseline, "daily_negative_count"] - spikes.loc[non_zero_baseline, "baseline_avg"])
        / spikes.loc[non_zero_baseline, "baseline_avg"]
        * 100
    )
    spikes.loc[~non_zero_baseline, "spike_percent"] = spikes.loc[
        ~non_zero_baseline, "daily_negative_count"
    ] * 100

    spikes["severity"] = "medium"
    spikes.loc[spikes["daily_negative_count"] > (3 * spikes["baseline_avg"]), "severity"] = "high"
    spikes.loc[spikes["baseline_avg"] == 0, "severity"] = "high"
    return spikes


def format_spike_output(spikes):
    if spikes.empty:
        return []

    output = spikes.sort_values(["spike_percent", "daily_negative_count"], ascending=[False, False])
    records = []
    for row in output.itertuples(index=False):
        records.append(
            {
                "outlet_id": row.outlet_id,
                "category": row.category,
                "date": row.date.strftime("%Y-%m-%d"),
                "today_count": int(row.daily_negative_count),
                "baseline_avg": round(float(row.baseline_avg), 2),
                "spike_percent": round(float(row.spike_percent), 2),
                "severity": row.severity,
                "trend": row.trend,
            }
        )
    return records


def get_complaint_spikes(data):
    counts = compute_daily_counts(data)
    rolling_avg = compute_rolling_average(counts)
    spikes = detect_spikes(counts, rolling_avg)
    return format_spike_output(spikes)
