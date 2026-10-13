"""Notifications (spec 008 T15, 008-DR-06): "sent when something needs you, not for routine work". Channels are an
ntfy topic URL and a webhook URL, kept in InstallationSettings.processing["notifications"]. A failed send is logged
and never fails the work that triggered it."""

from __future__ import annotations

import json
import logging
import urllib.request

log = logging.getLogger("substation.notify")

EVENTS = ("master_finished", "job_failed", "awaiting_calibration", "session_summary")


def config() -> dict:
    from apps.processing.config import processing_settings

    return processing_settings().get("notifications") or {}


def send(event: str, title: str, message: str, url: str | None = None, cfg: dict | None = None) -> list[str]:
    """Send to every configured channel that wants `event`. Returns the channels that failed, with why."""
    cfg = cfg if cfg is not None else config()
    if event != "test" and event not in (cfg.get("events") or []):
        return []
    failed = []
    if cfg.get("ntfy"):
        headers = {"Title": title.encode("ascii", "replace").decode(), "Tags": "telescope"}
        if url:
            headers["Click"] = url
        failed += _post("ntfy", cfg["ntfy"], message.encode(), headers)
    if cfg.get("webhook"):
        body = json.dumps({"event": event, "title": title, "message": message, "url": url}).encode()
        failed += _post("webhook", cfg["webhook"], body, {"Content-Type": "application/json"})
    return failed


def _post(name: str, target: str, body: bytes, headers: dict) -> list[str]:
    if not target.startswith(("http://", "https://")):
        return [f"{name}: the address must start with http:// or https://"]
    try:
        req = urllib.request.Request(target, data=body, headers=headers, method="POST")  # noqa: S310 (user's own URL)
        with urllib.request.urlopen(req, timeout=5):  # noqa: S310
            return []
    except Exception as exc:  # noqa: BLE001
        log.warning("Notification to %s failed: %s", name, exc)
        return [f"{name}: {exc}"]
