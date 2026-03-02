-- We moved buyer identity into passengers (is_buyer = true),
-- so buyer_* fields in bookings must not be required.

ALTER TABLE bookings
  ALTER COLUMN buyer_name DROP NOT NULL,
  ALTER COLUMN buyer_cpf DROP NOT NULL,
  ALTER COLUMN buyer_whatsapp DROP NOT NULL;