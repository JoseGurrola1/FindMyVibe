"""
Rate limiting tests. No API keys or network needed.
Run: python -m pytest tests/test_ratelimit.py -v
"""

import pytest
from fastapi.testclient import TestClient

import gemini_ai
import main
from ratelimit import RateLimiter


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


# --- The limiter on its own -------------------------------------------------

def test_allows_up_to_limit_then_blocks():
    clock = FakeClock()
    rl = RateLimiter([(3, 60)], clock=clock)
    assert [rl.hit("a") for _ in range(3)] == [None, None, None]
    assert rl.hit("a") == 60          # must wait for the first hit to expire


def test_window_slides():
    clock = FakeClock()
    rl = RateLimiter([(2, 60)], clock=clock)
    rl.hit("a"); clock.now += 30; rl.hit("a")
    assert rl.hit("a") == 30          # first hit expires 30s from now
    clock.now += 30
    assert rl.hit("a") is None        # first hit aged out
    assert rl.hit("a") == 30          # second one still counts


def test_visitors_are_independent():
    rl = RateLimiter([(1, 60)], clock=FakeClock())
    assert rl.hit("a") is None
    assert rl.hit("a") is not None
    assert rl.hit("b") is None


def test_blocked_requests_do_not_extend_the_wait():
    clock = FakeClock()
    rl = RateLimiter([(1, 60)], clock=clock)
    rl.hit("a")
    for _ in range(10):
        clock.now += 1
        rl.hit("a")                   # hammering while blocked...
    clock.now = 1060.0
    assert rl.hit("a") is None        # ...doesn't push the reset back


def test_hourly_rule_applies_after_minute_rule():
    clock = FakeClock()
    rl = RateLimiter([(5, 60), (8, 3600)], clock=clock)
    for _ in range(5):
        assert rl.hit("a") is None
    clock.now += 61
    for _ in range(3):
        assert rl.hit("a") is None
    wait = rl.hit("a")                # 8 in the hour now
    assert wait is not None and wait > 3000


def test_stale_visitors_are_cleaned_up():
    clock = FakeClock()
    rl = RateLimiter([(5, 60)], clock=clock)
    for i in range(100):
        rl.hit(f"ip{i}")
    clock.now += 400
    rl.hit("new")
    assert set(rl._hits) == {"new"}


# --- Through the API ---------------------------------------------------------

def boom(*a, **k):
    raise RuntimeError("no network in tests")


@pytest.fixture
def small_limits(monkeypatch):
    monkeypatch.setattr(gemini_ai, "_generate", boom)   # use built-in questions
    monkeypatch.setattr(main, "visitor_limiter", RateLimiter([(3, 60)]))
    monkeypatch.setattr(main, "global_limiter", RateLimiter([(5, 3600)]))
    monkeypatch.setattr(main, "RATE_LIMIT_ENABLED", True)


def play(client):
    return client.post("/api/game/next", json={"history": []})


def test_api_returns_429_with_retry_after(small_limits):
    c = TestClient(main.app, client=("1.1.1.1", 5000))
    assert [play(c).status_code for _ in range(3)] == [200, 200, 200]
    r = play(c)
    assert r.status_code == 429
    assert 1 <= int(r.headers["Retry-After"]) <= 60
    assert r.json()["retry_after"] == int(r.headers["Retry-After"])


def test_other_visitor_unaffected(small_limits):
    a = TestClient(main.app, client=("1.1.1.1", 5000))
    b = TestClient(main.app, client=("2.2.2.2", 5000))
    for _ in range(3):
        play(a)
    assert play(a).status_code == 429
    assert play(b).status_code == 200


def test_global_cap_across_visitors(small_limits):
    codes = [play(TestClient(main.app, client=(f"9.9.9.{i}", 5000))).status_code for i in range(6)]
    assert codes == [200] * 5 + [429]


def test_places_endpoint_is_limited_too(small_limits, monkeypatch):
    monkeypatch.setattr(main, "get_places", lambda q, c: [])
    c = TestClient(main.app, client=("3.3.3.3", 5000))
    codes = [c.get("/api/places", params={"query": "x"}).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


def test_homepage_not_limited(small_limits):
    c = TestClient(main.app, client=("4.4.4.4", 5000))
    assert {c.get("/").status_code for _ in range(10)} == {200}


def test_can_be_disabled(small_limits, monkeypatch):
    monkeypatch.setattr(main, "RATE_LIMIT_ENABLED", False)
    c = TestClient(main.app, client=("5.5.5.5", 5000))
    assert {play(c).status_code for _ in range(6)} == {200}
