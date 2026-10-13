"""Per-user preferences (007-DR-06): the theme follows the user, not the browser."""

from django.conf import settings
from django.db import models


class UserPreference(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="preference")
    theme = models.CharField(
        max_length=10, blank=True, default="", help_text="dark, light or night; blank = not chosen"
    )
