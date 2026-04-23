"""
Integration tests for the Expense Tracker API.

These tests hit the actual FastAPI app using TestClient.
We treat this like a black-box API and verify behavior end-to-end.

Run:
    pytest -v
"""

import pytest
import os

# Use a separate database for tests so we don't touch real data
os.environ["DB_PATH"] = "test_expenses.db"

from fastapi.testclient import TestClient
from main import app


# -------------------------------------------------------------------
# TEST CLIENT
# -------------------------------------------------------------------
@pytest.fixture
def client():
    """
    Create a fresh TestClient for each test.

    Important:
    - Avoids shared state across tests
    - Prevents connection reuse issues (especially with SQLite)
    """
    return TestClient(app)


# -------------------------------------------------------------------
# DB CLEANUP
# -------------------------------------------------------------------
@pytest.fixture(autouse=True)
def clean_db():
    """
    Ensure every test starts with a clean DB state.

    Instead of deleting the SQLite file (which causes locking issues on Windows),
    we simply wipe the table before each test.

    This gives us isolation without fighting the OS.
    """
    from main import get_db

    with get_db() as conn:
        conn.execute("DELETE FROM expenses")

    yield


# -------------------------------------------------------------------
# BASIC CREATION TESTS
# -------------------------------------------------------------------

def test_create_expense_returns_201(client):
    """Happy path: valid expense should be created successfully."""

    res = client.post("/expenses", json={
        "amount": 150.50,
        "category": "Food",
        "description": "Lunch",
        "date": "2024-04-01"
    })

    assert res.status_code == 201

    data = res.json()
    assert data["amount"] == "150.50"
    assert "id" in data


def test_amount_quantized_to_two_decimal_places(client):
    """
    Ensure amount is truncated (not rounded).

    Example:
    100.999 -> 100.99
    """

    res = client.post("/expenses", json={
        "amount": 100.999,
        "category": "Food",
        "description": "",
        "date": "2024-04-01"
    })

    assert res.status_code == 201
    assert res.json()["amount"] == "100.99"


# -------------------------------------------------------------------
# VALIDATION TESTS
# -------------------------------------------------------------------

def test_negative_amount_rejected(client):
    """Negative amounts should not be allowed."""

    res = client.post("/expenses", json={
        "amount": -50,
        "category": "Food",
        "description": "",
        "date": "2024-04-01"
    })

    assert res.status_code == 422


def test_zero_amount_rejected(client):
    """Zero is not a valid expense."""

    res = client.post("/expenses", json={
        "amount": 0,
        "category": "Food",
        "description": "",
        "date": "2024-04-01"
    })

    assert res.status_code == 422


def test_amount_over_limit_rejected(client):
    """Prevent unrealistic large values."""

    res = client.post("/expenses", json={
        "amount": 9999999,
        "category": "Food",
        "description": "",
        "date": "2024-04-01"
    })

    assert res.status_code == 422


def test_empty_category_rejected(client):
    """Category should not be empty or whitespace."""

    res = client.post("/expenses", json={
        "amount": 50,
        "category": "   ",
        "description": "",
        "date": "2024-04-01"
    })

    assert res.status_code == 422


def test_future_date_rejected(client):
    """Expenses cannot be recorded for future dates."""

    res = client.post("/expenses", json={
        "amount": 50,
        "category": "Food",
        "description": "",
        "date": "2099-01-01"
    })

    assert res.status_code == 422


def test_very_old_date_rejected(client):
    """We restrict how far back users can enter expenses."""

    res = client.post("/expenses", json={
        "amount": 50,
        "category": "Food",
        "description": "",
        "date": "1990-01-01"
    })

    assert res.status_code == 422


# -------------------------------------------------------------------
# IDEMPOTENCY
# -------------------------------------------------------------------

def test_idempotency_prevents_duplicate(client):
    """
    Same request with same idempotency key should not create duplicates.
    """

    payload = {
        "amount": 100,
        "category": "Transport",
        "description": "Cab",
        "date": "2024-04-01"
    }

    headers = {"Idempotency-Key": "test-key-abc"}

    res1 = client.post("/expenses", json=payload, headers=headers)
    res2 = client.post("/expenses", json=payload, headers=headers)
    res3 = client.post("/expenses", json=payload, headers=headers)

    # All responses should point to same record
    assert res1.json()["id"] == res2.json()["id"] == res3.json()["id"]

    data = client.get("/expenses").json()
    assert len(data["items"]) == 1


def test_without_idempotency_key_allows_duplicates(client):
    """
    Without idempotency, repeated calls should create multiple entries.
    """

    payload = {
        "amount": 100,
        "category": "Food",
        "description": "Lunch",
        "date": "2024-04-01"
    }

    client.post("/expenses", json=payload)
    client.post("/expenses", json=payload)

    data = client.get("/expenses").json()
    assert len(data["items"]) == 2


# -------------------------------------------------------------------
# FILTER / SORT
# -------------------------------------------------------------------

def test_filter_by_category(client):
    """Filtering should return only matching category."""

    client.post("/expenses", json={
        "amount": 100,
        "category": "Food",
        "description": "a",
        "date": "2024-04-01"
    })

    client.post("/expenses", json={
        "amount": 200,
        "category": "Travel",
        "description": "b",
        "date": "2024-04-02"
    })

    res = client.get("/expenses?category=Food").json()

    assert len(res["items"]) == 1
    assert res["items"][0]["category"] == "Food"


def test_filter_unknown_category_returns_empty(client):
    """Unknown category should return empty result."""

    client.post("/expenses", json={
        "amount": 100,
        "category": "Food",
        "description": "a",
        "date": "2024-04-01"
    })

    res = client.get("/expenses?category=NonExistent").json()
    assert res["items"] == []


def test_sort_date_desc(client):
    """Newest expenses should come first when sorting."""

    client.post("/expenses", json={
        "amount": 100,
        "category": "Food",
        "description": "old",
        "date": "2024-01-01"
    })

    client.post("/expenses", json={
        "amount": 200,
        "category": "Food",
        "description": "new",
        "date": "2024-04-01"
    })

    items = client.get("/expenses?sort=date_desc").json()["items"]
    dates = [i["date"] for i in items]

    assert dates == sorted(dates, reverse=True)


# -------------------------------------------------------------------
# CATEGORIES + HEALTH
# -------------------------------------------------------------------

def test_categories_deduplicated_and_sorted(client):
    """Categories should be unique and sorted alphabetically."""

    client.post("/expenses", json={
        "amount": 100,
        "category": "Food",
        "description": "a",
        "date": "2024-04-01"
    })

    client.post("/expenses", json={
        "amount": 200,
        "category": "Travel",
        "description": "b",
        "date": "2024-04-02"
    })

    res = client.get("/expenses/categories").json()
    assert res == ["Food", "Travel"]


def test_health(client):
    """Basic health check endpoint."""

    assert client.get("/health").json()["status"] == "ok"