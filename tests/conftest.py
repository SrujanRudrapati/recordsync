"""Shared fixtures."""
import pytest


def make_user(i: int) -> dict:
    """A minimal JSONPlaceholder-shaped user."""
    return {"id": i, "name": f"User {i}", "username": f"user{i}",
            "email": f"user{i}@site.example", "phone": f"602-555-01{i:02d}",
            "company": {"name": f"Company {i}"}}


@pytest.fixture
def api_users():
    return [make_user(i) for i in range(1, 11)]