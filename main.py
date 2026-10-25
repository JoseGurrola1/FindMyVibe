import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from places import get_places
from gemini_ai import (
    ask_question,
    create_search_query,
    choose_place
)
from fallback import fallback_question, offline_places

log = logging.getLogger("findmyvibe")

app = FastAPI()

# Let the Next.js dev server (on another port) call this API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)

# Broad search used when a specific query comes back empty.
BROAD_QUERY = "things to do"

# Last successful SerpApi results per city, reused if SerpApi goes down.
_last_good_places: dict[str, list] = {}


@app.get("/")
def home():
    return {"message": "FindMyVibe API is running!"}


@app.get("/api/places")
def search_places(query: str, city: str = "Austin TX"):
    try:
        places = get_places(query, city)

        return {
            "query": query,
            "city": city,
            "count": len(places),
            "places": places
        }

    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Oops! My crystal ball is having trouble finding places. Try again!"
        )


def find_places(query, city):
    """
    Search SerpApi, falling back step by step:
      1. the real query
      2. a broad query, if the real one found nothing
      3. the last good results for this city, if SerpApi errored
      4. saved Austin data (places.json)
    """
    city_key = city.strip().lower()

    try:
        places = get_places(query, city)
        if not places and query != BROAD_QUERY:
            log.warning("No results for %r; trying a broad search.", query)
            places = get_places(BROAD_QUERY, city)
        if places:
            _last_good_places[city_key] = places
            return places
    except Exception:
        log.exception("SerpApi search failed; using fallback places.")

    if _last_good_places.get(city_key):
        return _last_good_places[city_key]

    return offline_places(city)


class Answer(BaseModel):
    question: str
    answer: str


class GameRequest(BaseModel):
    city: str = "Austin TX"
    history: list[Answer] = Field(default_factory=list)
    rejected_ids: list[str] = Field(default_factory=list)
    rejection_feedback: list[str] = Field(default_factory=list)


@app.post("/api/game/next")
def next_turn(game: GameRequest):
    history = [
        answer.model_dump()
        for answer in game.history
    ]
    rejected = set(game.rejected_ids)

    try:
        # Initial round: ask 3 questions.
        # Each rejected guess adds one follow-up question.
        required_answers = 3 + len(rejected)

        if len(history) < required_answers:
            question = ask_question(
                history,
                game.rejection_feedback
            )

            return {
                "action": "ask_question",
                **question
            }

        # Generate a search query using preferences
        search_query = create_search_query(history, game.rejection_feedback)

        # Retrieve real places (with fallbacks)
        places = find_places(search_query, game.city)

        # Pick a non-rejected place (Gemini, or the built-in fallback)
        guess = choose_place(history, places, rejected)

        # Everything from that search was rejected: widen the net once.
        if guess is None and search_query != BROAD_QUERY:
            places = find_places(BROAD_QUERY, game.city)
            guess = choose_place(history, places, rejected)

        if guess is None:
            return {
                "action": "no_match",
                "message": "No matching places found."
            }

        return {
            "action": "guess",
            "search_query": search_query,
            **guess
        }

    except Exception:
        # Last line of defense: never leave the player on an error screen.
        log.exception("Game turn failed; sending a fallback question.")
        return {
            "action": "ask_question",
            **fallback_question(history, game.rejection_feedback)
        }
