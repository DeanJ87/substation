"""API wrapper: the only package that imports Django Ninja (plan: keep Ninja swappable).

Apps build endpoints with the names re-exported here (`Router`, `Schema`, `Field`, `Query`) and register
them in `substation.api.routes`. Endpoint modules must NOT use `from __future__ import annotations`:
Ninja resolves type hints through the (possibly decorated) view function, and string annotations behind
`admin_required` cannot be resolved. Every route requires a signed-in session unless declared public; unsafe
methods also require the CSRF token (allauth headless browser client sends X-CSRFToken).
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from functools import wraps
from typing import Any

from django.http import HttpRequest
from django.urls import register_converter
from ninja import Field, NinjaAPI, Query, Router, Schema
from ninja.errors import AuthenticationError, HttpError, ValidationError
from ninja.responses import Status
from ninja.security import django_auth

from apps.accounts.roles import is_admin

__all__ = [
    "ApiError",
    "Field",
    "Query",
    "Router",
    "Schema",
    "Status",
    "admin_required",
    "api",
    "decode_cursor",
    "encode_cursor",
    "register_router",
]


class Sha256Converter:
    """`{sha256:sha256}` in a path matches only a content hash, so `/frames/metadata` is never read as a frame."""

    regex = "[0-9a-f]{64}"

    def to_python(self, value: str) -> str:
        return value

    def to_url(self, value: str) -> str:
        return value


register_converter(Sha256Converter, "sha256")

api = NinjaAPI(
    title="SubStation API",
    version="0.1.0",
    urls_namespace="api",
    auth=django_auth,
    description="SubStation catalogue, ingest and queue API. Sign in through /_allauth/browser/v1/.",
)


class ApiError(Exception):
    """Raise with a plain-English message in the voice guide's form."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class ErrorOut(Schema):
    code: str
    message: str


@api.exception_handler(ApiError)
def _api_error(request: HttpRequest, exc: ApiError):  # type: ignore[no-untyped-def]
    return api.create_response(request, {"code": exc.code, "message": exc.message}, status=exc.status)


@api.exception_handler(AuthenticationError)
def _auth_error(request: HttpRequest, exc: AuthenticationError):  # type: ignore[no-untyped-def]
    return api.create_response(
        request, {"code": "not_signed_in", "message": "Sign in to use SubStation."}, status=401
    )


@api.exception_handler(HttpError)
def _http_error(request: HttpRequest, exc: HttpError):  # type: ignore[no-untyped-def]
    return api.create_response(request, {"code": "http_error", "message": str(exc)}, status=exc.status_code)


@api.exception_handler(ValidationError)
def _validation_error(request: HttpRequest, exc: ValidationError):  # type: ignore[no-untyped-def]
    first = exc.errors[0] if exc.errors else {}
    where = ".".join(str(p) for p in first.get("loc", []) if p not in ("body", "query", "path"))
    msg = first.get("msg", "invalid value")
    return api.create_response(
        request,
        {"code": "invalid", "message": f"{where}: {msg}" if where else str(msg), "errors": exc.errors},
        status=422,
    )


def admin_required(func: Callable[..., Any]) -> Callable[..., Any]:
    """Endpoint decorator: only admins (constitution VIII)."""

    @wraps(func)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
        if not is_admin(request.user):
            raise ApiError(403, "admin_only", "Only an admin can change this.")
        return func(request, *args, **kwargs)

    return wrapper


_registered: set[str] = set()


def register_router(prefix: str, router: Router) -> None:
    if prefix in _registered:
        return
    api.add_router(prefix, router)
    _registered.add(prefix)


def encode_cursor(values: dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(values, default=str).encode()).decode()


def decode_cursor(cursor: str | None) -> dict[str, Any] | None:
    if not cursor:
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ApiError(400, "bad_cursor", "Page link expired. Reload.") from exc
    return data if isinstance(data, dict) else None
