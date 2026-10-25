"""
Opening hours: reading SerpApi's hours, reading the player's "when",
and deciding open / closed / unknown.
Run: python -m pytest tests/test_hours.py -v
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from hours import (
    Target, annotate, day_intervals, hours_note, local_now, open_at, parse_when, prefer_open,
)

# Friday 3:00 PM in Austin
NOW = datetime(2026, 10, 23, 15, 0, tzinfo=ZoneInfo("America/Chicago"))
assert NOW.strftime("%A") == "Friday"

H = lambda h, m=0: h * 60 + m


# --- Reading posted hours -------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("6:30 AM–5 PM", [(H(6, 30), H(17))]),
    ("8AM–5PM", [(H(8), H(17))]),
    ("11 AM–2 AM", [(H(11), H(26))]),                       # past midnight
    ("12–2:45 PM, 4–10 PM", [(H(12), H(14, 45)), (H(16), H(22))]),
    ("11:30 AM–3 PM, 5–10 PM", [(H(11, 30), H(15)), (H(17), H(22))]),
    ("9–11 AM", [(H(9), H(11))]),
    ("12 AM–10 PM", [(H(0), H(22))]),
    ("5 PM–12 AM", [(H(17), H(24))]),
    ("7 AM – 9 PM", [(H(7), H(21))]),        # Google's narrow spaces
    ("Open 24 hours", [(0, H(24))]),
    ("Closed", []),
    ("", None),
    ("by appointment", None),
])
def test_day_intervals(text, expected):
    assert day_intervals(text) == expected


# --- Reading "when" --------------------------------------------------------------

@pytest.mark.parametrize("text, day, minute", [
    ("tonight after 8pm", "friday", H(20)),
    ("tonight", "friday", H(20)),
    ("around 9:30 p.m.", "friday", H(21, 30)),
    ("at 7", "friday", H(19)),                               # "at 7" = evening
    ("tomorrow morning", "saturday", H(10)),
    ("Saturday brunch", "saturday", H(11)),
    ("sunday", "sunday", None),                              # any time that day
    ("this weekend", "saturday", None),
    ("late night", "friday", H(23)),
    ("right now", "friday", H(15)),
    ("at 9am", "saturday", H(9)),                            # 9am already passed today
    ("monday lunch", "monday", H(12, 30)),
])
def test_parse_when(text, day, minute):
    t = parse_when(text, NOW)
    assert (t.day, t.minute) == (day, minute)


@pytest.mark.parametrize("text", ["", "with friends", "somewhere cheap", "for 6 people"])
def test_parse_when_nothing(text):
    assert parse_when(text, NOW) is None


def test_labels():
    assert parse_when("tonight after 8pm", NOW).label == "tonight at 8 PM"
    assert parse_when("tomorrow morning", NOW).label == "tomorrow at 10 AM"
    assert parse_when("sunday", NOW).label == "Sun"


# --- Open or closed --------------------------------------------------------------

BAR = {"friday": "5 PM–2 AM", "saturday": "5 PM–2 AM", "sunday": "Closed", "monday": "Closed"}
CAFE = {"friday": "7 AM–3 PM", "saturday": "8 AM–2 PM", "sunday": "Closed"}


def test_open_at():
    fri8pm, fri1pm = Target("friday", H(20), ""), Target("friday", H(13), "")
    assert open_at(BAR, fri8pm) is True and open_at(BAR, fri1pm) is False
    assert open_at(CAFE, fri8pm) is False and open_at(CAFE, fri1pm) is True


def test_open_past_midnight_counts_next_day():
    assert open_at(BAR, Target("saturday", H(1), "")) is True    # Fri night spills over
    assert open_at(BAR, Target("monday", H(1), "")) is False     # Sun closed


def test_any_time_that_day():
    assert open_at(BAR, Target("saturday", None, "")) is True
    assert open_at(BAR, Target("sunday", None, "")) is False


def test_unknown_hours_are_unknown_not_closed():
    assert open_at(None, Target("friday", H(20), "")) is None
    assert open_at({"friday": "call us"}, Target("friday", H(20), "")) is None
    assert open_at({"monday": "9 AM–5 PM"}, Target("friday", H(20), "")) is None


# --- Notes and filtering ---------------------------------------------------------

def test_hours_notes():
    t = parse_when("tonight after 8pm", NOW)
    assert hours_note({"operating_hours": BAR}, t, NOW) == "Open tonight at 8 PM · Fri 5 PM–2 AM"
    assert hours_note({"operating_hours": CAFE}, t, NOW) == "Closed tonight at 8 PM · Fri 7 AM–3 PM"
    assert hours_note({}, t, NOW) == "Hours not listed. Check before you go"
    sunday = parse_when("sunday evening", NOW)
    assert hours_note({"operating_hours": BAR}, sunday, NOW) == "Closed Sun at 7 PM (closed all day Sunday)"
    # no "when": today's hours, or SerpApi's live status
    assert hours_note({"operating_hours": CAFE}, None, NOW) == "Fri: 7 AM–3 PM"
    assert hours_note({"open_state": "Open ⋅ Closes 10 PM"}, None, NOW) == "Open ⋅ Closes 10 PM"


def test_annotate_and_prefer_open():
    places = [{"name": "Cafe", "operating_hours": CAFE}, {"name": "Bar", "operating_hours": BAR},
              {"name": "Mystery"}]
    out, target = annotate(places, "tonight after 8pm", now=NOW)
    assert target.minute == H(20)
    assert [p["open_at_requested_time"] for p in out] == [False, True, None]
    assert [p["name"] for p in prefer_open(out)] == ["Bar", "Mystery"]
    # if everything is closed, keep them all (the note says so honestly)
    all_closed, _ = annotate(places[:1], "tonight after 8pm", now=NOW)
    assert prefer_open(all_closed) == all_closed


def test_annotate_without_when_drops_nothing():
    out, target = annotate([{"name": "Cafe", "operating_hours": CAFE}], "", now=NOW)
    assert target is None and out[0]["open_at_requested_time"] is None and out[0]["hours_note"]


def test_bad_timezone_falls_back():
    assert local_now("Not/AZone").tzinfo is not None


# --- In the game -----------------------------------------------------------------

from fastapi.testclient import TestClient

import gemini_ai
import hours
import main

client = TestClient(main.app)
THREE = [{"question": f"q{i}", "answer": "drinks"} for i in range(3)]
# Highest-rated place is closed tonight; the open bar should win.
PLACES = [
    {"name": "Morning Cafe", "place_id": "c", "rating": 4.9, "reviews": 5000, "category": "Cafe", "operating_hours": CAFE},
    {"name": "Night Bar", "place_id": "b", "rating": 4.3, "reviews": 300, "category": "Bar", "operating_hours": BAR},
]


@pytest.fixture
def friday_3pm(monkeypatch):
    monkeypatch.setattr(hours, "local_now", lambda tz=None: NOW)
    monkeypatch.setattr(gemini_ai, "_generate", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")))
    monkeypatch.setattr(main, "get_places", lambda q, c: PLACES)


def test_guess_skips_place_closed_at_requested_time(friday_3pm):
    r = client.post("/api/game/next", json={"city": "Austin, TX", "when": "tonight after 8pm",
                                            "history": THREE, "tz": "America/Chicago"}).json()
    assert r["place"]["name"] == "Night Bar"
    assert r["place"]["hours_note"] == "Open tonight at 8 PM · Fri 5 PM–2 AM"


def test_without_when_nothing_is_filtered(friday_3pm):
    r = client.post("/api/game/next", json={"city": "Austin, TX", "history": THREE}).json()
    assert r["place"]["name"] == "Morning Cafe"
    assert r["place"]["hours_note"] == "Fri: 7 AM–3 PM"


def test_gemini_is_told_who_is_open(friday_3pm, monkeypatch):
    prompts = []
    def fake(prompt, schema):
        prompts.append(prompt)
        if schema is gemini_ai.SearchPlan:
            return schema(search_query="bars")
        return schema(candidate_id=1, reason="Open late.")
    monkeypatch.setattr(gemini_ai, "_generate", fake)
    r = client.post("/api/game/next", json={"city": "Austin, TX", "when": "tonight after 8pm", "history": THREE}).json()
    pick_prompt = prompts[-1]
    assert '"open_at_requested_time": true' in pick_prompt
    assert "Morning Cafe" not in pick_prompt          # closed tonight, filtered out
    assert "operating_hours" not in pick_prompt.split("Available REAL locations:")[1]
    assert r["place"]["name"] == "Night Bar"


def test_group_cards_get_todays_hours(friday_3pm):
    host = client.post("/api/groups", json={"name": "Ana", "city": "Austin, TX", "tz": "America/Chicago"}).json()
    room, tok = host["room_id"], {"X-Member-Token": host["member_token"]}
    client.post(f"/api/groups/{room}/start", headers=tok)
    q = client.post(f"/api/groups/{room}/turn", headers=tok, json={}).json()
    while not q["done"]:
        q = client.post(f"/api/groups/{room}/turn", headers=tok, json={"question": q["question"], "answer": q["options"][0]}).json()
    s = client.get(f"/api/groups/{room}", headers=tok).json()
    notes = {r["place"]["name"]: r["place"]["hours_note"] for r in s["results"]}
    assert notes == {"Morning Cafe": "Fri: 7 AM–3 PM", "Night Bar": "Fri: 5 PM–2 AM"}


def test_serpapi_hours_fields_are_kept(monkeypatch):
    import places

    class Resp:
        def raise_for_status(self): pass
        def json(self):
            return {"local_results": [{"title": "Night Bar", "place_id": "b",
                                        "operating_hours": BAR, "open_state": "Open ⋅ Closes 2 AM"}]}
    monkeypatch.setattr(places, "API_KEY", "test")
    monkeypatch.setattr(places.requests, "get", lambda *a, **k: Resp())
    got = places.get_places("bars", "Austin, TX")[0]
    assert got["operating_hours"] == BAR and got["open_state"] == "Open ⋅ Closes 2 AM"
