"""Survivorship: one golden record per customer, with field-level lineage and conflicts."""
from dataclasses import dataclass

from recordsync.match import MatchResult, Pair, Record
from recordsync.normalize import (display_name, is_nickname, normalize_company,
                                  normalize_name, split_phone)


@dataclass(frozen=True)
class FieldValue:
    """The surviving value of one field, where it came from, and why."""
    value: str
    source: str
    rule: str


@dataclass(frozen=True)
class Conflict:
    """Sources disagree after normalization; the rule chose a winner, a human should confirm."""
    field: str
    crm_value: str
    api_value: str
    chosen: str
    rule: str


@dataclass
class Golden:
    """One customer: surviving fields with lineage, conflicts, and the source ids behind it."""
    status: str            # matched | review | crm_only | api_only
    crm_id: str | None
    api_id: str | None
    fields: dict[str, FieldValue]
    conflicts: list[Conflict]
    pair: Pair | None = None


_EMPTY = Record("", "", "", "", "", "")


def canonical_phone(raw: str) -> str:
    """'770.736.8031 x56442' -> '7707368031 x56442'; '' stays ''."""
    digits, ext = split_phone(raw)
    return f"{digits} x{ext}" if ext else digits


def _choose(name: str, crm_val: str, api_val: str, order: tuple[str, str], rule: str,
            key=str) -> tuple[FieldValue, Conflict | None]:
    """First non-empty value in `order` wins; log a conflict if both exist and keys differ."""
    values = {"crm": crm_val, "api": api_val}
    present = [s for s in order if values[s]]
    if not present:
        return FieldValue("", "", "no value"), None
    if len(present) == 1:
        return FieldValue(values[present[0]], present[0], "only source with a value"), None
    winner = order[0]
    conflict = Conflict(name, crm_val, api_val, winner, rule) if key(crm_val) != key(api_val) else None
    return FieldValue(values[winner], winner, rule), conflict


def _name_rule(crm_name: str, api_name: str) -> tuple[tuple[str, str], str]:
    """CRM wins, unless CRM has a nickname and billing has the formal name."""
    if is_nickname(crm_name) and api_name and not is_nickname(api_name):
        return ("api", "crm"), "formal name over nickname"
    return ("crm", "api"), "crm wins"


def merge(crm: Record | None, api: Record | None, status: str, pair: Pair | None = None) -> Golden:
    """Build one golden record from up to one CRM and one API record."""
    c, a = crm or _EMPTY, api or _EMPTY
    name_order, name_rule = _name_rule(c.name, a.name)
    picks = {
        "name": _choose("name", display_name(c.name), display_name(a.name),
                        name_order, name_rule, normalize_name),
        "email": _choose("email", c.email_key, a.email_key, ("api", "crm"), "billing wins"),
        "phone": _choose("phone", canonical_phone(c.phone), canonical_phone(a.phone),
                         ("crm", "api"), "crm wins if valid"),
        "company": _choose("company", c.company, a.company, ("api", "crm"),
                           "billing wins", normalize_company),
        "address": _choose("address", c.address, a.address, ("api", "crm"), "billing wins"),
    }
    return Golden(status, crm and crm.source_id, api and api.source_id,
                  {f: fv for f, (fv, _) in picks.items()},
                  [cf for _, cf in picks.values() if cf], pair)


def build_goldens(result: MatchResult) -> list[Golden]:
    """Matched pairs merge; review pairs and unmatched records become single-source goldens."""
    goldens = [merge(p.crm, p.api, "matched", p) for p in result.matched]
    for p in result.review:
        goldens += [merge(p.crm, None, "review", p), merge(None, p.api, "review", p)]
    goldens += [merge(r, None, "crm_only") for r in result.crm_only]
    goldens += [merge(None, r, "api_only") for r in result.api_only]
    return goldens