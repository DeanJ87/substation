# SubStation – engine & metadata spike report

Date: 2026-10-09 · Data: night of 2026-10-07, ATR2600M + Askar 71F, NINA 3.2.0.9001 lights, PixInsight 1.9.3 WBPP masters.

**Headline:** Siril 1.4.2 runs headless in a pinned Debian container on the first attempt and does everything the product needs: it reads the NINA XISF lights and WBPP masters, calibrates, gives per-frame metrics, registers, stacks with chosen subs excluded, and stays alive as a single worker process. There are three sharp edges:
- `calibrate` will not accept XISF masters, so they must be converted to FITS first.
- The masters carry no temperature, gain or offset headers.
- The only matching flats are from a different site and 53 days old. The owner confirms they are the wrong flats and has unstacked raw flats that are newer.

`async-siril` works, but it throws away Siril's output, so we should wrap `siril-cli` ourselves.

| Step | Result |
|---|---|
| 1 Inventory | **PASS** |
| 2 Grouping / duplicates / time | **PASS** |
| 3 Matching rules | **PASS**. The rules resolve every light. The chosen flat is wrong in practice (see 3). |
| 4.1 Siril in Docker | **PASS**. Debian forky package, about 1 minute, no fallback to macOS needed. |
| 4.3a Reading XISF | **PASS** for lights. **PARTIAL** for masters: Siril always loads image #0 and you can't pick another. |
| 4.3b Calibrate | **PARTIAL → PASS**. It fails on XISF masters and works after converting them to FITS. |
| 4.3c Metrics | **PASS** (single image and sequence) |
| 4.3d Grader vs BAD_ | **PARTIAL**. 4 of 5 agree. |
| 4.3e Selective stacking | **PASS**. Exclusion is proven by log, `STACKCNT` and the files written. |
| 4.3f Long-lived worker | **PASS**. Both stdin and named pipes work; ping/ready/busy were observed. |
| 4.3g Time / RAM / disk | **PASS** (measured) |
| 4.4 async-siril | **PARTIAL**. It works but returns no results. Recommendation: wrap it ourselves. |

---

## Environment

- Host: Mac (arm64, 12 cores, 24 GB), macOS 15.1 (Darwin 24.1.0). Docker Desktop 28.0.4; the VM has 12.5 GB RAM and runs aarch64.
- Container: `debian:forky-slim@sha256:3c80e257…13e3`, Debian forky/sid, arm64, 944 MB unpacked (243 MB compressed).
- **Siril 1.4.2** (`siril 1.4.2-1+b2`, `siril-common 1.4.2-1`) from `deb.debian.org forky/main`. `siril-cli --version` prints `siril 1.4.2`.
- Python tooling on the host: uv 0.12.24, astropy 8.0.1, xisf 0.9.7.
- Source data: `/scratch/substation-spike/sub-test`. It was originally `a folder in the home directory` and the owner moved it mid-spike. Steps 1–2 were re-run on the new path; all 44 light SHA-256s and mtimes are identical before and after the move. Work data lives on T7 (ExFAT) via the symlink `~/substation-spike/data`, because the system volume had only 16 GiB free.

## Install method

| Option | Outcome |
|---|---|
| **Debian forky (testing) `apt install siril=1.4.2-1*`** | **Worked on the first try.** Build took 50 s; native arm64; siril-cli included. |
| Debian trixie (stable) | Not used: it ships 1.2.6, which is too old. |
| Ubuntu PPA `ppa:lock042/siril` | Not tried (forky worked). |
| Official AppImage | Not tried: it's x86_64 only, so it would need emulation on this Mac. A reasonable fallback for x86_64 hosts. |
| Source build (meson) | Not needed. |

Sources: [Debian package listing](https://packages.debian.org/sid/siril), [sources.debian.org siril 1.4.2-1](https://sources.debian.org/src/siril/1.4.2-1/README.md), [Siril 1.2 Linux install docs](https://siril.readthedocs.io/en/1.2/installation/linux.html), [Siril 1.4.0 beta3 AppImage note](https://siril.org/download/2025-07-11-siril-1-4-0-beta3/).

`docker/Dockerfile`:

```dockerfile
# SubStation spike: Siril headless on Debian testing (forky). trixie ships only 1.2.6.
FROM debian:forky-slim@sha256:3c80e257eff6274d593eb33a94bda5174ccd619836e6a728a73e11c97f2213e3
ARG SIRIL_VERSION=1.4.2-1
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends siril=${SIRIL_VERSION}* siril-common=${SIRIL_VERSION}* time procps \
 && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 siril
USER siril
WORKDIR /work
ENTRYPOINT ["siril-cli"]
```

Caveat: the base image is pinned by digest, but `apt-get` still pulls from the *live* forky archive. Forky is a moving target, and 1.4.2-1 will eventually leave it. For real reproducibility, point apt at `snapshot.debian.org` for a fixed date, or keep the built image in our own registry.

---

## STEP 1 – Inventory: PASS

`uv run scripts/inventory.py $SRC out/inventory.csv out/inventory_flags.csv` reads only the XISF XML header block (`open(...,'rb')`, the signature, then the header length and the XML). It reads all 80 image files in 0.24 s. FITS files would go through astropy, but there are none. Outputs: `out/inventory.csv` (every requested column) and `out/inventory_flags.csv`.

| Type | Files | Format | Images per file | Compression | Size |
|---|---|---|---|---|---|
| LIGHT | 44 | XISF, UInt16, 6224×4168×1, single image with no id, SHA-256 checksum attribute | 1 | **none** | 51.9 MB |
| MASTERFLAT | 20 | XISF, Float32, 6224×4168 | **3**: `integration`, `rejection_low`, `rejection_high` | none | 311 MB |
| MASTERDARK | 15 | same as flats | 3 | none | 311 MB |
| MASTERBIAS | 1 (only -10c) | same as flats | 3 | none | 311 MB |

You were right that the masters hold the integration plus two rejection maps, which explains 3 × 103.8 MB.

**Header vs folder/filename disagreements and missing headers**
- Lights: **no disagreements and no missing headers** across all 44. FILTER, EXPTIME and CCD-TEMP all match the filename tokens. Filename time = DATE-OBS + 1 h = DATE-LOC on every file.
- **Every master lacks GAIN, OFFSET and CCD-TEMP.** The darks and the bias also lack SET-TEMP. So a dark's temperature exists only in its folder/filename (`-20c`), and its gain/offset can't be checked against the lights (G120/O80).
- Masters use `LONG-OBS`/`LAT-OBS` (and `OBSGEO-*`), not `SITELONG`/`SITELAT`.
- `IMAGETYP` on masters is `'Master Dark'`, `'Master Flat'`, `'Master Bias'` (with a space); on lights it is `'LIGHT'`.
- FILTER case is inconsistent: `HAlpha` (the 2026-02-25 and 2026-03-01 flats) vs `Halpha` (later flats and folder names). Matching must be case-insensitive or use an alias table.
- Folder date vs DATE-OBS: the three 2026-04-13 RGB flats have DATE-OBS 2026-04-14 ~11:30 UTC. Flats shot after midnight (e.g. the `2026-03-01` folder) belong to *night* 2026-02-28.
- Two naming schemes: `MasterFlat_ATR2600M_{F}_{YYYYMMDD}` (Feb/Mar) and the WBPP default `masterFlat_BIN-1_6224x4168_FILTER-{F}_mono` (Apr, Aug). The 2026-08-15 flats are **not** in per-filter subfolders. Dark exposures appear as `600s` or `600.00s`. These are more reasons the product can't rely on paths.
- **The 2026-08-15 flats were taken at lat 28.77°, long −17.99°** (La Palma, by the look of it). The lights and every other master are from 54.99°, −1.66°.
- Non-image files: `.DS_Store`. After the move to ExFAT there are also 25 AppleDouble `._*` sidecars, several named `._*.xisf`. The inventory now skips `._*`.

## STEP 2 – Grouping, duplicates, time: PASS

`uv run scripts/grouping.py $SRC out/inventory.csv out/` writes `lights.csv`, `datasets.csv`, `duplicates.csv`, `pointing_clusters.csv` and `seq_runs.csv`.

### Datasets (headers only; key = target | panel | filter | INSTRUME | TELESCOP | binning | gain/offset)

| Dataset | Unique subs | BAD_-marked | Time (UTC) |
|---|---|---|---|
| NGC 7000, Panel 1, OIII | **15** | 5 | 19:27–23:34 |
| Heart Nebula, Panel 1, OIII | 11 | 1 | 23:56–01:57 |
| Heart Nebula, Panel 1, SII | 10 | 0 | 02:07–04:29 |
| Heart Nebula, Panel 2, OIII | 2 | 0 | 04:42–04:52 |

That is 44 files: 38 unique subs plus 6 byte-identical BAD_ copies.

**How NINA identifies panels:** in `OBJECT`, as `"<target> Panel <n>"` (e.g. `NGC 7000 Panel 1`, `Heart Nebula Panel 2`). There is no separate panel keyword. Each panel has its own planned centre in `OBJCTRA`/`OBJCTDEC`, and `OBJCTROT` = 134.45°. Splitting on `/\s+Panel\s+(\d+)$/` gives target and panel.

**Compared with your description:**
- Correct: there are NGC 7000 and Heart mosaics, in OIII and SII.
- Different: NGC 7000 has only Panel 1 tonight, and only in OIII. All the SII is Heart Panel 1. Heart Panel 2 has just 2 OIII subs at dawn.

**Pointing-only cross-check** (single-linkage on telescope RA/DEC): thresholds of 0.25°–1.0° give exactly the same 3 clusters as OBJECT; 2.0° merges the two Heart panels. The margin is thin, though:
- The telescope's RA/DEC **drifts up to 0.40° from the planned centre** within a panel (an internal span of 0.50° for NGC 7000 P1, 0.39° for Heart P1). That is about 18% of the 2.7° × 1.8° field.
- The Heart panel centres are only 1.10° apart.

So pointing works as a cross-check but is fragile as the primary key. Use OBJECT and fall back to clustering only when OBJECT is missing.

**Sequence numbers** (from the filename only, not in any header):

| Start (UTC) | Run | Seq |
|---|---|---|
| 19:27 | NGC 7000 P1 OIII | 0000–0014 |
| 23:56 | Heart P1 OIII | **0011**–0021 (restarts, but not at 0) |
| 02:07 | Heart P1 SII | 0000–0009 |
| 04:42 | Heart P2 OIII | 0000–0001 |

The resets do coincide with target or panel changes, but they also happen on a **filter** change within the same panel (Heart P1 OIII → SII). And the NGC→Heart change "reset" to 0011, presumably because NINA carried a counter over from an earlier session. Numbers 0000–0014 are reused across three different datasets in one night. **Sequence numbers are neither unique nor a reliable panel marker.** Never key on them.

### BAD_ files

- **All 6 are byte-identical to their unprefixed twins** (SHA-256 match). FITS keywords and XISF metadata are identical too, as are mtime and birth time, and there are no extended attributes.
- So nothing in the file says what created them. The pattern (time-preserving copies plus a rename) looks like a manual or tool-driven cull mark, not a NINA output.
- They are a **human quality verdict**: 5 in NGC 7000 P1 (seq 0000, 0004, 0006, 0007, 0014) and 1 in Heart P1 OIII (seq 0018). Step 4d confirms that 4 of the 5 have clearly bad metrics.
- **Recommendation:** identify subs by content hash (SHA-256 of the file, or the XISF `checksum` attribute of the image block, which NINA already writes). A `BAD_` file whose hash matches another file is a *verdict on that sub*, not a new sub. Record it as a `user_rejected` flag on the canonical sub and never count it twice. A `BAD_` file with no twin would be a sub that is simply marked rejected.

### Clocks and the observing night

| Clock | Relation | Meaning |
|---|---|---|
| `DATE-OBS` | UTC, exposure **start** | The authoritative time |
| `DATE-LOC` | DATE-OBS + 1 h exactly | Local civil time (BST) |
| Filename `{YYYY-MM-DD_HH-MM-SS}` | DATE-OBS + 1 h exactly, matches DATE-LOC | **Local start** time |
| File mtime | filename + 604–606 s | Local exposure **end**, i.e. save time |
| `XISF:CreationTime` | DATE-OBS + 603.8–605.8 s | UTC exposure end (written with a `Z`) |
| `DATE-AVG` | DATE-OBS + ~300 s | UTC midpoint |

Observing night = date of (DATE-OBS UTC + SITELONG/15 h − 12 h), with SITELONG = −1.6626°, a −6.65 min offset. That gives **2026-10-07 for all 44 lights.** The latest light (04:52 UTC, 04:46 local mean time) also lands on the 7th. For contrast, the calendar date in the filename would split the night 15 / 29 across the 7th and 8th. The per-light value is in `out/lights.csv`, column `observing_night`.

## STEP 3 – Matching: PASS (rules); flat choice is a real-world FAIL

`uv run scripts/matching.py out/inventory.csv out/lights.csv out/` writes `out/matching.csv`.

Rules:
- **Flat:** case-insensitive FILTER match, same INSTRUME and binning. Take the latest flat whose observing night is on or before the light's night. Each flat's night comes from its own DATE-OBS and its own LONG-OBS.
- **Dark:** exact EXPTIME, |ΔT| ≤ 2 °C. The dark's temperature comes from the **path token**, because no master has a temperature header.

| Dataset | Flat chosen | Dark chosen |
|---|---|---|
| NGC 7000 P1 OIII (15) | `MasterFlats/ATR2600M/2026-08-15/masterFlat_BIN-1_6224x4168_FILTER-OIII_mono.xisf` (53 d old) | `Masters/ATR2600M/Darks/-20c/MasterDark_ATR2600M_-20c_600s.xisf` |
| Heart P1 OIII (11) | same OIII flat (53 d) | same -20c 600 s dark |
| Heart P1 SII (10) | `…/2026-08-15/masterFlat_BIN-1_6224x4168_FILTER-SII_mono.xisf` (54 d) | same |
| Heart P2 OIII (2) | OIII flat (54 d) | same |

- Lights at −19.9 and −20.0 °C both match the −20c darks, so **no light lacks a dark**. The −10c darks are rejected by the ±2 °C rule. A bias isn't needed because the dark has the same exposure.
- **No filter lacks a flat on or before the night,** so the fallback never triggers. What-if with a night of 2026-01-01: "nearest later" would pick `2026-03-01/OIII/MasterFlat_ATR2600M_OIII_20260301.xisf` for OIII and `2026-03-04/SII/MasterFlat_ATR2600M_SII_20260304.xisf` for SII.
- **In practice the rule picks the wrong flat:** the "latest before" flat was shot at another site 53 days earlier. You've confirmed these don't match and that newer raw flats exist but haven't been stacked. The date rule alone can't detect this. The product needs flat validity tied to optical-train changes: rotation, site, or a user "rig changed" event. It also needs to handle *raw* flats, not only WBPP masters.

---

## STEP 4 – Siril

**Test group:** NGC 7000 Panel 1 OIII. These are the 15 unique subs (the unprefixed originals, BAD_ duplicates not copied) plus the matched dark and flat, staged with `scripts/stage_group.py` into `data/n7000p1_oiii/`. All Siril runs use `scripts/siril.sh` or `scripts/siril_timed.sh` (`docker run … substation-siril:1.4.2`, wrapped in GNU `time -v`). The scripts live in `scripts/ssf/*.ssf`.

**Command sources:**
- In-binary help: `out/siril_help.txt` (full list) and `out/siril_help_detail.txt` (`help <cmd>` for every command used).
- Docs: [Commands reference](https://siril.readthedocs.io/en/latest/Commands.html) and [Headless / pipe mode](https://siril.readthedocs.io/en/latest/Headless.html).
- I found no docs page for the `.seq` format (the page I tried returned 404). The field layout below is empirical and cross-checked against `stat` output.

| Command | Docs |
|---|---|
| `requires`, `cd`, `load`, `save`, `set32bits`, `setext`, `convert`, `calibrate`, `findstar`, `bgnoise`, `stat`, `jsonmetadata`, `register`, `select`, `unselect`, `seqapplyreg`, `stack`, `seqstat`, `exit` | [Commands.html](https://siril.readthedocs.io/en/latest/Commands.html) (each command has its own entry) |
| `ping`, the `ready` / `status:` / `progress:` protocol, `-p -r -w`, `-s -` | [Headless.html](https://siril.readthedocs.io/en/latest/Headless.html) |

### 4.3a Reading: PASS (lights) / PARTIAL (masters)

```
requires 1.4.0
cd lights
load 2026-10-07_20-27-58_OIII_-20.00_600.00s_0000.xisf   → "Reading XISF: … 1 layer(s), 6224x4168 pixels"
cd ../masters
load MasterDark_ATR2600M_-20c_600s.xisf                  → 6224x4168, mean 81.3
load masterFlat_BIN-1_6224x4168_FILTER-OIII_mono.xisf    → 6224x4168, mean 30641.4
```

- The NINA lights are uncompressed UInt16, so no codec question arises. All NINA FITS keywords come through (`dumpheader`).
- For the multi-image masters, Siril loads **image #0, the `integration` image**. Per-image stats from `scripts/xisf_images_stats.py` show image 0 has mean 81.3 / 30641.4, which equals Siril's `stat`; the rejection maps have median 0.
- `load` has **no option to pick an image by id or index.** This is only safe because WBPP writes `integration` first. The product should check that the first `<Image>` has `id="integration"`, or extract it itself.
- Dimensions match the lights (6224×4168).

### 4.3b Calibrate: PARTIAL → PASS

First attempt (**FAIL**):

```
calibrate light_ -dark=../masters/MasterDark_ATR2600M_-20c_600s.xisf …
→ "The file ../masters/MasterDark_ATR2600M_-20c_600s.xisf is not a FITS file or doesn't exists with FITS extensions."
```

Working sequence:

```
# 1. convert lights (XISF → FITS sequence "light_")
requires 1.4.0
cd lights
convert light -out=../process          → 15 converted, 0 failed; writes light_conversion.txt (source → index map)

# 2. masters → FITS  (05_masters_to_fits.ssf)
requires 1.4.0
set32bits
setext fit
cd masters
load MasterDark_ATR2600M_-20c_600s.xisf
save master_dark_600s
load masterFlat_BIN-1_6224x4168_FILTER-OIII_mono.xisf
save master_flat_oiii

# 3. calibrate  (10_calibrate.ssf)
requires 1.4.0
set32bits
setext fit
cd process
calibrate light_ -dark=../masters/master_dark_600s.fit -flat=../masters/master_flat_oiii.fit -cc=dark -prefix=pp_
→ "34812 corrected pixels (0 + 34812)", "Normalisation value auto evaluated: 0.473", "Sequence processing succeeded."
```

- **Originals untouched (PASS)** per `scripts/verify_untouched.py`: the 44 source lights re-hashed with 0 changes, the 15 staged inputs re-hashed with 0 changes, and the staged dark and flat are identical to the source. No source file has an mtime from the spike.
- Siril writes `FILENAME=<original xisf name>` into every converted and calibrated FITS, which makes tracing a result back to its source sub easy.
- The convert order is alphanumeric by filename, which equals time order here. The sequence name is `light_` (Siril appends `_`), not `light`.

### 4.3c Per-frame metrics: PASS

**(i) Single image on arrival.** One process, 0.86 s total, about 0.2 s per frame in the worker:

```
load pp_light_00001
findstar -out=pp_light_00001_stars.lst   → "Found 265 Gaussian profile stars in image, channel #0 (FWHM 2.423474)"
bgnoise                                  → "Background noise value (channel: #0): 29.172 (4.451e-04)"
stat main                                → "Mean: 354.6, Median: 353.6, Sigma: 73.8, …, bgnoise: 29.2, avgDev…, MAD…, sqrt(BWMV)…"
jsonmetadata pp_light_00001.fit -stats_from_loaded -out=pp_light_00001.json   → headers + stats as JSON
```

- What you get: star count and mean FWHM (findstar log), noise (bgnoise), background = median (stat). The `-out=` star list gives per-star FWHMx/FWHMy, so roundness is derivable.
- **What you don't get: wFWHM.** It's only computed at registration. findstar also works directly on the raw XISF (267 stars, FWHM 2.48), so metrics can run before calibration if needed.

**(ii) Sequence at registration** (`30_register.ssf`): `register pp_light_ -2pass` computes transforms without writing images. 15/15 registered; the reference is image 10. The metrics land in `pp_light_.seq` with this format (Siril 1.4.2, seq version 6):

```
S 'pp_light_' start nb_images nb_selected fixed_len ref_image(0-based) version variable_size fz_flag drizzle
I <filenum 1-based> <included 0|1>
R0 fwhm wfwhm roundness quality background nb_stars H h00 h01 h02 h10 h11 h12 h20 h21 h22
M0-<index0> total ngoodpix mean median sigma avgDev mad sqrtbwmv location scale min max normValue bgnoise
```

- Values are normalised to 0–1 (×65535 gives ADU). The M fields were verified against `stat` for frame 1, e.g. median 0.0053953 × 65535 = 353.6.
- `scripts/metrics.py` parses the `.seq`, joins `light_conversion.txt` and the manifest, and writes **`out/metrics.csv`**. Columns: index, source file, wFWHM, FWHM, roundness, stars, background, noise, rotation and shift vs the reference, grader verdict.
- Parsing the `.seq` is more reliable than scraping logs. `seqstat <seq> out.csv main` gives the M-line stats as CSV too.

### 4.3d Grader vs BAD_: PARTIAL (4/5)

The grader is relative to the dataset median: reject if wFWHM > 1.5× median, stars < 0.6× median, background > 2× median, or roundness < 0.85.

| # | Seq | BAD_ | wFWHM | Stars | Round | Bkg (ADU) | Grader |
|---|---|---|---|---|---|---|---|
| 1 | 0000 | Y | 6.22 | 265 | 0.87 | 400 | REJECT (all three: wFWHM, stars, bkg). Twilight frame, also rotated 178°, i.e. the other pier side. |
| 5 | 0004 | Y | 9.67 | 661 | 0.65 | 148 | REJECT |
| 7 | 0006 | Y | 7.88 | 653 | 0.79 | 125 | REJECT |
| 8 | 0007 | Y | 14.51 | 493 | 0.79 | 139 | REJECT |
| 15 | 0014 | Y | 4.46 | 894 | 0.96 | 113 | **ACCEPT (missed)** |
| 4 | 0003 | – | 4.54 | 934 | 0.96 | 136 | ACCEPT |
| others | – | – | 2.73–4.24 | 1068–1239 | 0.93–0.96 | 95–114 | ACCEPT |

- 4 of the 5 BAD_ marks agree with the grader, with no false rejects.
- #15 can't be told apart from the accepted #4 on these metrics. Your call on #15 probably rests on something else: a satellite trail, a gradient, a cloud patch, or just the trend at the end of the run. A z-score on wFWHM is worse than median ratios, because the outliers inflate σ (only 2–3 of the 5 are caught).

### 4.3e Selective stacking with exclusion: PASS

`40_select_applyreg_stack.ssf`:

```
requires 1.4.0
set32bits
setext fit
cd process
select pp_light_ 1 15
unselect pp_light_ 1 1
unselect pp_light_ 5 5
unselect pp_light_ 7 8
unselect pp_light_ 15 15
seqapplyreg pp_light_ -filter-included -framing=current
stack r_pp_light_ rej w 3 3 -norm=addscale -weight=wfwhm -out=../stack_n7000p1_oiii_excl_bad -32b
```

The excluded subs are exactly the 5 BAD_-marked ones (1, 5, 7, 8, 15 = seq 0000/0004/0006/0007/0014). Evidence they were left out:
- Log: `Selection update finished, 10 images are selected`, then `Using selected images filter (10/15 of the sequence)` and `Rejection stacking complete. 10 images have been stacked`.
- The integration summary shows winsorized sigma clipping, low/high 3.0, additive + scaling normalisation, weighting from weighted FWHM.
- Stack FITS header: `STACKCNT=10`, `LIVETIME=6000` (10 × 600 s). The HISTORY line records the method.
- Only `r_pp_light_000{02,03,04,06,09..14}.fit` were written. The registered files keep their original indices, which preserves traceability.

**`unselect` indices are the 1-based file numbers in the `.seq`.** I tested this directly: `unselect pp_light_ 1 1` cleared `I 1`. The docs example `select . 0 0` suggests otherwise.

**Control:** the same stack with all 15 subs has *lower* noise (4.35 vs 5.29 ADU) and more stars detected (3514 vs 3201), with FWHM 2.94 vs 2.91. With wFWHM weighting, the BAD_ subs still added signal. Exclusion works, but "exclude" vs "keep but down-weight" should be a user choice, not assumed.

### 4.3f Long-lived worker: PASS

`scripts/siril_worker.py` runs inside the container. ExFAT can't hold FIFOs, so the pipes go in the container's `/tmp`.

- **Named pipes** (`siril-cli -p -r /tmp/siril_pipes/siril_command.in -w /tmp/siril_pipes/siril_command.out -d /work/n7000p1_oiii`), from `out/worker_pipe.json` and `worker_busy.json`:
  - Siril prints `ready` 0.09 s after launch.
  - `ping` → `status: success ping`.
  - Each command gives `status: starting <cmd>`, then `log:` lines, then `status: success <cmd>` or `status: error <cmd>`.
  - Sixteen commands ran in one PID: load 0.07–0.13 s, findstar 0.16–0.20 s.
  - Error paths (`notacommand`, `load does_not_exist.fit`) return `status: error …` and the process stays alive; the next ping succeeds.
  - **`ping` while busy** returns `status: busy`, with no command name.
  - **Commands sent while busy are queued**, not dropped: `load` and `bgnoise` ran after `seqstat` finished, in order.
  - `exit` → exit code 0.
- **stdin** (`siril-cli -s - -d …`): commands written one at a time are executed immediately (each answered before EOF; `out/worker_stdin.json`). But there are no `status:` lines, so completion can only be detected by scraping the log. **Use pipe mode for the worker.**

### 4.3g Timings, RAM, disk: PASS

15 × 26 MP subs, 12 threads, Docker VM with 12.5 GB.

| Step | Wall time | Peak RSS |
|---|---|---|
| convert 15 XISF → FITS | 5.1 s (Siril log) | not measured |
| 2 masters XISF → FITS | 2.0 s | 268 MB |
| calibrate 15 | 9.4 s | 1.51 GB |
| single-image metrics (2 frames) | 0.86 s | 295 MB |
| register -2pass 15 | 5.8 s | 2.52 GB |
| select + seqapplyreg (10) + stack | 12.5 s | 3.44 GB |
| control: applyreg + stack of 15 | 20.8 s | 3.31 GB |

Siril sized its own stacking memory to "8155 MB max" of the VM's RAM. In a shared container, set `setmem`/`setcpu` explicitly.

**Working directory: 7.4 GB in total** (lights 745 MB, masters 793 MB, process 4.6 GB, stacks about 100 MB each). For the pipeline alone that is about **260 MB per sub**:
- converted 16-bit copy: 50 MB
- calibrated float32: 100 MB
- registered float32: 100 MB

That's 5× the raw size. The levers are `setcompress`, `-fitseq`, deleting intermediates as you go, and not converting lights at all where possible.

### 4.4 async-siril: PARTIAL → recommend our own wrapper

- **Package facts:** [async-siril](https://github.com/KyleLeNeau/async-siril) 0.4.0, BSD-3-Clause.
  - Last release 2025-12-03 (10 months ago). Four releases since July 2025, 2 open issues.
  - The README names Siril 1.4.0. Python ≥ 3.12, and it ran on 3.14 in the container.
  - Dependencies: `psutil`, `structlog`, and **`asyncio` from PyPI** (version 4.0.0 resolved). That's a third-party package with the stdlib's name, which is a supply-chain smell.
- **Transport:** the same `--pipe --inpipe --outpipe` protocol validated above. It waits for `ready`, then sends `requires 0.99.10` and `capabilities`.
- **What worked** (`scripts/try_async_siril.py`, `out/async_siril_test.txt`): starting a long-lived process (0.18 s), load, findstar, bgnoise, `register(two_pass=True)`, select/unselect, seqapplyreg `-filter-included`, and a stack whose output has `STACKCNT=10`, `LIVETIME=6000`. So it covers c (partly), e and f.
- **What didn't:**
  - Every `command()` returns `None`, and the `log:` lines aren't exposed. So findstar and bgnoise **values can't be read back** (c-i fails), and you'd still parse the `.seq` yourself.
  - Errors carry only the command name (`error: \`load\``), not Siril's reason.
  - The typed `stack()` defaults to `-nonorm`, while Siril defaults to additive+scale. A silent behaviour difference.
- **Recommendation:** write our own small worker (~200 lines, as in `scripts/siril_worker.py`). It should be pipe mode with one command in flight at a time, capture the `log:` lines per command, give typed results for the metric commands, and parse the `.seq`. We could borrow async-siril's generated command builders (BSD-3) if useful.

---

## Surprises and risks

1. **`calibrate` rejects XISF masters** even though `load` reads them. Every XISF master needs a conversion to FITS first. `load` can't choose an image within a multi-image XISF; it relies on `integration` being first.
2. **Masters have no temperature, gain or offset headers.** Dark temperature comes only from the folder name, and gain/offset compatibility can't be verified.
3. **Flat age and validity:** the date rule picked a 53-day-old flat from another site. You've confirmed they're wrong; raw flats exist but haven't been stacked. Calibrated output from this spike is mechanically correct but optically wrong.
4. **In `-s` mode a script without `requires` first runs nothing** and still prints "Script execution finished successfully" with exit code 0. The worker must check `status:` lines, not exit codes.
5. **AppleDouble `._*.xisf` sidecars** appear on ExFAT, SMB or NAS shares. Inside Docker Desktop they were unreadable and Siril skipped them silently. On a Linux NAS mount they would be readable 4 KB junk files with a `.xisf` suffix. The watcher must ignore `._*` and `.DS_Store`.
6. **Siril tries to `pip install` its Python module from pypi.org on every fresh container start.** It isn't blocking (offline runs still succeed in about 1 s). With `-o`, Siril still logs "Installing / updating python module in the background", but no pip errors appear and the run took 0.57 s instead of 1.24 s. Either bake the venv into the image or run with `-o`, and persist `$HOME/.local/share/siril` if needed.
7. **Disk:** about 5× the raw size per sub in intermediates. The T7 being ExFAT also rules out FIFOs and symlinks there; Siril symlinks FITS inputs when it can.
8. **Pointing drift** of up to 0.4° within a panel against 1.1° panel spacing makes pure pointing clustering fragile.
9. **Sequence numbers** repeat across datasets and don't reset to 0 on a target change.
10. The **stack's DATE-OBS** is the reference frame's (22:43), not the earliest sub's (19:27). Session time ranges must come from our own sub records.
11. **Meridian flip:** frame 1 is rotated 178° relative to the reference. Registration handled it, but flats taken on one pier side need to stay valid across a flip, which they do for a fixed rotator.
12. **Debian forky moves.** The container is reproducible only with snapshot apt sources or a stored image. `scripts/run_all.sh` was assembled from the individually-run, logged steps above and **has not been run end to end as a single script.**

## Decisions this forces for the product spec

1. **Identity = content hash.** Subs are keyed by SHA-256 (or NINA's per-image checksum). A `BAD_` copy becomes a `user_rejected` flag on the canonical sub. Filenames and sequence numbers are display-only.
2. **Dataset key** = OBJECT split into target and panel, plus FILTER (normalised case and aliases), INSTRUME, TELESCOP, binning, gain and offset. Pointing clustering is only a fallback or a sanity warning.
3. **Observing night** is computed from DATE-OBS UTC and SITELONG, never from the host timezone or the folder date. The same rule applies to masters, using their `LONG-OBS`.
4. **Master library metadata comes from the user, not the headers.** The product needs a registry with temperature, gain, offset, valid-from/to and rig/site. It should prefill from path tokens and require confirmation where headers are missing. Flats need validity tied to optical-train changes, not just "latest before".
5. **Build master flats (and darks) ourselves** from raw frames with Siril, or at least support it, rather than only consuming WBPP masters.
6. **The ingest step extracts XISF to FITS:** lights via `convert`, and masters via `load`/`save` after checking the first image is `integration`.
7. **Engine = one long-lived `siril-cli -p` worker per job slot,** with one command in flight, completion via `status:` lines, results parsed from `log:` lines and the `.seq` file. We wrap it ourselves rather than adopting async-siril.
8. **Verdicts are applied with `select`/`unselect`** (1-based file numbers) plus `-filter-included`. Whether to exclude bad subs or keep them down-weighted by wFWHM should be a per-dataset user choice; the control stack showed exclusion isn't automatically better.
9. **The grader** starts with median-relative thresholds on wFWHM, star count, background and roundness. It must accept human overrides, since #15 shows metrics don't capture every reason for a reject.
10. **Storage budget** is about 5× raw per sub. Plan for intermediate clean-up or compression, and put the work volume on a POSIX filesystem (not ExFAT).
11. **Container image** is Debian with Siril pinned via snapshot apt or our own registry. Run `-o`, set `setmem`/`setcpu`, and pre-bake the Siril Python venv.

## Files

- `scripts/`:
  - `hdr.py`, `inventory.py` (step 1); `grouping.py` (step 2); `matching.py` (step 3)
  - `stage_group.py`, `siril.sh`, `siril_timed.sh`, `ssf/*.ssf`, `xisf_images_stats.py`, `metrics.py`, `siril_worker.py`, `siril_worker_busy.py`, `try_async_siril.py`, `verify_untouched.py`
  - `run_all.sh` (end-to-end; untested as a whole)
- `docker/Dockerfile`, `docker/build1.log`
- `out/`:
  - CSVs: `inventory.csv`, `inventory_flags.csv`, `lights.csv`, `datasets.csv`, `duplicates.csv`, `pointing_clusters.csv`, `seq_runs.csv`, `matching.csv`, `metrics.csv`
  - Summaries: `*_summary.txt`
  - Siril step logs: `step_*.log`
  - Worker results: `worker_*.json`
  - Siril help dumps: `siril_help*.txt`
  - Integrity check: `verify_untouched.txt`
- Work data: `data/n7000p1_oiii/` on T7, with the calibrated and registered sequences and the stacks `stack_n7000p1_oiii_excl_bad.fit`, `stack_n7000p1_oiii_all15.fit` and `stack_async_siril.fit`.
