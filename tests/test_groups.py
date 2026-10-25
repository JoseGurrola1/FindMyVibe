"""
Group Mode: rooms, joining, per-member questions, group picks, voting.
No API keys or network needed (Gemini is faked as down; SerpApi is faked).
Run: python -m pytest tests/test_groups.py -v
"""

import pytest
from fastapi.testclient import TestClient

import gemini_ai
import groups
import main

client = TestClient(main.app)

PLACES = [
    {"name": f"Spot {i}", "place_id": f"p{i}", "rating": 4.0 + i / 10, "reviews": 100 * (i + 1), "category": "Bar"}
    for i in range(6)
]


def boom(*a, **k):
    raise RuntimeError("Gemini down")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(gemini_ai, "_generate", boom)
    monkeypatch.setattr(main, "get_places", lambda q, c: PLACES)


def create(name="Ana", city="Austin, TX"):
    r = client.post("/api/groups", json={"name": name, "city": city})
    assert r.status_code == 200, r.text
    return r.json()


def join(code, name):
    return client.post("/api/groups/join", json={"code": code, "name": name})


def h(token):
    return {"X-Member-Token": token}


def state(room, token):
    r = client.get(f"/api/groups/{room}", headers=h(token))
    assert r.status_code == 200, r.text
    return r.json()


def answer_all(room, token):
    """Answer this member's questions (first option each time)."""
    q = client.post(f"/api/groups/{room}/turn", headers=h(token), json={}).json()
    while not q["done"]:
        q = client.post(f"/api/groups/{room}/turn", headers=h(token),
                        json={"question": q["question"], "answer": q["options"][0]}).json()
    return q


@pytest.fixture
def party():
    host = create()
    guest = join(host["code"], "Ben").json()
    return host["room_id"], host, guest


# --- Creating and joining -----------------------------------------------------

def test_create_returns_room_and_private_token():
    r = create()
    assert r["code"].startswith("VIBE-") and len(r["code"]) == 9
    assert r["room_id"] and r["member_token"] and r["member_id"]
    s = state(r["room_id"], r["member_token"])
    assert s["status"] == "lobby" and s["city"] == "Austin, TX"
    assert s["me"]["is_host"] and [m["name"] for m in s["members"]] == ["Ana"]


def test_two_people_in_the_same_room(party):
    room, host, guest = party
    assert guest["room_id"] == room
    for who in (host, guest):
        names = [m["name"] for m in state(room, who["member_token"])["members"]]
        assert names == ["Ana", "Ben"]
    assert state(room, guest["member_token"])["me"]["is_host"] is False


@pytest.mark.parametrize("typed", ["{code}", "{lower}", "{bare}", " {code} "])
def test_join_code_is_forgiving(typed):
    host = create()
    code = host["code"]
    text = typed.format(code=code, lower=code.lower(), bare=code.split("-")[1])
    assert join(text, "Ben").status_code == 200


def test_bad_code_404():
    r = join("VIBE-ZZZZ", "Ben")
    assert r.status_code == 404 and "code" in r.json()["detail"].lower()


def test_duplicate_names_get_a_number():
    host = create(name="Sam")
    join(host["code"], "Sam")
    names = [m["name"] for m in state(host["room_id"], host["member_token"])["members"]]
    assert names == ["Sam", "Sam 2"]


def test_room_is_capped():
    host = create()
    for i in range(groups.MAX_MEMBERS - 1):
        assert join(host["code"], f"P{i}").status_code == 200
    assert join(host["code"], "Late").status_code == 409


def test_token_required_and_checked(party):
    room, host, _ = party
    assert client.get(f"/api/groups/{room}").status_code == 401
    assert client.get(f"/api/groups/{room}", headers=h("not-a-real-token")).status_code == 401
    other = create()
    assert client.get(f"/api/groups/{room}", headers=h(other["member_token"])).status_code == 401


def test_validation():
    assert client.post("/api/groups", json={"name": "", "city": "Austin"}).status_code == 422
    assert client.post("/api/groups", json={"name": "x" * 41, "city": "Austin"}).status_code == 422
    assert client.post("/api/groups", json={"name": "  ", "city": "Austin"}).status_code == 422


# --- Starting and answering ---------------------------------------------------

def test_only_host_can_start(party):
    room, host, guest = party
    assert client.post(f"/api/groups/{room}/start", headers=h(guest["member_token"])).status_code == 403
    assert client.post(f"/api/groups/{room}/start", headers=h(host["member_token"])).json()["status"] == "answering"


def test_questions_closed_before_start(party):
    room, host, _ = party
    assert client.post(f"/api/groups/{room}/turn", headers=h(host["member_token"]), json={}).status_code == 409


def test_each_member_gets_their_own_questions(party):
    room, host, guest = party
    client.post(f"/api/groups/{room}/start", headers=h(host["member_token"]))
    q = client.post(f"/api/groups/{room}/turn", headers=h(host["member_token"]), json={}).json()
    assert q["done"] is False and q["number"] == 1 and len(q["options"]) >= 2 and q["placeholder"]
    # Asking again (e.g. page refresh) returns the same pending question
    again = client.post(f"/api/groups/{room}/turn", headers=h(host["member_token"]), json={}).json()
    assert again["question"] == q["question"]
    # Answering a stale question is ignored (double-click protection)
    client.post(f"/api/groups/{room}/turn", headers=h(host["member_token"]),
                json={"question": "something else", "answer": "x"})
    assert state(room, host["member_token"])["me"]["answered"] == 0
    # Guest's progress is separate
    client.post(f"/api/groups/{room}/turn", headers=h(host["member_token"]),
                json={"question": q["question"], "answer": q["options"][0]})
    s = state(room, guest["member_token"])
    assert {m["name"]: m["answered"] for m in s["members"]} == {"Ana": 1, "Ben": 0}


def test_join_while_answering_is_allowed(party):
    room, host, _ = party
    client.post(f"/api/groups/{room}/start", headers=h(host["member_token"]))
    assert join(host["code"], "Cat").status_code == 200


# --- Group picks and voting ---------------------------------------------------

def test_last_finisher_triggers_search_and_voting(party):
    room, host, guest = party
    client.post(f"/api/groups/{room}/start", headers=h(host["member_token"]))
    answer_all(room, host["member_token"])
    assert state(room, host["member_token"])["status"] == "answering"   # Ben not done yet
    answer_all(room, guest["member_token"])
    s = state(room, host["member_token"])
    assert s["status"] == "voting"
    assert len(s["results"]) == 3
    ids = [r["place"]["place_id"] for r in s["results"]]
    assert len(set(ids)) == 3 and all(r["reason"] and r["votes"] == 0 for r in s["results"])


def test_votes_pick_the_winner(party):
    room, host, guest = party
    client.post(f"/api/groups/{room}/start", headers=h(host["member_token"]))
    answer_all(room, host["member_token"]); answer_all(room, guest["member_token"])
    client.post(f"/api/groups/{room}/vote", headers=h(host["member_token"]), json={"index": 2})
    s = state(room, guest["member_token"])
    assert s["status"] == "voting" and s["results"][2]["votes"] == 1
    assert [m["voted"] for m in s["members"]] == [True, False]
    s = client.post(f"/api/groups/{room}/vote", headers=h(guest["member_token"]), json={"index": 2}).json()
    assert s["status"] == "done" and s["winner"] == 2


def test_tie_goes_to_top_pick(party):
    room, host, guest = party
    client.post(f"/api/groups/{room}/start", headers=h(host["member_token"]))
    answer_all(room, host["member_token"]); answer_all(room, guest["member_token"])
    client.post(f"/api/groups/{room}/vote", headers=h(host["member_token"]), json={"index": 2})
    s = client.post(f"/api/groups/{room}/vote", headers=h(guest["member_token"]), json={"index": 1}).json()
    assert s["status"] == "done" and s["winner"] == 1


def test_can_change_vote_and_bad_index_rejected(party):
    room, host, guest = party
    client.post(f"/api/groups/{room}/start", headers=h(host["member_token"]))
    answer_all(room, host["member_token"]); answer_all(room, guest["member_token"])
    client.post(f"/api/groups/{room}/vote", headers=h(host["member_token"]), json={"index": 0})
    client.post(f"/api/groups/{room}/vote", headers=h(host["member_token"]), json={"index": 1})
    s = state(room, host["member_token"])
    assert [r["votes"] for r in s["results"]] == [0, 1, 0]
    assert client.post(f"/api/groups/{room}/vote", headers=h(host["member_token"]), json={"index": 7}).status_code == 400


def test_host_can_search_early_and_reveal_early(party):
    room, host, guest = party
    client.post(f"/api/groups/{room}/start", headers=h(host["member_token"]))
    answer_all(room, host["member_token"])
    assert client.post(f"/api/groups/{room}/search", headers=h(guest["member_token"])).status_code == 403
    s = client.post(f"/api/groups/{room}/search", headers=h(host["member_token"])).json()
    s = state(room, host["member_token"])
    assert s["status"] == "voting"
    client.post(f"/api/groups/{room}/vote", headers=h(guest["member_token"]), json={"index": 1})
    assert client.post(f"/api/groups/{room}/reveal", headers=h(guest["member_token"])).status_code == 403
    s = client.post(f"/api/groups/{room}/reveal", headers=h(host["member_token"])).json()
    assert s["status"] == "done" and s["winner"] == 1


def test_early_search_needs_someone_finished(party):
    room, host, _ = party
    client.post(f"/api/groups/{room}/start", headers=h(host["member_token"]))
    assert client.post(f"/api/groups/{room}/search", headers=h(host["member_token"])).status_code == 409


def test_cant_join_after_voting_opens(party):
    room, host, guest = party
    client.post(f"/api/groups/{room}/start", headers=h(host["member_token"]))
    answer_all(room, host["member_token"]); answer_all(room, guest["member_token"])
    assert join(host["code"], "Late").status_code == 409


def test_no_places_lets_host_retry(monkeypatch):
    # Not Austin, so the saved backup places don't apply.
    monkeypatch.setattr(main, "get_places", lambda q, c: [])
    host = create(city="Boise, ID")
    guest = join(host["code"], "Ben").json()
    room = host["room_id"]
    client.post(f"/api/groups/{room}/start", headers=h(host["member_token"]))
    answer_all(room, host["member_token"]); answer_all(room, guest["member_token"])
    s = state(room, host["member_token"])
    assert s["status"] == "answering" and "couldn't find" in s["message"].lower()


def test_search_crash_lets_host_retry(party, monkeypatch):
    room, host, guest = party
    monkeypatch.setattr("group_routes.choose_group_places", boom)
    client.post(f"/api/groups/{room}/start", headers=h(host["member_token"]))
    answer_all(room, host["member_token"]); answer_all(room, guest["member_token"])
    s = state(room, host["member_token"])
    assert s["status"] == "answering" and "try again" in s["message"].lower()


def test_gemini_group_picks_validated_and_filled(monkeypatch):
    def fake(prompt, schema):
        return schema(picks=[
            {"candidate_id": 3, "reason": "Ana gets a patio, Ben gets beer."},
            {"candidate_id": 3, "reason": "duplicate"},
            {"candidate_id": 99, "reason": "invented"},
        ])
    monkeypatch.setattr(gemini_ai, "_generate", fake)
    members = [{"name": "Ana", "history": [{"question": "q", "answer": "beer"}]}]
    picks = gemini_ai.choose_group_places(members, PLACES, "Austin, TX", limit=3)
    assert [p["place"]["place_id"] for p in picks][0] == "p3"
    assert picks[0]["reason"].startswith("Ana gets")
    assert len(picks) == 3 and len({p["place"]["place_id"] for p in picks}) == 3


def test_expired_room_is_gone(party, monkeypatch):
    room, host, _ = party
    real = groups._now
    monkeypatch.setattr(groups, "_now", lambda: real() + groups.ROOM_TTL_SECONDS + 1)
    assert client.get(f"/api/groups/{room}", headers=h(host["member_token"])).status_code == 404


# --- Rate limiting --------------------------------------------------------------

def test_polling_is_not_rate_limited_but_actions_are(party, monkeypatch):
    from ratelimit import RateLimiter
    monkeypatch.setattr(main, "visitor_limiter", RateLimiter([(3, 60)]))
    monkeypatch.setattr(main, "RATE_LIMIT_ENABLED", True)
    room, host, _ = party
    assert {client.get(f"/api/groups/{room}", headers=h(host["member_token"])).status_code for _ in range(10)} == {200}
    codes = [client.post(f"/api/groups/{room}/start", headers=h(host["member_token"])).status_code for _ in range(4)]
    assert codes[-1] == 429


def test_solo_mode_unaffected():
    r = client.post("/api/game/next", json={"city": "Austin, TX", "history": []})
    assert r.status_code == 200 and r.json()["action"] == "ask_question"
