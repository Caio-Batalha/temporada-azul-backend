from app.db import get_db_connection
from app.services.booking_service import create_hold_booking, NotEnoughSeatsError


def main():
    conn = get_db_connection()

    try:
        result = create_hold_booking(
            conn,
            tour_id=1,
            ticket_count=4,
            offer_code="group_deal",
        )
        print("OK:", result)

    except NotEnoughSeatsError as e:
        print("NOT ENOUGH SEATS")
        print("seats_left:", e.seats_left)
        print("alternative_dates:", e.alternative_dates)

    finally:
        conn.close()


if __name__ == "__main__":
    main()