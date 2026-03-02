import psycopg
from typing import Any


class NotEnoughSeatsError(Exception):
    def __init__(self, *, seats_left: int, alternative_dates: list[str]):
        self.seats_left = seats_left
        self.alternative_dates = alternative_dates
        super().__init__("Not enough seats available.")


def create_hold_booking(
    conn: psycopg.Connection,
    *,
    tour_id: int,
    ticket_count: int,
    offer_code: str,
    buyer_full_name: str,
    buyer_cpf: str,
    buyer_whatsapp: str,
    passengers: list[dict[str, Any]],
):
    
        # Buyer required fields (CPF is mandatory)
    if not buyer_full_name.strip():
        raise ValueError("buyer_full_name is required")
    if not buyer_cpf.strip():
        raise ValueError("buyer_cpf is required")
    if not buyer_whatsapp.strip():
        raise ValueError("buyer_whatsapp is required")

    # Passengers list must match ticket_count
    if len(passengers) != ticket_count:
        raise ValueError("passengers length must equal ticket_count")

    # Every passenger must have a name
    for p in passengers:
        if not str(p.get("full_name", "")).strip():
            raise ValueError("each passenger must have full_name")

    # Buyer must appear exactly once in passengers (match by CPF, since buyer_cpf is mandatory)
    buyer_matches = [
        p for p in passengers
        if str(p.get("cpf") or "").strip() == buyer_cpf.strip()
    ]
    if len(buyer_matches) != 1:
        raise ValueError("buyer must appear exactly once in passengers with matching CPF")
    

    """
    Creates a HOLD booking if there are enough seats available.
    Returns booking_id and hold_expires_at.
    """

    # 0) Basic input validation
    if ticket_count <= 0:
        raise ValueError("ticket_count must be at least 1")

    if offer_code not in ("standard", "trio_deal", "group_deal"):
        raise ValueError("Invalid offer_code")

    # 1) Discount rules (bps = basis points)
    if offer_code == "standard":
        discount_bps = 0

    elif offer_code == "trio_deal":
        if ticket_count != 3:
            raise ValueError("trio_deal requires exactly 3 tickets")
        discount_bps = 500

    else:  # group_deal
        if ticket_count < 4:
            raise ValueError("group_deal requires at least 4 tickets")
        discount_bps = 1000

    # 2) Price calculation (integer math)
    unit_price_cents = 35000  # R$ 350,00
    gross = ticket_count * unit_price_cents
    discount_amount = (gross * discount_bps) // 10_000
    total_amount_cents = gross - discount_amount

    with conn.cursor() as cur:

        # 3.0) Lazy-expire holds (event-driven cleanup)
        # This does NOT affect seat availability (we already compute holds with hold_expires_at > NOW()).
        # It keeps the database status accurate for reporting/debugging.
        cur.execute(
            """
            UPDATE bookings
            SET status = 'expired'
            WHERE status = 'hold'
              AND hold_expires_at IS NOT NULL
              AND hold_expires_at <= NOW();
            """
        )

        # 3.1) Check if tour exists and is active
        cur.execute(
            """
            SELECT capacity, is_active
            FROM tours
            WHERE id = %s
            FOR UPDATE; -- lock the row to prevent OVERBOOKING
            """,
            (tour_id,),
        )
        row = cur.fetchone()

        if not row:
            raise ValueError("Tour not found.")

        capacity, is_active = row

        if not is_active:
            raise ValueError("Tour is not active.")

        # 3.2) Count seats already taken (paid + unexpired holds)
        cur.execute(
            """
            SELECT COALESCE(SUM(ticket_count), 0)
            FROM bookings
            WHERE tour_id = %s
              AND (
                    status = 'paid'
                 OR (status = 'hold' AND hold_expires_at > NOW())
              );
            """,
            (tour_id,),
        )
        seats_taken = cur.fetchone()[0]
        seats_left = capacity - seats_taken

        # 3.3) If not enough seats, suggest alternative dates
        if ticket_count > seats_left:

            cur.execute(
                """
                SELECT t.tour_date
                FROM tours t
                WHERE t.id <> %s
                  AND t.is_active = TRUE
                  AND (
                        t.capacity -
                        COALESCE((
                            SELECT SUM(b.ticket_count)
                            FROM bookings b
                            WHERE b.tour_id = t.id
                              AND (
                                    b.status = 'paid'
                                 OR (b.status = 'hold' AND b.hold_expires_at > NOW())
                              )
                        ), 0)
                      ) >= %s
                ORDER BY t.tour_date;
                """,
                (tour_id, ticket_count),
            )

            alternative_dates = [
                r[0].isoformat() for r in cur.fetchall()
            ]

            raise NotEnoughSeatsError(
                seats_left=seats_left,
                alternative_dates=alternative_dates,
            )

        # 3.4) Insert HOLD booking (DB calculates expiration time)
        cur.execute(
            """
            INSERT INTO bookings (
              tour_id,
              offer_code,
              ticket_count,
              unit_price_cents,
              discount_bps,
              total_amount_cents,
              status,
              hold_expires_at
            )
            VALUES (
              %s, %s, %s, %s, %s, %s,
              'hold',
              NOW() + INTERVAL '15 minutes'
            )
            RETURNING id, hold_expires_at;
            """,
            (
                tour_id,
                offer_code,
                ticket_count,
                unit_price_cents,
                discount_bps,
                total_amount_cents,
            ),
        )

        booking_id, hold_expires_at = cur.fetchone()

        # 3.5) Insert buyer as passenger (is_buyer = TRUE)
        cur.execute(
            """
            INSERT INTO passengers (
                booking_id,
                full_name,
                cpf,
                whatsapp,
                is_buyer
            )
            VALUES (%s, %s, %s, %s, TRUE)
            RETURNING id;
            """,
            (
                booking_id,
                buyer_full_name,
                buyer_cpf,
                buyer_whatsapp,
            ),
        )

        buyer_passenger_id = cur.fetchone()[0]

                # 3.6) Insert remaining passengers (exclude the buyer)
        for p in passengers:
            passenger_cpf = (p.get("cpf") or "").strip()

            # Skip buyer (already inserted above)
            if passenger_cpf == buyer_cpf.strip():
                continue

            cur.execute(
                """
                INSERT INTO passengers (
                    booking_id,
                    full_name,
                    cpf,
                    whatsapp,
                    is_buyer,
                    payer_passenger_id
                )
                VALUES (%s, %s, %s, %s, FALSE, %s);
                """,
                (
                    booking_id,
                    p.get("full_name"),
                    p.get("cpf"),
                    p.get("whatsapp"),
                    buyer_passenger_id,
                ),
            )

    # Commit transaction
    conn.commit()

    return {
        "booking_id": booking_id,
        "tour_id": tour_id,
        "ticket_count": ticket_count,
        "offer_code": offer_code,
        "discount_bps": discount_bps,
        "total_amount_cents": total_amount_cents,
        "hold_expires_at": hold_expires_at.isoformat(),
        "seats_left": seats_left,
    }

