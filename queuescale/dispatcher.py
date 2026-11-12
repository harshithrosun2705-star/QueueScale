import logging
import signal
import time

import pika
import psycopg

from queuescale import broker, db

log = logging.getLogger(__name__)


def dispatch_one(channel):
    with db.connect() as conn:
        job = conn.execute(
            """
            SELECT id, attempts FROM jobs
            WHERE status = 'pending' AND available_at <= now()
            ORDER BY available_at, created_at
            LIMIT 1 FOR UPDATE SKIP LOCKED
            """
        ).fetchone()
        if job is None:
            return False
        broker.publish(channel, job["id"], job["attempts"] + 1)
        conn.execute("UPDATE jobs SET status = 'queued' WHERE id = %s", (job["id"],))
    return True


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("pika").setLevel(logging.WARNING)
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    db.init_database()
    while not stopping:
        try:
            with broker.connect() as connection:
                channel = broker.open_queue(connection)
                channel.confirm_delivery()
                while not stopping:
                    if not dispatch_one(channel):
                        connection.sleep(0.5)
        except (pika.exceptions.AMQPError, psycopg.Error) as exc:
            log.warning("Dispatcher will reconnect after %s", type(exc).__name__)
            time.sleep(2)


if __name__ == "__main__":
    main()
