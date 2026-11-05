"""Tests for fetch.py. No test touches the network."""
import pytest
import requests

from recordsync.config import Config
from recordsync.fetch import FetchError, fetch_users, get_users

USERS = [{"id": 1, "email": "Sincere@april.biz"}]


class FakeResponse:
    """Minimal stand-in for requests.Response."""

    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = USERS if body is None else body

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._body


class FakeSession:
    """Plays back a script of status codes, FakeResponses, or exceptions; records calls."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append({"url": url, "timeout": timeout})
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step if isinstance(step, FakeResponse) else FakeResponse(step)


@pytest.fixture
def cfg(tmp_path):
    return Config(api_url="http://test.invalid/users", max_retries=3,
                  backoff_base=0.5, data_dir=tmp_path)


@pytest.fixture
def sleeps():
    return []


def test_retries_503_then_succeeds(cfg, sleeps):
    session = FakeSession([503, 503, 200])
    assert fetch_users(cfg, session, sleeps.append) == USERS
    assert len(session.calls) == 3
    assert sleeps == [0.5, 1.0]


def test_gives_up_after_max_retries(cfg, sleeps):
    session = FakeSession([503] * 4)
    with pytest.raises(FetchError, match="4 attempts"):
        fetch_users(cfg, session, sleeps.append)
    assert len(session.calls) == 4         # 1 try + 3 retries
    assert sleeps == [0.5, 1.0, 2.0]       # no sleep after the final failure


def test_no_retry_on_404(cfg, sleeps):
    session = FakeSession([404])
    with pytest.raises(FetchError, match="not retryable"):
        fetch_users(cfg, session, sleeps.append)
    assert len(session.calls) == 1
    assert sleeps == []


def test_timeout_and_url_passed(cfg, sleeps):
    session = FakeSession([200])
    fetch_users(cfg, session, sleeps.append)
    assert session.calls == [{"url": cfg.api_url, "timeout": cfg.timeout}]


def test_connection_error_is_retried(cfg, sleeps):
    session = FakeSession([requests.ConnectionError("boom"), 200])
    assert fetch_users(cfg, session, sleeps.append) == USERS
    assert len(session.calls) == 2


def test_non_list_payload_rejected(cfg, sleeps):
    session = FakeSession([FakeResponse(200, body={"not": "a list"})])
    with pytest.raises(FetchError, match="list"):
        fetch_users(cfg, session, sleeps.append)


def test_cache_round_trip_and_offline(cfg, sleeps):
    with pytest.raises(FetchError, match="No cache"):
        get_users(cfg, offline=True)
    get_users(cfg, session=FakeSession([200]), sleep=sleeps.append)
    assert get_users(cfg, offline=True) == USERS