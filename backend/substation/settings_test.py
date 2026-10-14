"""Test settings: the real settings with temporary /data paths and a file-based test database
(file, not in-memory, so worker subprocesses in queue tests share it)."""

import os
import tempfile
from pathlib import Path

_TMP = Path(os.environ.get("SUBSTATION_TEST_TMP") or tempfile.mkdtemp(prefix="substation-tests-"))
os.environ["SUBSTATION_TEST_TMP"] = str(_TMP)  # subprocesses reuse the same directory
os.environ.setdefault("SUBSTATION_DATA_DIR", str(_TMP / "data"))
os.environ.setdefault("SUBSTATION_SECRET_KEY", "test-secret-key-not-for-production")

from .settings import *  # noqa: E402,F403
from .settings import DATA_DIR, DATABASES  # noqa: E402

for sub in ("library", "substation"):
    (DATA_DIR / sub).mkdir(parents=True, exist_ok=True)
if DATABASES["default"]["ENGINE"].endswith("sqlite3"):
    DATABASES["default"]["TEST"] = {"NAME": str(_TMP / "test.db")}
else:  # PostgreSQL (005-DR-24): the suite runs against both in CI
    DATABASES["default"]["TEST"] = {"NAME": "test_substation"}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]  # fast tests only

INGEST_VERIFY_COMPLETE = False  # fixtures are header-only
PROCESSING_ENABLED = False  # no Siril on the host; processing tests enable it
