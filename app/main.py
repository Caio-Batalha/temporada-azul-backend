from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

# Local modules:
# - get_db_connection(): opens a Postgres connection using DATABASE_URL
# - create_hold_booking(): contains our booking HOLD business logic (seat checks + insert)
from app.db import get_db_connection
from app.services.booking_service import create_hold_booking, NotEnoughSeatsError

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
    # The heavy logic is NOT here. It lives in booking_service.py (clean architecture):
    # - validate offer rules
    # - compute total price
    # - check capacity
    # - suggest alternative tours if needed
    # - insert into bookings with status='hold'

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


# Convenience runner:
# If you run: python app/main.py
# then uvicorn will start the server.
#
# In production, you'd normally run:
# uvicorn app.main:app --host 0.0.0.0 --port 8000
if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
