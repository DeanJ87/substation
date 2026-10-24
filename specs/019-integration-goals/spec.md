# Feature Specification: Integration goals

**Feature Branch**: `poc-substation`
**Created**: 2026-10-15
**Status**: Built 2026-10-15
**Input**: Owner, 2026-10-15 (site review item 4, "could be nice"): hours wanted per target, to see how far along
each is.

## User scenarios

1. On a collection's Overview, Goals → Set goals: hours of usable integration wanted per filter (any filter,
   including ones not shot yet). Each shows a bar: kept so far, still waiting (calibration or grading), and the
   rest to go, with "x of y · n% · z to go".
2. The Library's collection cards show "kept / goal" for filters with a goal.

## Requirements

- **FR-001** Goals are per collection and filter, in hours, 0–1,000; clearing one removes it.
- **FR-002** Progress counts usable (accepted or down-weighted) integration only; waiting integration is shown
  apart and doesn't count until graded.
- **FR-003** The bars are labelled for screen readers (progressbar with a value) and line up across rows.

### Amendment 2026-10-15: goals belong to projects

- **019-DR-01** A target is usually shot in more than one way over the years (a single field on one rig, later a
  20-panel mosaic on a longer one), so goals belong to a project, not the collection. A collection's existing goals
  moved to its newest project. The Library card shows every project's goals added up.
- **019-DR-02** Projects are cards on the collection's Overview (replacing the row of project pills under the
  title): name, kind and panels, rigs, months, and per filter a bar of kept (and waiting) integration against that
  project's goal, or against the project's biggest filter where there's no goal. Each card has "Show only this"
  (the page narrows to it, with a "Showing only …" note and "Show everything") and "Edit" (name, kind, panels,
  goals, remove). Datasets not in a project have their own card with "Suggest projects"; "Arrange datasets…"
  opens the drag-and-drop board.
- **019-DR-03** (2026-10-22) Merging projects keeps the larger goal for each filter and says where they differed;
  projects marked Done leave the collection's goal totals.

### Amendment 2026-10-24: a mosaic's goals are per panel

- **019-DR-04** A goal on a mosaic project is hours per panel (a 6 h Hα goal on six panels is 6 h for each). The
  project card's bar for a filter with a goal shows its least-covered panel against the goal ("2h / 6h per panel"),
  a planned panel not shot yet counting as none, and its accessible text names that panel and how many panels have
  reached the goal; the panel × filter table shows each column's goal and marks the panels that reached it. Goals
  are entered as hours per panel. The Library card's and collection's totals count a mosaic's goal once per panel
  (planned panels, or the panels shot when there are more). A single field is unchanged. The project carries its
  integration per panel and filter, and how many panels its goals are for.
