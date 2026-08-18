# Sopno HUD — Building a Premium Voice Assistant Interface
## How to Make Sopno Look & Feel Like Cursor / AntiGravity

**Date**: August 19, 2026
**Goal**: Build a world-class HUD that feels premium, not like a hobby project.

---

## Table of Contents
1. [The Premium Formula](#1-the-premium-formula)
2. [Tauri 2 Setup](#2-tauri-2-setup)
3. [Color System & Theme](#3-color-system--theme)
4. [Glassmorphism & Glow](#4-glassmorphism--glow)
5. [Component Architecture](#5-component-architecture)
6. [Status Orb (Center Piece)](#6-status-orb-center-piece)
7. [Response Panel](#7-response-panel)
8. [Token Ring (Context Display)](#8-token-ring-context-display)
9. [Model Selector](#9-model-selector)
10. [Thinking Display](#10-thinking-display)
11. [Streaming Text](#11-streaming-text)
12. [Animations & Transitions](#12-animations--transitions)
13. [Audio Waveform](#13-audio-waveform)
14. [Settings Panel](#14-settings-panel)
15. [Complete CSS Theme](#15-complete-css-theme)
16. [Component Code](#16-component-code)

---

## 1. The Premium Formula

**What makes Cursor/AntiGravity feel "premium" vs "hobby":**

| Factor | Hobby Project | Premium Product |
|--------|---------------|-----------------|
| **Background** | Flat solid color | Gradient with depth |
| **Surfaces** | Flat boxes | Glassmorphic panels with blur |
| **Text** | Plain rendering | Streaming with blinking cursor |
| **States** | Static labels | Animated orbs/particles |
| **Transitions** | Instant jumps | Spring-physics animations |
| **Colors** | Random palette | Cohesive system (oklab) |
| **Shadows** | 1px borders | Atmospheric 28px diffuse shadows |
| **Typography** | Single font | 2-3 font system |
| **Empty state** | Blank screen | Guided onboarding |
| **Feedback** | None | Every action has visual response |

**The 10 rules:**
1. Dark theme with colorful gradient background
2. Glassmorphic panels (blur + transparency + border)
3. Status orb that animates through states
4. Streaming text with blinking cursor
5. SVG ring for token usage with color shifts
6. Spring-physics transitions (framer-motion)
7. Glow effects on active elements
8. Progressive disclosure (minimal shell, reveal on demand)
9. Every state has a unique visual
10. The output IS the UX — beautifully typeset responses

---

## 2. Tauri 2 Setup

### 2.1 Project Structure
```
sopno-hud/
├── src/                          # React frontend
│   ├── App.tsx
│   ├── components/
│   │   ├── StatusOrb.tsx
│   │   ├── ResponsePanel.tsx
│   │   ├── TokenRing.tsx
│   │   ├── ModelSelector.tsx
│   │   ├── ThinkingBlock.tsx
│   │   ├── SettingsPanel.tsx
│   │   └── Waveform.tsx
│   ├── hooks/
│   │   ├── useStreamingText.ts
│   │   ├── useAutoScroll.ts
│   │   └── useAppState.ts
│   ├── styles/
│   │   ├── theme.css
│   │   ├── glassmorphism.css
│   │   └── animations.css
│   └── lib/
│       └── tauri-commands.ts
├── src-tauri/                    # Rust backend
│   ├── tauri.conf.json
│   ├── capabilities/
│   └── src/
└── package.json
```

### 2.2 Tauri Config (tauri.conf.json)
```json
{
  "$schema": "https://raw.githubusercontent.com/tauri-apps/tauri/dev/crates/tauri-config-schema/schema.json",
  "productName": "Sopno",
  "version": "1.0.0",
  "identifier": "app.sopno.desktop",
  "app": {
    "macOSPrivateApi": true,
    "windows": [
      {
        "label": "main",
        "title": "Sopno",
        "width": 420,
        "height": 600,
        "minWidth": 320,
        "minHeight": 400,
        "resizable": true,
        "transparent": true,
        "decorations": false,
        "shadow": false,
        "alwaysOnTop": true,
        "visibleOnAllWorkspaces": true,
        "skipTaskbar": true,
        "acceptFirstMouse": true,
        "x": 1200,
        "y": 100
      }
    ]
  },
  "bundle": {
    "active": true,
    "targets": "all",
    "icon": [
      "icons/32x32.png",
      "icons/128x128.png",
      "icons/128x128@2x.png",
      "icons/icon.icns",
      "icons/icon.ico"
    ]
  },
  "plugins": {
    "shell": {
      "open": true,
      "scope": [
        {
          "name": "binaries/sopno-backend",
          "sidecar": true,
          "args": true
        }
      ]
    }
  }
}
```

### 2.3 Capabilities (capabilities/default.json)
```json
{
  "$schema": "https://raw.githubusercontent.com/tauri-apps/tauri/dev/crates/tauri-utils/schema/capability.json",
  "identifier": "default",
  "description": "Default capabilities for Sopno",
  "windows": ["main"],
  "permissions": [
    "core:default",
    "core:window:allow-set-always-on-top",
    "core:window:allow-start-dragging",
    "core:window:allow-close",
    "core:window:allow-hide",
    "core:window:allow-show",
    "core:window:allow-set-position",
    "core:window:allow-set-size",
    "core:window:allow-toggle-maximize",
    "shell:allow-execute",
    "shell:allow-spawn",
    "shell:allow-stdin-write"
  ]
}
```

### 2.4 Package.json
```json
{
  "name": "sopno-hud",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "tauri dev",
    "build": "tauri build",
    "preview": "vite preview"
  },
  "dependencies": {
    "@tauri-apps/api": "^2.0.0",
    "@tauri-apps/plugin-shell": "^2.0.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "framer-motion": "^12.0.0",
    "react-markdown": "^9.0.0",
    "react-syntax-highlighter": "^15.5.0",
    "lucide-react": "^0.400.0"
  },
  "devDependencies": {
    "@tauri-apps/cli": "^2.0.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.3.0",
    "typescript": "^5.5.0",
    "vite": "^6.0.0"
  }
}
```

---

## 3. Color System & Theme

### 3.1 Sopno Color Palette

**Inspired by Cursor's warm palette + Gemini's gradient energy:**

```css
:root {
  /* ── Base Colors ── */
  --bg-deep: #06060c;          /* Deepest background */
  --bg-primary: #0a0a14;       /* Main background */
  --bg-secondary: #10101e;     /* Card/panel background */
  --bg-tertiary: #161628;      /* Elevated surfaces */

  /* ── Accent Colors ── */
  --accent-blue: #6366f1;      /* Primary (Indigo) */
  --accent-purple: #8b5cf6;    /* Secondary (Purple) */
  --accent-cyan: #06b6d4;      /* Tertiary (Cyan) */
  --accent-pink: #ec4899;      /* Thinking/energy */
  --accent-green: #10b981;     /* Success/active */
  --accent-amber: #f59e0b;     /* Warning */
  --accent-red: #ef4444;       /* Error/danger */

  /* ── Text Colors ── */
  --text-primary: #e2e8f0;     /* Main text */
  --text-secondary: #94a3b8;   /* Muted text */
  --text-tertiary: #64748b;    /* Dim text */
  --text-accent: #818cf8;      /* Link/highlight */

  /* ── Glass Colors ── */
  --glass-bg: rgba(255, 255, 255, 0.06);
  --glass-border: rgba(255, 255, 255, 0.10);
  --glass-highlight: rgba(255, 255, 255, 0.15);
  --glass-shadow: rgba(0, 0, 0, 0.5);

  /* ── Gradient Stops ── */
  --gradient-start: #6366f1;
  --gradient-mid: #8b5cf6;
  --gradient-end: #ec4899;

  /* ── Shadows ── */
  --shadow-sm: 0 2px 8px rgba(0, 0, 0, 0.3);
  --shadow-md: 0 8px 24px rgba(0, 0, 0, 0.4);
  --shadow-lg: 0 16px 48px rgba(0, 0, 0, 0.5);
  --shadow-glow: 0 0 20px rgba(99, 102, 241, 0.3);

  /* ── Blur ── */
  --blur-sm: 8px;
  --blur-md: 12px;
  --blur-lg: 20px;

  /* ── Border Radius ── */
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-xl: 24px;
  --radius-full: 9999px;

  /* ── Transitions ── */
  --ease-standard: cubic-bezier(0.4, 0, 0.2, 1);
  --ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
  --duration-fast: 150ms;
  --duration-normal: 250ms;
  --duration-slow: 400ms;
}
```

### 3.2 Background Gradient

**The animated gradient background that makes it feel alive:**

```css
body {
  background: var(--bg-deep);
  overflow: hidden;
}

/* Animated gradient orbs floating behind the glass */
.gradient-bg {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 0;
  overflow: hidden;
}

.gradient-bg::before,
.gradient-bg::after {
  content: '';
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  animation: float 20s ease-in-out infinite;
}

.gradient-bg::before {
  width: 300px;
  height: 300px;
  background: radial-gradient(circle, var(--accent-blue) 0%, transparent 70%);
  top: -100px;
  right: -50px;
  opacity: 0.4;
  animation-delay: 0s;
}

.gradient-bg::after {
  width: 250px;
  height: 250px;
  background: radial-gradient(circle, var(--accent-purple) 0%, transparent 70%);
  bottom: -80px;
  left: -30px;
  opacity: 0.3;
  animation-delay: -10s;
}

@keyframes float {
  0%, 100% { transform: translate(0, 0) scale(1); }
  25% { transform: translate(30px, -20px) scale(1.05); }
  50% { transform: translate(-20px, 30px) scale(0.95); }
  75% { transform: translate(20px, 20px) scale(1.02); }
}
```

---

## 4. Glassmorphism & Glow

### 4.1 Glass Panel

```css
.glass {
  background: var(--glass-bg);
  backdrop-filter: blur(var(--blur-md)) saturate(180%);
  -webkit-backdrop-filter: blur(var(--blur-md)) saturate(180%);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
}

/* Elevated glass (modals, popovers) */
.glass-elevated {
  background: rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(var(--blur-lg)) saturate(200%);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: var(--radius-xl);
  box-shadow:
    0 24px 80px rgba(0, 0, 0, 0.6),
    0 0 1px rgba(255, 255, 255, 0.1);
}
```

### 4.2 Glow Effects

```css
/* Subtle glow on hover */
.glow-hover {
  transition: box-shadow var(--duration-normal) var(--ease-standard);
}
.glow-hover:hover {
  box-shadow:
    0 0 15px rgba(99, 102, 241, 0.3),
    0 0 30px rgba(99, 102, 241, 0.15),
    var(--shadow-md);
}

/* Active state glow */
.glow-active {
  box-shadow:
    0 0 10px rgba(99, 102, 241, 0.4),
    0 0 20px rgba(99, 102, 241, 0.2),
    0 0 40px rgba(99, 102, 241, 0.1),
    var(--shadow-md);
}

/* Pulsing glow (for listening/thinking states) */
@keyframes glow-pulse {
  0%, 100% {
    box-shadow:
      0 0 15px rgba(99, 102, 241, 0.3),
      0 0 30px rgba(99, 102, 241, 0.15);
  }
  50% {
    box-shadow:
      0 0 25px rgba(99, 102, 241, 0.5),
      0 0 50px rgba(99, 102, 241, 0.25);
  }
}
.glow-pulse { animation: glow-pulse 2s ease-in-out infinite; }

/* Neon text glow */
.neon-text {
  color: var(--accent-blue);
  text-shadow:
    0 0 4px var(--accent-blue),
    0 0 8px var(--accent-blue),
    0 0 16px rgba(99, 102, 241, 0.5);
}
```

---

## 5. Component Architecture

### 5.1 Layout Structure

```
┌─────────────────────────────────────┐
│  [Drag Region]          [─] [□] [×] │  ← Custom titlebar (32px)
├─────────────────────────────────────┤
│                                     │
│         ┌───────────────┐           │
│         │  Status Orb   │           │  ← Center piece (80x80px)
│         │  (animated)   │           │
│         └───────────────┘           │
│                                     │
│  ┌─────────────────────────────┐    │
│  │     Response Panel          │    │  ← Glass panel
│  │  ┌─────────────────────┐    │    │
│  │  │ ▶ Thinking (2.3s)   │    │    │  ← Collapsible
│  │  ├─────────────────────┤    │    │
│  │  │ Response text...    │    │    │  ← Streaming markdown
│  │  │ █                   │    │    │  ← Blinking cursor
│  │  └─────────────────────┘    │    │
│  └─────────────────────────────┘    │
│                                     │
│  ┌──────────┐  ┌──────────────────┐ │
│  │ Token    │  │  Model Selector  │ │  ← Bottom bar
│  │ Ring     │  │  [Qwen3:8b ▾]   │ │
│  └──────────┘  └──────────────────┘ │
│                                     │
│  ┌─────────────────────────────┐    │
│  │  [🎤 Listening...]  [⚙️]   │    │  ← Status bar
│  └─────────────────────────────┘    │
└─────────────────────────────────────┘
```

### 5.2 App State Machine

```typescript
type AppState = 
  | 'idle'        // Orb breathing, waiting
  | 'listening'   // Orb waveform, capturing audio
  | 'thinking'    // Orb particles, LLM processing
  | 'speaking'    // Orb pulse, TTS playing
  | 'error'       // Orb red flash, error message
  | 'calibrating' // Orb subtle spin, mic calibration
  | 'loading'     // Orb dots, model loading
```

### 5.3 Component Hierarchy

```tsx
<App>
  <GradientBackground />        {/* Animated gradient orbs */}
  <DragRegion />                 {/* Invisible drag area */}
  <WindowControls />             {/* Close/minimize/maximize */}
  
  <MainPanel>
    <StatusOrb state={appState} />   {/* Animated center piece */}
    
    <ResponsePanel visible={hasResponse}>
      <ThinkingBlock text={thinking} collapsed={true} />
      <MarkdownRenderer text={response} streaming={isStreaming} />
    </ResponsePanel>
    
    <BottomBar>
      <TokenRing used={tokensUsed} max={tokensMax} />
      <ModelSelector 
        current={currentModel} 
        models={availableModels}
        onChange={switchModel}
      />
    </BottomBar>
    
    <StatusBar state={appState} message={statusMessage} />
  </MainPanel>
  
  <SettingsPanel open={showSettings} onClose={closeSettings} />
</App>
```

---

## 6. Status Orb (Center Piece)

The most important visual element. It communicates Sopno's state through animation.

### 6.1 Orb States

| State | Animation | Color | Size |
|-------|-----------|-------|------|
| **idle** | Gentle breathing pulse | Blue → Purple gradient | 64px |
| **listening** | Audio waveform ring | Cyan | 80px |
| **thinking** | Orbiting particles | Purple → Pink | 72px |
| **speaking** | Pulsing ring + bounce | Green | 80px |
| **error** | Red flash + shake | Red | 64px |
| **calibrating** | Subtle spinning ring | Amber | 64px |

### 6.2 StatusOrb Component

```tsx
import { motion, AnimatePresence } from 'framer-motion';

type OrbState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'error';

interface StatusOrbProps {
  state: OrbState;
  onClick?: () => void;
}

export function StatusOrb({ state, onClick }: StatusOrbProps) {
  const colors: Record<OrbState, string> = {
    idle: 'from-indigo-500 to-purple-500',
    listening: 'from-cyan-400 to-blue-500',
    thinking: 'from-purple-500 to-pink-500',
    speaking: 'from-green-400 to-emerald-500',
    error: 'from-red-500 to-red-600',
  };

  return (
    <motion.button
      onClick={onClick}
      className="relative flex items-center justify-center"
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.95 }}
    >
      {/* Outer glow ring */}
      <motion.div
        className={`absolute rounded-full bg-gradient-to-br ${colors[state]}`}
        animate={{
          scale: state === 'speaking' ? [1, 1.3, 1] : [1, 1.1, 1],
          opacity: state === 'idle' ? [0.2, 0.4, 0.2] : [0.3, 0.6, 0.3],
        }}
        transition={{
          duration: state === 'speaking' ? 0.8 : 2,
          repeat: Infinity,
          ease: 'easeInOut',
        }}
        style={{ width: 100, height: 100, filter: 'blur(20px)' }}
      />

      {/* Main orb */}
      <motion.div
        className={`relative rounded-full bg-gradient-to-br ${colors[state]} flex items-center justify-center`}
        animate={{
          scale: state === 'thinking' ? [1, 1.02, 1] : 1,
        }}
        transition={{
          duration: 1.5,
          repeat: state === 'thinking' ? Infinity : 0,
          ease: 'easeInOut',
        }}
        style={{
          width: 72,
          height: 72,
          boxShadow: `0 0 30px rgba(99, 102, 241, 0.4)`,
        }}
      >
        {/* Inner highlight */}
        <div 
          className="absolute inset-1 rounded-full"
          style={{
            background: 'radial-gradient(circle at 30% 30%, rgba(255,255,255,0.2), transparent 60%)',
          }}
        />

        {/* State-specific content */}
        <AnimatePresence mode="wait">
          {state === 'idle' && (
            <motion.div
              key="idle"
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.8 }}
            >
              {/* Sopno logo or mic icon */}
              <MicIcon className="w-6 h-6 text-white/80" />
            </motion.div>
          )}

          {state === 'listening' && (
            <motion.div
              key="listening"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex gap-0.5 items-center h-6"
            >
              {/* Mini waveform bars */}
              {[...Array(5)].map((_, i) => (
                <motion.div
                  key={i}
                  className="w-0.5 bg-white/80 rounded-full"
                  animate={{ height: [4, 16, 4] }}
                  transition={{
                    duration: 0.6,
                    repeat: Infinity,
                    delay: i * 0.1,
                    ease: 'easeInOut',
                  }}
                />
              ))}
            </motion.div>
          )}

          {state === 'thinking' && (
            <motion.div
              key="thinking"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex gap-1"
            >
              {[0, 1, 2].map((i) => (
                <motion.div
                  key={i}
                  className="w-1.5 h-1.5 rounded-full bg-white/80"
                  animate={{ y: [0, -8, 0], opacity: [0.4, 1, 0.4] }}
                  transition={{
                    duration: 0.8,
                    repeat: Infinity,
                    delay: i * 0.15,
                    ease: 'easeInOut',
                  }}
                />
              ))}
            </motion.div>
          )}

          {state === 'speaking' && (
            <motion.div
              key="speaking"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <VolumeIcon className="w-6 h-6 text-white/80" />
            </motion.div>
          )}

          {state === 'error' && (
            <motion.div
              key="error"
              initial={{ opacity: 0, x: -5 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0 }}
              transition={{ type: 'spring', stiffness: 500 }}
            >
              <AlertIcon className="w-6 h-6 text-white/80" />
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>

      {/* Orbiting particles (thinking state) */}
      {state === 'thinking' && (
        <>
          {[0, 1, 2].map((i) => (
            <motion.div
              key={`particle-${i}`}
              className="absolute w-2 h-2 rounded-full bg-purple-400"
              animate={{
                rotate: 360,
                scale: [0.5, 1, 0.5],
              }}
              transition={{
                rotate: { duration: 3, repeat: Infinity, ease: 'linear', delay: i * 1 },
                scale: { duration: 1.5, repeat: Infinity, delay: i * 0.5 },
              }}
              style={{
                width: 6,
                height: 6,
                top: '50%',
                left: '50%',
                marginTop: -3,
                marginLeft: -3,
                transformOrigin: '0 0',
                translateX: Math.cos((i * 2 * Math.PI) / 3) * 50,
                translateY: Math.sin((i * 2 * Math.PI) / 3) * 50,
              }}
            />
          ))}
        </>
      )}
    </motion.button>
  );
}
```

---

## 7. Response Panel

### 7.1 Markdown Streaming

```tsx
import ReactMarkdown from 'react-markdown';
import { motion } from 'framer-motion';

interface ResponsePanelProps {
  text: string;
  thinking?: string;
  isStreaming: boolean;
}

export function ResponsePanel({ text, thinking, isStreaming }: ResponsePanelProps) {
  return (
    <motion.div
      className="glass p-4 mx-4 my-2 overflow-hidden"
      initial={{ opacity: 0, y: 20, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ type: 'spring', stiffness: 300, damping: 25 }}
    >
      {/* Thinking block (collapsible) */}
      {thinking && (
        <ThinkingBlock text={thinking} />
      )}

      {/* Response text */}
      <div className="prose prose-invert max-w-none">
        <ReactMarkdown
          components={{
            code({ node, inline, className, children, ...props }) {
              return inline ? (
                <code className="bg-white/10 px-1.5 py-0.5 rounded text-sm" {...props}>
                  {children}
                </code>
              ) : (
                <div className="relative group my-3">
                  <pre className="bg-black/30 rounded-lg p-4 overflow-x-auto text-sm">
                    <code className={className} {...props}>{children}</code>
                  </pre>
                  <CopyButton text={String(children)} />
                </div>
              );
            },
            p({ children }) {
              return <p className="mb-3 last:mb-0 leading-relaxed">{children}</p>;
            },
          }}
        >
          {text}
        </ReactMarkdown>

        {/* Streaming cursor */}
        {isStreaming && (
          <motion.span
            className="inline-block w-0.5 h-4 bg-indigo-400 ml-0.5 align-middle"
            animate={{ opacity: [1, 0, 1] }}
            transition={{ duration: 0.8, repeat: Infinity }}
          />
        )}
      </div>
    </motion.div>
  );
}
```

### 7.2 Copy Button

```tsx
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <motion.button
      onClick={handleCopy}
      className="absolute top-2 right-2 p-1.5 rounded-md bg-white/10 
                 opacity-0 group-hover:opacity-100 transition-opacity"
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.95 }}
    >
      {copied ? <CheckIcon className="w-4 h-4" /> : <CopyIcon className="w-4 h-4" />}
    </motion.button>
  );
}
```

---

## 8. Token Ring (Context Display)

### 8.1 SVG Ring Component

```tsx
interface TokenRingProps {
  used: number;
  max: number;
  size?: number;
}

export function TokenRing({ used, max, size = 48 }: TokenRingProps) {
  const percentage = Math.min((used / max) * 100, 100);
  const radius = (size - 8) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference * (1 - percentage / 100);

  // Color based on usage
  const getColor = (pct: number) => {
    if (pct < 65) return '#10b981';  // Green
    if (pct < 85) return '#f59e0b';  // Amber
    return '#ef4444';                 // Red
  };

  const color = getColor(percentage);

  return (
    <div className="relative flex items-center gap-2">
      <svg width={size} height={size} className="transform -rotate-90">
        {/* Background track */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(255,255,255,0.1)"
          strokeWidth={3}
        />
        {/* Progress fill */}
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={3}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset }}
          transition={{ duration: 0.5, ease: 'easeOut' }}
        />
      </svg>
      {/* Label */}
      <div className="text-xs">
        <div className="text-white/60">Context</div>
        <div className="text-white/90 font-medium">
          {Math.round(percentage)}%
        </div>
      </div>
    </div>
  );
}
```

---

## 9. Model Selector

### 9.1 Dropdown Component

```tsx
import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

interface Model {
  id: string;
  name: string;
  provider: string;
  size: string;
  speed: 'fast' | 'medium' | 'slow';
}

interface ModelSelectorProps {
  current: Model;
  models: Model[];
  onChange: (model: Model) => void;
}

export function ModelSelector({ current, models, onChange }: ModelSelectorProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      {/* Trigger button */}
      <motion.button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg glass
                   text-sm text-white/80 hover:text-white transition-colors"
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}
      >
        <BrainIcon className="w-4 h-4" />
        <span>{current.name}</span>
        <ChevronIcon className={`w-3 h-3 transition-transform ${open ? 'rotate-180' : ''}`} />
      </motion.button>

      {/* Dropdown */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.95 }}
            transition={{ type: 'spring', stiffness: 400, damping: 25 }}
            className="absolute bottom-full mb-2 left-0 w-64 glass-elevated p-2 z-50"
          >
            {models.map((model) => (
              <motion.button
                key={model.id}
                onClick={() => {
                  onChange(model);
                  setOpen(false);
                }}
                className={`w-full flex items-center gap-3 p-2 rounded-lg text-left
                           ${model.id === current.id ? 'bg-white/10' : 'hover:bg-white/5'}
                           transition-colors`}
                whileHover={{ x: 4 }}
              >
                <div className="flex-1">
                  <div className="text-sm text-white/90">{model.name}</div>
                  <div className="text-xs text-white/50">
                    {model.size} · {model.provider}
                  </div>
                </div>
                <SpeedBadge speed={model.speed} />
                {model.id === current.id && (
                  <CheckIcon className="w-4 h-4 text-indigo-400" />
                )}
              </motion.button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function SpeedBadge({ speed }: { speed: 'fast' | 'medium' | 'slow' }) {
  const colors = {
    fast: 'bg-green-500/20 text-green-400',
    medium: 'bg-amber-500/20 text-amber-400',
    slow: 'bg-red-500/20 text-red-400',
  };
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded ${colors[speed]}`}>
      {speed === 'fast' ? '⚡' : speed === 'medium' ? '⚖️' : '🐌'}
    </span>
  );
}
```

---

## 10. Thinking Display

### 10.1 Collapsible Thinking Block

```tsx
import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

interface ThinkingBlockProps {
  text: string;
  duration?: number; // seconds
}

export function ThinkingBlock({ text, duration }: ThinkingBlockProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="mb-3 border-b border-white/10 pb-3">
      {/* Header (always visible) */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-sm text-white/50 hover:text-white/70 transition-colors"
      >
        <motion.div
          animate={{ rotate: expanded ? 90 : 0 }}
          transition={{ type: 'spring', stiffness: 300, damping: 20 }}
        >
          <ChevronIcon className="w-3 h-3" />
        </motion.div>
        <SparklesIcon className="w-3.5 h-3.5 text-purple-400" />
        <span>Thinking</span>
        {duration && (
          <span className="text-white/30">({duration.toFixed(1)}s)</span>
        )}
      </button>

      {/* Expandable content */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="mt-2 pl-5 text-sm text-white/40 leading-relaxed 
                            border-l-2 border-purple-500/30">
              {text}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
```

---

## 11. Streaming Text

### 11.1 Streaming Hook

```typescript
import { useState, useCallback, useRef } from 'react';

export function useStreamingText() {
  const [text, setText] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const bufferRef = useRef('');

  const onToken = useCallback((token: string) => {
    bufferRef.current += token;
    setText(bufferRef.current);
  }, []);

  const onStart = useCallback(() => {
    bufferRef.current = '';
    setText('');
    setIsStreaming(true);
  }, []);

  const onEnd = useCallback(() => {
    setIsStreaming(false);
  }, []);

  const reset = useCallback(() => {
    bufferRef.current = '';
    setText('');
    setIsStreaming(false);
  }, []);

  return { text, isStreaming, onToken, onStart, onEnd, reset };
}
```

### 11.2 Markdown Close-Open Fix

```typescript
function closeOpenMarkdown(text: string): string {
  let out = text;
  
  // Close unclosed code fences
  const fenceCount = (out.match(/```/g) || []).length;
  if (fenceCount % 2 === 1) out += '\n```';
  
  // Close unclosed bold/italic
  const boldCount = (out.match(/\*\*/g) || []).length;
  if (boldCount % 2 === 1) out += '**';
  
  const italicCount = (out.match(/(?<!\*)\*(?!\*)/g) || []).length;
  if (italicCount % 2 === 1) out += '*';
  
  return out;
}
```

---

## 12. Animations & Transitions

### 12.1 Spring Physics (framer-motion)

```tsx
// Message entrance
<motion.div
  initial={{ opacity: 0, y: 20, scale: 0.95 }}
  animate={{ opacity: 1, y: 0, scale: 1 }}
  transition={{ type: 'spring', stiffness: 300, damping: 24 }}
/>

// Panel slide in
<motion.div
  initial={{ opacity: 0, x: 20 }}
  animate={{ opacity: 1, x: 0 }}
  transition={{ type: 'spring', stiffness: 400, damping: 30 }}
/>

// Button hover
<motion.button
  whileHover={{ scale: 1.02, y: -1 }}
  whileTap={{ scale: 0.98 }}
/>
```

### 12.2 Keyframe Animations

```css
/* Breathing pulse */
@keyframes breathe {
  0%, 100% { opacity: 0.6; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.05); }
}

/* Waveform bars */
@keyframes waveform {
  0%, 100% { height: 4px; }
  50% { height: 20px; }
}

/* Gradient shift */
@keyframes gradient-shift {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}

/* Spin */
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* Shake (error) */
@keyframes shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-5px); }
  75% { transform: translateX(5px); }
}
```

---

## 13. Audio Waveform

### 13.1 Waveform Visualizer

```tsx
import { useEffect, useRef } from 'react';

interface WaveformProps {
  audioContext: AudioContext | null;
  isActive: boolean;
}

export function Waveform({ audioContext, isActive }: WaveformProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationRef = useRef<number>();

  useEffect(() => {
    if (!isActive || !canvasContext || !analyser) return;

    const canvas = canvasRef.current!;
    const ctx = canvas.getContext('2d')!;
    const analyser = audioContext.createAnalyser();
    const dataArray = new Uint8Array(analyser.frequencyBinCount);

    const draw = () => {
      animationRef.current = requestAnimationFrame(draw);
      analyser.getByteTimeDomainData(dataArray);

      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.lineWidth = 2;
      ctx.strokeStyle = 'rgba(99, 102, 241, 0.8)';
      ctx.beginPath();

      const sliceWidth = canvas.width / dataArray.length;
      let x = 0;

      for (let i = 0; i < dataArray.length; i++) {
        const v = dataArray[i] / 128.0;
        const y = (v * canvas.height) / 2;

        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
        x += sliceWidth;
      }

      ctx.lineTo(canvas.width, canvas.height / 2);
      ctx.stroke();
    };

    draw();

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [isActive, audioContext]);

  return (
    <canvas
      ref={canvasRef}
      width={200}
      height={40}
      className="rounded-lg"
      style={{ opacity: isActive ? 1 : 0.3 }}
    />
  );
}
```

---

## 14. Settings Panel

### 14.1 Sliding Settings Panel

```tsx
import { motion, AnimatePresence } from 'framer-motion';

interface SettingsPanelProps {
  open: boolean;
  onClose: () => void;
}

export function SettingsPanel({ open, onClose }: SettingsPanelProps) {
  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/50 z-40"
            onClick={onClose}
          />

          {/* Panel */}
          <motion.div
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 300, damping: 30 }}
            className="fixed right-0 top-0 bottom-0 w-80 glass-elevated z-50 p-6 overflow-y-auto"
          >
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-semibold text-white">Settings</h2>
              <button onClick={onClose} className="text-white/50 hover:text-white">
                <XIcon className="w-5 h-5" />
              </button>
            </div>

            {/* Settings content */}
            <div className="space-y-4">
              <SettingGroup title="Voice">
                <ToggleSetting label="Wake Word" checked={true} />
                <SliderSetting label="Volume" value={80} min={0} max={100} />
              </SettingGroup>

              <SettingGroup title="Model">
                <SelectSetting
                  label="Primary Model"
                  value="qwen3:8b"
                  options={['qwen3:4b', 'qwen3:8b', 'gemma3:4b']}
                />
                <ToggleSetting label="Thinking Mode" checked={false} />
              </SettingGroup>

              <SettingGroup title="Appearance">
                <SelectSetting
                  label="Theme"
                  value="dark"
                  options={['dark', 'light', 'auto']}
                />
                <SliderSetting label="Opacity" value={85} min={50} max={100} />
              </SettingGroup>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
```

---

## 15. Complete CSS Theme

```css
/* ── Reset & Base ── */
*, *::before, *::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html, body, #root {
  height: 100%;
  background: transparent;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  color: var(--text-primary);
  overflow: hidden;
  user-select: none;
  -webkit-font-smoothing: antialiased;
}

/* ── Scrollbar ── */
::-webkit-scrollbar {
  width: 6px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.2);
}

/* ── Glass Utilities ── */
.glass {
  background: var(--glass-bg);
  backdrop-filter: blur(var(--blur-md)) saturate(180%);
  -webkit-backdrop-filter: blur(var(--blur-md)) saturate(180%);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
}

.glass-elevated {
  background: rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(var(--blur-lg)) saturate(200%);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: var(--radius-xl);
  box-shadow: 0 24px 80px rgba(0, 0, 0, 0.6);
}

/* ── Button Base ── */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border-radius: var(--radius-md);
  font-size: 0.875rem;
  font-weight: 500;
  transition: all var(--duration-fast) var(--ease-standard);
  cursor: pointer;
  border: none;
  outline: none;
}

.btn-primary {
  background: linear-gradient(135deg, var(--accent-blue), var(--accent-purple));
  color: white;
}
.btn-primary:hover {
  box-shadow: 0 0 20px rgba(99, 102, 241, 0.4);
  transform: translateY(-1px);
}

.btn-ghost {
  background: transparent;
  color: var(--text-secondary);
}
.btn-ghost:hover {
  background: rgba(255, 255, 255, 0.05);
  color: var(--text-primary);
}

/* ── Drag Region ── */
.drag-region {
  -webkit-app-region: drag;
  app-region: drag;
}
.drag-region button, .drag-region input {
  -webkit-app-region: no-drag;
  app-region: no-drag;
}
```

---

## 16. Component Code

### 16.1 Main App

```tsx
import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { StatusOrb } from './components/StatusOrb';
import { ResponsePanel } from './components/ResponsePanel';
import { TokenRing } from './components/TokenRing';
import { ModelSelector } from './components/ModelSelector';
import { SettingsPanel } from './components/SettingsPanel';
import { useStreamingText } from './hooks/useStreamingText';
import './styles/theme.css';

type AppState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'error';

export default function App() {
  const [appState, setAppState] = useState<AppState>('idle');
  const [showSettings, setShowSettings] = useState(false);
  const { text, isStreaming, onToken, onStart, onEnd } = useStreamingText();

  // Listen to backend events
  useEffect(() => {
    const unlisten = listen<string>('state-change', (e) => {
      setAppState(e.payload as AppState);
    });
    return () => { unlisten.then(fn => fn()); };
  }, []);

  useEffect(() => {
    const unlisten = listen<string>('token', (e) => {
      onToken(e.payload);
    });
    return () => { unlisten.then(fn => fn()); };
  }, [onToken]);

  return (
    <div className="relative h-full">
      {/* Animated gradient background */}
      <div className="gradient-bg" />

      {/* Main content */}
      <div className="relative z-10 h-full flex flex-col">
        {/* Drag region / titlebar */}
        <div className="drag-region h-8 flex items-center justify-between px-4">
          <span className="text-xs text-white/40">Sopno</span>
          <div className="flex gap-2">
            <button className="btn-ghost p-1" onClick={() => setShowSettings(true)}>
              <SettingsIcon className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Center: Status Orb */}
        <div className="flex-1 flex items-center justify-center">
          <StatusOrb
            state={appState}
            onClick={() => invoke('toggle-listening')}
          />
        </div>

        {/* Response area */}
        {text && (
          <ResponsePanel text={text} isStreaming={isStreaming} />
        )}

        {/* Bottom bar */}
        <div className="flex items-center justify-between px-4 py-3">
          <TokenRing used={12453} max={8192} />
          <ModelSelector
            current={{ id: 'qwen3:8b', name: 'Qwen3:8b', provider: 'Ollama', size: '8B', speed: 'medium' }}
            models={[
              { id: 'qwen3:4b', name: 'Qwen3:4b', provider: 'Ollama', size: '4B', speed: 'fast' },
              { id: 'qwen3:8b', name: 'Qwen3:8b', provider: 'Ollama', size: '8B', speed: 'medium' },
              { id: 'gemma3:4b', name: 'Gemma3:4b', provider: 'Ollama', size: '4B', speed: 'fast' },
            ]}
            onChange={(m) => invoke('switch-model', { model: m.id })}
          />
        </div>

        {/* Status bar */}
        <div className="flex items-center justify-center px-4 py-2 border-t border-white/5">
          <span className="text-xs text-white/40">
            {appState === 'idle' && 'Ready'}
            {appState === 'listening' && 'Listening...'}
            {appState === 'thinking' && 'Thinking...'}
            {appState === 'speaking' && 'Speaking...'}
            {appState === 'error' && 'Error occurred'}
          </span>
        </div>
      </div>

      {/* Settings panel */}
      <SettingsPanel open={showSettings} onClose={() => setShowSettings(false)} />
    </div>
  );
}
```

---

## Quick Start

```bash
# 1. Create Tauri project
npm create tauri-app@latest sopno-hud -- --template react-ts
cd sopno-hud

# 2. Install dependencies
npm install framer-motion react-markdown lucide-react

# 3. Copy the CSS theme to src/styles/theme.css
# 4. Copy components to src/components/
# 5. Copy hooks to src/hooks/

# 6. Run in dev mode
npm run tauri dev
```

---

**Document Version**: 1.0
**Last Updated**: August 19, 2026
