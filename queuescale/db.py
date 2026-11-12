import time
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from queuescale.config import DATABASE_URL


def connect():
    return psycopg.connect(DATABASE_URL, connect_timeout=3, row_factory=dict_row)


def init_database():
    schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    for attempt in range(15):
        try:
            with connect() as conn:
                conn.execute("SELECT pg_advisory_xact_lock(817353912)")
                conn.execute(schema)
            return
        except psycopg.OperationalError:
            if attempt == 14:
                raise
            time.sleep(2)
