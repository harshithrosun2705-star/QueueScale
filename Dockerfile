FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
RUN apt-get update \
    && apt-get install --no-install-recommends -y tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home queuescale
WORKDIR /app
COPY requirements.txt .
RUN python -m pip install -r requirements.txt
COPY queuescale/ queuescale/
COPY tests/ tests/
COPY samples/ samples/
USER 10001
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "queuescale.api:app", "--host", "0.0.0.0", "--port", "8000"]
