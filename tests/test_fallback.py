"""
Fallback tests: the game must keep going when Gemini or SerpApi fails.

Run from the project root:  python -m pytest tests/test_fallback.py -v
No API keys or network needed.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

import gemini_ai
import main
from fallback import QUESTION_BANK, REJECTION_BANK, fallback_search_query

client = TestClient(main.app)

SAMPLE = [
    {"name": "Quiet Cafe", "place_id": "p1", "rating": 4.6, "reviews": 900, "category": "Cafe"},
    {"name": "Loud Bar", "place_id": "p2", "rating": 4.2, "reviews": 3000, "category": "Bar"},
    {"name": "Tiny Museum", "place_id": "p3", "rating": 4.9, "reviews": 120, "category": "Museum"},
]


def boom(*args, **kwargs):
    raise RuntimeError("simulated outage")


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    main._last_good_places.clear()
    # Default: Gemini is down for every test unless a test overrides it.
    monkeypatch.setattr(gemini_ai, "_generate", boom)


def turn(history, rejected=(), feedback=(), city="Austin TX"):
    res = client.post("/api/game/next", json={
        "city": city,
        "history": history,
        "rejected_ids": list(rejected),
        "rejection_feedback": list(feedback),
    })
    assert res.status_code == 200, res.text
    return res.json()


def answer_first_option(history, data):
    assert data["action"] == "ask_question"
    assert 2 <= len(data["options"]) <= 4
    return history + [{"question": data["question"], "answer": data["options"][0]}]


def test_full_game_with_gemini_and_serpapi_down(monkeypatch):
    monkeypatch.setattr(main, "get_places", boom)

    history = []
    for _ in range(3):
        data = turn(history)
        assert data.get("fallback") is True
        history = answer_first_option(history, data)

    questions = [h["question"] for h in history]
    assert len(set(questions)) == 3, "fallback must not repeat questions"

    first = turn(history)
    assert first["action"] == "guess"
    assert first["place"]["source"] == "offline"   # saved Austin data
    assert first["reason"]

    # Reject it: expect a rejection follow-up, then a different place.
    rejected = [first["place"]["place_id"]]
    feedback = ["Too expensive"]
    follow_up = turn(history, rejected, feedback)
    assert follow_up["question"] in [q["question"] for q in REJECTION_BANK]
    history = answer_first_option(history, follow_up)

    second = turn(history, rejected, feedback)
    assert second["action"] == "guess"
    assert second["place"]["place_id"] not in rejected


def test_non_austin_city_does_not_get_austin_places(monkeypatch):
    monkeypatch.setattr(main, "get_places", boom)
    history = [{"question": q["question"], "answer": q["options"][0]} for q in QUESTION_BANK[:3]]
    data = turn(history, city="Denver CO")
    assert data["action"] == "no_match"


def test_repeated_gemini_question_is_replaced(monkeypatch):
    history = [{"question": "Pick a vibe:", "answer": "Romantic"}]
    monkeypatch.setattr(
        gemini_ai, "_generate",
        lambda prompt, schema: schema(question="Pick a vibe:", options=["A", "B"]),
    )
    data = turn(history)
    assert data["question"] != "Pick a vibe:"
    assert data.get("fallback") is True


def test_gemini_question_with_one_option_is_replaced(monkeypatch):
    monkeypatch.setattr(
        gemini_ai, "_generate",
        lambda prompt, schema: schema(question="Ready?", options=["Yes", "yes"]),
    )
    data = turn([])
    assert data.get("fallback") is True


def test_good_gemini_question_passes_through(monkeypatch):
    monkeypatch.setattr(
        gemini_ai, "_generate",
        lambda prompt, schema: schema(question="Sun or shade?", options=["Sun", "Shade", "Sun", "x", "y", "z"]),
    )
    data = turn([])
    assert data["question"] == "Sun or shade?"
    assert data["options"] == ["Sun", "Shade", "x", "y"]   # deduped, max 4
    assert "fallback" not in data


def test_invalid_gemini_candidate_uses_fallback_pick(monkeypatch):
    monkeypatch.setattr(main, "get_places", lambda q, c: SAMPLE)

    def fake(prompt, schema):
        if schema is gemini_ai.SearchPlan:
            return schema(search_query="cozy cafes")
        return schema(candidate_id=99, reason="made up")

    monkeypatch.setattr(gemini_ai, "_generate", fake)
    history = [{"question": "q", "answer": "Chill and cozy coffee"}]
    data = turn(history * 1 + [{"question": "q2", "answer": "x"}, {"question": "q3", "answer": "y"}])
    assert data["action"] == "guess"
    assert data["fallback"] is True
    assert data["place"]["place_id"] in {"p1", "p2", "p3"}


def test_empty_search_retries_broad(monkeypatch):
    calls = []

    def fake_places(query, city):
        calls.append(query)
        return [] if query != main.BROAD_QUERY else SAMPLE

    monkeypatch.setattr(main, "get_places", fake_places)
    history = [{"question": f"q{i}", "answer": "Museums"} for i in range(3)]
    data = turn(history)
    assert data["action"] == "guess"
    assert calls[-1] == main.BROAD_QUERY


def test_serpapi_outage_reuses_last_good_results(monkeypatch):
    history = [{"question": f"q{i}", "answer": "Museums"} for i in range(3)]
    monkeypatch.setattr(main, "get_places", lambda q, c: SAMPLE)
    turn(history, city="Denver CO")

    monkeypatch.setattr(main, "get_places", boom)
    data = turn(history, city="Denver CO")
    assert data["action"] == "guess"
    assert data["place"]["place_id"] in {"p1", "p2", "p3"}


def test_all_rejected_widens_search(monkeypatch):
    def fake_places(query, city):
        return SAMPLE[:1] if query != main.BROAD_QUERY else SAMPLE

    monkeypatch.setattr(main, "get_places", fake_places)
    history = [{"question": f"q{i}", "answer": "coffee"} for i in range(4)]
    data = turn(history, rejected=["p1"], feedback=["meh"])
    assert data["action"] == "guess"
    assert data["place"]["place_id"] != "p1"


def test_fallback_query_uses_feedback():
    history = [{"question": "q", "answer": "Food & drinks"}]
    assert fallback_search_query(history, ["Too expensive"]) == "cheap restaurants"
    assert fallback_search_query([], []) == "things to do"
