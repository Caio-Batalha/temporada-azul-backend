from dotenv import load_dotenv
load_dotenv()  # Load variables from .env into the environment (local dev)

import os

import stripe
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

# Local modules:
# - get_db_connection(): opens a Postgres connection using DATABASE_URL
# - create_hold_booking(): contains our booking HOLD business logic (seat checks + insert)
from app.db import get_db_connection
from app.services.booking_service import create_hold_booking, NotEnoughSeatsError

from fastapi import Request
from stripe import SignatureVerificationError

# --- Stripe configuration (read from environment) ---
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
if not STRIPE_SECRET_KEY:
    raise RuntimeError("STRIPE_SECRET_KEY is not set. Put it in .env")

stripe.api_key = STRIPE_SECRET_KEY

# Where Stripe redirects the customer after payment/cancel.
# You can change these later to your real frontend URLs.
SUCCESS_URL = os.getenv(
    "STRIPE_SUCCESS_URL",
    "http://localhost:3000/success?session_id={CHECKOUT_SESSION_ID}",
)
CANCEL_URL = os.getenv(
    "STRIPE_CANCEL_URL",
    "http://localhost:3000/cancel",
)

# Create the FastAPI application instance
app = FastAPI(title="Temporada Azul API")


# Pydantic model = validates the JSON body the client sends to POST /bookings/hold
# FastAPI will:
# 1) parse incoming JSON
# 2) validate types (int, str)
# 3) give us a strongly-typed "payload" object
class PassengerIn(BaseModel):
    full_name: str
    cpf: str | None = None
    whatsapp: str | None = None


class HoldRequest(BaseModel):
    tour_id: int
    ticket_count: int
    offer_code: str  # 'standard', 'trio_deal', 'group_deal'

    # Buyer (required)
    buyer_full_name: str
    buyer_cpf: str
    buyer_whatsapp: str

    # Passengers (must include everyone, INCLUDING the buyer)
    passengers: list[PassengerIn]


class CheckoutRequest(BaseModel):
    booking_id: int


@app.get("/health")
def health():
    # Simple health check endpoint:
    # - used to confirm the API server is running
    # - does NOT touch the database
    return {"status": "ok"}


@app.get("/boats")
def boats():
    # Read-only endpoint: fetch boats from Postgres and return them as JSON

    # 1) Connect to DB (connection closes automatically when leaving the "with" block)
    with get_db_connection() as conn:
        # 2) Create cursor to run SQL commands
        with conn.cursor() as cur:
            # 3) Run query
            cur.execute("SELECT id, code, name FROM boats ORDER BY id;")
            rows = cur.fetchall()

    # 4) Convert DB rows (tuples) into JSON-friendly dicts
    return [{"id": r[0], "code": r[1], "name": r[2]} for r in rows]


@app.post("/bookings/hold")
def hold_booking(payload: HoldRequest):
    # This endpoint creates a temporary HOLD on seats for a tour.
    #
    # Why HOLD exists:
    # - prevents overbooking while the client pays (Stripe checkout)
    # - expires automatically after 15 minutes (computed in DB)
    #
    # The heavy logic is NOT here. It lives in booking_service.py:
    # - validate offer rules
    # - compute total price
    # - check capacity
    # - suggest alternative tours if the chosen one can't fit the request
    # - insert into bookings with status='hold'
    # - insert buyer + passengers in one transaction

    with get_db_connection() as conn:
        try:
            # Call service layer (business logic)
            result = create_hold_booking(
                conn,
                tour_id=payload.tour_id,
                ticket_count=payload.ticket_count,
                offer_code=payload.offer_code,
                buyer_full_name=payload.buyer_full_name,
                buyer_cpf=payload.buyer_cpf,
                buyer_whatsapp=payload.buyer_whatsapp,
                passengers=[p.model_dump() for p in payload.passengers],
            )
            return result

        except NotEnoughSeatsError as e:
            # Business exception: not enough capacity on selected tour.
            # We respond with HTTP 409 (conflict) and helpful data for the frontend.
            raise HTTPException(
                status_code=409,
                detail={
                    "message": f"Only {e.seats_left} seats left for the selected tour.",
                    "seats_left": e.seats_left,
                    "alternative_dates": e.alternative_dates,
                },
            )

        except ValueError as e:
            # Input/validation errors (bad offer code, wrong ticket count, tour inactive, etc.)
            # We respond with HTTP 400 (bad request).
            raise HTTPException(status_code=400, detail=str(e))


@app.post("/payments/checkout-session")
def create_checkout_session(payload: CheckoutRequest):
    """
    Create a Stripe Checkout Session for an existing HOLD booking.

    Flow:
    1) Validate booking exists and is still in HOLD (and not expired)
    2) Create Stripe Checkout session charging the total amount
    3) Save stripe_session_id in bookings (used later by webhook)
    4) Return checkout_url so frontend can redirect the client
    """
    booking_id = payload.booking_id

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # 1) Fetch booking data
            cur.execute(
                """
                SELECT
                    id,
                    tour_id,
                    ticket_count,
                    total_amount_cents,
                    status,
                    hold_expires_at
                FROM bookings
                WHERE id = %s;
                """,
                (booking_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Booking not found")

            (
                _id,
                tour_id,
                ticket_count,
                total_amount_cents,
                status,
                hold_expires_at,
            ) = row

            # 2) If booking is HOLD but already expired, expire it now (real-time correctness)
            cur.execute(
                """
                UPDATE bookings
                SET status = 'expired'
                WHERE id = %s
                  AND status = 'hold'
                  AND hold_expires_at IS NOT NULL
                  AND hold_expires_at <= NOW();
                """,
                (booking_id,),
            )

            # Re-check status after possible expiration
            cur.execute("SELECT status FROM bookings WHERE id = %s;", (booking_id,))
            status = cur.fetchone()[0]

            if status != "hold":
                raise HTTPException(
                    status_code=409,
                    detail=f"Booking is not in HOLD status (current: {status}).",
                )

            # 3) Create Stripe Checkout Session
            # We charge the TOTAL as a single line item (discount already included in total_amount_cents).
            session = stripe.checkout.Session.create(
                mode="payment",
                line_items=[
                    {
                        "price_data": {
                            "currency": "brl",
                            "product_data": {
                                "name": f"Temporada Azul — Tour #{tour_id} ({ticket_count} tickets)",
                            },
                            "unit_amount": int(total_amount_cents),
                        },
                        "quantity": 1,
                    }
                ],
                success_url=SUCCESS_URL,
                cancel_url=CANCEL_URL,
                metadata={
                    "booking_id": str(booking_id),
                    "tour_id": str(tour_id),
                },
            )

            # 4) Save session id so the webhook can link Stripe -> booking later
            cur.execute(
                """
                UPDATE bookings
                SET stripe_session_id = %s
                WHERE id = %s;
                """,
                (session.id, booking_id),
            )

        conn.commit()

    return {"checkout_url": session.url, "session_id": session.id}



@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    """
    Stripe sends events here (webhooks).

    We must:
    1) Verify signature (security)
    2) Store the event (audit + idempotency)
    3) Process the event (e.g., mark booking as paid)
    """
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not webhook_secret:
        raise HTTPException(status_code=500, detail="STRIPE_WEBHOOK_SECRET not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")

    # 1) Verify the webhook signature (prevents fake calls)
    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=webhook_secret,
        )
    except SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    except ValueError:
        # Invalid JSON
        raise HTTPException(status_code=400, detail="Invalid payload")

    event_id = event["id"]
    event_type = event["type"]

    # 2) Store the raw event (idempotent insert)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO webhook_events (stripe_event_id, event_type, payload, processing_status)
                VALUES (%s, %s, %s::jsonb, 'received')
                ON CONFLICT (stripe_event_id) DO NOTHING;
                """,
                (event_id, event_type, payload.decode("utf-8")),
            )

        conn.commit()

    # 3) Process event types we care about
    if event_type == "checkout.session.completed":
        session = event["data"]["object"]

        booking_id = session.get("metadata", {}).get("booking_id")
        payment_intent = session.get("payment_intent")
        session_id = session.get("id")

        if not booking_id:
            # If metadata is missing, we can still try to find booking by stripe_session_id
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id FROM bookings
                        WHERE stripe_session_id = %s
                        LIMIT 1;
                        """,
                        (session_id,),
                    )
                    row = cur.fetchone()
                conn.commit()

            if row:
                booking_id = str(row[0])

        if booking_id:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        UPDATE bookings
                        SET
                            status = 'paid',
                            stripe_payment_intent_id = COALESCE(stripe_payment_intent_id, %s)
                        WHERE id = %s;
                        """,
                        (payment_intent, int(booking_id)),
                    )

                    cur.execute(
                        """
                        UPDATE webhook_events
                        SET processing_status = 'processed',
                            processed_at = NOW()
                        WHERE stripe_event_id = %s;
                        """,
                        (event_id,),
                    )

                conn.commit()

    return {"received": True}


# Convenience runner:
# If you run: python app/main.py
# then uvicorn will start the server.
#
# In production, you'd normally run:
# uvicorn app.main:app --host 0.0.0.0 --port 8000
if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)