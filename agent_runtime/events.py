"""Pydantic v2 event schemas for the ducktape agent runtime.

Phase 1 scope: validates the first event (``session.created``) against a
typed Pydantic v2 envelope before any durable write occurs (AC-005).

The envelope is deliberately distinct from ``stk`` command-result envelopes.
``stk`` envelopes use ``schemaVersion``, ``ok``, ``command``, ``data``,
``errors``, ``warnings``, and ``elapsed_ms``.  Agent event envelopes use
``event_id``, ``event_type``, ``producer``, ``correlation_id``,
``occurred_at``, and ``payload``.  The two shapes are not interchangeable.
"""

from datetime import datetime

from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
)

# ---------------------------------------------------------------------------
# Shared occurred_at validator (rejects naive datetimes)
# ---------------------------------------------------------------------------


def _validate_occurred_at(v: Any) -> datetime:
    """Parse and validate occurred_at, rejecting naive datetimes."""
    if isinstance(v, datetime):
        if v.tzinfo is None:
            raise ValueError("naive datetime not allowed; must be timezone-aware")
        return v
    if isinstance(v, str):
        # Replace Z suffix with explicit +00:00 offset for fromisoformat
        v = v.replace("Z", "+00:00")
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            raise ValueError("naive datetime not allowed; must be timezone-aware")
        return dt
    raise ValueError(f"cannot parse {v!r} as datetime")


# ---------------------------------------------------------------------------
# Payload models
# ---------------------------------------------------------------------------


class SessionCreatedPayload(BaseModel):
    """Payload for the ``session.created`` opencode lifecycle event."""

    model_config = ConfigDict(extra="forbid")

    session_id: str


# ---------------------------------------------------------------------------
# Base envelope model
# ---------------------------------------------------------------------------


class AgentEvent(BaseModel):
    """Base envelope for all agent runtime events.

    Defines the shared fields required by the spec: event_id, event_type,
    occurred_at (UTC), producer, correlation_id (optional), and payload.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str
    # Generic field annotations (AC-019): base envelope uses str and dict[str, Any].
    # Concrete event types narrow these via field overrides.
    event_type: str
    occurred_at: datetime
    producer: str
    correlation_id: str | None = None
    payload: dict[str, Any]

    @field_validator("occurred_at", mode="before")
    @classmethod
    def _parse_occurred_at(cls, v: Any) -> datetime:
        return _validate_occurred_at(v)

    @classmethod
    def model_validate(cls, obj: Any, **kwargs: Any) -> "AgentEvent":
        """Discriminated-union entrypoint: returns SessionCreatedEvent for session.created."""
        if cls is AgentEvent:
            return _event_adapter.validate_python(obj, **kwargs)
        return super().model_validate(obj, **kwargs)


# ---------------------------------------------------------------------------
# Concrete event models
# ---------------------------------------------------------------------------


class SessionCreatedEvent(AgentEvent):
    """Concrete event envelope for the ``session.created`` lifecycle event."""

    # AC-020: concrete constraints for session.created.
    # Pydantic allows narrowing field types in subclasses (base uses str/dict).
    event_type: Literal["session.created"]  # pyright: ignore[reportIncompatibleVariableOverride]
    payload: SessionCreatedPayload  # pyright: ignore[reportIncompatibleVariableOverride]


# ---------------------------------------------------------------------------
# Discriminated union and entrypoint
# ---------------------------------------------------------------------------

# Internal adapter uses discriminated validation by event_type.
_event_adapter: TypeAdapter[SessionCreatedEvent] = TypeAdapter(
    Annotated[
        SessionCreatedEvent,
        Field(discriminator="event_type"),
    ]
)


__all__ = [
    "AgentEvent",
    "SessionCreatedEvent",
    "SessionCreatedPayload",
    "validate_event",
]


def validate_event(data: Any, **kwargs: Any) -> SessionCreatedEvent:
    """Validate a raw event dictionary and return the typed event model.

    This is the canonical entrypoint for event validation (AC-005).  It
    validates the ``event_type`` field and rejects unknown event types with
    a ``pydantic.ValidationError``.

    The deprecated ``sessionCreated`` name is explicitly rejected.
    Non-dict inputs raise ``ValidationError``, not ``TypeError``.
    """
    # Guard against non-dict inputs: must raise ValidationError, not TypeError
    if data is None or not isinstance(data, dict):
        raise ValidationError.from_exception_data(
            title="SessionCreatedEvent",
            line_errors=[
                {
                    "type": "dict_type",
                    "loc": (),
                    "input": data,
                }
            ],
        )

    # Check key presence explicitly: a missing key must raise ValidationError
    # even though the field has a default in the model.
    if "event_type" not in data:
        raise ValidationError.from_exception_data(
            title="SessionCreatedEvent",
            line_errors=[
                {
                    "type": "missing",
                    "loc": ("event_type",),
                    "input": data,
                }
            ],
        )

    raw_event_type = data["event_type"]
    if not isinstance(raw_event_type, str):
        raise ValidationError.from_exception_data(
            title="SessionCreatedEvent",
            line_errors=[
                {
                    "type": "string_type",
                    "loc": ("event_type",),
                    "input": raw_event_type,
                }
            ],
        )
    event_type: str = raw_event_type

    # Custom pre-check: reject the deprecated name explicitly before delegation.
    if event_type == "sessionCreated":
        raise ValidationError.from_exception_data(
            title="SessionCreatedEvent",
            line_errors=[
                {
                    "type": "literal_error",
                    "loc": ("event_type",),
                    "input": event_type,
                    "ctx": {
                        "expected": (
                            '"session.created" (the deprecated '
                            "'sessionCreated' form is not accepted)"
                        )
                    },
                }
            ],
        )

    # Delegate to the discriminated adapter for all other event types,
    # including the known "session.created" and any unknown type.
    # The adapter will raise ValidationError for unknown event types.
    return _event_adapter.validate_python(data, **kwargs)
