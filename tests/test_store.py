"""Tests for store.py."""
from contextlib import closing

import pytest

from recordsync.match import Record
from recordsync.store import connect, save
from recordsync.survive import merge


def rec(source, id_, phone="602-555-0100"):
    return Record(source, id_, "Leanne Graham", "sincere@april.biz", phone, "Romaguera-Crona")


@pytest.fixture
def conn(tmp_path):
    with closing(connect(tmp_path / "t.db")) as c:
        yield c


def count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_rerun_is_idempotent(conn):
    goldens = [merge(rec("crm", "C1"), rec("api", "1", phone="602-555-0199"), "matched"),
               merge(rec("crm", "C2"), None, "crm_only")]
    _, first = save(conn, goldens, {})
    _, second = save(conn, goldens, {})
    assert first == second
    tables = ("golden_customers", "crosswalk", "field_lineage", "conflicts", "runs")
    assert [count(conn, t) for t in tables] == [2, 3, 10, 1, 2]


def test_review_pair_later_merged_becomes_one_record(conn):
    c, a = rec("crm", "C5"), rec("api", "5")
    _, before = save(conn, [merge(c, None, "review"), merge(None, a, "review")], {})
    _, [after] = save(conn, [merge(c, a, "matched")], {})
    assert after in before and count(conn, "golden_customers") == 1
    assert {r[0] for r in conn.execute("SELECT golden_id FROM crosswalk")} == {after}


def test_matched_pair_later_split_becomes_two_records(conn):
    c, a = rec("crm", "C5"), rec("api", "5")
    _, [merged] = save(conn, [merge(c, a, "matched")], {})
    _, split = save(conn, [merge(c, None, "review"), merge(None, a, "review")], {})
    assert split[0] == merged and split[1] != merged
    assert count(conn, "golden_customers") == 2


def test_human_conflict_status_survives_rerun_unless_values_change(conn):
    def run(api_phone):
        save(conn, [merge(rec("crm", "C1"), rec("api", "1", phone=api_phone), "matched")], {})
        return conn.execute("SELECT status FROM conflicts").fetchone()[0]

    run("602-555-0199")
    with conn:
        conn.execute("UPDATE conflicts SET status = 'resolved'")
    assert run("602-555-0199") == "resolved"
    assert run("602-555-0123") == "open"