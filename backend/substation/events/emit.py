"""Append an event for the live stream (contracts/events.md). Safe to call from workers and requests."""

from __future__ import annotations

from typing import Any

from .models import Event


def emit(type_: str, payload: dict[str, Any] | None = None) -> None:
    Event.objects.create(type=type_, payload=payload or {})
