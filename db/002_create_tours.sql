-- creating the table for our tours

CREATE TABLE tours (
  id SERIAL PRIMARY KEY,
  tour_date DATE NOT NULL,
  departure_time TIME NOT NULL,
  boat_id INT NOT NULL REFERENCES boats(id),
  capacity INT NOT NULL DEFAULT 20,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  UNIQUE (tour_date, boat_id)
);
