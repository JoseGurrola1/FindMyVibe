import os
import json
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

MODEL = "gemini-3.5-flash-lite"


# Define the formats Gemini must return
class Question(BaseModel):
    question: str
    options: list[str]


class SearchPlan(BaseModel):
    search_query: str


class PlaceGuess(BaseModel):
    candidate_id: int
    reason: str


def ask_question(history):
    """Generate the next question based on previous answers."""

    prompt = f"""
    You are FindMyVibe, an Akinator-style game.

    Your goal is to discover what type of real-world
    place or activity the user wants.

    Previous questions and answers:
    {json.dumps(history)}

    Generate ONE fun, conversational question.

    Rules:
    - Provide 2 to 4 distinct answer options.
    - Do not repeat previous questions.
    - Use previous answers to ask smarter questions.
    - Narrow down mood, activity, setting, and budget.
    - Keep the question short.
    """

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=Question
        )
    )

    return Question.model_validate_json(response.text).model_dump()


def create_search_query(history):
    """Turn user answers into a Google Maps search query."""

    prompt = f"""
    Based on these user preferences:
    {json.dumps(history)}

    Generate ONE concise Google Maps search query
    for finding suitable real-world destinations.

    Do not include the city.
    Examples of search styles:
    quiet coffee shops
    scenic outdoor activities
    interactive museums
    """

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SearchPlan
        )
    )

    return SearchPlan.model_validate_json(
        response.text
    ).search_query


def choose_place(history, places, rejected_ids):
    """Choose a real candidate, never invent a location."""

    candidates = [
        {"candidate_id": i, **place}
        for i, place in enumerate(places)
        if place.get("place_id") not in rejected_ids
    ]

    if not candidates:
        return None

    prompt = f"""
    You are recommending a place for FindMyVibe.

    User answers:
    {json.dumps(history)}

    Available REAL locations:
    {json.dumps(candidates)}

    Choose the best matching candidate_id.

    Explain briefly why it matches the user's vibe.
    Only choose a candidate from the provided list.
    """

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=PlaceGuess
        )
    )

    guess = PlaceGuess.model_validate_json(response.text)

    # Validate Gemini's selection against real candidates
    allowed = {p["candidate_id"]: p for p in candidates}
    chosen = allowed.get(guess.candidate_id)

    if chosen is None:
        raise ValueError("Gemini selected an invalid candidate")

    return {
        "place": {
            k: v for k, v in chosen.items()
            if k != "candidate_id"
        },
        "reason": guess.reason
    }
