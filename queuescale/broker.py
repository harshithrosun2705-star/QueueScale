import json
from uuid import UUID

import pika

from queuescale.config import AMQP_URL, MAX_ATTEMPTS, QUEUE_NAME


def connect():
    parameters = pika.URLParameters(AMQP_URL)
    parameters.heartbeat = 60
    parameters.socket_timeout = 5
    parameters.blocked_connection_timeout = 10
    return pika.BlockingConnection(parameters)


def open_queue(connection):
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE_NAME, durable=True)
    return channel


def publish(channel, job_id, attempt):
    channel.basic_publish(
        exchange="",
        routing_key=QUEUE_NAME,
        body=json.dumps({"id": str(job_id), "attempt": attempt}),
        properties=pika.BasicProperties(
            content_type="application/json", delivery_mode=2, message_id=str(job_id)
        ),
        mandatory=True,
    )


def parse_message(body):
    message = json.loads(body)
    if not isinstance(message, dict) or not isinstance(message.get("id"), str):
        raise ValueError("Missing job identifier")
    attempt = message.get("attempt")
    if type(attempt) is not int or not 1 <= attempt <= MAX_ATTEMPTS:
        raise ValueError("Invalid attempt number")
    return UUID(message["id"]), attempt
