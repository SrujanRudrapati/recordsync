"""Pure normalization helpers. No I/O."""
import re

_EXT = re.compile(r"\s*(?:x|ext\.?|extension)\s*(\d+)\s*$", re.IGNORECASE)


def split_phone(raw: str) -> tuple[str, str | None]:
    """Split a phone into (digits, extension), dropping formatting and a leading US '1'."""
    match = _EXT.search(raw)
    ext = match.group(1) if match else None
    main = raw[: match.start()] if match else raw
    digits = re.sub(r"\D", "", main)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits, ext