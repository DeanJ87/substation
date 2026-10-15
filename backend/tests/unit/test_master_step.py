"""PostgreSQL enforces column lengths: a long progress line ("Plate solve (412 of 412, 380 already solved)") failed
the M 42 L stack with "value too long for type character varying(30)" (2026-10-15)."""

import pytest

from apps.catalogue.models import Dataset
from apps.processing.masters import _step
from apps.processing.models import Master

pytestmark = pytest.mark.django_db


def test_a_long_progress_line_is_kept():
    ds = Dataset.objects.create(group_key="s", target="M 42", filter_norm="L", display_name="M 42 · L")
    m = Master.objects.create(dataset=ds, version=1, state="running")
    line = "Plate solve (412 of 412, 380 already solved)"
    _step(m, line, 0.4)
    _step(m, "x" * 500, 0.5)  # never fails the stack, however long
    assert len(Master.objects.get(pk=m.pk).step) == 200
