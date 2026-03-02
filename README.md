# Temporada Azul Backend

Backend system for managing whale watching tour bookings in Vitória, Espírito Santo, Brazil.

---

## Business Context

Temporada Azul is a boat tour company that operates whale watching tours along the coast of Vitória, ES.

Due to the high frequency of tours and the absence of an internal sales team, the company relied on a third-party agency to sell tickets. The agency charged 50% commission per ticket sold, significantly reducing margins.

This project was created to eliminate that dependency by building an in-house booking and payment system that:

- Automates ticket sales
- Prevents overbooking
- Manages tour dates and seat capacity
- Stores buyer and passenger data
- Integrates with online payments

The company now runs paid traffic campaigns on Instagram and captures 100% of ticket revenue directly.

---

## Project Goals

- Build a transactional booking system
- Prevent race conditions and overbooking
- Model real-world payment responsibility (buyer vs passengers)
- Support discount rules (group deals, trio deals)
- Maintain data consistency with proper database constraints
- Create a production-ready API architecture

---

## Tech Stack

- Python 3.12
- FastAPI
- PostgreSQL
- psycopg (v3)
- Pydantic
- Uvicorn

---

## Architecture Overview

The project follows a layered structure:

app/
├── main.py # API routes
├── db.py # Database connection
└── services/
└── booking_service.py # Business logic

db/
├── SQL schema migrations

scripts/
└── test_hold.py # Local testing script


### Separation of Concerns

- **API Layer** → HTTP validation and request handling
- **Service Layer** → Business rules and booking logic
- **Database Layer** → Schema constraints and transactional guarantees

---

## Core Business Logic

### 1. Seat Hold System

When a user starts checkout:

- A booking is created with status = `hold`
- Seats are reserved for 15 minutes
- `hold_expires_at` defines expiration time

Only holds where:

status = 'hold' AND hold_expires_at > NOW()


count toward seat availability.

---

### 2. Overbooking Prevention

To prevent race conditions:

```sql
SELECT ... FOR UPDATE

is used when checking tour capacity.

This creates a row-level lock in PostgreSQL, ensuring that concurrent booking attempts cannot oversell seats.

3. Buyer vs Passengers Model

The system distinguishes between:

Buyer (payer)

Passengers

The buyer is stored as a passenger with:

is_buyer = true

Other passengers reference the buyer through payer_passenger_id

This models real-world responsibility for refunds and payments.

4. Discount Rules

Supported offers:

standard (single ticket with no discount)

trio_deal (exactly 3 tickets, 5% off)

group_deal (4+ tickets, 10% off)

Discounts are calculated in basis points to avoid floating point errors.

Database Design Principles

Check constraints enforce valid offer codes and statuses

Foreign keys maintain relational integrity

Transactions guarantee atomic booking creation

Row-level locking prevents overbooking

How to Run Locally:
git clone https://github.com/Caio-Batalha/temporada-azul-backend.git
cd temporada-azul-backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL='postgresql://postgres:yourpassword@localhost:5432/temporada_azul'
uvicorn app.main:app --reload

API Docs available at:
http://127.0.0.1:8000/docs


Future Improvements:

Stripe Checkout integration

Automatic hold expiration cleanup job

Admin dashboard

Reporting endpoints

Containerization (Docker)

Deployment to cloud infrastructure

Author

Caio Batalha
Production Engineer / Backend & Data Engineer

