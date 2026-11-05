from pathlib import Path

from recordsync.config import DEFAULT_API_URL, load_config


def test_defaults(monkeypatch):
    monkeypatch.delenv("RECORDSYNC_API_URL", raising=False)
    monkeypatch.delenv("RECORDSYNC_DATA_DIR", raising=False)
    cfg = load_config()
    assert cfg.api_url == DEFAULT_API_URL
    assert cfg.db_path == Path("data/recordsync.db")


def test_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("RECORDSYNC_API_URL", "http://localhost:9999/users")
    monkeypatch.setenv("RECORDSYNC_DATA_DIR", str(tmp_path))
    cfg = load_config()
    assert cfg.api_url == "http://localhost:9999/users"
    assert cfg.db_path == tmp_path / "recordsync.db"


def test_threshold_band_is_ordered():
    t = load_config().thresholds
    assert t.name_review < t.name_auto