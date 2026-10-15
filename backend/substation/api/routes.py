"""Registers every app's router on the API. Imported once by substation.urls."""

from substation.api import register_router
from substation.api.health import router as health_router

register_router("/health", health_router)

from substation.tasks.api import router as queue_router  # noqa: E402

register_router("/queue", queue_router)

from substation.tasks.activity import router as activity_router  # noqa: E402

register_router("/work", activity_router)  # not "/activity": content blockers drop that path (2026-10-10)

from apps.libraries.api import settings_router  # noqa: E402

register_router("/settings", settings_router)

from substation.backup_api import router as backups_router  # noqa: E402

register_router("/backups", backups_router)

from apps.accounts.api import router as users_router  # noqa: E402

register_router("/users", users_router)

import apps.catalogue.api_bin  # noqa: E402,F401  (the bin: binning and restoring files, spec 011)
import apps.catalogue.api_calibration  # noqa: E402,F401  (calibration library, on the catalogue router)
import apps.catalogue.api_changes  # noqa: E402,F401  (your recent changes and undo, spec 016)
import apps.catalogue.api_ignore  # noqa: E402,F401  (ignore endpoints, on the catalogue router)
import apps.catalogue.api_library  # noqa: E402,F401  (library, collections, rigs)
import apps.catalogue.api_map  # noqa: E402,F401  (the map of where subs were shot)
import apps.catalogue.api_metadata  # noqa: E402,F401  (adds the metadata endpoints to the catalogue router)
import apps.catalogue.api_nights  # noqa: E402,F401  (nights, on the catalogue router)
import apps.catalogue.api_projects  # noqa: E402,F401  (projects inside collections)
import apps.catalogue.api_search  # noqa: E402,F401  (search from the header)
import apps.processing.api  # noqa: E402,F401  (subs, sessions, grades, review, on the catalogue router)
import apps.processing.api_bulk  # noqa: E402,F401  (bulk build, re-grade, stack and move, spec 016)
import apps.processing.api_calibration  # noqa: E402,F401  (calibration QA and built masters)
import apps.processing.api_masters  # noqa: E402,F401  (integrations, on the catalogue router)
import apps.processing.api_sky  # noqa: E402,F401  (a night's sky, spec 015, on the catalogue router)
from apps.catalogue.api import router as catalogue_router  # noqa: E402
from apps.libraries.api import libraries_router  # noqa: E402

register_router("/libraries", libraries_router)

from apps.processing.api_helper import router as helper_router  # noqa: E402

register_router("/helper", helper_router)  # post-processing helpers on faster machines (token, not a session)
register_router("", catalogue_router)
