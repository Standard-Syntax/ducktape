# Task
fix issues from review team

# Context tool plan
- grepai: skipped — review findings identify exact files and strings.
- Probe: skipped — no Python source symbols or call sites are involved.
- rg/rga: used — exact checks for provider wording, stale event names, ignore behavior, and local config.
- ast-grep: skipped — no structural code refactor.
- Context7: skipped — opencode provider shape was already verified in Phase 0; this task fixes local consistency issues.
- Exa: skipped — no external evidence needed.

# Context findings
## grepai
- Skipped. Exact files are known from review: `.gitignore`, `opencode.json`, `specs/event-driven-agent-runtime-plan.md`, `eda-multi-agent-plan.md`, and `tests/test_phase0_plan.py`.

## Probe
- Skipped. No symbols/functions/classes are being edited.

## rg/rga
- `specs/event-driven-agent-runtime-plan.md:24` still says `Exact opencode provider config remains Phase 0 validation` even though line 37 says the MiniMax provider config is verified and line 45 says opencode provider shape is verified.
- `specs/event-driven-agent-runtime-plan.md:189` lists planned future source file `.opencode/plugins/event-forwarder.ts`.
- `.gitignore:3` currently ignores all `.opencode/`.
- `git check-ignore -v .opencode/plugins/event-forwarder.ts .opencode/skills/example/SKILL.md opencode.json || true` reports `.opencode/plugins/event-forwarder.ts` and `.opencode/skills/example/SKILL.md` ignored by `.gitignore:3`; `opencode.json` is not ignored.
- `opencode.json:6-10` contains a machine-local absolute path `/home/dscv/Repo/ducktape`.
- `eda-multi-agent-plan.md:734-738` still contains a runnable `session.idle` forwarding block inside a TypeScript code fence.

## ast-grep
- Skipped. No syntax-aware rewrite needed.

## Context7 / Exa
- Skipped. Existing Phase 0 evidence already records the verified MiniMax provider shape.

# Acceptance criteria
- [x] AC-001: `.gitignore` must not blanket-ignore `.opencode/`; planned source paths `.opencode/plugins/event-forwarder.ts` and `.opencode/skills/example/SKILL.md` must not be ignored by normal git ignore rules.
- [x] AC-002: Local `opencode.json` must be protected from accidental commit or made portable. Preferred minimal fix: ignore root `opencode.json` and add a portable `opencode.json.example` without absolute local paths or secrets.
- [x] AC-003: The controlling plan must no longer say exact opencode provider config remains Phase 0 validation after T00-007 is checked and Q1 is resolved.
- [x] AC-004: The superseded plan must not contain runnable fenced code blocks that forward or branch on `session.idle`.

# Files to modify
- `.gitignore`
- `opencode.json.example` (create if using local-config template approach)
- `specs/event-driven-agent-runtime-plan.md`
- `eda-multi-agent-plan.md`
- `tests/test_phase0_plan.py`
- `.opencode/loop-task.md` (audit/state only)

# Files explicitly out of scope
- `pyproject.toml` unless dependency/config change is explicitly approved
- `uv.lock` unless dependency/config change is explicitly approved
- `opencode.json` local machine config unless choosing to make it portable instead of ignoring it
- `.grepai/**`
- `.opencode/context-gate-events.jsonl`
- production runtime files such as `agent_runtime/**`

# Code context
## `.gitignore`
```gitignore
# Generated and session artifacts
.grepai/
.opencode/

# Context gate events (runtime log, not source)
.opencode/context-gate-events.jsonl
```

## Current ignore behavior
```text
.gitignore:3:.opencode/    .opencode/plugins/event-forwarder.ts
.gitignore:3:.opencode/    .opencode/skills/example/SKILL.md
```

## `opencode.json`
```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "grepai": {
      "type": "local",
      "command": [
        "grepai",
        "mcp-serve",
        "/home/dscv/Repo/ducktape"
      ],
      "enabled": true,
      "timeout": 10000
    }
  }
}
```

## Provider wording conflict
```markdown
| Use MiniMax direct Token Plan API. | MiniMax docs verify model `MiniMax-M2.7`, base URL `https://api.minimax.io/v1`, and env var `MINIMAX_API_KEY`. | Remove OpenRouter as the primary provider path. Exact opencode provider config remains Phase 0 validation. |
```

## `session.idle` code block
```typescript
// ⚠️ UNVERIFIED: session.idle event not verified in opencode docs
// This event type is superseded; do not use in implementation without verification
if (event.type === "session.status" && event.properties.status.type === "idle") {
  await forward({ event_type: "session.idle", producer_id: "opencode", // eslint-disable-line no-unused-vars
                  payload: { status: "idle" } })
}
```

## Current tests
- `tests/test_phase0_plan.py` checks stale names in line context, but it does not fail on stale names inside fenced code when nearby comments contain `unverified`/`superseded`.
- `tests/test_phase0_plan.py` currently requires `.opencode/`, which conflicts with planned source files under `.opencode/plugins/`.

# Test file path
- `tests/test_phase0_plan.py`

# Latest verification result
- `py-tester` returned TESTS_READY.
- RED command: `uv run pytest tests/test_phase0_plan.py -v`.
- New failures: 9 failed, 2 passed, 28 deselected for focused review-fix tests.
- Failing coverage maps to AC-001 through AC-004:
  - `.opencode/plugins/event-forwarder.ts` and `.opencode/skills/example/SKILL.md` are currently ignored.
  - `opencode.json` is not ignored and `opencode.json.example` does not exist.
  - stale provider phrase remains in controlling plan.
  - `session.idle` remains in a fenced code block.
- Tester tracked file gate: `/tmp/tester-new-files.txt` empty; no tracked non-test file added by tester.
- `py-implementer` reported GREEN:
  - `uv run pytest tests/test_phase0_plan.py -v` => 39 passed.
  - `uv run ruff check .` => passed.
  - `uv run ty check .` => passed.
  - `uv run pytest -v` => 39 passed.
- Orchestrator local verification:
  - `uv run pytest tests/test_phase0_plan.py -v` => 39 passed.
  - `git check-ignore -v .opencode/plugins/event-forwarder.ts .opencode/skills/example/SKILL.md opencode.json .opencode/context-gate-events.jsonl || true` shows only `opencode.json` and `.opencode/context-gate-events.jsonl` ignored.
  - `.gitignore` now ignores `.opencode/context-gate-events.jsonl` and `opencode.json`, not `.opencode/`.
  - `opencode.json.example` exists and uses `<workspace-path>`.
  - `specs/event-driven-agent-runtime-plan.md:24` now says provider config is verified in Phase 0 Design Lock.
  - `eda-multi-agent-plan.md` no longer has the `session.idle` TypeScript block.

# Unresolved critic feedback
- Critic iteration 1 verdict: ACCEPTABLE.
- Blocking issues: 0.
- Follow-up only: `tests/test_phase0_plan.py` still has a fragile substring check where REQUIRED_PATTERNS includes `.opencode/` and passes because `.opencode/context-gate-events.jsonl` contains that substring. No behavioral defect; follow-up OK.

# Tool constraints for subagents
- `py-tester`: may use read-only local search; may only create/modify test files.
- `py-implementer`: may use local search; may only edit files listed under "Files to modify".
- `py-critic`: may use read-only local search; must not edit files.

# Final loop summary
## TDD phase
- TESTS_READY.
- RED: 9 failed, 2 passed, 28 deselected for the focused review-fix tests.
- GREEN: `uv run pytest tests/test_phase0_plan.py -v` => 39 passed.

## Context tools used
- grepai: skipped — exact review findings and files were known.
- Probe: skipped — no Python symbols or implementation references involved.
- rg/rga: used — exact string and git-ignore checks for provider wording, `session.idle`, `.opencode/`, and `opencode.json`.
- ast-grep: skipped — no structural rewrite.
- Context7: skipped — provider shape already verified in Phase 0.
- Exa: skipped — no external research needed.

## Critic iterations
- 1.
- Verdict: ACCEPTABLE.
- Blocking issues: 0.
- Low follow-up: tighten one `.gitignore` test assertion to avoid substring ambiguity.

## Files changed
- `.gitignore`
- `opencode.json.example`
- `specs/event-driven-agent-runtime-plan.md`
- `eda-multi-agent-plan.md`
- `tests/test_phase0_plan.py`
- `.opencode/loop-task.md`

## Final validation
- `git diff --name-only` => `eda-multi-agent-plan.md` (tracked diff only; other changed artifacts are untracked).
- `git diff --stat` => `eda-multi-agent-plan.md | 174 +++++++++++-------------------------------------`.
- `rg "TODO|FIXME|pass|NotImplemented" .` found only existing prose/code-example uses of `pass`, no TODO/FIXME/NotImplemented action markers.
- `uv run pytest -v` => 39 passed.
- `uv run ruff check .` => passed.
- `uv run ty check .` => passed.
- `git check-ignore -v .opencode/plugins/event-forwarder.ts .opencode/skills/example/SKILL.md opencode.json .opencode/context-gate-events.jsonl || true` => only `opencode.json` and `.opencode/context-gate-events.jsonl` ignored.

## Final impact summary
- `.opencode/plugins/**` and `.opencode/skills/**` planned source paths are no longer hidden by `.gitignore`.
- Local `opencode.json` is ignored; portable `opencode.json.example` exists with `<workspace-path>` placeholder.
- Controlling plan no longer claims provider config remains Phase 0 validation.
- Superseded plan no longer contains runnable fenced code that forwards or branches on `session.idle`.
