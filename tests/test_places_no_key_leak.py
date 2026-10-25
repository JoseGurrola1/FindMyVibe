"""
SerpApi errors must never expose the API key.

requests puts the full URL (including api_key=...) in its error messages,
so get_places() must replace those errors with key-free ones.
Run: python -m pytest tests/test_places_no_key_leak.py -v
"""

import os
import sys
import logging
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import requests

import places

FAKE_KEY = "secret_test_key_1234567890"
URL = f"https://serpapi.com/search.json?q=cafes&api_key={FAKE_KEY}"


class FakeResponse:
    def __init__(self, status=200, body=None, bad_json=False):
        self.status_code = status
        self._body = body if body is not None else {"local_results": []}
        self._bad_json = bad_json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error for url: {URL}", response=self)

    def json(self):
        if self._bad_json:
            raise ValueError(f"bad json from {URL}")
        return self._body


def raise_proxy(*a, **k):
    raise requests.exceptions.ProxyError(f"HTTPSConnectionPool: Max retries exceeded with url: {URL}")


def raise_timeout(*a, **k):
    raise requests.exceptions.Timeout(f"Read timed out. url: {URL}")


CASES = {
    "network error": raise_proxy,
    "timeout": raise_timeout,
    "http 401": lambda *a, **k: FakeResponse(status=401),
    "http 500": lambda *a, **k: FakeResponse(status=500),
    "bad json": lambda *a, **k: FakeResponse(bad_json=True),
}


@pytest.mark.parametrize("name", CASES)
def test_error_never_contains_key(monkeypatch, name, caplog):
    monkeypatch.setattr(places, "API_KEY", FAKE_KEY)
    monkeypatch.setattr(places.requests, "get", CASES[name])

    with pytest.raises(RuntimeError) as info:
        places.get_places("cafes")

    # The message, the full printed traceback, and anything logged
    # with log.exception() must all be free of the key.
    full_tb = "".join(traceback.format_exception(info.type, info.value, info.tb))
    assert FAKE_KEY not in str(info.value)
    assert FAKE_KEY not in full_tb
    assert "api_key" not in full_tb

    logging.getLogger("test").exception("search failed", exc_info=info.value)
    assert FAKE_KEY not in caplog.text


def test_success_still_works(monkeypatch):
    monkeypatch.setattr(places, "API_KEY", FAKE_KEY)
    body = {"local_results": [{"title": "Cafe", "place_id": "p1", "thumbnail": "t.jpg"}]}
    monkeypatch.setattr(places.requests, "get", lambda *a, **k: FakeResponse(body=body))
    result = places.get_places("cafes")
    assert result[0]["name"] == "Cafe"
    assert result[0]["thumbnail"] == "t.jpg"
