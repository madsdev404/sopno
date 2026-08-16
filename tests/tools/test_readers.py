"""
tests/test_readers.py
━━━━━━━━━━━━━━━━━━━━━
Tests for the binary document readers (PDF / image OCR / Office) and their
routing from read_file. Optional extractors are mocked so tests run offline.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sopno.config.settings import settings
from sopno.tools.builtins import files, readers


class ReadersTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory(prefix="sopno-readers-test-")
        self.root = Path(self._td.name)
        self._saved = {
            "read": settings.file_allowed_read,
            "write": settings.file_allowed_write,
            "confirm": settings.file_confirm_writes,
            "enabled": settings.file_enabled,
            "ocr": settings.file_ocr_enabled,
            "max_pages": settings.readers_max_pages,
            "max_chars": settings.readers_max_chars,
        }
        settings.file_allowed_read = [str(self.root)]
        settings.file_allowed_write = [str(self.root)]
        settings.file_confirm_writes = False
        settings.file_enabled = True
        settings.file_ocr_enabled = True
        settings.readers_max_pages = 20
        settings.readers_max_chars = 20000
        files._PENDING_ACTION = None

    def tearDown(self) -> None:
        files._PENDING_ACTION = None
        for key, value in self._saved.items():
            setattr(settings, {
                "read": "file_allowed_read",
                "write": "file_allowed_write",
                "confirm": "file_confirm_writes",
                "enabled": "file_enabled",
                "ocr": "file_ocr_enabled",
                "max_pages": "readers_max_pages",
                "max_chars": "readers_max_chars",
            }[key], value)
        self._td.cleanup()

    def make(self, name: str, data: bytes = b"x") -> Path:
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p


# ── extract_text routing ─────────────────────────────────────────────────────

class TestExtractTextRouting(ReadersTestCase):
    def test_routes_pdf(self) -> None:
        p = self.make("doc.pdf")
        with mock.patch.object(readers, "_read_pdf", return_value=("t", "pdf-native")):
            text, method = readers.extract_text(p)
        self.assertEqual((text, method), ("t", "pdf-native"))

    def test_routes_image(self) -> None:
        p = self.make("pic.png")
        with mock.patch.object(readers, "_read_image", return_value=("t", "image-ocr")):
            text, method = readers.extract_text(p)
        self.assertEqual((text, method), ("t", "image-ocr"))

    def test_routes_office_docs(self) -> None:
        for suffix, reader in (
            (".docx", "_read_docx"),
            (".pptx", "_read_pptx"),
            (".xlsx", "_read_xlsx"),
            (".doc", "_read_legacy"),
        ):
            p = self.make(f"f{suffix}")
            with mock.patch.object(readers, reader, return_value=("t", "x")):
                text, method = readers.extract_text(p)
            self.assertEqual(method, "x", f"{suffix} should route to {reader}")

    def test_unknown_suffix_returns_empty(self) -> None:
        p = self.make("notes.txt")
        self.assertEqual(readers.extract_text(p), ("", ""))


# ── _read_pdf ────────────────────────────────────────────────────────────────

def _fake_pymupdf(page_texts: list[str]):
    """A fake pymupdf module; pages have get_text() and get_pixmap()."""

    class _Page:
        def __init__(self, text: str):
            self._text = text

        def get_text(self) -> str:
            return self._text

        def get_pixmap(self, dpi: int = 72):
            class _Pix:
                def tobytes(self, fmt: str = "") -> bytes:
                    return b"PNGDATA"
            return _Pix()

    class _Doc:
        def __init__(self, texts: list[str]):
            self._pages = [_Page(t) for t in texts]

        def __len__(self) -> int:
            return len(self._pages)

        def __iter__(self):
            return iter(self._pages)

        def close(self) -> None:
            pass

    class _Mod:
        def open(self, path):
            return _Doc(page_texts)

    return _Mod()


class TestReadPdf(ReadersTestCase):
    def test_native_text_extraction(self) -> None:
        p = self.make("ok.pdf")
        with mock.patch.dict(sys.modules, {"pymupdf": _fake_pymupdf(["Page one text", "Page two text"])}):
            text, method = readers._read_pdf(p, 20)
        self.assertEqual(method, "pdf-native")
        self.assertIn("Page one text", text)
        self.assertIn("Page two text", text)

    def test_scanned_pdf_uses_ocr_fallback(self) -> None:
        p = self.make("scan.pdf")
        with mock.patch.dict(sys.modules, {"pymupdf": _fake_pymupdf(["", ""])}):
            with mock.patch.object(readers, "_ocr_image_bytes", return_value="SCANNED WORDS"):
                text, method = readers._read_pdf(p, 20)
        self.assertEqual(method, "pdf-ocr")
        self.assertIn("SCANNED WORDS", text)

    def test_scanned_pdf_without_ocr(self) -> None:
        p = self.make("scan.pdf")
        settings.file_ocr_enabled = False
        with mock.patch.dict(sys.modules, {"pymupdf": _fake_pymupdf([""])}):
            text, method = readers._read_pdf(p, 20)
        self.assertEqual(method, "pdf-ocr-unavailable")
        self.assertIn("no readable text", text)

    def test_missing_pymupdf(self) -> None:
        p = self.make("doc.pdf")
        with mock.patch.dict(sys.modules, {"pymupdf": None}):
            with mock.patch("builtins.__import__", side_effect=ImportError):
                text, method = readers._read_pdf(p, 20)
        self.assertEqual(method, "pdf-unavailable")
        self.assertIn("pymupdf", text)

    def test_page_cap(self) -> None:
        p = self.make("long.pdf")
        pages = [f"page {i}" for i in range(50)]
        with mock.patch.dict(sys.modules, {"pymupdf": _fake_pymupdf(pages)}):
            text, method = readers._read_pdf(p, 3)
        self.assertIn("47 more pages", text)
        self.assertNotIn("page 3", text)


# ── images / office ──────────────────────────────────────────────────────────

class TestImageAndOffice(ReadersTestCase):
    def test_image_ocr_success(self) -> None:
        p = self.make("photo.jpg")
        with mock.patch.object(readers, "_ocr_image_bytes", return_value="HELLO IMAGE"):
            text, method = readers._read_image(p)
        self.assertEqual(method, "image-ocr")
        self.assertIn("HELLO IMAGE", text)

    def test_image_ocr_unavailable(self) -> None:
        p = self.make("photo.jpg")
        settings.file_ocr_enabled = False
        with mock.patch.object(readers, "_ocr_image_bytes", return_value=None):
            text, method = readers._read_image(p)
        self.assertEqual(method, "image-unavailable")

    def test_docx_missing_dependency(self) -> None:
        p = self.make("f.docx")
        with mock.patch.dict(sys.modules, {"docx": None}):
            text, method = readers._read_docx(p)
        self.assertEqual(method, "docx-unavailable")
        self.assertIn("python-docx", text)

    def test_pptx_missing_dependency(self) -> None:
        p = self.make("f.pptx")
        with mock.patch.dict(sys.modules, {"pptx": None}):
            text, method = readers._read_pptx(p)
        self.assertEqual(method, "pptx-unavailable")

    def test_xlsx_missing_dependency(self) -> None:
        p = self.make("f.xlsx")
        with mock.patch.dict(sys.modules, {"openpyxl": None}):
            text, method = readers._read_xlsx(p)
        self.assertEqual(method, "xlsx-unavailable")


# ── read_file routing ────────────────────────────────────────────────────────

class TestReadFileRouting(ReadersTestCase):
    def test_pdf_routed_through_readers(self) -> None:
        p = self.make("report.pdf")
        with mock.patch.object(
            readers, "extract_text", return_value=("Invoice No. 42", "pdf-native")
        ):
            out = files.read_file(str(p))
        self.assertEqual(out, "[pdf-native] Invoice No. 42")

    def test_text_files_not_routed(self) -> None:
        p = self.make("plain.txt", b"hello world")
        out = files.read_file(str(p))
        self.assertIn("hello world", out)
        self.assertNotIn("[", out)

    def test_ocr_message_for_images(self) -> None:
        p = self.make("scan.png")
        with mock.patch.object(
            readers, "extract_text", return_value=("MEMO TEXT", "image-ocr")
        ):
            out = files.read_file(str(p))
        self.assertEqual(out, "[image-ocr] MEMO TEXT")


# ── is_binary_like ───────────────────────────────────────────────────────────

class TestIsBinaryLike(ReadersTestCase):
    def test_document_suffix(self) -> None:
        self.assertTrue(readers.is_binary_like(self.make("a.pdf")))
        self.assertTrue(readers.is_binary_like(self.make("a.docx")))

    def test_null_byte_detection(self) -> None:
        p = self.make("weird.bin", b"\x00\x01\x02")
        self.assertTrue(readers.is_binary_like(p))

    def test_text_file(self) -> None:
        self.assertFalse(readers.is_binary_like(self.make("a.txt", b"hello")))


if __name__ == "__main__":
    unittest.main()
