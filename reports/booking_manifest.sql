/*
=========================================================
Booking Manifest Report
---------------------------------------------------------
Purpose:
Returns the list of passengers for a given booking,
including who paid for each passenger.

This is used for:
- Tour check-in list
- Operational control
- Customer service validation
- Future admin dashboard

Assumptions:
- Buyer is stored in passengers with is_buyer = TRUE
- payer_passenger_id references the paying passenger
=========================================================
*/

SELECT 
    p.id AS passenger_id,
    p.full_name AS passenger_name,
    p.cpf,
    p.whatsapp,
    p.is_buyer,
    payer.full_name AS who_paid
FROM passengers p
JOIN passengers payer
    ON p.payer_passenger_id = payer.id
WHERE p.booking_id = :booking_id
ORDER BY p.id;