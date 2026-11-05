"""Fetch billing users from the API with timeouts, retries, and an on-disk cache."""
import json
import time
from pathlib import Path
from typing import Callable

import requests

from recordsync.config import Config

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
CACHE_NAME = "api_users.json"


class FetchError(RuntimeError):
    """The API could not be fetched, or returned something unusable."""


class _Transient(Exception):
    """Internal signal: this attempt failed in a way worth retrying."""


def backoff_delay(attempt: int, base: float) -> float:
    """Exponential backoff in seconds: base, 2*base, 4*base, ... for attempt 0, 1, 2."""
    return base * (2 ** attempt)


def _parse_users(resp: requests.Response) -> list[dict]:
    """Decode the body and check it is a list of JSON objects."""
    try:
        body = resp.json()
    except ValueError as exc:
        raise FetchError(f"Response is not valid JSON: {exc}") from exc
    if not isinstance(body, list) or not all(isinstance(u, dict) for u in body):
        raise FetchError("Expected a JSON list of user objects")
    return body


def _attempt(session: requests.Session, cfg: Config) -> list[dict]:
    """Make one request. Raise _Transient if retryable, FetchError if fatal."""
    try:
        resp = session.get(cfg.api_url, timeout=cfg.timeout)
    except (requests.ConnectionError, requests.Timeout) as exc:
        raise _Transient(f"{type(exc).__name__}: {exc}") from exc
    if resp.status_code in RETRYABLE_STATUS:
        raise _Transient(f"HTTP {resp.status_code}")
    if not resp.ok:
        raise FetchError(f"HTTP {resp.status_code} from {cfg.api_url} (not retryable)")
    return _parse_users(resp)


def fetch_users(
    cfg: Config,
    session: requests.Session | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict]:
    """GET cfg.api_url, retrying transient failures up to cfg.max_retries times."""
    if session is None:
        with requests.Session() as own:
            return fetch_users(cfg, own, sleep)
    attempts = cfg.max_retries + 1
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return _attempt(session, cfg)
        except _Transient as exc:
            last_error = exc
            if attempt < attempts - 1:
                sleep(backoff_delay(attempt, cfg.backoff_base))
    raise FetchError(f"Gave up after {attempts} attempts; last error: {last_error}")


def save_cache(users: list[dict], data_dir: Path) -> Path:
    """Write users to the cache atomically (temp file, then rename); return its path."""
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / CACHE_NAME
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(users, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def load_cache(data_dir: Path) -> list[dict]:
    """Read cached users; raise FetchError if no cache exists yet."""
    path = data_dir / CACHE_NAME
    if not path.exists():
        raise FetchError(f"No cache at {path}; run once without --offline first")
    return json.loads(path.read_text(encoding="utf-8"))


def get_users(
    cfg: Config,
    offline: bool = False,
    session: requests.Session | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict]:
    """Return users from the cache when offline, else fetch and refresh the cache."""
    if offline:
        return load_cache(cfg.data_dir)
    users = fetch_users(cfg, session, sleep)
    save_cache(users, cfg.data_dir)
    return users