"""T027: SSE stream: new events, Last-Event-ID resume, resync after pruning (contracts/events.md)."""

from __future__ import annotations

import json

import pytest
from django.test import AsyncClient

from substation.events.emit import emit
from substation.events.models import Event
from tests.conftest import signed_in_client

pytestmark = pytest.mark.django_db(transaction=True)


def parse(body: str) -> list[dict]:
    out = []
    for block in body.split("\n\n"):
        fields = dict(
            line.split(": ", 1) for line in block.splitlines() if ": " in line and not line.startswith(":")
        )
        if "event" in fields:
            out.append(
                {"id": int(fields["id"]), "event": fields["event"], "data": json.loads(fields["data"])}
            )
    return out


async def read_stream(client: AsyncClient, last_id: int | None, seconds: float = 1.2) -> list[dict]:
    headers = {"Last-Event-ID": str(last_id)} if last_id is not None else {}
    r = await client.get(f"/api/v1/events?max_seconds={seconds}", headers=headers)
    assert r.status_code == 200
    assert r["Content-Type"] == "text/event-stream"
    body = b"".join([chunk async for chunk in r.streaming_content]).decode()
    return parse(body)


@pytest.fixture
def async_admin(admin_user):
    sync = signed_in_client("admin")
    client = AsyncClient()
    client.cookies = sync.cookies
    return client


async def test_resume_from_last_event_id(async_admin):
    from asgiref.sync import sync_to_async

    await sync_to_async(emit)("frame.catalogued", {"n": 1})
    first = await sync_to_async(lambda: Event.objects.order_by("id").last().id)()
    await sync_to_async(emit)("frame.catalogued", {"n": 2})
    await sync_to_async(emit)("dataset.updated", {"n": 3})
    events = await read_stream(async_admin, first)
    assert [e["data"]["n"] for e in events] == [2, 3]
    assert [e["event"] for e in events] == ["frame.catalogued", "dataset.updated"]


async def test_new_connection_only_gets_new_events(async_admin):
    from asgiref.sync import sync_to_async

    await sync_to_async(emit)("frame.catalogued", {"n": "old"})
    events = await read_stream(async_admin, None, seconds=0.6)
    assert events == []


async def test_resync_when_id_was_pruned(async_admin):
    from asgiref.sync import sync_to_async

    for n in range(5):
        await sync_to_async(emit)("frame.catalogued", {"n": n})
    ids = await sync_to_async(lambda: list(Event.objects.order_by("id").values_list("id", flat=True)))()
    await sync_to_async(lambda: Event.objects.filter(id__in=ids[:3]).delete())()
    events = await read_stream(async_admin, ids[0] - 5, seconds=0.6)
    assert events and events[0]["event"] == "resync"
