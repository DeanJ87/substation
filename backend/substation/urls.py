"""URL configuration: allauth headless endpoints, the versioned API and the admin."""

from django.contrib import admin
from django.urls import include, path

import substation.api.routes  # noqa: F401  (registers routers)
from substation.api import api
from substation.events.views import events

urlpatterns = [
    path("_allauth/", include("allauth.headless.urls")),
    path("api/v1/events", events, name="events"),
    path("api/v1/", api.urls),
    path("admin/", admin.site.urls),
]
