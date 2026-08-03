# Agent System Implementation Guide

## Overview

Sopno currently has a flat `user -> LLM -> tools -> reply` flow. This doc outlines what's needed to build a true multi-agent system.

## Architecture

```
User Request
    |
    v
[Planner Agent] -- decomposes request into sub-tasks
    |
    ├── [Coder Agent]     -- code reading/writing, git ops
    ├── [Researcher Agent] -- web search, doc lookup (RAG)
    ├── [Desktop Agent]   -- volume, media, apps, system
    └── [Orchestrator]    -- tracks progress, handles handoffs
```

## Steps

### 1. Create `sopno/agents/` module

```
sopno/agents/
├── __init__.py
├── base.py          # BaseAgent class (shared interface)
├── planner.py       # decomposes intent into sub-tasks
├── coder.py         # file I/O, code execution, git
├── researcher.py    # web search, RAG retrieval
├── desktop.py       # existing 7 tools
└── orchestrator.py  # state machine for task lifecycle
```

### 2. BaseAgent contract

```python
class BaseAgent:
    name: str
    system_prompt: str
    tools: list[ToolDef]

    async def run(self, task: Task, context: Context) -> AgentResult
```

Each agent gets its own system prompt scoped to its responsibility.

### 3. Planner agent

- Takes the raw user utterance
- Uses the LLM to decompose it into a list of sub-tasks with dependencies
- Outputs a task graph (DAG)

### 4. Orchestrator

- Maintains a `Task` state machine: `pending -> running -> completed | failed`
- Executes tasks in dependency order
- Passes results between agents
- Handles retries and error recovery
- Limits concurrent sub-tasks (resource quotas)

### 5. Agent handoff

Agents can call other agents via the orchestrator. The orchestrator collects results and feeds them back to the planner if re-planning is needed.

### 6. State persistence

- Store task history, agent outputs, and intermediate results in SQLite
- Enables resume across restarts and auditing

### 7. Integration with existing code

- Replace the single-step loop in `sopno/core/assistant.py` with the orchestrator
- Reuse existing tools (`sopno/tools/`) as the Desktop Agent's toolset
- Conversation history in `sopno/core/context.py` still holds the top-level user/assistant turns

## Dependencies to add

```
# requirements.txt additions
sqlalchemy         # or aiosqlite for task persistence
networkx           # optional, for DAG dependency graphs
```

## Resource quotas

Each agent task should have configurable limits:
- Max sub-tasks per request
- Max LLM calls per sub-task
- Max wall-clock time per sub-task
- Max total tokens consumed

## Future: RAG integration

Once RAG is built, the Researcher Agent will use the vector store for document/project retrieval before calling the LLM.
