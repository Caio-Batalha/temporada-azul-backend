-- Create bookings (one purchase attempt for a specific tour)
-- We store offer_code for analytics, but pricing is enforced by ticket_count rules in the backend.

CREATE TABLE bookings (
  id SERIAL PRIMARY KEY,
  tour_id INT NOT NULL REFERENCES tours(id),

  -- marketing attribution (what promo card the user clicked)
  offer_code TEXT NOT NULL CHECK (offer_code IN ('standard','trio_deal','group_deal')),

  ticket_count INT NOT NULL CHECK (ticket_count > 0),

  buyer_name TEXT NOT NULL,
  buyer_cpf TEXT NOT NULL,
  buyer_whatsapp TEXT NOT NULL,

  unit_price_cents INT NOT NULL DEFAULT 35000,
  discount_bps INT NOT NULL DEFAULT 0,   -- 0, 500, 1000
  total_amount_cents INT NOT NULL,

  status TEXT NOT NULL CHECK (status IN ('hold','paid','expired','canceled')),
  hold_expires_at TIMESTAMP,

  stripe_session_id TEXT UNIQUE,
  stripe_payment_intent_id TEXT UNIQUE,

  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);


