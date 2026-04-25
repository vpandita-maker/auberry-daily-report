from collections import Counter
from datetime import UTC, datetime
from zoneinfo import ZoneInfo


IST = ZoneInfo("Asia/Kolkata")
MIN_PATTERN_COUNT = 2

ITEM_KEYWORDS = (
    "paneer tikka",
    "biscoff donut",
    "double chocolate donut",
    "custard croissant",
    "donut",
    "croissant",
    "coffee",
    "cake",
    "pastry",
    "bread",
    "puff",
    "sandwich",
)


def _review_datetime_ist(review):
    timestamp = review.get("timestamp")
    if timestamp:
        try:
            return datetime.fromtimestamp(float(timestamp), UTC).astimezone(IST)
        except (TypeError, ValueError):
            pass

    value = review.get("timestamp_iso") or review.get("date_time") or review.get("date")
    if not value:
        value = timestamp
    if value:
        text = str(value).strip()
        for fmt in ("%Y-%m-%d %H:%M UTC", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=UTC).astimezone(IST)
            except ValueError:
                pass
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(IST)
    return None


def _time_bucket(hour):
    start = (hour // 2) * 2
    end = start + 2
    return f"{start:02d}:00-{end:02d}:00"


def _mentioned_item(text):
    normalized = str(text or "").lower()
    for item in ITEM_KEYWORDS:
        if item in normalized:
            return item
    return None


def _negative_reviews(data):
    reviews = []
    for review in data or []:
        sentiment = str(review.get("sentiment", "")).strip().lower()
        if sentiment != "negative":
            continue
        review_dt = _review_datetime_ist(review)
        if not review_dt:
            continue
        reviews.append({**review, "review_dt": review_dt})
    return reviews


def get_root_cause_patterns(data):
    negative_reviews = _negative_reviews(data)
    if not negative_reviews:
        return []

    time_outlet_counts = Counter()
    item_counts = Counter()
    category_outlet_counts = Counter()

    for review in negative_reviews:
        outlet_id = str(review.get("outlet_id", "Unknown outlet"))
        text = str(review.get("text", ""))
        bucket = _time_bucket(review["review_dt"].hour)
        time_outlet_counts[(outlet_id, bucket)] += 1

        item = _mentioned_item(text)
        if item:
            item_counts[item] += 1

        for category in review.get("categories") or []:
            category_outlet_counts[(outlet_id, str(category))] += 1

    patterns = []
    for (outlet_id, bucket), count in time_outlet_counts.items():
        if count >= MIN_PATTERN_COUNT:
            patterns.append(
                {
                    "pattern_type": "time_outlet",
                    "message": f"Negative reviews cluster around {bucket} at {outlet_id}.",
                    "outlet_id": outlet_id,
                    "time_window": bucket,
                    "count": count,
                    "severity": "high" if count >= 4 else "medium",
                }
            )

    for item, count in item_counts.items():
        if count >= MIN_PATTERN_COUNT:
            patterns.append(
                {
                    "pattern_type": "item",
                    "message": f"{item.title()} was mentioned negatively {count} times.",
                    "item": item,
                    "count": count,
                    "severity": "high" if count >= 4 else "medium",
                }
            )

    for (outlet_id, category), count in category_outlet_counts.items():
        if count >= MIN_PATTERN_COUNT:
            patterns.append(
                {
                    "pattern_type": "category_outlet",
                    "message": f"{category.replace('_', ' ').title()} complaints repeat at {outlet_id}.",
                    "outlet_id": outlet_id,
                    "category": category,
                    "count": count,
                    "severity": "high" if count >= 4 else "medium",
                }
            )

    return sorted(patterns, key=lambda item: (-item["count"], item["pattern_type"], item["message"]))[:5]
