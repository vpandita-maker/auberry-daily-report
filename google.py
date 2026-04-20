import requests
import os
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
    
    print("Raw response:", data)
    
    candidates = data.get("candidates", [])
    if candidates:
        place = candidates[0]
        print(f"\nFound: {place['name']}")
        print(f"Address: {place['formatted_address']}")
        print(f"Place ID: {place['place_id']}")
        return place["place_id"]
    
    print("No place found")
    return NoneGOOGLE_PLACES_API_KEY=AIzaSyA8s5HdVl6TR-t7YsCFWKKEwvo2AvL87Xg

