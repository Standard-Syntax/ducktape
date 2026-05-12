# Task
fix findings 1 and 2

# Context tool plan
- grepai: skip — review findings identify exact files and symbols.
- Probe: use — editing existing `AgentEvent.model_validate`, `validate_event`, and package/spec references.
- rg/rga: use — exact checks for `validate_event`, stale `borrow`, `schemaVersion`, and structured error wording; rga not needed because no PDFs/archives are involved.
- ast-grep: skip — targeted edits, no structural codemod.
- Context7: skip — Pydantic behavior was reproduced locally and no dependency API uncertainty remains.
- Exa: skip — no external evidence needed.

# Context findings
## grepai
- Skipped. The code review identified exact paths and symbols.

## Probe
- `agent_runtime/events.py` defines `AgentEvent.model_validate()` at lines 88-93. It already forwards `**kwargs` to `_event_adapter.validate_python(obj, **kwargs)` when `cls is AgentEvent`.
- `agent_runtime/events.py` defines `validate_event(data: Any) -> SessionCreatedEvent` at lines 131-204. It manually pre-validates dict/event_type/deprecated names, then calls `_event_adapter.validate_python(data)` without accepting or forwarding kwargs.
- `validate_event` is documented as the canonical entrypoint, so it should not be less capable than `AgentEvent.model_validate` for supported Pydantic validation kwargs.

## rg/rga
- `tests/test_events.py:257-278` covers `AgentEvent.model_validate(data, extra="allow")`, but no test covers `validate_event(data, extra="allow")`.
- Runtime repro before this task: `validate_event(data, extra="allow")` raises `TypeError: validate_event() got an unexpected keyword argument 'extra'`.
- `agent_runtime/__init__.py:8-10` points to `specs/event-driven-agent-runtime-plan.md` as the authoritative field list.
- `specs/event-driven-agent-runtime-plan.md:60` says events can borrow `stk` conventions such as `schemaVersion` and structured error fields.
- `specs/event-driven-agent-runtime-plan.md:295` says agent events borrow `schemaVersion` and structured error fields while adding event-specific fields.
- `specs/event-driven-agent-runtime-plan.md:447` phrases AC-008 around envelopes borrowing from `stk` conventions.

## ast-grep
- Skipped. No structural rewrite planned.

## Context7 / Exa
- Skipped. No external documentation needed.

# Acceptance criteria
- [ ] AC-001: `validate_event()` accepts supported Pydantic validation kwargs and forwards them to `_event_adapter.validate_python()`, matching `AgentEvent.model_validate()` behavior for `extra="allow"`.
- [ ] AC-002: A focused regression test fails before implementation and passes after implementation for `validate_event(data, extra="allow")`.
- [ ] AC-003: `specs/event-driven-agent-runtime-plan.md` no longer says agent event envelopes borrow `stk` `schemaVersion` or structured error fields; it states the event envelope is distinct and uses the implemented event fields.
- [ ] AC-004: Existing event behavior remains intact; focused tests, full tests with injected deps, ruff, and type checking pass or known environment-only warnings are documented.

# Files to modify
- `agent_runtime/events.py`
- `tests/test_events.py`
- `specs/event-driven-agent-runtime-plan.md`
- `.opencode/loop-task.md` (audit trail only)

# Files explicitly out of scope
- `pyproject.toml` unless dependency/config change is explicitly approved
- `uv.lock` unless dependency/config change is explicitly approved
- generated files unless explicitly required
- `agent_runtime/__pycache__/` and `.pytest_cache/`

# Code context
Current `AgentEvent.model_validate()`:

```python
@classmethod
def model_validate(cls, obj: Any, **kwargs: Any) -> "AgentEvent":
    """Discriminated-union entrypoint: returns SessionCreatedEvent for session.created."""
    if cls is AgentEvent:
        return _event_adapter.validate_python(obj, **kwargs)
    return super().model_validate(obj, **kwargs)
```

Current `validate_event()`:

```python
def validate_event(data: Any) -> SessionCreatedEvent:
    """Validate a raw event dictionary and return the typed event model.

    This is the canonical entrypoint for event validation (AC-005).  It
    validates the ``event_type`` field and rejects unknown event types with
    a ``pydantic.ValidationError``.

    The deprecated ``sessionCreated`` name is explicitly rejected.
    Non-dict inputs raise ``ValidationError``, not ``TypeError``.
    """
    # Guard against non-dict inputs: must raise ValidationError, not TypeError
    if data is None or not isinstance(data, dict):
        raise ValidationError.from_exception_data(...)

    if "event_type" not in data:
        raise ValidationError.from_exception_data(...)

    raw_event_type = data["event_type"]
    if not isinstance(raw_event_type, str):
        raise ValidationError.from_exception_data(...)
    event_type: str = raw_event_type

    if event_type == "sessionCreated":
        raise ValidationError.from_exception_data(...)

    return _event_adapter.validate_python(data)
```

Current test coverage around kwargs:

```python
class TestModelValidateKwargsForwarding:
    def test_agent_event_model_validate_forwards_extra_allow(self) -> None:
        data = _valid_session_created_dict()
        data["extra_field"] = "extra_value"

        concrete = SessionCreatedEvent.model_validate(data, extra="allow")
        assert isinstance(concrete, SessionCreatedEvent)
        assert concrete.model_extra is not None
        assert concrete.model_extra["extra_field"] == "extra_value"

        event = AgentEvent.model_validate(data, extra="allow")
        assert isinstance(event, SessionCreatedEvent)
        assert event.model_extra is not None
        assert event.model_extra["extra_field"] == "extra_value"
```

Current stale spec snippets:

```markdown
The event schema should be separate from `stk` command results. It can borrow `stk` conventions such as `schemaVersion` and structured error fields, but it needs event-specific fields including `event_id`, `event_type`, `producer`, `correlation_id`, `occurred_at`, and `payload`.

Agent event envelopes are **not** `stk` command-result envelopes. Agent events borrow some conventions (`schemaVersion`, structured error fields) but add event-specific fields: `event_id`, `event_type`, `producer`, `correlation_id`, `occurred_at`, and `payload`.

- AC-008: WHEN an event envelope borrows from `stk` conventions, THE SYSTEM SHALL distinguish it from `stk` command-result envelopes.
```

# Test file path
- `tests/test_events.py`

# Latest verification result
- Pre-task focused tests: `uv run --with pydantic --with pytest python -m pytest tests/test_events.py -q` => 56 passed.
- Pre-task full tests: `uv run --with pydantic --with pytest python -m pytest -q` => 95 passed.
- Pre-task ruff: `uv run --with pydantic --with ruff ruff check .` => passed.
- Pre-task basedpyright focused: `uv run --with pydantic --with pytest --with basedpyright basedpyright agent_runtime tests/test_events.py` => 0 errors, 79 warnings.
- Pre-task repro: `validate_event(data, extra="allow")` raises `TypeError`.
- Tester verdict: TESTS_READY.
- Tester added `TestModelValidateKwargsForwarding::test_validate_event_forwards_extra_allow` in `tests/test_events.py`.
- RED command: `uv run --with pydantic --with pytest python -m pytest tests/test_events.py -v`.
- RED result: 1 failed, 56 passed. Failure is `TypeError: validate_event() got an unexpected keyword argument 'extra'`.
- Tester file gate: required tracked diff gate output was empty; `git status --short` still shows only pre-existing untracked `agent_runtime/` and `tests/test_events.py` plus modified `.opencode/loop-task.md`.
- Implementer result: GREEN reported.
- Implementer changed `agent_runtime/events.py` so `validate_event(data: Any, **kwargs: Any)` forwards `_event_adapter.validate_python(data, **kwargs)`.
- Implementer changed `specs/event-driven-agent-runtime-plan.md` lines 60, 295, and AC-008 to describe agent event envelopes as distinct from `stk` command-result envelopes.
- Implementer verification reported: focused kwargs tests passed, full suite 96 passed, ruff passed, focused basedpyright 0 errors with warnings.
- Orchestrator post-implementation exact check still finds `specs/event-driven-agent-runtime-plan.md:23` with phrase `Agent event envelopes may borrow conventions but must not pretend to be stk command results`; critic should decide whether this remains within AC-003 scope.

# Unresolved critic feedback
## Critic Feedback — Iteration 1

**Status:** NEEDS WORK
**Failing criterion:** AC-003
**Evidence:** `specs/event-driven-agent-runtime-plan.md:23` still says `Agent event envelopes may borrow conventions but must not pretend to be stk command results.` The critic judged this as stale normative permission that contradicts the event envelope design.
**Required correction:** Replace the line 23 planning-impact wording with language that says agent event envelopes are deliberately distinct from `stk` command-result envelopes, use different fields, and are not interchangeable. Then re-run exact wording checks.
**Priority:** HIGH

## Implementer Response — Iteration 2

**Status:** FIXED
**Changed file:** `specs/event-driven-agent-runtime-plan.md`
**Evidence:** Line 23 now says `Agent event envelopes are deliberately distinct from stk command-result envelopes, use different fields (...), and are not interchangeable.`
**Exact check:** `grep` still finds `schemaVersion` where the spec factually documents `stk` fields, and `SHALL NOT borrow` in AC-008; no `may borrow` or `borrow conventions` phrase remains.

## Review Finding 1 — validate_event kwargs
**Status:** REQUEST CHANGES
**Failing criterion:** AC-001 / AC-002
**Evidence:** `agent_runtime/events.py:131-204` does not accept kwargs and calls `_event_adapter.validate_python(data)` without forwarding kwargs. Runtime repro raises `TypeError` for `validate_event(data, extra="allow")`.
**Required correction:** Add `**kwargs` support to `validate_event()` and forward kwargs into `_event_adapter.validate_python(data, **kwargs)`. Add a focused regression test.
**Priority:** HIGH

## Review Finding 2 — stale authoritative spec wording
**Status:** REQUEST CHANGES
**Failing criterion:** AC-003
**Evidence:** `agent_runtime/__init__.py:8-10` points to `specs/event-driven-agent-runtime-plan.md` as authoritative, while spec lines 60 and 295 still claim agent events borrow `stk` `schemaVersion` and structured error fields.
**Required correction:** Rewrite those spec statements and AC-008 so event envelopes are described as distinct from `stk` command-result envelopes and limited to implemented event fields.
**Priority:** MEDIUM

# Tool constraints for subagents
- `py-tester`: may use read-only local search; may only create/modify test files.
- `py-implementer`: may use local search; may only edit files listed under "Files to modify".
- `py-critic`: may use read-only local search; must not edit code.

# Long-task prompt for subagents
This is a lengthy task. Make full use of the available context window (within 200k tokens total). Complete each part thoroughly before moving on.

# Final loop summary

## TDD phase
- Status: TESTS_READY.
- Tester added `TestModelValidateKwargsForwarding::test_validate_event_forwards_extra_allow`.
- RED: `uv run --with pydantic --with pytest python -m pytest tests/test_events.py -v` => 1 failed, 56 passed. Failure: `TypeError: validate_event() got an unexpected keyword argument 'extra'`.
- GREEN: `uv run --with pydantic --with pytest python -m pytest tests/test_events.py -v` => 57 passed.

## Context tools used
- grepai: skipped — exact review findings and files were known.
- Probe: used — extracted `AgentEvent.model_validate` and `validate_event` definitions.
- rg/rga: used — exact checks for `validate_event`, `borrow`, `schemaVersion`, and structured error wording; rga not needed.
- ast-grep: skipped — no structural rewrite.
- Context7: skipped — no dependency API uncertainty.
- Exa: skipped — no external information needed.

## Critic iterations
- Iteration 1 verdict: NEEDS WORK. Blocking issue: `specs/event-driven-agent-runtime-plan.md:23` still said agent event envelopes may borrow conventions.
- Iteration 2 verdict: ACCEPTABLE. Blocking issues: 0.

## Files changed
- `.opencode/loop-task.md`: loop state and audit trail.
- `agent_runtime/events.py`: `validate_event(data: Any, **kwargs: Any)` now forwards kwargs to `_event_adapter.validate_python(data, **kwargs)`.
- `tests/test_events.py`: added regression coverage for `validate_event(data, extra="allow")`.
- `specs/event-driven-agent-runtime-plan.md`: removed stale `stk` borrowing language and clarified agent event envelopes are distinct and non-interchangeable.

## Final validation
- `git diff --name-only` => `.opencode/loop-task.md`, `specs/event-driven-agent-runtime-plan.md` (tracked diffs only; `agent_runtime/` and `tests/test_events.py` remain untracked in `git status`).
- `git diff --stat` => 2 tracked files changed, 141 insertions, 147 deletions.
- `rg "TODO|FIXME|pass|NotImplemented" .` found existing planning-document uses and expected `pass  # expected` in `tests/test_events.py`; no new unresolved TODO/FIXME/NotImplemented markers.
- Default `uv run pytest -v` fails during collection because the bare environment lacks `pydantic`.
- Default `uv run ruff check .` passes.
- Default `uv run ty check .` reports unresolved imports for `pydantic`/`pytest` in the bare environment.
- Dependency-injected focused tests: `uv run --with pydantic --with pytest python -m pytest tests/test_events.py -v` => 57 passed.
- Dependency-injected full tests: `uv run --with pydantic --with pytest python -m pytest -v` => 96 passed.
- Dependency-injected ruff: `uv run --with pydantic --with ruff ruff check .` => passed.
- Dependency-injected basedpyright: `uv run --with pydantic --with pytest --with basedpyright basedpyright .` => 0 errors, 97 warnings.

## Final verdict
Loop complete. All acceptance criteria are satisfied. Critic final verdict: ACCEPTABLE. Remaining default-environment failures are dependency declaration/environment issues already present for Pydantic tests, not behavior regressions from this loop.
