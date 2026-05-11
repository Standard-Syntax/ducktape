"""Documentation-level tests for Phase 0 verification and design lock.

These tests validate that the controlling plan and stale source plan have
reached Phase 0 completion criteria before any production runtime code is
implemented.
"""

import pathlib
import re
import subprocess

REPO_ROOT = pathlib.Path(__file__).parent.parent
CONTROLLING_PLAN = REPO_ROOT / "specs" / "event-driven-agent-runtime-plan.md"
STALE_PLAN = REPO_ROOT / "eda-multi-agent-plan.md"


def _read(path: pathlib.Path) -> str:
    if not path.exists():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8")


class TestPhase0TaskCompletion:
    """T00-001 through T00-020 must be marked complete or locked in a Phase 0 section."""

    def test_controlling_plan_exists(self) -> None:
        assert CONTROLLING_PLAN.exists(), "Controlling plan must exist"

    def test_t00_tasks_checked(self) -> None:
        text = _read(CONTROLLING_PLAN)
        missing = []
        for task_num in range(1, 21):
            task_id = f"T00-{task_num:03d}"
            pattern = rf"^\s*-\s+\[\s*[xX]\s*\]\s*{re.escape(task_id)}:"
            if not re.search(pattern, text, re.MULTILINE):
                missing.append(task_id)
        assert not missing, f"Phase 0 tasks must be marked complete: {missing}"

    def test_phase0_lock_section_exists(self) -> None:
        text = _read(CONTROLLING_PLAN)
        lock_patterns = [
            r"##\s+Phase\s+0\s+Lock",
            r"##\s+Phase\s+0\s+Design\s+Lock",
            r"##\s+Phase\s+0\s+Completion",
        ]
        assert any(re.search(p, text, re.IGNORECASE) for p in lock_patterns), (
            "Controlling plan must contain a Phase 0 lock section recording all decisions"
        )


class TestStaleApiNamesExcluded:
    """Stale opencode API names must not appear in active implementation guidance."""

    STALE_NAMES = [
        "sessionCreated",
        "toolExecuted",
        "promptAsync",
        "prompt_async",
        "/session/{sessionID}/prompt_async",
        "/session/{id}/prompt_async",
        "messageCreated",
        "session.idle",
    ]

    def test_no_stale_names_in_controlling_plan_implementation_sections(self) -> None:
        text = _read(CONTROLLING_PLAN)
        lines = text.splitlines()
        for i, line in enumerate(lines):
            for stale in self.STALE_NAMES:
                if stale in line:
                    context = " ".join(lines[max(0, i - 3) : i + 4]).lower()
                    allowed = (
                        "unverified" in context
                        or "deprecated" in context
                        or "exclude" in context
                        or "stale" in context
                        or "remove" in context
                        or "do not use" in context
                        or "must not" in context
                        or "should not" in context
                        or "exit criteria" in context
                        or "not" in context
                    )
                    assert allowed, (
                        f"Stale API name '{stale}' found in controlling plan line {i + 1} "
                        f"without deprecation context: {line.strip()!r}"
                    )

    def test_no_stale_names_in_stale_plan(self) -> None:
        """The stale source plan must be scrubbed or superseded."""
        text = _read(STALE_PLAN)
        lines = text.splitlines()
        bad = []
        for i, line in enumerate(lines):
            for stale in self.STALE_NAMES:
                if stale in line:
                    context = " ".join(lines[max(0, i - 3) : i + 4]).lower()
                    allowed = (
                        "unverified" in context
                        or "deprecated" in context
                        or "superseded" in context
                        or "historical" in context
                        or "stale" in context
                        or "do not use" in context
                        or "must not" in context
                        or "should not" in context
                    )
                    if not allowed:
                        bad.append((stale, i + 1, line.strip()))
        assert not bad, (
            f"Stale source plan still contains active stale API guidance: {bad}. "
            "These must be removed, marked as unverified/deprecated/historical, "
            "or the plan must be explicitly superseded."
        )


class TestMiniMaxProviderConfig:
    """Direct MiniMax provider configuration must be documented with verified fields."""

    REQUIRED_FRAGMENTS = [
        "provider",
        "@ai-sdk/openai-compatible",
        "baseURL",
        "https://api.minimax.io/v1",
        "{env:MINIMAX_API_KEY}",
        "MiniMax-M2.7",
    ]

    def test_minimax_direct_provider_configured(self) -> None:
        text = _read(CONTROLLING_PLAN)
        missing = [frag for frag in self.REQUIRED_FRAGMENTS if frag not in text]
        assert not missing, (
            f"Missing MiniMax provider config fragments: {missing}. "
            "Exact opencode provider config must be verified and documented in Phase 0."
        )

    def test_openrouter_slug_not_in_controlling_plan(self) -> None:
        text = _read(CONTROLLING_PLAN)
        slug = "openrouter/minimax/minimax-m2.7"
        assert slug not in text, (
            f"OpenRouter slug '{slug}' must not be in the primary provider path "
            "of the controlling plan."
        )

    def test_openrouter_slug_not_in_stale_plan(self) -> None:
        text = _read(STALE_PLAN)
        slug = "openrouter/minimax/minimax-m2.7"
        assert slug not in text, (
            f"OpenRouter slug '{slug}' must not appear in the stale source plan. "
            "It should be removed or the plan superseded."
        )


class TestProviderConfigContradiction:
    """Provider config must not be simultaneously complete and unverified/blocking."""

    def _extract_section(self, text: str, heading: str) -> str:
        """Extract text from a markdown heading until the next same-level heading."""
        pattern = rf"{re.escape(heading)}(.*?)(?=\n##\s|$)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        return match.group(1) if match else ""

    def test_t00_007_checked(self) -> None:
        text = _read(CONTROLLING_PLAN)
        assert re.search(r"^\s*-\s+\[\s*[xX]\s*\]\s*T00-007:", text, re.MULTILINE), (
            "T00-007 must be checked before asserting provider config is verified"
        )

    def test_phase0_marked_complete(self) -> None:
        text = _read(CONTROLLING_PLAN)
        assert "Phase 0 is complete" in text, "Controlling plan must mark Phase 0 as complete"

    def test_provider_not_listed_unverified_after_t00_007(self) -> None:
        text = _read(CONTROLLING_PLAN)
        unverified_section = self._extract_section(text, "## Remaining Unverified Items")
        assert "exact opencode `opencode.json` provider shape for MiniMax direct API" not in unverified_section, (
            "MiniMax provider config must not be listed as unverified after T00-007 is checked"
        )

    def test_provider_q1_not_blocking_after_phase0_complete(self) -> None:
        text = _read(CONTROLLING_PLAN)
        assert "Phase 0 is complete" in text
        q1_section = self._extract_section(text, "Q1:")
        # Q1 is specifically about the exact opencode provider configuration
        if "exact opencode `opencode.json` provider configuration for MiniMax direct API" in q1_section:
            assert "Blocking: Yes" not in q1_section, (
                "Q1 (exact opencode MiniMax provider config) must not be Blocking: Yes "
                "after Phase 0 is complete and T00-007 is checked"
            )

    def test_no_recommend_t00_007_after_phase0_complete(self) -> None:
        text = _read(CONTROLLING_PLAN)
        assert "Phase 0 is complete" in text
        rec_section = self._extract_section(text, "## Recommended Next Action")
        assert "T00-007" not in rec_section, (
            "T00-007 must not appear in Recommended Next Action after Phase 0 is complete"
        )


class TestGitignoreRules:
    """Root .gitignore must protect generated artifacts without ignoring source docs/tests."""

    REQUIRED_PATTERNS = [
        ".grepai/",
        ".opencode/",
        "*.bak.*",
        "__pycache__/",
        ".pytest_cache/",
    ]

    def test_root_gitignore_exists(self) -> None:
        gitignore = REPO_ROOT / ".gitignore"
        assert gitignore.exists(), "Root .gitignore must exist to protect generated/session artifacts"

    def test_gitignore_protects_generated_artifacts(self) -> None:
        gitignore = REPO_ROOT / ".gitignore"
        assert gitignore.exists()
        content = gitignore.read_text(encoding="utf-8")
        missing = [p for p in self.REQUIRED_PATTERNS if p not in content]
        assert not missing, f".gitignore missing required patterns: {missing}"

    def test_gitignore_does_not_ignore_source_docs(self) -> None:
        gitignore = REPO_ROOT / ".gitignore"
        assert gitignore.exists()
        content = gitignore.read_text(encoding="utf-8")
        lines = [line.strip() for line in content.splitlines()]
        for line in lines:
            if line.startswith("#") or not line:
                continue
            assert line != "specs/", f".gitignore must not ignore intended source docs: {line}"
            assert not line.startswith("tests/") or line.startswith("!tests/"), (
                f".gitignore must not ignore tests/ directory: {line}"
            )
            assert line not in ("test_*.py", "*.py"), (
                f".gitignore must not ignore test source files: {line}"
            )


class TestEventSchemaDecisions:
    """Event schema ownership, stk exposure, and envelope design must be decided."""

    def test_event_schema_ownership_decided(self) -> None:
        text = _read(CONTROLLING_PLAN)
        assert re.search(r"^\s*-\s+\[\s*[xX]\s*\]\s*T00-011:", text, re.MULTILINE), (
            "T00-011 must be checked or event schema ownership explicitly decided"
        )

    def test_stk_schema_exposure_decided(self) -> None:
        text = _read(CONTROLLING_PLAN)
        assert re.search(r"^\s*-\s+\[\s*[xX]\s*\]\s*T00-012:", text, re.MULTILINE), (
            "T00-012 must be checked or `stk schema` exposure explicitly decided"
        )

    def test_first_event_choice_decided(self) -> None:
        text = _read(CONTROLLING_PLAN)
        assert re.search(r"^\s*-\s+\[\s*[xX]\s*\]\s*T00-015:", text, re.MULTILINE), (
            "T00-015 must be checked or first event choice explicitly decided"
        )

    def test_event_envelope_fields_defined(self) -> None:
        text = _read(CONTROLLING_PLAN)
        assert re.search(r"^\s*-\s+\[\s*[xX]\s*\]\s*T00-016:", text, re.MULTILINE), (
            "T00-016 must be checked or event envelope fields explicitly defined"
        )

    def test_idempotency_key_defined(self) -> None:
        text = _read(CONTROLLING_PLAN)
        assert re.search(r"^\s*-\s+\[\s*[xX]\s*\]\s*T00-017:", text, re.MULTILINE), (
            "T00-017 must be checked or idempotency key construction explicitly defined"
        )

    def test_sqlite_wal_policy_defined(self) -> None:
        text = _read(CONTROLLING_PLAN)
        assert re.search(r"^\s*-\s+\[\s*[xX]\s*\]\s*T00-018:", text, re.MULTILINE), (
            "T00-018 must be checked or SQLite WAL pragmas and checkpoint policy explicitly defined"
        )

    def test_telemetry_adapter_boundary_defined(self) -> None:
        text = _read(CONTROLLING_PLAN)
        assert re.search(r"^\s*-\s+\[\s*[xX]\s*\]\s*T00-019:", text, re.MULTILINE), (
            "T00-019 must be checked or telemetry adapter boundaries explicitly defined"
        )

    def test_otel_genai_risk_documented(self) -> None:
        text = _read(CONTROLLING_PLAN)
        assert re.search(r"^\s*-\s+\[\s*[xX]\s*\]\s*T00-020:", text, re.MULTILINE), (
            "T00-020 must be checked or OpenTelemetry GenAI Development-status risk explicitly documented"
        )

    def test_stk_envelope_distinction_documented(self) -> None:
        text = _read(CONTROLLING_PLAN)
        assert re.search(r"^\s*-\s+\[\s*[xX]\s*\]\s*T00-014:", text, re.MULTILINE), (
            "T00-014 must be checked or agent event envelope distinction from `stk` command results explicitly documented"
        )


class TestVerifiedEventNames:
    """Verified opencode lifecycle event names must be used."""

    def test_verified_event_names_in_plan(self) -> None:
        text = _read(CONTROLLING_PLAN)
        verified_events = [
            "session.created",
            "session.compacted",
            "permission.asked",
            "permission.replied",
            "tool.execute.before",
            "tool.execute.after",
        ]
        for event_name in verified_events:
            assert event_name in text, f"Plan must reference verified event `{event_name}`"

    def test_no_deprecated_session_created_in_controlling_plan(self) -> None:
        text = _read(CONTROLLING_PLAN)
        # sessionCreated should not appear outside unverified/deprecated contexts
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if "sessionCreated" in line:
                context = " ".join(lines[max(0, i - 3) : i + 4]).lower()
                assert "unverified" in context or "not" in context, (
                    f"Deprecated `sessionCreated` found in controlling plan line {i + 1}"
                )

    def test_no_deprecated_tool_executed_in_controlling_plan(self) -> None:
        text = _read(CONTROLLING_PLAN)
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if "toolExecuted" in line:
                context = " ".join(lines[max(0, i - 3) : i + 4]).lower()
                assert "unverified" in context or "not" in context, (
                    f"Deprecated `toolExecuted` found in controlling plan line {i + 1}"
                )


class TestGitignoreOpencodeSourcePaths:
    """AC-001: .gitignore must not blanket-ignore planned .opencode/ source paths."""

    def _git_check_ignore(self, path: str) -> bool:
        """Return True if *path* is ignored by git, False otherwise."""
        result = subprocess.run(
            ["git", "check-ignore", path],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        # exit 0 => ignored, exit 1 => not ignored
        return result.returncode == 0

    def test_opencode_plugin_event_forwarder_not_ignored(self) -> None:
        assert not self._git_check_ignore(
            ".opencode/plugins/event-forwarder.ts"
        ), ".opencode/plugins/event-forwarder.ts must not be ignored by git"

    def test_opencode_skills_example_not_ignored(self) -> None:
        assert not self._git_check_ignore(
            ".opencode/skills/example/SKILL.md"
        ), ".opencode/skills/example/SKILL.md must not be ignored by git"

    def test_opencode_runtime_artifacts_remain_ignored(self) -> None:
        assert self._git_check_ignore(
            ".opencode/context-gate-events.jsonl"
        ), ".opencode/context-gate-events.jsonl must remain ignored (runtime artifact)"


class TestOpencodeJsonPortable:
    """AC-002: Local opencode.json must be protected or made portable."""

    def test_opencode_json_is_ignored(self) -> None:
        result = subprocess.run(
            ["git", "check-ignore", "opencode.json"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            "Root opencode.json must be ignored to protect local machine config from accidental commit"
        )

    def test_opencode_json_example_exists(self) -> None:
        example = REPO_ROOT / "opencode.json.example"
        assert example.exists(), (
            "opencode.json.example must exist as a portable template without local paths or secrets"
        )

    def test_opencode_json_example_has_no_absolute_local_paths(self) -> None:
        example = REPO_ROOT / "opencode.json.example"
        assert example.exists()
        text = example.read_text(encoding="utf-8")
        assert "/home/dscv/Repo/ducktape" not in text, (
            "opencode.json.example must not contain machine-local absolute paths"
        )

    def test_opencode_json_example_has_no_api_key_literals(self) -> None:
        example = REPO_ROOT / "opencode.json.example"
        assert example.exists()
        text = example.read_text(encoding="utf-8")
        # Reject obvious hard-coded API key patterns
        bad_patterns = [
            r'"apiKey"\s*:\s*"[a-zA-Z0-9_-]{20,}"',
            r'"api_key"\s*:\s*"[a-zA-Z0-9_-]{20,}"',
            r'"token"\s*:\s*"[a-zA-Z0-9_-]{20,}"',
        ]
        for pattern in bad_patterns:
            assert not re.search(pattern, text), (
                f"opencode.json.example must not contain hard-coded API key literals "
                f"(matched pattern: {pattern!r})"
            )

    def test_opencode_json_example_has_portable_placeholders(self) -> None:
        example = REPO_ROOT / "opencode.json.example"
        assert example.exists()
        text = example.read_text(encoding="utf-8")
        # Expect at least one placeholder marker such as <workspace-path>, {env:...}, or CHANGE_ME
        has_placeholder = bool(
            re.search(r"<[^>]+>", text)
            or "{env:" in text
            or "CHANGE_ME" in text
            or "YOUR_" in text
            or "placeholder" in text.lower()
        )
        assert has_placeholder, (
            "opencode.json.example must include portable placeholder guidance "
            "(e.g., <workspace-path>, {env:...}, CHANGE_ME)"
        )


class TestProviderWordingScrubbed:
    """AC-003: Controlling plan must not claim exact provider config is still Phase 0 validation after T00-007 is done."""

    STALE_PHRASE = "Exact opencode provider config remains Phase 0 validation"

    def test_stale_provider_validation_phrase_removed(self) -> None:
        text = _read(CONTROLLING_PLAN)
        assert self.STALE_PHRASE not in text, (
            f"Controlling plan must not contain stale phrase: {self.STALE_PHRASE!r}. "
            "T00-007 is checked and Q1 is resolved; provider config is verified, not remaining validation."
        )

    def test_minimax_provider_described_as_verified(self) -> None:
        text = _read(CONTROLLING_PLAN)
        # After fix, the plan should still describe MiniMax provider config as verified
        assert "MiniMax direct API provider configuration is verified" in text or (
            "provider config is verified" in text
        ), (
            "Controlling plan should still describe MiniMax provider config as verified"
        )


class TestStalePlanSessionIdleCodeBlocks:
    """AC-004: Stale plan must not contain runnable fenced code blocks that forward or branch on session.idle."""

    def _extract_fenced_code_blocks(self, text: str) -> list[str]:
        """Return all triple-backtick fenced code blocks."""
        pattern = r"```[\w]*\n(.*?)\n```"
        return re.findall(pattern, text, re.DOTALL)

    def test_no_session_idle_in_fenced_code_blocks(self) -> None:
        text = _read(STALE_PLAN)
        blocks = self._extract_fenced_code_blocks(text)
        bad_blocks = []
        for idx, block in enumerate(blocks):
            if "session.idle" in block:
                bad_blocks.append((idx, "session.idle"))
            elif "session.status" in block and "idle" in block:
                bad_blocks.append((idx, "session.status + idle"))
        assert not bad_blocks, (
            f"Stale plan contains {len(bad_blocks)} fenced code block(s) referencing "
            f"session.idle or session.status/idle: {bad_blocks}. "
            "These must be removed or converted to non-runnable commentary."
        )
