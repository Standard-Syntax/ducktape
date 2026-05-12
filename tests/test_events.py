"""Tests for AC-005: Pydantic v2 event schema validation.

These tests define the expected public API for ``agent_runtime.events`` and
drive a minimal implementation of the first event vertical slice
(``session.created``).
"""

from datetime import datetime, timezone
from typing import Any, Literal
import typing

import pytest
from pydantic import ValidationError
from unittest.mock import Mock

from agent_runtime.events import (
    AgentEvent,
    SessionCreatedEvent,
    SessionCreatedPayload,
    validate_event,
)


def _valid_session_created_dict(correlation_id: str | None = None) -> dict[str, Any]:
    """Return a minimal valid ``session.created`` event dictionary."""
    data = {
        "event_id": "evt-test-001",
        "event_type": "session.created",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "producer": "opencode",
        "payload": {"session_id": "sess-abc-123"},
    }
    if correlation_id is not None:
        data["correlation_id"] = correlation_id
    return data


class TestValidSessionCreatedEvent:
    """A valid ``session.created`` payload must validate and expose typed data."""

    def test_validate_event_entrypoint_returns_typed_event(self) -> None:
        data = _valid_session_created_dict()
        event = validate_event(data)
        assert isinstance(event, SessionCreatedEvent)
        assert event.event_id == "evt-test-001"
        assert event.event_type == "session.created"
        assert event.producer == "opencode"

    def test_model_validate_also_works(self) -> None:
        """``AgentEvent.model_validate`` must act as a discriminated union entrypoint."""
        data = _valid_session_created_dict()
        event = AgentEvent.model_validate(data)
        assert isinstance(event, SessionCreatedEvent)
        assert event.payload.session_id == "sess-abc-123"

    def test_payload_is_typed_session_created_payload(self) -> None:
        data = _valid_session_created_dict()
        event = validate_event(data)
        assert isinstance(event.payload, SessionCreatedPayload)
        assert event.payload.session_id == "sess-abc-123"

    def test_optional_correlation_id_accepted(self) -> None:
        data = _valid_session_created_dict(correlation_id="corr-xyz")
        event = validate_event(data)
        assert event.correlation_id == "corr-xyz"

    def test_missing_correlation_id_is_accepted(self) -> None:
        data = _valid_session_created_dict()
        assert "correlation_id" not in data
        event = validate_event(data)
        assert event.correlation_id is None


class TestRequiredBaseFields:
    """Required base fields must be enforced by the schema."""

    @pytest.mark.parametrize(
        "field",
        [
            "event_id",
            "event_type",
            "producer",
            "occurred_at",
            "payload",
        ],
    )
    def test_missing_required_field_raises_validation_error(self, field: str) -> None:
        data = _valid_session_created_dict()
        del data[field]
        with pytest.raises(ValidationError):
            validate_event(data)


class TestUnknownEventType:
    """Unknown ``event_type`` values must be rejected."""

    def test_unknown_event_type_rejected(self) -> None:
        data = _valid_session_created_dict()
        data["event_type"] = "session.unknown"
        with pytest.raises(ValidationError):
            validate_event(data)

    def test_deprecated_session_created_rejected(self) -> None:
        """The old ``sessionCreated`` name must not be accepted."""
        data = _valid_session_created_dict()
        data["event_type"] = "sessionCreated"
        with pytest.raises(ValidationError):
            validate_event(data)


class TestPayloadConstraints:
    """The ``session.created`` payload must contain at least ``session_id``."""

    def test_payload_missing_session_id_raises(self) -> None:
        data = _valid_session_created_dict()
        data["payload"] = {}
        with pytest.raises(ValidationError):
            validate_event(data)


class TestStkEnvelopeDistinction:
    """AC-008: The schema must reject ``stk`` command-result envelope shapes."""

    def test_stk_command_envelope_rejected(self) -> None:
        """A bare ``stk`` command result lacks event-specific fields."""
        data = {
            "schemaVersion": 1,
            "ok": True,
            "command": "schema",
            "data": {},
            "errors": [],
            "warnings": [],
            "elapsed_ms": 42,
        }
        with pytest.raises(ValidationError):
            validate_event(data)

    def test_stk_envelope_with_event_type_but_no_event_id_rejected(self) -> None:
        """Borrowing ``event_type`` without ``event_id`` is still not an event."""
        data = {
            "schemaVersion": 1,
            "event_type": "session.created",
            "ok": True,
            "command": "schema",
            "data": {},
            "errors": [],
            "warnings": [],
            "elapsed_ms": 42,
        }
        with pytest.raises(ValidationError):
            validate_event(data)


class TestDirectModelValidation:
    """AC-011: Direct concrete model validation must enforce required fields."""

    def test_direct_model_validate_rejects_missing_event_type(self) -> None:
        data = _valid_session_created_dict()
        del data["event_type"]
        with pytest.raises(ValidationError):
            SessionCreatedEvent.model_validate(data)


class TestInvalidOccurredAt:
    """AC-012: Invalid ``occurred_at`` must raise ``ValidationError``, not ``TypeError``."""

    @pytest.mark.parametrize(
        "entrypoint",
        [validate_event, AgentEvent.model_validate, SessionCreatedEvent.model_validate],
    )
    def test_invalid_occurred_at_type_raises_validation_error(self, entrypoint) -> None:
        data = _valid_session_created_dict()
        data["occurred_at"] = 123
        with pytest.raises(ValidationError):
            entrypoint(data)


class TestValidationEntrypointsAreConsistent:
    """AC-013: ``validate_event()`` must delegate to the discriminated adapter
    after custom pre-checks so that both entrypoints share a single source of truth.
    """

    @pytest.mark.parametrize(
        "entrypoint",
        [validate_event, AgentEvent.model_validate],
    )
    def test_missing_event_type_rejected_by_both(self, entrypoint) -> None:
        data = _valid_session_created_dict()
        del data["event_type"]
        with pytest.raises(ValidationError):
            entrypoint(data)

    @pytest.mark.parametrize(
        "entrypoint",
        [validate_event, AgentEvent.model_validate],
    )
    def test_non_string_event_type_rejected_by_both(self, entrypoint) -> None:
        data = _valid_session_created_dict()
        data["event_type"] = 123
        with pytest.raises(ValidationError):
            entrypoint(data)

    @pytest.mark.parametrize(
        "entrypoint",
        [validate_event, AgentEvent.model_validate],
    )
    def test_unknown_event_type_rejected_by_both(self, entrypoint) -> None:
        data = _valid_session_created_dict()
        data["event_type"] = "session.unknown"
        with pytest.raises(ValidationError):
            entrypoint(data)

    @pytest.mark.parametrize(
        "entrypoint",
        [validate_event, AgentEvent.model_validate],
    )
    def test_deprecated_event_type_rejected_by_both(self, entrypoint) -> None:
        data = _valid_session_created_dict()
        data["event_type"] = "sessionCreated"
        with pytest.raises(ValidationError):
            entrypoint(data)

    def test_validate_event_delegates_to_adapter_for_valid_event(self, monkeypatch) -> None:
        import agent_runtime.events as ev_mod

        mock_adapter = Mock()
        mock_adapter.validate_python.return_value = SessionCreatedEvent(
            event_id="evt-test-001",
            event_type="session.created",
            occurred_at=datetime.now(timezone.utc),
            producer="opencode",
            payload=SessionCreatedPayload(session_id="sess-abc-123"),
        )
        monkeypatch.setattr(ev_mod, "_event_adapter", mock_adapter)

        data = _valid_session_created_dict()
        validate_event(data)
        mock_adapter.validate_python.assert_called_once_with(data)


class TestExtraFieldsForbidden:
    """AC-014: Extra envelope and payload fields must raise ``ValidationError``."""

    def test_extra_top_level_envelope_field_rejected(self) -> None:
        data = _valid_session_created_dict()
        data["extra_field"] = "should_not_be_here"
        with pytest.raises(ValidationError):
            validate_event(data)

    def test_extra_payload_field_rejected(self) -> None:
        data = _valid_session_created_dict()
        data["payload"]["extra_field"] = "should_not_be_here"
        with pytest.raises(ValidationError):
            validate_event(data)


class TestModelValidateKwargsForwarding:
    """AC-001 regression: ``AgentEvent.model_validate`` must forward supported
    Pydantic validation kwargs to ``_event_adapter.validate_python`` so base
    entrypoint behavior matches concrete model behavior."""

    def test_agent_event_model_validate_forwards_extra_allow(self) -> None:
        """Base entrypoint must accept extra fields when extra='allow' is passed,
        matching ``SessionCreatedEvent.model_validate`` behavior."""
        data = _valid_session_created_dict()
        data["extra_field"] = "extra_value"

        # Concrete model accepts extra fields with extra="allow"
        concrete = SessionCreatedEvent.model_validate(data, extra="allow")
        assert isinstance(concrete, SessionCreatedEvent)
        assert concrete.model_extra is not None
        assert concrete.model_extra["extra_field"] == "extra_value"

        # Base entrypoint must also accept extra fields by forwarding kwargs
        event = AgentEvent.model_validate(data, extra="allow")
        assert isinstance(event, SessionCreatedEvent)
        assert event.model_extra is not None
        assert event.model_extra["extra_field"] == "extra_value"

    def test_validate_event_forwards_extra_allow(self) -> None:
        """AC-002 regression: ``validate_event()`` must accept and forward
        Pydantic validation kwargs so it behaves consistently with
        ``AgentEvent.model_validate()``."""
        data = _valid_session_created_dict()
        data["extra_field"] = "extra_value"

        event = validate_event(data, extra="allow")
        assert isinstance(event, SessionCreatedEvent)
        assert event.model_extra is not None
        assert event.model_extra["extra_field"] == "extra_value"


class TestAgentEventBaseModelEnvelope:
    """AC-015: ``AgentEvent`` must be a real Pydantic ``BaseModel`` base envelope
    matching the spec fields, and ``SessionCreatedEvent`` must inherit from it."""

    def test_agent_event_is_base_model(self) -> None:
        from pydantic import BaseModel

        assert issubclass(AgentEvent, BaseModel)

    def test_session_created_event_inherits_agent_event(self) -> None:
        assert issubclass(SessionCreatedEvent, AgentEvent)

    def test_validated_event_is_instance_of_agent_event(self) -> None:
        data = _valid_session_created_dict()
        event = validate_event(data)
        assert isinstance(event, AgentEvent)

    def test_agent_event_exposes_shared_envelope_fields(self) -> None:
        """The base envelope must declare the spec fields so they are visible on subclasses."""
        from pydantic import BaseModel

        assert issubclass(AgentEvent, BaseModel)
        agent_fields = AgentEvent.model_fields
        assert "event_id" in agent_fields
        assert "event_type" in agent_fields
        assert "occurred_at" in agent_fields
        assert "producer" in agent_fields
        assert "correlation_id" in agent_fields
        assert "payload" in agent_fields

    # AC-019: AgentEvent base envelope must match the spec-level generic field annotations
    def test_agent_event_event_type_annotation_is_str(self) -> None:
        """The base envelope's event_type must be annotated as ``str`` (not a concrete Literal)."""
        assert AgentEvent.model_fields["event_type"].annotation is str

    def test_agent_event_payload_annotation_is_dict_str_any(self) -> None:
        """The base envelope's payload must be annotated as ``dict[str, Any]``."""
        ann = AgentEvent.model_fields["payload"].annotation
        origin = typing.get_origin(ann)
        args = typing.get_args(ann)
        assert origin is dict, f"expected dict origin, got {origin!r}"
        assert str in args, f"expected str in args, got {args!r}"
        assert Any in args, f"expected Any in args, got {args!r}"

    # AC-020: SessionCreatedEvent must carry the concrete session.created constraints
    def test_session_created_event_event_type_annotation_is_literal(self) -> None:
        """The concrete subclass's event_type must be annotated as ``Literal['session.created']``."""
        ann = SessionCreatedEvent.model_fields["event_type"].annotation
        origin = typing.get_origin(ann)
        args = typing.get_args(ann)
        assert origin is Literal, f"expected Literal origin, got {origin!r}"
        assert "session.created" in args, f"expected 'session.created' in args, got {args!r}"

    def test_session_created_event_payload_annotation_is_session_created_payload(self) -> None:
        """The concrete subclass's payload must be annotated as ``SessionCreatedPayload``."""
        assert SessionCreatedEvent.model_fields["payload"].annotation is SessionCreatedPayload


class TestOccurredAtTimezoneAwareness:
    """AC-016: ``occurred_at`` must reject naive datetimes and naive ISO strings
    while accepting timezone-aware values and ``Z``-suffix UTC strings."""

    @pytest.mark.parametrize(
        "entrypoint",
        [validate_event, AgentEvent.model_validate, SessionCreatedEvent.model_validate],
    )
    def test_naive_iso_string_raises_validation_error(self, entrypoint) -> None:
        data = _valid_session_created_dict()
        data["occurred_at"] = "2026-05-11T12:00:00"
        with pytest.raises(ValidationError):
            entrypoint(data)

    @pytest.mark.parametrize(
        "entrypoint",
        [validate_event, AgentEvent.model_validate, SessionCreatedEvent.model_validate],
    )
    def test_naive_datetime_object_raises_validation_error(self, entrypoint) -> None:
        data = _valid_session_created_dict()
        data["occurred_at"] = datetime(2026, 5, 11, 12, 0, 0)
        with pytest.raises(ValidationError):
            entrypoint(data)

    @pytest.mark.parametrize(
        "entrypoint",
        [validate_event, AgentEvent.model_validate, SessionCreatedEvent.model_validate],
    )
    def test_z_suffix_iso_string_validates(self, entrypoint) -> None:
        data = _valid_session_created_dict()
        data["occurred_at"] = "2026-05-11T12:00:00Z"
        event = entrypoint(data)
        assert event.occurred_at.tzinfo is not None

    @pytest.mark.parametrize(
        "entrypoint",
        [validate_event, AgentEvent.model_validate, SessionCreatedEvent.model_validate],
    )
    def test_timezone_aware_iso_string_validates(self, entrypoint) -> None:
        data = _valid_session_created_dict()
        data["occurred_at"] = "2026-05-11T12:00:00+00:00"
        event = entrypoint(data)
        assert event.occurred_at.tzinfo is not None

    @pytest.mark.parametrize(
        "entrypoint",
        [validate_event, AgentEvent.model_validate, SessionCreatedEvent.model_validate],
    )
    def test_timezone_aware_datetime_object_validates(self, entrypoint) -> None:
        data = _valid_session_created_dict()
        data["occurred_at"] = datetime(2026, 5, 11, 12, 0, 0, tzinfo=timezone.utc)
        event = entrypoint(data)
        assert event.occurred_at.tzinfo is not None


class TestValidateEventNonDictInput:
    """AC-017: ``validate_event()`` must reject non-dict inputs such as ``None``
    with ``pydantic.ValidationError``, not leak ``TypeError``."""

    def test_validate_event_none_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            validate_event(None)

    def test_validate_event_none_does_not_raise_type_error(self) -> None:
        """Explicit guard: the failure mode must be ValidationError, never TypeError."""
        try:
            validate_event(None)
        except TypeError:
            pytest.fail("validate_event(None) raised TypeError instead of ValidationError")
        except ValidationError:
            pass  # expected
