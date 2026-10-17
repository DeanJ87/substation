"""Ninja keeps one schema per class name: two response classes with the same name silently share a schema
(and the frontend's generated types). Every API schema name must be unique."""

from __future__ import annotations

import importlib
from collections import defaultdict

from ninja import Schema

MODULES = [
    "apps.catalogue.api",
    "apps.catalogue.api_metadata",
    "apps.catalogue.api_ignore",
    "apps.catalogue.api_calibration",
    "apps.catalogue.api_nights",
    "apps.catalogue.api_library",
    "apps.catalogue.api_archive",
    "apps.processing.api",
    "apps.processing.api_masters",
    "substation.tasks.activity",
    "substation.tasks.api",
    "apps.libraries.api",
    "substation.api.health",
]


def test_schema_names_are_unique():
    seen = defaultdict(list)
    for mod in MODULES:
        m = importlib.import_module(mod)
        for name, obj in vars(m).items():
            if isinstance(obj, type) and issubclass(obj, Schema) and obj.__module__ == mod:
                seen[name].append(mod)
    assert {n: m for n, m in seen.items() if len(m) > 1} == {}


def test_accept_suggestions_route_is_reachable(admin_client, db):
    r = admin_client.post("/api/v1/collections/accept-suggestions")
    assert r.status_code == 200, r.content
