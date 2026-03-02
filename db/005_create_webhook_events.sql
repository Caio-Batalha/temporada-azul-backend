-- Webhook events table
-- This acts as a safety log (black box) for Stripe events.
-- It ensures we never lose track of payments even if something fails.

CREATE TABLE webhook_events (
  id SERIAL PRIMARY KEY,

  stripe_event_id TEXT NOT NULL UNIQUE,
  event_type TEXT NOT NULL,

  payload JSONB NOT NULL,

  processing_status TEXT NOT NULL CHECK (
    processing_status IN ('received', 'processed', 'failed', 'unmatched')
  ) DEFAULT 'received',

  received_at TIMESTAMP NOT NULL DEFAULT NOW(),
  processed_at TIMESTAMP
);
