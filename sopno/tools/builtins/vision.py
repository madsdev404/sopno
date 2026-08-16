"""
sopno/tools/builtins/vision.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Vision tools.

``describe_screenshot`` feeds an image to a local Ollama vision model
(opt-in: ``vision_enabled`` + a ``vision_model`` like ``qwen2.5vl:7b``) and
returns its description. ``ocr_image`` extracts text with Tesseract via
pytesseract (falling back to the ``tesseract`` CLI) — both optional deps that
degrade with a friendly message when absent. Images must be inside the file
read roots.
"""

from __future__ import annotations

import base64
import subprocess
from pathlib import Path
from typing import Optional

import requests

from sopno.config.settings import settings
from sopno.tools.builtins import files

_OLLAMA_BASE = "http://localhost:11434"
_CHAT_URL = f"{_OLLAMA_BASE}/api/chat"


def _resolve(path: str) -> tuple[Optional[Path], str]:
    if not path.strip():
        return None, "Which image should I look at?"
    target, err = files._resolve_target(path)
    if err:
        return None, err
    assert target is not None
    if not target.is_file():
        return None, f"Image file not found: {target}"
    reason = files._authorize(target, "read")
    if reason:
        return None, reason
    return target, ""


def _image_data_uri(target: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(target.read_bytes()).decode()


def describe_screenshot(path: str) -> str:
    """
    Describe an image with the configured local vision model.

    Args:
        path: Absolute path of the image (must be inside the read roots).

    Returns:
        The model's description, or a reason it can't be used.
    """
    if not getattr(settings, "vision_enabled", False):
        return (
            "Vision is off. To use it, set vision_enabled = true and "
            "vision_model (e.g. 'qwen2.5vl:7b') in config.json."
        )
    model = (getattr(settings, "vision_model", "") or "").strip()
    if not model:
        return "No vision model is configured (vision_model is empty in config.json)."
    target, err = _resolve(path)
    if err:
        return err
    assert target is not None
    if target.stat().st_size > 8 * 1024 * 1024:
        return "That image is over 8 MB — please use a smaller one."
    try:
        resp = requests.post(
            _CHAT_URL,
            json={
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": "Describe this image briefly and clearly.",
                        "images": [_image_data_uri(target)],
                    }
                ],
                "stream": False,
                "options": {"num_predict": 300},
            },
            timeout=180,
        )
        resp.raise_for_status()
        text = (resp.json().get("message") or {}).get("content", "").strip()
        if not text:
            return f"{model} returned an empty description."
        return text
    except requests.RequestException as e:
        return f"Could not reach Ollama: {e}"


def ocr_image(path: str) -> str:
    """
    Extract text from an image with Tesseract.

    Args:
        path: Absolute path of the image (must be inside the read roots).

    Returns:
        The extracted text, or a reason it can't be read.
    """
    target, err = _resolve(path)
    if err:
        return err
    assert target is not None
    try:
        import pytesseract
        from PIL import Image
    except Exception:  # noqa: BLE001
        pytesseract = None  # type: ignore[assignment]
    if pytesseract is not None:
        try:
            text = pytesseract.image_to_string(Image.open(str(target)))
            text = text.strip()
            if text:
                return text
        except Exception:  # noqa: BLE001
            pass
    try:
        proc = subprocess.run(
            ["tesseract", str(target), "stdout"],
            capture_output=True, text=True, timeout=120,
        )
        text = (proc.stdout or "").strip()
        if proc.returncode == 0 and text:
            return text
    except FileNotFoundError:
        return "OCR needs Tesseract — install tesseract-ocr (and pip install pytesseract Pillow)."
    except Exception as e:  # noqa: BLE001
        return f"OCR failed: {e}"
    return "OCR found no readable text in that image."
