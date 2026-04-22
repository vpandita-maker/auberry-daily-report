import os
import re
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import requests
from dotenv import load_dotenv

load_dotenv()


def _format_review_timestamp(timestamp_value):
    if not timestamp_value:
        return None, "", ""

    if isinstance(timestamp_value, (int, float)):
        review_dt = datetime.fromtimestamp(timestamp_value, UTC)
        return int(timestamp_value), review_dt.strftime("%Y-%m-%d"), review_dt.strftime("%Y-%m-%d %H:%M UTC")

    try:
        review_dt = datetime.fromisoformat(str(timestamp_value).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None, "", ""

    return int(review_dt.timestamp()), review_dt.strftime("%Y-%m-%d"), review_dt.strftime("%Y-%m-%d %H:%M UTC")


def _normalize_review_text(text):
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _fetch_place_review_links(place_id, api_key):
    url = f"https://places.googleapis.com/v1/places/{place_id}"
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "reviews.rating,reviews.relativePublishTimeDescription,reviews.publishTime,"
            "reviews.text.text,reviews.authorAttribution.displayName,reviews.googleMapsUri"
        ),
    }
    response = requests.get(
        url,
        headers=headers,
        params={"languageCode": "en"},
        timeout=20,
    )
    response.raise_for_status()
    result = response.json()

    links = {}
    for review in result.get("reviews", []):
        author = (review.get("authorAttribution") or {}).get("displayName", "")
        text = (review.get("text") or {}).get("text", "")
        rating = review.get("rating")
        key = (
            str(author).strip().lower(),
            _normalize_review_text(text),
            str(rating or ""),
        )
        google_maps_uri = str(review.get("googleMapsUri", "")).strip()
        if google_maps_uri and key not in links:
            links[key] = google_maps_uri
    return links

def find_place_id(restaurant_name):
    api_key = os.getenv("GOOGLE_PLACES_API_KEY")
    
    url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
    params = {
        "input": restaurant_name,
        "inputtype": "textquery",
        "fields": "place_id,name,formatted_address",
        "key": api_key
    }
    
    response = requests.get(url, params=params)
    data = response.json()
    
    candidates = data.get("candidates", [])
    if candidates:
        place = candidates[0]
        print(f"Found: {place['name']}")
        print(f"Address: {place['formatted_address']}")
        print(f"Place ID: {place['place_id']}")
        return place["place_id"]
    
    print("No place found")
    return None


def get_google_reviews(place_id):
    api_key = os.getenv("GOOGLE_PLACES_API_KEY")
    place_url = f"https://www.google.com/maps/search/?api=1&query_place_id={place_id}"
    review_links = {}
    try:
        review_links = _fetch_place_review_links(place_id, api_key)
    except requests.RequestException as exc:
        print(f"Places API (New) review link fetch failed for {place_id}: {exc}. Falling back to place-level Maps URLs.")

    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "name,formatted_address,rating,reviews,user_ratings_total",
        "key": api_key,
        "language": "en",
        "reviews_sort": "newest",
    }

    response = requests.get(url, params=params, timeout=20)
    data = response.json()

    if "result" not in data:
        print("Error fetching reviews:", data)
        return []

    result = data["result"]
    print(f"\nRestaurant: {result.get('name')}")
    print(f"Overall rating: {result.get('rating')}")
    print(f"Total ratings: {result.get('user_ratings_total')}")
    formatted_address = result.get("formatted_address", "")
    place_name = result.get("name", "")

    reviews = []
    for r in result.get("reviews", []):
        timestamp, exact_date, exact_datetime = _format_review_timestamp(r.get("time"))
        author = r.get("author_name", "")
        text = r.get("text", "")
        rating = r.get("rating")
        review_key = (
            str(author).strip().lower(),
            _normalize_review_text(text),
            str(rating or ""),
        )
        reviews.append({
            "source": "Google",
            "rating": rating,
            "text": text,
            "author": author,
            "author_url": r.get("author_url", ""),
            "date": r.get("relative_time_description", ""),
            "date_exact": exact_date,
            "date_time_exact": exact_datetime,
            "timestamp": timestamp,
            "outlet_address": formatted_address,
            "place_name": place_name,
            "place_id": place_id,
            "source_url": review_links.get(review_key) or place_url,
        })

    print(f"Reviews fetched: {len(reviews)}\n")
    return reviews


def extract_place_id_from_google_url(source_url):
    parsed = urlparse(source_url)
    query_params = parse_qs(parsed.query)

    for key in ("q", "query", "place_id"):
        for value in query_params.get(key, []):
            match = re.search(r"(ChI[A-Za-z0-9_-]{20,})", value)
            if match:
                return match.group(1)

    if parsed.path:
        match = re.search(r"(ChI[A-Za-z0-9_-]{20,})", parsed.path)
        if match:
            return match.group(1)

    try:
        response = requests.get(source_url, allow_redirects=True, timeout=20)
        candidates = [
            response.url,
            response.text,
        ]
    except requests.RequestException:
        return None

    for candidate in candidates:
        match = re.search(r"(ChI[A-Za-z0-9_-]{20,})", candidate)
        if match:
            return match.group(1)

    return None
