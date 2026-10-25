"""
One-box start screen ("live music in Austin tonight") and the hint text
shown in the "type your own answer" box.
Run: python -m pytest tests/test_intro.py -v
"""

import pytest
from fastapi.testclient import TestClient

import gemini_ai
import main
from fallback import (
    DEFAULT_PLACEHOLDER,
    QUESTION_BANK,
    city_is_grounded,
    parse_intro_fallback,
    validate_question,
)

client = TestClient(main.app)


def boom(*a, **k):
    raise RuntimeError("Gemini down")


def turn(**body):
    r = client.post("/api/game/next", json=body)
    assert r.status_code == 200, r.text
    return r.json()


# --- Parsing the sentence -----------------------------------------------------

@pytest.mark.parametrize("text, city, what, when", [
    ("live music in Austin, TX tonight", "Austin, TX", "live music", "tonight"),
    ("quiet bookstore in austin", "Austin, TX", "quiet bookstore", ""),
    ("tacos near Denver after 8pm", "Denver, CO", "tacos", "after 8pm"),
    ("Austin, TX", "Austin, TX", "", ""),
    ("ramen tomorrow night", "", "ramen", "tomorrow night"),
    ("coffee in a quiet place", "", "coffee in a quiet place", ""),
])
def test_fallback_parser(text, city, what, when):
    assert parse_intro_fallback(text) == {"city": city, "what": what, "when": when}


@pytest.mark.parametrize("city, text, ok", [
    ("Austin, TX", "tacos in austin", True),
    ("New York, NY", "pizza in NYC", True),
    ("Philadelphia, PA", "cheesesteak in philly", True),
    ("Los Angeles, CA", "beach day in LA", True),
    ("Austin, TX", "tacos tonight", False),          # invented city
    ("Paris, France", "romantic dinner", False),
])
def test_city_must_come_from_players_words(city, text, ok):
    assert city_is_grounded(city, text) is ok


def test_gemini_parse_used_when_available(monkeypatch):
    monkeypatch.setattr(gemini_ai, "_generate",
                        lambda p, s: s(city="Austin, TX", what="tacos", when="tonight"))
    assert gemini_ai.parse_intro("tacos in ATX tonight") == {"city": "Austin, TX", "what": "tacos", "when": "tonight"}


def test_gemini_invented_city_is_dropped(monkeypatch):
    monkeypatch.setattr(gemini_ai, "_generate",
                        lambda p, s: s(city="Austin, TX", what="tacos", when="tonight"))
    assert gemini_ai.parse_intro("tacos tonight")["city"] == ""


def test_parse_falls_back_when_gemini_down(monkeypatch):
    monkeypatch.setattr(gemini_ai, "_generate", boom)
    assert gemini_ai.parse_intro("jazz in Chicago, IL tonight")["city"] == "Chicago, IL"


# --- The game endpoint --------------------------------------------------------

def test_first_turn_parses_intro_and_returns_context(monkeypatch):
    monkeypatch.setattr(gemini_ai, "_generate", boom)
    data = turn(intro="live music in Nashville, TN tonight", history=[])
    assert data["action"] == "ask_question"
    assert data["context"] == {"city": "Nashville, TN", "what": "live music", "when": "tonight"}


def test_no_city_asks_for_one(monkeypatch):
    monkeypatch.setattr(gemini_ai, "_generate", boom)
    data = turn(intro="tacos tonight", history=[])
    assert data["action"] == "need_city"
    assert "city" in data["message"].lower()


def test_parsed_city_drives_the_search(monkeypatch):
    monkeypatch.setattr(gemini_ai, "_generate", boom)
    searched = []
    monkeypatch.setattr(main, "get_places", lambda q, c: searched.append((q, c)) or
                        [{"name": "X", "place_id": "x", "rating": 4}])
    history = [{"question": f"q{i}", "answer": "a"} for i in range(3)]
    # later turns send the parsed context back as city / what / when
    data = turn(city="Nashville, TN", what="live music", when="tonight", history=history)
    assert data["action"] == "guess"
    assert searched[0][1] == "Nashville, TN" and "live music" in searched[0][0]


def test_overlong_intro_rejected():
    assert client.post("/api/game/next", json={"intro": "x" * 201}).status_code == 422


# --- Hint text for the custom-answer box -------------------------------------

def test_every_builtin_question_has_a_short_hint():
    for q in QUESTION_BANK:
        assert 3 <= len(q["placeholder"]) <= 70


def test_gemini_hint_passed_through(monkeypatch):
    monkeypatch.setattr(gemini_ai, "_generate", lambda p, s: s(
        question="Sun or shade?", options=["Sun", "Shade"], placeholder="e.g. 'shady patio by the water'"))
    data = turn(city="Austin, TX", history=[])
    assert data["placeholder"] == "e.g. 'shady patio by the water'"


@pytest.mark.parametrize("bad", ["", "x", "y" * 200, None])
def test_bad_hint_replaced_with_default(bad):
    q = validate_question({"question": "Q?", "options": ["A", "B"], "placeholder": bad}, [])
    assert q["placeholder"] == DEFAULT_PLACEHOLDER


def test_fallback_question_has_hint(monkeypatch):
    monkeypatch.setattr(gemini_ai, "_generate", boom)
    data = turn(city="Austin, TX", history=[])
    assert data.get("fallback") and data["placeholder"]


def test_nickname_place_trusted_but_no_place_still_dropped(monkeypatch):
    monkeypatch.setattr(gemini_ai, "_generate",
                        lambda p, s: s(city="New York, NY", what="pizza", when=""))
    assert gemini_ai.parse_intro("pizza near the Big Apple")["city"] == "New York, NY"
    assert gemini_ai.parse_intro("pizza please")["city"] == ""


@pytest.mark.parametrize("text, named", [
    ("pizza near the Big Apple", True),
    ("tacos in ATX", True),
    ("tacos in atx", True),
    ("coffee in a quiet place", False),
    ("ramen tonight", False),
])
def test_mentions_place(text, named):
    from fallback import mentions_place
    assert mentions_place(text) is named


@pytest.mark.parametrize("text, city, what, when", [
    ("Austin Picnic evening", "Austin, TX", "Picnic", "evening"),          # city first, no "in"
    ("ATX tacos tonight", "Austin, TX", "tacos", "tonight"),
    ("pizza NYC friday", "New York, NY", "pizza", "friday"),
    ("Chicago", "Chicago, IL", "", ""),
    ("Denver omelette in Austin", "Austin, TX", "Denver omelette", ""),   # "in X" wins
    ("jazz in Portland, ME", "Portland, ME", "jazz", ""),                 # explicit state kept
    ("rooftop bar in Lisbon, Portugal", "Lisbon, Portugal", "rooftop bar", ""),  # not in the list
    ("la croix tasting", "", "la croix tasting", ""),                      # lowercase "la" isn't LA
])
def test_fallback_finds_city_anywhere(text, city, what, when):
    assert parse_intro_fallback(text) == {"city": city, "what": what, "when": when}


def test_start_screen_works_when_gemini_is_down(monkeypatch):
    monkeypatch.setattr(gemini_ai, "_generate", boom)
    data = turn(intro="Austin Picnic evening", history=[])
    assert data["action"] == "ask_question"
    assert data["context"] == {"city": "Austin, TX", "what": "Picnic", "when": "evening"}
