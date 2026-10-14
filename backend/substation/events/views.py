"""GET /api/v1/events: Server-Sent Events (research R12, contracts/events.md).

Polls the Event table every 500 ms (LISTEN/NOTIFY would do; polling is simple and enough), resumes from Last-Event-ID, sends a
heartbeat comment every 15 s, and sends `resync` when the requested id has already been pruned.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator

from asgiref.sync import sync_to_async
from django.http import HttpRequest, HttpResponse, JsonResponse, StreamingHttpResponse

from .models import Event

POLL_S = 0.5
HEARTBEAT_S = 15
BATCH = 200


def _format(event_id: int, type_: str, data: object) -> str:
    return f"id: {event_id}\nevent: {type_}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


@sync_to_async
def _fetch(after: int) -> list[tuple[int, str, dict]]:
    rows = Event.objects.filter(id__gt=after).order_by("id").values_list("id", "type", "payload")[:BATCH]
    return list(rows)


@sync_to_async
def _bounds() -> tuple[int, int]:
    first = Event.objects.order_by("id").values_list("id", flat=True).first() or 0
    last = Event.objects.order_by("-id").values_list("id", flat=True).first() or 0
    return first, last


async def _stream(last_id: int | None, max_seconds: float | None) -> AsyncIterator[str]:
    first, last = await _bounds()
    if last_id is None:
        cursor = last  # new connection: only events from now on
    elif first and last_id < first - 1:
        yield _format(last, "resync", {})
        cursor = last
    else:
        cursor = last_id
    yield "retry: 3000\n\n"
    started = last_beat = time.monotonic()
    while True:
        for event_id, type_, payload in await _fetch(cursor):
            yield _format(event_id, type_, payload)
            cursor = event_id
        now = time.monotonic()
        if now - last_beat >= HEARTBEAT_S:
            yield ": heartbeat\n\n"
            last_beat = now
        if max_seconds is not None and now - started >= max_seconds:
            return
        await asyncio.sleep(POLL_S)


async def events(request: HttpRequest) -> HttpResponse | StreamingHttpResponse:
    user = await request.auser()
    if not user.is_authenticated:
        return JsonResponse({"code": "not_signed_in", "message": "Sign in to use SubStation."}, status=401)
    header = request.headers.get("Last-Event-ID") or request.GET.get("last_event_id")
    last_id = int(header) if header and header.isdigit() else None
    max_seconds = float(request.GET["max_seconds"]) if "max_seconds" in request.GET else None  # tests
    response = StreamingHttpResponse(_stream(last_id, max_seconds), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
