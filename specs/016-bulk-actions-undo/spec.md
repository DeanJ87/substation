# Feature Specification: Bulk actions and undo

**Feature Branch**: `poc-substation`
**Created**: 2026-10-15
**Status**: Built 2026-10-15 (first slice: subs)
**Input**: Owner request, 2026-10-15 (site review items 2 and 10): clearing the review backlog takes a click per
sub; agreeing with a night's automatic grades should be one action; actions in general should work on many
things at once, and a change made by hand should be undoable.

## User scenarios

1. **Agree with a night.** On a dataset's Subs tab, each session offers "Agree with N flagged". The flagged subs
   (rejected, down-weighted or near a threshold, not decided by hand) keep their automatic grade as the owner's own
   verdict and leave the review list. "Agree with N flagged" in the filter bar does the whole dataset, after a
   confirmation.
2. **Select many.** Each session has "Select all"; with a selection, "Select all N shown" extends it to everything
   the filter shows. Ctrl/Cmd+A, shift-click and the A, W, R, U keys work as before.
3. **Undo.** After a change to several subs, binning, or agreeing, a toast says what was done, with Undo.
   Ctrl/Cmd+Z anywhere (outside a text field) undoes your latest change. Activity → Your changes lists recent
   changes with Undo on each.

## Requirements

- **FR-001** Every verdict change, agreement and binning is recorded as one change: who, what (a sentence), how many,
  when, and what undoing needs.
- **FR-002** Undoing a verdict change or an agreement removes that change's own verdict rows; a later verdict on the
  same sub stays in force. Undoing binning restores the files it binned.
- **FR-003** A change can be undone once, by the person who made it or an admin, for 30 days; otherwise the reason
  is given.
- **FR-004** Agreeing maps reject → reject, down-weighted → keep (down-weighted), near a threshold → accept, and
  skips subs already decided by hand or marked bad in NINA.
- **FR-005** Read-only accounts can't agree or undo.
- **FR-006** Undo, Select all and Agree are buttons with text, keyboard reachable; the toast's Undo is a button.

## Later

The same selection and undo for other lists: calibration sets (build, QA overrides), collections (archive, spec
013), datasets in the Library (stack, re-grade), Activity jobs (retry or dismiss many).
