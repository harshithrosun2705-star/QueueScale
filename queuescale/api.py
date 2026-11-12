from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import psycopg
from fastapi import FastAPI, HTTPException, UploadFile, status

from queuescale import db
from queuescale.config import MAX_FILE_BYTES
from queuescale.ocr import image_extension


@asynccontextmanager
async def lifespan(app):
    db.init_database()
    yield


app = FastAPI(title="QueueScale", version="1.0.0", lifespan=lifespan)


@app.get("/healthz")
def health():
    return {"status": "ok"}


@app.get("/readyz")
def readiness():
    try:
        with db.connect() as conn:
            conn.execute("SELECT 1 FROM jobs LIMIT 1")
    except psycopg.Error:
        raise HTTPException(503, "Database unavailable") from None
    return {"status": "ready"}


@app.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
def create_job(file: UploadFile):
    try:
        document = file.file.read(MAX_FILE_BYTES + 1)
    finally:
        file.file.close()

    if len(document) > MAX_FILE_BYTES:
        raise HTTPException(413, "Maximum upload size is 5 MiB.")
    try:
        image_extension(document)
    except ValueError as exc:
        raise HTTPException(415, str(exc)) from None

    job_id = uuid4()
    filename = (file.filename or "document")[:255].replace("\x00", "")
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO jobs (id, filename, document) VALUES (%s, %s, %s)",
            (job_id, filename, document),
        )
    return {"id": job_id, "status": "pending"}


@app.get("/jobs/{job_id}")
def get_job(job_id: UUID):
    with db.connect() as conn:
        job = conn.execute(
            """
            SELECT id, filename, status, attempts, result, error, created_at
            FROM jobs WHERE id = %s
            """,
            (job_id,),
        ).fetchone()
    if job is None:
        raise HTTPException(404, "Job not found")
    return job
