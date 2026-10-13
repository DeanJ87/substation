# SubStation spike · phase 2 report

Date: 2026-10-09 · Engine: Siril 1.4.2 in `substation-siril:1.4.2` (Debian forky, arm64; Dockerfile from phase 1)
Source: `/scratch/substation-spike/sub-test` (read-only; mounted `:ro` into every container) · Work: `/scratch/substation-spike/phase2-work`
Visual report: `phase2/report.html` (images in `phase2/img/`). Scripts: `scripts/phase2/`. Data tables: `phase2/out/`.

## Summary

| Step | Result | One line |
|---|---|---|
| 1 Inventory, dedupe, grouping | **PASS** | 653 raw files → **636 unique subs**; 17 BAD_ copies folded into REJECT verdicts; 8 light sets, 6 flat sets, 3 dark-flat sets, 0 raw darks; 45 reconciliation items |
| 2 Calibration QA | **PASS** | 552 frames; **1 REJECT (truncated readout)**. **No star contamination found in any dark** on any test (raw dark flats, WBPP master darks, their rejection maps), and an injection test shows the detector would have caught it |
| 3 Masters | **PASS** | 3 master dark flats and 6 master flats, each built from all frames and from frames excluding QA rejects. Old 08-15 WBPP flats agree within 0.5% for L, R, G and OIII but **differ by about 5% for Hα and SII** |
| 4.1 On-arrival path | **PARTIAL** | Works for 60 subs, but `calibrate_single` **only reads FITS**, so every XISF must be `load`/`save`-converted first. 2–5 s per sub vs about 0.6 s per sub in batch |
| 4.2–4.4 Lights at scale | **PASS** | 4 datasets (60 subs): grader vs NINA verdicts, all vs excluded stacks with centre and corner PSF, time, RAM and disk |
| 5 Siril vs WBPP | **PARTIAL** | Distortion correction, background extraction, drizzle and noise weighting run like-for-like. None improves quality on this data. The WBPP side is researched only; PixInsight isn't available to measure |
| 6 Visual report | **PASS** | `report.html` |

The biggest surprises:
1. **Siril's FITS are vertically flipped relative to XISF.**
2. **`select`/`unselect` index by position, not file number**, which silently picked the wrong subs once.
3. **Docker Desktop leaks disk space on the T7 bind mount.**
4. **`OBJCTROT` is not the camera angle.**
5. **The darks are clean.**

---

## Step 1 · Inventory, dedupe, grouping: PASS

Commands:

```
uv run scripts/phase2/inventory2.py $SRC phase2/out/inventory.csv phase2/out/inventory_flags.csv
uv run scripts/phase2/grouping2.py  $SRC phase2/out/inventory.csv phase2/out/
```

- The new tree holds 689 image files (all uncompressed; lights, flats and darks are UInt16 6224×4168). Every one carries a SHA-256.
- **17 BAD_ files fold into REJECT verdicts on their twins.** One, `BAD_2026-09-29_01-29-50_Halpha_…_0031.xisf`, has **no unprefixed twin** (Robocopy evidently never copied the original). It is kept as one sub with a REJECT verdict.
- **The new folder called DARK holds no darks for the lights.** It has 250 frames with `IMAGETYP='DARK'` and `OBJECT='FlatWizard'` at 0.01, 1 and 2 s, so they're dark flats.
  - Classification uses `OBJECT=FlatWizard` or an exposure matching a flat set on the same night.
  - There's no header that says "dark flat".
  - The 600 s darks for the lights exist only as the WBPP master (owner confirmed), so each light set is on the reconciliation list.

| Sets | Count | Exposure | CCD-TEMP | UTC |
|---|---|---|---|---|
| NGC 7000 P2 Hα | 6 (2 NINA REJECT) | 600 s | −20.0 | 09-28 19:05–20:00 |
| NGC 7000 P3 Hα | 24 (5) | 600 s | −20.1…−19.9 | 09-28 20:16 → 00:29 |
| Heart P2 Hα | 15 (4) | 600 s | −20.0…−19.9 | 09-29 00:43–03:36 |
| Heart P2 Luminance | 1 (1) | 600 s | −20.0 | 09-29 03:11 |
| Phase 1 sets (10-07) | 15 / 11 / 10 / 2 | 600 s | | unchanged |
| Flats L / R / G | 51 / 51 / 50 | 0.01 / 1 / 1 s | −20.5…−19.1 | 09-29 03:49–04:15 |
| Flats SII / Hα / OIII | 50 / 50 / 50 | 2 s | −20.1…−19.8 | 09-29 04:00–04:07 |
| Dark flats 2 s | 150 (blocks SII 50, Hα 50, OIII 50) | 2 s | −20.1…−19.9 | 04:07–04:14 |
| Dark flats 0.01 s / 1 s | 50 / 50 (labelled Luminance / Red) | | −20.3…−19.3 | 04:16–04:18 |

- Green flats (1 s) use the 1 s dark flats that NINA labelled "Red"; dark flats are filter-independent, so that's correct.
- The L and R flat sets each contain one extra frame (seq 0000) taken 25 minutes after the rest, matching the set.

**Reconciliation list** (`phase2/out/reconciliation.csv`, 45 items):
- 36 WBPP masters lack GAIN, OFFSET, CCD-TEMP and SET-TEMP; their temperature comes from the path only.
- 8 light sets have no raw 600 s darks, so they use the WBPP master, whose gain and offset can't be verified.
- 1 BAD_ file has no twin.

## Step 2 · Calibration-frame QA: PASS

Output: `phase2/out/calibration_qa.csv` (552 rows, with verdict, reason and details per frame), plus contact sheets `phase2/img/contact_*.png`.

| Check | Method | Result |
|---|---|---|
| Per-frame statistics | median, mean, MAD, min, max, saturated fraction, 32 px block-median map (`calqa_stats.py`) | All flats sit at **48–52% of the 16-bit range**, with 0 saturated pixels and medians within ±0.3% of their set. Dark flats are at 80 ADU (the offset), MAD 2 |
| Stars, Siril defaults | `findstar` on every frame, one pipe-mode worker (`calqa_findstar.py`) | 0 stars in all 552. **Not evidence:** with defaults, findstar also misses all 200 injected 30 ADU stars |
| Stars, Siril tuned | `setfindstar -sigma=0.3 -relax=on`; `findstar` (all 250 darks) | 0–4 detections per frame, all FWHM < 1.1 px, i.e. hot pixels. Tuned findstar recovers 200/200 injected stars at 30 ADU and 0/200 at 8 ADU |
| Stars, residual detector | frame − set median (cancels consistent hot pixels and amp glow), 3×3 median, matched filter, PSF-shape cut (`calqa_leaks.py`) | 0–10 PSF-like detections per frame, at the false-alarm level of 1–3. Injection recovery: **≥ 99% at 15 ADU peak**, 12–47% at 8 ADU |
| Large-scale structure | block-median residual: gradient and level vs set | Normal everywhere except the truncated frame |
| WBPP master darks and bias | same detector on the integration image (`calqa_masters.py`) | 9–232 low-SNR detections each. About **25% recur at the same pixel across masters from different sessions and sites** (random positions: 0), so these are sensor features, not stars |
| WBPP rejection maps | clustering of multi-frame `rejection_high` pixels (`calqa_rejmaps.py`, `rejmap_cluster.py`) | Mild clustering (1.4–4× chance), largest blob ≤ 17 px, the same at both sites: sensor behaviour. Stars from an open panel would leave thousands of large, strongly rejected blobs |
| Flats: rotation | `OBJCTROT`, rotator keywords | No rotator keyword exists; `OBJCTROT` is 0.0 on flats. **Plate solving shows the camera never rotated** (step 4) |
| Flats: matching dark flat | by exposure, gain, offset, night | Present for all 6 sets |

**Verdicts:** 551 PASS, **1 REJECT**: `2026-09-28/DARK/2026-09-29_05-11-47_Halpha_-19.90_2.00s_0045.xisf`, a **truncated readout** in which rows 1600–4167 (62%) are zero. It looks like a USB transfer fault, not a leak.

**Light leak: not found.** No raw dark flat, master dark or rejection map shows stars, and no dark flat shows flat-panel light (every median is 80 ADU). Two explanations would fit the owner's belief: the contaminated darks aren't in this tree, or they were discarded. A rough photon estimate says an open panel during a 2 s narrowband dark would put dozens of 7th–9th magnitude stars well above 15 ADU, which this detector catches at 99–100%. Evidence is in `img/evidence/`: the injection control and the strongest real detection (SNR 7, FWHM 4.2, at the false-alarm level).

## Step 3 · Masters with Siril: PASS

**Method.** I followed Siril's bundled `Mono_Preprocessing.ssf` v1.4 (`/usr/share/siril/scripts`), substituting dark flats for bias. The commands are in [Commands.html](https://siril.readthedocs.io/en/latest/Commands.html) and the normalisation rules (none for darks, multiplicative for flats) in [stacking.html](https://siril.readthedocs.io/en/latest/preprocessing/stacking.html).

```
# staged as symlinks inside the container (Siril refuses to cd into the read-only source)
convert df -out=/work/proc_df_2s
stack df_ rej 3 3 -nonorm -out=/work/masters/master_df_2s_all
select df_ 1 150 ; unselect df_ <pos> <pos> ; stack df_ rej 3 3 -nonorm -filter-included -out=…_clean
convert fl -out=/work/proc_flat_X
calibrate fl_ -dark=/work/masters/master_df_2s_all.fit   -prefix=call_  ; stack call_fl_ rej 3 3 -norm=mul -out=…_all
calibrate fl_ -dark=/work/masters/master_df_2s_clean.fit -prefix=cdfclean_ ; stack cdfclean_fl_ rej 3 3 -norm=mul -out=…_dfclean
```

- The stacking page also calls median "mostly used" for darks and flats; I used the bundled script's winsorized `rej 3 3` instead.
- For comparison, your WBPP `ProcessingHistory` shows: darks averaged with winsorized clipping (σ 4/3) and no normalisation; flats with **linear-fit** clipping, multiplicative normalisation and equalise-fluxes.

| Master | Frames | Result |
|---|---|---|
| Dark flat 2 s | 150 vs 149 | all − clean: median 0, max \|Δ\| 17 ADU, 0.009% of pixels > 0.5 ADU. **Winsorized rejection absorbed the truncated frame.** Exclusion still matters for small sets |
| Dark flat 1 s, 0.01 s | 50, 50 | No QA rejects, so the clean master equals the all-frames master |
| Flats SII, Hα, OIII | 50 each | Using the all vs clean dark flat changes the master flat by ≤ 0.44% at isolated pixels: negligible |

| Flat | Falloff mean % (TL/TR/BL/BR) | Dust motes | New / old 08-15 WBPP ratio range |
|---|---|---|---|
| Luminance | 3.0 (2.65/2.99/2.96/3.36) | 4 | **0.47%** |
| Red | 3.0 (3.39/3.77/2.34/2.48) | 6 | **0.43%** |
| Green | 3.0 (2.81/3.27/2.92/3.09) | 5 | **0.43%** |
| OIII | 3.4 (4.77/6.24/0.96/1.75) | 6 | **0.24%** |
| Hα | 5.4 (2.63/4.98/6.92/6.91) | 12 | **5.06%** (TL corner ×1.034) |
| SII | 6.4 (5.96/4.86/8.77/5.82) | 14 | **4.89%** (TL corner ×0.965) |

- **The old 08-15 flats would have been nearly right for L, R, G and OIII, but wrong by 3–5% in the corners for Hα and SII.** The Hα ratio image shows a smooth left-to-right ±5% illumination difference, plus dust-mote rings that moved.
- This corrects my phase 1 statement: on shape, the OIII flat used there was fine.
- Our 2 s master dark flat vs WBPP's −20c 2 s master (different frames, March vs September): median 80.29 vs 80.26 ADU, difference p0.1/p99.9 −4.5/+5.0 ADU.
- No existing WBPP master covers the same frames, so there's no like-for-like WBPP-vs-Siril master comparison.

## Step 4 · Lights at scale

### 4.1 On-arrival path: PARTIAL

`scripts/phase2/arrival_worker.py` runs one long-lived `siril-cli -p` process per dataset. Each arriving sub is staged as `light_NNNNN.xisf` (NNNNN = arrival order), then:

```
load /tmp/stage/light_00007.xisf
save light_00007                                   # calibrate_single only reads FITS
calibrate_single light_00007.fit -dark=/work/masters/wbpp_dark_-20c_600s.fit -flat=/work/masters/master_flat_Halpha_2s_dfclean.fit -cc=dark -prefix=pp_
load pp_light_00007 ; findstar ; bgnoise ; stat    # per-sub metrics on arrival
```

When the dataset closes, the individually calibrated `pp_light_NNNNN.fit` files form a valid sequence `pp_light_` and Siril finds it automatically: `register pp_light_ -2pass` worked on all 60 subs.

- **FAIL as specified:** `calibrate_single <x>.xisf` gives "FITS error: This does not look like a FITS file", even though `load` reads XISF.
- **Cost:** convert 0.6–1.8 s plus calibrate 1.7–4.7 s per sub (median 1.7–2.2 s on the larger sets), against about 0.6 s per sub in batch. Each call reloads both masters and re-derives the hot-pixel map from the dark. Trivial next to a 600 s exposure.
- Metrics on arrival take 0.22–0.28 s per sub. Peak RSS of the worker is 480 MB.

### 4.2 Grader vs NINA BAD_ verdicts

The grader is phase 1's median-relative one: wFWHM > 1.5× median, stars < 0.6×, background > 2×, or roundness < 0.85. Subs that fail registration are now an explicit REJECT.

| Dataset | NINA REJECT | Grader REJECT | Both | NINA only | Grader only |
|---|---|---|---|---|---|
| NGC 7000 P3 Hα (24) | 1, 16, 22, 23, 24 | 22, 23, 24 | 22, 23, 24 | 1, 16 | – |
| Heart P2 Hα (15) | 6, 7, 8, 9 | 1, 2, 3, 5, 7, 8, 9 | 7, 8, 9 | 6 | 1, 2, 3, 5 |
| NGC 7000 P1 OIII (15) | 1, 5, 7, 8, 15 | 1, 5, 7, 8 | 1, 5, 7, 8 | 15 | – |
| NGC 7000 P2 Hα (6) | 5, 6 | 2, 3, 5 | 5 | 6 | 2, 3 |

- **Every frame NINA and the grader both reject is a clearly bad frame:** clouded subs with 0 or 50 stars that failed registration (P3 #24, Heart #7–9), or high-background twilight.
- **NINA-only:** #1 on P3 and OIII are early twilight frames. The others (P3 #16, Heart #6, OIII #15) are indistinguishable from accepted neighbours on these metrics.
- **Grader-only:** Heart #1–3 have wFWHM 7.7–9.0, 2× the median, and **header data explains them**. FWHM grows steadily between autofocus runs and drops at every `FOCPOS` change (Heart sub 4: 4605 → 4590 steps, wFWHM 9.0 → 4.4; sub 10: 4590 → 4584, wFWHM → 2.7), while `FOCTEMP` falls 11 → 6 °C. That's focus drift, and the product can show it.

### 4.3 Stacks: (a) all subs vs (b) excluding grader and NINA rejects

`register pp_light_ -2pass` → `seqapplyreg pp_light_ -framing=current` → `stack r_pp_light_ rej 3 3 -norm=addscale -weight=wfwhm`, then `select`, `unselect <positions>` and `stack … -filter-included`. Stars come from `findstar -out=` on each stack. Regions: centre third, corner fifths.

| Dataset | Stack | Subs | Noise ADU | Stars | FWHM | Centre | TL | TR | BL | BR |
|---|---|---|---|---|---|---|---|---|---|---|
| P3 Hα | all | 24 | 2.87 | 3161 | 3.37 | 3.08 | 3.96 | **5.35** | 2.93 | 4.08 |
| P3 Hα | excl | 19 | 3.40 | 2932 | 3.25 | 2.97 | 3.84 | **5.28** | 2.81 | 3.92 |
| Heart Hα | all | 15 | 4.59 | 3870 | 2.82 | 2.73 | 3.58 | 4.04 | 2.44 | 2.87 |
| Heart Hα | excl | 7 | 5.72 | 3280 | 2.73 | 2.64 | 3.55 | 4.30 | 2.33 | 2.74 |
| OIII | all | 15 | 4.36 | 3497 | 2.74 | 2.60 | 3.24 | **4.76** | 2.49 | 3.59 |
| OIII | excl | 10 | 5.30 | 3187 | 2.71 | 2.58 | 3.20 | **4.71** | 2.47 | 3.55 |

FWHM is in pixels at 1.58″/px. Roundness is 0.88–0.98 everywhere; see the HTML for per-region values. NGC 7000 P2 (6 subs, only 2 left after exclusion) is in the HTML but not meaningful.

- **Exclusion sharpens the stack 1–4% and costs 18–25% in noise.** Neither noise nor FWHM alone tells the story.
- **The field-dependent PSF is unchanged by any selection:** the top-right corner is +70–80% FWHM vs centre on both nights and every target, and bottom-left matches the centre. That pattern looks like sensor tilt or a collimation fault, which the product should report as an equipment finding, not a sub-selection one.

### 4.4 Time, RAM, disk at scale

| Dataset | Subs | A on arrival | B register + apply + stack | C excluded stack + measure | Peak RSS (B) | Peak work dir | After cleanup |
|---|---|---|---|---|---|---|---|
| NGC 7000 P3 Hα | 24 | 58.8 s (2.0 s/sub) | 50.1 s (register 9.1, apply 19.5, stack 20.7) | 12.3 s | 4.3 GB | **4.75 GB** | 0.2 GB |
| Heart P2 Hα | 15 | 32.1 s | 18.8 s | 3.6 s | 3.8 GB | 2.81 GB | 0.2 GB |
| NGC 7000 P1 OIII | 15 | 42.8 s | 33.4 s | 5.5 s | 3.8 GB | 3.10 GB | 0.2 GB |
| Masters (per flat set, 2 variants) | 50 | | 104–390 s | | 5.2 GB | 13–14 GB | 0 |
| Master dark flat 2 s | 150 | | 98 s | | **7.6 GB** | 7.35 GB | 0 |

- About **200 MB of intermediates per light** at peak (calibrated plus registered float32), deleted after previews.
- The work directory peaked at 14 GB in total. T7 never went above 50% used.

## Step 5 · Siril vs WBPP: PARTIAL

**What WBPP does that this pipeline didn't.** This is from forum sources and your masters' `ProcessingHistory`; the WBPP documentation page returned 404, so treat the defaults as unverified:
- PSF Signal Weight sub weighting
- Local Normalization (a per-sub spatial background and scale model, grid 4 by default; known to be CPU-heavy)
- StarAlignment with optional distortion correction
- automatic CosmeticCorrection
- drizzle data generation
- calibrated, cosmetised, registered and LN intermediates (`.xnml`, `.xdrz`) written to disk
- linear-fit clipping for flats

PixInsight isn't installed here, so **no WBPP step was timed**. The comparison below is Siril with and without each equivalent, on the same 15 calibrated OIII subs (`step5_variants.py`, `step5_snr.py`).

| Variant | Siril commands | Wall, median of runs | Δ per sub | FWHM | Centre / TR FWHM | Relative SNR |
|---|---|---|---|---|---|---|
| v0 baseline | `register -2pass`; `seqapplyreg`; `stack … -weight=wfwhm` | **24 s** (24, 23.5, 147) | — | 2.74 | 2.60 / 4.76 | 1.00 |
| v1 distortion correction | `platesolve -order=3 -catalog=gaia -disto=…wcs` (4.8 s, online Gaia DR3 via VizieR) + `register -2pass -disto=file <wcs>` | 32 s (38, 32, 28) | +0.5 s | 2.73 | 2.59 / 4.76 | **0.99** |
| v2 per-sub background (nearest Siril analogue to LN) | `seqsubsky pp_light_ 1` + register / apply / stack | 40 s (134, 40) | +1.0 s | 2.74 | 2.61 / 4.75 | 1.01 |
| v3 drizzle 1× | `seqapplyreg … -drizzle -scale=1 -pixfrac=1` | 36 s (126, 36, 32) | +0.8 s | 2.80 | 2.66 / 4.76 | 1.00 |
| v4 noise weighting | `stack … -weight=noise` | 27 s | ≈0 | 2.82 | 2.71 / 5.00 | **0.73** |

- **None of the WBPP-style extras improves this data.** Distortion is negligible on the Askar 71F, so the soft corner is optical, not registration.
- **Noise weighting is actively worse.** It gives high weight to low-noise but blurred subs (wFWHM 9.7 and 14.6): FWHM +3%, SNR −27%, and strongly correlated pixels.
- **Noise alone misled twice.** v1 showed 3.08 vs 4.36 ADU noise because its stack came out on a 0.75× intensity scale (additive+scale normalisation follows the reference). Its SNR is unchanged.
- **Siril has no local normalisation.** `-overlap_norm` exists only for mosaics with `-maximize`.
- **Why Siril is faster, like-for-like per sub at 26 MP:**

| Step | Cost |
|---|---|
| batch calibrate | about 0.6 s |
| register, star detection and matching | about 0.4–0.6 s |
| apply registration | about 0.6–0.8 s |
| stack | about 0.5–0.9 s |

  That's about **2–3 s per sub end to end** with 12 threads and no PSF modelling, LN or drizzle files. The extras each add 0.5–1 s per sub. WBPP's LN and PSF-signal weighting are the parts users report as CPU-heavy, but I couldn't measure WBPP itself.
- **Timing variance:** identical runs ranged from 24 s to 147 s. The 2-minute outliers were I/O stalls (one normalisation step took 2 min 00 s against 7–12 s normally) on ExFAT through Docker Desktop file sharing, with Spotlight indexing enabled on T7. Single-run timings on this storage are unreliable.

## Step 6 · Visual report: PASS

`phase2/report.html` (84 KB, 171 images under `phase2/img/`, all links verified) contains:
- the step 1 tables and reconciliation list
- QA contact sheets with flagged frames outlined in red, the truncated-frame evidence, the injection control and the strongest real dark detection
- every master with its histogram, falloff profiles, dust maps, all-vs-clean difference images and new/old ratio images
- per dataset: best, median and worst subs as raw, calibrated and registered (full frame plus 100% centre and top-left crops), and both stacks with crops

It uses **one STF stretch per dataset**, computed once from the all-subs stack (black point = median − 2.8×MADN, midtone mapping the median to 0.25) and applied unchanged in ADU to every stage. That's why the raw frame looks brighter: it still has its 80 ADU pedestal. It ends with the metric, verdict, timing, RAM and disk tables. I couldn't render a screenshot (no Chrome installed); the page is plain HTML and CSS.

---

## Surprises and risks

1. **Orientation.** Siril writes FITS bottom-up while XISF is top-down, and there's no `ROWORDER` keyword. Raw-vs-master comparisons are wrong unless flipped (correlation −0.36 as read vs 0.9997 flipped). Siril's star-list Y is measured from the *top*. My first flat-ratio analysis was wrong because of this; it has been fixed.
2. **`select`/`unselect` take the 1-based position in the sequence, not the file number.** `r_` sequences keep the original file numbers but skip subs that failed registration. My first Heart P2 run unselected subs 10–12 (the best) instead of 7–9. This was caught and re-run, but it's an easy silent error.
3. **`calibrate` and `calibrate_single` only read FITS.** Masters and lights must be converted from XISF first (phase 1 found this for masters; it applies to lights too).
4. **Siril won't `cd` into a read-only directory** ("You don't have permission to write…"), and `convert` only reads the current directory. Inputs must be staged (symlinks inside the container work; ExFAT can't hold symlinks).
5. **`-out="…"` keeps the quote characters** and created a directory literally named `"`.
6. **Docker Desktop leaks disk space on the bind mount.** Its VM process (`com.apple.Virtualization.VirtualMachine`) keeps deleted bind-mount files open: 1,629 handles, about 71 GiB. Space isn't returned until Docker Desktop restarts (T7 now shows about 50 GB more used than its files). I didn't restart Docker because your other containers run in it.
7. **`OBJCTROT` is the planned framing angle, not the camera angle.** It says 134.45° or 181.21°, while plate solving gives +1.8° to +2.1° on every dataset on both nights (+180.5° for a reference frame across the meridian flip). The camera was never rotated, so the 09-28 flats are geometrically valid for the 10-07 lights.
8. **Siril defaults to `core.mem_ratio = 0.9`** (stacking planned for 8 GB of the 12 GB VM, and 150-frame masters peaked at 7.6 GB RSS) and **`core.check_updates = true`**.
9. **Default `findstar` is blind to faint compact sources in darks.** Leak detection needs its own detector or tuned `setfindstar`.
10. **Registration can fail on clouded subs** ("Cannot perform star matching … Image 24 skipped"). Siril then excludes them automatically and the sequence gets gaps (see item 2).
11. **WBPP's master flats use linear-fit clipping; ours use winsorized.** The master-flat differences are dominated by illumination change, but the method isn't identical.

## Decisions this forces for the product spec

1. **XISF ingest = convert to FITS once** (`load` + `save`), for masters and lights alike. Keep the FITS as the calibration input, and record the orientation convention explicitly. Any code outside Siril that reads pixels must flip Siril FITS.
2. **Sequence handling must map file number to position from the `.seq` `I` lines** before any `select`/`unselect`. Never assume they match.
3. **On-arrival calibration is viable** (2–5 s per sub). Name staged subs as a sequence (`light_NNNNN`) so they assemble without a second calibration pass. Batch calibration remains the fast path for backfills.
4. **Calibration-frame QA belongs in the product,** using a set-median residual, a matched-filter PSF detector and a truncated-readout check. Siril defaults aren't enough. Keep the injection self-test as a regression test.
5. **Dark-flat vs dark is inferred,** from `OBJECT=FlatWizard` or an exposure matching flats, and should appear in the UI as an inference the user can correct.
6. **Flat matching stays the user's call** (as you specified), but the product can **show** what would change: the new/old ratio image and falloff numbers. It must **not** use `OBJCTROT` as evidence of rotation; plate solving is the reliable signal (about 5 s, online Gaia).
7. **Sub grading:** keep median-relative thresholds and add "registration failed" as a verdict. Show FOCPOS and FOCTEMP next to the wFWHM trend; focus drift explains most grader-only rejects. NINA's thumbs-down is a separate, human verdict, and the two should never be merged.
8. **The stack comparison** in the UI should report SNR (star flux / noise), centre and corner FWHM, and roundness, never noise alone. Include the field-PSF map, which here shows a tilt no sub selection fixes.
9. **Defaults:** wFWHM weighting (not noise). No drizzle, distortion correction or background extraction by default; offer them as options, since none helped this data.
10. **Container:** set `setmem`/`setcpu` (or `mem_ratio`) and turn off update checks.
11. **Bulk work must not go through Docker Desktop file sharing on ExFAT.** Use a POSIX volume (on a Linux host this problem doesn't exist) and budget about 200 MB per sub plus about 14 GB per 50-frame flat set during master building.

## Reproduce

```
scripts/phase2/disk_sampler.sh &                       # optional
uv run scripts/phase2/inventory2.py  $SRC phase2/out/inventory.csv phase2/out/inventory_flags.csv
uv run scripts/phase2/grouping2.py   $SRC phase2/out/inventory.csv phase2/out/
uv run scripts/phase2/calqa_stats.py $SRC phase2/out/frames.csv phase2/work/qa_stats
scripts/phase2/dk.sh --entrypoint python3 substation-siril:1.4.2 /scripts/phase2/calqa_findstar.py /phase2/out/frames.csv /src /work/qa_findstar [--tuned]
uv run scripts/phase2/calqa_leaks.py $SRC phase2/out/frames.csv phase2/work/qa_stats phase2/work/qa_leaks --inject
uv run scripts/phase2/calqa_masters.py $SRC phase2/out/inventory.csv phase2/work/qa_masters
uv run scripts/phase2/calqa_rejmaps.py $SRC phase2/out/inventory.csv phase2/work/qa_masters
uv run scripts/phase2/calqa_verdicts.py $SRC phase2/out phase2/work phase2/img
uv run scripts/phase2/build_masters.py && uv run scripts/phase2/analyze_masters.py $SRC
scripts/phase2/run_all_lights.sh      # (+ run_dataset.py for NGC 7000 P2, which was the smoke test)
uv run scripts/phase2/analyze_stacks.py L_n7000p3_ha L_heartp2_ha L_n7000p1_oiii L_n7000p2_ha
uv run scripts/phase2/run_dataset.py "LIGHTS:NGC 7000|Panel 1|OIII|…" n7000p1_oiii master_flat_OIII_2s_dfclean.fit --keep
docker run --rm -i -v /scratch/substation-spike/phase2-work:/work --entrypoint siril-cli substation-siril:1.4.2 -s - < scripts/phase2/platesolve_ref.ssf   # -> disto_ref10.wcs
uv run scripts/phase2/step5_variants.py && uv run scripts/phase2/step5_snr.py
uv run scripts/phase2/evidence.py && uv run scripts/phase2/build_report.py
```

The pipeline was run step by step (with the fixes above applied mid-run), not end to end from this list in one go.
