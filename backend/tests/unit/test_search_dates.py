"""Search reads dates as people type them (2026-10-15: "october" found nothing)."""

from datetime import date

import pytest

from apps.catalogue.api_search import night_filter
from apps.catalogue.models import Night

pytestmark = pytest.mark.django_db
TODAY = date(2026, 10, 15)


@pytest.fixture
def nights():
    for d in ["2025-10-02", "2026-10-14", "2026-10-15", "2026-09-28", "2026-01-14"]:
        Night.objects.create(site_key="h", date=date.fromisoformat(d))


def found(q: str) -> list[str]:
    f = night_filter(q, TODAY)
    return [] if f is None else sorted(str(n.date) for n in Night.objects.filter(f))


def test_typed_dates(nights):
    assert found("october") == ["2025-10-02", "2026-10-14", "2026-10-15"]
    assert found("Oct 2026") == ["2026-10-14", "2026-10-15"]
    assert found("14 october") == ["2026-10-14"]
    assert found("oct 14th") == ["2026-10-14"]
    assert found("14/10") == ["2026-10-14"]
    assert found("14/01/2026") == ["2026-01-14"]
    assert found("2026-09") == ["2026-09-28"]
    assert found("last night") == ["2026-10-14"] and found("tonight") == ["2026-10-15"]
    assert night_filter("orion", TODAY) is None and night_filter("may flowers", TODAY) is None
