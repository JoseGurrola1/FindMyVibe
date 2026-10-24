import os
import requests
from dotenv import load_dotenv

# Load variables from .env
load_dotenv()

API_KEY = os.getenv("SERPAPI_KEY")

if not API_KEY:
    raise ValueError("Missing SERPAPI_KEY in .env")

# Make a request to SerpApi
response = requests.get(
    "https://serpapi.com/search.json",
    params={
        "engine": "google_maps",
        "q": "fun things to do in Austin TX",
        "ll": "@30.2672,-97.7431,13z",
        "type": "search",
        "api_key": API_KEY
    },
    timeout=20
)

response.raise_for_status()
data = response.json()

# Check for errors from SerpApi
if "error" in data:
    raise RuntimeError(data["error"])

# Extract useful information
places = []

for place in data.get("local_results", []):
    places.append({
        "name": place.get("title"),
        "place_id": place.get("place_id"),
        "rating": place.get("rating"),
        "category": place.get("type"),
        "address": place.get("address"),
        "coordinates": place.get("gps_coordinates")
    })

for place in places:
    print(place)


import json

with open("places.json", "w", encoding="utf-8") as file:
    json.dump(places, file, indent=2)

print(f"Saved {len(places)} locations to places.json")
