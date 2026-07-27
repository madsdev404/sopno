# Sopno AI Assistant

## Complete Feature Roadmap & Capability Reference

Version: 1.0
Target: Offline Local AI Assistant
Model: Qwen3 8B / 14B
OS: Linux (Ubuntu → Arch)
Author: MD. Abduss Sobhan

---

# Vision

Sopno is a completely local AI operating system assistant similar to:

- Cursor
- Claude Code
- Gemini CLI
- OpenAI Codex CLI
- Jarvis

Unlike those, Sopno owns the entire computer through modular tools.

The LLM is **only the brain**.

Everything else is implemented as tools.

---

# Architecture

```
                    User

                      │

          Voice / CLI / GUI / API

                      │

             Conversation Manager

                      │

                 Qwen3 (Brain)

                      │

               Agent / Planner

                      │

        Tool Selection + Memory Layer

                      │

 ┌──────────┬─────────┬──────────┬──────────┐
 │ Files    │ Browser │ Terminal │ Coding   │
 └──────────┴─────────┴──────────┴──────────┘
                      │
             Linux Operating System
```

---

# Core Modules

- AI Brain
- Memory
- Planning
- Tool Calling
- Permission Manager
- Context Manager
- Plugin System

---

# 1. File System Tools

## Read

- Read file
- Read folder
- Read project
- Read binary metadata
- Read images
- Read PDFs
- Read Office documents
- Read markdown

## Write

- Create file
- Create folder
- Rename
- Delete
- Move
- Copy
- Duplicate

## Search

- Search filename
- Search content
- Regex search
- Duplicate finder

## Monitor

- Watch filesystem
- Auto detect changes
- Auto indexing

---

# 2. Code Tools

## Project Understanding

- Understand project architecture
- Understand dependencies
- Explain code
- Explain errors

## Editing

- Create project
- Edit file
- Refactor
- Rename symbols
- Fix bugs
- Optimize code

## Generation

- Generate classes
- Generate API
- Generate frontend
- Generate backend
- Generate tests

## Analysis

- Find dead code
- Find security issues
- Find performance bottlenecks
- Detect code smells

## Testing

- Run tests
- Create tests
- Coverage report

## Build

- npm
- pnpm
- yarn
- cargo
- go
- python
- cmake

---

# 3. Git Tools

- git status
- add
- commit
- push
- pull
- stash
- checkout
- branch
- merge
- rebase

AI Features

- Explain commits
- Write commit messages
- Review pull requests
- Summarize changes

---

# 4. Terminal Tools

- Execute Bash
- Execute Fish
- Execute Zsh
- Execute Python

Manage

- Process
- Services
- Cron
- Logs

---

# 5. Browser Automation

Playwright

- Open browser
- Close browser
- Click
- Scroll
- Fill forms
- Upload
- Download

Search

- Google
- GitHub
- Stack Overflow
- Documentation

Reading

- Extract text
- Screenshot
- PDF export

---

# 6. Internet Tools

- REST API
- GraphQL
- RSS
- HTTP Requests

Search

- Search engines
- Documentation
- Wikipedia

Downloads

- Models
- Packages
- GitHub repos

---

# 7. Voice

Speech To Text

- Whisper
- faster-whisper

Text To Speech

- Piper
- Coqui

Wake Words

- Hey Sopno
- Hello Sopno

Streaming

- Interrupt speech
- Continuous conversation

---

# 8. Memory

Short Memory

Conversation Context

Long Memory

SQLite

Semantic Memory

Vector Database

Examples

Remember

- Name
- Preferences
- Coding style
- Projects

---

# 9. Planning

Task decomposition

Example

"Build a Django app"

↓

- Create folder
- Install Django
- Create app
- Create models
- Run migrations

---

# 10. Scheduler

- Reminder
- Alarm
- Automation
- Daily tasks

---

# 11. Email

- Read
- Send
- Reply
- Draft

---

# 12. Calendar

- Read
- Create event
- Update
- Delete

---

# 13. Notes

- Markdown
- Knowledge base
- Daily journal

---

# 14. Database Tools

SQLite

Postgres

MySQL

MongoDB

Redis

Operations

- Query
- Backup
- Restore
- Explain schema

---

# 15. Docker

- Build
- Run
- Stop
- Logs
- Compose

---

# 16. Kubernetes

- Deploy
- Logs
- Scale
- Restart

---

# 17. Linux Administration

Packages

- apt
- pacman
- dnf
- snap
- flatpak

Users

- adduser
- passwd
- sudo

System

- hostname
- timezone
- locale

---

# 18. Hardware

CPU

RAM

GPU

Temperature

Battery

Disk

USB

Bluetooth

Sensors

---

# 19. Networking

Ping

Traceroute

SSH

FTP

SFTP

Firewall

WiFi

VPN

LAN Scanner

---

# 20. AI Tools

Run

- Ollama
- llama.cpp

Manage

- Download models
- Delete models
- Benchmark

---

# 21. Image AI

Generate

- Images

Edit

- Background removal
- Upscale
- OCR

---

# 22. Video

Read

Create

Convert

Subtitle

Transcribe

---

# 23. Audio

Convert

Transcribe

Noise Removal

Music Metadata

---

# 24. Office

Word

Excel

PowerPoint

PDF

OCR

---

# 25. Smart Home

Lights

Switches

Camera

Sensors

Home Assistant

MQTT

---

# 26. Messaging

Discord

Telegram

Slack

Signal

WhatsApp (automation where permitted)

---

# 27. Development Integrations

VS Code

Cursor

JetBrains

Neovim

GitHub

GitLab

Jira

Linear

---

# 28. MCP Support

Model Context Protocol

Dynamic tool loading

Remote MCP servers

Local MCP servers

Custom MCP

---

# 29. Plugin System

Install plugin

Disable plugin

Update plugin

Plugin Marketplace

Hot Reload

---

# 30. Security

Permissions

Allow

Deny

Prompt

Examples

Delete File

Ask

Install Package

Ask

Shutdown

Ask

Read Downloads

Allow

Read Home

Allow

Run Python

Allow

Run rm -rf /

Always Ask

---

# 31. Logging

Every action

Every command

Every file

Every browser action

Export logs

Replay logs

---

# 32. GUI

Dashboard

Chat

Settings

Memory

Tools

Plugins

Logs

Models

---

# 33. Mobile Companion

Notifications

Remote execution

Voice

Status

---

# 34. Multi-Agent System

Planner

Coder

Researcher

Browser

Debugger

Reviewer

Each agent has different responsibilities.

---

# 35. Learning System

Learn preferences

Learn habits

Learn project structure

Remember corrections

Remember mistakes

---

# 36. Local Knowledge Base

Index

Books

PDFs

Code

Notes

Videos

Repositories

Search everything locally.

---

# 37. RAG

Semantic search

Document retrieval

Project retrieval

Knowledge retrieval

---

# 38. Vision

Read screenshots

Read desktop

Read webcam

Read documents

OCR

---

# 39. Desktop Control

Mouse

Keyboard

Clipboard

Windows

Notifications

Screenshots

Screen recording

---

# 40. Automation

"If battery below 20%

↓

Enable power saving."

"If compile succeeds

↓

Commit changes."

"If package updated

↓

Run tests."

---

# 41. Future Features

Autonomous coding

Long-running background agents

Research agent

News agent

Finance assistant

Medical reminder

Home server management

Cluster management

NAS management

Virtual machine management

Android control

IoT control

Robot control

Drone control

---

# Features Intentionally Not Included

These are technically possible, but should be carefully considered or avoided depending on your security model and ethics:

- Unrestricted execution of destructive commands without confirmation
- Automatic privilege escalation
- Keystroke logging
- Credential theft or password extraction
- Browser cookie theft
- Circumventing operating system security
- Self-replicating or self-modifying behavior without explicit controls
- Actions that violate laws or service terms

For learning OS internals, you can study how these mechanisms work, but your assistant should expose them through well-audited, permission-controlled modules rather than giving the model unrestricted access.

---

# Suggested Development Order

Phase 1

✓ Chat
✓ Tool calling
✓ Memory

Phase 2

✓ File tools
✓ Terminal
✓ Python
✓ Git

Phase 3

✓ Code editing
✓ Project understanding
✓ Browser

Phase 4

✓ Voice
✓ RAG
✓ Plugins

Phase 5

✓ Multi-Agent
✓ Automation
✓ GUI

Phase 6

✓ Full Linux integration
✓ MCP ecosystem
✓ Remote companion

---

# Final Goal

Sopno becomes a personal AI operating-system companion that can understand your intent, plan tasks, use tools responsibly, automate development workflows, manage your computer, and grow through plugins and long-term memory while keeping all core processing local.
