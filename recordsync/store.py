"""SQLite persistence. Idempotent: crosswalk-based ids, upserts, one transaction per run."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from recordsync.survive import Golden

NAMESPACE = uuid.UUID("6f1c2a52-5b1e-4e0b-9a51-2f3f0d6c9b11")
FIELDS = ("name", "email", "phone", "company", "address")

SCHEMA = """
CREATE TABLE IF NOT EXISTS golden_customers (
    golden_id TEXT PRIMARY KEY, status TEXT NOT NULL,
    name TEXT, email TEXT, phone TEXT, company TEXT, address TEXT,
    last_run_id INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS crosswalk (
    source TEXT NOT NULL, source_id TEXT NOT NULL, golden_id TEXT NOT NULL,
    PRIMARY KEY (source, source_id));
CREATE TABLE IF NOT EXISTS field_lineage (
    golden_id TEXT NOT NULL, field TEXT NOT NULL, value TEXT, source TEXT, rule TEXT,
    PRIMARY KEY (golden_id, field));
CREATE TABLE IF NOT EXISTS conflicts (
    golden_id TEXT NOT NULL, field TEXT NOT NULL, crm_value TEXT, api_value TEXT,
    chosen TEXT, rule TEXT, status TEXT NOT NULL DEFAULT 'open',
    PRIMARY KEY (golden_id, field));
CREATE TABLE IF NOT EXISTS runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL, summary TEXT NOT NULL);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    """Open the database, creating the directory and tables if needed."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    return conn


def source_keys(g: Golden) -> list[tuple[str, str]]:
    """The (source, source_id) keys behind a golden record."""
    return [(s, i) for s, i in (("crm", g.crm_id), ("api", g.api_id)) if i]


def resolve_id(conn: sqlite3.Connection, keys: list[tuple[str, str]], taken: set) -> str:
    """Reuse a crosswalk id not already used this run; otherwise mint a stable uuid5."""
    known = sorted({row[0] for k in keys for row in conn.execute(
        "SELECT golden_id FROM crosswalk WHERE source = ? AND source_id = ?", k)} - taken)
    if known:
        return known[0]
    return str(uuid.uuid5(NAMESPACE, "|".join(f"{s}:{i}" for s, i in sorted(keys))))


def _upsert_golden(conn: sqlite3.Connection, gid: str, g: Golden, run_id: int) -> None:
    """Insert or update the golden row, its lineage, and its crosswalk entries."""
    conn.execute("""INSERT INTO golden_customers VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(golden_id) DO UPDATE SET status = excluded.status, name = excluded.name,
          email = excluded.email, phone = excluded.phone, company = excluded.company,
          address = excluded.address, last_run_id = excluded.last_run_id""",
                 (gid, g.status, *(g.fields[f].value for f in FIELDS), run_id))
    conn.executemany("""INSERT INTO field_lineage VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(golden_id, field) DO UPDATE SET value = excluded.value,
          source = excluded.source, rule = excluded.rule""",
                     [(gid, f, fv.value, fv.source, fv.rule) for f, fv in g.fields.items()])
    conn.executemany("""INSERT INTO crosswalk VALUES (?, ?, ?)
        ON CONFLICT(source, source_id) DO UPDATE SET golden_id = excluded.golden_id""",
                     [(s, i, gid) for s, i in source_keys(g)])


def _sync_conflicts(conn: sqlite3.Connection, gid: str, g: Golden) -> None:
    """Upsert current conflicts, keeping a human's status unless the values changed."""
    fields = [c.field for c in g.conflicts]
    conn.execute(f"DELETE FROM conflicts WHERE golden_id = ? AND field NOT IN "
                 f"({','.join('?' * len(fields))})", (gid, *fields))
    conn.executemany("""INSERT INTO conflicts (golden_id, field, crm_value, api_value, chosen, rule)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(golden_id, field) DO UPDATE SET
          status = CASE WHEN conflicts.crm_value = excluded.crm_value
                         AND conflicts.api_value = excluded.api_value
                        THEN conflicts.status ELSE 'open' END,
          crm_value = excluded.crm_value, api_value = excluded.api_value,
          chosen = excluded.chosen, rule = excluded.rule""",
                     [(gid, c.field, c.crm_value, c.api_value, c.chosen, c.rule) for c in g.conflicts])


def _drop_orphans(conn: sqlite3.Connection) -> None:
    """Delete golden records no source points to any more (they were merged into another)."""
    orphans = "SELECT golden_id FROM golden_customers WHERE golden_id NOT IN (SELECT golden_id FROM crosswalk)"
    for table in ("field_lineage", "conflicts", "golden_customers"):
        conn.execute(f"DELETE FROM {table} WHERE golden_id IN ({orphans})")


def save(conn: sqlite3.Connection, goldens: list[Golden], summary: dict) -> tuple[int, list[str]]:
    """Write one run atomically. Returns (run_id, golden ids aligned with `goldens`)."""
    with conn:
        run_id = conn.execute("INSERT INTO runs (started_at, summary) VALUES (?, ?)",
                              (datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               json.dumps(summary))).lastrowid
        ids: list[str] = []
        for g in goldens:
            gid = resolve_id(conn, source_keys(g), set(ids))
            ids.append(gid)
            _upsert_golden(conn, gid, g, run_id)
            _sync_conflicts(conn, gid, g)
        _drop_orphans(conn)
    return run_id, ids