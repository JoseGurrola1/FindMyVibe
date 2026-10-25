"""
Deterministic fallbacks for FindMyVibe.

Used whenever Gemini or SerpApi fails, times out, or returns something
we can't use, so the game always has a next step to show.
Nothing here calls an external API.
"""

import json
import math
import re
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
        "placeholder": "Be specific, e.g. 'axe throwing' or 'ramen'",
    },
    {
        "question": "Pick a vibe:",
        "options": [
            "Chill and cozy",
            "Lively and social",
            "Quirky and unusual",
            "Romantic",
        ],
        "placeholder": "Describe it, e.g. 'dim lights, jazz, low-key'",
    },
    {
        "question": "What's the budget looking like?",
        "options": ["Free or cheap", "Moderate", "Treat myself"],
        "placeholder": "Name a number, e.g. 'under $20 a person'",
    },
    {
        "question": "Indoors or outdoors?",
        "options": ["Indoors", "Outdoors", "Either works"],
        "placeholder": "e.g. 'a shady patio if it's not too hot'",
    },
    {
        "question": "Who's coming with you?",
        "options": ["Just me", "A date", "Friends", "Family with kids"],
        "placeholder": "e.g. 'a group of 6, one vegetarian'",
    },
    {
        "question": "When are you heading out?",
        "options": ["Morning", "Afternoon", "Evening", "Late night"],
        "placeholder": "e.g. 'Saturday around 2pm'",
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
        "placeholder": "Say what to change, e.g. 'closer and less pricey'",
    },
    {
        "question": "Should I stay close to that idea or switch it up?",
        "options": ["Similar, just a better fit", "Something completely different"],
        "placeholder": "e.g. 'same vibe, but with live music'",
    },
    {
        "question": "What matters most for the next guess?",
        "options": [
            "Great reviews",
            "Unique and memorable",
            "Easy and low-key",
            "Good for a group",
        ],
        "placeholder": "e.g. 'good for a first date'",
    },
]


def _norm(text):
    return " ".join(str(text or "").lower().split())


def asked_questions(history):
    return {_norm(item.get("question")) for item in history}


# Built-in questions the start screen's What / When boxes already answer.
WHAT_QUESTION = "What kind of outing are you craving?"
WHEN_QUESTION = "When are you heading out?"


def fallback_question(history, rejection_feedback=None, context=None):
    """Return the next unasked built-in question."""
    rejection_feedback = rejection_feedback or []
    context = context or {}
    asked = asked_questions(history)
    if context.get("what"):
        asked.add(_norm(WHAT_QUESTION))
    if context.get("when"):
        asked.add(_norm(WHEN_QUESTION))

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
        "placeholder": "e.g. 'something I can't do back home'",
        "fallback": True,
    }


# Hint for the "type your own answer" box when a question doesn't have one.
DEFAULT_PLACEHOLDER = "Not listed? Be specific, e.g. 'quiet patio with tacos'"


def clean_placeholder(text):
    """Keep a short, single-line hint; otherwise use the default."""
    text = " ".join(str(text or "").split())
    return text if 3 <= len(text) <= 70 else DEFAULT_PLACEHOLDER


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

    return {
        "question": question,
        "options": options,
        "placeholder": clean_placeholder(data.get("placeholder")),
    }


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


def fallback_search_query(history, rejection_feedback=None, context=None):
    """Build a simple Google Maps query from keywords in the answers."""
    rejection_feedback = rejection_feedback or []
    context = context or {}
    text = " ".join(
        [_norm(context.get("what")), _norm(context.get("when"))]
        + [_norm(item.get("answer")) for item in history]
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


def fallback_rank(history, places, rejected_ids, context=None, limit=1):
    """
    The best-rated non-rejected places (up to `limit`), with a small bonus
    for places whose name/category mention something the user asked for.
    """
    candidates = [p for p in places if not is_rejected(p, rejected_ids)]
    wanted = fallback_search_query(history, None, context).split()

    def score(place):
        rating = place.get("rating") or 0
        reviews = place.get("reviews") or 0
        value = rating * math.log10(reviews + 10)
        label = _norm(f"{place.get('name')} {place.get('category')}")
        if any(word.rstrip("s") in label for word in wanted if word != "things"):
            value += 2
        return value

    return sorted(candidates, key=score, reverse=True)[:limit]


def fallback_choose(history, places, rejected_ids, context=None):
    """Pick the single best place (see fallback_rank)."""
    ranked = fallback_rank(history, places, rejected_ids, context, limit=1)
    if not ranked:
        return None
    return {"place": ranked[0], "reason": grounded_reason(ranked[0]), "fallback": True}


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


# ---------------------------------------------------------------------------
# Start-screen sentence -> city / what / when (used when Gemini is down)
# ---------------------------------------------------------------------------


_TIME = re.compile(
    r"\b(?:tonight|today|tomorrow(?: (?:morning|afternoon|evening|night))?"
    r"|this (?:morning|afternoon|evening|weekend|week)|right now|late night"
    r"|(?:this |next |on )?(?:mon|tues|wednes|thurs|fri|satur|sun)day"
    r"(?: (?:morning|afternoon|evening|night|brunch|lunch|dinner))?"
    r"|(?:after|before|around|at|by) \d{1,2}(?::\d{2})?\s*(?:am|pm)?"
    r"|\d{1,2}(?::\d{2})?\s*(?:am|pm)"
    r"|morning|afternoon|evening)\b",
    re.IGNORECASE,
)
_PLACE = re.compile(r"\b(?:in|near|around)\s+(.+)$", re.IGNORECASE)
_NOT_A_CITY = ("a ", "an ", "the ", "my ", "some ", "somewhere", "town", "the city")


def parse_intro_fallback(text):
    """
    Best-effort split of e.g. "live music in Austin, TX tonight" into
    {"city": "Austin, TX", "what": "live music", "when": "tonight"}.
    City is "" when none is found.
    """
    text = " ".join(str(text or "").split())
    when = ", ".join(m.group(0) for m in _TIME.finditer(text))
    rest = " ".join(_TIME.sub(" ", text).split()).strip(" ,.;!-")

    city, what = "", rest
    match = _PLACE.search(rest)
    # Prefer a city after "in"/"near" ("Denver omelette in Austin" -> Austin).
    known = None
    if match and "," not in match.group(1):
        inside = _find_known_city(match.group(1))
        if inside:
            known = (inside[0], match.start(), len(rest))
    if not known and not (match and "," in match.group(1)):
        known = _find_known_city(rest)
    if known:
        # A well-known city anywhere in the sentence: "Austin picnic evening"
        city, start, end = known
        what = " ".join((rest[:start] + " " + rest[end:]).split()).strip(" ,.;!-")
        what = re.sub(r"\b(?:in|near|around)$", "", what).strip(" ,.;!-")
    elif match:
        candidate = match.group(1).strip(" ,.;!-")
        if candidate and not candidate.lower().startswith(_NOT_A_CITY) and len(candidate.split()) <= 4:
            city = candidate
            what = rest[: match.start()].strip(" ,.;!-")
    elif "," in rest and len(rest.split()) <= 4:
        # Just a place, e.g. "Austin, TX"
        city, what = rest, ""

    if city and city.islower():
        city = city.title()
    return {"city": city, "what": what, "when": when}


def _find_known_city(text):
    """(formatted city, start, end) for the longest known city named in text."""
    from known_cities import KNOWN_CITIES
    low = text.lower()
    for name in sorted(KNOWN_CITIES, key=len, reverse=True):
        # Two-letter nicknames (LA, SF, DC) only count in capitals, so "la"
        # in "la croix" or "dc" in prose don't trigger.
        flags = 0 if len(name) <= 2 else re.IGNORECASE
        target = name.upper() if len(name) <= 2 else name
        m = re.search(rf"(?<![\w-]){re.escape(target)}(?![\w-])(?:,\s*[A-Za-z]{{2}}\b)?", text, flags)
        if m:
            return KNOWN_CITIES[name], m.start(), m.end()
    return None


def city_is_grounded(city, text):
    """
    True if the city plausibly comes from the player's own words (guards
    against the model inventing a city). Accepts "NYC" -> "New York, NY",
    "Philly" -> "Philadelphia, PA".
    """
    words = re.findall(r"[a-z]+", _norm(text))
    name = re.findall(r"[a-z]+", _norm(str(city).split(",")[0]))
    if not name or not words:
        return False
    initials = "".join(w[0] for w in name)
    for w in words:
        if len(initials) >= 2 and w.startswith(initials):
            return True
        for n in name:
            if len(n) >= 3 and (w == n or (len(w) >= 4 and len(n) >= 4 and w[:4] == n[:4])):
                return True
    return False


def mentions_place(text):
    """
    Did the player name some place ("in ATX", "near the Big Apple")?
    Generic phrases like "in a quiet place" don't count.
    """
    if parse_intro_fallback(text)["city"]:
        return True
    match = _PLACE.search(" ".join(str(text or "").split()))
    return bool(match and re.search(r"\b[A-Z][a-zA-Z]", match.group(1)))
