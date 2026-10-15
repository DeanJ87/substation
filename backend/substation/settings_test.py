"""Test settings: the real settings with temporary /data paths. Tests need PostgreSQL: SUBSTATION_DATABASE_URL, or
a local one on port 5432 (docker run -e POSTGRES_PASSWORD=substation -e POSTGRES_USER=substation -p 5432:5432
postgres:17-alpine)."""

import os
import tempfile
from pathlib import Path

_TMP = Path(os.environ.get("SUBSTATION_TEST_TMP") or tempfile.mkdtemp(prefix="substation-tests-"))
os.environ["SUBSTATION_TEST_TMP"] = str(_TMP)  # subprocesses reuse the same directory
os.environ.setdefault("SUBSTATION_DATA_DIR", str(_TMP / "data"))
os.environ.setdefault("SUBSTATION_SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("SUBSTATION_DATABASE_URL", "postgres://substation:substation@localhost:5432/substation")  # noqa: E501

from .settings import *  # noqa: E402,F403
from .settings import DATA_DIR, DATABASES  # noqa: E402

for sub in ("library", "substation"):
    (DATA_DIR / sub).mkdir(parents=True, exist_ok=True)
# another name lets two checkouts (or worktrees) run their tests against one PostgreSQL at once
DATABASES["default"]["TEST"] = {"NAME": os.environ.get("SUBSTATION_TEST_DB", "test_substation")}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # fast tests only

INGEST_VERIFY_COMPLETE = False  # fixtures are header-only
PROCESSING_ENABLED = False  # no Siril on the host; processing tests enable it

# nothing cached between tests (the Library's totals are kept for a minute in use)
CACHES = {"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
