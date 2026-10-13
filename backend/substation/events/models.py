"""Event log streamed to browsers over Server-Sent Events (contracts/events.md)."""

from django.db import models


class Event(models.Model):
    id = models.BigAutoField(primary_key=True)
    type = models.CharField(max_length=60)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self) -> str:
        return f"{self.id} {self.type}"
