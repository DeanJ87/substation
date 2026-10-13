"""T011: 8 processes × 500 short write transactions against the WAL database, no "database is locked"
(research R1: WAL + transaction_mode=IMMEDIATE + timeout)."""

import subprocess

import pytest

from substation.events.models import Event
from tests.conftest import manage

pytestmark = pytest.mark.django_db(transaction=True)

WRITER = """
from django.db import transaction
from substation.events.models import Event
for i in range(500):
    with transaction.atomic():
        Event.objects.create(type="test.concurrency", payload={"writer": WID, "i": i})
"""


def test_concurrent_writers():
    procs = [
        manage("shell", "-c", WRITER.replace("WID", str(w)), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for w in range(8)
    ]
    errors = []
    for p in procs:
        _, err = p.communicate(timeout=180)
        if p.returncode != 0:
            errors.append(err.decode()[-500:])
    assert not errors, errors
    assert Event.objects.filter(type="test.concurrency").count() == 8 * 500
