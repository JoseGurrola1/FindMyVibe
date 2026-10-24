from fastapi import FastAPI, HTTPException
from places import get_places

app = FastAPI()


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

    
from pydantic import BaseModel, Field
from gemini_ai import (
    ask_question,
    create_search_query,
    choose_place
)


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
    try:
        history = [
            answer.model_dump()
            for answer in game.history
        ]

        rejected = set(game.rejected_ids)

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
        search_query = create_search_query(history)

        # Retrieve real places from SerpApi
        places = get_places(search_query, game.city)

        # Have Gemini select a non-rejected place
        guess = choose_place(
            history,
            places,
            rejected
        )

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
        import logging
        logging.exception("Game turn failed")

        raise HTTPException(
            status_code=502,
            detail="Unable to generate the next game turn"
        )

