import json
import unittest
from pathlib import Path
from uuid import uuid4

from queuescale.broker import parse_message
from queuescale.ocr import extract_text, image_extension


class CoreTests(unittest.TestCase):
    def test_queue_message_round_trip(self):
        job_id = uuid4()
        body = json.dumps({"id": str(job_id), "attempt": 2}).encode()
        self.assertEqual(parse_message(body), (job_id, 2))

    def test_reject_invalid_message(self):
        for body in (b"[]", b"{}", b'{"id":"bad","attempt":1}', b"\xff"):
            with self.subTest(body=body), self.assertRaises(ValueError):
                parse_message(body)

    def test_reject_unsupported_document(self):
        with self.assertRaises(ValueError):
            image_extension(b"%PDF-1.4")

    def test_ocr_sample(self):
        sample = Path(__file__).resolve().parents[1] / "samples" / "sample-form.png"
        self.assertIn("QUEUESCALE", extract_text(sample.read_bytes()).upper())


if __name__ == "__main__":
    unittest.main()
