import os

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://queuescale:queuescale@localhost:5432/queuescale"
)
AMQP_URL = os.getenv("AMQP_URL", "amqp://queuescale:queuescale@localhost:5672/")
QUEUE_NAME = "ocr-jobs"
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ATTEMPTS = 3
OCR_TIMEOUT_SECONDS = 30
