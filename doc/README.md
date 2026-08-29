# Sopno Documentation

All project docs live here, organized to mirror the codebase layout.

## Getting Started

| Doc | Description |
|-----|-------------|
| [installation.md](getting-started/installation.md) | Prerequisites, setup, first run |
| [user-guide.md](getting-started/user-guide.md) | Full product guide and usage |

## Architecture

| Doc | Description |
|-----|-------------|
| [CODEBASE.md](CODEBASE.md) | **Complete codebase guide** — every folder, file, and function explained |
| [overview.md](architecture/overview.md) | Module layout, data flow, folder structure |
| [code-organization.md](architecture/code-organization.md) | File-size standard, split pattern, migration plans |
| [observations.md](architecture/observations.md) | Stack review and upgrade recommendations |
| [project-assessment.md](architecture/project-assessment.md) | Implementation status, gaps, and prioritized suggestions |

## Roadmap

| Doc | Description |
|-----|-------------|
| [features.md](roadmap/features.md) | Complete feature vision and capability reference |
| [status.md](roadmap/status.md) | Incremental progress tracker |
| [implementation-plan.md](roadmap/implementation-plan.md) | Step-by-step implementation plan |
| [thinking-modes.md](roadmap/thinking-modes.md) | Reasoning modes (quick/thinking/deep/plan) — design, auto-detection, planner flow |
| [long-running-agents.md](roadmap/long-running-agents.md) | Background agent system design |
| [autonomous-coding.md](roadmap/autonomous-coding.md) | Autonomous coding agent design |
| [MATURITY.md](roadmap/MATURITY.md) | **Maturity roadmap** — how to make Sopno as polished as Cursor/AntiGravity |

## HUD (Graphical Interface)

| Doc | Description |
|-----|-------------|
| [DESIGN.md](hud/DESIGN.md) | **Visual design guide** — colors, glassmorphism, glow effects, component specs, full CSS theme |
| [PYWEBVIEW.md](hud/PYWEBVIEW.md) | **Implementation guide** — pywebview setup, Python bridge, HTML/CSS/JS frontend, assistant integration |
| [voice-mode-ui-design.md](voice-mode-ui-design.md) | **Voice page spec** — orb research (ChatGPT/Gemini/Siri), 8-layer QPainter design, animation constants |
| [text-mode-ui-design.md](text-mode-ui-design.md) | **Text page spec** — full research digest, component placement, responsive token map, motion spec, phased implementation plan |

## Modules

Docs for specific packages (mirrors `sopno/`):

| Module | Doc |
|--------|-----|
| voice | [tts.md](modules/voice/tts.md) |
| memory | [memory.md](modules/memory/memory.md) |
| internet | [internet.md](modules/internet/internet.md) |

## Agents

| Doc | Description |
|-----|-------------|
| [agent-implementation.md](agen/agent-implementation.md) | Multi-agent system implementation guide |

---

## Layout

```
doc/
├── README.md                 ← you are here
├── voice-mode-ui-design.md   ← voice page UI spec (complete)
├── text-mode-ui-design.md    ← text page UI spec + implementation plan
├── getting-started/
│   ├── installation.md
│   └── user-guide.md
├── architecture/
│   ├── overview.md
│   ├── code-organization.md
│   ├── observations.md
│   └── project-assessment.md
├── roadmap/
│   ├── features.md
│   ├── status.md
│   ├── implementation-plan.md
│   ├── long-running-agents.md
│   ├── autonomous-coding.md
│   └── MATURITY.md
├── hud/
│   ├── DESIGN.md
│   └── PYWEBVIEW.md
├── modules/
│   ├── voice/
│   ├── memory/
│   └── internet/
└── agen/
    └── agent-implementation.md
```
