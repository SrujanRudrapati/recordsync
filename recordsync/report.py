"""Build and write the JSON reconciliation report."""
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from recordsync.match import MatchResult, Pair
from recordsync.schemas import Issue, ValidationResult
from recordsync.store import source_keys
from recordsync.survive import Golden


def summarize(crm_v: ValidationResult, api_v: ValidationResult,
              result: MatchResult, goldens: list[Golden]) -> dict:
    """Headline counts. Per source: matched + review + only == valid rows."""
    return {"crm_valid": len(crm_v.valid), "api_valid": len(api_v.valid),
            "matched": len(result.matched), "review": len(result.review),
            "crm_only": len(result.crm_only), "api_only": len(result.api_only),
            "golden_records": len(goldens),
            "conflicts": sum(len(g.conflicts) for g in goldens),
            "errors": len(crm_v.errors) + len(api_v.errors),
            "warnings": len(crm_v.warnings) + len(api_v.warnings)}


def _pair_row(p: Pair, ids: dict) -> dict:
    """One matched or review pair, with scores and the golden id on each side."""
    return {"crm_id": p.crm.source_id, "api_id": p.api.source_id, "method": p.method,
            "name_score": p.name_score, "company_score": p.company_score,
            "crm_name": p.crm.name, "api_name": p.api.name,
            "crm_golden_id": ids[p.crm.key], "api_golden_id": ids[p.api.key]}


def build_report(run_id: int, summary: dict, result: MatchResult, goldens: list[Golden],
                 golden_ids: list[str], issues: list[Issue]) -> dict:
    """Assemble the full report: summary, pairs, unmatched, conflicts, validation."""
    ids = {key: gid for g, gid in zip(goldens, golden_ids) for key in source_keys(g)}
    return {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summary": summary,
        "matched": [_pair_row(p, ids) for p in result.matched],
        "review": [_pair_row(p, ids) for p in result.review],
        "unmatched": {
            "crm": [{"crm_id": r.source_id, "name": r.name, "golden_id": ids[r.key]} for r in result.crm_only],
            "api": [{"api_id": r.source_id, "name": r.name, "golden_id": ids[r.key]} for r in result.api_only]},
        "conflicts": [{"golden_id": gid, "crm_id": g.crm_id, "api_id": g.api_id, **asdict(c)}
                      for g, gid in zip(goldens, golden_ids) for c in g.conflicts],
        "validation": {"errors": [asdict(i) for i in issues if i.severity == "error"],
                       "warnings": [asdict(i) for i in issues if i.severity == "warning"]},
    }


def write_report(report: dict, path: Path) -> Path:
    """Write the report atomically as pretty JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return path