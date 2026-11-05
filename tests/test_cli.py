"""End-to-end tests: the CLI, offline, against a real API snapshot."""
import json
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from recordsync.cli import main
from recordsync.config import load_config
from recordsync.generate import CASES

FIXTURE = Path(__file__).parent / "fixtures" / "api_users.json"
TABLES = {"golden_customers": "golden_id, status, name, email, phone, company, address",
          "crosswalk": "*", "field_lineage": "*", "conflicts": "*"}


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("RECORDSYNC_DATA_DIR", str(tmp_path))
    shutil.copy(FIXTURE, tmp_path / "api_users.json")
    return load_config()


def _snapshot(db: Path) -> dict:
    with closing(sqlite3.connect(db)) as conn:
        return {t: sorted(conn.execute(f"SELECT {cols} FROM {t}")) for t, cols in TABLES.items()}


def test_end_to_end_matches_ground_truth(cfg):
    assert main(["--offline", "--generate-crm"]) == 0
    report = json.loads((cfg.data_dir / "report.json").read_text(encoding="utf-8"))
    outcome = {r["crm_id"]: f"match_{r['method']}" for r in report["matched"]}
    outcome |= {r["crm_id"]: "review" for r in report["review"]}
    outcome |= {r["crm_id"]: "crm_only" for r in report["unmatched"]["crm"]}
    outcome |= {e["record_id"]: "invalid" for e in report["validation"]["errors"] if e["source"] == "crm"}
    assert outcome == {crm_id: case.expect for crm_id, case in CASES.items()}
    assert [r["api_id"] for r in report["unmatched"]["api"]] == ["8"]
    s = report["summary"]
    assert s["matched"] + s["review"] + s["crm_only"] == s["crm_valid"]
    assert s["matched"] + s["review"] + s["api_only"] == s["api_valid"]


def test_rerun_changes_nothing(cfg):
    assert main(["--offline", "--generate-crm"]) == 0
    first = _snapshot(cfg.db_path)
    assert main(["--offline"]) == 0
    assert _snapshot(cfg.db_path) == first


def test_missing_crm_file_exits_with_error(cfg, capsys):
    assert main(["--offline"]) == 2
    assert "crm.csv" in capsys.readouterr().err