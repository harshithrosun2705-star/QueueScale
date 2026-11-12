import subprocess
import tempfile
from pathlib import Path

from queuescale.config import OCR_TIMEOUT_SECONDS


def image_extension(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    raise ValueError("Upload a PNG or JPEG scan.")


def extract_text(data):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / ("document" + image_extension(data))
        path.write_bytes(data)
        result = subprocess.run(
            ["tesseract", str(path), "stdout", "-l", "eng"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=OCR_TIMEOUT_SECONDS,
        )
    return result.stdout.strip()
