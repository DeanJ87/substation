# Feature Specification: Settings

**Feature Branch**: `008-settings`

**Created**: 2026-10-10

**Status**: Draft

**Input**: SubStation v2 design, Activity file A4 (Settings) and Screens 09, reviewed in `docs/design/design-review.md`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - One page for every setting (Priority: P1)

Settings is one scrolling page with a left rail: Folders, Rigs, Grading, Stacking, Plate solving, Metadata
sources, Path patterns, Ignored, Notifications, Workers, Users, Appearance. Changes collect in a sticky save bar
that says what changed and what it will cause (re-grades), with Discard and Save.

**Independent Test**: Change a grading threshold: the save bar names the change and the datasets that would be
re-graded; Save and re-grade queues them; Discard restores the values.

### Edge Cases

- Leaving the page with unsaved changes asks in-page (not a browser dialog).
- A read-only user sees settings but cannot change them.

## Requirements *(mandatory)*

1. **008-DR-01**: Settings MUST be one scrolling page with a left rail that jumps to its sections: Folders, Rigs,
   Grading, Stacking, Plate solving, Metadata sources, Path patterns, Ignored, Notifications, Workers, Users,
   Appearance.
2. **008-DR-02**: Folders MUST list each watched folder with its role (Lights, Lights archive, Calibration), status
   with a dot ("Watching · last file 3 min ago", "idle since 28 Sep") and Edit. It MUST show the output folder with
   free and total space and offer "Add folder".
3. **008-DR-03**: Grading MUST say "Each sub is compared with the median of its own session." It MUST show, per
   measure, the down-weight and reject levels with their direction (above or below) and a one-line explanation, and
   MUST include the switch "Use SQM and cloud when recorded" ("A sub is flagged, not rejected, on SQM or cloud
   alone").
4. **008-DR-04**: Changes MUST collect in one sticky save bar that states what changed ("FWHM reject threshold
   1.60× → 1.50×") and, for grading changes, how many datasets would be re-graded and that manual overrides are
   kept. It MUST offer Discard and "Save and re-grade" (or Save).
5. **008-DR-05**: Workers MUST set the worker count (shown as "N of M CPU threads") and the priority (New subs first
   or In order). Activity's "Worker settings" MUST link to this section.
6. **008-DR-06**: Notifications MUST offer channels (ntfy topic, webhook, email), event choices (Master finished,
   Job failed, Awaiting calibration, Session summary) and "Send test". The description MUST read "Sent when
   something needs you, not for routine work."
7. **008-DR-07**: Users MUST list accounts with role and last sign-in, offer "Add user", and support a read-only role
   ("can review, can't override").
8. **008-DR-08**: Appearance MUST offer Dark, Light and Night vision as a segmented control with the note "Press N
   anywhere for night vision".
9. **008-DR-09**: Rigs MUST show camera, focal length, image scale, mount type when known and session count, with
   Edit (rename, merge) and "Add rig".

## Amendment 2026-10-11 (owner): tabbed settings

- **008-DR-10 Tabs.** Settings is tabbed down the side (Library, Rigs, Processing, Workers, Notifications, Users,
  Appearance), not one long page; links to a section (/settings#workers) open its tab.
- **008-DR-11 Ignored list pages.** Ignore rules load 40 at a time, sorted on the server, in a pane that scrolls
  on its own; only the rules shown are counted.
- **008-DR-12 Rows line up.** Rig rows put their controls in fixed columns.

## Amendment 2026-10-12: file paths, not downloads

Downloading a master the user can already reach on the share is wasted effort; showing its path (mapped to how
each machine mounts the share, e.g. a Windows drive letter) lets them open it in place.

- **008-DR-10**: Masters and combined masters MUST show where their file is, with a Copy path button, instead of a
  download. Server paths are mapped by prefix (Settings → Library → File paths, for everyone), and a browser MAY
  keep its own mappings, which win. Windows targets (a drive letter or `\\server`) get backslashes.

## Amendment 2026-10-14: Pushover

- **008-DR-13**: Notifications can go to Pushover as well as ntfy and a webhook: a user (or group) key and the
  application's API token, each 30 letters and digits. A failed job is sent at high priority; a link opens the item
  in SubStation. Only admins see the keys and private addresses; other users see that a channel is set.

### Amendment 2026-10-15: open in place, or download

- **008-DR-14 Each browser chooses how it gets files.** Settings → File paths has a per-browser choice: open files
  where they are (the path mapped to this machine's share, with Copy path), or download them. Masters, combined
  masters and every processed version (GraXpert, BlurXTerminator, NoiseXTerminator) offer both; a file no mapping
  reaches from this browser downloads even when opening in place is chosen, since a path the machine can't reach is
  of no use. Processed versions gained their own download (`/stacks/{id}/post/{run}/{stage}/download`).

### Amendment 2026-10-17: libraries' access and roles

- **008-DR-15**: Settings → Library → Folders says whether each library is mounted read-write or read-only, and
  holds each library's archive role and an active library's archive (spec 013), plus how many days without new subs
  before a collection is suggested for archiving (`processing.archive.suggest_after_days`, 0–3,650, default 60). A
  control a read-only library can't use stays visible, disabled, with the reason beside it.

### Amendment 2026-10-17: open in Finder

- **008-DR-16**: Where a file's server path is mapped to a network share (`\\host\share\…`, for everyone or for
  this browser), a browser on a Mac also shows **Open in Finder**: an `smb://host/share/…/` link to the folder holding
  the file, which Finder opens directly. A web page can't open a file on the viewer's machine itself, so the file
  stays one click away in its folder; Copy path remains for every machine. Other systems don't open `smb://` links
  from a browser, so they keep Copy path only.
