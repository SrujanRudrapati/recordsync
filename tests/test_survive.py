"""Tests for survive.py."""
from recordsync.match import MatchResult, Pair, Record
from recordsync.survive import build_goldens, merge


def rec(source, id_, name="Leanne Graham", email="sincere@april.biz",
        phone="770-736-8031 x56442", company="Romaguera-Crona", address=""):
    return Record(source, id_, name, email, phone, company, address)


def test_field_rules_and_lineage():
    g = merge(rec("crm", "C1", email="SINCERE@APRIL.BIZ"),
              rec("api", "1", address="Kulas Light, Gwenborough"), "matched")
    assert {f: v.source for f, v in g.fields.items()} == {
        "name": "crm", "email": "api", "phone": "crm", "company": "api", "address": "api"}
    assert g.fields["address"].rule == "only source with a value"
    assert g.conflicts == []


def test_formal_name_beats_nickname_without_a_conflict():
    g = merge(rec("crm", "C3", name="Clem Bauch"), rec("api", "3", name="Clementine Bauch"), "matched")
    assert (g.fields["name"].value, g.fields["name"].source) == ("Clementine Bauch", "api")
    assert g.fields["name"].rule == "formal name over nickname"
    assert g.conflicts == []


def test_crm_phone_wins_and_difference_is_a_conflict():
    g = merge(rec("crm", "C3", phone="463-555-0199"), rec("api", "3", phone="1-463-123-4447"), "matched")
    assert (g.fields["phone"].value, g.fields["phone"].source) == ("4635550199", "crm")
    [c] = g.conflicts
    assert (c.field, c.chosen, c.api_value) == ("phone", "crm", "4631234447")


def test_billing_email_wins_and_difference_is_a_conflict():
    g = merge(rec("crm", "C2", email="ervin.howell@mail.example"),
              rec("api", "2", email="Shanna@melissa.tv"), "matched")
    assert (g.fields["email"].value, g.fields["email"].source) == ("shanna@melissa.tv", "api")
    assert [c.field for c in g.conflicts] == ["email"]


def test_empty_value_never_wins():
    g = merge(rec("crm", "C1", phone=""), rec("api", "1"), "matched")
    assert (g.fields["phone"].source, g.fields["phone"].rule) == ("api", "only source with a value")
    assert g.conflicts == []


def test_single_source_golden_and_display_name():
    g = merge(rec("crm", "C9", name="GLENNA REICHERT"), None, "crm_only")
    assert g.fields["name"].value == "Glenna Reichert"
    assert {v.source for v in g.fields.values() if v.value} == {"crm"}
    assert (g.crm_id, g.api_id, g.conflicts) == ("C9", None, [])


def test_build_goldens_keeps_review_pairs_separate():
    c, a = rec("crm", "C5"), rec("api", "5")
    result = MatchResult(matched=[], review=[Pair(c, a, "fuzzy", 0.76, 1.0, "review")],
                         crm_only=[rec("crm", "C6")], api_only=[rec("api", "8")])
    got = sorted((g.status, g.crm_id or "", g.api_id or "") for g in build_goldens(result))
    assert got == [("api_only", "", "8"), ("crm_only", "C6", ""),
                   ("review", "", "5"), ("review", "C5", "")]