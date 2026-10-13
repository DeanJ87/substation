

- **007-DR-24 Hover to see a frame.** Hovering a file name or frame reference (reconcile files, quality table,
  master inputs, calibration frames, review) shows the frame beside the pointer after a short pause, from its
  existing preview or a small one drawn from the file and cached (`GET /frames/{sha}/glance`).

## Amendment 2026-10-13: scrolling panes hand off to the page

- **007-DR-25**: A pane that scrolls inside the page (tables, queues, frame grids) lets the page carry on scrolling
  once the pane reaches its end, so the pointer is never stuck inside one. No pane sets `overscroll-behavior:
  contain`.
