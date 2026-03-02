--first time cretaing the tables to construct the database

CREATE TABLE boats (
    id SERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE CHECK (code IN ('PROMAR', 'PROVEDOR')),
    name TEXT NOT NULL
);

INSERT INTO boats (code, name) VALUES
('PROMAR', 'Promar'),
('PROVEDOR', 'Provedor');



