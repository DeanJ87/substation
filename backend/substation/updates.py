"""Updates without scripts (005-DR-23). SubStation notices a newer build, waits until no stack is running, then asks
Portainer to redeploy its stack; it checks the new version came up and resumes the queue.

Configured by two environment variables, both set on the stack, never in the repository:
  SUBSTATION_UPDATE_WEBHOOK  Portainer's redeploy webhook for this stack (without it, updates are off)
  SUBSTATION_UPDATE_REPO     the GitHub repository whose "publish images" runs make the images (owner/name)

State lives in InstallationSettings.updates. The supervisor in the API container calls `tick()` every 10 s.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone

log = logging.getLogger("substation.updates")

CHECK_EVERY = timedelta(minutes=10)
DEPLOY_TIMEOUT = timedelta(minutes=20)  # the new version must answer within this, or the update has failed


def webhook() -> str:
    return os.environ.get("SUBSTATION_UPDATE_WEBHOOK", "").strip()


def repo() -> str:
    return os.environ.get("SUBSTATION_UPDATE_REPO", "").strip()


def running() -> tuple[str, str]:
    """(branch, short commit) from the image's version string: "0.1.0 · poc-substation · 64176ed · 14 Oct 2026"."""
    parts = [p.strip() for p in (settings.SUBSTATION_VERSION or "").split("·")]
    return (parts[1], parts[2]) if len(parts) >= 3 else ("", "")


def latest_build(repo_name: str, branch: str) -> dict | None:
    """The newest successful image build for the branch, from GitHub's public API."""
    url = (
        f"https://api.github.com/repos/{repo_name}/actions/workflows/publish.yml/runs"
        f"?branch={branch}&status=success&per_page=1"
    )
    req = urllib.request.Request(
        url, headers={"Accept": "application/vnd.github+json", "User-Agent": "SubStation"}
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        runs = json.load(r).get("workflow_runs") or []
    if not runs:
        return None
    run = runs[0]
    return {
        "sha": run["head_sha"],
        "title": (run.get("display_title") or "").split("\n")[0][:200],
        "built_at": run.get("updated_at") or run.get("created_at"),
        "url": run.get("html_url", ""),
    }


def _when(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


def heavy_running() -> int:
    from substation.tasks.models import Task, TaskStatus

    return Task.objects.filter(status=TaskStatus.RUNNING, slot="siril_heavy").count()


def _save(s, u: dict) -> None:  # noqa: ANN001
    s.updates = u
    s.save(update_fields=["updates"])


def _resume(s, u: dict) -> None:  # noqa: ANN001
    """Unpause the queue if the update paused it; a pause set by hand stays."""
    if u.pop("paused_by_update", False):
        s.queue_paused = False
        s.save(update_fields=["queue_paused"])


def tick(now: datetime | None = None, fetch=latest_build, post=None) -> dict:  # noqa: ANN001
    from apps.libraries.models import InstallationSettings

    now = now or timezone.now()
    s = InstallationSettings.load()
    u = dict(s.updates or {})
    branch, sha = running()
    if not webhook() or not repo() or not sha:
        return u

    if u.get("state") == "deploying":
        if u.get("target", "").startswith(sha):
            _resume(s, u)
            u.update(state="", reason="", last={"sha": sha, "at": now.isoformat()})
            u.pop("target", None)
            u.pop("requested", None)
            log.info("Updated to %s", sha)
        elif now - (_when(u.get("since")) or now) > DEPLOY_TIMEOUT:
            _resume(s, u)
            u.update(state="failed", reason=f"Portainer was asked to redeploy, but {sha} is still running.")
            u.pop("requested", None)
        _save(s, u)
        return u

    checked = _when(u.get("checked_at"))
    if checked is None or now - checked > CHECK_EVERY or u.get("requested"):
        try:
            u["latest"] = fetch(repo(), branch)
            u["checked_at"] = now.isoformat()
            u.pop("check_error", None)
        except Exception as e:  # noqa: BLE001
            u["checked_at"] = now.isoformat()
            u["check_error"] = f"Couldn't reach GitHub: {e}"

    latest = u.get("latest") or {}
    newer = bool(latest.get("sha")) and not latest["sha"].startswith(sha)
    if not newer:
        if u.get("state") == "draining":  # nothing to wait for any more
            _resume(s, u)
            u["state"] = ""
        u.pop("requested", None)
        _save(s, u)
        return u

    if u.get("state") in ("", None, "failed") and (u.get("auto", True) or u.get("requested")):
        if u.get("state") == "failed" and not u.get("requested") and u.get("target") == latest["sha"]:
            _save(s, u)  # this build already failed to come up: wait for a newer one or a press of Update now
            return u
        u.update(state="draining", target=latest["sha"], since=now.isoformat(), reason="")
        if not s.queue_paused:
            s.queue_paused = True
            s.save(update_fields=["queue_paused"])
            u["paused_by_update"] = True

    if u.get("state") == "draining":
        busy = heavy_running()
        if busy:
            u["reason"] = f"Waiting for {busy} stack{'s' if busy != 1 else ''} to finish before updating."
        else:
            try:
                # name the exact build: Portainer sets stack variables from the webhook's query string
                sep = "&" if "?" in webhook() else "?"
                (post or _post)(f"{webhook()}{sep}SUBSTATION_TAG={latest['sha'][:7]}")
                u.update(state="deploying", since=now.isoformat(), reason="")
                log.info("Asked Portainer to redeploy for %s", latest["sha"][:7])
            except Exception as e:  # noqa: BLE001
                _resume(s, u)
                u.update(state="failed", reason=f"Portainer didn't take the redeploy: {e}")
    _save(s, u)
    return u


def _post(url: str) -> None:
    req = urllib.request.Request(url, data=b"", method="POST", headers={"User-Agent": "SubStation"})
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()


def cancel() -> dict:
    """Stop an update that is waiting for stacks; the queue resumes if the update paused it."""
    from apps.libraries.models import InstallationSettings

    s = InstallationSettings.load()
    u = dict(s.updates or {})
    if u.get("state") == "draining":
        _resume(s, u)
        u.update(state="", reason="", auto=False)
        u.pop("requested", None)
        _save(s, u)
    return u
