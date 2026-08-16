"""
tests/test_desktop.py
━━━━━━━━━━━━━━━━━━━━
Desktop-control + hardware tools, tested without any X tools installed: the
command runner and binary checks are stubbed, so behaviour (gates, binary
detection, confirmations, safe-arg validation, screenshot permissions) is
fully covered. Hardware reads use real psutil where safe and fakes for the
parts that are missing here (NVIDIA GPU).
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

from sopno.config.settings import settings
from sopno.tools.builtins import desktop as mod
from sopno.tools.builtins import files


class DesktopToolsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {
            "enabled": settings.desktop_enabled,
            "require_x11": getattr(settings, "desktop_require_x11", True),
            "display": os.environ.get("DISPLAY"),
            "wayland": os.environ.get("WAYLAND_DISPLAY"),
            "roots": list(settings.file_allowed_write),
            "confirm": getattr(settings, "file_confirm_writes", True),
        }
        settings.desktop_enabled = True
        settings.desktop_require_x11 = True
        os.environ["DISPLAY"] = ":0"
        os.environ.pop("WAYLAND_DISPLAY", None)
        self.tmp = Path(tempfile.mkdtemp(prefix="sopno-desktop-test-"))
        settings.file_allowed_write = [str(self.tmp)]
        settings.file_confirm_writes = True
        self._orig_run = mod._run
        self._orig_have = mod._have
        self.calls: list[list] = []

    def _stub_run(self, ok: bool = True, out: str = "", err: str = "") -> None:
        def run(cmd: list, input_text=None):  # noqa: ANN001
            self.calls.append(cmd)
            return ok, out, err

        mod._run = run  # type: ignore[assignment]

    def _have_all(self, *binaries: str) -> None:
        def have(b: str) -> bool:
            return b in binaries

        mod._have = have  # type: ignore[assignment]

    def tearDown(self) -> None:
        mod._run = self._orig_run
        mod._have = self._orig_have
        settings.desktop_enabled = self._saved["enabled"]
        settings.desktop_require_x11 = self._saved["require_x11"]
        if self._saved["display"] is None:
            os.environ.pop("DISPLAY", None)
        else:
            os.environ["DISPLAY"] = self._saved["display"]
        if self._saved["wayland"] is None:
            os.environ.pop("WAYLAND_DISPLAY", None)
        else:
            os.environ["WAYLAND_DISPLAY"] = self._saved["wayland"]
        settings.file_allowed_write = self._saved["roots"]
        settings.file_confirm_writes = self._saved["confirm"]


# ── Gates ────────────────────────────────────────────────────────────────────

class DesktopGateTest(DesktopToolsTest):
    def test_disabled(self) -> None:
        settings.desktop_enabled = False
        self.assertIn("desktop_enabled", mod.clipboard_get())
        self.assertIn("desktop_enabled", mod.get_disk_stats())

    def test_x11_requires_display(self) -> None:
        os.environ.pop("DISPLAY", None)
        out = mod.clipboard_get()
        self.assertIn("No display server", out)

    def test_x11_refuses_wayland(self) -> None:
        os.environ["WAYLAND_DISPLAY"] = "wayland-0"
        out = mod.press_key("Return")
        self.assertIn("Wayland", out)
        self.assertIn("desktop_require_x11", out)

    def test_wayland_allowed_when_require_x11_false(self) -> None:
        settings.desktop_require_x11 = False
        os.environ["WAYLAND_DISPLAY"] = "wayland-0"
        self._have_all("xclip")
        self._stub_run(ok=True, out="hi")
        out = mod.clipboard_get()
        self.assertIn("hi", out)

    def test_hardware_reads_do_not_need_x11(self) -> None:
        os.environ.pop("DISPLAY", None)
        out = mod.get_gpu_stats()
        self.assertIn("NVIDIA", out)


# ── Clipboard ────────────────────────────────────────────────────────────────

class ClipboardTest(DesktopToolsTest):
    def test_get_missing_binary(self) -> None:
        self._have_all()
        self.assertIn("xclip or xsel", mod.clipboard_get())

    def test_get_via_xclip(self) -> None:
        self._have_all("xclip")
        self._stub_run(ok=True, out="hello world")
        out = mod.clipboard_get()
        self.assertEqual(out, "hello world")
        self.assertEqual(self.calls, [["xclip", "-selection", "clipboard", "-o"]])

    def test_get_empty_clipboard(self) -> None:
        self._have_all("xsel")
        self._stub_run(ok=True, out="")
        self.assertIn("empty", mod.clipboard_get())

    def test_get_failure(self) -> None:
        self._have_all("xclip")
        self._stub_run(ok=False, err="no selection")
        self.assertIn("empty or couldn't be read", mod.clipboard_get())

    def test_set_empty_text(self) -> None:
        self._have_all("xclip")
        self.assertIn("What should I copy", mod.clipboard_set("  "))

    def test_set_confirmed(self) -> None:
        self._have_all("xclip")
        self._stub_run(ok=True)
        out = mod.clipboard_set("notes")
        self.assertIn("permission to copy", out)
        pending = files.pending_action()
        self.assertIsNotNone(pending)
        result = files.resolve_pending(pending["id"], "yes")
        self.assertIn("Done", result)
        self.assertEqual(self.calls, [["xclip", "-selection", "clipboard"]])
        self.assertEqual(pending["description"], "copy text to the clipboard")


# ── Screenshot ───────────────────────────────────────────────────────────────

class ScreenshotTest(DesktopToolsTest):
    def test_missing_binary(self) -> None:
        self._have_all()
        target = self.tmp / "shot.png"
        self.assertIn("scrot or maim", mod.take_screenshot(str(target)))

    def test_new_file_writes_immediately(self) -> None:
        self._have_all("scrot")
        self._stub_run(ok=True)
        target = self.tmp / "shot.png"
        out = mod.take_screenshot(str(target))
        self.assertIn("saved", out)
        self.assertEqual(self.calls, [["scrot", str(target)]])

    def test_outside_write_roots(self) -> None:
        self._have_all("scrot")
        outside = Path(tempfile.mkdtemp()) / "shot.png"
        out = mod.take_screenshot(str(outside))
        self.assertIn("outside the allowed write roots", out)

    def test_region_uses_scrot_a(self) -> None:
        self._have_all("scrot")
        self._stub_run(ok=True)
        target = self.tmp / "shot.png"
        mod.take_screenshot(str(target), region="10,20,640,480")
        self.assertEqual(self.calls, [["scrot", "-a", "10,20,640,480", str(target)]])

    def test_region_uses_maim_g(self) -> None:
        self._have_all("maim")
        self._stub_run(ok=True)
        target = self.tmp / "shot.png"
        mod.take_screenshot(str(target), region="10,20,640,480")
        self.assertEqual(self.calls, [["maim", "-g", "640x480+10+20", str(target)]])

    def test_overwrite_confirmed(self) -> None:
        self._have_all("scrot")
        self._stub_run(ok=True)
        target = self.tmp / "shot.png"
        target.write_bytes(b"old")
        out = mod.take_screenshot(str(target))
        self.assertIn("permission to overwrite", out)
        pending = files.pending_action()
        self.assertIsNotNone(pending)
        result = files.resolve_pending(pending["id"], "yes")
        self.assertIn("saved", result)

    def test_failure_message(self) -> None:
        self._have_all("scrot")
        self._stub_run(ok=False, err="xauth fail")
        target = self.tmp / "shot.png"
        self.assertIn("xauth fail", mod.take_screenshot(str(target)))


# ── Windows ──────────────────────────────────────────────────────────────────

class WindowTest(DesktopToolsTest):
    def test_list_missing_binary(self) -> None:
        self._have_all()
        self.assertIn("wmctrl", mod.list_windows())

    def test_list_windows(self) -> None:
        self._have_all("wmctrl")
        self._stub_run(ok=True, out="0x1  Desktop\n0x2  Term\n")
        out = mod.list_windows()
        self.assertIn("Desktop", out)
        self.assertIn("Term", out)

    def test_list_empty(self) -> None:
        self._have_all("wmctrl")
        self._stub_run(ok=True, out="")
        self.assertIn("No windows", mod.list_windows())

    def test_focus_empty_title(self) -> None:
        self._have_all("wmctrl")
        self.assertIn("Which window", mod.focus_window(" "))

    def test_focus_success(self) -> None:
        self._have_all("wmctrl")
        self._stub_run(ok=True)
        out = mod.focus_window("Terminal")
        self.assertIn("Focused 'Terminal'", out)
        self.assertEqual(self.calls, [["wmctrl", "-a", "Terminal"]])

    def test_focus_not_found(self) -> None:
        self._have_all("wmctrl")
        self._stub_run(ok=False, err="Cannot find window")
        self.assertIn("Cannot find window", mod.focus_window("zzz"))


# ── Keyboard ─────────────────────────────────────────────────────────────────

class KeyboardTest(DesktopToolsTest):
    def test_send_missing_binary(self) -> None:
        self._have_all()
        self.assertIn("xdotool", mod.send_keys("hi"))

    def test_send_empty(self) -> None:
        self._have_all("xdotool")
        self.assertIn("What should I type", mod.send_keys(""))

    def test_send_confirmed(self) -> None:
        self._have_all("xdotool")
        self._stub_run(ok=True)
        out = mod.send_keys("hello")
        self.assertIn("permission to type", out)
        pending = files.pending_action()
        self.assertIsNotNone(pending)
        result = files.resolve_pending(pending["id"], "yes")
        self.assertIn("typed", result)
        self.assertEqual(self.calls, [["xdotool", "type", "--delay", "30", "hello"]])

    def test_press_empty(self) -> None:
        self._have_all("xdotool")
        self.assertIn("Which key", mod.press_key(" "))

    def test_press_unsafe_combo_rejected(self) -> None:
        self._have_all("xdotool")
        out = mod.press_key("Return;rm -rf /")
        self.assertIn("unsafe", out)
        self.assertEqual(self.calls, [])

    def test_press_confirmed(self) -> None:
        self._have_all("xdotool")
        self._stub_run(ok=True)
        out = mod.press_key("ctrl+alt+t")
        self.assertIn("permission to press", out)
        pending = files.pending_action()
        self.assertIsNotNone(pending)
        result = files.resolve_pending(pending["id"], "yes")
        self.assertIn("Pressed ctrl+alt+t", result)
        self.assertEqual(self.calls, [["xdotool", "key", "ctrl+alt+t"]])

    def test_press_denied_does_not_run(self) -> None:
        self._have_all("xdotool")
        self._stub_run(ok=True)
        mod.press_key("super+l")
        pending = files.pending_action()
        self.assertIsNotNone(pending)
        result = files.resolve_pending(pending["id"], "no")
        self.assertNotIn("Pressed", result)
        self.assertEqual(self.calls, [])


# ── Hardware reads ───────────────────────────────────────────────────────────

class HardwareTest(DesktopToolsTest):
    def test_disk_stats_speaks(self) -> None:
        out = mod.get_disk_stats()
        self.assertIn("Disk usage", out)

    def test_gpu_no_driver(self) -> None:
        saved = sys.modules.get("pynvml")
        sys.modules.pop("pynvml", None)
        try:
            out = mod.get_gpu_stats()
            self.assertIn("NVIDIA", out)
        finally:
            if saved is not None:
                sys.modules["pynvml"] = saved

    def test_gpu_with_driver(self) -> None:
        fake = ModuleType("pynvml")
        fake.nvmlInit = lambda: None  # noqa: E731
        fake.nvmlDeviceGetCount = lambda: 1  # noqa: E731
        fake.NVML_TEMPERATURE_GPU = 0
        handle = object()
        fake.nvmlDeviceGetHandleByIndex = lambda i: handle  # noqa: E731
        fake.nvmlDeviceGetName = lambda h: b"RTX 4090"  # noqa: E731
        fake.nvmlDeviceGetUtilizationRates = lambda h: type("U", (), {"gpu": 55})()  # noqa: E731
        fake.nvmlDeviceGetMemoryInfo = lambda h: type("M", (), {"used": 1 << 30, "total": 2 << 30})()  # noqa: E731
        fake.nvmlDeviceGetTemperature = lambda h, t: 62  # noqa: E731
        saved = sys.modules.get("pynvml")
        sys.modules["pynvml"] = fake
        try:
            out = mod.get_gpu_stats()
            self.assertIn("RTX 4090", out)
            self.assertIn("55%", out)
            self.assertIn("62°C", out)
        finally:
            if saved is not None:
                sys.modules["pynvml"] = saved
            else:
                sys.modules.pop("pynvml", None)

    def test_network_stats(self) -> None:
        out = mod.get_network_stats()
        self.assertIn("Network", out)


if __name__ == "__main__":
    unittest.main()
