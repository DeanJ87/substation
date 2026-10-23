# Research: Finished projects and the render read API (spec 020)

Decisions as built, with the reasons and what was set aside. References are to amendments in [spec.md](spec.md)
and files under `backend/apps/finished/`.

## Access

### R1. Personal bearer tokens, hashed, with one scope

- **Decision**: `ApiToken` with a random secret (`sst_` + 32 url-safe bytes), stored only as a SHA-256 digest plus a
  four-character hint; scope `render`; optional expiry; `revoked_at`; `last_used_at` written at most once a minute.
  The render router's only auth is `RenderToken(HttpBearer)`, which accepts an active render-scope token and nothing
  else; every other router uses the session, so a render token is refused there. Refusals log method and path only.
- **Rationale**: the renderer is one app on the same network behind the existing HTTPS proxy (Assumptions); a
  fast unsalted hash is adequate for a high-entropy random secret and allows a lookup by digest.
- **Alternatives**: OAuth or per-user API keys with full access (more than a read-only consumer needs); Django
  sessions for the renderer (would give it the whole API); a salted slow hash (needless for random secrets and
  prevents indexed lookup).

### R2. Owner routes stay on the session; changes are admin-only

- **Decision**: `/finished` and `/tokens` are normal session routes; reads are open to signed-in users, every change
  (links, roles, distance, progression, tokens) is `@admin_required`. Link changes are recorded as undoable changes
  (DR-20).
- **Alternatives**: a separate owner token scope (not needed; the owner uses the app).

## The API surface

### R3. Root-relative URLs (DR-02)

- **Decision**: every URL in responses is `/api/v1/render/projects/<id>/files/<key>`; the renderer joins it with the
  address it already calls.
- **Rationale**: nothing depends on the scheme or host the reverse proxy reports.
- **Alternatives**: absolute URLs built from the request (wrong behind a proxy that rewrites the scheme).

### R4. File ETags from a cheap fingerprint (DR-05)

- **Decision**: a file's ETag is a SHA-256 of `rel_path|size|mtime` (first 32 hex); thumbnails add `-thumb`;
  progression images use their checkpoint hash. `If-None-Match` returns 304. Thumbnails are made through a temporary
  file and an atomic replace, with 16-bit and float images scaled by their range; a resolved path outside the project
  folder is never served.
- **Rationale**: hashing a 300 MB TIFF inside a request would break SC-003.
- **Alternatives**: content SHA-256 per request; a stored content hash (see Q1).

### R5. `updated_at` from a data fingerprint (DR-03, DR-11)

- **Decision**: `changed_at()` hashes everything render data is built from (the folder's files and roles, distance,
  linked projects' kind, panels and collection, datasets and their counts, aggregates over subs, grades, verdicts,
  measurements, plate solves and site sums, site descriptions, and the progression build). When the hash differs
  from `data_fingerprint`, `data_changed_at` becomes now. The list filters `changed > since` and sorts oldest first;
  times without a zone are UTC; the value is never in the future.
- **Rationale**: the newest-timestamp rule missed a dataset moved into a linked project and a changed project kind.
- **Alternatives**: max of related `updated_at` columns (misses moves and deletions); signals on every related model
  (spread over many apps and easy to miss one).

### R6. Only offered projects, only display-ready files

- **Decision**: `offered()` requires the folder present, a link for astro projects (nightscapes and videos need none,
  DR-16), and a final image; refused ids answer 404 without detail. Only PNG, JPEG and TIFF outside `project/` can
  have a served role.
- **Alternatives**: placeholder images or partial records (FR-008 forbids guesses).

### R7. An unreachable library keeps the last known list (DR-06)

- **Decision**: a missing or empty mount point marks the scan unreachable and leaves projects as they were; the list
  carries `library_reachable`.

## Render data

### R8. Privacy: whole-degree sites, tracks from the rounded site (DR-01, DR-07, DR-08)

- **Decision**: a site is the sub's latitude and longitude rounded to whole degrees. `capture.sites` has one entry per
  such site, ids `s1, s2 …` by integration, with subs, integration, `lat_1deg`, and region and Bortle only from a
  library or the installation settings whose own site rounds to the same key. Every graded sub's site is listed (0
  used when all were rejected). Timeline rows and quality entries carry the site id. Alt/az tracks are computed with
  astropy from the target's median plate-solve position at each sub's time and the rounded site, never from stored
  positions; a test recovers the site from the output and checks it is no better than whole degrees.
- **Rationale**: real alt/az at real times plus the target's coordinates would locate the site to about a kilometre.
- **Alternatives**: a single averaged site (wrong for masters from two places); stored alt/az (leaks the site).

### R9. Totals from the datasets' own counts (FR-009, DR-04)

- **Decision**: totals sum the datasets' denormalised `accepted_count`, `down_count`, `rejected_count` and
  `accepted_integration_s`, as the app shows them; data with no filter keeps its totals with no name; per-sub quality
  reports `fwhm_arcsec` and `fwhm_px` separately and uses the effective verdict.

### R10. Mosaic from the project's effective kind (DR-10, DR-17)

- **Decision**: `_is_mosaic()` uses `effective_kind()` of each linked project: the owner's choice when set, otherwise
  worked out from its panels. A single-field project has no `mosaic` and its timeline is not split by panel.
- **Rationale**: capture software can set panel numbers on what is one field.

### R11. Target naming and distance (DR-07, DR-13)

- **Decision**: the target name prefers a catalogue designation from the collection's other names or the datasets'
  targets; the collection name becomes `common_name`. Distance is typed by the owner (`distance_source = "manual"`) or
  looked up on request from SIMBAD TAP: the median of `mesDistance` for the first of up to eight designations that has
  any (catalogue numbers first), converted to light years, stored with a source string. A look-up is refused while a
  manual figure is set. Nothing is looked up while rendering.
- **Alternatives**: a bundled catalogue (not available offline at this precision); look-up during rendering (slow,
  network-dependent).

### R12. Processing steps from file names (DR-14)

- **Decision**: role `step` guessed from `…step-<n>-<what>`; `n` is the order, `<what>` split on `+` with common
  tools spelled out (`STEP_ALIASES`). The owner can change order and label; any owner-set role stops re-guessing the
  project. Render data lists `frames.steps: [{order, label, url}]` and `processing` is the labels in order. The typed
  list and Settings defaults were removed (migration 0003).

### R13. Role guesses never override the owner

- **Decision**: guesses run on first sight and when files change, only while no file in the project has an owner-set
  role. A name saying stars were put back is a final (DR-16); web and social crops are never the final (DR-06); of
  several finals the newest is kept; a single unroled export becomes the final.

## Progression (DR-15, DR-18, DR-19)

### R14. One registration, prefix stacks, shared crop and stretch

- **Decision**: kept subs come from the same selection as master builds; nights are grouped into at most 12
  contiguous checkpoints with date-range labels. All kept subs are registered once to one pinned reference (kept
  between runs while still kept; otherwise the sub with most stars, in Hα when present). Each checkpoint `select`s its
  prefix by sequence position and stacks per channel; the images share one crop, are level-matched to the full stack
  and drawn with the full stack's stretch. Channels combine as HOO, SHO, RGB, OSC or MONO. JPEGs at most 2400 px in
  `STATION_ROOT/cache/progression/fp<id>/<hash>.jpg`; unchanged inputs reuse them.
- **Rationale**: re-registering per checkpoint would shift framing; per-image stretches would hide the noise drop.
- **Alternatives**: the owner's own progressive exports only (kept as `frames.progressive`, which takes precedence).

### R15. Noise weighting, verified on real Siril

- **Decision**: progression stacks always use SNR weighting, whatever master builds use; rejection only with three
  or more subs. Siril `select`/`unselect` take positions in the registered sequence, mapped from file numbers.
- **Rationale**: with sharpness weighting, real Siril gave the softest sub of a two-sub stack almost no weight.

### R16. Queued at lower priority, automatic with limits

- **Decision**: `build_progression` runs on the `stack` queue in the `siril_heavy` slot at `PRIORITY_BULK`, below
  master integrations; deduplicated per project; cancellable; a restart re-queues it. It starts after linking and,
  for linked astro projects that never had one, from the supervisor's periodic jobs (three per pass). An automatic
  start is skipped with a reason when more than 30% of subs would need calibrating again. First version refuses
  mosaics, several panels and mixed pixel scales (over 10% apart) with a reason.

### R17. `project.json` withdrawn (DR-12)

- **Decision**: no file is written into the Completed library; the renderer reads the live API only.
- **Rationale**: a file in the folder was a stale snapshot that disagreed with the API, and writing there conflicted
  with Principle I.

## Open questions

Differences between spec and code, recorded without changing either.

- **Q1. Files tracked by content (FR-003, Key Entities)**: files are tracked by path, size and time; `FinishedFile.sha256`
  exists but nothing fills it (the scan clears it on change; the API uses the cheap fingerprint). The `scan.py`
  docstring and task F3 say it is filled when served. A replaced export is the same row with new size and time; a
  rename keeps its role only by an exact size-and-time match.
- **Q2. Link suggestions by plate-solve overlap (FR-004, Story 2 scenario 1)**: not built; suggestions use catalogue
  numbers, names and year (task F12, later). The reason "overlapping field" is never produced.
- **Q3. Annotations, target type and angular size (FR-007)**: not emitted; the contract marks them optional (tasks
  F12, F13).
- **Q4. Automatic progression start (DR-15 vs code)**: DR-15 says after linking "when no sub needs calibrating
  again"; the code allows up to 30% (`RECAL_AUTO_LIMIT = 0.3`). DR-19 says "not when many", which matches the code.
- **Q5. Mosaic panel count (DR-17)**: `capture.mosaic.panels` takes planned panels only from linked projects whose
  stored kind is `mosaic`, while whether it is a mosaic uses the effective kind; a project worked out as a mosaic with
  no stored kind reports panels shot, not planned.
- **Q6. Stale text in the spec body**: FR-006 (typed steps, Settings default), FR-007 `processing` "steps from FR-006",
  SC-005 ("written project.json"), the Assumption that progressive stacks are a later spec, and DR-09 (write access to
  project folders) are superseded by DR-14, DR-12 and DR-15 but not marked so in place.
- **Q7. Last-use time**: FR-011 lists "last use"; the code writes it at most once a minute, so it can lag by up to a
  minute. SC-006 (revoked refused on next call) holds, as `active` is checked on every call.
