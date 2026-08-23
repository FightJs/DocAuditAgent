"""Shared API schema primitives."""

from __future__ import annotations

from dataclasses import dataclass

from app.hitl.enums import ActorRole


@dataclass(frozen=True)
class ActorContext:
    """Authenticated subject fixture used by the MVP API.

    Real authentication is intentionally outside this MVP. The API still treats
    these values as an authenticated principal supplied by the hosting layer.
    """

    actor_id: str
    role: ActorRole
