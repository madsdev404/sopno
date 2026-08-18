# Sopno Maturity Roadmap
## From Terminal Voice Assistant to Desktop AI Product

**Date**: August 19, 2026
**Goal**: Make Sopno as mature as Cursor, AntiGravity, or Antigravity — a real desktop AI product for Windows and Linux.

---

## Table of Contents
1. [Vision & Architecture](#1-vision--architecture)
2. [HUD & Visualization](#2-hud--visualization)
3. [Thinking & Self-Evaluation System](#3-thinking--self-evaluation-system)
4. [Model Selection System](#4-model-selection-system)
5. [Memory & Context Management](#5-memory--context-management)
6. [Token & Context Display](#6-token--context-display)
7. [Interrupt & Barge-In System](#7-interrupt--barge-in-system)
8. [Permission System](#8-permission-system)
9. [Packaging & Distribution](#9-packaging--distribution)
10. [Implementation Phases](#10-implementation-phases)

---

## 1. Vision & Architecture

### What Cursor & AntiGravity Do Right
| Feature | Cursor | AntiGravity | Sopno Current |
|---------|--------|-------------|---------------|
| **Interface** | Electron IDE + Agents Window | VS Code fork + CLI + Desktop | Terminal (curses) |
| **Voice** | No (text only) | Live transcription via Gemini | ✅ Full voice pipeline |
| **Thinking display** | Collapsible reasoning | Multi-step artifacts | ❌ None |
| **Token display** | Context ring + breakdown | agy-hud status bar | ❌ None |
| **Model selection** | Cmd+/ dropdown, Auto mode | Multi-model routing | Config file only |
| **Self-evaluation** | No | No | ❌ None |
| **Interrupt** | Stop button | Stop button | ✅ Barge-in (basic) |
| **Permissions** | Tool approval prompts | Graduated autonomy | ❌ None |
| **Packaging** | Electron auto-updater | .deb/.rpm/.exe/.dmg | pip install only |

### Sopno's Unique Advantage
Sopno is a **voice-first** assistant — Cursor and AntiGravity are text/code-first. Sopno's voice pipeline (wake word → STT → LLM → TTS with barge-in) is already more advanced than most AI products. The gap is in **visualization and product polish**.

### Recommended Architecture
```
┌─────────────────────────────────────────────────┐
│  Tauri 2 + React/Svelte Frontend                │
│  (10MB bundle, always-on-top overlay)           │
├─────────────────────────────────────────────────┤
│  Python Backend (Tauri sidecar)                 │
│  ┌───────────┬───────────┬───────────┐          │
│  │ Voice     │ LLM       │ Tools     │          │
│  │ Pipeline  │ Client    │ Registry  │          │
│  └───────────┴───────────┴───────────┘          │
├─────────────────────────────────────────────────┤
│  Local Storage (SQLite)                         │
│  Memory │ Reminders │ Rules │ Agents │ Config   │
└─────────────────────────────────────────────────┘
```

**Why Tauri 2?**
- 10MB bundle (vs 150MB Electron)
- Always-on-top overlay for voice assistant HUD
- System webview (no bundled Chromium)
- Rust backend for performance-critical paths
- Python sidecar for existing AI pipeline
- Cross-platform: Windows, Linux, macOS

---

## 2. HUD & Visualization

### Design Philosophy
- **"Always visible, never intrusive"** — floating widget that appears when needed
- **Dark mode first** — 82% of users prefer dark for AI tools
- **Minimal chrome** — no title bars, clean edges, translucent background
- **State-driven** — different visuals for idle/listening/thinking/speaking/error

### Core HUD Elements

#### 2.1 Status Orb (Center-Piece)
A circular animated indicator showing Sopno's current state:

| State | Visual | Animation |
|-------|--------|-----------|
| **Idle** | Breathing pulse (soft glow) | Gentle opacity oscillation |
| **Listening** | Waveform ring | Real-time audio visualization |
| **Thinking** | Orbiting particles | 9 animation states (thinking-orbs library) |
| **Speaking** | Pulsing ring + text | Audio-reactive pulse |
| **Error** | Red flash + message | Brief shake + error text |

**Implementation**: Canvas-based `thinking-orbs` library (2,486 GitHub stars, 9 animated states, works in all browsers).

#### 2.2 Response Panel
- Slides in from right or appears below the orb
- Markdown-rendered response text
- Streaming text with typing cursor (thin vertical bar)
- Collapsible thinking/reasoning sections above the response
- Auto-scroll with "Jump to latest" button

#### 2.3 Context Ring (Token Display)
A circular progress ring (donut chart) showing context window usage:

```
┌──────────────────────┐
│   ┌──────────┐       │
│   │  45%     │       │  ← Color-coded: green < 65%, amber 65-85%, red > 85%
│   │  tokens  │       │
│   └──────────┘       │
│   Context Window     │
└──────────────────────┘
```

**Color thresholds** (industry standard):
- Green (emerald): < 65% used
- Amber (yellow): 65-85% used
- Red: > 85% used

**Hover popover breakdown**:
```
Input:      12,453 tokens
Cached:      8,192 tokens
Output:        892 tokens
Reasoning:   3,201 tokens
─────────────────────
Total:     24,738 / 128,000 (19%)
```

#### 2.4 Model Selector (Pill Dropdown)
Claude-style pill selector in the HUD header:

```
[🧠 Qwen3:8b ▾]
┌────────────────────────────┐
│ ● qwen3:8b        ✓       │  ← Current model
│   Balanced, fast, local   │
│                            │
│ ○ gemma3:4b                │
│   Lightweight, fast        │
│                            │
│ ○ qwen3:32b                │
│   Best quality, slow       │
│                            │
│ ○ claude-sonnet-4          │
│   Cloud, highest quality   │
└────────────────────────────┘
```

#### 2.5 Listening Mode Toggle
Toggle switch in HUD:
```
[🌙 Wake Word] ←→ [🎙️ Always On]
```

#### 2.6 Quick Actions Bar
Bottom bar with common actions:
```
[🎤 Mute] [⚙️ Settings] [📝 History] [🔌 Plugins] [❓ Help]
```

### Layout Options

**Option A: Floating Overlay (Recommended)**
- Small, always-on-top widget (300x400px)
- Translucent background (configurable opacity: 0.7-0.95)
- Position: top-right corner (configurable)
- Expands on interaction, collapses when idle

**Option B: Full Window**
- Traditional desktop app window
- Left sidebar: conversation history
- Center: response + thinking
- Right panel: context ring + model selector
- More screen real estate but less "assistant-like"

**Option C: Hybrid**
- Floating overlay by default (voice interaction)
- Double-click to expand to full window (detailed review)
- Best of both worlds

### Visual Assets Needed
1. **Sopno logo** — animated version for the orb
2. **State icons** — listening, thinking, speaking, error
3. **Color palette** — dark theme primary colors
4. **Font** — monospace for tokens, sans-serif for UI
5. **Animations** — CSS keyframes for all states

---

## 3. Thinking & Self-Evaluation System

### 3.1 Thinking Mode

**How it works:**
1. User asks a question
2. LLM generates a "thinking" block (reasoning/chain-of-thought)
3. Thinking is shown as a collapsible section above the answer
4. Answer is generated after thinking

**Implementation with Qwen3:**
Qwen3 has native thinking mode. Enable via:
```python
response = ollama.chat(
    model="qwen3:8b",
    messages=[...],
    options={"num_predict": 512},  # thinking budget
)
# Qwen3 returns <think>...</think> blocks
```

**UI display:**
```
┌─────────────────────────────────┐
│ ▶ Thinking (2.3s)               │  ← Collapsed by default
│   ├─ Analyzing the question...  │     Click to expand
│   ├─ Checking date logic...     │
│   └─ Verifying calculation...   │
├─────────────────────────────────┤
│ Tomorrow is Thursday,           │  ← Answer
│ August 20, 2026.               │
└─────────────────────────────────┘
```

### 3.2 Self-Evaluation System

**Key research finding**: LLMs already have latent self-evaluation ability — it just needs to be surfaced (Self-Evaluation Elicitation, ACL 2026).

**Implementation approach:**
1. After generating an answer, ask the LLM to rate its confidence (1-10)
2. If confidence < 7, regenerate with "think step by step" prompt
3. If confidence < 4, search the web for verification
4. Show confidence indicator in HUD

**Confidence indicator:**
```
┌──────────────────┐
│ Confidence: 8/10 │  ← Green (high), Yellow (medium), Red (low)
│ ████████░░        │
└──────────────────┘
```

**Self-evaluation prompt template:**
```python
EVAL_PROMPT = """
Rate your confidence in this answer from 1-10.
Consider: Is this factually correct? Is it complete?
Could it be misleading?

Answer: {answer}
Confidence (1-10):
"""
```

### 3.3 Fast Mode vs Quality Mode

| Setting | Effect | Use Case |
|---------|--------|----------|
| **Fast mode** | No thinking, short responses | Quick questions, confirmations |
| **Balanced mode** | Light thinking, moderate responses | Daily use (default) |
| **Quality mode** | Deep thinking, detailed responses | Complex analysis, coding |

**UI toggle:**
```
[⚡ Fast] [⚖️ Balanced] [🧠 Deep Think]
```

**Implementation:**
- Fast: `llm_think: false`, `num_predict: 120`
- Balanced: `llm_think: true`, `num_predict: 512`
- Quality: `llm_think: true`, `num_predict: 2048`

---

## 4. Model Selection System

### 4.1 Local Model Support

**Recommended local models (Ollama):**

| Model | Size | Speed | Quality | Best For |
|-------|------|-------|---------|----------|
| `qwen3:0.6b` | 0.6B | ⚡⚡⚡⚡ | ★★ | Quick replies, mobile |
| `qwen3:1.7b` | 1.7B | ⚡⚡⚡ | ★★★ | Daily use, low RAM |
| `qwen3:4b` | 4B | ⚡⚡ | ★★★★ | Balanced (recommended) |
| `qwen3:8b` | 8B | ⚡ | ★★★★ | Current default |
| `qwen3:14b` | 14B | 🐌 | ★★★★★ | Complex tasks |
| `gemma3:4b` | 4B | ⚡⚡ | ★★★★ | Google quality |
| `phi4-mini` | 3.8B | ⚡⚡ | ★★★ | Microsoft, fast |
| `llama3.2:3b` | 3B | ⚡⚡⚡ | ★★★ | Meta, lightweight |

### 4.2 Cloud Model Support

**API-based models (optional):**

| Model | Provider | Cost | Quality |
|-------|----------|------|---------|
| `claude-sonnet-4` | Anthropic | $3/1M tokens | ★★★★★ |
| `gpt-4o-mini` | OpenAI | $0.15/1M tokens | ★★★★ |
| `gemini-2.0-flash` | Google | Free tier | ★★★★ |

### 4.3 Model Selector UI

**In the HUD:**
```python
# config.json addition
"models": [
    {"name": "qwen3:8b", "provider": "ollama", "size": "8B", "default": true},
    {"name": "qwen3:4b", "provider": "ollama", "size": "4B"},
    {"name": "gemma3:4b", "provider": "ollama", "size": "4B"},
    {"name": "claude-sonnet-4", "provider": "anthropic", "size": "cloud"},
]
```

**Switching mid-conversation:**
- Context is preserved when switching models
- Model change is logged in conversation history
- New model picks up existing context automatically

### 4.4 Auto-Mode (Smart Routing)

Like Cursor's "Auto" mode — automatically select the best model for the task:

```python
def auto_select_model(query: str, context: list) -> str:
    """Select model based on query complexity."""
    simple_patterns = r"\b(time|date|hello|hi|bye|yes|no|thanks)\b"
    complex_patterns = r"\b(code|debug|analyze|explain|write|create|research)\b"

    if re.search(simple_patterns, query, re.I):
        return "qwen3:1.7b"  # Fast, simple
    elif re.search(complex_patterns, query, re.I):
        return "qwen3:8b"    # Quality
    else:
        return settings.model_name  # Default
```

---

## 5. Memory & Context Management

### 5.1 Current Memory System
- SQLite-based persistent memory
- FTS5 keyword search
- Semantic (vector) recall with Ollama embeddings
- Token budget: 400 tokens max

### 5.2 Enhanced Memory System (8K Token Budget)

**Problem**: Current 400-token limit is too restrictive for mature conversations.

**Solution**: Tiered memory system with smart summarization.

#### Memory Tiers
```
┌─────────────────────────────────────────┐
│ Tier 1: Working Memory (Current Turn)   │
│   - Full context for current exchange   │
│   - 2,048 tokens                        │
├─────────────────────────────────────────┤
│ Tier 2: Session Memory (This Session)   │
│   - Summarized conversation history     │
│   - 2,048 tokens                        │
├─────────────────────────────────────────┤
│ Tier 3: Long-Term Memory (Persistent)   │
│   - Key facts, user preferences         │
│   - 2,048 tokens                        │
├─────────────────────────────────────────┤
│ Tier 4: Knowledge Base (Searchable)     │
│   - Documents, web research             │
│   - On-demand retrieval                 │
└─────────────────────────────────────────┘
```

**Total budget**: 8,192 tokens (configurable)

#### Smart Summarization
When context fills up:
1. Summarize older turns into 200-token chunks
2. Store summaries in session memory
3. Keep full text in searchable archive
4. Reference archives when needed ("Let me check our previous conversation...")

```python
def summarize_conversation(messages: list, max_tokens: int = 200) -> str:
    """Summarize conversation history into compact form."""
    prompt = f"""
    Summarize this conversation in {max_tokens} tokens or less.
    Focus on: key decisions, facts, user preferences, ongoing tasks.

    Conversation:
    {_format_messages(messages)}

    Summary:
    """
    return llm_chat([{"role": "user", "content": prompt}])
```

#### Memory Types
| Type | Description | Example |
|------|-------------|---------|
| **Factual** | Concrete information | "User's name is Ahmed" |
| **Preference** | User likes/dislikes | "Prefers Bangla responses" |
| **Procedural** | How to do things | "Always use vim for editing" |
| **Contextual** | Situational awareness | "Working on sopno project" |
| **Episodic** | Past events | "Yesterday we fixed barge-in" |

### 5.3 Context Window Management

**Auto-summarization trigger**: When context > 75% of max
**Context pruning**: Remove oldest tool results first
**Reference recovery**: "Let me check our earlier conversation about..."

---

## 6. Token & Context Display

### 6.1 Real-Time Token Counter

**Display in HUD:**
```
┌──────────────────────────┐
│ Context: 12,453 / 8,192  │  ← Shows current/limit
│ ████████░░░░░░░░ 61%     │  ← Progress bar
│                          │
│ Breakdown:               │
│   System:    1,200       │
│   Tools:       800       │
│   Memory:     2,000      │
│   History:    8,453      │
│   ─────────────────      │
│   Total:    12,453       │
└──────────────────────────┘
```

### 6.2 Token Estimation (Python)

```python
# Simple token estimation (no external dependency)
def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English."""
    return len(text) // 4

# Or use tiktoken for accurate counting
import tiktoken
encoder = tiktoken.get_encoding("cl100k_base")

def count_tokens(text: str) -> int:
    return len(encoder.encode(text))
```

### 6.3 Cost Estimation (Cloud Models)

```python
MODEL_COSTS = {
    "claude-sonnet-4": {"input": 3.0, "output": 15.0},  # per 1M tokens
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
    "qwen3:8b": {"input": 0.0, "output": 0.0},  # Local = free
}

def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    costs = MODEL_COSTS.get(model, {"input": 0, "output": 0})
    return (input_tokens * costs["input"] + output_tokens * costs["output"]) / 1_000_000
```

---

## 7. Interrupt & Barge-In System

### 7.1 Current State
- Basic energy-based barge-in in InputStream callback
- Calibration for TTS audio baseline
- Configurable threshold and confirmation blocks

### 7.2 Mature Interrupt System

**Production pipeline** (from LiveKit research):
```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ Audio In │ → │   VAD    │ → │Classify  │ → │  Action  │
│          │    │ Scoring  │    │Decision  │    │          │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
                     │               │               │
                     │               │               │
              Voice Activity    True Barge-in    Stop TTS
              Detection         vs Backchannel   Cancel LLM
                                 ("uh-huh")      Preserve Context
```

**Latency targets:**
| Stage | Target |
|-------|--------|
| VAD → trigger | < 20ms |
| TTS flush | < 100ms |
| LLM cancel | < 40ms |
| Skill cancel | < 200ms |

### 7.3 Backchannel Detection

**Problem**: "Uh-huh", "yeah", "mm-hmm" are not barge-ins — they're acknowledgments.

**Solution**: Classify audio events:
- **Barge-in**: User wants to interrupt and take over the conversation
- **Backchannel**: User is acknowledging, Sopno should continue
- **Pause**: User wants Sopno to pause, then continue

```python
BACKCHANNEL_PATTERNS = [
    "uh-huh", "yeah", "mm-hmm", "ok", "right",
    "আচ্ছা", "হ্যাঁ", "ঠিক আছে",  # Bangla backchannels
]
```

### 7.4 Context Preservation on Interrupt

When barge-in occurs:
1. Record the interrupted utterance
2. Preserve any in-flight tool calls
3. Save conversational state
4. Start new turn with context from interruption

```python
def handle_barge_in(interrupted_text: str, user_text: str):
    """Handle user interruption gracefully."""
    context.add_system_message(
        f"Note: I was saying '{interrupted_text}' when you interrupted."
    )
    context.add_user_message(user_text)
    # Continue conversation with preserved context
```

---

## 8. Permission System

### 8.1 Graduated Autonomy (Inspired by Claude Code)

| Mode | Description | Use Case |
|------|-------------|----------|
| **Plan** | Read-only, no edits | Exploration, learning |
| **Default** | Manual approval for writes/bash | Standard use (recommended) |
| **Accept Edits** | Auto-accept file edits | Trusted coding sessions |
| **Auto** | ML classifier approves/denies | Power users |
| **Bypass** | No prompts (dangerous) | Isolated environments only |

### 8.2 Tool Permission Categories

```python
TOOL_PERMISSIONS = {
    # Read-only tools (always allowed)
    "read": "allow",
    "search": "allow",
    "list": "allow",

    # File operations (ask first)
    "write_file": "ask",
    "edit_file": "ask",
    "delete_file": "ask",

    # System operations (always ask)
    "run_terminal": "ask",
    "install_package": "ask",
    "network_request": "ask",

    # Dangerous operations (deny by default)
    "sudo": "deny",
    "shutdown": "deny",
    "format_disk": "deny",
}
```

### 8.3 Permission UI

```
┌─────────────────────────────────────────┐
│ ⚠️ Tool Permission Required             │
│                                         │
│ Tool: write_file                        │
│ Target: /home/user/notes.txt            │
│ Content: "Hello, this is a note..."     │
│                                         │
│ [✓ Allow]  [✗ Deny]  [Always Allow]    │
└─────────────────────────────────────────┘
```

### 8.4 Auto-Mode Classifier

When in "Auto" mode, use a simple rule-based classifier:

```python
def classify_tool_call(tool: str, args: dict) -> str:
    """Classify tool call risk level."""
    HIGH_RISK = {"sudo", "shutdown", "reboot", "mkfs", "rm -rf"}
    MEDIUM_RISK = {"write_file", "edit_file", "run_terminal", "install"}

    if tool in HIGH_RISK:
        return "deny"
    elif tool in MEDIUM_RISK:
        # Check if target is in allowed paths
        target = args.get("path", "")
        if any(target.startswith(root) for root in settings.file_allowed_write):
            return "allow"
        return "ask"
    else:
        return "allow"
```

---

## 9. Packaging & Distribution

### 9.1 Recommended Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Frontend** | Tauri 2 + React/Svelte | 10MB bundle, always-on-top overlay |
| **Backend** | Python (Tauri sidecar) | Leverage existing AI ecosystem |
| **Binary** | Nuitka | 2-4x faster than PyInstaller, source protection |
| **Windows** | Inno Setup | Professional installer, auto-updates |
| **Linux** | AppImage + .deb/.rpm | Universal + native packaging |
| **macOS** | App bundle + DMG | Standard distribution |

### 9.2 Windows Distribution

**Pipeline:**
```
Python source → Nuitka (.exe) → Inno Setup (Setup.exe) → MSIX (optional)
```

**Inno Setup script** (`setup.iss`):
```iss
[Setup]
AppName=Sopno
AppVersion=1.0.0
DefaultDirName={autopf}\Sopno
DefaultGroupName=Sopno
OutputDir=dist
OutputBaseFilename=Sopno-Setup-1.0.0

[Files]
Source: "dist\sopno.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Sopno"; Filename: "{app}\sopno.exe"
Name: "{autodesktop}\Sopno"; Filename: "{app}\sopno.exe"

[Run]
Filename: "{app}\sopno.exe"; Description: "Launch Sopno"; Flags: postinstall nowait
```

### 9.3 Linux Distribution

**AppImage (universal):**
```bash
# Build with Nuitka
python -m nuitka --standalone --onefile --output-dir=dist main.py

# Create AppImage
appimagetool --appimage-extract-and-run dist/sopno dist/Sopno.AppImage
```

**Debian/Ubuntu (.deb):**
```bash
# Using FPM
fpm -s dir -t deb \
    -n sopno \
    -v 1.0.0 \
    --depends python3 \
    --depends libgl1-mesa-glx \
    --after-install scripts/post-install.sh \
    ./dist/sopno=/usr/bin/sopno \
    ./assets/sopno.desktop=/usr/share/applications/sopno.desktop
```

**Fedora/RHEL (.rpm):**
```bash
fpm -s dir -t rpm \
    -n sopno \
    -v 1.0.0 \
    ./dist/sopno=/usr/bin/sopno
```

### 9.4 Auto-Update System

**Tauri built-in updater:**
```json
// tauri.conf.json
{
  "updater": {
    "active": true,
    "endpoints": [
      "https://releases.sopno.app/{{target}}/{{arch}}/{{current_version}}"
    ],
    "pubkey": "dW50cnVzdGVk..."
  }
}
```

**Update flow:**
1. Check for updates on startup
2. Download in background
3. Prompt user to install
4. Restart with new version

### 9.5 Installation Methods

| Method | Platform | Command |
|--------|----------|---------|
| **AppImage** | Linux (any) | `chmod +x Sopno.AppImage && ./Sopno.AppImage` |
| **.deb** | Ubuntu/Debian | `sudo dpkg -i sopno_1.0.0_amd64.deb` |
| **.rpm** | Fedora/RHEL | `sudo rpm -i sopno-1.0.0.x86_64.rpm` |
| **Inno Setup** | Windows | Double-click `Sopno-Setup.exe` |
| **npm** | All | `npm install -g sopno` (wrapper script) |
| **pip** | All | `pip install sopno` (CLI only) |
| **Homebrew** | macOS/Linux | `brew install sopno` |

---

## 10. Implementation Phases

### Phase 1: HUD Foundation (Week 1-2)
- [ ] Set up Tauri 2 project with React/Svelte
- [ ] Create basic floating overlay window
- [ ] Implement status orb with 3 states (idle/listening/thinking)
- [ ] Add text response display
- [ ] Basic dark theme

### Phase 2: Core Features (Week 3-4)
- [ ] Token counter (context ring)
- [ ] Model selector dropdown
- [ ] Listening mode toggle (wake_word / always_on)
- [ ] Settings panel
- [ ] Connect to Python backend via Tauri commands

### Phase 3: Thinking & Quality (Week 5-6)
- [ ] Thinking mode toggle (Fast/Balanced/Deep)
- [ ] Collapsible thinking display
- [ ] Confidence indicator
- [ ] Self-evaluation prompt
- [ ] Auto-regeneration on low confidence

### Phase 4: Memory & Context (Week 7-8)
- [ ] Tiered memory system (8K token budget)
- [ ] Smart summarization
- [ ] Context breakdown display
- [ ] Cost estimation (cloud models)
- [ ] Memory management UI

### Phase 5: Permissions & Safety (Week 9-10)
- [ ] Tool permission system
- [ ] Permission request UI
- [ ] Auto-mode classifier
- [ ] Backchannel detection
- [ ] Context preservation on interrupt

### Phase 6: Packaging & Polish (Week 11-12)
- [ ] Nuitka build pipeline
- [ ] Windows installer (Inno Setup)
- [ ] Linux packages (AppImage + .deb + .rpm)
- [ ] Auto-update system
- [ ] Beta testing

### Phase 7: Advanced Features (Month 4+)
- [ ] Plugin system UI
- [ ] MCP server management
- [ ] Multi-agent orchestration
- [ ] Voice cloning
- [ ] Mobile companion app

---

## Appendix A: Technology Comparison

### Frontend Frameworks
| Framework | Size | Performance | Maturity | Best For |
|-----------|------|-------------|----------|----------|
| **Tauri 2 + React** | 10MB | ⚡⚡⚡⚡ | Production | Recommended |
| **Tauri 2 + Svelte** | 8MB | ⚡⚡⚡⚡⚡ | Production | Best performance |
| **Electron + React** | 150MB | ⚡⚡⚡ | Battle-tested | Most plugins |
| **PyQt/PySide** | 50MB | ⚡⚡ | Mature | Python-native |
| **CustomTkinter** | 20MB | ⚡ | Experimental | Simplest |

### Packaging Tools
| Tool | Platform | Size | Speed | Best For |
|------|----------|------|-------|----------|
| **Nuitka** | All | Smallest | ⚡⚡⚡⚡ | Recommended |
| **PyInstaller** | All | Medium | ⚡⚡ | Most compatible |
| **cx_Freeze** | All | Medium | ⚡⚡ | Cross-platform |
| **Briefcase** | All | Medium | ⚡⚡ | BeeWare ecosystem |

---

## Appendix B: Design Resources

### Inspiration
- **Cursor**: Context ring, model selector, streaming text
- **AntiGravity**: Multi-agent dashboard, artifact system
- **Jan.ai**: Clean local ChatGPT UI
- **Pluely**: Always-on-top translucent overlay (10MB)
- **thinking-orbs**: Animated status indicators

### Libraries
- `thinking-orbs` — 9 animated states, canvas-based
- `@assistant-ui/react` — Context display components
- `tiktoken` — Accurate token counting
- `framer-motion` — Smooth animations
- `radix-ui` — Accessible UI primitives

### Color Palette (Suggested)
```css
--bg-primary: #0a0a0f;      /* Deep dark */
--bg-secondary: #12121a;     /* Slightly lighter */
--accent-primary: #6366f1;   /* Indigo */
--accent-secondary: #8b5cf6; /* Purple */
--text-primary: #e2e8f0;     /* Light gray */
--text-secondary: #94a3b8;   /* Muted gray */
--success: #10b981;          /* Emerald */
--warning: #f59e0b;          /* Amber */
--error: #ef4444;            /* Red */
```

---

**Document Version**: 1.0
**Last Updated**: August 19, 2026
**Author**: Sopno Development Team
