"""Two-pass, one-to-one matching: email + name first, then fuzzy name + company."""
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import cached_property

from recordsync.config import Thresholds
from recordsync.normalize import normalize_company, normalize_email, normalize_name
from recordsync.schemas import ApiUser, CrmRow


@dataclass(frozen=True)
class Record:
    """A validated record from either source, in one shape."""
    source: str
    source_id: str
    name: str
    email: str
    phone: str
    company: str
    address: str = ""

    @property
    def key(self) -> tuple[str, str]:
        """Unique identity across both sources."""
        return (self.source, self.source_id)

    @cached_property
    def name_key(self) -> str:
        """Normalized name used for matching."""
        return normalize_name(self.name)

    @cached_property
    def email_key(self) -> str:
        """Normalized email used for matching."""
        return normalize_email(self.email)

    @cached_property
    def company_key(self) -> str:
        """Normalized company used for matching."""
        return normalize_company(self.company)


def from_crm(row: CrmRow) -> Record:
    """Wrap a validated CRM row."""
    return Record("crm", row.crm_id, row.full_name, row.email, row.phone, row.company)


def from_api(user: ApiUser) -> Record:
    """Wrap a validated API user, flattening the address."""
    a = user.address
    address = ", ".join(p for p in (a.street, a.suite, a.city, a.zipcode) if p) if a else ""
    return Record("api", str(user.id), user.name, user.email, user.phone, user.company.name, address)


@dataclass(frozen=True)
class Pair:
    """A candidate link between one CRM and one API record."""
    crm: Record
    api: Record
    method: str          # "email" or "fuzzy"
    name_score: float
    company_score: float
    decision: str        # "match" or "review"


@dataclass
class MatchResult:
    matched: list[Pair]
    review: list[Pair]
    crm_only: list[Record]
    api_only: list[Record]


def similarity(a: str, b: str) -> float:
    """difflib ratio in [0, 1], rounded so reports and tie-breaks are stable."""
    return round(SequenceMatcher(None, a, b).ratio(), 3)


def _email_candidates(crm: list[Record], api: list[Record], t: Thresholds) -> list[Pair]:
    """Pass 1: same email. A match only if the names also agree; otherwise review."""
    out = []
    for c in crm:
        for a in api:
            if c.email_key == a.email_key:
                ns = similarity(c.name_key, a.name_key)
                out.append(Pair(c, a, "email", ns, similarity(c.company_key, a.company_key),
                                "match" if ns >= t.email_name_min else "review"))
    return out


def _fuzzy_candidates(crm: list[Record], api: list[Record], t: Thresholds) -> list[Pair]:
    """Pass 2: name at or above the review floor AND company similar enough."""
    out = []
    for c in crm:
        for a in api:
            ns, cs = similarity(c.name_key, a.name_key), similarity(c.company_key, a.company_key)
            if ns >= t.name_review and cs >= t.company_min:
                out.append(Pair(c, a, "fuzzy", ns, cs, "match" if ns >= t.name_auto else "review"))
    return out


def _take_one_to_one(candidates: list[Pair], used: set) -> list[Pair]:
    """Accept candidates best-first (deterministic ties), skipping records already used."""
    ordered = sorted(candidates, key=lambda p: (-p.name_score, -p.company_score,
                                                p.crm.source_id, p.api.source_id))
    taken = []
    for p in ordered:
        if p.crm.key not in used and p.api.key not in used:
            used.update((p.crm.key, p.api.key))
            taken.append(p)
    return taken


def _free(records: list[Record], used: set) -> list[Record]:
    """Records not yet claimed by any pair."""
    return [r for r in records if r.key not in used]


def match_records(crm: list[Record], api: list[Record], t: Thresholds) -> MatchResult:
    """Strong email pairs, then fuzzy on leftovers, then weak email pairs go to review."""
    used: set = set()
    email = _email_candidates(crm, api, t)
    pairs = _take_one_to_one([p for p in email if p.decision == "match"], used)
    pairs += _take_one_to_one(_fuzzy_candidates(_free(crm, used), _free(api, used), t), used)
    pairs += _take_one_to_one([p for p in email if p.decision == "review"], used)
    return MatchResult(matched=[p for p in pairs if p.decision == "match"],
                       review=[p for p in pairs if p.decision == "review"],
                       crm_only=_free(crm, used), api_only=_free(api, used))


def _histogram(scores: list[float]) -> list[str]:
    """Text histogram of scores in 0.1-wide buckets (1.0 lands in the top bucket)."""
    lines = []
    for i in range(10):
        n = sum(i / 10 <= s < (i + 1) / 10 or (i == 9 and s == 1.0) for s in scores)
        lines.append(f"  {i / 10:.1f}-{(i + 1) / 10:.1f} {'#' * n} {n}")
    return lines


def score_report(crm: list[Record], api: list[Record], t: Thresholds) -> str:
    """For each CRM record: best and runner-up API name score; then a histogram of all pairs."""
    if not api:
        return "no API records to score"
    lines = [f"thresholds: email+name>={t.email_name_min} auto>={t.name_auto} "
             f"review>={t.name_review} company>={t.company_min}",
             f"{'crm_id':9}{'best api':>9}{'name':>7}{'company':>9}{'runner-up':>11}"]
    scores = []
    for c in crm:
        ranked = sorted(((similarity(c.name_key, a.name_key),
                          similarity(c.company_key, a.company_key), a.source_id) for a in api),
                        reverse=True)
        scores += [r[0] for r in ranked]
        (ns, cs, aid), runner = ranked[0], (ranked[1][0] if len(ranked) > 1 else 0.0)
        lines.append(f"{c.source_id:9}{aid:>9}{ns:7.2f}{cs:9.2f}{runner:11.2f}")
    return "\n".join(lines + ["name-score histogram (all CRM x API pairs):"] + _histogram(scores))