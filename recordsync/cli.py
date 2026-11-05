"""RecordSync: reconcile CRM and billing customers into golden records."""
import argparse
import json
import sys
from contextlib import closing
from pathlib import Path

from recordsync.config import Config, load_config
from recordsync.fetch import FetchError, get_users
from recordsync.generate import generate
from recordsync.match import from_api, from_crm, match_records, score_report
from recordsync.report import build_report, summarize, write_report
from recordsync.schemas import load_crm, validate_api, validate_crm
from recordsync.store import connect, save
from recordsync.survive import build_goldens


def run(cfg: Config, crm_path: Path, offline: bool) -> dict:
    """One full sync: fetch, validate, match, survive, store, report. Returns the report."""
    api_v = validate_api(get_users(cfg, offline=offline))
    crm_v = validate_crm(load_crm(crm_path))
    crm, api = [from_crm(r) for r in crm_v.valid], [from_api(u) for u in api_v.valid]
    print(score_report(crm, api, cfg.thresholds), "\n")
    result = match_records(crm, api, cfg.thresholds)
    goldens = build_goldens(result)
    summary = summarize(crm_v, api_v, result, goldens)
    with closing(connect(cfg.db_path)) as conn:
        run_id, ids = save(conn, goldens, summary)
    report = build_report(run_id, summary, result, goldens, ids, crm_v.issues + api_v.issues)
    write_report(report, cfg.data_dir / "report.json")
    return report


def main(argv: list[str] | None = None) -> int:
    """Parse args and run one sync. Exit 0 on success, 2 on missing or unreachable input."""
    parser = argparse.ArgumentParser(prog="recordsync", description=__doc__)
    parser.add_argument("--offline", action="store_true", help="use the cached API response")
    parser.add_argument("--generate-crm", action="store_true", help="(re)build the synthetic CRM CSV first")
    parser.add_argument("--crm", type=Path, help="CRM CSV path (default: <data dir>/crm.csv)")
    args = parser.parse_args(argv)
    cfg = load_config()
    crm_path, offline = args.crm or cfg.data_dir / "crm.csv", args.offline
    try:
        if args.generate_crm:
            crm_path = generate(get_users(cfg, offline=offline), cfg.data_dir)
            offline = True  # the cache was just refreshed; don't fetch twice
        report = run(cfg, crm_path, offline)
    except (FetchError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report["summary"], indent=2))
    print(f"report: {cfg.data_dir / 'report.json'}  db: {cfg.db_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())