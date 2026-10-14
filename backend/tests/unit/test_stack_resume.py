"""005-DR-25: an interrupted stack resumes from its checkpoint, or starts again when its inputs have gone."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from apps.catalogue.models import Dataset, Frame
from apps.processing.masters import _checkpoint, _resumed_inputs, _save_checkpoint
from apps.processing.models import Master, MasterMember, SubMeasurement

pytestmark = pytest.mark.django_db


def _master():
    d = Dataset.objects.create(group_key="k", display_name="M 31 · L", target="M 31", filter_norm="L")
    m = Master.objects.create(dataset=d, version=1, state="running")
    members = []
    for i in range(3):
        f = Frame.objects.create(
            sha256=f"{i:064x}", size_bytes=1, format="fits", first_seen_at=datetime.now(UTC)
        )
        SubMeasurement.objects.create(frame=f)
        members.append(MasterMember.objects.create(master=m, frame=f, included=True))
    return m, members


def test_a_checkpoint_belongs_to_its_master(tmp_path):
    m, _ = _master()
    _save_checkpoint(tmp_path, {"master": m.pk, "done": ["inputs"], "order": {}})
    assert _checkpoint(tmp_path, m.pk)["done"] == ["inputs"]
    assert _checkpoint(tmp_path, m.pk + 1)["done"] == []  # another master's leftovers start fresh
    assert _checkpoint(tmp_path / "nothing", m.pk)["done"] == []


def test_inputs_resume_only_while_every_link_is_there(tmp_path):
    m, members = _master()
    order = {str(i): mm.pk for i, mm in enumerate(members, start=1)}
    for i in order:
        (tmp_path / f"sub_{int(i):05d}.fit").write_bytes(b"x")
    ck = {"master": m.pk, "done": ["inputs"], "order": order}
    got = _resumed_inputs(tmp_path, ck)
    assert got is not None and [mm.pk for mm in got.values()] == [mm.pk for mm in members]
    (tmp_path / "sub_00002.fit").unlink()
    assert _resumed_inputs(tmp_path, ck) is None
