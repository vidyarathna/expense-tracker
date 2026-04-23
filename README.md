# Expense Tracker

A minimal full-stack expense tracker built with focus on **correctness under real-world conditions**, not just basic CRUD.

The system is designed to handle situations like:

* duplicate submissions (double-click)
* retries after network failures
* page refresh during request execution

The goal is predictable and safe behavior rather than feature-heavy implementation.

---

## What it supports

* Add an expense (amount, category, description, date)
* View all expenses
* Filter by category
* Sort by date (newest first)
* See total for the currently visible list

---

## Running locally

### Backend

cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload

Runs at: [http://localhost:8000](http://localhost:8000)
Docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

### Frontend

cd frontend
npx serve .

Or open `index.html` directly.

Before deploying, update:

const API = "[http://localhost:8000](http://localhost:8000)";

---

## API

| Method | Endpoint             | Notes                        |
| ------ | -------------------- | ---------------------------- |
| POST   | /expenses            | Create expense (idempotent)  |
| GET    | /expenses            | Supports filtering + sorting |
| GET    | /expenses/categories | List categories              |
| GET    | /health              | Health check                 |

---

## Idempotency (core behavior)

POST requests support an `Idempotency-Key` header.

Behavior:

* same key + same payload → returns existing record
* same key + different payload → rejected (409)

Why this matters:

In real systems, requests are not guaranteed to run exactly once.
Clients may retry due to:

* network timeouts
* slow responses
* user refreshing the page

Without idempotency, this leads to duplicate data.

Implementation approach:

* frontend generates a UUID per submission
* the same key is reused on retry
* backend stores key with UNIQUE constraint
* payload hash ensures same request intent

To prevent misuse, the system rejects cases where the same idempotency key is reused with different payloads.

### Concurrency safety

Idempotency is enforced at the database level using a UNIQUE constraint.
This ensures correctness even under concurrent requests, since duplicate inserts fail atomically.

---

## Consistency guarantees

* Write operations are idempotent (no duplicate inserts)
* Data is consistent within a single instance
* Backend is the source of truth for computed totals

Not guaranteed:

* Strong consistency across multiple instances (SQLite limitation)

---

## Failure handling

The system is designed to behave safely under failures:

* Network timeout → user can retry safely (same idempotency key)
* Partial request execution → backend prevents duplicate inserts
* Slow responses → frontend shows loading state

---

## Deployment

### Backend (Railway)

* Deploy `backend/`
* Set `DB_PATH=/data/expenses.db` for persistence

### Frontend (Vercel)

* Deploy `frontend/`
* Update API URL before deploy

---

## Key design decisions

### 1. SQLite for persistence

SQLite was chosen because:

* no setup required
* works well for single-instance apps
* fast for small datasets

Limitations:

* not suitable for high concurrency at scale
* no native decimal type

In a real system, this would be replaced with Postgres.

---

### 2. Handling money safely

Amounts are:

* validated using `Decimal`
* stored as strings in the database

Reason:

* floating point numbers introduce rounding errors
* SQLite does not enforce numeric precision

---

### 3. API response design

`GET /expenses` returns both:

* list of items
* computed total

The backend is responsible for total calculation to ensure consistency with filtering logic.

---

### 4. Frontend simplicity

Used plain HTML + JavaScript:

* no build step
* easy to run
* minimal overhead

Focus was on correctness rather than UI complexity.

---

### 5. Error handling

Frontend:

* validates input before API call
* disables submit button during request
* shows clear error messages
* safely retries using same idempotency key

Backend:

* strict validation using Pydantic
* rejects invalid requests
* ensures data integrity

---

## Trade-offs

* No authentication (single-user scope)
* No pagination (acceptable for small datasets)
* No update/delete operations
* Hardcoded API URL (should use env config)
* SQLite limits scalability

---

## What I skipped intentionally

* User authentication / multi-user isolation
* Update and delete APIs
* Pagination / large dataset handling
* Multi-currency support
* Full test coverage

---

## Tests

Basic integration tests cover:

* expense creation
* validation rules
* idempotency behavior
* filtering and sorting

Run tests:

cd backend
pytest -v

---

## What I would improve next

* move to Postgres with migrations
* add authentication and user isolation
* add pagination and indexing
* add update/delete endpoints
* improve frontend state handling (React)
* expand test coverage

---

## Final note

This project is intentionally minimal.

The focus was:

* correctness under unreliable conditions
* safe handling of money
* preventing duplicate writes
* keeping the system simple and maintainable

Designed with production concerns in mind (correctness, retries, data safety), while keeping the scope intentionally small.
