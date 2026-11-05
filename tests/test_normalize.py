"""Tests for normalize.py."""
import pytest

from recordsync.normalize import (NICKNAMES, display_name, is_nickname, normalize_company,
                                  normalize_email, normalize_name, split_phone)


# --- phone ---
@pytest.mark.parametrize("raw", ["1-770-736-8031 x56442", "770.736.8031 x56442",
                                 "(770) 736-8031 ext. 56442"])
def test_split_phone_formats_agree(raw):
    assert split_phone(raw) == ("7707368031", "56442")


def test_split_phone_without_extension():
    assert split_phone("024 648 3804") == ("0246483804", None)


def test_split_phone_garbage_gives_no_digits():
    assert split_phone("call me") == ("", None)


# --- email ---
@pytest.mark.parametrize("raw, expected", [
    (" SINCERE@APRIL.BIZ ", "sincere@april.biz"),
    ("nathan@Yesenia.NET", "nathan@yesenia.net"),
])
def test_normalize_email(raw, expected):
    assert normalize_email(raw) == expected


# --- names: one test per nickname, and the map can't grow silently ---
@pytest.mark.parametrize("raw, expected", [
    ("Clem Bauch", "clementine bauch"),
    ("Pat Lebsack", "patricia lebsack"),
    ("Erv Howell", "ervin howell"),
])
def test_each_nickname_expands(raw, expected):
    assert normalize_name(raw) == expected


def test_nickname_map_is_only_what_our_cases_use():
    assert set(NICKNAMES) == {"clem", "pat", "erv"}


@pytest.mark.parametrize("raw, expected", [
    ("Mrs. Dennis Schulist", "dennis schulist"),
    ("Nicholas Runolfsdottir V", "nicholas runolfsdottir"),
    ("Dr. Jane Smith Jr.", "jane smith"),
    ("Ana V", "ana v"),                      # never strip below two tokens
    ("  GLENNA   REICHERT ", "glenna reichert"),
    ("Tomás Ruiz", "tomas ruiz"),
    ("Julianne O'Conner", "julianne oconner"),
    ("Ana Pat", "ana pat"),                  # nicknames only in first position
    ("Chelsea Dietz", "chelsea dietz"),      # unknown names pass through
])
def test_normalize_name(raw, expected):
    assert normalize_name(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("Clem Bauch", True),
    ("Mrs. Pat Lebsack", True),
    ("Clementine Bauch", False),
    ("Ana Pat", False),
])
def test_is_nickname(raw, expected):
    assert is_nickname(raw) is expected


@pytest.mark.parametrize("raw, expected", [
    ("GLENNA REICHERT", "Glenna Reichert"),
    ("erv howell", "Erv Howell"),
    ("  Leanne   Graham ", "Leanne Graham"),
    ("Rey McDermott", "Rey McDermott"),      # mixed case is left alone
])
def test_display_name(raw, expected):
    assert display_name(raw) == expected


# --- company ---
@pytest.mark.parametrize("a, b", [
    ("Deckow-Crist Inc.", "Deckow-Crist"),
    ("Yost & Sons", "Yost and Sons"),
    ("ROBEL-CORKERY", "Robel-Corkery"),
    ("Keebler LLC", "Keebler"),
])
def test_company_variants_normalize_equal(a, b):
    assert normalize_company(a) == normalize_company(b)


@pytest.mark.parametrize("raw, expected", [
    ("Johns Group", "johns"),
    ("Group", "group"),                      # never strip to nothing
])
def test_company_suffix_stripping(raw, expected):
    assert normalize_company(raw) == expected