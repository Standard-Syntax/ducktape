# Event-Driven Agent Runtime Plan

## Status

Planning artifact only. Do not implement production code from this file until Phase 0 exit criteria are complete.

## Source Inputs

- Primary input: `eda-multi-agent-plan.md`
- Follow-up decision: target latest/current opencode behavior; local installed version verified as `1.14.48`.
- Follow-up decision: `stk` is a local dependency at `/home/dscv/Repo/stk`.
- Follow-up decision: MiniMax M2.7 should use the direct MiniMax Token Plan API, not OpenRouter.
- Follow-up decision: adopt OpenTelemetry GenAI semantic conventions immediately, with Development-status caveat.

## Verified Decisions

| Decision | Evidence | Planning Impact |
|---|---|---|
| Use documented opencode plugin events, not `sessionCreated` or `toolExecuted`. | opencode docs verify `session.created`, `session.compacted`, `permission.asked`, `permission.replied`, `tool.execute.before`, and `tool.execute.after`. | Plugin design should use the generic `event` hook or documented event names. |
| Do not use `promptAsync`, `prompt_async`, or `/session/{id}/prompt_async`. | Context7 and official opencode docs did not verify these APIs. | Dispatch design must use verified opencode APIs such as `session.prompt`, `session.command`, and `event.subscribe` where applicable. |
| Use `subtask: true` only for opencode command/subagent config. | opencode docs verified `subtask: true` command behavior. | Parallel agent launch should be modeled through documented command config, not assumed SDK flags. |
| Use structured output as JSON schema config, not `format="json"` for SDK calls. | opencode docs verified `format: { type: "json_schema", schema, retryCount? }`; CLI `--format json` is separate. | Structured extraction and validator calls need JSON-schema format objects. |
| Treat `stk` command envelopes as verified, but define agent events separately. | `/home/dscv/Repo/stk` verifies `schemaVersion: 1`, `ok`, `command`, `data`, `errors`, `warnings`, and `elapsed_ms`. | Agent event envelopes may borrow conventions but must not pretend to be `stk` command results. |
| Use MiniMax direct Token Plan API. | MiniMax docs verify model `MiniMax-M2.7`, base URL `https://api.minimax.io/v1`, and env var `MINIMAX_API_KEY`. | Remove OpenRouter as the primary provider path. Provider config is verified in Phase 0 Design Lock (T00-007). |
| Use AnyIO for Python concurrency. | Project global stack requires AnyIO; AnyIO docs verify task groups, memory object streams, semaphores, capacity limiters, locks, and thread offload. | Replace raw `asyncio` examples from the input plan with AnyIO equivalents during implementation. |
| Use Pydantic v2 for event models. | Pydantic docs verify `BaseModel`, `model_validate`, `model_dump`, `Field(default_factory=...)`, `Literal`, and discriminated unions. | Event schemas should use Pydantic v2 and discriminated unions by event type. |
| Use SQLite WAL only for local durable event logging. | SQLite docs verify WAL, one-writer behavior, reader/writer concurrency, and `SQLITE_BUSY` caveats. | Add serialized writes, busy timeout, checkpoint policy, and local-host constraint. |
| Adopt OpenTelemetry GenAI conventions immediately. | OpenTelemetry docs verify GenAI attributes including `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.conversation.id`, and token usage attributes. | Telemetry adapter should isolate Development-status convention churn. |

## Remaining Unverified Items

- Unverified: grepai semantic repository findings because the grepai MCP workspace was not configured in this session.
- Unverified: `promptAsync`, `prompt_async`, and `/session/{sessionID}/prompt_async`. These should be removed from the implementation plan unless future docs verify them.
- Unverified: whether the event schema should live in `ducktape` only, in `/home/dscv/Repo/stk`, or in both repositories.
- Unverified: whether `stk schema` should expose agent-event schemas in addition to command-result schemas.

> **Note:** The MiniMax direct API provider configuration is verified and recorded in the Phase 0 Design Lock section above (T00-007 completed).

## Dependency Register

| Dependency | Version / source | Verified API / behavior | Evidence | Risk |
|---|---|---|---|---|
| opencode | Local `1.14.48`; current official docs | Plugin events, local plugins, `permission` config, `subtask: true`, `event.subscribe`, `session.prompt`, JSON-schema structured output | Context7 and official docs | Latest docs may drift from local installed behavior. |
| `stk` | `/home/dscv/Repo/stk` | Command envelope `schemaVersion: 1`, `ok`, `command`, `data`, `errors`, `warnings`, `elapsed_ms`; `stk schema`; `STK_OUTPUT=json` | Local Probe, reads, and `rg` | Agent event fields are not present in the verified command envelope. |
| MiniMax M2.7 | Direct Token Plan API | Model `MiniMax-M2.7`, base URL `https://api.minimax.io/v1`, env var `MINIMAX_API_KEY`; opencode provider shape verified with `@ai-sdk/openai-compatible`, `options.baseURL`, env-backed `options.apiKey`, and model key `MiniMax-M2.7` | Context7 MiniMax and opencode docs | Local config should still be smoke-tested before first live provider call. |
| OpenTelemetry GenAI | OpenTelemetry semantic conventions, Development status | GenAI operation/provider/model/conversation/token attributes | Context7 and official docs | Development conventions may change. |
| Pydantic v2 | Current Pydantic docs | `BaseModel`, validation, dumping, discriminated unions, default factories | Context7 | Schema design must avoid Pydantic v1 patterns. |
| AnyIO | Current AnyIO docs | Task groups, memory object streams, semaphores, capacity limiters, locks, thread offload | Context7 | Input plan examples use raw `asyncio`; implementation must translate carefully. |
| SQLite | Official SQLite WAL docs | WAL mode, one writer, reader/writer concurrency, busy cases, local-host constraint | SQLite docs | Multi-process contention and checkpoint behavior require tests. |
| grepai | Local MCP configured but unavailable | No verified semantic findings | MCP returned no configured workspaces | Cannot rely on semantic repo findings until workspace is fixed. |

## Architecture Plan

The runtime should evolve in three layers:

1. opencode plugin event capture: forward verified lifecycle events such as `session.created`, `permission.asked`, and `tool.execute.after` into a local bridge.
2. In-process Python event bus: normalize events into typed Pydantic v2 envelopes and route them through AnyIO memory streams with explicit backpressure.
3. Durable event backbone: persist normalized events to SQLite WAL with serialized writes, idempotency keys, read-only readers, and checkpoint policy.

The event schema should be separate from `stk` command results. It can borrow `stk` conventions such as `schemaVersion` and structured error fields, but it needs event-specific fields including `event_id`, `event_type`, `producer`, `correlation_id`, `occurred_at`, and `payload`.

Telemetry should be captured through an adapter that emits OpenTelemetry GenAI attributes for model operations while insulating the rest of the code from convention churn.

## Phase Plan

### Phase 0: Verification And Design Lock

Goal: remove configuration ambiguity before implementation.

Deliverables:

- Updated architecture notes replacing stale opencode API names with verified names.
- MiniMax direct API provider decision recorded with exact verified fields.
- Decision on event schema repository ownership.
- Decision on whether `stk schema` should expose event envelopes.
- Spike result for exact opencode MiniMax provider config shape.

Exit criteria:

- No implementation task depends on `promptAsync`, `prompt_async`, or `/session/{id}/prompt_async`.
- The exact opencode MiniMax direct provider config is verified or explicitly deferred behind a feature flag.
- Event envelope ownership is decided.

### Phase 1: First Event Vertical Slice

Goal: prove one opencode event can be captured, normalized, persisted, and observed.

Deliverables:

- Local opencode plugin captures one verified event: prefer `session.created`; fallback `permission.asked` if easier to trigger.
- Local bridge receives the event.
- Pydantic v2 event envelope validates the normalized payload.
- SQLite WAL event log persists the event with idempotency key.
- OpenTelemetry GenAI adapter is present for model-call metadata, even if this slice emits only non-model event metadata.

Exit criteria:

- A repeat event does not duplicate persisted state when the same idempotency key is used.
- WAL settings and write serialization are verified by tests or direct observation.
- The event envelope is documented as distinct from `stk` command results.

### Phase 2: AnyIO Bus And Backpressure

Goal: replace direct forwarding with a bounded in-process event bus.

Deliverables:

- AnyIO memory object streams for event fan-out.
- Capacity limits for agent/task dispatch.
- Structured event failure path for handler exceptions.
- Tests for bounded queues, cancellation, and graceful shutdown.

Exit criteria:

- Slow consumers cannot grow memory without bound.
- Handler failures produce typed failure events.
- Shutdown drains or explicitly abandons work according to documented policy.

### Phase 3: RPIV Agent Workflow Events

Goal: map RPIV workflow seams onto typed events.

Deliverables:

- Event types for task assignment, task completion, task failure, HITL approval request, artifact write, artifact conflict, artifact resolution, budget warning, and budget exceeded.
- Non-circular clarification gate: MiniMax proposes interpretations; Claude Validator or HITL validates when needed.
- Blackboard artifact conflict policy based on path/hash detection.

Exit criteria:

- Conflict events are deterministic and reviewable.
- Clarification gates cannot self-approve their own ambiguous interpretation.
- Budget exhaustion produces a HITL decision event.

### Phase 4: Experience Pool And Canary Evaluation

Goal: add role-aligned learning without unsafe autonomous mutation.

Deliverables:

- Role-aligned experience pool keyed by role, stage, task, and step.
- Reward and retrieval policy using explicit signals first; semantic retrieval can be added later.
- Canary metric combining structural validation, tests, and model/self-judge review.
- HITL gate before modifying durable prompt, skill, or routing behavior.

Exit criteria:

- Learned experience can be traced to source events.
- Canary failure blocks promotion.
- Autonomous skill mutation is disabled unless explicitly approved.

### Phase 5: Saga Compensation And Operational Hardening

Goal: make failures recoverable and auditable.

Deliverables:

- RPIV saga state machine for stage-level compensation.
- Safe compensation policies that avoid destructive git commands by default.
- Event-log replay tooling.
- Operational runbook for WAL checkpoints, busy handling, and recovery.

Exit criteria:

- Compensation failures escalate to HITL.
- Replay can reconstruct the current workflow state from the event log.
- Operational runbook covers SQLite local-host/WAL limitations.

## First Vertical Slice

Scope:

- Capture one verified opencode event.
- Normalize it into a Pydantic v2 agent-event envelope.
- Persist it through SQLite WAL.
- Document how the event envelope relates to, but differs from, `stk` command envelopes.

Out of scope:

- Full multi-agent dispatch.
- Skill evolution.
- Saga compensation.
- Market-based task assignment.
- Durable cross-machine event backbone.
- OpenRouter provider support.

Likely files to add later:

- `.opencode/plugins/event-forwarder.ts`
- `agent_runtime/events.py`
- `agent_runtime/bus.py`
- `agent_runtime/event_log.py`
- `agent_runtime/telemetry.py`
- `tests/test_events.py`
- `tests/test_event_log.py`

Do not add these files as part of this planning artifact.

## Atomic Tasks

### Phase 0 Tasks

- [x] T00-001: Record local opencode version `1.14.48` in the implementation notes.
- [x] T00-002: Replace all references to `sessionCreated` with documented event `session.created` or generic `event` hook usage.
- [x] T00-003: Replace all references to `toolExecuted` with documented `tool.execute.after` or `tool.execute.before`.
- [x] T00-004: Remove `promptAsync`, `prompt_async`, and `/session/{sessionID}/prompt_async` from planned implementation paths.
- [x] T00-005: Replace SDK `format="json"` language with `format: { type: "json_schema", schema, retryCount? }` for structured SDK calls.
- [x] T00-006: Keep CLI `opencode run --format json` documented separately from SDK structured output.
- [x] T00-007: Validate exact `opencode.json` provider config for MiniMax direct API with `MiniMax-M2.7`.
- [x] T00-008: Record MiniMax direct API values: base URL `https://api.minimax.io/v1`, model `MiniMax-M2.7`, env var `MINIMAX_API_KEY`.
- [x] T00-009: Remove OpenRouter slug from the primary provider path.
- [x] T00-010: Decide whether OpenRouter remains a documented fallback or is removed entirely.
- [x] T00-011: Decide whether event schema source of truth lives in `ducktape`, `/home/dscv/Repo/stk`, or both.
- [x] T00-012: Decide whether `stk schema` should expose agent-event schemas.
- [x] T00-013: Document verified `stk` command envelope fields from `/home/dscv/Repo/stk`.
- [x] T00-014: Document that agent event envelopes are not `stk` command-result envelopes.
- [x] T00-015: Decide the first opencode event for the vertical slice: `session.created` or `permission.asked`.
- [x] T00-016: Define the first event envelope field list and required/optional fields.
- [x] T00-017: Define idempotency key construction for the first event type.
- [x] T00-018: Define SQLite WAL pragmas and checkpoint policy for the local event log.
- [x] T00-019: Define telemetry adapter boundaries and which OpenTelemetry GenAI attributes are emitted in Phase 1.
- [x] T00-020: Document OpenTelemetry GenAI Development-status risk.

## Phase 0 Design Lock

Phase 0 is complete. The following decisions are locked and supersede any conflicting guidance in `eda-multi-agent-plan.md` or earlier drafts.

### Verified opencode lifecycle events

The following opencode plugin event names are verified and SHALL be used in all implementation tasks:

- `session.created` — emitted when a new session starts
- `session.compacted` — emitted after session context compaction
- `permission.asked` — emitted when a tool requires human approval
- `permission.replied` — emitted when human responds to a permission request
- `tool.execute.before` — emitted before a tool is executed
- `tool.execute.after` — emitted after a tool completes

The old names `sessionCreated` and `toolExecuted` are deprecated and MUST NOT appear in implementation code.

### Unverified APIs excluded from implementation

The following APIs are **not verified** in opencode docs and are excluded from implementation tasks:

- `promptAsync` / `prompt_async` — POST to `/session/{sessionID}/prompt_async`
- `/session/{id}/prompt_async` endpoint
- Any SDK method that returns HTTP 204 for non-blocking dispatch (unless later verified)

Implementation SHALL use verified opencode APIs such as `session.prompt`, `session.command`, and `event.subscribe` where applicable.

### MiniMax direct Token Plan provider configuration

MiniMax M2.7 uses the direct Token Plan API, not OpenRouter. Verified configuration:

```json
{
  "provider": {
    "minimax": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "MiniMax",
      "options": {
        "baseURL": "https://api.minimax.io/v1",
        "apiKey": "{env:MINIMAX_API_KEY}"
      },
      "models": {
        "MiniMax-M2.7": {
          "name": "MiniMax-M2.7"
        }
      }
    }
  }
}
```

The old OpenRouter MiniMax slug is removed from the primary provider path. OpenRouter MAY be documented as a fallback but is not the primary path.

### Event schema ownership

- Event schema source of truth: `ducktape` repository (this project)
- Schema MAY later be promoted to `/home/dscv/Repo/stk` if shared CLI support is needed
- `stk schema` exposure: deferred until first event envelope is stable; not blocking Phase 1

### stk command envelope vs. agent event envelope

Verified `stk` command envelope fields (do not use for agent events):

- `schemaVersion: 1`
- `ok`
- `command`
- `data`
- `errors`
- `warnings`
- `elapsed_ms`

Agent event envelopes are **not** `stk` command-result envelopes. Agent events borrow some conventions (`schemaVersion`, structured error fields) but add event-specific fields: `event_id`, `event_type`, `producer`, `correlation_id`, `occurred_at`, and `payload`.

### First vertical slice event selection

First event for Phase 1: `session.created`

Rationale: easiest to trigger reliably in testing; no human-in-the-loop dependency.

### First event envelope fields

```python
class AgentEvent(BaseModel):
    event_id: str              # UUID, auto-generated
    event_type: str            # namespaced: "session.created", etc.
    occurred_at: datetime      # UTC, auto-generated
    producer: str              # "opencode" or "bridge"
    correlation_id: str | None # links related events
    payload: dict[str, Any]    # event-specific data
```

Required fields: `event_id`, `event_type`, `producer`, `occurred_at`, `payload`
Optional fields: `correlation_id`

### Idempotency key construction

Idempotency key for `session.created` events:

```
idempotency_key = sha256(f"{session_id}:{event_type}:{occurred_at.isoformat()}")[:16]
```

Duplicate events with the same idempotency key within a 24-hour window are suppressed.

### SQLite WAL policy

Pragmas for the local event log:

- `PRAGMA journal_mode=WAL` — enables Write-Ahead Logging
- `PRAGMA synchronous=NORMAL` — balanced safety/speed for local development
- `PRAGMA busy_timeout=5000` — 5 second timeout before returning SQLITE_BUSY
- Checkpoint policy: `PRAGMA wal_checkpoint(TRUNCATE)` after every 100 events or on graceful shutdown

WAL is local-host only. Multi-process access is not supported.

### Telemetry adapter boundary

The telemetry adapter:

- Receives model-call metadata (model name, token counts, operation duration)
- Emits OpenTelemetry GenAI attributes: `gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.conversation.id`, and token usage attributes
- All GenAI convention churn is localized to the adapter
- Phase 1 emits event metadata only; model-call telemetry is Phase 2+

### OpenTelemetry GenAI Development-status risk

OpenTelemetry GenAI semantic conventions are at **Development** status. This means:

- Attribute names and semantics may change in future releases
- Risk is localized to the telemetry adapter
- If conventions change, only the adapter needs updates; event schemas and bus are unaffected

### Phase 1 Tasks

- [ ] T01-001: Create a minimal local opencode plugin that subscribes to the selected verified event.
- [ ] T01-002: Forward the selected event to a local bridge without blocking opencode execution.
- [ ] T01-003: Define Pydantic v2 `AgentEvent` base envelope.
- [ ] T01-004: Define the first concrete event model for the selected opencode event.
- [ ] T01-005: Add discriminated union validation by event type.
- [ ] T01-006: Add `model_validate` coverage for valid event payloads.
- [ ] T01-007: Add validation coverage for missing required event fields.
- [ ] T01-008: Add validation coverage for unknown event types.
- [ ] T01-009: Implement SQLite event-log initialization with WAL mode.
- [ ] T01-010: Add `PRAGMA synchronous=NORMAL` for the local event log.
- [ ] T01-011: Add `PRAGMA busy_timeout=5000` or an explicitly justified alternative.
- [ ] T01-012: Serialize event-log writes with an application-level lock.
- [ ] T01-013: Add idempotent append behavior for duplicate event keys.
- [ ] T01-014: Add read-only event-log reader behavior.
- [ ] T01-015: Add tests or direct verification for duplicate event suppression.
- [ ] T01-016: Add tests or direct verification for WAL settings.
- [ ] T01-017: Emit initial telemetry metadata through the telemetry adapter.
- [ ] T01-018: Document the first event flow from opencode event to persisted row.
- [ ] T01-019: Document how the event envelope maps to and diverges from `stk` command envelopes.
- [ ] T01-020: Run lint, type check, and tests before closing the slice.

### Phase 2 Tasks

- [ ] T02-001: Introduce an AnyIO memory object stream for normalized events.
- [ ] T02-002: Define max buffer size and backpressure behavior.
- [ ] T02-003: Add an AnyIO task group for event handlers.
- [ ] T02-004: Add capacity limits for concurrent handler execution.
- [ ] T02-005: Add structured handler failure events.
- [ ] T02-006: Add cancellation behavior for shutdown.
- [ ] T02-007: Add tests for bounded queue behavior.
- [ ] T02-008: Add tests for handler failure isolation.
- [ ] T02-009: Add tests for graceful shutdown.
- [ ] T02-010: Document bus lifecycle and ownership.

### Phase 3 Tasks

- [ ] T03-001: Define `TaskAssigned` event schema.
- [ ] T03-002: Define `TaskCompleted` event schema.
- [ ] T03-003: Define `TaskFailed` event schema.
- [ ] T03-004: Define `HITLApprovalRequested` event schema.
- [ ] T03-005: Define `ArtifactWritten` event schema.
- [ ] T03-006: Define `ArtifactConflict` event schema.
- [ ] T03-007: Define `ArtifactResolved` event schema.
- [ ] T03-008: Define `BudgetWarning` event schema.
- [ ] T03-009: Define `BudgetExceeded` event schema.
- [ ] T03-010: Add artifact path/hash conflict detection policy.
- [ ] T03-011: Add Validator/HITL authority policy for artifact conflicts.
- [ ] T03-012: Add clarification gate where MiniMax proposes interpretations and Claude Validator or HITL validates.
- [ ] T03-013: Add tests proving clarification proposals cannot self-approve.
- [ ] T03-014: Add tests proving artifact conflict events are emitted deterministically.
- [ ] T03-015: Document RPIV workflow event mapping.

### Phase 4 Tasks

- [ ] T04-001: Define role-aligned experience record schema.
- [ ] T04-002: Add fields for role, stage, task, step, source event, reward, and retrieval keywords.
- [ ] T04-003: Define reward scoring inputs.
- [ ] T04-004: Define retrieval policy using explicit fields first.
- [ ] T04-005: Defer semantic embeddings unless a later phase verifies the dependency.
- [ ] T04-006: Define composite canary metric inputs.
- [ ] T04-007: Add structural validation component to canary metric.
- [ ] T04-008: Add test pass-rate component to canary metric.
- [ ] T04-009: Add model/self-judge component to canary metric with non-circular validation.
- [ ] T04-010: Add HITL gate before modifying skills, prompts, or routing defaults.
- [ ] T04-011: Add tests for canary promotion and rejection behavior.
- [ ] T04-012: Document learning and promotion policy.

### Phase 5 Tasks

- [ ] T05-001: Define RPIV saga states.
- [ ] T05-002: Define stage-level compensation actions.
- [ ] T05-003: Prohibit destructive git compensation by default.
- [ ] T05-004: Require reviewable compensation artifacts for file changes.
- [ ] T05-005: Add HITL escalation for compensation failures.
- [ ] T05-006: Add event-log replay command or script plan.
- [ ] T05-007: Add replay tests for reconstructing workflow state.
- [ ] T05-008: Add operational runbook for WAL checkpointing.
- [ ] T05-009: Add operational runbook for `SQLITE_BUSY` handling.
- [ ] T05-010: Add operational runbook for local-host-only WAL constraints.

## EARS Acceptance Criteria

- AC-001: WHEN the plan references opencode lifecycle events, THE SYSTEM SHALL use documented names such as `session.created`, `permission.asked`, and `tool.execute.after`.
- AC-002: IF a proposed API is not verified in current opencode docs, THEN THE SYSTEM SHALL mark it unverified and exclude it from implementation tasks.
- AC-003: WHEN MiniMax M2.7 is configured, THE SYSTEM SHALL use the direct MiniMax Token Plan model `MiniMax-M2.7` unless a later verified decision changes the provider.
- AC-004: IF exact opencode MiniMax provider config is not verified, THEN THE SYSTEM SHALL block provider implementation behind Phase 0 validation.
- AC-005: WHEN an agent event is persisted, THE SYSTEM SHALL validate it against a Pydantic v2 event schema before writing.
- AC-006: WHEN an event is appended to the durable log, THE SYSTEM SHALL use idempotency to prevent duplicate persisted events.
- AC-007: WHILE using SQLite WAL, THE SYSTEM SHALL serialize writes and document local-host constraints.
- AC-008: WHEN an event envelope borrows from `stk` conventions, THE SYSTEM SHALL distinguish it from `stk` command-result envelopes.
- AC-009: WHEN model telemetry is emitted, THE SYSTEM SHALL route GenAI attributes through a telemetry adapter.
- AC-010: IF OpenTelemetry GenAI conventions change, THEN THE SYSTEM SHALL localize changes to the telemetry adapter where possible.
- AC-011: WHEN artifact conflicts are detected, THE SYSTEM SHALL emit typed conflict events and require Validator or HITL resolution.
- AC-012: IF a clarification gate proposes an interpretation, THEN THE SYSTEM SHALL prevent that same gate from self-approving the interpretation.

## Risks And Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Event envelope is confused with `stk` command envelope. | Medium | High | Keep separate schemas; document mapping and differences. |
| opencode docs drift from local version `1.14.48`. | Medium | Medium | Verify local behavior in Phase 0 before implementation. |
| MiniMax direct provider config drifts from opencode docs or local `1.14.48` behavior. | Medium | High | Keep the Phase 0 verified config as the implementation baseline and smoke-test the local config before the first live provider call. |
| OpenTelemetry GenAI conventions change. | Medium | Medium | Use telemetry adapter and document Development status. |
| SQLite WAL contention causes `SQLITE_BUSY`. | Medium | Medium | Serialize writes, set busy timeout, add checkpoint policy, test contention. |
| Self-evolution modifies skills or routing unsafely. | Medium | High | Require canary pass and HITL approval before promotion. |
| Compensation logic damages user worktree. | Low | High | Avoid destructive git commands; require reviewable compensation artifacts. |
| grepai remains unavailable. | Medium | Low | Use Probe, `rg`, `rga`, and ast-grep until workspace is configured. |

## Open Questions

Q1: What is the exact opencode `opencode.json` provider configuration for MiniMax direct API?

Why it matters: provider implementation cannot be safely automated without verified config syntax.

**Resolved:** T00-007 validated the exact provider configuration; see Phase 0 Design Lock for verified config.

Blocking: No (resolved).

Q2: Should the event schema live in `ducktape`, `/home/dscv/Repo/stk`, or both?

Why it matters: schema ownership affects versioning, reuse, and release boundaries.

Suggested default: start in `ducktape`; later promote stable schema to `stk` only if shared CLI support is needed.

Blocking: Deferred for schema publication; not blocking for first local slice.

Q3: Should `stk schema` expose agent-event schemas?

Why it matters: exposing event schema through `stk` could make it a cross-project contract.

Suggested default: defer until the first event envelope is stable.

Blocking: No.

Q4: Should self-evolution ever modify skill files automatically?

Why it matters: autonomous prompt/skill mutation can create hard-to-review behavior changes.

Suggested default: require HITL approval for any durable prompt, skill, or routing mutation.

Blocking: No for early phases; Yes before Phase 4 promotion.

## Recommended Next Action

Begin Phase 1: implement the first event vertical slice using `session.created` as the trigger event, per the Phase 0 Design Lock. The MiniMax direct provider config is verified; proceed to implement the opencode plugin event capture layer.
