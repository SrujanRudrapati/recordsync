# RecordSync

Reconciles customer records from a CRM CSV export (System A) and a billing API (System B;
JSONPlaceholder `/users` stands in) into one golden record per customer, with field-level
lineage, stored in SQLite, plus a JSON reconciliation report.

## Run

```bash
pip install -r requirements.txt
python -m recordsync.cli --generate-crm   # first run: fetch API, build synthetic CRM, sync
python -m recordsync.cli --offline        # re-run from the cached API response
pytest -q
```

Outputs go to `data/recordsync.db` and `data/report.json`. `RECORDSYNC_API_URL` and
`RECORDSYNC_DATA_DIR` override the defaults. No credentials are needed or stored.

Pipeline: fetch (timeout, 3 retries with exponential backoff on 429/5xx/connection errors,
cached to disk) → validate (pydantic; bad rows reported, never fatal) → normalize → match →
survive → store → report.

## Decisions

**Matching** is one-to-one, best score first, in three passes:
1. Same email and name similarity ≥ 0.60 → match.
2. Fuzzy on the leftovers: name ≥ 0.85 and company ≥ 0.80 → match; name 0.70–0.85 → review.
3. Same email but names disagree → review. This pass runs last, so a shared inbox
   (billing@, info@) can't block a real fuzzy match.

**Review pairs are never merged.** Each side gets its own golden record with status `review`.

**Survivorship.** A valid value is never replaced by an empty one. Any disagreement left
after normalization is logged as a conflict, even though a rule picked a winner.

| Field | Winner |
|---|---|
| Name | CRM, unless the CRM has a nickname and billing has the formal name |
| Email | Billing |
| Phone | CRM if valid, else billing |
| Company, address | Billing |

**Phones** are valid with 10 digits after normalization, and extensions are kept separately.
Area codes starting with 0 or 1 produce a warning, not a rejection.

**The nickname map** is deliberately tiny (Clem, Pat, Erv) and pinned by a test, because
every entry is a false-merge risk.

**Idempotency.** Golden ids come from a crosswalk of (source, source_id). New ids are
uuid5 of the source keys, so even a fresh database reproduces them. Writes are upserts in
one transaction per run. If a review pair is later merged, one id survives and the other is
deleted; if a match is later split, the CRM side keeps the id. A conflict's review status
survives re-runs unless its values change.

## Known limitations

- **Thresholds are not calibrated.** The data has true matches at 1.00, one near miss at
  0.76 and nothing in between, so it can't tell 0.85 from 0.80 or 0.90. Fix: label a set
  of near-miss pairs from real data and tune the thresholds against precision and recall.
- **The losing email survives only as a conflict.** When billing's email wins, the CRM
  email is often the person's day-to-day contact. A real system should keep it as a
  secondary contact.
- **An invalid CRM phone rejects the whole row**, so the "else billing" phone rule only
  fires when the CRM phone is empty. Fix: downgrade a bad phone to a warning and blank it.
- **Review decisions don't feed back.** There is no override table, so a human confirming
  a review pair has no effect on the next run.
- **Records deleted upstream are not retired.** `last_run_id` shows which golden records
  the latest run didn't touch.
- **The name metric is blunt and matching is O(n×m).** That's fine for thousands of rows.
  Larger data needs blocking (by company or email domain) and a name-specific metric
  such as Jaro-Winkler.
- **A missing extension counts as a phone conflict**, even when the digits agree.