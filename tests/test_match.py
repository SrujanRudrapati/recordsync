"""Tests for match.py."""
from recordsync.config import Thresholds
from recordsync.match import Record, match_records, score_report

T = Thresholds()


def crm(id_, name, email, company="Acme"):
    return Record("crm", id_, name, email, "602-555-0100", company)


def api(id_, name, email, company="Acme"):
    return Record("api", id_, name, email, "602-555-0100", company)


def ids(pairs):
    return [(p.crm.source_id, p.api.source_id) for p in pairs]


def test_email_and_similar_name_match_in_pass_1():
    r = match_records([crm("C1", "Leanne Graham", "SINCERE@april.biz")],
                      [api("1", "Leanne Graham", "sincere@april.biz")], T)
    assert ids(r.matched) == [("C1", "1")] and r.matched[0].method == "email"


def test_shared_email_with_different_name_goes_to_review():
    r = match_records([crm("C7", "Maria Lopez", "info@acme.example")],
                      [api("7", "Kurtis Weissnat", "info@acme.example")], T)
    assert r.matched == [] and ids(r.review) == [("C7", "7")]


def test_shared_email_does_not_block_a_better_fuzzy_match():
    r = match_records([crm("C1", "Maria Lopez", "info@acme.example")],
                      [api("1", "Kurtis Weissnat", "info@acme.example"),
                       api("2", "Maria Lopez", "maria@acme.example")], T)
    assert ids(r.matched) == [("C1", "2")] and r.matched[0].method == "fuzzy"
    assert [a.source_id for a in r.api_only] == ["1"] and r.review == []


def test_nickname_plus_same_company_is_a_fuzzy_match():
    r = match_records([crm("C2", "Erv Howell", "erv@mail.example", "Deckow-Crist Inc.")],
                      [api("2", "Ervin Howell", "shanna@melissa.tv", "Deckow-Crist")], T)
    assert ids(r.matched) == [("C2", "2")]


def test_same_name_different_company_does_not_match():
    r = match_records([crm("C1", "Leanne Graham", "a@x.example", "Acme")],
                      [api("1", "Leanne Graham", "b@y.example", "Globex")], T)
    assert r.matched == [] and len(r.crm_only) == 1 and len(r.api_only) == 1


def test_name_in_review_band_goes_to_review():
    r = match_records([crm("C5", "Chelsea Dietz", "c@keebler.example", "Keebler LLC")],
                      [api("5", "Chelsey Dietrich", "lucio@annie.ca", "Keebler LLC")], T)
    assert r.matched == [] and ids(r.review) == [("C5", "5")]


def test_matching_is_one_to_one():
    r = match_records([crm("C1", "Leanne Graham", "a@x.example"),
                       crm("C2", "Leanne Grahm", "b@x.example")],
                      [api("1", "Leanne Graham", "c@x.example")], T)
    assert ids(r.matched) == [("C1", "1")]
    assert [c.source_id for c in r.crm_only] == ["C2"]


def test_score_report_lists_every_crm_record():
    report = score_report([crm("C1", "Leanne Graham", "a@x.example"),
                           crm("C2", "Priya Natarajan", "p@x.example")],
                          [api("1", "Leanne Graham", "a@x.example")], T)
    assert "C1" in report and "C2" in report and "auto>=0.85" in report