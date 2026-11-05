"""Tests for schemas.py."""
from recordsync.schemas import validate_api, validate_crm


def crm_row(**overrides):
    row = {"crm_id": "CRM-001", "full_name": "Leanne Graham", "email": "sincere@april.biz",
           "phone": "770-736-8031", "company": "Romaguera-Crona"}
    return {**row, **overrides}


def test_good_row_has_no_issues():
    result = validate_crm([crm_row()])
    assert len(result.valid) == 1 and result.issues == []


def test_missing_email_reported_with_row_and_field():
    result = validate_crm([crm_row(crm_id="CRM-901", email="")])
    [issue] = result.errors
    assert (issue.row, issue.record_id, issue.field) == (2, "CRM-901", "email")
    assert "required" in issue.message
    assert result.valid == []


def test_two_bad_fields_give_two_errors_on_same_row():
    result = validate_crm([crm_row(crm_id="CRM-902", email="bob[at]example", phone="call me")])
    assert [(i.row, i.field) for i in result.errors] == [(2, "email"), (2, "phone")]


def test_bad_rows_do_not_stop_good_ones():
    rows = [crm_row(crm_id="A"), crm_row(crm_id="B", email=""), crm_row(crm_id="C")]
    result = validate_crm(rows)
    assert [r.crm_id for r in result.valid] == ["A", "C"]
    assert [i.row for i in result.errors] == [3]


def test_impossible_area_code_warns_but_keeps_row():
    result = validate_crm([crm_row(phone="010-692-6593 x09125")])
    assert len(result.valid) == 1 and result.errors == []
    [warning] = result.warnings
    assert (warning.field, warning.severity) == ("phone", "warning")
    assert "010" in warning.message


def test_whitespace_is_stripped():
    result = validate_crm([crm_row(email="  sincere@april.biz  ")])
    assert result.valid[0].email == "sincere@april.biz"


def test_api_users_validate_and_nested_errors_name_the_path(api_users):
    api_users[0]["company"] = {"name": ""}
    result = validate_api(api_users)
    assert len(result.valid) == 9
    [issue] = result.errors
    assert (issue.row, issue.record_id, issue.field) == (1, "1", "company.name")