"""Create the first admin from SUBSTATION_ADMIN_USERNAME / SUBSTATION_ADMIN_PASSWORD when no users exist."""

from __future__ import annotations

import os

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from apps.accounts.roles import ADMIN, ensure_groups


class Command(BaseCommand):
    help = "Create the bootstrap admin account if there are no users yet."

    def handle(self, *args, **options) -> None:
        ensure_groups()
        User = get_user_model()
        if User.objects.exists():
            self.stdout.write("Accounts already exist; bootstrap admin not needed.")
            return
        username = os.environ.get("SUBSTATION_ADMIN_USERNAME")
        password = os.environ.get("SUBSTATION_ADMIN_PASSWORD")
        if not username or not password:
            self.stdout.write(
                "No accounts yet. Set SUBSTATION_ADMIN_USERNAME and SUBSTATION_ADMIN_PASSWORD to create the first admin."
            )
            return
        user = User.objects.create_user(username=username, password=password)
        user.is_staff = True
        user.save(update_fields=["is_staff"])
        user.groups.add(Group.objects.get(name=ADMIN))
        self.stdout.write(f"Created admin account '{username}'. Change its password after signing in.")
