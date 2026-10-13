"""Accounts are created by admins only (constitution VIII): public signup is closed."""

from allauth.account.adapter import DefaultAccountAdapter


class ClosedSignupAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request) -> bool:  # noqa: ANN001
        return False
