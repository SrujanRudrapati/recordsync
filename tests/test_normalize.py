"""Tests for normalize.py."""
import pytest

from recordsync.normalize import split_phone


@pytest.mark.parametrize("raw", ["1-770-736-8031 x56442", "770.736.8031 x56442",
                                 "(770) 736-8031 ext. 56442"])
def test_split_phone_formats_agree(raw):
    assert split_phone(raw) == ("7707368031", "56442")


def test_split_phone_without_extension():
    assert split_phone("024 648 3804") == ("0246483804", None)


def test_split_phone_garbage_gives_no_digits():
    assert split_phone("call me") == ("", None)