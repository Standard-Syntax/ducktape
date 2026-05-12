"""Event schema models for the ducktape agent runtime.

This package defines agent event envelopes that are distinct from ``stk``
command-result envelopes. Agent event envelopes use these fields:
``event_id``, ``event_type``, ``producer``, ``correlation_id``,
``occurred_at``, and ``payload``.  The two shapes are not interchangeable.

See Phase 0 Design Lock in ``specs/event-driven-agent-runtime-plan.md`` for
the authoritative field list and the rationale for not using
``sessionCreated`` or other deprecated names.
"""

from agent_runtime.events import (
    AgentEvent,
    SessionCreatedEvent,
    SessionCreatedPayload,
    validate_event,
)

__all__ = [
    "AgentEvent",
    "SessionCreatedEvent",
    "SessionCreatedPayload",
    "validate_event",
]
