import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from places import get_places
from gemini_ai import (
    ask_question,
    create_search_query,
    choose_place,
    parse_intro,
)
from fallback import fallback_question, offline_places
from ratelimit import limiters_from_env

log = logging.getLogger("findmyvibe")

app = FastAPI()

# Rate limits (see ratelimit.py). Read after the imports above have
# loaded .env, so limits can be tuned there.
RATE_LIMIT_ENABLED, visitor_limiter, global_limiter = limiters_from_env()


def client_ip(request: Request) -> str:
    # Behind Caddy, uvicorn's proxy-header support (on by default for
    # connections from 127.0.0.1) already replaces this with the visitor's
    # real IP from X-Forwarded-For.
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if RATE_LIMIT_ENABLED and request.url.path.startswith("/api/"):
        ip = client_ip(request)
        wait = visitor_limiter.hit(ip)
        if wait is None:
            wait = global_limiter.hit("all")
            if wait is not None:
                log.warning("Global rate limit reached; asking %s to wait %ss", ip, wait)
        if wait is not None:
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(wait)},
                content={
                    "detail": "Too many requests. Please slow down.",
                    "retry_after": wait,
                },
            )
    return await call_next(request)


# Added after the rate limiter so CORS headers also apply to 429 replies.
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
    # First turn: the start-screen sentence, e.g. "tacos in Austin tonight".
    # The reply includes the parsed "context" (city / what / when), which
    # the frontend sends back as the fields below on every later turn.
    intro: str = Field("", max_length=200)
    city: str = Field("Austin TX", max_length=80)
    what: str = Field("", max_length=120)
    when: str = Field("", max_length=120)
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

    if game.intro.strip():
        context = parse_intro(game.intro)
        if not context["city"]:
            return {
                "action": "need_city",
                "message": "Which city should Puss search? Add one, e.g. \"tacos in Austin, TX\".",
                "context": context,
            }
    else:
        # Blank city falls back to Austin so older clients keep working.
        context = {
            "city": game.city.strip() or "Austin TX",
            "what": game.what.strip(),
            "when": game.when.strip(),
        }
    city = context["city"]

    try:
        # Initial round: ask 3 questions.
        # Each rejected guess adds one follow-up question.
        required_answers = 3 + len(rejected)

        if len(history) < required_answers:
            question = ask_question(
                history,
                game.rejection_feedback,
                context,
            )

            return {
                "action": "ask_question",
                "context": context,
                **question
            }

        # Generate a search query using preferences
        search_query = create_search_query(history, game.rejection_feedback, context)

        # Retrieve real places (with fallbacks)
        places = find_places(search_query, city)

        # Pick a non-rejected place (Gemini, or the built-in fallback)
        guess = choose_place(history, places, rejected, context)

        # Everything from that search was rejected: widen the net once.
        if guess is None and search_query != BROAD_QUERY:
            places = find_places(BROAD_QUERY, city)
            guess = choose_place(history, places, rejected, context)

        if guess is None:
            return {
                "action": "no_match",
                "context": context,
                "message": f"No matching places found in {city}."
            }

        return {
            "action": "guess",
            "context": context,
            "search_query": search_query,
            **guess
        }

    except Exception:
        # Last line of defense: never leave the player on an error screen.
        log.exception("Game turn failed; sending a fallback question.")
        return {
            "action": "ask_question",
            "context": context,
            **fallback_question(history, game.rejection_feedback, context)
        }
