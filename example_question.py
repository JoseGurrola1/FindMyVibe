"""Run with: python example_question.py (requires server-side GEMINI_API_KEY)."""

import sys
from pathlib import Path

from dotenv import load_dotenv

from gemini_questions import QuestionGenerationError, SessionData, generate_next_question


def main():
    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
    session = SessionData(
        location="Austin, TX",
        active_preferences={"setting": "outdoors", "budget": "low cost"},
        previous_questions=[
            "Would you prefer to be indoors or outdoors?",
            "How much would you like to spend?",
        ],
        answers=["Outdoors", "Low cost"],
    )
    try:
        question = generate_next_question(session)
    except QuestionGenerationError as exc:
        print(f"Question generation failed: {exc}", file=sys.stderr)
        return 1
    print(question.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
