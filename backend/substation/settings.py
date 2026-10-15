"""SubStation settings. Everything environment-specific comes from SUBSTATION_* variables
(specs/001-ingest-catalogue/contracts/container.md)."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(f"SUBSTATION_{name}", default)


# --- Filesystem layout (constitution VII) ---------------------------------------------------------
DATA_DIR = Path(env("DATA_DIR", "/data") or "/data")
LIBRARY_ROOT = DATA_DIR / "library"  # read-only mounts, one subdirectory per library
STATION_ROOT = DATA_DIR / "substation"  # SubStation's writable area (local disk)
WORK_DIR = STATION_ROOT / "work"
PREVIEWS_DIR = STATION_ROOT / "previews"
STACKS_DIR = STATION_ROOT / "stacks"
# spec 014: where database backups go unless Settings → Backups names another folder
BACKUP_DIR = Path(env("BACKUP_DIR", "") or STATION_ROOT / "backups")
MASTERS_DIR = STATION_ROOT / "masters"  # calibration masters SubStation builds
CONFIG_DIR = STATION_ROOT / "config"


def _secret_key() -> str:
    key = env("SECRET_KEY")
    if key:
        return key
    path = CONFIG_DIR / "secret_key"
    try:
        return path.read_text().strip()
    except FileNotFoundError:
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            key = secrets.token_urlsafe(50)
            path.write_text(key)
            path.chmod(0o600)
            return key
        except OSError:
            # Not writable (for example while building the image): an ephemeral key is fine there.
            return secrets.token_urlsafe(50)


SECRET_KEY = _secret_key()
DEBUG = env("DEBUG", "0") == "1"
ALLOWED_HOSTS = [h.strip() for h in (env("ALLOWED_HOSTS", "*") or "*").split(",")]
CSRF_TRUSTED_ORIGINS = [o for o in (env("CSRF_TRUSTED_ORIGINS", "") or "").split(",") if o]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "allauth",
    "allauth.account",
    "allauth.mfa",
    "allauth.headless",
    "django_tasks",
    "substation.tasks",
    "substation.events",
    "apps.accounts",
    "apps.libraries",
    "apps.catalogue",
    "apps.ingest",
    "apps.processing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "substation.urls"
ASGI_APPLICATION = "substation.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]


# --- Database: PostgreSQL (005-DR-24) --------------------------------------------------------------------------
# SUBSTATION_DATABASE_URL=postgres://user:password@host:5432/name. The password may instead come from
# SUBSTATION_DATABASE_PASSWORD, or SUBSTATION_DATABASE_PASSWORD_FILE (a mounted Kubernetes or Docker secret).
def _database() -> dict:
    from urllib.parse import unquote, urlparse

    # unset (tools, image builds, a development checkout): a local PostgreSQL; the containers insist on it being set
    url = env("DATABASE_URL", "") or "postgres://substation@localhost:5432/substation"
    u = urlparse(url)
    if u.scheme not in ("postgres", "postgresql"):
        raise ImproperlyConfigured(
            "Set SUBSTATION_DATABASE_URL to the PostgreSQL database (postgres://user@host:5432/name)."
        )
    password = env("DATABASE_PASSWORD", "") or unquote(u.password or "")
    secret = env("DATABASE_PASSWORD_FILE", "")
    if secret:
        password = Path(secret).read_text().strip()
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": (u.path or "/substation").lstrip("/") or "substation",
        "USER": unquote(u.username or "substation"),
        "PASSWORD": password,
        "HOST": u.hostname or "localhost",
        "PORT": str(u.port or 5432),
        # 0 under ASGI: each request may run on a different thread, and a connection kept per thread is never
        # reused, so held connections pile up until PostgreSQL refuses more (2026-10-14: "too many clients").
        # Long-running workers can set SUBSTATION_DB_CONN_MAX_AGE to keep theirs.
        "CONN_MAX_AGE": int(env("DB_CONN_MAX_AGE", "0") or "0"),
        "CONN_HEALTH_CHECKS": True,
    }


DATABASES = {"default": _database()}
ATOMIC_REQUESTS = False
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Accounts (constitution VIII, research R11) ---------------------------------------------------
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]
HEADLESS_ONLY = True
HEADLESS_CLIENTS = ("browser",)
ACCOUNT_ADAPTER = "apps.accounts.adapter.ClosedSignupAdapter"
ACCOUNT_LOGIN_METHODS = {"username", "email"}
ACCOUNT_SIGNUP_FIELDS = ["username*", "email", "password1*"]
ACCOUNT_EMAIL_VERIFICATION = "none"
MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]
MFA_TOTP_ISSUER = "SubStation"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # the React app reads it to send X-CSRFToken

# --- Tasks (research R2) ----------------------------------------------------------------------------
TASKS = {
    "default": {
        "BACKEND": "substation.tasks.backend.SubStationTaskBackend",
        "QUEUES": ["default", "ingest", "engine", "process", "stack", "finish", "finish_ctl"],
    }
}
# Refuse to hash an image shorter than its header says (it is still being written). Off only for tests,
# whose fixtures are header-only.
# 0 only for header-only test fixtures (CI e2e)
INGEST_VERIFY_COMPLETE = env("INGEST_VERIFY_COMPLETE", "1") == "1"
# Calibrate, measure and grade lights as they are catalogued (specs 002, 003). Off in host tests.
PROCESSING_ENABLED = env("PROCESSING", "1") == "1"
# Siril's share of the machine: CPU threads (0 = half the CPUs) and the fraction of memory it may use.
SIRIL_THREADS = int(env("SIRIL_THREADS", "0") or "0") or None
SIRIL_MEM_RATIO = float(env("SIRIL_MEM_RATIO", "0.5") or "0.5")
CALIBRATED_CACHE_GB = float(env("CALIBRATED_CACHE_GB", "40") or "40")
# most working space one stack may use (its subs and their registered copies); a stack that needs more stops with
# the reason instead of filling the disk (spec 004 FR-010)
STACK_WORK_BUDGET_GB = float(env("STACK_WORK_BUDGET_GB", "150") or "150")  # calibrated subs kept for stacking

SUBSTATION_WORKERS = int(env("WORKERS", "2") or "2")
# post-processing helpers (spec 010, owner 2026-10-13) authenticate with this; unset, no helper can connect
SUBSTATION_HELPER_TOKEN = env("HELPER_TOKEN", "")
# set at image build time (docker/*.Dockerfile, publish workflow): version, branch, commit and build date
SUBSTATION_VERSION = env("VERSION", "") or ""

# --- Static files: only Django admin's own, served by WhiteNoise. The React app is served by the
# frontend container (Caddy), or by the Vite dev server in development.
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "var" / "static"

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "UTC"  # never used for night calculation (constitution II)
USE_I18N = True
USE_TZ = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"stdout": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["stdout"], "level": (env("LOG_LEVEL", "info") or "info").upper()},
}
