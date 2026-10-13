# Feature Specification: Plate solving

**Feature Branch**: `009-plate-solving`

**Created**: 2026-10-10

**Status**: Draft

**Input**: Owner decision 2026-10-10: solve with Siril's own solver (no ASTAP), offline against its local
star catalogues. Deferred by spec 006 ("plate solves will replace this"); SubStation v2 design (framing overlays, Add datasets ranking, solve fields on sub detail), reviewed in `docs/design/design-review.md`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Every light knows where it points (Priority: P2)

Each light is solved locally (ASTAP) using the header position as a hint; centre, rotation, scale and field size
are recorded and shown with the solver and time; collections use solved positions for suggestions and framing.

**Independent Test**: Solve the phase 2 NGC 7000 panels: each panel's centre is within 2′ of its header pointing,
and the collection's framing panel draws three overlapping fields.

### Edge Cases

- Too few stars (cloud): the sub is left unsolved or falls back to the header position (setting), with the reason.
- No solver installed: solving is off and the UI says so in Settings → Plate solving.

## Requirements *(mandatory)*

1. **009-DR-01**: The system MUST plate-solve every light with a local solver (ASTAP, configurable path), using the
   header RA, DEC and OBJCTROT as a hint when switched on. On failure it MUST either fall back to the header
   position or leave the sub unsolved (setting), and MUST log the reason ("too few stars (cloud)").
2. **009-DR-02**: Solves MUST record centre, rotation, pixel scale, field size and offset from the dataset's
   reference framing, each shown on the sub detail with the solver and time ("ASTAP · 1.4 s").
3. **009-DR-03**: Collection suggestions and the "Add datasets" ranking MUST use the solved centre distance,
   rotation difference and field overlap, and MUST say so in the note.
4. **009-DR-04**: Back-filling solves for existing subs MUST run as a low-priority job visible in Activity.

## Amendment 2026-10-10: Siril, offline

Owner decision: plate solving uses Siril's `platesolve` (constitution IV: all image processing through Siril), not
ASTAP. To keep SubStation fully offline (constitution, deployment), Siril uses its local KStars catalogues
(namedstars, unnamedstars, deepstars/Tycho-2 and USNO-NOMAD-1e8, about 1.6 GB, verified against the published
SHA-1 sums) mounted read-only into the worker. Online catalogues stay optional. Where 009-DR-01 to 009-DR-04 say
ASTAP, read Siril; "ASTAP · 1.4 s" becomes "Siril · 1.4 s". When the catalogues are missing, solving is off and
Settings → Plate solving says how to install them.

## Validation finding (2026-10-10)

Header pointing (RA/DEC written by the capture software) is the mount's own idea of where it points and drifts
by up to 0.9° over a session on the owner's data; plate solves agree with each other to about 1′. So wherever
a solve exists it replaces the header pointing (collection suggestions, Add datasets, framing), and header
pointing is never used to judge a solve. A failed solve on a sub with fewer than 300 detected stars is reported
as the sky's fault ("Only N stars detected… cloud, dew or poor focus?"), not the solver's.

## Amendment 2026-10-12: annotations

Solves were recorded but not used anywhere an image is shown; labelling what is in the frame was wanted.

- **009-DR-09**: A solved sub or dataset master MUST offer annotations: the Messier, NGC, IC, Sharpless and LDN
  objects and bright named stars in its field, drawn over the preview (sub page) and the 100% view (subs and
  masters), with catalogue name and common name. Large objects that reach into the field are included and
  labelled at the edge. One switch ("Annotate · n", key N in the 100% view) turns them on everywhere, remembered
  per browser. Unsolved images say why instead.
- **009-DR-10**: Annotations MUST work offline from Siril 1.4.2's own annotation catalogues (shipped with the app,
  GPL-3.0), and are computed from the stored solve; no engine call.
- **Fix**: fields under a degree were read as degrees (Siril prints `26m 55.59s`, read as 26.9°). The reading is
  fixed and the 26 affected solves are dropped so the solve backfill redoes them.
