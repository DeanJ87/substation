"""Ingest task modules. Importing this package registers every ingest task (and its queue options)."""

from . import archive, catalogue, hash, ignore, reresolve  # noqa: F401
