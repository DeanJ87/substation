# Calibration

**Calibration** lists your raw flats, darks, dark flats and bias, grouped into sets by session. It also lists
the masters SubStation found or built. SubStation calibrates each light with a matching master dark and
master flat. A light with no match waits as *Awaiting calibration*, and the note names what's missing.

## Inspecting a set

Open a set to see a contact sheet of every frame. SubStation checks each frame against the rest of its set:

| Verdict | Meaning |
|---|---|
| *Pass* | Consistent with the rest of the set |
| *Check* | Its level differs from the set's, or (for flats) the exposure is outside 10–85% of full scale, or more than 1% of pixels are saturated. Still used |
| *Rejected* | A truncated readout (more than 2% of rows or columns are zero, usually a transfer fault). Left out of the master |

Choose **Leave out** or **Use it** on a frame to override the verdict; **Undo** returns it to SubStation's.

## Building masters

**Build master** on a set, or **Build missing masters** on the Calibration page, stacks the frames that passed
with Siril:

- Darks, dark flats and bias: winsorised sigma clipping, no normalisation.
- Flats: first calibrated by a master dark flat at the same exposure (a master dark at exactly that exposure
  also works), or else by a master bias, then stacked with multiplicative normalisation. With neither, the build
  is *blocked* and says why. You can build it anyway, but the flat will carry the sensor's offset.

Bias and dark flats are built first, so the flats that need them find them; then flats, then darks. A built master records which
frames it used, which it left out and why, and which master calibrated it. It joins matching straight away,
and lights waiting for it are calibrated.

An old flat is fine: if your optical train hasn't changed, SubStation uses it whatever its age.

## Flat reports and dust motes

Each master flat gets a report:

- **Corner falloff**: how much darker each corner is than the centre.
- **Radial profile**: brightness from the centre to the edge.
- **Dust motes**: darker rings against the smooth illumination, with their position, size and depth.
- **Dust map**: the flat divided by its own smooth illumination, so vignetting drops out and dust shows as dark
  rings, with each measured mote circled. For colour cameras the analysis works on 2×2 superpixels, so the
  Bayer pattern isn't mistaken for dust.

When a set already has a master of the same kind (camera, gain, exposure, and filter for flats), the new one is
compared with it: for flats as a ratio image, where dust that moved, arrived or left shows up; for darks and
bias as a difference.

## Disk space

Calibrated subs are kept as a cache for stacking: 40 GB by default (`CALIBRATED_CACHE_GB`). When it's full
the oldest are deleted, and a stack that needs one calibrates it again.
