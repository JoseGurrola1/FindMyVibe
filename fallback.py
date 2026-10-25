"""
Deterministic fallbacks for FindMyVibe.

Used whenever Gemini or SerpApi fails, times out, or returns something
we can't use, so the game always has a next step to show.
Nothing here calls an external API.
"""

import json
import math
from pathlib import Path


# ---------------------------------------------------------------------------
# Questions
# ---------------------------------------------------------------------------

# Broad opening questions, asked in this order.
QUESTION_BANK = [
    {
        "question": "What kind of outing are you craving?",
        "options": [
            "Food & drinks",
            "Something active or outdoors",
            "Arts, culture or museums",
            "Games, music or nightlife",
        ],
    },
    {
        "question": "Pick a vibe:",
        "options": [
            "Chill and cozy",
            "Lively and social",
            "Quirky and unusual",
            "Romantic",
        ],
    },
    {
        "question": "What's the budget looking like?",
        "options": ["Free or cheap", "Moderate", "Treat myself"],
    },
    {
        "question": "Indoors or outdoors?",
        "options": ["Indoors", "Outdoors", "Either works"],
    },
    {
        "question": "Who's coming with you?",
        "options": ["Just me", "A date", "Friends", "Family with kids"],
    },
    {
        "question": "When are you heading out?",
        "options": ["Morning", "Afternoon", "Evening", "Late night"],
    },
]

# Asked right after the user rejects a guess.
REJECTION_BANK = [
    {
        "question": "Got it. What should the next spot lean toward?",
        "options": [
            "Quieter and more relaxed",
            "Cheaper",
            "More hands-on things to do",
            "A totally different kind of place",
        ],
    },
    {
        "question": "Should I stay close to that idea or switch it up?",
        "options": ["Similar, just a better fit", "Something completely different"],
    },
    {
        "question": "What matters most for the next guess?",
        "options": [
            "Great reviews",
            "Unique and memorable",
            "Easy and low-key",
            "Good for a group",
        ],
    },
]


def _norm(text):
    return " ".join(str(text or "").lower().split())


def asked_questions(history):
    return {_norm(item.get("question")) for item in history}


def fallback_question(history, rejection_feedback=None):
    """Return the next unasked built-in question."""
    rejection_feedback = rejection_feedback or []
    asked = asked_questions(history)

    banks = [QUESTION_BANK]
    # Once the opening questions are done and the user has rejected a
    # guess, prefer the follow-ups written for rejections.
    if rejection_feedback and len(history) >= 3:
        banks = [REJECTION_BANK, QUESTION_BANK]

    for bank in banks:
        for item in bank:
            if _norm(item["question"]) not in asked:
                return {**item, "fallback": True}

    # Every built-in question has been used: make a unique last-resort one.
    n = len(history) + 1
    return {
        "question": f"Question {n}: which sounds best right now?",
        "options": ["Somewhere new", "An old favorite type of place", "Surprise me"],
        "fallback": True,
    }


def validate_question(data, history):
    """
    Clean up a question from Gemini.

    Returns the cleaned question, or None if it can't be used
    (missing text, fewer than 2 options, or a repeat).
    """
    if not isinstance(data, dict):
        return None

    question = str(data.get("question") or "").strip()
    if not question or _norm(question) in asked_questions(history):
        return None

    options = []
    seen = set()
    for option in data.get("options") or []:
        option = str(option or "").strip()
        if option and _norm(option) not in seen:
            seen.add(_norm(option))
            options.append(option)

    options = options[:4]
    if len(options) < 2:
        return None

    return {"question": question, "options": options}


# ---------------------------------------------------------------------------
# Search query
# ---------------------------------------------------------------------------

# Words in answers/feedback -> what kind of place to search for.
PLACE_KEYWORDS = [
    (("coffee", "cafe", "café"), "cafes"),
    (("food", "eat", "dinner", "lunch", "brunch", "restaurant"), "restaurants"),
    (("drink", "bar", "cocktail", "beer", "wine"), "bars"),
    (("museum", "art", "culture", "history", "gallery"), "museums"),
    (("game", "arcade", "bowling"), "arcades"),
    (("music", "concert", "live"), "live music venues"),
    (("nightlife", "late night", "club"), "nightlife"),
    (("hike", "nature", "park", "outdoor", "outside"), "parks"),
    (("active", "sport", "hands-on", "adventure"), "activities"),
    (("shop", "market", "store"), "shops"),
]

# Words in answers/feedback -> a describing word for the search.
VIBE_KEYWORDS = [
    (("chill", "cozy", "relax", "low-key"), "cozy"),
    (("quiet", "crowded", "loud"), "quiet"),
    (("lively", "social", "group", "party"), "lively"),
    (("quirky", "unusual", "weird", "unique", "memorable"), "unique"),
    (("romantic", "date"), "romantic"),
    (("cheap", "free", "budget", "expensive"), "cheap"),
    (("kids", "family"), "family friendly"),
    (("patio",), "patio"),
]


def _match(text, table, limit):
    found = []
    for words, term in table:
        if term not in found and any(w in text for w in words):
            found.append(term)
    return found[:limit]


def fallback_search_query(history, rejection_feedback=None):
    """Build a simple Google Maps query from keywords in the answers."""
    rejection_feedback = rejection_feedback or []
    text = " ".join(
        [_norm(item.get("answer")) for item in history]
        + [_norm(reason) for reason in rejection_feedback]
    )

    vibes = _match(text, VIBE_KEYWORDS, limit=2)
    places = _match(text, PLACE_KEYWORDS, limit=1)
    noun = places[0] if places else "things to do"

    return " ".join(vibes + [noun])


# ---------------------------------------------------------------------------
# Choosing a place
# ---------------------------------------------------------------------------

def is_rejected(place, rejected_ids):
    """The frontend sends place_id, or the name when there is no id."""
    return (
        place.get("place_id") in rejected_ids
        or place.get("name") in rejected_ids
    )


def fallback_choose(history, places, rejected_ids):
    """
    Pick the best-rated non-rejected place, with a small bonus for places
    whose name/category mention something the user asked for.
    """
    candidates = [p for p in places if not is_rejected(p, rejected_ids)]
    if not candidates:
        return None

    wanted = fallback_search_query(history).split()

    def score(place):
        rating = place.get("rating") or 0
        reviews = place.get("reviews") or 0
        value = rating * math.log10(reviews + 10)
        label = _norm(f"{place.get('name')} {place.get('category')}")
        if any(word.rstrip("s") in label for word in wanted if word != "things"):
            value += 2
        return value

    chosen = max(candidates, key=score)
    return {"place": chosen, "reason": grounded_reason(chosen), "fallback": True}


def grounded_reason(place):
    """A reason built only from fields we actually have."""
    category = place.get("category") or "spot"
    article = "an" if category[:1].lower() in "aeiou" else "a"
    rating = place.get("rating")
    reviews = place.get("reviews")

    if rating and reviews:
        detail = f" rated {rating}★ across {reviews:,} Google reviews"
    elif rating:
        detail = f" rated {rating}★ on Google"
    else:
        detail = ""

    return (
        f"It's {article} {category.lower()}{detail}, and it's the strongest "
        f"match I found for your answers."
    )


# ---------------------------------------------------------------------------
# Offline places
# ---------------------------------------------------------------------------

OFFLINE_FILE = Path(__file__).with_name("places.json")


def offline_places(city):
    """Saved Austin results, for when SerpApi is down. Austin only."""
    if "austin" not in _norm(city):
        return []
    try:
        places = json.loads(OFFLINE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [{**p, "source": "offline"} for p in places if p.get("name")]
