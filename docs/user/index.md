# SubStation

SubStation watches the folders your capture software writes to, catalogues every sub as it lands, and keeps
track of it wherever it goes afterwards. It runs on your own machine (a NAS is ideal) and never changes,
moves or renames your files.

## What it does today

- **Catalogues subs as they arrive.** Each sub appears in its dataset (target, panel and filter) within
  seconds of NINA finishing the file.
- **Knows files by content.** Moves, renames and copies keep their history. NINA's thumbs-down (the `BAD_`
  rename) counts as your rejection, and a duplicate never counts twice.
- **Reads headers first, and lets you fill gaps.** When software writes a poor header, a path pattern can read
  the value from the folder or file name, or you can give it once in **Reconcile**. Every value shows where it
  came from.
- **Groups calibration frames.** Flats, dark flats and bias are grouped into sets by session; masters you made
  in PixInsight are recognised.
- **Queues big drops.** Hundreds of files after a trip are worked through in the background, and live subs
  always go first.

Stacking, grading subs and building masters come next.

## Words used in SubStation

| Word | Meaning |
|---|---|
| Sub | One exposure: a light, flat, dark, dark flat or bias |
| Dataset | Every light of one target, panel, filter, camera and telescope (and gain, offset, binning), across all nights |
| Night | The observing night: an evening and the morning after it, at your site |
| Library | A folder SubStation watches, mounted read-only |
| Reconcile | The list of things SubStation couldn't work out on its own |
