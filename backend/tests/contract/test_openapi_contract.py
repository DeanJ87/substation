"""T017: the live API covers every path and method in specs/001-ingest-catalogue/contracts/openapi.yaml.

Paths implemented by later user stories are listed in PENDING with their story; they are strict xfails, so
when a story lands its endpoint this test fails until the entry is removed from PENDING.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from django.test import Client
from openapi_spec_validator import validate

CONTRACT = Path(__file__).resolve().parents[3] / "specs/001-ingest-catalogue/contracts/openapi.yaml"

# path -> story that implements it
PENDING: dict[str, str] = {}
NOT_IN_NINJA = {"/events"}  # plain async Django view (SSE), tested in test_events.py

contract = yaml.safe_load(CONTRACT.read_text())


def test_contract_is_valid_openapi():
    validate(contract)


@pytest.fixture(scope="module")
def live_schema(django_db_blocker):
    with django_db_blocker.unblock():
        r = Client().get("/api/v1/openapi.json")
    assert r.status_code == 200
    return r.json()


def _params():
    for path, ops in contract["paths"].items():
        if path in NOT_IN_NINJA:
            continue
        for method in ops:
            marks = (
                [pytest.mark.xfail(strict=True, reason=f"implemented in {PENDING[path]}")]
                if path in PENDING
                else []
            )
            yield pytest.param(path, method, marks=marks, id=f"{method.upper()} {path}")


@pytest.mark.parametrize(("path", "method"), list(_params()))
def test_path_is_implemented(live_schema, path, method):
    live_paths = {p.removeprefix("/api/v1"): v for p, v in live_schema["paths"].items()}
    assert path in live_paths, f"{path} missing from the API"
    assert method in live_paths[path], f"{method.upper()} {path} missing"
