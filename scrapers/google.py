import os
import re
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import requests
from dotenv import load_dotenv

load_dotenv()

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
    
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields": "name,formatted_address,rating,reviews,user_ratings_total",
        "key": api_key,
        "language": "en",
        "reviews_sort": "newest",
    }
    
    response = requests.get(url, params=params)
    data = response.json()
    
    if "result" not in data:
        print("Error fetching reviews:", data)
        return []
    
    result = data["result"]
    print(f"\nRestaurant: {result.get('name')}")
    print(f"Overall rating: {result.get('rating')}")
    print(f"Total ratings: {result.get('user_ratings_total')}")
    formatted_address = result.get("formatted_address", "")
    
    reviews = []
    for r in result.get("reviews", []):
        timestamp = r.get("time")
        exact_date = ""
        if timestamp:
            exact_date = datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d")
        reviews.append({
            "source": "Google",
            "rating": r.get("rating"),
            "text": r.get("text", ""),
            "author": r.get("author_name", ""),
            "date": r.get("relative_time_description", ""),
            "date_exact": exact_date,
            "timestamp": timestamp,
            "outlet_address": formatted_address,
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
