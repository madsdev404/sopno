"""
tests/test_vision.py
━━━━━━━━━━━━━━━━━━━
Vision tools: the opt-in gate, missing-file / read-root handling, and the
Ollama chat call (stubbed) for describe_screenshot; OCR degrade paths.
"""

import tempfile
import unittest
from pathlib import Path

from sopno.config.settings import settings
from sopno.tools.builtins import vision as mod


class VisionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {
            "enabled": settings.vision_enabled,
            "model": getattr(settings, "vision_model", ""),
            "roots": list(getattr(settings, "file_allowed_read", [])),
        }
        settings.vision_enabled = False
        settings.vision_model = ""
        self.tmp = Path(tempfile.mkdtemp(prefix="sopno-vision-test-"))
        settings.file_allowed_read = [str(self.tmp)]
        self.img = self.tmp / "pic.png"
        self.img.write_bytes(b"\x89PNG fake image bytes")
        self._orig_post = mod.requests.post

    def tearDown(self) -> None:
        mod.requests.post = self._orig_post
        settings.vision_enabled = self._saved["enabled"]
        settings.vision_model = self._saved["model"]
        settings.file_allowed_read = self._saved["roots"]

    def test_disabled(self) -> None:
        out = mod.describe_screenshot(str(self.img))
        self.assertIn("vision_enabled", out)

    def test_no_model(self) -> None:
        settings.vision_enabled = True
        out = mod.describe_screenshot(str(self.img))
        self.assertIn("No vision model", out)

    def test_missing_file(self) -> None:
        settings.vision_enabled = True
        settings.vision_model = "qwen2.5vl:7b"
        out = mod.describe_screenshot(str(self.tmp / "nope.png"))
        self.assertIn("not found", out)

    def test_outside_read_roots(self) -> None:
        settings.vision_enabled = True
        settings.vision_model = "qwen2.5vl:7b"
        outside = Path(tempfile.mkdtemp()) / "x.png"
        outside.write_bytes(b"x")
        out = mod.describe_screenshot(str(outside))
        self.assertIn("outside the allowed read roots", out)

    def test_calls_ollama_with_image(self) -> None:
        settings.vision_enabled = True
        settings.vision_model = "qwen2.5vl:7b"
        captured = {}

        def fake_post(url, json=None, timeout=None):  # noqa: ANN001
            captured["url"] = url
            captured["json"] = json

            class R:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {"message": {"content": "A red ball on a table."}}

            return R()

        mod.requests.post = fake_post  # type: ignore[assignment]
        out = mod.describe_screenshot(str(self.img))
        self.assertEqual(out, "A red ball on a table.")
        self.assertIn("api/chat", captured["url"])
        msg = captured["json"]["messages"][0]
        self.assertEqual(msg["role"], "user")
        self.assertTrue(msg["images"][0].startswith("data:image/png;base64,"))

    def test_ollama_unreachable(self) -> None:
        settings.vision_enabled = True
        settings.vision_model = "qwen2.5vl:7b"

        def fake_post(url, json=None, timeout=None):  # noqa: ANN001
            import requests as rq

            raise rq.ConnectionError("refused")

        mod.requests.post = fake_post  # type: ignore[assignment]
        out = mod.describe_screenshot(str(self.img))
        self.assertIn("Could not reach Ollama", out)

    def test_ocr_missing_file(self) -> None:
        out = mod.ocr_image(str(self.tmp / "nope.png"))
        self.assertIn("not found", out)

    def test_ocr_no_tesseract(self) -> None:
        out = mod.ocr_image(str(self.img))
        self.assertIn("Tesseract", out)  # neither pytesseract nor CLI present


if __name__ == "__main__":
    unittest.main()
