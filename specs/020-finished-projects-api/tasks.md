# Tasks: Finished projects and the render read API (spec 020)

- [X] F1 Completed library role (read-only allowed); site region and Bortle on libraries and installation settings;
  default processing steps; a library folder named `completed` starts with the role; Completed libraries are never
  swept for subs (FR-001, FR-010)
- [X] F2 Models: `FinishedProject`, `FinishedFile` (roles), `ApiToken` (hashed, scoped, revocable, expiry, last
  use) (FR-003, FR-005, FR-011)
- [X] F3 Scan: `<kind>/<subject>/<name>/{exports,web,social,project}`, stat-only, files tracked by path, size and
  time with the content hash filled when served; not-a-project folders reported with the reason; role guesses
  from file names, never over the owner's (FR-002, FR-003, FR-005)
- [X] F4 Render data v1 from the linked projects: target, capture totals from the datasets' own counts, filters,
  rigs, mosaic, site (region, Bortle, whole-degree latitude only), per-night timeline with alt/az track, per-sub
  quality with effective verdicts, frames by role, processing; unknown fields omitted (FR-007..010)
- [X] F5 Render API, render tokens only: `GET /render/projects?since&kind`, `GET /render/projects/{id}`,
  `GET /render/projects/{id}/files/{key}` (final, starless, stars, per_filter/<name>, progressive/<n>, thumb) with
  ETag and 304; refusals reveal nothing; calls logged without tokens (FR-012, FR-013, FR-016)
- [X] F6 Owner API: list/rescan, detail, link suggestions (catalogue numbers, names, year), links, roles, re-guess,
  processing, render-data preview, write project.json (read-write only, never over a file SubStation didn't
  write), default processing; tokens list/create (secret shown once)/revoke (FR-004..006, FR-011, FR-014)
- [X] F7 Contract `contracts/render-api.openapi.yaml`; app OpenAPI exported (FR-015)
- [X] F8 Compose: a fourth optional library slot (`SUBSTATION_LIBRARY_4`, `_4_NAME`, `_4_MODE`, read-only by
  default); install guide row
- [X] F9 Tests: scan and roles, token refusals (none, wrong, revoked, session), a render token refused elsewhere,
  unlinked not offered then linked, totals and omissions, no coordinates, files with ETag and thumbnail, tokens
  shown once and revocable, project.json rules (`tests/integration/test_finished_render.py`)
- [X] F9a (2026-10-21) Review fixes 020-DR-01..06 with tests (15 tests)
- [X] F10 Frontend: Finished page (list, empty states, rescan, not-a-project list), project detail (link with
  suggestions, file roles, processing steps, render-data preview, write project.json), Settings → API tokens,
  Completed role and region/Bortle/default processing in Settings; tests and accessibility check
  (`frontend/src/features/finished/`, `settings/ApiTokens.tsx`, `FinishedDefaults.tsx`, `LibrarySite.tsx`;
  `/finished` added to the a11y e2e screens)
- [X] F11 Deploy: set `SUBSTATION_LIBRARY_4` and `_4_NAME=completed` on the stack, check the library appears with
  the Completed role, create a render token, put one project folder in place and query it end to end
  (2026-10-21: live; list, render data, final and thumbnail served, refused without a token)
- [X] F15 (2026-10-21) Several sites per master: `capture.sites` with ids, site id on timeline rows and quality
  entries, tracks per site, catalogue-first target names (020-DR-07); tests
- [X] F16 (2026-10-21) `updated_at` follows a fingerprint of the render data's inputs, so moved datasets and a
  changed project kind show up in `since` polling (020-DR-11); test
- [ ] F12 (later) Link suggestions by plate-solve overlap once finished images are solved; annotations from that
  solve (FR-004, FR-007)
- [ ] F13 (later) Target type, distance and angular size from the catalogue data (FR-007)

- [ ] F14 (later) A session thumbnail route so the Finished page can show each project's final image
