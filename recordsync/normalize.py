"""Pure normalization helpers. No I/O."""
import re
import unicodedata

_EXT = re.compile(r"\s*(?:x|ext\.?|extension)\s*(\d+)\s*$", re.IGNORECASE)

HONORIFICS = frozenset({"mr", "mrs", "ms", "miss", "mx", "dr", "prof"})
SUFFIXES = frozenset({"jr", "sr", "ii", "iii", "iv", "v"})
# Only the nicknames our cases use. Every entry is a merge risk in fuzzy matching,
# so each one needs its own test (see test_nickname_map_is_only_what_our_cases_use).
NICKNAMES = {"clem": "clementine", "pat": "patricia", "erv": "ervin"}
COMPANY_SUFFIXES = frozenset({"inc", "llc", "ltd", "co", "corp", "corporation", "group"})


def split_phone(raw: str) -> tuple[str, str | None]:
    """Split a phone into (digits, extension), dropping formatting and a leading US '1'."""
    match = _EXT.search(raw)
    ext = match.group(1) if match else None
    main = raw[: match.start()] if match else raw
    digits = re.sub(r"\D", "", main)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits, ext


def normalize_email(raw: str) -> str:
    """Trim and lowercase. No provider tricks (e.g. Gmail dots); they cause false merges."""
    return raw.strip().lower()


def _fold(text: str) -> str:
    """Casefold and strip accents: 'Tomás' -> 'tomas'."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def _tokens(text: str) -> list[str]:
    """Fold, drop apostrophes, spell out '&', and split on anything not a letter or digit."""
    folded = _fold(text).replace("'", "").replace("\u2019", "").replace("&", " and ")
    return re.findall(r"[a-z0-9]+", folded)


def _strip_ends(tokens: list[str], prefixes: frozenset, suffixes: frozenset, keep: int) -> list[str]:
    """Drop leading prefixes and trailing suffixes while more than `keep` tokens remain."""
    tokens = list(tokens)
    while len(tokens) > keep and tokens[0] in prefixes:
        tokens.pop(0)
    while len(tokens) > keep and tokens[-1] in suffixes:
        tokens.pop()
    return tokens


def _name_tokens(raw: str) -> list[str]:
    """Name tokens with honorifics and generational suffixes removed (never below two)."""
    return _strip_ends(_tokens(raw), HONORIFICS, SUFFIXES, keep=2)


def normalize_name(raw: str) -> str:
    """Matching key for a person: folded, honorifics/suffixes dropped, first-name nickname expanded."""
    tokens = _name_tokens(raw)
    if tokens:
        tokens[0] = NICKNAMES.get(tokens[0], tokens[0])
    return " ".join(tokens)


def is_nickname(raw: str) -> bool:
    """True if the first name is a known nickname, so a formal name should win in survivorship."""
    tokens = _name_tokens(raw)
    return bool(tokens) and tokens[0] in NICKNAMES


def display_name(raw: str) -> str:
    """Human-facing name: collapse whitespace; title-case only if all upper or all lower."""
    name = " ".join(raw.split())
    return name.title() if name.isupper() or name.islower() else name


def normalize_company(raw: str) -> str:
    """Matching key for a company: folded, '&' -> 'and', punctuation and legal suffixes dropped."""
    return " ".join(_strip_ends(_tokens(raw), frozenset(), COMPANY_SUFFIXES, keep=1))