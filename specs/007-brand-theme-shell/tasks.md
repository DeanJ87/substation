# Tasks: Brand, theme and app shell

Done items were verified against the code on 10 October 2026. Open items name the files to touch and the
requirement they close. Gap numbers (G1–G16) refer to `docs/design/design-review.md` section C.

## Phase 1: Foundations (built)

- [X] B1 Token file with the exact dark, light and night values from A.2 [A.2]
  - `frontend/src/design/substation-tokens.css`
- [X] B2 Three themes switched by `data-theme`, N toggles night vision and returns to the previous theme [007-DR-06, partial]
  - `design/theme.ts`, `design/useTheme.ts`, `design/theme.test.ts`
- [X] B3 Self-hosted Inter and JetBrains Mono, body 15/1.55, type scale, tabular figures in tables [007-DR-10, partial]
  - `design/base.css` (fontsource)
- [X] B4 Five-item nav Library · Review · Calibration · Activity · Settings with Review and Activity counts [007-DR-05, partial]
  - `routes/AppFrame.tsx`
- [X] B5 Seven verdict states with distinct shapes and glyphs [A.7]
  - `components/VerdictBadge.tsx`
- [X] B6 Rejected concept marks are not shipped (only in `docs/design/assets/logo/concepts`, referenced nowhere in `frontend` or `docs/user`) [007-DR-08]
- [X] B7 Docs theme stylesheet with the three schemes and font-face rules written [007-DR-15, partial]
  - `docs/user/stylesheets/substation.css`

## Phase 2: Tokens and night vision

- [X] B8 Add `--sst-scrim` and `--sst-warn-tint` to all three themes; replace the colour literals [007-DR-01, G2]
  - `design/substation-tokens.css`; `features/v2/v2.module.css` (banner), `features/dataset/dataset.module.css` (3 overlays), `features/frames/frames.module.css`
- [X] B9 Guard: Vitest fails on hex or rgba literals in module CSS outside the token file [007-DR-01]
  - new `design/tokens.test.ts`
- [X] B10 Red-only rasters in night vision: SVG `#sst-red` filter mounted once, applied to `img`, `canvas`, `svg image` [007-DR-07, G2]
  - `routes/AppFrame.tsx` (hidden filter SVG), `design/base.css`
- [X] B11 Theme applied before first paint and persisted per user [007-DR-06] — done 2026-10-10: inline script applies the saved theme before first paint; UserPreference.theme (GET/PUT /users/me/preferences) loads on sign-in and saves on change
  - `frontend/index.html` (inline script); new `backend/apps/accounts/models.py` `UserPreference` + migration, `backend/apps/accounts/api.py` `GET/PATCH /me/preferences`, register in `substation/api/routes.py`; `design/useTheme.ts`

## Phase 3: Shell

- [X] B12 Header: remove the theme select, `QueueIndicator`, failed and reconcile links; "Watching N folders" in mono with ok dot; divider; account menu with avatar initial, username and Sign out [007-DR-05, G1, G5, G6]
  - `routes/AppFrame.tsx`, `routes/frame.module.css`, new `components/AccountMenu.tsx` (Radix Dropdown); reconcile entry moves to a Library notice in `features/library/Library.tsx`
- [X] B13 Header geometry: 56 px, no wrap, gap 40 px, nav 14 px gap 28 px full-height items, inactive 500, active 600 with bottom-edge underline [007-DR-05, G3]
  - `routes/frame.module.css`
- [X] B14 Count pills: mono 11 px, tint fill, accent text, accent-line border on Review and Activity [007-DR-05, G4]
  - `routes/frame.module.css` `.count`, `.countAccent`
- [X] B15 Inline `Logo` component (mark + live wordmark, token colours, clear space, lockup gap, size fallbacks) used in header and sign-in [007-DR-08, G7]
  - new `components/Logo.tsx`; `routes/AppFrame.tsx`, `routes/SignIn.tsx` (drop the `<img>` lockup imports)
- [X] B16 Page layout: 1240 px container, 32 px gutters, titles 24 px 600 −0.02em, 13 px muted summary [007-DR-13, G13]
  - `routes/frame.module.css` `.main`; `features/v2/v2.module.css` `.head`

## Phase 4: Components and type

- [X] B17 Cards `panel → card-end`; readouts radius 0.7rem, mono 34–36 px, 500, −0.03em, first value accent [007-DR-02, G10, G13]
  - `components/ui.module.css` `.card`, `.readoutValue`; `features/v2/v2.module.css` `.card`, `.readout`, `.readoutValue`
- [X] B18 Buttons: primary tint fill at rest and 600, secondary 500, danger, disabled dashed line with `--sst-dim` [007-DR-03, G11]
  - `components/ui.module.css`
- [X] B19 Verdict badge as a neutral pill with only the 14 px icon coloured [007-DR-04, G12]
  - `components/VerdictBadge.module.css`, `components/VerdictBadge.tsx`
- [X] B20 Body `font-feature-settings: 'cv11','ss01'`; paths, files and FITS keywords in mono [007-DR-10, G9]
  - `design/base.css`; spot fixes in `features/frames/FrameValues.tsx`, `features/settings/PathPatterns.tsx`
- [X] B21 Writing rules: formatters for U+2212 minus, en-GB grouping, long and short dates, durations, "—" for missing values; copy pass [007-DR-14] — partial 2026-10-10: "—" for missing values everywhere, U+2212 minus in temperatures, en-GB grouping on counts; a full copy pass still to do. Done 2026-10-10: format.ts signed (U+2212, en-GB grouping), shortDateText, durationText with tests; Dec pointing uses U+2212
  - `features/format.ts` + new `features/format.test.ts`; copy in `features/**/*.tsx`

## Phase 5: Screens and keys

- [X] B22 Sign-in: mark and wordmark above the card, "to the SubStation on <host>", Username and Password, field-level errors in the voice guide, Enter submits, footer "SubStation <version>", no other copy [007-DR-11, G16]
  - `routes/SignIn.tsx`, `routes/frame.module.css`, `api/auth.ts` (error `param`); `backend/substation/api/health.py` `version`
- [X] B23 "?" opens the shortcut list for the current screen; screens register their keys [007-DR-12, G14]
  - new `components/Shortcuts.tsx` (Radix Dialog, `useShortcuts`); mounted in `routes/AppFrame.tsx`; registrations in `features/review/ReviewScreen.tsx`, `features/dataset/SubsTab.tsx`
- [X] B24 In-page confirmation component replacing `window.confirm` [007-DR-16]
  - new `components/Confirm.tsx`; `features/dataset/MastersTab.tsx:254`; `features/library/CollectionView.tsx:88` (with L18)

## Phase 6: Assets and docs

- [X] B25 Favicons 16, 32, 48 and SVG, 512 px PNG app icon (22% radius), touch icon and `theme-color` [007-DR-09, G8]
  - `frontend/public/` (from `docs/design/assets/favicon`, `app-icon`); `frontend/index.html`
- [X] B26 Docs site: three palette schemes with toggles, `font: false`, logo and favicon; self-hosted woff2 [007-DR-15, G15]
  - `mkdocs.yml`; new `docs/user/fonts/InterVariable.woff2`, `JetBrainsMono-Variable.woff2`; `docs/user/assets/`

## Phase 7: Validation

- [X] B27 Independent tests: no colour literals (B9 passes); N on every screen; in night vision no green, blue or white pixel (screenshot sample); header one line at 1280–1440 px; Sign out in the account menu; ? opens the list [US1, US2] — done 2026-10-10 (frontend/.b27.mjs): night vision on Library, Review, Calibration, Activity, Settings, a collection: 0–1 non-red pixels of 13,361 sampled; header 56 px (one line) at 1280 and 1440; Sign out in the account menu; no colour literals test passes. Found and fixed a race where the saved theme could undo an N pressed while a page loaded
- [X] B28 BusyBar in the shell (007-DR-17)
- [X] B29 Spinner, Skeleton, PageLoading, Collapsible, LoadMore components (007-DR-18)
- [X] B30 optimistic() / patchItems / patchDeep helpers; MutationCache onError toast with meta.failed (007-DR-19)
- [X] B31 Toasts component in the shell (007-DR-20)
- [X] B32 Core hooks optimistic: verdicts, stack start/rerun/cancel/delete, collection create/add/accept, job cancel/bump/retry/dismiss/move, pause, calibration build/override (007-DR-19)
- [X] B33 Settings, metadata, library, dataset and calibration screens optimistic: projects, collection, calibration tab, re-grade, masters, subs, review, calibration library and set, close look, reconcile, values, path patterns, ignore, rigs, save bar, users, workers (007-DR-19)
- [X] B34 Collapsible sections across library, collection, dataset tabs, sub, review, night, calibration, settings, reconcile, frame drawer (007-DR-21)
- [X] B35 useProgressive + LoadMore in scrolling panes for every long list (007-DR-22)
- [X] B36 Shared table widths and alignment; masters row actions on one line (007-DR-23)
- [X] B37 Glance component and /frames/{sha}/glance endpoint; used on file names across the site (007-DR-24)
- [X] B38 (owner 2026-10-13) `overscroll-behavior: contain` removed from every scrolling pane (007-DR-25)
- [X] B39 (2026-10-14) `GET /search` (collections, datasets, nights, files) and the header search box with "/",
  arrow keys and Enter; test (007-DR-26)
- [X] B40 (2026-10-14) Specs 001, 002, 005 and 007 rebuilt: their main text and several amendments had been
  overwritten on 2026-10-11 by scripts that opened the file for writing before reading it; restored from the first
  commit and the session record, owner quotes rewritten in neutral words
- [X] B41 (2026-10-14) All jsx-a11y rules as errors in `.oxlintrc.json`; axe e2e updated (Map, Bin, Activity, the
  viewer modal, WCAG 2.2 tags) and run in CI against the stack (007-DR-27)
- [X] B42 (2026-10-15) `night_filter`: month names, day and month, UK numeric dates, yesterday/last night/tonight
  (007-DR-28); test
- [X] B43 (2026-10-15) Phone layout: two-row header, scrolling tabs, unwrapped buttons, full-screen viewer, map below
  the header, settings within the screen (007-DR-29); screenshots at 400 px
- [X] B44 (2026-10-15) Phone: tables as cards below 600 px (shared `cards` rule in `base.css`, `data-label` on
  cells) on the collection, dataset, Calibration, What to shoot, Bin and night pages; Activity rows wrap; the night
  page's three readouts in one row (007-DR-31 to 007-DR-33); before/after screenshots at 400 px
- [X] B45 (2026-10-15) Work pill removed; search widens on focus; account menu narrower (007-DR-30)
- [X] B46 (2026-10-15) Bulk choose boxes in phone cards; dataset tabs close up on a phone so Sky fits (007-DR-34)
- [X] B47 (2026-10-16) Filter tint tokens, `filterTint`, `<Tinted>` on collection, combined and dataset master
  thumbnails; the collection's masters carry their filter (007-DR-35); tests; screenshots
- [X] B48 (2026-10-16) Thumbnail tints removed (007-DR-36); the filter tokens kept for the sky dome
- [X] (2026-10-22) Search matches filter aliases to their canonical names (007-DR-37); test
- [X] B49 (2026-10-22) Colour roles in `substation-tokens.css` (data, chart, status, filter tokens in dark, light and
  night; series-1 no longer the accent); verdict, grade, night and chart colours moved to them; no uppercase labels;
  mono only for paths (007-DR-38)
- [X] B50 (2026-10-22) `format.ts` rebuilt (dates, times, durations, exposures, numbers, binning, `datasetLabel`,
  `shutterSpan`); inline `toLocale*`/`toFixed` replaced outside the library and finished screens; tests (007-DR-39)
- [X] B51 (2026-10-22) `ui.tsx` primitive layer and `filters.ts`; Modal focus trap and sizes; dead CSS and five unused
  dependencies removed (007-DR-40)
- [X] B52 (2026-10-22) Screens: dataset (title order, one action bar, Needs a look, quiet tiles and sessions, masters
  count with failures, short errors), night (one time convention, one Moon), sky, Activity, Calibration, What to
  shoot, Bin, Settings (file paths, post-processing rows, help behind ?), sub viewer, phone navigation; axe clean;
  screenshots at 1440 and 400 px (007-DR-41)
- [X] B53 (2026-10-22) Library, collection and project screens onto FilterMeter, GradeMeter and the colour roles (owned by the
  library rework)
- [X] B54 (2026-10-22) Library totals and whole-library tiles as StatTile/GradeMeter/FilterMeter, labelled for scope;
  collection cards (filter meters with a key, labelled kept, rig in facts, name placeholder); one Add-to choice per
  ungrouped dataset; one search (007-DR-42)
- [X] B55 (2026-10-22) Collection page: Edit and Add datasets dialogs, remove inside edit, rig rename/merge only in
  Settings, sessions only on their tab with month ticks, one Masters empty state, grade meters, canonical filter
  order; project cards with filter meters, panel matrix for mosaics, one New project and one Arrange button, goals per
  filter in hours; collection Files card in one line; tests updated (007-DR-43)
- [X] B56 (2026-10-22) Quality strips with scale and box/median, "relative to bias", FWHM and SQM as two labelled
  charts (007-DR-44)
- [X] B57 (2026-10-22) Sky tracks by filter with target shapes; `DateInput` in the scope bar and map; phone scope bar
  behind Filters; calibration set "Use" checkbox; Finished pages on Chip, Select, Input and format.ts; pill classes
  replaced on the screens touched; axe clean in dark, light and night on every screen changed; light warn token
  darkened for chip contrast (007-DR-45)
- [X] B58 (2026-10-22) axe clean on every route at 1440 and 400 in dark, light and night; CI spec covers every route
  and both widths, with a skip-link and dialog keyboard test; skip link; focus ring on the header search and
  Settings tabs; menu button keyboard (`components/useMenu.ts`); 24 px sub tile targets (007-DR-46)
- [X] B59 (2026-10-22) Glossary in the design system; the sky's reading note behind `?`; "quarantine" and "frames"
  out of user copy (007-DR-47)
