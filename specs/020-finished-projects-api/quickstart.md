# Quickstart: validating finished projects and the render API (spec 020)

Shapes are defined in [contracts/render-api.openapi.yaml](contracts/render-api.openapi.yaml); entities in
[data-model.md](data-model.md). Placeholders: `$SST` is the SubStation address (e.g. `https://substation.example`),
`$TOKEN` a render token, `$ID` a finished project id.

## Prerequisites

- A running stack with a library given the Completed role (Settings → Libraries; a library slot named `completed`
  starts with it). Read-only mounting is enough.
- In that library, one folder laid out as `Astro/<subject>/<year> <name>/exports/<name>-final.png`, optionally with
  `<name>-starless.png`, `<name>-stars.png` and `<name>-step-1-graxpert.png`.
- A catalogue project with graded, plate-solved subs of the same target, in a collection whose name or other names
  share the catalogue number.
- An admin account.

## 1. The project appears (Story 1)

1. Open **Finished** and press Rescan (or wait up to 5 minutes).
2. Expect the project under its kind and subject, its exports as thumbnails, roles guessed: final, starless, stars,
   step 1 labelled "GraXpert". A folder outside `Astro|Nightscapes|Videos` is listed under "Not a project" with a reason.
3. Check the library is untouched: no new files appear in the project folder at any point in this guide.

## 2. Create a render token (Story 3)

1. Settings → API tokens → create one named for the renderer. The secret (`sst_…`) is shown once; copy it.
2. The list shows name, created time, last use (empty) and an optional expiry.

## 3. Refusals before linking

```sh
curl -s -o /dev/null -w '%{http_code}\n' "$SST/api/v1/render/projects"                        # 401: no token
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer wrong" "$SST/api/v1/render/projects"   # 401
curl -s -H "Authorization: Bearer $TOKEN" "$SST/api/v1/render/projects"
# {"projects": [], "library_reachable": true}     the astro project is not linked yet, so not offered
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $TOKEN" "$SST/api/v1/finished"         # 401 or 403: render tokens reach nothing else
```

## 4. Link the project (Story 2)

1. Open the finished project. The link section lists at most five suggestions, each with reasons ("same target
   (IC 1805)", "same name", "same year"). Accept the first.
2. Expect the Render data preview to fill in, and the Progression section to show Queued or Building (or a reason,
   e.g. a mosaic, or too many subs needing calibration).
3. Unlinking warns that the image is no longer offered; the change can be undone from recent changes.

## 5. Read it as the renderer

```sh
H="Authorization: Bearer $TOKEN"
curl -s -H "$H" "$SST/api/v1/render/projects"
# {"projects":[{"id":"7","name":"…","kind":"astro","target":"IC 1805","collection_ids":[3],
#   "updated_at":"2026-…Z","thumb_url":"/api/v1/render/projects/7/files/thumb"}],"library_reachable":true}
curl -s -H "$H" "$SST/api/v1/render/projects/$ID" | jq '{schema_version, project, target, capture: .capture | keys, frames: .frames | keys, processing}'
# schema_version 1; frames has final, thumb, steps (and starless, stars, progression when present);
# URLs are root-relative; no field holds coordinates finer than lat_1deg
curl -s -D - -o final.png -H "$H" "$SST/api/v1/render/projects/$ID/files/final" | grep -i etag
curl -s -o /dev/null -w '%{http_code}\n' -H "$H" -H 'If-None-Match: "<etag from above>"' \
  "$SST/api/v1/render/projects/$ID/files/final"                                             # 304
curl -s -o /dev/null -w '%{http_code}\n' -H "$H" "$SST/api/v1/render/projects/$ID/files/thumb"   # 200, JPEG
curl -s -o /dev/null -w '%{http_code}\n' -H "$H" "$SST/api/v1/render/projects/$ID/files/nope"    # 404
```

Check: `capture` totals equal the linked project's Overview (integration counts accepted and down-weighted subs);
`capture.sites[*]` carry only `id`, `region`, `bortle`, `lat_1deg`, `subs`, `integration_s`.

## 6. Progression

1. On the project page press Generate (or wait for the automatic start). Activity shows the job below master builds.
2. When done, the page lists checkpoints with date labels; the render data gains `frames.progression` and
   `frames.progression_info`, and `files/progression/1` serves a JPEG with an ETag.
3. A mosaic or mixed pixel scales shows Unavailable with the reason instead.

## 7. `since` polling and `updated_at`

```sh
T=$(curl -s -H "$H" "$SST/api/v1/render/projects" | jq -r '.projects[0].updated_at')
curl -s -H "$H" "$SST/api/v1/render/projects?since=$T" | jq '.projects | length'    # 0
```

Then change one input (relabel a step, set a distance, override a sub's verdict, move a dataset into the linked
project, or rebuild the progression) and repeat: the project returns with a later `updated_at`. Re-running with no
change returns nothing.

## 8. Revoke

Revoke the token in Settings; the next call with it returns 401.

## Automated checks

```sh
cd backend
uv run pytest tests/integration/test_finished_render.py tests/unit/test_progression_plan.py tests/unit/test_progression_task.py
scripts/test-in-worker.sh tests/engine/test_progression_siril.py -m siril     # real Siril, inside the worker image
uv run python manage.py export_openapi ../frontend/src/api/openapi.json && git diff --exit-code -- ../frontend/src/api/openapi.json

cd ../frontend
npx vitest run src/features/finished src/features/settings/ApiTokens.test.tsx
npx playwright test tests/e2e/a11y.spec.ts      # includes /finished and a project page
```

CI runs the full backend and frontend suites, lint, types and the OpenAPI diff on every push.
