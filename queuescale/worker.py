import logging
import os
import signal
import subprocess
import time

import pika
import psycopg

from queuescale import broker, db, ocr
from queuescale.config import MAX_ATTEMPTS, QUEUE_NAME

log = logging.getLogger(__name__)


def process(job_id, attempt):
    with db.connect() as conn:
        job = conn.execute(
            "SELECT status, attempts, document FROM jobs WHERE id = %s FOR UPDATE",
            (job_id,),
        ).fetchone()
        if (
            job is None
            or job["status"] not in ("pending", "queued")
            or job["attempts"] + 1 != attempt
        ):
            return "skipped"

        try:
            result = ocr.extract_text(job["document"])
        except (subprocess.SubprocessError, ValueError):
            if attempt == MAX_ATTEMPTS:
                conn.execute(
                    """
                    UPDATE jobs SET status = 'failed', attempts = %s, document = NULL,
                        error = 'OCR failed after three attempts'
                    WHERE id = %s
                    """,
                    (attempt, job_id),
                )
                return "failed"
            conn.execute(
                """
                UPDATE jobs SET status = 'pending', attempts = %s,
                    available_at = now() + (%s * interval '1 second')
                WHERE id = %s
                """,
                (attempt, 2 ** attempt, job_id),
            )
            return "retry_scheduled"

        conn.execute(
            """
            UPDATE jobs SET status = 'completed', attempts = %s,
                document = NULL, result = %s
            WHERE id = %s
            """,
            (attempt, result.replace("\x00", ""), job_id),
        )
        return "completed"


def handle(connection, channel, delivery, body, ack_delay):
    try:
        job_id, attempt = broker.parse_message(body)
    except ValueError:
        log.warning("Discarding invalid queue message")
        channel.basic_reject(delivery.delivery_tag, requeue=False)
        return

    outcome = process(job_id, attempt)
    log.info("job=%s attempt=%s outcome=%s redelivered=%s",
             job_id, attempt, outcome, delivery.redelivered)
    if outcome == "completed" and ack_delay > 0:
        connection.sleep(ack_delay)
    channel.basic_ack(delivery.delivery_tag)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("pika").setLevel(logging.WARNING)
    ack_delay = float(os.getenv("DEMO_ACK_DELAY_SECONDS", "0"))
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
                channel.basic_qos(prefetch_count=1)
                for delivery, _, body in channel.consume(QUEUE_NAME, inactivity_timeout=1):
                    if delivery is not None:
                        handle(connection, channel, delivery, body, ack_delay)
                    if stopping:
                        channel.cancel()
                        break
        except (pika.exceptions.AMQPError, psycopg.Error) as exc:
            log.warning("Worker will reconnect after %s", type(exc).__name__)
            time.sleep(2)


if __name__ == "__main__":
    main()
