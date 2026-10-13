"""Annotation payloads (009 amendment 2026-10-12), shared by the sub and master endpoints. No
`from __future__ import annotations` here: see substation.api."""

from substation.api import Schema


class AnnotationOut(Schema):
    name: str
    alias: str = ""
    kind: str  # messier, ngc, ic, sh2, ldn, star
    u: float  # across the preview, 0 (left) to 1 (right)
    v: float  # down the preview, 0 (top) to 1 (bottom)
    size: float | None = None  # the object's diameter as a share of the preview's width
    mag: float | None = None


class AnnotationsOut(Schema):
    solved: bool
    note: str = ""
    objects: list[AnnotationOut] = []
