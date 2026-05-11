# Event-Driven Patterns for a Multi-Agent Software Development Team

**Document type:** Explanation + Specification  
**Audience:** Architects and engineers building Python 3.13 agent pipelines in the opencode harness  
**Status:** Proposed

> **⚠️ HISTORICAL DOCUMENT — SUPERSEDED**
> This document was an early input to planning. It has been superseded by `specs/event-driven-agent-runtime-plan.md`, which is the authoritative controlling plan.
> Where conflicts exist between this document and the controlling plan, the controlling plan takes precedence.
> In particular: `messageCreated`, `session.idle`, and other stale event names in this document are **not** verified implementation guidance.
> Always cross-reference the controlling plan before acting on this document's recommendations.

---

> The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119.

---

## Table of contents

1. [Why event-driven fits agent systems](#1-why-event-driven-fits-agent-systems)
2. [Hidden factors most architects overlook](#2-hidden-factors-most-architects-overlook)
3. [The three-layer event model](#3-the-three-layer-event-model)
4. [Canonical patterns and where they apply](#4-canonical-patterns-and-where-they-apply)
5. [opencode integration points](#5-opencode-integration-points)
6. [Python 3.13 implementation](#6-python-313-implementation)
7. [The event envelope schema](#7-the-event-envelope-schema)
8. [Operational concerns](#8-operational-concerns)
9. [Phased implementation plan](#9-phased-implementation-plan)
10. [Architecture decision records](#10-architecture-decision-records)

**Amendment B — Critical gaps, academic research findings, and corrections**

- [B1. Critical: SQLite concurrent writes will corrupt event ordering](#b1-critical-sqlite-concurrent-writes-will-corrupt-event-ordering)
- [B2. High: Cross-task memory is absent](#b2-high-cross-task-memory-is-absent--mael-shows-this-is-a-major-missed-opportunity)
- [B3. High: Canary metric is undefined](#b3-high-the-canary-metric-is-undefined--use-self-certainty-as-the-intrinsic-reward-signal)
- [B4. High: Validator self-approves its own routing](#b4-high-the-validator-self-approves-its-own-routing--circular-validation)
- [B5. Medium: Blackboard write conflicts unresolved](#b5-medium-blackboard-write-conflicts-have-no-resolution-policy)
- [B6. Medium: Context7 agent missing from config](#b6-medium-the-context7-sub-agent-has-no-model-assignment-or-event-integration)
- [B7. Medium: No compensating transactions](#b7-medium-no-compensating-transaction-for-partial-rpiv-run-failures--adopt-sagallm-pattern)
- [B8. Low-Medium: Token budget ceiling missing](#b8-low-medium-token-budget-ceiling-missing-for-full-rpiv-runs-with-m27)
- [B9. Low: Regex parsing on reasoning-model output](#b9-low-parse_compaction_summary-uses-regex-on-m27-reasoning-model-output)
- [B10. Summary table](#b10-summary-what-changes-what-stays)
- [B11. Additional ADRs 0008–0010](#b11-additional-adrs)

**Amendment A — MiniMax M2.7 model integration**

- [A1. M2.7 strengths and weaknesses in the RPIV context](#a1-m27-strengths-and-weaknesses-in-the-rpiv-context)
- [A2. Stage-to-model routing table](#a2-stage-to-model-routing-table)
- [A3. Mitigating M2.7 weaknesses in opencode](#a3-mitigating-m27-weaknesses-in-opencode)
- [A4. Wiring M2.7 self-evolution into the harness](#a4-wiring-m27-self-evolution-into-the-harness)
- [A5. Self-evolution feedback loop implementation](#a5-self-evolution-feedback-loop-implementation)
- [A6. opencode configuration for M2.7](#a6-opencode-configuration-for-m27)
- [A7. Updated phased plan — M2.7 integration tasks](#a7-updated-phased-plan--m27-integration-tasks)
- [A8. Additional ADRs](#a8-additional-adrs)

---

## 1. Why event-driven fits agent systems

An agent's cognition loop is already event-shaped:

```
stimulus (event) → perception → reasoning → action → new events
```

Yet most early agent pipelines use synchronous, request-response chains. That design breaks in three ways when teams scale:

| Problem | Synchronous effect | Event-driven fix |
|---------|--------------------|-----------------|
| LLM latency variance (1–30 s per call) | Entire pipeline blocks on slowest agent | Async fan-out; each agent processes independently |
| Five-agent sequential chain | 15 s minimum latency, zero parallelism | Parallel stage execution where dependency graph allows |
| Single-agent failure | Full pipeline halt | Dead-letter queue isolates failures; others continue |
| Human-in-the-loop | Awkward polling | Native pause/resume on `permission.asked` events |
| Audit trail | Distributed traces added after the fact | Event log IS the audit trail, from day one |

The emerging industry consensus (Zylos Research, 2026; Confluent, 2025): use request-response for tool calls *within* a single agent's reasoning loop, and event-driven design for *everything else* — agent-to-agent communication, cross-system integration, and long-running workflows.

---

## 2. Hidden factors most architects overlook

These are the factors that standard EDA literature misses when applied to LLM-based software development teams.

### 2.1 Your pipeline is already macro-event-driven — the problem is the seams

The RPIV pipeline (Locator → Analyst → Context7 → Planner → Implementer → Validator) describes a workflow where *stages* are event-driven at a macro level: Planner cannot start until Analyst emits a completed research artifact. But at the *micro* level — within each stage, and across the handoff between stages — the current implementation is a blocking prompt call. EDA investment should target those seams first, not the internal LLM reasoning loop.

### 2.2 LLM failures are taxonomically different from network failures

Traditional EDA dead-letter queues handle transient failures (timeouts, network drops). LLM agent failures include a richer taxonomy:

| Failure class | Example | DLQ treatment |
|---------------|---------|---------------|
| Transient infrastructure | API rate limit, timeout | Retry with exponential backoff |
| Context overflow | Agent context exceeded 200k tokens | Compact and retry |
| Schema violation | Agent output fails Pydantic validation | Route to Validator critic |
| Semantic drift | Agent's plan contradicts the spec | Route to human review |
| Circular delegation | Agent A spawns B which spawns A | Circuit breaker; halt |
| Irreversible side effect | Git push to wrong branch | At-most-once guard; never retry |

Your DLQ MUST classify failure type before routing. A flat "retry or discard" policy is insufficient.

### 2.3 Idempotency applies to side effects, not LLM outputs

LLM outputs are non-deterministic by design. You can't make the same prompt produce the same output. What you CAN make idempotent are the *side effects*: file writes, git operations, test runs, API calls. The pattern:

```python
# Idempotency key: (task_id, action_type, content_hash)
# Check before executing; record after; skip on replay
```

This is the difference between "idempotent LLM pipeline" (impossible) and "idempotent effect pipeline" (achievable and necessary).

### 2.4 The `stk` JSON envelope is already an event schema

The `stk` CLI's JSON envelope — the stable contract used for stacked PR management — is structurally an event record. It has a type discriminant, a payload, and a producer identity. Rather than designing a new event schema from scratch, the implementation plan SHOULD extend `stk`'s envelope as the canonical event contract for the broader pipeline. This avoids proliferating schemas and creates a natural audit trail that maps to the PR graph.

### 2.5 The `compound-engine` broken feedback loop IS a Blackboard pattern deficit

The split knowledge store identified as a critical broken feedback loop in `compound-engine` is architecturally the same problem the Blackboard multi-agent pattern solves. The Blackboard pattern gives all agents a single shared, event-sourced log as their shared memory. When `compound-engine`'s knowledge nodes write to isolated stores instead of a shared bus, the feedback loop breaks. The EDA plan fixes this structurally, not just as a `compound-engine` refactor.

### 2.6 opencode's `permission.asked` event is already HITL — exploit it

Most teams build human-in-the-loop supervision as an external layer. opencode already emits `permission.asked` events natively for every tool invocation that requires approval. This is a production-ready HITL hook. The implementation plan SHOULD route these events through the same event bus as all other agent events rather than treating them as an opencode-internal concern.

### 2.7 In-process async vs. cross-process EDA are two different problems

Python 3.13 `asyncio.TaskGroup` and `asyncio.Queue` handle in-process event-driven concurrency. NATS, Redis Streams, or a SQLite-backed event log handle cross-process, cross-session EDA. The plan must explicitly scope each component to one of these two layers. Confusing them leads to over-engineering (adding Kafka for what a TaskGroup handles) or under-engineering (using a TaskGroup for what needs durability).

---

## 3. The three-layer event model

```
┌─────────────────────────────────────────────────────────┐
│  Layer 3: Durable Event Backbone (cross-process)        │
│  SQLite-backed event log OR Redis Streams               │
│  Scope: sessions, RPIV stage boundaries, HITL events    │
├─────────────────────────────────────────────────────────┤
│  Layer 2: In-Process Async Bus (within a Python process)│
│  asyncio.TaskGroup + asyncio.Queue                      │
│  Scope: parallel tool calls, fan-out within one stage   │
├─────────────────────────────────────────────────────────┤
│  Layer 1: opencode Plugin Event System                  │
│  api.event.on() / plugin hooks                          │
│  Scope: session lifecycle, tool execution, permissions  │
└─────────────────────────────────────────────────────────┘
```

**Rule:** Events flow upward (Layer 1 → 2 → 3) when they need to cross process or session boundaries. They stay local when they don't. An implementation that routes every event to Layer 3 is over-engineered. One that never uses Layer 3 cannot survive process restarts.

---

## 4. Canonical patterns and where they apply

The four patterns from Confluent's canonical EDA literature map directly to RPIV stages.

### 4.1 Orchestrator-Worker — RPIV stage dispatch

The orchestrator emits a `task.assigned` event per eligible RPIV task. Worker agents (Locator, Analyst, Planner, and so on) consume from their named topics and emit `task.completed` or `task.failed` events.

```
Orchestrator
  │ task.assigned{stage=locate, task_id=X}
  ▼
Locator worker
  │ task.completed{stage=locate, task_id=X, artifact=...}
  ▼
[event backbone]
  │
  ▼
Analyst worker (unblocked by completed locate event)
```

This replaces sequential blocking calls with asynchronous fan-out. The dependency graph (Locator must complete before Analyst) is encoded in the Orchestrator's subscription logic, not in each agent's code.

### 4.2 Hierarchical Agent — Implementer spawning subtasks

The Implementer agent uses opencode's `subtask` mechanism to spawn subtask agents per eligible task from `tasks.md`. Each subtask agent is a worker in a temporary hierarchy rooted at the Implementer. Events from subtask agents (`subtask.completed`, `subtask.failed`) flow back to the Implementer via the Layer 2 async bus.

This maps directly to opencode's `subtask: true` command configuration and the `AgentPartInput` / `SubtaskPartInput` SDK types.

### 4.3 Blackboard — shared artifact store as event log

All agents read from and write to a shared artifact store structured as an append-only log. Each write is an event (`artifact.written{agent, stage, path, content_hash}`). No agent polls; all agents subscribe to the artifact event stream.

This directly resolves the `compound-engine` feedback loop deficit. The Analyst, Planner, and Validator read Locator output not by polling a file, but by subscribing to `artifact.written` events from the Locator.

```python
# Every artifact write is an event
class ArtifactWritten(BaseModel):
    event_id: str
    stage: RPIVStage
    agent_id: str
    path: Path
    content_hash: str
    timestamp: datetime
```

### 4.4 Market-Based — Implementer task assignment under concurrency limits

When multiple implementation tasks are eligible simultaneously, the Orchestrator SHOULD NOT blindly fan out all of them. The market-based pattern lets worker agents bid based on context load. In practice for the RPIV pipeline, this is simpler: use a semaphore-bounded task queue. Workers claim tasks from the queue when they have capacity. This prevents LLM API rate limit exhaustion.

```python
semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)

async def claim_task(task: Task) -> None:
    async with semaphore:
        await run_implementer(task)
```

---

## 5. opencode integration points

### 5.1 Plugin hooks as Layer 1 event sources

Every significant agent lifecycle event is observable through the opencode plugin system. The plugin MUST register handlers for these hooks and forward them to the Layer 2 or Layer 3 bus as appropriate.

| opencode hook | Event produced | Destination layer |
|---------------|---------------|------------------|
| `session.created` | `session.started` | Layer 3 (durable) |
| ~~`messageCreated`~~ ⚠️ UNVERIFIED | ~~`message.received`~~ ⚠️ UNVERIFIED | Layer 2 (in-process) — **superseded; use verified `session.created` events only** |
| `tool.execute.after` | `tool.completed` or `tool.failed` | Layer 2 |
| `permission.asked` | `hitl.approval.requested` | Layer 3 (durable — waits for human) |
| `session.compacted` | `context.compacting` | Layer 3 (checkpoint trigger) |

### 5.2 Non-blocking agent dispatch

**[UNVERIFIED]** Earlier non-blocking SDK method and endpoint names in this section were not verified in opencode docs and MUST NOT be used in implementation.

For non-blocking dispatch, use verified `session.prompt` with event-subscription for completion detection, or use opencode commands with `subtask: true` for parallel agent fan-out.

### 5.3 `subtask` configuration for parallelism

opencode's `subtask: true` command flag forces a command to run in a separate session context. This is the mechanism for Implementer subtask fan-out.

```json
{
  "command": {
    "implement-task": {
      "subtask": true
    }
  },
  "agent": {
    "rpiv-orchestrator": {
      "mode": "primary",
      "permission": {
        "task": {
          "*": "deny",
          "rpiv-*": "allow",
          "rpiv-validator": "ask"
        }
      }
    }
  }
}
```

### 5.4 Compaction hook as checkpoint trigger

The `session.compacted` hook fires before opencode compresses the session context. This MUST trigger a checkpoint write to the durable event log. On recovery, agents replay events from the last checkpoint rather than starting cold.

```typescript
// opencode plugin (TypeScript)
export const CheckpointPlugin = async (ctx) => ({
  "session.compacted": async (input, output) => {
    await writeCheckpoint({
      sessionId: input.session.id,
      stage: getCurrentStage(),
      artifactHashes: await getArtifactHashes(),
    })
    output.context.push(`## Checkpoint recorded\nStage: ${getCurrentStage()}`)
  }
})
```

---

## 6. Python 3.13 implementation

### 6.1 In-process async bus (Layer 2)

Python 3.13's `asyncio.TaskGroup` is the correct primitive for parallel stage fan-out. It provides structured concurrency with automatic cleanup on failure.

```python
# agent_runtime/bus.py
import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

type EventHandler[T] = Callable[[T], Coroutine[Any, Any, None]]

class AsyncEventBus:
    """In-process pub/sub bus using asyncio queues.
    
    Scope: within a single Python process. For cross-process events,
    use the DurableEventLog (Layer 3).
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, event_type: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers[event_type].append(q)
        return q

    async def publish(self, event_type: str, payload: Any) -> None:
        for q in self._subscribers.get(event_type, []):
            await q.put(payload)

    async def fan_out[T](
        self,
        tasks: list[T],
        handler: EventHandler[T],
        max_concurrent: int = 4,
    ) -> list[BaseException | None]:
        """Run handler for each task with bounded concurrency."""
        semaphore = asyncio.Semaphore(max_concurrent)
        errors: list[BaseException | None] = []

        async def run(task: T) -> None:
            async with semaphore:
                try:
                    await handler(task)
                except Exception as e:
                    errors.append(e)
                    await self.publish("task.failed", {"task": task, "error": str(e)})

        async with asyncio.TaskGroup() as tg:
            for task in tasks:
                tg.create_task(run(task))

        return errors
```

### 6.2 Event envelope (Pydantic v2)

```python
# agent_runtime/events.py
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class RPIVStage(StrEnum):
    RESEARCH = "research"
    PLAN = "plan"
    IMPLEMENT = "implement"
    VALIDATE = "validate"


class EventSeverity(StrEnum):
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class AgentEvent(BaseModel):
    """Base event envelope. Extends stk's JSON envelope contract."""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str  # namespaced: "task.assigned", "artifact.written", etc.
    produced_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    producer_id: str  # agent name + session ID
    stage: RPIVStage | None = None
    task_id: str | None = None
    severity: EventSeverity = EventSeverity.INFO
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None  # links related events across agents


class TaskAssigned(AgentEvent):
    event_type: Literal["task.assigned"] = "task.assigned"
    assignee_agent: str
    task_description: str
    priority: int = 0


class TaskCompleted(AgentEvent):
    event_type: Literal["task.completed"] = "task.completed"
    artifact_path: str
    content_hash: str
    duration_ms: int


class TaskFailed(AgentEvent):
    event_type: Literal["task.failed"] = "task.failed"
    failure_class: Literal[
        "transient", "context_overflow", "schema_violation",
        "semantic_drift", "circular_delegation", "irreversible_side_effect"
    ]
    error_message: str
    retryable: bool


class HITLApprovalRequested(AgentEvent):
    event_type: Literal["hitl.approval.requested"] = "hitl.approval.requested"
    opencode_permission_id: str
    tool_name: str
    tool_args: dict[str, Any]


class ArtifactWritten(AgentEvent):
    event_type: Literal["artifact.written"] = "artifact.written"
    path: str
    content_hash: str
    stage: RPIVStage
```

### 6.3 Durable event log (Layer 3, SQLite-backed)

For local development and CI, SQLite is sufficient as the durable backbone. It supports append-only writes, replay by `sequence_id`, and checkpoint-based recovery.

```python
# agent_runtime/event_log.py
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from agent_runtime.events import AgentEvent


class DurableEventLog:
    """Append-only event log backed by SQLite.
    
    Use for cross-session events, HITL events, and checkpoint triggers.
    Replace with Redis Streams for multi-machine deployments.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    sequence_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id      TEXT NOT NULL UNIQUE,
                    event_type    TEXT NOT NULL,
                    produced_at   TEXT NOT NULL,
                    producer_id   TEXT NOT NULL,
                    stage         TEXT,
                    task_id       TEXT,
                    correlation_id TEXT,
                    payload       TEXT NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_event_type ON events(event_type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_task_id ON events(task_id)"
            )

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def append(self, event: AgentEvent) -> int:
        """Append an event. Returns the sequence_id."""
        with self._conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO events
                    (event_id, event_type, produced_at, producer_id,
                     stage, task_id, correlation_id, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.event_type,
                    event.produced_at.isoformat(),
                    event.producer_id,
                    event.stage,
                    event.task_id,
                    event.correlation_id,
                    event.payload_json(),
                ),
            )
        return cursor.lastrowid

    def replay(
        self,
        from_sequence: int = 0,
        event_types: list[str] | None = None,
    ) -> list[dict]:
        """Replay events from a sequence ID, optionally filtered by type."""
        with self._conn() as conn:
            if event_types:
                placeholders = ",".join("?" * len(event_types))
                rows = conn.execute(
                    f"""
                    SELECT * FROM events
                    WHERE sequence_id > ?
                      AND event_type IN ({placeholders})
                    ORDER BY sequence_id ASC
                    """,
                    [from_sequence, *event_types],
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM events WHERE sequence_id > ? ORDER BY sequence_id ASC",
                    [from_sequence],
                ).fetchall()
        return [dict(row) for row in rows]

    def last_checkpoint(self, task_id: str) -> dict | None:
        """Find the most recent checkpoint event for a task."""
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM events
                WHERE task_id = ? AND event_type = 'session.checkpoint'
                ORDER BY sequence_id DESC LIMIT 1
                """,
                [task_id],
            ).fetchone()
        return dict(row) if row else None
```

### 6.4 Side-effect idempotency guard

```python
# agent_runtime/idempotency.py
import hashlib
from pathlib import Path
from collections.abc import Callable, Coroutine
from typing import Any

from agent_runtime.event_log import DurableEventLog


class IdempotencyGuard:
    """Ensures side effects execute at most once per (task_id, action_type, content_hash)."""

    def __init__(self, log: DurableEventLog) -> None:
        self._log = log

    def _key(self, task_id: str, action_type: str, content: str) -> str:
        raw = f"{task_id}:{action_type}:{content}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    async def execute_once(
        self,
        task_id: str,
        action_type: str,
        content: str,
        effect: Callable[[], Coroutine[Any, Any, Any]],
    ) -> Any:
        """Execute effect only if not already recorded for this key."""
        key = self._key(task_id, action_type, content)
        existing = self._log.replay(event_types=[f"effect.executed:{key}"])
        if existing:
            return None  # already executed; skip

        result = await effect()
        # Record the execution AFTER success
        from agent_runtime.events import AgentEvent
        self._log.append(
            AgentEvent(
                event_type=f"effect.executed:{key}",
                producer_id="idempotency-guard",
                task_id=task_id,
                payload={"action_type": action_type, "result": str(result)},
            )
        )
        return result
```

---

## 7. The event envelope schema

The canonical event envelope extends the existing `stk` JSON envelope schema. This avoids a second schema proliferation.

```
stk envelope
  └── event_id         (new: UUID, replaces numeric stk message ID)
  └── event_type       (new: namespaced string, "task.assigned")
  └── produced_at      (new: ISO 8601 UTC timestamp)
  └── producer_id      (maps to stk's `agent` field)
  └── stage            (new: RPIVStage enum)
  └── task_id          (maps to stk's `pr_id` or `task_id`)
  └── correlation_id   (new: links related events across agents)
  └── severity         (new: info | warn | error)
  └── payload          (maps to stk's `data` body)
```

All agents MUST produce events conforming to this envelope. Agents MAY extend the envelope with typed subtypes (see `TaskAssigned`, `TaskCompleted`, and so on in section 6.2).

---

## 8. Operational concerns

### 8.1 Dead-letter queue taxonomy

The DLQ MUST route by failure class, not by a flat retry-or-discard policy.

| Failure class | Routing rule | Max retries |
|---------------|-------------|-------------|
| `transient` | Retry with exponential backoff (base 2 s, max 60 s) | 5 |
| `context_overflow` | Trigger compaction, then retry | 2 |
| `schema_violation` | Route to Validator critic agent | 1 |
| `semantic_drift` | Route to HITL approval queue | 0 (no auto-retry) |
| `circular_delegation` | Halt; alert; never retry | 0 |
| `irreversible_side_effect` | Halt; alert; never retry | 0 |

### 8.2 Backpressure

The in-process bus MUST respect token budget and LLM API rate limits. Apply these controls in order:

1. Semaphore-bounded `fan_out` (section 6.1): cap concurrent LLM calls to `MAX_CONCURRENT_LLM_CALLS` (RECOMMENDED default: 3 for Anthropic API).
2. Queue depth monitoring: if Layer 2 queue depth exceeds `HIGH_WATERMARK` (RECOMMENDED: 20 items), pause new task dispatch until depth falls below `LOW_WATERMARK` (RECOMMENDED: 5 items).
3. Token bucket: track estimated token consumption per minute; pause dispatch when approaching the API rate limit.

### 8.3 Observability

Every event MUST include a `correlation_id` that links all events in a single RPIV run. This enables end-to-end traces without a distributed tracing system.

OpenTelemetry GenAI semantic conventions SHOULD be applied to all LLM call spans. The event log's `sequence_id` SHOULD be attached as the `gen_ai.conversation.id` attribute.

### 8.4 Event replay for debugging

LLM non-determinism makes reproduction of bugs difficult. The durable event log solves this: replay events from the last checkpoint to reconstruct the pipeline state at any point in time.

```python
# Replay an RPIV run from the Planner stage forward
events = log.replay(
    from_sequence=planner_checkpoint_sequence,
    event_types=["task.assigned", "task.completed", "artifact.written"],
)
```

---

## 8a. TypeScript–Python bridge specification

The opencode plugin system is TypeScript; the orchestrator is Python. The bridge MUST use a local HTTP server on the Python side, not file-based inter-process communication.

### HTTP receiver (Python)

```python
# agent_runtime/bridge.py
from __future__ import annotations

import asyncio
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

from agent_runtime.bus import AsyncEventBus
from agent_runtime.events import AgentEvent


class PluginBridgeServer:
    """Receives events forwarded from the opencode TypeScript plugin over HTTP."""

    PORT = 4097  # opencode server is on 4096; we take 4097

    def __init__(self, bus: AsyncEventBus) -> None:
        self._bus = bus
        self._loop = asyncio.get_event_loop()

    def start(self) -> None:
        bus = self._bus
        loop = self._loop

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                event = AgentEvent.model_validate(json.loads(body))
                asyncio.run_coroutine_threadsafe(
                    bus.publish(event.event_type, event), loop
                )
                self.send_response(204)
                self.end_headers()

            def log_message(self, *_):
                pass  # suppress default HTTP logging

        server = HTTPServer(("127.0.0.1", self.PORT), Handler)
        Thread(target=server.serve_forever, daemon=True).start()
```

### TypeScript plugin forwarder

```typescript
// opencode-plugin/index.ts
import type { Plugin } from "@opencode-ai/plugin"

const BRIDGE_URL = "http://127.0.0.1:4097"

async function forward(event: object): Promise<void> {
  await fetch(BRIDGE_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(event),
  }).catch(() => {/* orchestrator not running; swallow */})
}

export const BridgePlugin: Plugin = async ({ project }) => ({
  async event({ event }) {
    if (event.type === "session.created") {
      await forward({ event_type: "session.started", producer_id: event.sessionId,
                      payload: { project_id: project.id } })
    }
    if (event.type === "tool.execute.after") {
      await forward({ event_type: "tool.completed", producer_id: event.sessionId,
                      payload: { name: event.toolName, result: event.result } })
    }
    if (event.type === "permission.asked") {
      await forward({ event_type: "hitl.approval.requested",
                      producer_id: "opencode",
                      payload: { opencode_permission_id: event.properties.id } })
    }
  },
})
```

**Security note:** The bridge MUST bind to `127.0.0.1` only. It MUST NOT bind to `0.0.0.0`. No authentication is required for localhost-only communication on a developer machine, but SHOULD be added for multi-user or CI environments.

---

## 9. Phased implementation plan

### Phase 0 — Prerequisites (1–2 days)

- [ ] Audit `stk` envelope schema; document extension points for `event_id`, `event_type`, `stage`, and `correlation_id`.
- [ ] Confirm opencode SDK version supports verified event hooks and `client.event.subscribe()`.
- [ ] Create `agent_runtime/` package skeleton with `uv init`.
- [ ] Write Pydantic v2 event models (`AgentEvent` and typed subtypes).

**Exit criterion:** `AgentEvent` and all subtype models pass `mypy --strict` and have 100% test coverage.

### Phase 1 — Layer 1 integration: opencode plugin hooks (2–3 days)

- [ ] Implement opencode plugin in TypeScript that forwards `session.created`, `tool.execute.after`, `permission.asked`, and `session.compacted` hooks to a local HTTP endpoint on the Python orchestrator.
- [ ] Implement the Python HTTP receiver that deserialises incoming hooks into `AgentEvent` instances and publishes them to the Layer 2 async bus.
- [ ] Wire `permission.asked` hook to the HITL approval queue (Layer 3).

**Exit criterion:** A test session in opencode produces observable events on the Python bus.

### Phase 2 — Layer 2 async bus and fan-out (3–4 days)

- [ ] Implement `AsyncEventBus` with `subscribe` and `publish`.
- [ ] Implement `fan_out` with semaphore-bounded concurrency.
- [ ] Replace blocking `prompt` calls in the RPIV Implementer with verified non-blocking patterns and event-subscription completion detection.
- [ ] Add DLQ routing table; implement per-failure-class handlers.

**Exit criterion:** The Implementer can dispatch three concurrent subtasks and handle one simulated `schema_violation` failure by routing it to the Validator critic.

### Phase 3 — Layer 3 durable event log and checkpointing (2–3 days)

- [ ] Implement `DurableEventLog` (SQLite).
- [ ] Implement checkpoint write on `session.compacted`.
- [ ] Implement checkpoint-based recovery: on orchestrator restart, replay from last checkpoint.
- [ ] Implement `IdempotencyGuard` for git operations and file writes.

**Exit criterion:** Kill the orchestrator mid-run and restart; the pipeline resumes from the last checkpoint without re-executing completed stages.

### Phase 4 — Blackboard pattern for artifact sharing (2–3 days)

- [ ] Replace file-polling between RPIV stages with `artifact.written` event subscriptions.
- [ ] Apply this fix to `compound-engine` specifically: Analyst and Planner subscribe to Locator's `artifact.written` events rather than reading from an isolated knowledge store.
- [ ] Add content-hash-based deduplication: an agent that receives an `artifact.written` event MUST NOT re-read if the hash matches its cached version.

**Exit criterion:** `compound-engine`'s feedback loop test passes; knowledge propagation is observable in the event log.

### Phase 5 — Observability and operational tooling (2–3 days)

- [ ] Add `correlation_id` threading through all events.
- [ ] Build a minimal CLI command (`stk events replay --task-id X`) that replays the event log for a given task. Output format:

  ```json
  {
    "task_id": "task-abc123",
    "events": [
      { "seq": 1, "event_type": "task.assigned", "producer_id": "orchestrator",
        "stage": "research", "produced_at": "2026-05-11T14:00:00Z" },
      { "seq": 4, "event_type": "artifact.written", "producer_id": "rpiv-locator",
        "stage": "research", "produced_at": "2026-05-11T14:00:47Z",
        "payload": { "path": "research/locator-output.md", "content_hash": "a3f..." } },
      { "seq": 7, "event_type": "task.failed", "producer_id": "rpiv-implementer",
        "stage": "implement", "produced_at": "2026-05-11T14:03:12Z",
        "payload": { "failure_class": "schema_violation", "retryable": true } }
    ]
  }
  ```
- [ ] Add queue depth monitoring and backpressure enforcement.
- [ ] Write runbook for DLQ triage: how to inspect, classify, and re-route failed events.

**Exit criterion:** A simulated pipeline failure can be diagnosed entirely from the event log without querying agent session histories.

---

## 10. Architecture decision records

### ADR-0001: SQLite as the initial durable event backbone

**Status:** Proposed

**Context:** The pipeline runs on a single developer machine (blazar self-hosted runner). Cross-machine distribution is not required in the near term. Kafka adds operational complexity (JVM, broker management) that is disproportionate to the current scale.

**Decision:** Use SQLite as the Layer 3 durable event backbone. The `DurableEventLog` class encapsulates all SQLite access behind an interface that can be swapped for Redis Streams or Kafka without changing consumer code.

**Consequences:** Positive: zero infrastructure dependencies; fast local development. Negative: no horizontal scaling beyond a single machine; schema migrations require care. Neutral: when multi-machine deployment becomes necessary, replace the `DurableEventLog` implementation (not its interface) with Redis Streams.

---

### ADR-0002: Extend stk envelope as the canonical event schema

**Status:** Proposed

**Context:** A new event schema would create a second contract that agents must learn and that tooling must support. The `stk` CLI already has a stable JSON envelope used across the pipeline.

**Decision:** Extend the `stk` envelope with `event_id`, `event_type`, `stage`, `correlation_id`, and `severity` fields. All new event types MUST be subtypes of `AgentEvent` in `agent_runtime/events.py`.

**Consequences:** Positive: one schema, not two; `stk events` commands have a natural home. Negative: `stk` must accept schema version negotiation as the envelope evolves. Neutral: existing `stk` consumers ignore unknown fields by default (JSON forward-compatibility).

---

### ADR-0003: In-process async bus for intra-stage events; durable log for inter-stage events

**Status:** Proposed

**Context:** Routing every event through the durable log adds latency and I/O for events that never need to cross a process boundary (for example, individual tool call completions within a single Implementer session).

**Decision:** Events that cross stage boundaries or require human-in-the-loop approval MUST go through the durable event log (Layer 3). Events that stay within a single stage's Python process SHOULD use the `AsyncEventBus` (Layer 2). Events native to opencode's own lifecycle SHOULD be handled by the plugin system (Layer 1) and forwarded to Layer 2 or 3 as appropriate.

**Consequences:** Positive: minimizes I/O; keeps local events fast. Negative: requires developers to consciously decide which layer an event belongs to. Neutral: the `AgentEvent` envelope is valid at all three layers; the routing decision is in the publisher, not the schema.

---

### ADR-0004: At-most-once semantics for irreversible side effects

**Status:** Proposed

**Context:** LLM non-determinism means retrying a failed operation may produce a different (and possibly conflicting) result. Git pushes, file writes to shared paths, and external API calls are irreversible or expensive to undo.

**Decision:** All side effects classified as `irreversible_side_effect` MUST use the `IdempotencyGuard.execute_once` pattern. These events MUST NOT be retried. On failure, they MUST be routed to the HITL approval queue for manual resolution.

**Consequences:** Positive: prevents duplicate git commits, double API calls, and conflicting file writes. Negative: any failure in an irreversible side effect requires manual intervention. Neutral: the vast majority of agent operations (research, planning, analysis) are reads and do not trigger this guard.

---

---

# Amendment A — MiniMax M2.7 Model Integration

**Amendment status:** Proposed  
**Supersedes:** None (additive amendment to sections 5, 8, 9, and 10)  
**Research basis:** Artificial Analysis Intelligence Index (March 2026), MiniMax official blog (May 2026), Kilo.ai head-to-head evaluation (March 2026), AwesomeAgents.ai review (May 2026)

This amendment adjusts the EDA plan to account for MiniMax M2.7 as the primary model in the opencode harness. It specifies where M2.7's strengths should be exploited, where its weaknesses require mitigation or escalation to Claude, and how M2.7's native self-evolution capability can be structurally wired into the harness itself.

---

## A1. M2.7 strengths and weaknesses in the RPIV context

### Confirmed strengths

| Strength | Evidence | RPIV stage benefiting most |
|----------|----------|---------------------------|
| SWE-bench Verified: 78% — leads all public models | Artificial Analysis, March 2026 | Implement (PR-sized patches) |
| SWE-Pro: 56.22% — within 1 point of Claude Opus 4.6 | MiniMax official benchmarks | Implement (multi-file, multi-step) |
| Hallucination rate: 34% — lower than Claude Sonnet 4.6 (46%) | Artificial Analysis AA-Omniscience | Research / Locator, Analyst |
| GDPval-AA ELO 1495 — highest among open-weight models | Artificial Analysis | Plan (document/artifact processing) |
| 97% skill adherence across 40+ complex skills >2,000 tokens | MiniMax MM Claw benchmark | All stages; directly maps to RPIV skill files |
| MLE Bench Lite 66.6% medal rate | MiniMax self-evolution evaluation | Validate (ML experiment scoring) |
| Native Agent Teams with stable role identity | MiniMax model card | Orchestrator coordination |
| Terminal Bench 2: 57.0% — strong shell/SRE reasoning | MiniMax official benchmarks | Implement (debugging, log analysis) |
| SRE-level incident recovery under 3 minutes | MiniMax production report | Implement / incident response |
| $0.30/$1.20 per million tokens — ~17x cheaper than Claude Opus 4.6 | Artificial Analysis pricing | All stages; enables aggressive parallelism |
| Self-evolution: 30% improvement in 100+ autonomous rounds | MiniMax official blog | Harness improvement (see §A4) |

### Confirmed weaknesses

| Weakness | Evidence | RPIV impact | Mitigation |
|----------|----------|-------------|-----------|
| τ²-Bench regression: −11 p.p. from M2.5 | Artificial Analysis | Multi-turn tool coordination in Locator | Route Locator to Claude |
| NL2Repo: 39.8% | Artificial Analysis | Planner stage: new codebase decomposition | Escalate ambiguous repo-structure tasks |
| Terminal Bench 2: 57.0% vs GPT-5.4's 75.1% | Serenities AI | Shell agent tasks in Implement | Compensate with richer tool schemas |
| 3.3x output verbosity (87M tokens vs 26M median) | Artificial Analysis | Context overflow, high token cost | Aggressive compaction; `prune: true` |
| 47 t/s, 2.91s TTFT | Artificial Analysis | Interactive / inline latency unusable | Use verified non-blocking dispatch; never block |
| No multimodal | All sources | Validator can't diff images/design specs | Route visual tasks to Claude or separate tool |
| BridgeBench regression (12th → 19th) | Artificial Analysis | Cross-service integration work | Test integration tasks against Claude first |
| "Modified-MIT" license — commercial use restricted | Multiple sources | Production commercial deployment risk | Internal / non-commercial use is fine; review before productizing |
| "Picks an interpretation and runs" vs. asking for clarification | Kilo.ai evaluation | Ambiguous requirements in Planner | Add explicit clarification gate before Planner starts |
| Reasoning-only model: longer chain-of-thought token budget | Botmonster review | Context window pressure at 204.8K | Set `reserved: 15000`; enable auto-compaction |

### The key asymmetry to exploit

Kilo.ai's head-to-head testing (March 2026) established that M2.7 delivers 90% of Claude Opus 4.6's code quality at 7% of the cost. The quality gap materializes in two specific areas:

1. **Test coverage depth** — M2.7 writes unit tests; Claude Opus writes integration tests that cover middleware and routing.
2. **Security fix completeness** — M2.7 closes vulnerabilities with simpler approaches and sometimes flags its own shortcuts. Claude Opus applies defense-in-depth.

Both gaps sit in the **Validate** stage. The correct architecture is: M2.7 as the primary agent for Research, Plan, and Implement; Claude for the Validator critic and for ambiguous Planner inputs. This is the route-and-escalate pattern.

---

## A2. Stage-to-model routing table

```
RPIV Stage       Primary Model    Escalation Trigger              Escalation Model
─────────────────────────────────────────────────────────────────────────────────
Research/Locator Claude*          Always (τ²-Bench regression)    —
Research/Analyst M2.7             Hallucination rate on niche      Claude
                                  specialist facts
Plan             M2.7             Ambiguous requirements;          Claude
                                  NL2Repo failure detected
Implement        M2.7             —                                Claude (rollback logic)
Validate         Claude           Always (integration tests,       —
                                  security depth, visual diff)
Compaction       M2.7             —                                —
Self-evolution   M2.7             —                                —
```

*Locator is the heaviest MCP tool user. M2.7's τ²-Bench regression (multi-turn tool coordination) is a direct liability here. Locator SHOULD use Claude by default until M2.7's tool-chaining on Locator-style workloads is independently validated.

---

## A3. Mitigating M2.7 weaknesses in opencode

### A3.1 Verbosity — aggressive compaction

M2.7 produces 3.3x more output tokens than the peer-model median. Without mitigation, a reasoning-heavy Implementer session will exhaust the 204.8K context window mid-task. The opencode configuration MUST set:

```json
{
  "compaction": {
    "auto": true,
    "prune": true,
    "reserved": 15000
  }
}
```

`reserved: 15000` gives the compaction agent enough headroom to run before M2.7's reasoning chain overflows the window. The default of `10000` is insufficient for a reasoning-only model generating 3.3x tokens.

### A3.2 Latency — non-blocking dispatch everywhere

M2.7's 2.91s TTFT rules out any synchronous, blocking prompt pattern. Use verified non-blocking dispatch patterns (see section 5.2) for all inter-agent calls. Implementation MUST use verified opencode APIs only.

### A3.3 Context creep — prune tool outputs

M2.7 traces call chains extensively before generating output. This is a strength on hard tasks but a liability for token budget. Enable `prune: true` to discard old tool outputs from context. The event log (Layer 3) retains the full record; the active context window should hold only the current task's artifacts.

### A3.4 Ambiguous requirements — clarification gate

M2.7 is observed to "pick an interpretation and run" rather than surface ambiguity. Insert an explicit clarification gate between Research and Plan stages. The gate is a simple structured prompt that M2.7 runs before the Planner starts:

```python
CLARIFICATION_PROMPT = """
You are about to begin the Plan stage. Before planning:
1. List every requirement in the spec that is ambiguous, underspecified, or contradictory.
2. For each: state your intended interpretation.
3. If ANY interpretation involves an irreversible architectural choice, emit a HITL event and STOP.
4. If all interpretations are reversible, proceed.

Format your response as a JSON object: {"ambiguities": [...], "interpretations": [...], "hitl_required": bool}
"""
```

If `hitl_required` is `true`, the orchestrator emits a `hitl.approval.requested` event and pauses until the human confirms the interpretation.

### A3.5 No multimodal — visual task routing

The Validator stage MUST NOT attempt to process design mockups, screenshots, or visual diffs through M2.7. Route any visual artifact to a separate Claude call with image input. The event schema already supports this: `TaskAssigned` includes an `assignee_agent` field; set it to `claude-validator-visual` for visual-diff tasks.

---

## A4. Wiring M2.7 self-evolution into the harness

This is the plan's highest-value integration point and the most architecturally novel.

### How M2.7's self-evolution works (from MiniMax's own documentation)

MiniMax built a three-component harness that M2.7 ran inside during its own training:

1. **Short-term memory** — after each iteration, the agent writes a markdown file recording what it tried, what failed, and what worked.
2. **Self-criticism** — the agent evaluates its own output against the task objective and generates "optimization directions" for the next round.
3. **Self-optimization** — the next iteration starts from the memory + self-criticism chain of all prior rounds.

The model ran 100+ iterations of `analyze failure trajectories → plan changes → modify scaffold code → run evaluations → keep or revert`, achieving a 30% performance improvement with no human intervention.

### The structural insight: opencode's compaction hook IS the memory write

The `session.compacted` hook fires every time M2.7's context approaches the window limit. This is structurally equivalent to the "end of iteration" event in M2.7's self-evolution loop. The plan already uses this hook for checkpoint writes (section 5.4). The amendment extends it to also write a **skill evolution log** in M2.7's native format.

```
Each compaction event → one iteration of the self-evolution loop
Compaction summary    → short-term memory markdown
Self-criticism block  → structured self-evaluation injected into compaction context
Optimization note     → written to skill evolution log → picked up by next session
```

This is not a metaphor. It is a direct structural match between opencode's compaction lifecycle and M2.7's self-evolution architecture.

---

## A5. Self-evolution feedback loop implementation

### A5.1 Skill evolution log

```python
# agent_runtime/evolution.py
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field


class IterationMemory(BaseModel):
    """One round of M2.7-style self-evolution memory."""
    iteration: int
    stage: str
    task_id: str
    what_was_tried: str
    what_failed: str
    what_worked: str
    optimization_directions: list[str]
    skill_files_modified: list[str] = Field(default_factory=list)
    recorded_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )


class SkillEvolutionLog:
    """Append-only log of self-evolution iterations per skill/stage.
    
    Written after each compaction event. Read at the start of each new session
    to prime M2.7 with prior iteration context before it begins work.
    """

    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, skill_name: str) -> Path:
        return self.log_dir / f"{skill_name}-evolution.jsonl"

    def record(self, skill_name: str, memory: IterationMemory) -> None:
        with self._path(skill_name).open("a") as f:
            f.write(memory.model_dump_json() + "\n")

    def last_n(self, skill_name: str, n: int = 5) -> list[IterationMemory]:
        path = self._path(skill_name)
        if not path.exists():
            return []
        lines = path.read_text().strip().splitlines()
        return [
            IterationMemory.model_validate(json.loads(line))
            for line in lines[-n:]
        ]

    def as_context_block(self, skill_name: str, n: int = 5) -> str:
        """Render the last N iterations as a markdown context block
        for injection into the next session's compaction prompt."""
        memories = self.last_n(skill_name, n)
        if not memories:
            return ""
        lines = [f"## Self-evolution history: {skill_name} (last {len(memories)} iterations)\n"]
        for m in memories:
            lines.append(f"### Iteration {m.iteration} — {m.stage} stage")
            lines.append(f"- **Tried:** {m.what_was_tried}")
            lines.append(f"- **Failed:** {m.what_failed}")
            lines.append(f"- **Worked:** {m.what_worked}")
            lines.append(f"- **Next directions:** {'; '.join(m.optimization_directions)}")
            if m.skill_files_modified:
                lines.append(f"- **Skills modified:** {', '.join(m.skill_files_modified)}")
            lines.append("")
        return "\n".join(lines)
```

### A5.2 Enhanced compaction plugin with self-evolution injection

```typescript
// opencode-plugin/evolution-compaction.ts
import type { Plugin } from "@opencode-ai/plugin"
import * as fs from "fs"
import * as path from "path"

const EVOLUTION_LOG_DIR = ".agent-runtime/evolution"
const BRIDGE_URL = "http://127.0.0.1:4097"

interface IterationMemory {
  iteration: number
  stage: string
  task_id: string
  what_was_tried: string
  what_failed: string
  what_worked: string
  optimization_directions: string[]
  skill_files_modified: string[]
  recorded_at: string
}

function loadEvolutionContext(skillName: string, n = 5): string {
  const logPath = path.join(EVOLUTION_LOG_DIR, `${skillName}-evolution.jsonl`)
  if (!fs.existsSync(logPath)) return ""
  const lines = fs.readFileSync(logPath, "utf-8").trim().split("\n").slice(-n)
  const memories: IterationMemory[] = lines.map(l => JSON.parse(l))
  if (!memories.length) return ""
  const blocks = memories.map(m =>
    `### Iteration ${m.iteration} — ${m.stage} stage\n` +
    `- Tried: ${m.what_was_tried}\n` +
    `- Failed: ${m.what_failed}\n` +
    `- Worked: ${m.what_worked}\n` +
    `- Next: ${m.optimization_directions.join("; ")}`
  )
  return `## Self-evolution history (last ${memories.length} iterations)\n${blocks.join("\n\n")}`
}

export const EvolutionCompactionPlugin: Plugin = async ({ project }) => ({
  "session.compacted": async (input, output) => {
    // 1. Inject prior evolution history into the compaction context
    // so M2.7 carries forward what it learned in prior sessions.
    const skillName = (input as any).agent ?? "rpiv-implementer"
    const evolutionContext = loadEvolutionContext(skillName)
    if (evolutionContext) {
      output.context.push(evolutionContext)
    }

    // 2. Replace default compaction prompt with M2.7 self-evolution format.
    // This instructs M2.7 to produce a self-criticism block as part of its
    // compaction summary — the same structure M2.7 used during its own training.
    output.prompt = `
You are generating a continuation prompt for an RPIV agent session.

## Instructions

Produce a structured compaction summary in EXACTLY this format:

### Current task and status
[What the task is; what stage it is in; what has been completed]

### Files actively being modified
[List of file paths and what change is in progress]

### Blockers and dependencies
[Any blocked sub-tasks; which tasks are waiting on which]

### Self-criticism
[Honest evaluation of this session's performance:
 - What approach was taken and why
 - What failed or was slower than expected
 - What worked well
 - Specific optimization directions for the next session]

### Optimization directions for next session
[Numbered list of concrete changes to try next time]

### Next steps
[Ordered list of the immediate next actions when the session resumes]

This summary MUST be structured so a new M2.7 agent session can resume
the task without re-reading the full prior context.
`

    // 3. Forward a compaction event to the Python orchestrator so it can
    // record an IterationMemory entry in the SkillEvolutionLog.
    await fetch(BRIDGE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_type: "session.compacting",
        producer_id: (input as any).session?.id ?? "unknown",
        payload: { agent: skillName, project_id: project.id }
      })
    }).catch(() => {})
  }
})
```

### A5.3 Orchestrator: parse compaction output and record iteration memory

```python
# agent_runtime/evolution_recorder.py
import re
from agent_runtime.evolution import IterationMemory, SkillEvolutionLog


def parse_compaction_summary(
    summary_text: str,
    stage: str,
    task_id: str,
    iteration: int,
) -> IterationMemory:
    """Parse M2.7's structured compaction output into an IterationMemory.
    
    M2.7 reliably produces the structured format when given the evolution
    compaction prompt. Parse defensively — missing sections default to empty.
    """
    def extract(header: str) -> str:
        pattern = rf"### {re.escape(header)}\n(.*?)(?=\n###|\Z)"
        match = re.search(pattern, summary_text, re.DOTALL)
        return match.group(1).strip() if match else ""

    def extract_list(header: str) -> list[str]:
        block = extract(header)
        return [
            line.lstrip("0123456789.-• ").strip()
            for line in block.splitlines()
            if line.strip()
        ]

    criticism = extract("Self-criticism")
    # Parse self-criticism sub-sections
    tried = re.search(r"- What approach.*?:\s*(.+)", criticism)
    failed = re.search(r"- What failed.*?:\s*(.+)", criticism)
    worked = re.search(r"- What worked.*?:\s*(.+)", criticism)

    return IterationMemory(
        iteration=iteration,
        stage=stage,
        task_id=task_id,
        what_was_tried=tried.group(1) if tried else criticism[:200],
        what_failed=failed.group(1) if failed else "",
        what_worked=worked.group(1) if worked else "",
        optimization_directions=extract_list("Optimization directions for next session"),
        skill_files_modified=[],  # populated by the Implementer via artifact.written events
    )
```

### A5.4 Closing the loop: skill file self-modification

The highest-fidelity expression of M2.7's self-evolution capability is allowing it to modify its own skill files between sessions. This maps directly to what M2.7 did during its own training: it modified its own scaffold code based on failure analysis.

In the opencode harness, the skill files live in `.opencode/skills/`. The self-evolution loop's "modify scaffold" step becomes:

```
1. Orchestrator reads last N IterationMemory entries for the active skill.
2. Orchestrator prompts M2.7 with: "Given this evolution history, propose
   specific edits to the skill file at .opencode/skills/rpiv-implementer/SKILL.md
   that would improve performance. Output a unified diff."
3. Orchestrator validates the diff (MUST NOT modify security-critical sections;
   MUST pass a human review gate for diffs >50 lines).
4. Orchestrator applies the diff via the IdempotencyGuard.
5. The modification is recorded as an ArtifactWritten event with
   content_hash so future sessions can detect if the skill regressed.
```

This is self-modification with guardrails — not unconstrained rewriting. The human review gate for large diffs is the critical safety control.

---

## A6. opencode configuration for M2.7

**[SUPERSEDED]** This section is superseded by `specs/event-driven-agent-runtime-plan.md`. The authoritative MiniMax direct provider configuration is documented there.

For reference, the old OpenRouter MiniMax slug has been removed. MiniMax M2.7 uses the direct Token Plan API via the `@ai-sdk/openai-compatible` provider with base URL `https://api.minimax.io/v1` and model ID `MiniMax-M2.7`.

---

## A7. Updated phased plan — M2.7 integration tasks

These tasks MUST be inserted into the existing phases. They are additive — they don't replace existing tasks.

### Phase 0 additions

- [ ] Confirm M2.7 availability via MiniMax direct Token Plan API (`MiniMax-M2.7`); verify `MINIMAX_API_KEY` and rate limits.
- [ ] Run Kilo.ai's three-task benchmark (bug debug, security review, greenfield build) on M2.7 against a real RPIV task to establish a project-specific quality baseline before relying on published benchmarks.
- [ ] Review MiniMax "Modified-MIT" license terms against the intended use case. Confirm non-commercial / internal use is within scope.

### Phase 1 additions

- [ ] Set per-agent model in `opencode.jsonc` per the routing table in §A2.
- [ ] Install the `EvolutionCompactionPlugin` alongside the existing `BridgePlugin`.
- [ ] Set `compaction.reserved: 15000` and `compaction.prune: true`.

### Phase 2 additions

- [ ] Add the clarification gate prompt (§A3.4) as a mandatory step between Research completion and Plan start.
- [ ] Add failure class `context_overflow` detection: parse M2.7 error responses for context-length signals and route to compaction before retrying.

### Phase 3 additions

- [ ] Implement `SkillEvolutionLog` (§A5.1) as part of the `agent_runtime` package.
- [ ] Wire the `session.compacting` event from the bridge to the `parse_compaction_summary` parser (§A5.3) and `SkillEvolutionLog.record()`.
- [ ] Verify that the evolution log accumulates across multiple sessions for a single task.

### New Phase 6 — Self-evolution harness (3–4 days)

- [ ] Implement the `evolve-skill` command: after the `SkillEvolutionLog` accumulates ≥3 `IterationMemory` entries for a given skill (configurable threshold), the orchestrator automatically triggers `evolve-skill` for that skill. The orchestrator reads the last 10 entries and prompts M2.7 to propose a skill file diff.
- [ ] Add the HITL gate for skill diffs >50 lines: emit `hitl.approval.requested`; wait for human approval before applying.
- [ ] Apply the skill diff via `IdempotencyGuard.execute_once` with `action_type="skill.modified"`.
- [ ] Record the skill modification as an `ArtifactWritten` event with `content_hash`.
- [ ] Add a regression detection check: if the next session's performance on a canary task drops below the prior checkpoint, revert the skill modification using the event log's content hash.

**Exit criterion for Phase 6:** M2.7 proposes and applies at least one valid improvement to the `rpiv-implementer` skill file based on iteration memory, the improvement is observable in the evolution log, and a simulated regression triggers an automatic revert.

---

## A8. Additional ADRs

### ADR-0005: MiniMax M2.7 as primary model with Claude as Validator and Locator

**Status:** Proposed

**Context:** The team evaluated M2.7 against Claude Sonnet 4.6 and Claude Opus 4.6 for the RPIV pipeline. M2.7 delivers SWE-bench Verified at 78% (versus Claude Opus 4.6 at 55%), hallucinations at 34% (versus Claude Sonnet 4.6 at 46%), and a price of $0.30/$1.20 per million tokens (versus Claude Opus 4.6 at $5/$25). However, M2.7 has documented regressions in multi-turn tool coordination (τ²-Bench) and produces 3.3x more output tokens than the peer-model median. Claude outperforms M2.7 on integration test depth, security fix completeness, and any visual or multimodal task.

**Decision:** M2.7 is the primary model for Analyst, Plan, Implement, and Orchestrator stages. Claude (Sonnet 4.6) is the primary model for Locator (τ²-Bench liability) and Validator (integration test depth, security review, visual diff). This route-and-escalate pattern is the same used in production by the WaveSpeed evaluation team.

**Consequences:** Positive: 90% quality at ~7% cost for the majority of pipeline stages; M2.7's 97% skill adherence makes the skill file system reliable; lower hallucination rate improves Research stage fidelity. Negative: two models means two API keys, two rate limit budgets, and two cost centers to track. Neutral: the `assignee_agent` field in `TaskAssigned` events makes model routing explicit and changeable without touching business logic.

---

### ADR-0006: opencode compaction hook as the self-evolution iteration boundary

**Status:** Proposed

**Context:** M2.7's self-evolution mechanism uses a three-component harness: short-term memory (markdown file written after each iteration), self-criticism (structured self-evaluation), and self-optimization (next iteration reads prior memory chain). MiniMax ran this for 100+ iterations within a 24-hour window to achieve a 30% performance improvement. opencode fires `session.compacted` each time M2.7's context approaches the window limit. These events are structurally equivalent: both mark the boundary of one "iteration" and the beginning of the next.

**Decision:** Treat each `session.compacted` event as one iteration of M2.7's self-evolution loop. The compaction plugin MUST produce a structured compaction summary in M2.7's self-evolution format (§A5.2). The orchestrator MUST parse this summary and append it to the `SkillEvolutionLog`. The next session MUST receive the last N iterations as context before starting work.

**Consequences:** Positive: zero additional infrastructure; self-evolution emerges from the compaction lifecycle already required for M2.7's token verbosity. Negative: compaction events are bounded by context window size — a very efficient session may compact infrequently, producing fewer evolution iterations per wall-clock hour. Neutral: the evolution log accumulates indefinitely; add a pruning policy if log files exceed a practical size.

---

### ADR-0007: Skill file self-modification with HITL gate for large diffs

**Status:** Proposed

**Context:** M2.7's self-evolution during training included modifying its own scaffold code. In the opencode harness, the equivalent is modifying skill files in `.opencode/skills/`. Unconstrained self-modification is a safety risk: a skill file that removes validation steps or lowers quality gates could degrade the entire pipeline silently.

**Decision:** M2.7 MAY propose skill file diffs based on `IterationMemory` entries. Diffs ≤50 lines that do not touch security-critical sections (permission rules, DLQ routing, idempotency guards) MAY be applied automatically after a dry-run validation. Diffs >50 lines, or any diff touching security-critical sections, MUST be routed to a human via `hitl.approval.requested` before application. All applied diffs MUST be recorded in the `DurableEventLog` with `content_hash`. A canary test MUST run on the next session; if performance drops below the prior checkpoint, the modification MUST be reverted using the stored `content_hash`.

**Consequences:** Positive: enables genuine harness self-improvement within safe bounds; aligns with how MiniMax used M2.7 to improve its own RL pipeline. Negative: small diffs can still introduce subtle regressions; the canary test must be well-calibrated to catch them. Neutral: the HITL gate for large diffs means the most significant improvements still involve a human, which is the intended safety boundary.

---

---

# Amendment B — Critical Gaps, Academic Research Findings, and Corrections

**Amendment status:** Proposed  
**Supersedes:** Specific subsections noted below  
**Research basis:** MAEL (arXiv:2505.23187, May 2025), ALAS (arXiv:2511.03094, Nov 2025), SagaLLM (arXiv:2503.11951, Mar 2025), ESAA (arXiv:2602.23193, Feb 2026), Intrinsic Memory Agents (arXiv:2508.08997, Aug 2025), CodeCRDT/CRDT (arXiv:2510.18893, Oct 2025), RLSR (arXiv:2505.08827, May 2025), Intuitor (arXiv:2505.19590, May 2025)

Nine gaps were identified after a complete re-read of the plan against current academic literature. They are ordered by severity.

---

## B1. Critical: SQLite concurrent writes will corrupt event ordering

**Severity: Critical — will cause silent data corruption under parallel agent execution.**

**The gap:** The `DurableEventLog` in section 6.3 calls `sqlite3.connect()` with no isolation or WAL mode specified. SQLite's default journal mode is DELETE, which uses a database-level write lock. With multiple Implementer subtask agents writing events concurrently, writers queue behind the lock — and, more dangerously, the `sequence_id` AUTOINCREMENT values are assigned at commit time, not at insert time. Under concurrent transactions, two agents can read the same "next" sequence position before either commits, resulting in duplicate or out-of-order sequence IDs.

**The research:** ESAA (arXiv:2602.23193, Feb 2026) documents exactly this requirement: "Concurrent execution is naturally serialized at the event level: multiple agents can work in parallel, but their results are validated and appended sequentially, preserving total ordering in the log." The "validated and appended sequentially" part is the part the plan omits.

**The fix:** Replace the `DurableEventLog._conn()` context manager with WAL mode and a write serialization lock:

```python
# agent_runtime/event_log.py  (corrected _conn and __init__)
import threading

class DurableEventLog:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._write_lock = threading.Lock()  # serializes all writes
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn(write=True) as conn:
            conn.execute("PRAGMA journal_mode=WAL")     # concurrent reads
            conn.execute("PRAGMA synchronous=NORMAL")   # safe with WAL
            conn.execute("PRAGMA busy_timeout=5000")    # 5s wait on lock
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    sequence_id    INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id       TEXT NOT NULL UNIQUE,
                    event_type     TEXT NOT NULL,
                    produced_at    TEXT NOT NULL,
                    producer_id    TEXT NOT NULL,
                    stage          TEXT,
                    task_id        TEXT,
                    correlation_id TEXT,
                    payload        TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_event_type ON events(event_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_task_id ON events(task_id)")

    @contextmanager
    def _conn(self, write: bool = False):
        if write:
            with self._write_lock:          # one writer at a time
                conn = sqlite3.connect(self.db_path, check_same_thread=False)
                conn.row_factory = sqlite3.Row
                try:
                    yield conn
                    conn.commit()
                finally:
                    conn.close()
        else:
            conn = sqlite3.connect(
                f"file:{self.db_path}?mode=ro", uri=True,
                check_same_thread=False
            )
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()

    def append(self, event: AgentEvent) -> int:
        with self._conn(write=True) as conn:   # was: self._conn()
            cursor = conn.execute(...)          # unchanged
        return cursor.lastrowid
```

**Impact on replay:** `replay()` uses read-only connections and is unaffected. The WAL mode allows concurrent readers while the writer holds the lock.

---

## B2. High: Cross-task memory is absent — MAEL shows this is a major missed opportunity

**Severity: High — the plan treats every RPIV task as isolated; literature shows 30–40% improvement from cross-task experience retrieval.**

**The gap:** The `SkillEvolutionLog` (§A5.1) accumulates compaction summaries per skill name but provides no mechanism for: (a) scoring experiences by quality, (b) retrieving experiences relevant to the *current* task rather than the last N by time, or (c) distinguishing experiences by stage or sub-agent role.

**The research:** MAEL (arXiv:2505.23187, May 2025) introduces reward-weighted, step-wise experience retrieval. Key findings:
- Step-wise retrieval (different experiences at each reasoning step) outperforms task-wise retrieval (a single prior solution trace applied throughout).
- Reward annotation of each experience step is essential — not all past experience is worth surfacing.
- Agents retrieve high-reward, *task-relevant* experiences as few-shot examples, not the most recent ones.

Intrinsic Memory Agents (arXiv:2508.08997, Aug 2025) adds: per-agent, role-aligned memory templates produce 38.6% improvement over shared flat memory. The Analyst's memory should record research failures, source quality, and retrieval strategies. The Implementer's memory should record code patterns that passed review and those that failed. Sharing a flat log loses the role-specific perspective.

**The fix:** Replace `SkillEvolutionLog` with a `RoleAlignedExperiencePool` that: stores experiences with reward scores, supports semantic similarity retrieval by task description, and maintains separate role-aligned schemas per agent.

```python
# agent_runtime/experience_pool.py
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class Experience:
    """One scored experience entry for a specific agent role."""
    experience_id: str
    agent_role: str                 # "rpiv-analyst", "rpiv-implementer", etc.
    stage: str
    task_description: str           # used for similarity retrieval
    task_id: str
    step_type: str                  # "research", "plan", "implement", "validate"
    input_context: str              # what the agent was given
    output_produced: str            # what the agent produced
    reward: float                   # 0.0–1.0; higher = more useful to surface
    reward_rationale: str           # why this reward was assigned
    tags: list[str] = field(default_factory=list)
    recorded_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )


class RoleAlignedExperiencePool:
    """Per-role experience store with reward-weighted retrieval.

    Implements the core insight from MAEL (arXiv:2505.23187):
    high-reward, task-relevant experiences retrieved at each step
    outperform recency-based retrieval from a flat log.
    """

    ROLE_SCHEMAS = {
        "rpiv-analyst": [
            "source_quality_signals",
            "retrieval_strategies_that_worked",
            "hallucination_triggers_to_avoid",
        ],
        "rpiv-planner": [
            "decomposition_patterns",
            "ambiguity_resolution_approaches",
            "dependency_graph_mistakes",
        ],
        "rpiv-implementer": [
            "code_patterns_that_passed_review",
            "patterns_that_failed_validation",
            "rollback_strategies",
        ],
        "rpiv-validator": [
            "integration_test_gaps_found",
            "security_issues_missed_by_implementer",
            "false_positive_patterns",
        ],
    }

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._lock = __import__("threading").Lock()
        self._init()

    def _init(self) -> None:
        with self._write_conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS experiences (
                    experience_id    TEXT PRIMARY KEY,
                    agent_role       TEXT NOT NULL,
                    stage            TEXT NOT NULL,
                    task_description TEXT NOT NULL,
                    task_id          TEXT NOT NULL,
                    step_type        TEXT NOT NULL,
                    input_context    TEXT NOT NULL,
                    output_produced  TEXT NOT NULL,
                    reward           REAL NOT NULL,
                    reward_rationale TEXT NOT NULL,
                    tags             TEXT NOT NULL DEFAULT '[]',
                    recorded_at      TEXT NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_role_reward "
                "ON experiences(agent_role, reward DESC)"
            )

    def store(self, exp: Experience) -> None:
        with self._write_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO experiences VALUES
                   (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    exp.experience_id, exp.agent_role, exp.stage,
                    exp.task_description, exp.task_id, exp.step_type,
                    exp.input_context, exp.output_produced, exp.reward,
                    exp.reward_rationale, json.dumps(exp.tags),
                    exp.recorded_at,
                ),
            )

    def retrieve(
        self,
        agent_role: str,
        task_description: str,
        step_type: str,
        top_k: int = 3,
        min_reward: float = 0.6,
    ) -> list[Experience]:
        """Retrieve high-reward experiences for this role and step type.

        Full semantic similarity search (embedding-based) is a future
        enhancement. This initial implementation uses keyword overlap
        as a proxy — sufficient until an embedding store is added.
        """
        with self._read_conn() as conn:
            rows = conn.execute(
                """SELECT * FROM experiences
                   WHERE agent_role = ?
                     AND step_type = ?
                     AND reward >= ?
                   ORDER BY reward DESC
                   LIMIT ?""",
                (agent_role, step_type, min_reward, top_k * 3),
            ).fetchall()

        # Keyword overlap re-rank against task_description
        query_words = set(task_description.lower().split())
        scored: list[tuple[float, dict]] = []
        for row in rows:
            row_d = dict(row)
            candidate_words = set(row_d["task_description"].lower().split())
            overlap = len(query_words & candidate_words) / max(len(query_words), 1)
            combined = row_d["reward"] * 0.7 + overlap * 0.3
            scored.append((combined, row_d))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            Experience(**{**d, "tags": json.loads(d["tags"])})
            for _, d in scored[:top_k]
        ]

    def as_few_shot_block(
        self,
        agent_role: str,
        task_description: str,
        step_type: str,
        top_k: int = 3,
    ) -> str:
        """Render retrieved experiences as a few-shot examples block."""
        experiences = self.retrieve(agent_role, task_description, step_type, top_k)
        if not experiences:
            return ""
        lines = [
            f"## Relevant past experiences for {agent_role} "
            f"({step_type} step, reward ≥ 0.6)\n"
        ]
        for i, exp in enumerate(experiences, 1):
            lines.append(f"### Example {i} (reward: {exp.reward:.2f})")
            lines.append(f"**Task:** {exp.task_description[:200]}")
            lines.append(f"**What worked:** {exp.output_produced[:400]}")
            lines.append(f"**Why it scored well:** {exp.reward_rationale}")
            lines.append("")
        return "\n".join(lines)

    @__import__("contextlib").contextmanager
    def _write_conn(self):
        with self._lock:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    @__import__("contextlib").contextmanager
    def _read_conn(self):
        conn = sqlite3.connect(
            f"file:{self.db_path}?mode=ro", uri=True,
            check_same_thread=False
        )
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
```

**Reward assignment:** Until a dedicated evaluator is wired (see §B3), rewards SHOULD be assigned by the Validator agent at the end of each task, scoring each prior stage's contribution on a 0–1 scale. This is the "backward pass" from MAEL: after the task outcome is known, annotate each step's contribution.

---

## B3. High: The canary metric is undefined — use self-certainty as the intrinsic reward signal

**Severity: High — the regression detection in §A5 and Phase 6 references "a canary task drops below the prior checkpoint" with no defined metric. Without a metric, the revert logic cannot fire.**

**The gap:** Phase 6 says "if the next session's performance on a canary task drops below the prior checkpoint, revert the skill modification." Neither the canary task nor the measurement method is defined. If the metric is "did the task succeed?" that's a binary signal too coarse to detect subtle regressions. If it requires human labeling, it defeats the purpose of autonomous self-improvement.

**The research:** Two complementary approaches from 2025 literature:

1. **Intrinsic self-certainty (Intuitor, arXiv:2505.19590):** Use the model's own token-level confidence (KL divergence from uniform distribution over the vocabulary at each output position) as a reward signal. Higher self-certainty = model is more confident in its output = proxy for quality. This requires access to logprobs, which the MiniMax API SHOULD expose.

2. **Self-judging (RLSR, arXiv:2505.08827):** Ask M2.7 to evaluate its own output against a rubric without external labels. At 88% verification accuracy, self-judging provides a sufficient signal for meaningful self-improvement — the model doesn't need to be a perfect judge, just a good-enough one.

**The fix:** Define a concrete three-signal canary metric:

```python
# agent_runtime/canary.py
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CanarySignal(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class CanaryResult:
    signal: CanarySignal
    self_judge_score: float      # 0.0–1.0: M2.7 self-evaluation of output quality
    structural_score: float      # 0.0–1.0: Pydantic schema validation pass rate
    test_pass_rate: float        # 0.0–1.0: fraction of pytest tests passing
    composite: float             # weighted average


CANARY_WEIGHTS = {
    "self_judge": 0.3,
    "structural": 0.4,   # highest weight — schema violations are hard failures
    "test_pass":  0.3,
}


def compute_canary(
    self_judge_score: float,
    structural_score: float,
    test_pass_rate: float,
) -> CanaryResult:
    composite = (
        self_judge_score * CANARY_WEIGHTS["self_judge"]
        + structural_score * CANARY_WEIGHTS["structural"]
        + test_pass_rate * CANARY_WEIGHTS["test_pass"]
    )
    if composite >= 0.75:
        signal = CanarySignal.PASS
    elif composite >= 0.55:
        signal = CanarySignal.WARN
    else:
        signal = CanarySignal.FAIL
    return CanaryResult(
        signal=signal,
        self_judge_score=self_judge_score,
        structural_score=structural_score,
        test_pass_rate=test_pass_rate,
        composite=composite,
    )
```

**Self-judge prompt for canary evaluation:**

```python
SELF_JUDGE_PROMPT = """
You produced the following output for the task below. Evaluate it honestly.

## Task
{task_description}

## Your output
{agent_output}

## Evaluation rubric
Score each dimension 0–10:
1. Correctness: Does the output actually solve the task?
2. Completeness: Are all required parts present?
3. Code quality: Is the code idiomatic, typed, and tested?
4. Robustness: Does it handle edge cases and failure modes?

Respond ONLY as JSON: {{"correctness": N, "completeness": N, "code_quality": N, "robustness": N}}
"""
```

The self-judge score is `mean(scores) / 10`. Combined with structural validation (Pydantic) and pytest pass rate, this gives a three-signal composite that can fire the revert without human labeling.

**Revert threshold:** Revert if `composite < prior_checkpoint_composite - 0.10`. A 10-point drop triggers revert; smaller drops log a warning but do not revert.

---

## B4. High: The Validator self-approves its own routing — circular validation

**Severity: High — the ALAS paper identifies this as one of the three root causes of planning failure in LLM systems.**

**The gap:** In §A3.4, the clarification gate asks M2.7 to evaluate its own interpretation of requirements: "List every requirement that is ambiguous... For each: state your intended interpretation." M2.7 then decides whether to proceed. This is self-approval: the same model context that proposed the interpretation judges whether the interpretation is safe to proceed with.

The plan's Validator uses Claude (good), but the Planner's clarification gate uses M2.7 validating itself.

**The research:** ALAS (arXiv:2511.03094, Nov 2025) identifies circular validation as a root cause: "verification is often circular: the same model or context that proposes a plan is asked to approve it." Their solution: the validator uses "fresh, bounded prompts" that consume only a short, grounded log slice — not the full planner context.

SagaLLM (arXiv:2503.11951, Mar 2025) formalizes this with independent validation agents: "independent validation agents... temporal-spatial context tracking... external verification mechanisms to validate inter-agent dependencies."

**The fix:** Route the clarification gate output to the Validator agent (Claude), not back to M2.7. The validation call is cheap — Claude only sees the spec and M2.7's interpretation list, not M2.7's full planning context.

```python
async def run_clarification_gate(
    spec: str,
    m2_7_interpretations: dict,
    validator_client: OpencodeClient,
    validator_session_id: str,
) -> bool:
    """Non-circular validation: Claude checks M2.7's interpretations.
    
    Returns True if interpretations are safe to proceed with.
    The Validator sees only the spec and the interpretation list —
    not M2.7's reasoning chain. This is the 'bounded prompt' from ALAS.
    """
    validation_prompt = f"""
    A planning agent proposed the following interpretations of the spec below.
    Your job: identify any interpretation that is:
    - Architecturally irreversible
    - Contradicting the spec's stated requirements
    - Missing a requirement entirely

    ## Spec
    {spec}

    ## Proposed interpretations
    {m2_7_interpretations}

    Respond ONLY as JSON:
    {{"safe_to_proceed": bool, "issues": [list of strings], "must_escalate": bool}}
    """
    response = await validator_client.session.prompt(
        session_id=validator_session_id,
        agent="rpiv-validator",
        parts=[{"type": "text", "text": validation_prompt}],
    )
    # Parse and return
    ...
```

**Configuration change required:** Add `rpiv-validator` to the opencode config with `tools: {write: false, edit: false}` — the validator never writes files; it only reads spec and interpretations.

---

## B5. Medium: Blackboard write conflicts have no resolution policy

**Severity: Medium — will produce silent data divergence when Analyst and Planner write to the same artifact path.**

**The gap:** The Blackboard pattern (§4.3) says "all agents read from and write to a shared artifact store structured as an append-only log." But two agents can write different content to the same logical artifact path (for example, both Analyst and Planner write to `research/findings.md`). The plan has no conflict resolution policy. Last-write-wins by timestamp is dangerous because M2.7's 2.91s TTFT plus network jitter makes wall-clock timestamps unreliable.

**The research:** The CodeCRDT paper (arXiv:2510.18893, Oct 2025) demonstrates that "5–10% of concurrent code edits by LLM agents produce structurally valid but logically conflicting results after CRDT merge." CRDTs handle *structural* convergence automatically but cannot detect *semantic* conflicts. Their solution: CRDTs at the structural layer + an LLM-driven arbiter for semantic conflicts.

**The practical fix (without full CRDT infrastructure):** Add an explicit conflict event type and a logical clock:

```python
# agent_runtime/events.py — add these types

class ArtifactConflict(AgentEvent):
    """Emitted when two agents write different content to the same path."""
    event_type: Literal["artifact.conflict"] = "artifact.conflict"
    path: str
    incumbent_hash: str     # hash of the existing artifact
    challenger_hash: str    # hash of the new write
    incumbent_producer: str
    challenger_producer: str

class ArtifactResolved(AgentEvent):
    """Emitted after conflict resolution; carries the winning content hash."""
    event_type: Literal["artifact.resolved"] = "artifact.resolved"
    path: str
    winning_hash: str
    resolution_strategy: Literal["incumbent_wins", "challenger_wins", "merged", "hitl"]
```

**Conflict resolution policy (in `DurableEventLog.append`):**

```python
def write_artifact(
    self,
    path: str,
    content_hash: str,
    producer_id: str,
    task_id: str,
) -> str:
    """Write an artifact; detect and handle conflicts. Returns winning hash."""
    # Find the most recent write to this path
    existing = self._latest_artifact(path)
    if existing is None:
        self._record_artifact_write(path, content_hash, producer_id, task_id)
        return content_hash
    if existing["content_hash"] == content_hash:
        return content_hash  # idempotent write; no conflict
    # Conflict: emit conflict event; apply resolution policy
    self.append(ArtifactConflict(...))
    # Resolution: Validator stage → challenger wins (Validator has final authority).
    # Otherwise: incumbent wins; challenger change logged but not applied.
    if producer_id.startswith("rpiv-validator"):
        self._record_artifact_write(path, content_hash, producer_id, task_id)
        return content_hash
    else:
        # Emit HITL if conflict is in a Plan or Implement artifact
        self.append(HITLApprovalRequested(...))
        return existing["content_hash"]
```

**Future direction:** Replace this policy with Yjs CRDT structural merging + M2.7 semantic conflict resolution for artifact paths with high write contention. This is the architecture proven by CodeCRDT at EuroSys 2025.

---

## B6. Medium: The Context7 sub-agent has no model assignment or event integration

**Severity: Medium — the plan describes the RPIV pipeline as Locator → Analyst → Context7 → Planner → Implementer → Validator, but Context7 appears nowhere in §A6's opencode configuration or in §A2's routing table.**

**The fix:** Add the Context7 agent to the configuration. Context7 is a library documentation lookup agent — it makes structured API calls to the Context7 MCP server and returns documentation snippets. This is a pure retrieval task with high precision requirements but no code generation. M2.7's hallucination rate (34%) is acceptable here; Claude is unnecessary.

```jsonc
// Add to opencode.jsonc agent section:
"rpiv-context7": {
  "model": "MiniMax-M2.7",  // Direct MiniMax Token Plan API
  "mode": "subagent",
  "hidden": true,  // only invokable by rpiv-analyst and rpiv-planner
  "description": "Retrieves library documentation via Context7 MCP",
  "tools": {
    "write": false,
    "edit": false,
    "bash": false
    // MCP tools allowed by default
  },
  "permission": {
    "task": {
      "*": "deny"   // Context7 does not spawn sub-agents
    }
  }
},
```

**Routing table update (§A2):**

```
RPIV Stage      Primary Model    Notes
──────────────────────────────────────────────────────────────
Context7        M2.7             Pure retrieval; no code gen; hallucination
                                 rate acceptable for doc lookup. Validate
                                 that returned snippets are used verbatim,
                                 not paraphrased (paraphrase introduces drift).
```

**Event integration:** Context7 SHOULD emit `artifact.written` events with `stage: "research"` and `payload.source: "context7"` for every documentation snippet it retrieves. This makes library documentation available on the Blackboard (§4.3) for all downstream agents without re-querying.

---

## B7. Medium: No compensating transaction for partial RPIV run failures — adopt SagaLLM pattern

**Severity: Medium — the plan has idempotency guards for individual side effects but no rollback strategy for multi-step partial failures.**

**The gap:** If the Implementer completes three of five tasks and then fails with `circular_delegation`, the pipeline halts with: three tasks in a committed state, two tasks not started, and no defined path back to a clean state. The current plan routes to HITL but gives the human no structured information about what was committed and what can safely be retried.

**The research:** SagaLLM (arXiv:2503.11951, Mar 2025) adapts the Saga transactional pattern to LLM workflows. Each step in the workflow has a defined compensating action. If step N fails, steps 1 through N-1 execute their compensating actions in reverse order. SagaLLM reports "significant improvements in consistency, validation accuracy, and adaptive coordination under uncertainty" versus standalone LLM baselines.

**The practical fix:** Define compensating actions for each RPIV stage. These don't need to be perfect inverses — they need to restore the system to a state where re-execution is safe.

```python
# agent_runtime/saga.py
from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SagaStep:
    name: str
    execute: Callable[[], Coroutine[Any, Any, Any]]
    compensate: Callable[[], Coroutine[Any, Any, None]]
    completed: bool = False


class RPIVSaga:
    """Saga coordinator for an RPIV run.
    
    Each stage registers itself as a step with a compensating action.
    If any step raises, the saga runs compensation in reverse.
    """

    COMPENSATION_ACTIONS: dict[str, str] = {
        "research":  "Delete research/ artifacts; reset Locator and Analyst sessions.",
        "plan":      "Delete plan/ artifacts; mark tasks.md as invalid.",
        "implement": "Revert all git changes made in this run; delete implement/ artifacts.",
        "validate":  "No compensation needed — Validator is read-only.",
    }

    def __init__(self, task_id: str, log: "DurableEventLog") -> None:
        self.task_id = task_id
        self.log = log
        self.steps: list[SagaStep] = []

    def register(self, step: SagaStep) -> None:
        self.steps.append(step)

    async def execute(self) -> None:
        completed: list[SagaStep] = []
        for step in self.steps:
            try:
                await step.execute()
                step.completed = True
                completed.append(step)
                self.log.append(AgentEvent(
                    event_type="saga.step.completed",
                    producer_id="rpiv-orchestrator",
                    task_id=self.task_id,
                    payload={"step": step.name},
                ))
            except Exception as e:
                self.log.append(AgentEvent(
                    event_type="saga.step.failed",
                    producer_id="rpiv-orchestrator",
                    task_id=self.task_id,
                    payload={"step": step.name, "error": str(e)},
                ))
                # Compensate in reverse order
                for done_step in reversed(completed):
                    try:
                        await done_step.compensate()
                        self.log.append(AgentEvent(
                            event_type="saga.step.compensated",
                            producer_id="rpiv-orchestrator",
                            task_id=self.task_id,
                            payload={"step": done_step.name},
                        ))
                    except Exception as comp_err:
                        # Compensation failure: always escalate to HITL
                        self.log.append(HITLApprovalRequested(
                            producer_id="rpiv-orchestrator",
                            task_id=self.task_id,
                            opencode_permission_id="",
                            tool_name="saga.compensate",
                            tool_args={"step": done_step.name, "error": str(comp_err)},
                        ))
                raise
```

**Compensation actions per stage:**

| Stage | Compensating action |
|-------|---------------------|
| Research | `git rm -rf research/` for the task branch; invalidate Blackboard entries with `task_id` |
| Plan | Delete `plan/spec.md`, `tasks.md`; emit `artifact.invalidated` events |
| Implement | `git checkout HEAD -- .` on the task branch (reverts all uncommitted changes); revert committed changes via `git revert` if pushed |
| Validate | No-op — Validator is read-only and produces no persistent side effects |

---

## B8. Low-Medium: Token budget ceiling missing for full RPIV runs with M2.7

**Severity: Low-Medium — without a per-run token ceiling, a five-stage M2.7 pipeline can exhaust API budget silently.**

**The gap:** M2.7 produces 3.3x the median token count. A five-stage RPIV run with M2.7 primary across Analyst, Plan, and Implement could burn 50,000–200,000 output tokens per run at $0.30/$1.20 pricing. No per-run budget is defined anywhere in the plan.

**The fix:** Add a `RunBudget` context that the orchestrator enforces:

```python
# agent_runtime/budget.py
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RunBudget:
    """Per-RPIV-run token budget. Enforced by the orchestrator."""
    max_input_tokens: int = 500_000    # hard ceiling
    max_output_tokens: int = 200_000   # hard ceiling; M2.7 verbosity risk
    warn_at_output: int = 150_000      # emit budget.warning event at 75%
    used_input: int = 0
    used_output: int = 0

    def record(self, input_tokens: int, output_tokens: int) -> None:
        self.used_input += input_tokens
        self.used_output += output_tokens

    @property
    def output_exhausted(self) -> bool:
        return self.used_output >= self.max_output_tokens

    @property
    def output_warn(self) -> bool:
        return self.used_output >= self.warn_at_output

    @property
    def estimated_cost_usd(self) -> float:
        return (self.used_input / 1_000_000 * 0.30
                + self.used_output / 1_000_000 * 1.20)
```

The orchestrator MUST check `budget.output_exhausted` before dispatching each stage. If exhausted, emit a `budget.exceeded` event and route to HITL.

---

## B9. Low: `parse_compaction_summary` uses regex on M2.7 reasoning-model output

**Severity: Low — reasoning models emit variable-length chain-of-thought before the structured output. Regex parsing on this output will fail silently when the chain-of-thought bleeds into the structured section.**

**The gap:** `parse_compaction_summary` (§A5.3) uses `re.search` to find `### Self-criticism` and similar headers directly in M2.7's compaction output. M2.7 is a reasoning-only model whose output includes extended internal reasoning before the final answer. The headers may appear inside the reasoning chain with different content than the final structured answer.

**The fix:** Wrap the compaction output parser with a dedicated structured extraction call. Rather than parsing the full compaction text, send only the final compaction output through a structured extraction prompt with `format: "json"`:

```python
async def extract_iteration_memory(
    compaction_text: str,
    client: OpencodeClient,
    session_id: str,
) -> IterationMemory:
    """Use a dedicated M2.7 call to extract structured memory from compaction output.
    
    This is cheaper than parsing via regex and more reliable on reasoning model output.
    """
    extraction_prompt = f"""
Extract the following fields from the compaction summary below.
Respond ONLY as a JSON object with these exact keys:
"what_was_tried", "what_failed", "what_worked",
"optimization_directions" (array of strings), "skill_files_modified" (array of strings)

## Compaction summary
{compaction_text[:4000]}  # truncate to avoid context blowout on extraction call
"""
    response = await client.session.prompt(
        session_id=session_id,
        agent="rpiv-orchestrator",
        format={"type": "json_schema", "schema": IterationMemory.model_json_schema()},
        parts=[{"type": "text", "text": extraction_prompt}],
    )
    data = json.loads(response.parts[0].text)
    return IterationMemory(
        iteration=0,  # set by caller
        stage="",     # set by caller
        task_id="",   # set by caller
        **data,
    )
```

---

## B10. Summary: what changes, what stays

| Section | Status | Change |
|---------|--------|--------|
| §6.3 DurableEventLog | **Replace** | Add WAL mode, write lock, read-only URI for readers (§B1) |
| §A5.1 SkillEvolutionLog | **Replace** | Replace with RoleAlignedExperiencePool (§B2) |
| Phase 6 canary metric | **Define** | Three-signal composite: self-judge + structural + test pass rate (§B3) |
| §A3.4 clarification gate | **Correct** | Route gate output to Claude Validator, not back to M2.7 (§B4) |
| §4.3 Blackboard | **Extend** | Add ArtifactConflict event type and resolution policy (§B5) |
| §A2 routing table + §A6 config | **Extend** | Add Context7 agent with model assignment (§B6) |
| §9 phased plan | **Extend** | Add RPIVSaga for compensating transactions (§B7) |
| §A6 config | **Extend** | Add RunBudget enforcement in orchestrator (§B8) |
| §A5.3 parser | **Replace** | Structured extraction call instead of regex (§B9) |
| §4.1 Orchestrator-Worker | **No change** | Correct as written |
| §4.2 Hierarchical Agent | **No change** | Correct as written |
| §5.1–5.4 opencode integration | **No change** | Correct as written |
| §8.1 DLQ taxonomy | **No change** | Correct as written |
| §A4 self-evolution wiring | **No change** | Correct; §B2 extends rather than replaces |
| ADR-0001 through ADR-0007 | **No change** | Add ADR-0008 through ADR-0010 below |

---

## B11. Additional ADRs

### ADR-0008: WAL mode and write serialization lock for DurableEventLog

**Status:** Proposed (supersedes the implicit SQLite configuration in §6.3)

**Context:** SQLite's default DELETE journal mode serializes all access through a database-level write lock, which blocks concurrent readers. Multiple Implementer subtask agents write events simultaneously. Without WAL mode, readers block during writes, creating latency spikes during high-concurrency phases. Without a write lock in the application layer, concurrent Python threads can produce duplicate or out-of-order `sequence_id` values.

**Decision:** Enable WAL mode (`PRAGMA journal_mode=WAL`) at database initialization. Add a `threading.Lock()` in `DurableEventLog.__init__` that all write paths must acquire. Read paths use a read-only database URI (`file:path?mode=ro`) and do not acquire the lock.

**Consequences:** Positive: concurrent reads proceed without blocking; write ordering is guaranteed. Negative: the in-process write lock does not protect against concurrent writes from *separate processes* — if the orchestrator ever runs as multiple processes, this must be replaced with `fcntl` file locking or a Redis-backed lock. Neutral: WAL mode adds a `-wal` and `-shm` file alongside the `.db` file; include both in `.gitignore`.

---

### ADR-0009: RoleAlignedExperiencePool over flat SkillEvolutionLog

**Status:** Proposed (supersedes §A5.1 SkillEvolutionLog)

**Context:** The SkillEvolutionLog stores compaction summaries by skill name. Two problems: (1) all experiences are equally weighted regardless of outcome quality; (2) a shared flat log cannot maintain the agent-specific perspectives proven important by Intrinsic Memory Agents (arXiv:2508.08997, 38.6% improvement). MAEL (arXiv:2505.23187) further demonstrates that reward-weighted, task-similarity-based retrieval outperforms recency-based retrieval.

**Decision:** Replace `SkillEvolutionLog` with `RoleAlignedExperiencePool`. Each experience stores a reward score (0–1) assigned by the Validator backward pass. Retrieval uses reward-weighted keyword overlap as an initial approximation of semantic similarity, with an embedding-based upgrade path planned for Phase 7.

**Consequences:** Positive: higher-quality experiences surface more often; per-role memory maintains heterogeneous agent perspectives. Negative: the Validator backward pass adds one extra API call per completed task. Neutral: the SQLite schema supports an `embedding` BLOB column for future dense retrieval without a schema migration.

---

### ADR-0010: RPIVSaga for compensating transactions on partial pipeline failures

**Status:** Proposed

**Context:** The existing DLQ taxonomy (§8.1) handles individual event failures but provides no rollback semantics for multi-step partial runs. If the Implement stage fails after committing three of five tasks to git, the system is in a partially-committed state with no defined recovery path. The Saga pattern (SagaLLM, arXiv:2503.11951) provides exactly this: each step registers a compensating action run in reverse order on failure.

**Decision:** Wrap each RPIV run in an `RPIVSaga` instance. Each stage registers `execute` and `compensate` callbacks. The orchestrator calls `saga.execute()`, which automatically runs compensation on failure. Compensation failures always escalate to HITL — there is no automatic retry of a compensation.

**Consequences:** Positive: humans get a structured account of what was committed and what was rolled back; git history remains clean. Negative: compensation logic for the Implement stage (git revert) is complex and must be tested independently. Neutral: the Validate stage has no compensating action, which is correct — it produces no persistent side effects.
