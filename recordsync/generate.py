"""Generate a synthetic CRM export (System A) from API users, with deliberate mismatches."""
import csv
from dataclasses import dataclass, field
from pathlib import Path

CRM_FIELDS = ["crm_id", "full_name", "email", "phone", "company"]


@dataclass(frozen=True)
class Case:
    """One CRM row: the API user it derives from, its overrides, and the intended outcome."""
    api_id: int | None  # None means a CRM-only customer (or an invalid row)
    expect: str         # match_email | match_fuzzy | review | crm_only | invalid
    overrides: dict = field(default_factory=dict)


CASES: dict[str, Case] = {
    "CRM-001": Case(1, "match_email", {"email": "SINCERE@APRIL.BIZ", "phone": "770.736.8031 x56442"}),
    "CRM-002": Case(2, "match_fuzzy", {"full_name": "Erv Howell", "email": "ervin.howell@mail.example",
                                       "company": "Deckow-Crist Inc."}),
    "CRM-003": Case(3, "match_email", {"full_name": "Clem Bauch", "email": "nathan@Yesenia.NET",
                                       "phone": "463-555-0199"}),          # phone conflict
    "CRM-004": Case(4, "match_email", {"full_name": "Pat Lebsack", "company": "ROBEL-CORKERY"}),
    "CRM-005": Case(5, "review", {"full_name": "Chelsea Dietz", "email": "c.dietz@keebler.example"}),
    "CRM-006": Case(6, "match_email", {"full_name": "Dennis Schulist", "phone": "477-935-0000"}),  # phone conflict
    "CRM-007": Case(7, "review", {"full_name": "Maria Lopez"}),           # shares Kurtis's email
    "CRM-009": Case(9, "match_fuzzy", {"full_name": "GLENNA REICHERT", "email": "glenna@yost.example",
                                       "company": "Yost & Sons"}),
    "CRM-010": Case(10, "match_email", {"email": "REY.PADBERG@KARINA.BIZ", "phone": "024 648 3804"}),
    "CRM-101": Case(None, "crm_only", {"full_name": "Priya Natarajan", "email": "priya@lumen.example",
                                       "phone": "602-555-0142", "company": "Lumen Analytics"}),
    "CRM-102": Case(None, "crm_only", {"full_name": "Tomás Ruiz", "email": "tomas.ruiz@cactus.example",
                                       "phone": "480-555-0177", "company": "Cactus Works"}),
    "CRM-901": Case(None, "invalid", {"full_name": "Missing Email", "email": "",
                                      "phone": "602-555-0100", "company": "Nowhere Inc"}),
    "CRM-902": Case(None, "invalid", {"full_name": "Bad Email", "email": "bob[at]example",
                                      "phone": "call me", "company": "Nowhere Inc"}),
}


def _lookup(by_id: dict[int, dict], api_id: int) -> dict:
    """Return the API user for api_id, failing loudly if the API data lacks it."""
    if api_id not in by_id:
        raise ValueError(f"CASES references api_id {api_id}, which is not in the API data")
    return by_id[api_id]


def _base_row(user: dict) -> dict:
    """Map an API user onto CRM columns, before any mutation."""
    return {"full_name": user["name"], "email": user["email"],
            "phone": user["phone"], "company": user["company"]["name"]}


def build_rows(users: list[dict]) -> list[dict]:
    """Build one CRM row per case: the API user's data with the case's overrides on top."""
    by_id = {u["id"]: u for u in users}
    rows = []
    for crm_id, case in CASES.items():
        base = _base_row(_lookup(by_id, case.api_id)) if case.api_id is not None else {}
        rows.append({"crm_id": crm_id, **base, **case.overrides})
    return rows


def write_crm_csv(rows: list[dict], path: Path) -> Path:
    """Write rows to CSV atomically (temp file, then rename) in a fixed column order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CRM_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)
    return path


def generate(users: list[dict], data_dir: Path) -> Path:
    """Build and write data_dir/crm.csv; same input always gives the same bytes."""
    return write_crm_csv(build_rows(users), data_dir / "crm.csv")