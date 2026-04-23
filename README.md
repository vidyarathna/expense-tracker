# Expense Tracker

A minimal full-stack expense tracker built with focus on **correctness under real-world conditions**, not just basic CRUD.

The system is designed to handle:

* duplicate submissions (double-click)
* retries after network failures
* page refresh during request execution

The goal is predictable and safe behavior, not feature-heavy implementation.

---

## Live Demo

Frontend:
https://expense-tracker-nine-silk-30.vercel.app/

Backend API:
https://expense-tracker-production-edc1.up.railway.app/

API Docs:
https://expense-tracker-production-edc1.up.railway.app/docs

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

Runs at: http://localhost:8000
Docs: http://localhost:8000/docs

---

### Frontend

cd frontend
npx serve .

Or open `index.html` directly.

Update API URL before running:

const API = "http://localhost:8000";

---

## API

| Method | Endpoint             | Notes                        |
| ------ | -------------------- | ---------------------------- |
| POST   | /expenses            | Create expense (idempotent)  |
| GET    | /expenses            | Supports filtering + sorting |
| GET    | /expenses/categories | List categories              |
| GET    | /health              | Health check                 |
| GET    | /                    | Basic API check              |

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

Implementation:

* frontend generates a UUID per submission
* same key is reused on retry
* backend stores key with UNIQUE constraint
* payload hash ensures request consistency

---

## Deployment

Backend:

* deployed on Railway
* root directory: `backend/`
* persistent DB path: `/data/expenses.db`

Frontend:

* deployed on Vercel
* static HTML/JS app
* API URL updated to production backend

---

## Key design decisions

### SQLite

Used because:

* no setup required
* simple and fast for small-scale apps

Trade-off:

* not suitable for high concurrency or scaling

---

### Handling money

* validated using `Decimal`
* stored as string

Reason:

* avoids floating point precision issues
* SQLite doesn’t enforce decimal precision

---

### API design

`GET /expenses` returns:

* filtered items
* total for those items

This keeps frontend logic simple and consistent.

---

### Frontend approach

Used plain HTML + JavaScript:

* no build step
* easy to run and review
* minimal complexity

Focus was correctness, not UI complexity.

---

## Error handling

Frontend:

* validates input before API call
* disables submit during request
* handles timeouts and network errors
* retries safely using same idempotency key

Backend:

* strict validation using Pydantic
* rejects invalid or inconsistent requests
* ensures data integrity

---

## Trade-offs

* No authentication (single-user scope)
* No pagination
* No update/delete operations
* API URL is hardcoded
* SQLite limits scalability

---

## Tests

Basic integration tests cover:

* expense creation
* validation rules
* idempotency behavior
* filtering and sorting

Run:

cd backend
pytest -v

---

## How to verify correctness

Try these manually:

1. Click submit multiple times quickly → only one expense created
2. Retry request after failure → no duplicates
3. Refresh page during submission → still no duplicates

---

## What I would improve next

* move to Postgres with migrations
* add authentication and user isolation
* add pagination
* add update/delete endpoints
* improve frontend with a framework (React)
* expand test coverage

---

## Final note

This project is intentionally minimal.

Focus areas:

* correctness under unreliable conditions
* safe handling of money
* preventing duplicate writes
* keeping the system simple and maintainable
