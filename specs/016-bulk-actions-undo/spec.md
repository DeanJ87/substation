# Feature Specification: Bulk actions and undo

**Feature Branch**: `poc-substation`
**Created**: 2026-10-15
**Status**: Built 2026-10-15 (subs; then calibration, datasets and failed jobs, U6)
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

## Amendment 2026-10-15: bulk selection beyond subs (U6)

Built for calibration sets and frames, datasets and failed jobs. Archiving collections stays with spec 013.

**Scenarios**

4. **Build several calibration sets.** On Calibration → Raw sets, each row has a choose box and each night's
   header one for the whole night. With any chosen, a bar says how many and offers Build masters and Select all
   N shown. Sets already building, and anything that is not a raw set, are skipped and the toast says why.
5. **Use or leave out several calibration frames.** On a raw set's page each frame tile has a choose box; the
   bar offers Use them, Leave them out, Clear your choice and Select all N. The toast offers Undo.
6. **Act on several datasets.** In the Library's Not in a collection list and on a collection's Datasets tab,
   rows have choose boxes (the tab's header box chooses every row shown). The bar offers Re-grade (one job, your
   own verdicts kept), Stack (after a confirmation; the default rule: accepted and down-weighted subs, every
   night; a dataset that can't be stacked is skipped with the reason), and Move to another collection, or out of
   this one. Moving is undoable from the toast, Ctrl/Cmd+Z or Activity → Your changes.
7. **Retry or dismiss several failed jobs.** In Activity → Recent, each failure (or group of the same failure)
   has a choose box, and Select all N failed chooses them all. The bar offers Retry (admins) and Dismiss; a
   group's own Retry all and Dismiss all work the same way. Dismissing is undoable.

**Requirements**

- **FR-007** Three more kinds of change are recorded: `move` (datasets to another collection, or out of one; it
  keeps each dataset's previous collection, project and place in the project), `dismiss` (failed jobs taken off
  Activity; it keeps each job's previous note) and `qa` (your QA choice on calibration frames; it keeps each
  frame's previous choice). Only frames, datasets and jobs that actually changed are recorded; when none did,
  nothing is recorded and no Undo is offered.
- **FR-008** Undoing a move puts back only datasets still in the collection they were moved to; undoing a
  dismissal shows again only jobs still dismissed; undoing a QA choice restores only frames whose choice is still
  the one made. A later change stays in force (as FR-002).
- **FR-009** A moved dataset leaves any project of the collection it came from (projects belong to a
  collection); undoing restores the project too. Both collections' object lists are refreshed.
- **FR-010** Endpoints: `POST /bulk/calibration-sets/build`, `POST /bulk/datasets/regrade`,
  `POST /bulk/datasets/stack`, `POST /bulk/datasets/move` (returns `change_id`), `POST /work/bulk/jobs/retry`
  (admins), `POST /work/bulk/jobs/dismiss` (returns `change_id`); `POST /calibration-qa/override` now returns
  `change_id`. Up to 500 at a time; read-only accounts are refused every one of them.
- **FR-011** Every bar is a toolbar named for what is chosen, states the count, has buttons with text reachable
  by keyboard and a Clear; Escape inside it clears the choice. Choose boxes are labelled with what they choose.
