from fastapi import FastAPI, Query, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from decimal import Decimal, ROUND_DOWN, InvalidOperation
from datetime import date, datetime, UTC
from typing import Optional
import sqlite3
import uuid
import os
import hashlib
import json
import logging

app = FastAPI(title="Expense Tracker API")

# Allow all origins for simplicity (fine for demo; would restrict in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database location (overridable for tests/deployment)
DB = os.environ.get("DB_PATH", "expenses.db")

# Upper bound to avoid unrealistic or accidental large entries
MAX_AMOUNT = Decimal("1000000.00")

# Basic logging setup (kept simple for this project)
logging.basicConfig(level=logging.INFO)


# -------------------------------------------------------------------
# DATABASE LAYER
# -------------------------------------------------------------------

def get_db():
    """
    Open a new SQLite connection.

    Using WAL mode improves read/write concurrency slightly.
    Each request gets its own connection for simplicity.
    """
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("DROP TABLE IF EXISTS expenses")

        conn.execute("""
            CREATE TABLE expenses (
                id TEXT PRIMARY KEY,
                amount TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                date TEXT NOT NULL,
                created_at TEXT NOT NULL,
                idempotency_key TEXT UNIQUE,
                payload_hash TEXT
            )
        """)

        conn.execute("CREATE INDEX idx_category ON expenses(category)")
        conn.execute("CREATE INDEX idx_date ON expenses(date)")
        
        
# Ensure DB is ready when app starts
init_db()


# -------------------------------------------------------------------
# REQUEST SCHEMA
# -------------------------------------------------------------------

class ExpenseIn(BaseModel):
    amount: Decimal
    category: str
    description: str = ""
    date: date

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v):
        """
        - Normalize to 2 decimal places (truncate, not round)
        - Ensure value is positive and within limits
        """
        try:
            v = v.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        except InvalidOperation:
            raise ValueError("Invalid amount")

        if v <= 0:
            raise ValueError("Amount must be positive")

        if v > MAX_AMOUNT:
            raise ValueError("Amount too large")

        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v):
        """
        Strip whitespace and ensure it's not empty.
        """
        v = v.strip()
        if not v:
            raise ValueError("Category required")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v):
        """
        Keep descriptions short and clean.
        """
        return v.strip()[:500]

    @field_validator("date")
    @classmethod
    def validate_date(cls, v):
        """
        Allow reasonable backdating, but no future dates.
        """
        today = date.today()
        min_date = date(today.year - 10, today.month, today.day)

        if v < min_date:
            raise ValueError("Date too old")

        if v > today:
            raise ValueError("Future date not allowed")

        return v


# -------------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------------

def row_to_dict(row):
    """
    Convert DB row into API response format.
    Internal fields (like idempotency metadata) are excluded.
    """
    d = dict(row)
    d.pop("idempotency_key", None)
    d.pop("payload_hash", None)
    return d


def generate_payload_hash(body: ExpenseIn):
    """
    Generate a deterministic hash of the request payload.

    Used to ensure that an idempotency key is not reused with
    different data.
    """
    payload_str = json.dumps({
        "amount": str(body.amount),
        "category": body.category,
        "description": body.description,
        "date": body.date.isoformat(),
    }, sort_keys=True)

    return hashlib.sha256(payload_str.encode()).hexdigest()


# -------------------------------------------------------------------
# CREATE EXPENSE
# -------------------------------------------------------------------

@app.post("/expenses", status_code=201)
def create_expense(
    body: ExpenseIn,
    idempotency_key: Optional[str] = Header(None),
):
    """
    Create a new expense.

    If an idempotency key is provided:
    - Same key + same payload → return existing record
    - Same key + different payload → reject
    """
    payload_hash = generate_payload_hash(body)

    with get_db() as conn:
        try:
            # Explicit transaction for safety if logic grows later
            conn.execute("BEGIN")

            if idempotency_key:
                existing = conn.execute(
                    "SELECT * FROM expenses WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()

                if existing:
                    if existing["payload_hash"] != payload_hash:
                        raise HTTPException(
                            status_code=409,
                            detail="Idempotency key reused with different payload"
                        )
                    return row_to_dict(existing)

            expense_id = str(uuid.uuid4())
            created_at = datetime.now(UTC).isoformat()

            conn.execute(
                """
                INSERT INTO expenses
                (id, amount, category, description, date, created_at, idempotency_key, payload_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    expense_id,
                    str(body.amount),
                    body.category,
                    body.description,
                    body.date.isoformat(),
                    created_at,
                    idempotency_key,
                    payload_hash,
                ),
            )

            conn.commit()
            logging.info(f"Expense created: {expense_id}")

            return {
                "id": expense_id,
                "amount": str(body.amount),
                "category": body.category,
                "description": body.description,
                "date": body.date.isoformat(),
                "created_at": created_at,
            }

        except Exception as e:
            conn.rollback()
            logging.error(f"Failed to create expense: {str(e)}")
            raise


# -------------------------------------------------------------------
# LIST EXPENSES
# -------------------------------------------------------------------

@app.get("/expenses")
def list_expenses(
    category: Optional[str] = Query(None),
    sort: Optional[str] = Query(None),
):
    """
    Fetch expenses with optional filtering and sorting.

    Returns:
    - items: list of expenses
    - total: sum of visible expenses
    """
    query = "SELECT * FROM expenses WHERE 1=1"
    params = []

    if category:
        query += " AND category = ?"
        params.append(category)

    if sort == "date_desc":
        query += " ORDER BY date DESC, created_at DESC"
    else:
        query += " ORDER BY created_at DESC"

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        items = [row_to_dict(r) for r in rows]

        # Let DB compute total (avoids floating-point issues in Python)
        total_query = "SELECT SUM(amount) as total FROM expenses WHERE 1=1"
        total_params = []

        if category:
            total_query += " AND category = ?"
            total_params.append(category)

        total_row = conn.execute(total_query, total_params).fetchone()
        total = total_row["total"] if total_row["total"] else "0.00"

    return {
        "items": items,
        "total": total
    }


# -------------------------------------------------------------------
# CATEGORY LIST
# -------------------------------------------------------------------

@app.get("/expenses/categories")
def list_categories():
    """
    Return unique categories in sorted order.
    Used for filter dropdowns in UI.
    """
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT category FROM expenses ORDER BY category"
        ).fetchall()

    return [r["category"] for r in rows]


# -------------------------------------------------------------------
# HEALTH CHECK
# -------------------------------------------------------------------

@app.get("/health")
def health():
    """
    Simple health endpoint for monitoring or deployment checks.
    """
    return {"status": "ok"}


@app.get("/")
def root():
    """
    Basic root endpoint to confirm the API is running.

    Useful for:
    - quick manual checks (browser / curl)
    - deployment health verification
    """
    return {"message": "Expense Tracker API is running"}