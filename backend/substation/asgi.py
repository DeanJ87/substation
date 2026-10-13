"""ASGI entry point (uvicorn), needed for the Server-Sent Events stream."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "substation.settings")

application = get_asgi_application()
