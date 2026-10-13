"""Write the live API's OpenAPI schema (what the frontend's types are generated from).

uv run python manage.py export_openapi ../frontend/src/api/openapi.json
"""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Export the API's OpenAPI schema as JSON"

    def add_arguments(self, parser) -> None:  # noqa: ANN001
        parser.add_argument("path")

    def handle(self, *args, **options) -> None:
        import substation.api.routes  # noqa: F401  (registers every router)
        from substation.api import api

        schema = api.get_openapi_schema(path_prefix="")
        Path(options["path"]).write_text(json.dumps(schema, indent=1, sort_keys=True, default=str) + "\n")
        self.stdout.write(f"Wrote {len(schema.get('paths', {}))} paths to {options['path']}")
