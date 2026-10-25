import os
import requests
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List

load_dotenv()

API_KEY = os.getenv("SERPAPI_KEY")

app = FastAPI()

# Allow Next.js (running on localhost:3000) to call this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_places(query, city="Austin TX"):
    if not API_KEY:
        raise ValueError("Missing SERPAPI_KEY")

    response = requests.get(
        "https://serpapi.com/search.json",
        params={
            "engine": "google_maps",
            "q": f"{query} in {city}",
            "type": "search",
            "api_key": API_KEY,
        },
        timeout=20,
    )

    response.raise_for_status()
    data = response.json()

    if "error" in data:
        raise RuntimeError(data["error"])

    places = []
    for place in data.get("local_results", []):
        places.append({
            "name": place.get("title"),
            "place_id": place.get("place_id"),
            "rating": place.get("rating"),
            "reviews": place.get("reviews"),
            "category": place.get("type"),
            "address": place.get("address"),
            "thumbnail": place.get("thumbnail"),
            "coordinates": place.get("gps_coordinates"),
        })

    return places


class VibeRequest(BaseModel):
    answers: List[str]


@app.post("/api/find-vibe")
def find_vibe_endpoint(req: VibeRequest):
    # Combine user questionnaire answers into a single search query
    combined_query = " ".join([a for a in req.answers if a.strip()])
    results = get_places(combined_query)
    return {"places": results}


if __name__ == "__main__":
    results = get_places("romantic date spots")
    for place in results:
        print(place)