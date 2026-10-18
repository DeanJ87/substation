# SubStation roadmap (after the MVP)

Ideas captured for later; not specified yet.

- Infographics over the results: SNR growth as subs are added to a stack, integration over time per
  target, quality across nights and seasons.
- Animated progression of a dataset (for example a GIF or video of the stack building up night by night).
- Two-factor authentication (designed in from the start; switched on after the MVP).
- Blink review, re-grade, stacking options, automatic nightly stacks (specified; after the POC).
- Finished work and a public API (2026-10-18): finished output lives in one place per project
  (`Completed/<Astro|Nightscapes|Videos>/<subject>/<YYYY…> <name>/` with `project/`, `exports/`, `web/`, `social/`)
  and a `project.json` manifest that SubStation fills from its data: target, collection, nights, rigs, filters and
  integration, the sky track. A documented read API then lets a separate app pick up a project's output, data and
  skies to make visuals and videos for social media.
