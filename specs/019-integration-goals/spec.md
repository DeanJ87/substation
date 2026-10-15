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
