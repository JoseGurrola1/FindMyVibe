import os
import json
import logging
from google import genai
from google.genai import types
from pydantic import BaseModel
from dotenv import load_dotenv

from fallback import (
    fallback_question,
    fallback_search_query,
    fallback_choose,
    validate_question,
    is_rejected,
    parse_intro_fallback,
    city_is_grounded,
    mentions_place,
)

load_dotenv()

log = logging.getLogger("findmyvibe.gemini")

MODEL = "gemini-3.5-flash-lite"


PREFERENCE_RULES = """
CRITICAL USER PREFERENCE RULES:

- The user's latest explicit preference ALWAYS overrides
  conflicting previous preferences.
- Users can change their minds at any point.
- If the user says "actually", "never mind", "instead",
  or corrects themselves, immediately adapt.
- NEVER recommend an activity the user explicitly
  said they no longer want.
- Keep earlier preferences only if they don't conflict
  with newer ones.
- Never try to convince the user to return to an
  earlier preference.
- If the user changes activity categories, abandon
  the old category immediately.
- A new correction overrides multiple older answers.
- Interpret the user's answer based on its actual meaning,
  even if it doesn't directly answer the question.

PRIORITY: What the user wants NOW matters most.
"""


def _context_block(context):
    """Describe the player's start-screen answers (city, what, when) for prompts."""
    context = context or {}
    lines = []
    if context.get("city"):
        lines.append(f"- City: {context['city']}")
    if context.get("what"):
        lines.append(f"- What they're in the mood for: {context['what']}")
    if context.get("when"):
        lines.append(f"- When they're going: {context['when']}")
    if not lines:
        return ""
    return (
        "Player's starting details (given before the first question; later\n"
        "answers may refine or override them):\n" + "\n".join(lines) + "\n"
    )


# Give up on Gemini after this long and use the built-in fallback instead.
GEMINI_TIMEOUT_MS = 15_000

# If the key is missing, run in fallback-only mode instead of crashing.
_api_key = os.getenv("GEMINI_API_KEY")
if _api_key:
    client = genai.Client(
        api_key=_api_key,
        http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS),
    )
else:
    client = None
    log.warning("GEMINI_API_KEY is missing; using built-in fallbacks only.")


# Define the formats Gemini must return
class Question(BaseModel):
    question: str
    options: list[str]
    # Short hint shown in the "type your own answer" box.
    placeholder: str = ""


class IntroParse(BaseModel):
    city: str
    what: str
    when: str


class SearchPlan(BaseModel):
    search_query: str


class PlaceGuess(BaseModel):
    candidate_id: int
    reason: str


def _generate(prompt, schema):
    """Call Gemini and parse the JSON reply. Raises on any failure."""
    if client is None:
        raise RuntimeError("Gemini is not configured")

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
        ),
    )
    return schema.model_validate_json(response.text)


def parse_intro(text):
    """
    Split the start-screen sentence into {"city", "what", "when"}.
    Uses Gemini, falling back to simple pattern matching. "city" is ""
    if the player didn't name a place (we never guess one).
    """
    text = " ".join(str(text or "").split())[:200]
    prompt = f"""
    A player typed this to start a place-finding game:
    {json.dumps(text)}

    Extract:
    - city: the city or town they named, formatted like "Austin, TX" or
      "Paris, France" when the state/country is obvious. If they named a
      neighborhood or area, put the city here and keep the neighborhood in
      "what". Use "" if no place is named. NEVER guess a city.
    - what: what they want to do or find (e.g. "live music", "tacos").
      "" if not said.
    - when: when they're going (e.g. "tonight after 8pm"). "" if not said.
    """
    try:
        parsed = _generate(prompt, IntroParse)
        city = parsed.city.strip()[:80]
        # Drop a city the model may have invented: keep it only if it matches
        # the player's words, or they clearly named some place ("in ATX").
        if city and not (city_is_grounded(city, text) or mentions_place(text)):
            log.warning("Ignoring city %r not found in the player's text.", city)
            city = ""
        return {"city": city, "what": parsed.what.strip()[:120], "when": parsed.when.strip()[:120]}
    except Exception:
        log.exception("Gemini intro parsing failed; using fallback.")
    parsed = parse_intro_fallback(text)
    return {k: v[:120] for k, v in parsed.items()}


def ask_question(history, rejection_feedback=None, context=None):
    """Generate a question using previous answers and rejections."""

    rejection_feedback = rejection_feedback or []

    prompt = f"""
    {PREFERENCE_RULES}

    You are FindMyVibe, an Akinator-style location game.

    Your goal is to discover the user's ideal real-world
    place or activity.

    {_context_block(context)}
    Previous questions and answers:
    {json.dumps(history)}

    Previous rejection feedback:
    {json.dumps(rejection_feedback)}

    Generate ONE useful follow-up question.

    Rules:
    - Provide 2 to 4 distinct answer options.
    - Do not repeat previous questions.
    - Use earlier answers and rejection feedback.
    - Ask questions that narrow down their preferences.
    - If a place was rejected, focus on learning why
      other locations might be a better fit.
    - Keep the question short and conversational.
    - Also give a "placeholder": a short hint (under 60 characters) for
      players who'd rather type their own answer, nudging them to be
      specific with a concrete example, e.g. "Be specific, e.g. 'rooftop
      bar with a view'". Match it to this question.
    - Never ask which city; it is already chosen.
    - Don't re-ask anything the starting details already answer
      (e.g. what they want or when they're going); build on it.
    """

    try:
        question = validate_question(
            _generate(prompt, Question).model_dump(),
            history,
        )
        if question is not None:
            return question
        log.warning("Gemini question was unusable; using fallback.")
    except Exception:
        log.exception("Gemini question failed; using fallback.")

    return fallback_question(history, rejection_feedback, context)


def create_search_query(history, rejection_feedback=None, context=None):
    """Turn user answers into a Google Maps search query."""

    prompt = f"""
    {PREFERENCE_RULES}

    {_context_block(context)}

    Conversation history (oldest first, newest last):
{json.dumps(history)}

Previous rejection feedback:
{json.dumps(rejection_feedback or [])}

IMPORTANT:
- Generate the search based on the user's CURRENT preferences.
- If newer answers contradict older answers, use the newer ones.
- Do not search for activities the user explicitly rejected.

    Generate ONE concise Google Maps search query
    for finding suitable real-world destinations.

    Do not include the city.
    Examples of search styles:
    quiet coffee shops
    scenic outdoor activities
    interactive museums
    """

    try:
        query = _generate(prompt, SearchPlan).search_query.strip()
        # Guard against empty or rambling queries.
        if query and len(query) <= 80:
            return query
        log.warning("Gemini search query was unusable; using fallback.")
    except Exception:
        log.exception("Gemini search query failed; using fallback.")

    return fallback_search_query(history, rejection_feedback, context)


def choose_place(history, places, rejected_ids, context=None):
    """Choose a real candidate, never invent a location."""

    candidates = [
        {"candidate_id": i, **place}
        for i, place in enumerate(places)
        if not is_rejected(place, rejected_ids)
    ]

    if not candidates:
        return None

    prompt = f"""
    {PREFERENCE_RULES}

    You are recommending a place for FindMyVibe.

    Your goal is to select the real location that best
    matches the user's preferences.

    {_context_block(context)}
    User answers:
    {json.dumps(history)}

    Available REAL locations:
    {json.dumps(candidates)}

    INSTRUCTIONS:
    1. Choose the best matching candidate_id.
    2. Only choose a candidate from the provided list.
    3. Explain briefly why it matches the user's vibe.

    RECOMMENDATION RULES:
    - Only use facts supported by the provided location data.
    - Never infer crowd levels from review counts.
    - Never invent prices, opening hours, or amenities.
    - If an attribute is unknown, acknowledge uncertainty.
    - Explain why the location may match the user's vibe.
    - Do not claim the venue is empty unless verified.
    - Never recommend a rejected place.
    - Do not make unsupported assumptions about a place.
    """

    try:
        guess = _generate(prompt, PlaceGuess)

        # Validate Gemini's selection against real candidates
        allowed = {p["candidate_id"]: p for p in candidates}
        chosen = allowed.get(guess.candidate_id)

        if chosen is not None and guess.reason.strip():
            return {
                "place": {
                    k: v for k, v in chosen.items()
                    if k != "candidate_id"
                },
                "reason": guess.reason.strip(),
            }
        log.warning("Gemini picked an invalid candidate; using fallback.")
    except Exception:
        log.exception("Gemini place choice failed; using fallback.")

    return fallback_choose(history, places, rejected_ids, context)
