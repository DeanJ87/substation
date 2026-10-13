# Plan: Brand, theme and app shell

The tokens, the three themes, the N key, the five-item nav and the seven verdict icons exist. What remains
is applying the brand rules to the shared components and the shell, making night vision complete for
raster images, the "?" key list, sign-in, favicons and the docs theme. Almost all of it is frontend CSS and
small components; the backend changes are a per-user theme preference and the version on `/health`.

## Technical context

- Tokens: `frontend/src/design/substation-tokens.css` (exact A.2 values, `[data-theme='light'|'night']`);
  global styles `design/base.css` (fontsource Inter Variable and JetBrains Mono, type scale).
- Theme: `design/theme.ts` (localStorage `sst-theme`, `applyTheme`, `toggleNight`) and `design/useTheme.ts`
  (react-hotkeys-hook `n`; the hook ignores form fields by default).
- Shell: `routes/AppFrame.tsx`, `routes/frame.module.css`, `routes/SignIn.tsx`; shared components
  `components/ui.tsx`, `ui.module.css`, `VerdictBadge.tsx`, `VerdictBadge.module.css`; v2 layout
  `features/v2/v2.module.css`.
- Brand artwork: `docs/design/assets/{logo,favicon,app-icon,social}`; docs theme CSS already written at
  `docs/user/stylesheets/substation.css` (three schemes, self-hosted font-face) but not wired in `mkdocs.yml`.
- Libraries available: Radix Dialog and Dropdown Menu, react-hotkeys-hook.

## Design

- **Colour only from tokens** (007-DR-01): add `--sst-scrim` (thumbnail overlays) and `--sst-warn-tint`
  (notice banner) to all three theme blocks; replace the five literals (`v2.module.css` banner,
  `dataset.module.css` overlays, `frames.module.css`). A Vitest check (`design/tokens.test.ts`) reads every
  `*.module.css` under `src/features`, `src/components`, `src/routes` and fails on hex or rgba literals.
- **Night vision for rasters** (007-DR-07): one hidden inline SVG in `AppFrame` defines
  `<filter id="sst-red">` (feColorMatrix: luminance into red, green and blue to zero);
  `base.css` applies `filter: url(#sst-red)` to `img`, `canvas` and `svg image` under `[data-theme='night']`.
  Charts drawn with tokens already collapse to red; verdicts keep shape and glyph. Thumbnails, previews,
  master previews and calibration evidence are all `<img>`, so one rule covers them.
- **Theme persistence** (007-DR-06): an inline script in `index.html` applies `sst-theme` from localStorage
  before first paint. Per-user persistence: `accounts.UserPreference` (one-to-one, `theme`), exposed as
  `GET/PATCH /me/preferences`; `useTheme` writes through and adopts the server value after sign-in. The
  header select goes; Settings → Appearance (spec 008, T17) is the control.
- **Header** (007-DR-05): 56 px fixed height, no wrap; brand = inline `Logo` (mark 22 px + "SubStation"
  16/600/−0.01em); nav 14 px gap 28 px, full-height items, inactive 500, active 600 with the underline on the
  header's bottom edge; counts as mono 11 px pills (tint fill, accent text, accent-line border); right side
  "Watching N folders" (mono 12 px, 7 px ok dot), a divider and an account menu (Radix Dropdown: avatar
  initial, username; Sign out inside). The `QueueIndicator`, "N failed" and "N to reconcile" links leave the
  header: the Activity count is the queue indicator and reconciliation is reached from a Library notice.
- **Logo** (007-DR-08): `components/Logo.tsx` draws the converge mark inline (back frames
  `--sst-muted`, front frame and star `--sst-accent`), so dark, light and night need no file swap. Props for
  mark, horizontal lockup and size; clear space of a quarter of the mark height, lockup gap a third; below
  96 px wide renders the mark only; below 24 px uses the favicon-16 artwork. Concept marks stay in
  `docs/design/assets/logo/concepts` (not shipped).
- **Components** (007-DR-02, 03, 04, 13): cards `panel → card-end`; readouts radius 0.7rem, mono 34–36 px,
  500, −0.03em, first value accent; buttons per A.5 (primary tint fill at rest, secondary 500, danger,
  disabled dashed `--sst-dim`); verdict badge neutral pill with only the icon coloured; page container
  1240 px with 32 px gutters, titles 24 px 600 −0.02em with a 13 px muted summary.
- **Type** (007-DR-10): `font-feature-settings: 'cv11','ss01'` on body; `.mono` for paths and FITS keys.
- **Sign-in** (007-DR-11): mark 36 px and wordmark 24 px above the card; "Sign in" with "to the SubStation on
  <host>" (mono, `location.host`); Username and Password; allauth errors mapped to their field (`param`)
  with the voice-guide copy; footer "SubStation <version>" from `/health` (`version`, from the package
  version baked at build). No other copy.
- **Shortcuts** (007-DR-12): `components/Shortcuts.tsx` with `useShortcuts(screen, keys)` to register a
  screen's keys; `?` opens a Radix Dialog listing the global keys (N, ?) and the current screen's keys.
- **Confirmations** (007-DR-16): `components/Confirm.tsx`, an inline confirm row (message, danger action,
  Cancel) used instead of `window.confirm` in `MastersTab.tsx` and `CollectionView.tsx`.
- **Copy** (007-DR-14): `features/format.ts` gains signed numbers with U+2212, en-GB grouping, long and short
  dates, durations per A.9; one pass over feature copy; "—" for missing table values (decision table).
- **Favicons and app icon** (007-DR-09): copy `favicon-16/32/48.svg`, `favicon.svg` to `frontend/public`,
  add sized `<link rel="icon">`, `apple-touch-icon`, `theme-color` (`#080d14`); export the 512 px PNG app
  icon (22% radius) once from `substation-app-icon-512.svg` and commit it with the SVG.
- **Docs** (007-DR-15): `mkdocs.yml` palette with the three schemes and toggles, `font: false`, logo and
  favicon; woff2 files in `docs/user/fonts/`, artwork in `docs/user/assets/`.

## Constitution check

No principle is affected; VIII gains a per-user preference recorded against the user. Pass.

## Project structure

```text
frontend/index.html                        pre-paint theme script, favicons, theme-color
frontend/public/                           favicon-16/32/48.svg, favicon.svg, app-icon-512.png
frontend/src/design/                       substation-tokens.css (+2 tokens), base.css, theme.ts, useTheme.ts, tokens.test.ts
frontend/src/components/                   Logo.tsx, AccountMenu.tsx, Shortcuts.tsx, Confirm.tsx, ui.module.css, VerdictBadge.*
frontend/src/routes/                       AppFrame.tsx, frame.module.css, SignIn.tsx
frontend/src/features/                     v2.module.css, dataset.module.css, frames.module.css, format.ts
backend/apps/accounts/                     models.py (UserPreference), api.py (/me/preferences), migration
backend/substation/api/health.py           version
mkdocs.yml, docs/user/{fonts,assets}/
```

## Complexity tracking

None.
