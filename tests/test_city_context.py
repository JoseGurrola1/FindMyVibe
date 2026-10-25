"""
Start-screen answers (Where / What / When): the city reaches the search,
and What / When reach Gemini and the fallbacks.
Run: python -m pytest tests/test_city_context.py -v
"""

import pytest
from fastapi.testclient import TestClient

import gemini_ai
import main
from fallback import WHAT_QUESTION, WHEN_QUESTION

client = TestClient(main.app)

SAMPLE = [{"name": "Spot", "place_id": "p1", "rating": 4.5, "reviews": 100, "category": "Bar"}]
THREE = [{"question": f"q{i}", "answer": "x"} for i in range(3)]


@pytest.fixture
def prompts(monkeypatch):
    """Record every prompt sent to Gemini, then fail so fallbacks run."""
    seen = []

    def fake(prompt, schema):
        seen.append(prompt)
        raise RuntimeError("offline")

    monkeypatch.setattr(gemini_ai, "_generate", fake)
    return seen


def turn(**body):
    r = client.post("/api/game/next", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_city_reaches_the_search(prompts, monkeypatch):
    searched = []
    monkeypatch.setattr(main, "get_places", lambda q, c: searched.append(c) or SAMPLE)
    data = turn(city="Denver, CO", history=THREE)
    assert data["action"] == "guess"
    assert searched == ["Denver, CO"]


def test_blank_city_defaults_to_austin(prompts, monkeypatch):
    searched = []
    monkeypatch.setattr(main, "get_places", lambda q, c: searched.append(c) or SAMPLE)
    turn(city="   ", history=THREE)
    assert searched == ["Austin TX"]


def test_city_what_when_reach_every_gemini_prompt(prompts, monkeypatch):
    monkeypatch.setattr(main, "get_places", lambda q, c: SAMPLE)
    ctx = {"city": "Chicago, IL", "what": "deep dish pizza", "when": "Friday night"}
    turn(**ctx, history=[])          # question prompt
    turn(**ctx, history=THREE)       # search-query prompt + place-choice prompt
    assert len(prompts) == 3
    for p in prompts:
        assert "Chicago, IL" in p and "deep dish pizza" in p and "Friday night" in p


def test_blank_what_when_are_left_out_of_prompt(prompts):
    turn(city="", what="", when="", history=[])
    assert "City: Austin TX" in prompts[0]           # blank city -> Austin
    assert "in the mood for" not in prompts[0]
    assert "When they're going" not in prompts[0]


def test_fallback_skips_questions_already_answered(prompts):
    history, asked = [], []
    for _ in range(3):
        data = turn(city="Denver, CO", what="live music", when="tonight", history=history)
        asked.append(data["question"])
        history.append({"question": data["question"], "answer": data["options"][0]})
    assert WHAT_QUESTION not in asked
    assert WHEN_QUESTION not in asked
    assert len(set(asked)) == 3


def test_fallback_asks_what_first_only_if_blank(prompts):
    assert turn(city="Denver, CO", history=[])["question"] == WHAT_QUESTION
    assert turn(city="Denver, CO", what="tacos", history=[])["question"] != WHAT_QUESTION


def test_fallback_search_uses_what(prompts, monkeypatch):
    queries = []
    monkeypatch.setattr(main, "get_places", lambda q, c: queries.append(q) or SAMPLE)
    data = turn(city="Nashville, TN", what="live music", history=THREE)
    assert "live music" in queries[0]
    assert data["search_query"] == queries[0]


def test_other_city_with_serpapi_down_gets_no_match(prompts, monkeypatch):
    def down(q, c):
        raise RuntimeError("SerpApi down")
    monkeypatch.setattr(main, "get_places", down)
    data = turn(city="Boise, ID", history=THREE)
    assert data["action"] == "no_match"
    assert "Boise, ID" in data["message"]


def test_overlong_inputs_rejected():
    assert client.post("/api/game/next", json={"city": "x" * 81}).status_code == 422
    assert client.post("/api/game/next", json={"what": "x" * 121}).status_code == 422


def test_old_clients_without_new_fields_still_work(prompts):
    data = turn(history=[])
    assert data["action"] == "ask_question"
