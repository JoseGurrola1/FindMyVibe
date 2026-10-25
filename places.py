import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("SERPAPI_KEY")


def get_places(query, city="Austin TX"):
    """
    Search Google Maps through SerpApi.

    Args:
        query: What the user wants to do.
        city: The city to search in.

    Returns:
        List of matching locations.
    """

    if not API_KEY:
        raise ValueError("Missing SERPAPI_KEY")

    # SerpApi takes the key in the URL, and requests puts the full URL
    # (key included) in its error messages. Re-raise without the original
    # error ("from None") so the key never shows up in logs or tracebacks.
    try:
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
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        raise RuntimeError(f"SerpApi returned HTTP {status}") from None
    except requests.RequestException as exc:
        raise RuntimeError(
            f"SerpApi request failed ({type(exc).__name__})"
        ) from None
    except ValueError:
        raise RuntimeError("SerpApi returned invalid JSON") from None

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
            # Opening hours, e.g. {"friday": "11 AM–2 AM", ...}, and live
            # status like "Open ⋅ Closes 10 PM" (see hours.py).
            "operating_hours": place.get("operating_hours"),
            "open_state": place.get("open_state"),
        })

    return places


# Only execute this when running places.py directly
if __name__ == "__main__":
    results = get_places("romantic date spots")
    for place in results:
        print(place)
