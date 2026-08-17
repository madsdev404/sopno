"""
sopno/core/agents/sources.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Event sources for long-running agents (long-running-agents.md, rollout step 7):
a file-system watcher and an HTTP webhook receiver.

Both turn an *external* event into the same durable wake as a human reply —
``AgentEvents.wake`` checkpoints any state delta, queues the message on the
session's pending input, and enqueues a ``resume`` job the worker claims. The
sources never talk to the LLM; they only make the state resumable.

  - ``FileWatcher``: a poll-based ``os.scandir``-style snapshot watcher. For
    each entry in ``agents_file_watches`` (``{path, agent, message?, recursive?}``)
    it detects created / changed / deleted files and wakes the target agent with
    the list of changed paths. The snapshot is updated every tick, so the same
    change never fires twice.
  - ``WebhookServer``: a threaded HTTP server on ``agents_webhook_host`` /
    ``agents_webhook_port`` (port 0 = disabled). ``POST /webhook`` with JSON
    ``{agent, message?, state_delta?}`` wakes an agent; ``GET /health`` is a
    liveness probe. Bound to localhost by default — put it behind a trusted
    reverse proxy, never expose it raw to the internet.
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Optional

from sopno.config.settings import settings

from sopno.core.agents.events import AgentEvents
from sopno.core.agents.queue import AgentQueue
from sopno.core.agents.session import AgentSessionStore


def _resolve_agent_ref(store: AgentSessionStore, ref: Any) -> Optional[int]:
    """An agent id or name → session id (None if unknown)."""
    if ref is None:
        return None
    try:
        if isinstance(ref, int) or str(ref).isdigit():
            return int(ref)
        agent = store.get_by_name(str(ref))
        return agent["id"] if agent else None
    except Exception:  # noqa: BLE001
        return None


class FileWatcher(threading.Thread):
    """
    Poll-based file watcher: wakes an agent when configured paths change.
    ``watches`` entries are ``{path, agent, message?, recursive?}``.
    """

    def __init__(
        self,
        store: Optional[AgentSessionStore] = None,
        queue: Optional[AgentQueue] = None,
        *,
        watches: Optional[list[dict]] = None,
        poll_seconds: Optional[float] = None,
    ) -> None:
        super().__init__(name="agent-file-watcher", daemon=True)
        self._store = store or AgentSessionStore(settings.agents_path)
        self._events = AgentEvents(self._store, queue or AgentQueue(settings.agents_path))
        self._watches = [dict(w) for w in (watches or settings.agents_file_watches)]
        self._poll = max(
            0.5, float(poll_seconds if poll_seconds is not None
                       else settings.agents_file_poll_seconds)
        )
        # key: (path, recursive) → {relative_path: (mtime, size)}
        self._snapshots: dict[tuple[str, bool], dict[str, tuple[float, int]]] = {}
        self._run = threading.Event()

    # ── Snapshot machinery ───────────────────────────────────────────────────

    @staticmethod
    def _snapshot(root: Path, recursive: bool) -> dict[str, tuple[float, int]]:
        snap: dict[str, tuple[float, int]] = {}
        if not root.is_dir():
            return snap
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".git")]
            for name in filenames:
                path = Path(dirpath) / name
                try:
                    stat = path.stat()
                except OSError:
                    continue
                snap[str(path.relative_to(root))] = (stat.st_mtime, stat.st_size)
            if not recursive:
                break
        return snap

    def _diff(self, key: tuple[str, bool], snap: dict) -> list[str]:
        old = self._snapshots.get(key, {})
        changed = [rel for rel in snap if rel not in old or old[rel] != snap[rel]]
        changed += [rel for rel in old if rel not in snap]  # deletions
        self._snapshots[key] = snap
        return changed

    # ── Tick ─────────────────────────────────────────────────────────────────

    def _tick(self) -> None:
        for watch in self._watches:
            raw = str(watch.get("path") or "").strip()
            if not raw:
                continue
            root = Path(raw).expanduser()
            if not root.is_absolute():
                root = settings.project_root / root
            if not root.exists():
                continue
            recursive = bool(watch.get("recursive"))
            key = (str(root), recursive)
            # The first scan is the baseline: it seeds the snapshot without
            # waking, so pre-existing files never count as "new".
            first = key not in self._snapshots
            changed = self._diff(key, self._snapshot(root, recursive))
            if not first and changed:
                self._wake(watch, changed)

    def _wake(self, watch: dict, changed: list[str]) -> None:
        agent_id = _resolve_agent_ref(self._store, watch.get("agent"))
        if agent_id is None:
            return
        message = str(watch.get("message") or "").strip() or "file changed: {path}"
        try:
            message = message.format(path=", ".join(changed[:5]))
        except Exception:  # noqa: BLE001
            pass
        try:
            self._events.wake(agent_id, message, source="file")
        except ValueError:
            pass  # agent deleted mid-poll

    def run(self) -> None:
        while not self._run.is_set():
            try:
                self._tick()
            except Exception:  # noqa: BLE001 — never kill the watcher
                pass
            self._run.wait(self._poll)

    def stop(self) -> None:
        self._run.set()


class _WebhookHandler(BaseHTTPRequestHandler):
    """Serves POST /webhook (wake an agent) and GET /health (liveness)."""

    _events: AgentEvents = None  # type: ignore[assignment]
    _store: AgentSessionStore = None  # type: ignore[assignment]

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(200, {"ok": True})
        else:
            self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/webhook":
            self._json(404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length).decode("utf-8") if length else "{}"
            data = json.loads(raw or "{}")
            if not isinstance(data, dict):
                raise ValueError("body must be a JSON object")
        except Exception as e:  # noqa: BLE001
            self._json(400, {"ok": False, "error": f"bad JSON: {e}"})
            return
        agent_id = _resolve_agent_ref(self._store, data.get("agent"))
        if agent_id is None:
            self._json(404, {"ok": False,
                             "error": f"unknown agent {data.get('agent')!r}"})
            return
        message = (data.get("message") or "").strip() or "webhook"
        state_delta = data.get("state_delta")
        try:
            self._events.wake(agent_id, message,
                              state_delta=state_delta, source="webhook")
        except Exception as e:  # noqa: BLE001
            self._json(400, {"ok": False, "error": str(e)})
            return
        self._json(200, {"ok": True})

    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A002
        pass  # quiet by default


class WebhookServer:
    """
    Threaded HTTP server: ``POST /webhook`` wakes an agent with a message and
    an optional state delta. Bound to localhost unless configured otherwise;
    port 0 disables it (the runtime simply doesn't start it).
    """

    def __init__(
        self,
        store: Optional[AgentSessionStore] = None,
        queue: Optional[AgentQueue] = None,
        *,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ) -> None:
        self._store = store or AgentSessionStore(settings.agents_path)
        self._events = AgentEvents(self._store, queue or AgentQueue(settings.agents_path))
        self._host = host or settings.agents_webhook_host
        self._port = int(port if port is not None else settings.agents_webhook_port)
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._httpd is not None:
            return
        handler = type("WebhookHandler", (_WebhookHandler,), {
            "_events": self._events, "_store": self._store,
        })
        self._httpd = ThreadingHTTPServer((self._host, self._port), handler)
        self._port = int(self._httpd.server_address[1])
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name="agent-webhook", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        if self._httpd is not None:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:  # noqa: BLE001
                pass
            self._httpd = None
            self._thread = None

    @property
    def port(self) -> int:
        return self._port


# ── Singleton access (shared by the runtime / tests) ─────────────────────────

_WATCHER: Optional[FileWatcher] = None
_WEBHOOK: Optional[WebhookServer] = None


def get_watcher() -> Optional[FileWatcher]:
    """The currently-started file watcher, if any."""
    return _WATCHER


def set_watcher(watcher: Optional[FileWatcher]) -> Optional[FileWatcher]:
    global _WATCHER
    _WATCHER = watcher
    return _WATCHER


def get_webhook() -> Optional[WebhookServer]:
    """The currently-started webhook server, if any."""
    return _WEBHOOK


def set_webhook(webhook: Optional[WebhookServer]) -> Optional[WebhookServer]:
    global _WEBHOOK
    _WEBHOOK = webhook
    return _WEBHOOK
