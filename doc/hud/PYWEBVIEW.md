# Sopno HUD — pywebview Implementation Guide

## Overview

Build a premium floating HUD overlay for Sopno using **pywebview** — a lightweight Python library that creates native windows with HTML/CSS/JS frontends. The HUD runs alongside the existing voice pipeline with zero changes to mic.py, listener.py, or assistant.

**Why pywebview:**
- ~25MB footprint (vs 150MB Electron)
- Native transparency + always-on-top + frameless
- CSS `backdrop-filter: blur()` for glassmorphism
- Direct Python↔JS bridge (no HTTP server)
- Works on Linux, macOS, Windows

---

## Installation

```bash
pip install pywebview
```

No other dependencies needed. No Node.js, no npm, no build step.

---

## Project Structure

```
sopno/
├── hud/                          ← NEW: HUD module
│   ├── __init__.py
│   ├── app.py                    ← pywebview window manager
│   ├── bridge.py                 ← Python↔JS communication
│   ├── static/                   ← Frontend files
│   │   ├── index.html
│   │   ├── styles.css
│   │   └── app.js
│   └── themes/
│       └── dark.css              ← Theme variables
├── voice/                        ← EXISTING: unchanged
├── core/                         ← EXISTING: unchanged
└── main.py                       ← EXISTING: add HUD launch
```

---

## Core Components

### 1. Window Manager (`hud/app.py`)

```python
"""
sopno/hud/app.py
━━━━━━━━━━━━━━━━
pywebview window manager — creates the floating HUD overlay.
"""

import webview
import threading
from pathlib import Path
from typing import Optional

from sopno.hud.bridge import HUDBridge


class HUDWindow:
    """Manages the pywebview HUD overlay window."""

    def __init__(self, bridge: HUDBridge):
        self.bridge = bridge
        self.window: Optional[webview.Window] = None
        self._thread: Optional[threading.Thread] = None
        self._static_dir = Path(__file__).parent / "static"

    def start(self) -> None:
        """Launch the HUD window in a background thread."""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        html_path = self._static_dir / "index.html"
        css_path = self._static_dir / "styles.css"
        js_path = self._static_dir / "app.js"

        self.window = webview.create_window(
            title="Sopno",
            url=str(html_path),
            width=400,
            height=560,
            x=50,
            y=100,
            frameless=True,
            transparent=True,
            on_top=True,
            resizable=True,
            js_api=self.bridge,
        )

        # Inject CSS and JS after page loads
        self.window.events.loaded += self._on_loaded

        webview.start(debug=False)

    def _on_loaded(self) -> None:
        """Inject custom CSS and JS after the page loads."""
        if self.window is None:
            return

        css_path = self._static_dir / "styles.css"
        js_path = self._static_dir / "app.js"

        css = css_path.read_text(encoding="utf-8")
        js = js_path.read_text(encoding="utf-8")

        self.window.evaluate_js(f"""
            const style = document.createElement('style');
            style.textContent = `{css}`;
            document.head.appendChild(style);
        """)

        self.window.evaluate_js(js)

    def stop(self) -> None:
        """Close the HUD window."""
        if self.window is not None:
            self.window.destroy()

    # ── Public API (called from assistant) ──

    def set_state(self, state: str) -> None:
        """Update HUD state: idle, listening, thinking, speaking, error."""
        if self.window:
            self.window.evaluate_js(f"window.setAppState('{state}')")

    def set_response(self, text: str) -> None:
        """Update the response text."""
        if self.window:
            # Escape for JS string
            safe = text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
            self.window.evaluate_js(f"window.setResponse('{safe}')")

    def set_thinking(self, text: str, duration: float = 0) -> None:
        """Update the thinking block."""
        if self.window:
            safe = text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
            self.window.evaluate_js(
                f"window.setThinking('{safe}', {duration:.1f})"
            )

    def set_tokens(self, used: int, max_tokens: int) -> None:
        """Update the token counter."""
        if self.window:
            self.window.evaluate_js(
                f"window.setTokens({used}, {max_tokens})"
            )

    def set_model(self, name: str) -> None:
        """Update the current model name."""
        if self.window:
            safe = name.replace("'", "\\'")
            self.window.evaluate_js(f"window.setModel('{safe}')")

    def set_status(self, message: str) -> None:
        """Update the status bar message."""
        if self.window:
            safe = message.replace("'", "\\'")
            self.window.evaluate_js(f"window.setStatus('{safe}')")
```

### 2. Python↔JS Bridge (`hud/bridge.py`)

```python
"""
sopno/hud/bridge.py
━━━━━━━━━━━━━━━━━━━
pywebview JavaScript API — methods callable from the frontend.
"""

from typing import Optional, Callable


class HUDBridge:
    """
    Python functions exposed to the HUD frontend.
    
    In JS: window.pywebview.api.methodName(args)
    """

    def __init__(self):
        self._on_model_change: Optional[Callable[[str], None]] = None
        self._on_settings_open: Optional[Callable[[], None]] = None
        self._on_orb_click: Optional[Callable[[], None]] = None
        self._on_mute_toggle: Optional[Callable[[], None]] = None

    # ── Callbacks (set by assistant) ──

    def set_callbacks(
        self,
        on_model_change: Optional[Callable[[str], None]] = None,
        on_settings_open: Optional[Callable[[], None]] = None,
        on_orb_click: Optional[Callable[[], None]] = None,
        on_mute_toggle: Optional[Callable[[], None]] = None,
    ) -> None:
        self._on_model_change = on_model_change
        self._on_settings_open = on_settings_open
        self._on_orb_click = on_orb_click
        self._on_mute_toggle = on_mute_toggle

    # ── Methods called from JS ──

    def change_model(self, model_id: str) -> str:
        """Called when user selects a different model."""
        if self._on_model_change:
            self._on_model_change(model_id)
        return "ok"

    def open_settings(self) -> str:
        """Called when user clicks settings button."""
        if self._on_settings_open:
            self._on_settings_open()
        return "ok"

    def orb_clicked(self) -> str:
        """Called when user clicks the status orb."""
        if self._on_orb_click:
            self._on_orb_click()
        return "ok"

    def toggle_mute(self) -> str:
        """Called when user toggles mute."""
        if self._on_mute_toggle:
            self._on_mute_toggle()
        return "ok"

    def get_config(self) -> dict:
        """Return current config to the frontend."""
        from sopno.config.settings import settings
        return {
            "model": settings.model_name,
            "listening_mode": settings.listening_mode,
            "wake_words": settings.wake_words,
            "barge_in_enabled": settings.barge_in_enabled,
        }

    def get_models(self) -> list:
        """Return available models."""
        return [
            {"id": "qwen3:4b", "name": "Qwen3 4B", "provider": "Ollama", "speed": "fast"},
            {"id": "qwen3:8b", "name": "Qwen3 8B", "provider": "Ollama", "speed": "medium"},
            {"id": "gemma3:4b", "name": "Gemma3 4B", "provider": "Ollama", "speed": "fast"},
        ]
```

### 3. Frontend (`hud/static/index.html`)

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sopno HUD</title>
</head>
<body>
    <div id="app">
        <!-- Drag region -->
        <div class="drag-region" id="titlebar">
            <span class="title">Sopno</span>
            <div class="controls">
                <button class="btn-icon" id="btn-settings">⚙</button>
            </div>
        </div>

        <!-- Status Orb -->
        <div class="orb-container">
            <div class="orb-glow" id="orb-glow"></div>
            <button class="orb" id="orb">
                <div class="orb-inner" id="orb-inner">
                    <span class="orb-icon" id="orb-icon">🎤</span>
                </div>
            </button>
        </div>

        <!-- Response Panel -->
        <div class="response-panel glass" id="response-panel" style="display: none;">
            <div class="thinking-block" id="thinking-block" style="display: none;">
                <button class="thinking-toggle" id="thinking-toggle">
                    <span class="thinking-chevron">▶</span>
                    <span>Thinking</span>
                    <span class="thinking-duration" id="thinking-duration"></span>
                </button>
                <div class="thinking-content" id="thinking-content"></div>
            </div>
            <div class="response-text" id="response-text"></div>
            <div class="streaming-cursor" id="cursor" style="display: none;">|</div>
        </div>

        <!-- Bottom Bar -->
        <div class="bottom-bar">
            <div class="token-ring" id="token-ring">
                <svg width="40" height="40">
                    <circle cx="20" cy="20" r="16" fill="none" 
                            stroke="rgba(255,255,255,0.1)" stroke-width="3"/>
                    <circle cx="20" cy="20" r="16" fill="none" 
                            stroke="#10b981" stroke-width="3" 
                            stroke-linecap="round"
                            stroke-dasharray="100.53" 
                            stroke-dashoffset="100.53"
                            id="token-arc"
                            transform="rotate(-90 20 20)"/>
                </svg>
                <div class="token-label">
                    <div class="token-pct" id="token-pct">0%</div>
                </div>
            </div>

            <button class="model-selector glass" id="model-btn">
                <span id="model-name">Qwen3:8b</span>
                <span class="chevron">▾</span>
            </button>
        </div>

        <!-- Status Bar -->
        <div class="status-bar">
            <span id="status-text">Ready</span>
        </div>

        <!-- Model Dropdown -->
        <div class="model-dropdown glass-elevated" id="model-dropdown" 
             style="display: none;">
        </div>
    </div>

    <script>
    // ── State ──
    let appState = 'idle';
    let thinkingExpanded = false;

    // ── pywebview bridge ──
    async function api(method, ...args) {
        if (window.pywebview) {
            return await window.pywebview.api[method](...args);
        }
        console.log(`[HUD] ${method}(${args})`);
        return null;
    }

    // ── State updates (called from Python) ──
    window.setAppState = function(state) {
        appState = state;
        const orb = document.getElementById('orb');
        const glow = document.getElementById('orb-glow');
        const icon = document.getElementById('orb-icon');

        orb.className = 'orb orb-' + state;
        glow.className = 'orb-glow glow-' + state;

        const icons = {
            idle: '🎤', listening: '🎧', thinking: '🧠',
            speaking: '🔊', error: '⚠️', calibrating: '⏳'
        };
        icon.textContent = icons[state] || '🎤';

        document.getElementById('status-text').textContent = 
            state.charAt(0).toUpperCase() + state.slice(1);
    };

    window.setResponse = function(text) {
        const panel = document.getElementById('response-panel');
        const textEl = document.getElementById('response-text');
        panel.style.display = 'block';
        textEl.innerHTML = text;  // Basic HTML rendering
    };

    window.setThinking = function(text, duration) {
        const block = document.getElementById('thinking-block');
        const content = document.getElementById('thinking-content');
        const dur = document.getElementById('thinking-duration');
        block.style.display = 'block';
        content.textContent = text;
        dur.textContent = duration > 0 ? `(${duration.toFixed(1)}s)` : '';
    };

    window.setTokens = function(used, max) {
        const pct = Math.min((used / max) * 100, 100);
        const arc = document.getElementById('token-arc');
        const circumference = 2 * Math.PI * 16;  // r=16
        const offset = circumference * (1 - pct / 100);
        arc.style.strokeDashoffset = offset;

        // Color based on usage
        if (pct < 65) arc.style.stroke = '#10b981';
        else if (pct < 85) arc.style.stroke = '#f59e0b';
        else arc.style.stroke = '#ef4444';

        document.getElementById('token-pct').textContent = Math.round(pct) + '%';
    };

    window.setModel = function(name) {
        document.getElementById('model-name').textContent = name;
    };

    window.setStatus = function(msg) {
        document.getElementById('status-text').textContent = msg;
    };

    // ── Event handlers ──
    document.getElementById('orb').addEventListener('click', () => {
        api('orb_clicked');
    });

    document.getElementById('btn-settings').addEventListener('click', () => {
        api('open_settings');
    });

    document.getElementById('model-btn').addEventListener('click', async () => {
        const dropdown = document.getElementById('model-dropdown');
        if (dropdown.style.display === 'none') {
            const models = await api('get_models');
            dropdown.innerHTML = models.map(m => `
                <div class="model-option" data-id="${m.id}">
                    <span>${m.name}</span>
                    <span class="model-speed">${m.speed}</span>
                </div>
            `).join('');
            dropdown.style.display = 'block';

            dropdown.querySelectorAll('.model-option').forEach(el => {
                el.addEventListener('click', () => {
                    api('change_model', el.dataset.id);
                    dropdown.style.display = 'none';
                });
            });
        } else {
            dropdown.style.display = 'none';
        }
    });

    document.getElementById('thinking-toggle').addEventListener('click', () => {
        thinkingExpanded = !thinkingExpanded;
        const content = document.getElementById('thinking-content');
        const chevron = document.querySelector('.thinking-chevron');
        content.style.display = thinkingExpanded ? 'block' : 'none';
        chevron.textContent = thinkingExpanded ? '▼' : '▶';
    });

    // Init
    window.setAppState('idle');
    </script>
</body>
</html>
```

### 4. Styles (`hud/static/styles.css`)

```css
/* ── Reset ── */
* { box-sizing: border-box; margin: 0; padding: 0; }

html, body {
    height: 100%;
    background: transparent;
    font-family: 'Inter', -apple-system, sans-serif;
    color: #e2e8f0;
    overflow: hidden;
    user-select: none;
}

/* ── Glassmorphism ── */
.glass {
    background: rgba(255, 255, 255, 0.06);
    backdrop-filter: blur(12px) saturate(180%);
    -webkit-backdrop-filter: blur(12px) saturate(180%);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 16px;
}

.glass-elevated {
    background: rgba(255, 255, 255, 0.08);
    backdrop-filter: blur(20px) saturate(200%);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 20px;
    box-shadow: 0 24px 80px rgba(0, 0, 0, 0.6);
}

/* ── App Container ── */
#app {
    height: 100%;
    display: flex;
    flex-direction: column;
    padding: 0;
}

/* ── Drag Region ── */
.drag-region {
    -webkit-app-region: drag;
    app-region: drag;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 16px;
    height: 36px;
}

.title {
    font-size: 12px;
    color: rgba(255, 255, 255, 0.4);
    font-weight: 500;
}

.controls {
    -webkit-app-region: no-drag;
    display: flex;
    gap: 8px;
}

.btn-icon {
    background: none;
    border: none;
    color: rgba(255, 255, 255, 0.4);
    cursor: pointer;
    font-size: 14px;
    padding: 4px;
    border-radius: 6px;
    transition: all 0.15s ease;
}
.btn-icon:hover {
    background: rgba(255, 255, 255, 0.08);
    color: rgba(255, 255, 255, 0.8);
}

/* ── Status Orb ── */
.orb-container {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
}

.orb {
    width: 72px;
    height: 72px;
    border-radius: 50%;
    border: none;
    cursor: pointer;
    position: relative;
    background: linear-gradient(135deg, #6366f1, #8b5cf6);
    transition: transform 0.2s ease;
}
.orb:hover { transform: scale(1.05); }
.orb:active { transform: scale(0.95); }

.orb-inner {
    width: 100%;
    height: 100%;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    background: radial-gradient(circle at 30% 30%, 
                rgba(255,255,255,0.2), transparent 60%);
}

.orb-icon { font-size: 24px; }

.orb-glow {
    position: absolute;
    width: 100px;
    height: 100px;
    border-radius: 50%;
    filter: blur(20px);
    opacity: 0.3;
    animation: glow-pulse 2s ease-in-out infinite;
}

/* Orb states */
.orb-idle { background: linear-gradient(135deg, #6366f1, #8b5cf6); }
.orb-listening { background: linear-gradient(135deg, #06b6d4, #3b82f6); }
.orb-thinking { background: linear-gradient(135deg, #8b5cf6, #ec4899); }
.orb-speaking { background: linear-gradient(135deg, #10b981, #059669); }
.orb-error { background: linear-gradient(135deg, #ef4444, #dc2626); }

.glow-idle { background: #6366f1; }
.glow-listening { background: #06b6d4; }
.glow-thinking { background: #8b5cf6; }
.glow-speaking { background: #10b981; }
.glow-error { background: #ef4444; }

@keyframes glow-pulse {
    0%, 100% { opacity: 0.3; transform: scale(1); }
    50% { opacity: 0.5; transform: scale(1.1); }
}

/* ── Response Panel ── */
.response-panel {
    margin: 0 12px 12px;
    padding: 16px;
    max-height: 250px;
    overflow-y: auto;
}

.thinking-block { margin-bottom: 12px; }

.thinking-toggle {
    background: none;
    border: none;
    color: rgba(255, 255, 255, 0.5);
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    padding: 4px 0;
}
.thinking-toggle:hover { color: rgba(255, 255, 255, 0.8); }

.thinking-chevron { font-size: 10px; }

.thinking-duration {
    color: rgba(255, 255, 255, 0.3);
    font-size: 12px;
}

.thinking-content {
    display: none;
    margin-top: 8px;
    padding: 12px;
    border-left: 2px solid rgba(139, 92, 246, 0.3);
    color: rgba(255, 255, 255, 0.4);
    font-size: 13px;
    line-height: 1.5;
}

.response-text {
    font-size: 14px;
    line-height: 1.6;
    color: rgba(255, 255, 255, 0.9);
}

.streaming-cursor {
    display: inline;
    color: #818cf8;
    animation: blink 0.8s step-end infinite;
}

@keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0; }
}

/* ── Bottom Bar ── */
.bottom-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 16px;
}

.token-ring {
    display: flex;
    align-items: center;
    gap: 8px;
}

.token-label {
    font-size: 11px;
    color: rgba(255, 255, 255, 0.5);
}

.token-pct {
    font-weight: 600;
    color: rgba(255, 255, 255, 0.8);
}

.model-selector {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 10px;
    color: rgba(255, 255, 255, 0.8);
    cursor: pointer;
    font-size: 13px;
    transition: all 0.15s ease;
}
.model-selector:hover {
    background: rgba(255, 255, 255, 0.10);
    border-color: rgba(255, 255, 255, 0.15);
}

.chevron {
    font-size: 10px;
    color: rgba(255, 255, 255, 0.4);
}

/* ── Status Bar ── */
.status-bar {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 8px;
    border-top: 1px solid rgba(255, 255, 255, 0.05);
}

.status-bar span {
    font-size: 11px;
    color: rgba(255, 255, 255, 0.35);
}

/* ── Model Dropdown ── */
.model-dropdown {
    position: absolute;
    bottom: 80px;
    right: 16px;
    width: 220px;
    padding: 8px;
    z-index: 100;
}

.model-option {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 12px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 13px;
    color: rgba(255, 255, 255, 0.8);
    transition: background 0.1s ease;
}
.model-option:hover {
    background: rgba(255, 255, 255, 0.08);
}

.model-speed {
    font-size: 11px;
    color: rgba(255, 255, 255, 0.4);
}
```

---

## Integration with Assistant

### Adding HUD to `main.py`

```python
# In main.py — add HUD launch after assistant init

from sopno.hud.app import HUDWindow
from sopno.hud.bridge import HUDBridge

def main():
    assistant = SopnoAssistant(...)

    # Create HUD
    bridge = HUDBridge()
    hud = HUDWindow(bridge)

    # Wire callbacks
    bridge.set_callbacks(
        on_model_change=lambda m: assistant.set_model(m),
        on_orb_click=lambda: assistant.toggle_listening(),
    )

    # Start HUD
    hud.start()

    # Wire assistant to HUD
    assistant.hud = hud

    # Run assistant
    assistant.run()
```

### Updating Assistant to Use HUD

Add these lines to `sopno/core/assistant/__init__.py`:

```python
# In __init__:
self.hud = None  # Set by main.py

# In _deliver_reply:
if self.hud:
    self.hud.set_response(text)
    self.hud.set_state("speaking")

# In _await_command:
if self.hud:
    self.hud.set_state("listening")

# In _process_command (thinking):
if self.hud:
    self.hud.set_state("thinking")

# After transcription:
if self.hud:
    self.hud.set_tokens(used_tokens, max_tokens)
```

---

## How It Works

```
┌─────────────────────────────────────────────────┐
│  Python Backend                                 │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │ Voice    │    │ LLM      │    │ HUD      │  │
│  │ Pipeline │    │ Client   │    │ Bridge   │  │
│  └────┬─────┘    └────┬─────┘    └────┬─────┘  │
│       │               │               │         │
│       └───────────────┴───────────────┘         │
│                       │                         │
│              evaluate_js() / api()              │
│                       │                         │
├───────────────────────┼─────────────────────────┤
│  pywebview Window     │                         │
│  ┌────────────────────┴────────────────────┐    │
│  │  HTML/CSS/JS Frontend                   │    │
│  │  ┌─────────┐ ┌──────────┐ ┌─────────┐  │    │
│  │  │ Orb     │ │ Response │ │ Token   │  │    │
│  │  │ (state) │ │ Panel    │ │ Ring    │  │    │
│  │  └─────────┘ └──────────┘ └─────────┘  │    │
│  └─────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

**Communication:**
- **Python → JS**: `window.evaluate_js("setAppState('thinking')")`
- **JS → Python**: `window.pywebview.api.orb_clicked()`

No HTTP server. No WebSocket. Direct in-process bridge.

---

## What the HUD Shows

| Element | What It Does |
|---------|-------------|
| **Status Orb** | Animated center piece — changes color/animation per state |
| **Response Panel** | Glassmorphic panel with streaming markdown response |
| **Thinking Block** | Collapsible reasoning display with duration timer |
| **Token Ring** | SVG circular progress — green/amber/red based on usage |
| **Model Selector** | Dropdown to switch between local models |
| **Status Bar** | Current state message (Ready/Listening/Thinking...) |
| **Drag Region** | Invisible area for moving the window |

---

## Cross-Platform Notes

| Feature | Linux | macOS | Windows |
|---------|:-----:|:-----:|:-------:|
| Transparent window | ✅ | ✅ | ❌ (frameless only) |
| Always-on-top | ✅ | ✅ | ✅ |
| Frameless | ✅ | ✅ | ✅ |
| CSS backdrop-filter | ✅ (WebKit) | ✅ (WebKit) | ✅ (WebView2) |
| Glassmorphism | ✅ | ✅ | ✅ (CSS only, no OS blur) |

**Windows workaround**: Use `frameless=True` with a dark solid background (`#0a0a14`) instead of `transparent=True`. The CSS `backdrop-filter: blur()` still works for inner glass panels.

---

## Next Steps

1. `pip install pywebview`
2. Create `sopno/hud/` directory with the files above
3. Wire HUD to assistant in `main.py`
4. Test: `python -m sopno`
5. Iterate on visual design based on what looks good
