"""Pydantic schemas for both sources, and validate_rows(), which reports bad rows and keeps going."""
import csv
import re
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Annotated, Iterable

from pydantic import AfterValidator, BaseModel, ConfigDict, ValidationError

from recordsync.normalize import split_phone

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class Issue:
    """One data-quality finding. 'error' rejects the row; 'warning' keeps it."""
    source: str             # "crm" or "api"
    row: int                # CSV: file line number (header is line 1). API: 1-based position.
    record_id: str | None
    field: str
    message: str
    severity: str = "error"


@dataclass
class ValidationResult:
    """Valid records plus every issue found, in row order."""
    valid: list[BaseModel] = dc_field(default_factory=list)
    issues: list[Issue] = dc_field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]


def require_text(value: str) -> str:
    """Reject empty strings (whitespace is already stripped)."""
    if not value:
        raise ValueError("value is required")
    return value


def check_email(value: str) -> str:
    """Require a non-empty, plausibly shaped email; return it unchanged."""
    if not value:
        raise ValueError("email is required")
    if not EMAIL_RE.match(value):
        raise ValueError(f"not a valid email address: {value!r}")
    return value


def check_phone(value: str) -> str:
    """Require 10 digits once formatting, a leading US '1', and any extension are removed."""
    digits, _ = split_phone(value)
    if len(digits) != 10:
        raise ValueError(f"phone needs 10 digits after normalization, got {len(digits)}: {value!r}")
    return value


NonEmpty = Annotated[str, AfterValidator(require_text)]
Email = Annotated[str, AfterValidator(check_email)]
Phone = Annotated[str, AfterValidator(check_phone)]


class _Base(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")


class CrmRow(_Base):
    """One row of the CRM CSV export (System A)."""
    crm_id: NonEmpty
    full_name: NonEmpty
    email: Email
    phone: Phone
    company: NonEmpty


class Company(_Base):
    name: NonEmpty


class Address(_Base):
    street: str = ""
    suite: str = ""
    city: str = ""
    zipcode: str = ""


class ApiUser(_Base):
    """One user from the billing API (System B). Extra API fields are ignored."""
    id: int
    name: NonEmpty
    email: Email
    phone: Phone
    company: Company
    address: Address | None = None


def _record_id(raw: object, id_field: str) -> str | None:
    """Best-effort id for error messages, even when the row is malformed."""
    value = raw.get(id_field) if isinstance(raw, dict) else None
    return None if value in (None, "") else str(value)


def _issues_from(exc: ValidationError, source: str, row: int, record_id: str | None) -> list[Issue]:
    """Turn a pydantic ValidationError into one Issue per failing field."""
    return [
        Issue(source, row, record_id,
              ".".join(str(p) for p in err["loc"]) or "(record)",
              err["msg"].removeprefix("Value error, "))
        for err in exc.errors()
    ]


def _area_code_warning(phone: str, source: str, row: int, record_id: str | None) -> Issue | None:
    """Warn when the area code starts with 0 or 1, which no real US number has."""
    digits, _ = split_phone(phone)
    if digits[0] in "01":
        return Issue(source, row, record_id, "phone",
                     f"area code {digits[:3]} can't be a real US number", "warning")
    return None


def validate_rows(rows: Iterable[dict], model: type[_Base], source: str,
                  first_row: int, id_field: str) -> ValidationResult:
    """Validate each raw dict against model, collecting issues without stopping."""
    result = ValidationResult()
    for row, raw in enumerate(rows, start=first_row):
        record_id = _record_id(raw, id_field)
        try:
            item = model.model_validate(raw)
        except ValidationError as exc:
            result.issues.extend(_issues_from(exc, source, row, record_id))
            continue
        result.valid.append(item)
        if warning := _area_code_warning(item.phone, source, row, record_id):
            result.issues.append(warning)
    return result


def validate_crm(rows: Iterable[dict]) -> ValidationResult:
    """Validate CRM rows; row numbers are CSV line numbers (data starts on line 2)."""
    return validate_rows(rows, CrmRow, "crm", first_row=2, id_field="crm_id")


def validate_api(users: Iterable[dict]) -> ValidationResult:
    """Validate API users; row numbers are 1-based positions in the response."""
    return validate_rows(users, ApiUser, "api", first_row=1, id_field="id")


def load_crm(path: Path) -> list[dict]:
    """Read the CRM CSV into raw dicts (every value is a string)."""
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))