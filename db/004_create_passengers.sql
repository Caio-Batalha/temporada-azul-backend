-- Passengers for a booking
-- The buyer is also a passenger (is_buyer = true).
-- CPF + WhatsApp are mandatory only for the buyer.
-- payer_passenger_id can point to the passenger who paid (usually the buyer).

CREATE TABLE passengers (
  id SERIAL PRIMARY KEY,

  booking_id INT NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,

  full_name TEXT NOT NULL,
  cpf TEXT,
  whatsapp TEXT,

  is_buyer BOOLEAN NOT NULL DEFAULT FALSE,
  payer_passenger_id INT REFERENCES passengers(id),

  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Enforce: only one buyer per booking
CREATE UNIQUE INDEX ux_one_buyer_per_booking
ON passengers (booking_id)
WHERE is_buyer = TRUE;

-- Enforce: buyer must have CPF and WhatsApp
ALTER TABLE passengers
ADD CONSTRAINT chk_buyer_requires_cpf_whatsapp
CHECK (
  is_buyer = FALSE
  OR (cpf IS NOT NULL AND whatsapp IS NOT NULL)
);
