import os
import psycopg


def get_db_connection() -> psycopg.Connection:
    """
    Creates a new connection to PostgreSQL.
    For now (lean MVP), we open/close per request.
    Later we can add pooling.
    """
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set. Export it in your shell (Option A).")

    return psycopg.connect(database_url)