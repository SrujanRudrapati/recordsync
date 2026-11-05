"""Tests for generate.py."""
import csv

import pytest

from recordsync.generate import CASES, CRM_FIELDS, build_rows, generate


def _by_id(rows):
    return {r["crm_id"]: r for r in rows}


def test_output_is_deterministic(api_users, tmp_path):
    a = generate(api_users, tmp_path / "a").read_bytes()
    b = generate(api_users, tmp_path / "b").read_bytes()
    assert a == b


def test_every_api_user_but_8_has_a_crm_row():
    linked = {c.api_id for c in CASES.values() if c.api_id is not None}
    assert linked == set(range(1, 11)) - {8}


def test_overrides_win_over_api_values(api_users):
    rows = _by_id(build_rows(api_users))
    assert rows["CRM-001"]["email"] == "SINCERE@APRIL.BIZ"
    assert rows["CRM-004"]["company"] == "ROBEL-CORKERY"
    assert rows["CRM-004"]["email"] == api_users[3]["email"]  # untouched field kept


def test_shared_email_case_keeps_email_but_changes_person(api_users):
    row = _by_id(build_rows(api_users))["CRM-007"]
    assert row["email"] == api_users[6]["email"]
    assert row["full_name"] != api_users[6]["name"]


def test_crm_only_rows_have_every_column(api_users):
    for row in build_rows(api_users):
        if CASES[row["crm_id"]].expect == "crm_only":
            assert set(row) == set(CRM_FIELDS) and all(row.values())


def test_missing_api_user_is_a_clear_error(api_users):
    with pytest.raises(ValueError, match="api_id 3"):
        build_rows([u for u in api_users if u["id"] != 3])


def test_csv_round_trip(api_users, tmp_path):
    path = generate(api_users, tmp_path)
    with path.open(newline="", encoding="utf-8") as f:
        assert list(csv.DictReader(f)) == build_rows(api_users)