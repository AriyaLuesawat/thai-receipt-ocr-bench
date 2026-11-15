# Experiment log

Every run is recorded here, including the ones that failed: what was tried, what happened, why it passed or failed, and what changed next. Newest entries are at the bottom.

Scores are exact-match field accuracy on the Big C sample (50 receipts per noise level), and from EXP-011 on the Makro sample too. "Readable" means clean–noise4, the levels a person can still read. noise5–6 are a stress test (see EXP-002).

| ID | Date | What | Result |
| --- | --- | --- | --- |
| EXP-001 | 2026-11-14 | Download sample one row per request | Failed: rate-limited (HTTP 429). Fixed by fetching one window per level. |
| EXP-002 | 2026-11-14 | EasyOCR + rule extractor v1, 350 receipts | Baseline. Readable total 75%. Clean 100%. noise4–6 0%. |
| EXP-003 | 2026-11-14 | Median filter before OCR on noise4 | Failed: 0/10. Wrong diagnosis (noise4 is blur, not speckle). |
| EXP-004 | 2026-11-14 | Upscale and sharpen before OCR on noise4 | Failed: 0/10 at every setting. Sharpening also hurt noise1. |
| EXP-005 | 2026-11-14 | Rule extractor v2 (fuzzy labels, Thai digits) | Passed: noise1 time 72% → 96%, receipt no. 82% → 96%, change 46% → 68%. No loss on clean. |
| EXP-006 | 2026-11-14 | Quality gate: detect failed OCR from its own confidence | Passed (in-sample): mean confidence < 0.3 rejects 100% of failed images and 0% of good ones. |
| EXP-007 | 2026-11-14 | Replace EasyOCR with Tesseract 5 (Thai + English) | Passed: readable total 77% → 93%, noise4 total 0% → 84%, 3.5× faster. New weakness: reads `3` as `2` on some clean receipts. |
| EXP-008 | 2026-11-14 | Rule extractor v3 (label colon optional) | Small pass: noise4 receipt no. 16% → 34% on Tesseract, no loss anywhere. |
| EXP-009 | 2026-11-14 | Quality gate for Tesseract, checked on held-out images | Image-level gate passes on held-out but with a margin of only 0.03. Per-field gate passes: 99.1% of accepted values correct on held-out images. |
| EXP-010 | 2026-11-14 | Arithmetic cross-checks (cash − total = change, items sum = total) | Passed: on Tesseract, wrong amounts accepted 9 → 1 (of about 650). Every confirmed or repaired value is correct, on both engines. |
| EXP-011 | 2026-11-15 | Big C rules on Makro tax invoices, unchanged | Failed as expected: total, change and date 0%. The Big C rules read the pre-VAT `TOTAL` row and miss Thai labels. |
| EXP-012 | 2026-11-15 | Extractor v4 (layout detection + Makro rules) and VAT/receipt-number checks | Partial pass: readable total 0% → 54%, clean 100%. Checks hold up on the new layout (3 wrong of 397 accepted), but 2 confirmed values were wrong: a correlated misread passes C1. |
| EXP-013 | 2026-11-15 | CLAHE contrast preprocessing before Tesseract | Mixed: Makro faded total 0% → 84%, blur 0% → 44%, but crumpled change 84% → 0%. Helps some images, hurts others. |
| EXP-014 | 2026-11-15 | Read every image twice (raw + CLAHE), let the checks choose. Plus a bug fix in the checks | Passed: Big C 1 wrong value accepted in 1,500 readable fields. Makro total 54% → 66%. Bug: cash was marked confirmed without any check (14 wrong values under CLAHE), now fixed. |
| EXP-015 | 2026-11-15 | Vote on receipt no., date, time: possible-value rules + the two printed receipt-number copies | Passed: Makro readable receipt no. 38% → 50%, Big C readable wrong values 1 → 0, all-level wrong 14 → 11. First try (majority of 4 reads) failed: 6 → 9 wrong on Makro. |
| EXP-016 | 2026-11-15 | Per-image pipeline + FastAPI service and demo page | Passed: the pipeline reproduces the benchmark decisions on all 700 images (tested). Latency median 1.1 s (Big C), 3.8 s (Makro) per image on CPU. Docker image written but not built yet. |

---

## EXP-001: Download the sample

- **Goal:** 50 random receipts per noise level from `nectec/thairocr` (`bigc` split) without downloading 14.6 GB.
- **Tried:** one `/rows` API request per randomly chosen row (350 requests).
- **Result:** failed after 32 rows with `HTTP 429 Too Many Requests`, even with exponential backoff.
- **Why:** the Hugging Face datasets server rate-limits many small requests.
- **Change:** request one contiguous window of 50 rows at a seeded random offset inside each 1,000-row block (7 requests in total), wait 0.2 s between image downloads, and back off for up to 60 s on 429. The rows inside a block are not in any obvious order, so a window is still a fair sample.
- **Outcome:** 350/350 images downloaded.

## EXP-002: EasyOCR baseline

- **Setup:** EasyOCR 1.7.2, Thai + English, CPU (Apple M5). Rule extractor v1 finds the label ("Total", "Cash", "Receipt No", ...) and reads the value after it, fixing `o` → `0` and similar look-alikes. A second extractor copies SaiJai's slip rule: the largest number with two decimals is the amount.

| Level | s/img | total (largest) | total | cash | change | receipt no. | date | time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| clean | 5.5 | 10% | 100% | 100% | 100% | 100% | 100% | 100% |
| noise1 | 4.7 | 24% | 80% | 66% | 46% | 82% | 100% | 72% |
| noise2 | 4.9 | 18% | 96% | 90% | 66% | 72% | 98% | 86% |
| noise3 | 4.8 | 30% | 100% | 98% | 100% | 98% | 100% | 100% |
| noise4 | 8.6 | 0% | 0% | 0% | 0% | 0% | 0% | 0% |
| noise5 | 9.3 | 0% | 0% | 0% | 0% | 0% | 0% | 0% |
| noise6 | 7.9 | 0% | 0% | 0% | 0% | 0% | 0% | 0% |

**What passed**

- Clean and noise3 (yellow paper) are close to perfect, so the extractor logic is right when the OCR text is right.

**What failed, and why**

- **"Largest amount" rule (SaiJai's): 12% overall.** On a receipt the cash paid is usually larger than the total, so the largest number is the cash. The rule only works on documents with a single amount, such as transfer slips. Lesson for SaiJai: a receipt needs label-based extraction.
- **noise1 (crumpled paper) and noise2 (faded):** almost every miss is a *missing* value, not a wrong one. Looking at the OCR lines, the labels themselves are misread: `chance:` for `change:`, `tme:` / `t!me:` / `tim=:` for `time:`, `cate:` for `date:`, and `receipt n๑:`. Digits are also misread as Thai digits (`5o.๓`) or letters (`2d.0d`, `id.o`). Rule v1 needs an exact label, so it gives up. Fixed in EXP-005.
- **noise4: 0% on every field.** The OCR output is gibberish (`aดcรมาอาเรฯ`, `1^42=?49!56!`). The receipt is readable by eye, so this is an OCR failure, not an extractor bug. See EXP-003 and EXP-004.
- **noise5 (very faded ink) and noise6 (pixelated): 0%.** A person can barely read these either (see `results/samples/`, not committed). They are reported as a stress test and kept out of the main score, so they don't drag the average down for reasons no real app would face.

**Next:** fix label matching (EXP-005), and find a preprocessing step that rescues noise4.

## EXP-003: Median filter on noise4

- **Hypothesis:** noise4 is speckle ("salt and pepper") noise, which a median filter removes.
- **Tried:** grayscale + `cv2.medianBlur` with a 3 px and a 5 px kernel, on the first 10 noise4 receipts.
- **Result:** 0/10 on every field with both kernels. No improvement.
- **Why it failed:** the hypothesis was wrong. A close crop shows that noise4 is **blur** on a narrow 384 px image: the letters are small and soft, with no speckle. A median filter smooths the image further.
- **Lesson:** look at a full-resolution crop before choosing a fix.

## EXP-004: Upscale and sharpen on noise4

- **Hypothesis:** the text is too small and soft for EasyOCR's detector. Upscaling 2–3× and applying an unsharp mask should restore readable strokes.
- **Tried:** none / 2× / 3× bicubic upscale, with and without an unsharp mask, on 10 noise4 receipts and, as a control, 10 noise1 receipts (to check the step doesn't hurt images that already work).
- **Result:** no setting rescued noise4. The average share of the 6 fields correct is shown below; noise1 is the control.

| Preprocessing | noise4 | noise1 (control) |
| --- | ---: | ---: |
| none | 0% | 80% |
| 2× upscale | 0% | 80% |
| 3× upscale | 0% | 78% |
| 2× + sharpen | 0% | **65%** |
| 3× + sharpen | 0% | **67%** |

- **Why it failed:** running EasyOCR on a cropped, 3×-upscaled noise4 region still returns gibberish, with mean box confidence 0.02–0.04. The blur removes the thin strokes that separate Thai characters, and resizing cannot bring back detail that is gone. Sharpening also amplifies the crumple texture on noise1 and breaks the receipt number (8/10 → 1/10).
- **Lesson:** classic preprocessing does not fix this level for EasyOCR. Two options are left: a model trained on degraded text (to test with Typhoon OCR, a vision-language model), or detecting these images and asking the user for a better photo (EXP-006).
- **Useful side finding:** noise4 has the lowest sharpness of all levels (Laplacian variance 315, against 11,154 for clean), and EasyOCR's confidence collapses on it. That led to EXP-006.

## EXP-005: Rule extractor v2

- **Change:** instead of an exact label, v2 compares every `word:` on a line with the expected label by string similarity (≥ 0.6), so `chance:` still matches `change` and `tme:` still matches `time`. It also maps Thai digits `๐–๙` to `0–9` and adds `d` → `0`, `i`/`!` → `1` inside numbers. Same OCR output as EXP-002; only the extractor changed.

| Level | total | cash | change | receipt no. | date | time |
| --- | --- | --- | --- | --- | --- | --- |
| clean | 100% → 100% | 100% → 100% | 100% → 100% | 100% → 100% | 100% → 100% | 100% → 100% |
| noise1 | 80% → **86%** | 66% → **72%** | 46% → **68%** | 82% → **96%** | 100% → 100% | 72% → **96%** |
| noise2 | 96% → **98%** | 90% → **92%** | 66% → **82%** | 72% → **98%** | 98% → 98% | 86% → **92%** |
| noise3 | no change (98–100%) | | | | | |
| Readable (clean–noise4) | 75% → 77% | 71% → 72% | 62% → 70% | 70% → 78% | 80% → 80% | 72% → 78% |

- **Passed:** big gains on noise1–2, no loss on clean.
- **Still failing:** noise1 change is 68%. The remaining misses have the value itself badly garbled (`5o.qd` for `50.00`), and `q` is too ambiguous to map safely (it also looks like `9`). The readable average is held down by noise4, which is still 0%. That is an OCR problem, not an extraction problem.
- **Risk to watch:** fuzzy matching could pick the wrong label on other receipt layouts (for example, `cash` matching `cashier`). Needs a check when Makro and the bills are added.

## EXP-006: Quality gate

- **Question:** a real app should not silently return wrong numbers. Can it tell that OCR failed, and ask for a retake?
- **Signals (no extra model):** mean EasyOCR box confidence, and image sharpness (variance of the Laplacian). Script: `scripts/quality_gate.py`.

| Level | median confidence | median sharpness | field accuracy (v2) |
| --- | ---: | ---: | ---: |
| clean | 0.72 | 11,154 | 100% |
| noise1 | 0.63 | 2,306 | 86% |
| noise2 | 0.66 | 1,735 | 93% |
| noise3 | 0.72 | 8,090 | 99% |
| noise4 | 0.03 | 315 | 0% |
| noise5 | 0.11 | 157 | 0% |
| noise6 | 0.10 | 848 | 0% |

Rule: reject when mean confidence < t. "Good" = at least 5 of 6 fields right (149 images). "Failed" = fewer than 3 right (150 images).

| t | failed images rejected | good images rejected |
| ---: | ---: | ---: |
| 0.1 | 65% | 0% |
| 0.2 | 100% | 0% |
| **0.3** | **100%** | **0%** |
| 0.5 | 100% | 0% |
| 0.6 | 100% | 3% |

- **Passed:** any threshold from 0.2 to 0.5 separates the two groups perfectly. 0.3 sits in the middle of that range.
- **Sharpness alone is weaker:** the blocky edges of pixelated noise6 count as "sharp" (848), so a failing level sits only about 2× below a working one (noise2, 1,735), while confidence differs by about 6× (0.10 vs 0.66). Confidence is the better single signal.
- **Caveats, so this is not over-claimed:**
  - The threshold was chosen on the same 350 images it is scored on. It needs a held-out check.
  - In this synthetic data, an image either works or fails completely, which makes separation easy. Real photos will have partial failures (one smudged number on an otherwise clear receipt). A per-field confidence will be needed for those.
- **Next:** check the gate on held-out images and on real receipts, and try per-field confidence.

## EXP-007: Tesseract instead of EasyOCR

- **Question:** is the noise4 failure a limit of classic (non-VLM) OCR on blurred receipts, or specific to EasyOCR?
- **Setup:** Tesseract 5.5.4 (LSTM) with the `tessdata_best` Thai and English models, page segmentation mode 6, no preprocessing, same 350 images. Script: `scripts/run_tesseract.py`. Fields from the same extractor v2, so only the OCR engine changed.

| Level | EasyOCR total | Tesseract total | EasyOCR change | Tesseract change | EasyOCR receipt no. | Tesseract receipt no. | EasyOCR s/img | Tesseract s/img |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| clean | 100% | 100% | 100% | 100% | 100% | 100% | 5.5 | 1.6 |
| noise1 | 86% | 86% | 68% | **98%** | 96% | **100%** | 4.7 | 1.6 |
| noise2 | 98% | 96% | 82% | **92%** | 98% | 94% | 4.9 | 1.6 |
| noise3 | 100% | 100% | 100% | 100% | 98% | **100%** | 4.8 | 1.5 |
| noise4 | 0% | **84%** | 0% | **28%** | 0% | **16%** | 8.6 | 1.9 |
| noise5 (stress) | 0% | 52% | 0% | 20% | 0% | 2% | 9.3 | 2.0 |
| noise6 (stress) | 0% | 0% | 0% | 0% | 0% | 0% | 7.9 | 2.7 |
| **Readable** | 77% | **93%** | 70% | **84%** | 78% | **82%** | 5.7 | **1.6** |

Readable averages for all six fields (v2): total 93%, cash 74%, change 84%, receipt no. 82%, date 82%, time 81%.

**What passed**

- **noise4 is no longer 0%.** Tesseract reads blurred English and digits well enough: `Total: 1816.50`, `Change 0.00`, `Time: 15:11`. So the blur is not beyond classic OCR. EasyOCR's text detector is what breaks on it (EXP-002).
- **About 3.5× faster** on CPU (1.6 s against 5.7 s per image).
- **Better on change** for noise1–2 (68% → 98% and 82% → 92%).

**What failed, and why**

- **noise4, fields other than total are still low** (cash 0%, date 10%). Looking at the text:
  - The colon after the label is often lost: `Cash 243.00`, `Recept No 000141`. Extractor v2 needs `word:`, so it skips these lines. This part is an extractor problem → EXP-008.
  - Digits and separators are misread: `000149` for `000169`, `2209/2025` (slash lost), `Change: 1000` for `10.00` (decimal point lost). This part is OCR and the extractor cannot fix it safely.
  - The `Cash` line is sometimes missing from the output altogether.
- **Clean cash is 94%, not 100%.** Three clean receipts read `Cash: 702.00` for `703.00`, `362.00` for `363.00`, `892.00` for `893.00`. EasyOCR reads the same three correctly. Tesseract confuses `3` with `2` in this font even when the image is sharp, so a 100% clean score cannot be assumed for any engine.
- **noise6 (pixelated) is still 0%** for both engines.
- **No confidence signal yet.** The EXP-006 quality gate uses EasyOCR box confidence. Tesseract's word confidence needs `tsv` output, not plain text, before the gate can be ported.

**Next:** relax the label colon (EXP-008), then port the quality gate to Tesseract confidence. Check whether a Thai VLM (Typhoon OCR) fixes the remaining digit errors.

## EXP-008: Rule extractor v3

- **Change:** v2 only accepts a label written as `word:`. v3 also accepts a label word followed directly by a digit (`Cash 243.00`). v3 only runs where v2 found nothing, so it cannot change a field v2 already read.

| Engine / level | cash v2 → v3 | change v2 → v3 | receipt no. v2 → v3 | total v2 → v3 |
| --- | --- | --- | --- | --- |
| Tesseract noise4 | 0% → 6% | 28% → 34% | 16% → **34%** | 84% → 84% |
| Tesseract noise5 (stress) | 20% → 30% | 20% → **62%** | 2% → 2% | 52% → 64% |
| EasyOCR noise1 | 72% → 78% | 68% → 68% | 96% → 98% | 86% → 86% |
| Every other level, both engines | no change | | | |

- **Passed, but small:** gains only where the colon was lost, no loss on any level for either engine.
- **Still failing:** Tesseract noise4 cash is 6% because the `Cash` line is usually missing or garbled in the OCR text, not because the extractor misses it.
- **Risk to watch:** without a colon, a label word followed by a number is a looser pattern. It still requires a fuzzy label match of at least 0.6, but needs checking on the Makro and bill layouts.

## EXP-009: Quality gate for Tesseract, checked on held-out images

- **Questions:** (1) does the EXP-006 gate hold on images it was not tuned on? (2) does it work for Tesseract?
- **Change:** `scripts/run_tesseract.py` now also saves every word with Tesseract's 0–100 confidence (TSV output; the page text is unchanged, and the scores matched EXP-007/008 exactly). `scripts/quality_gate.py` splits the images into a *tune* half and a *test* half by a hash of the file name, chooses the threshold on tune, and reports on test. When several thresholds tie, it takes the middle one.
- **Fixed on the way:** the first rerun crashed because `txt`/`tsv` are config files that live in Tesseract's own tessdata folder, not in `data/tessdata/`. Passing `-c tessedit_create_txt=1 -c tessedit_create_tsv=1` avoids the config files.

**1. Image-level gate (reject the whole image when mean confidence is low)**

| Engine | threshold (chosen on tune) | failed rejected, test half | good rejected, test half | margin between groups |
| --- | ---: | ---: | ---: | ---: |
| EasyOCR | 0.35 | 100% (75/75) | 0% (0/61) | 0.38 |
| Tesseract | 0.90 | 100% (64/64) | 0% (0/66) | **0.03** |

- **EasyOCR passed on held-out images.** The EXP-006 caveat is cleared for this dataset: the lowest-confidence good image (0.55) sits far above the highest-confidence failed one (0.16).
- **Tesseract passed, but only just.** Tesseract stays confident when it is wrong: noise4 has median word confidence 0.85, against 0.93 on clean. The good and failed groups are only 0.03 apart, so a slightly different image source could break the threshold.
- **It also throws away good data.** It rejects every noise4 image, yet Tesseract reads the total right on 84% of them. An image-level gate is the wrong unit for an engine that half-works.

**2. Per-field gate (accept or reject each value on its own)**

For each extracted value, find the OCR word that contains it and take that word's confidence. Keep the value only if the confidence is above a threshold, otherwise ask the user to check that one field.

| keep field if conf ≥ | fields kept (of 1,419) | correct among kept | wrong let through | correct thrown away |
| ---: | ---: | ---: | ---: | ---: |
| 0 (no gate) | 1,419 | 95.0% | 71 | 0 |
| 0.70 | 1,306 | 98.2% | 23 | 65 |
| 0.80 | 1,241 | 99.0% | 12 | 119 |
| 0.90 | 1,087 | 99.7% | 3 | 264 |
| 0.95 | 782 | 100.0% | 0 | 566 |

Held-out check: the lowest threshold with at least 99% correct on the tune half is 0.77. On the test half (94.6% correct with no gate) it keeps 544 of 611 values, 99.1% of them correct (5 wrong let through, 39 correct thrown away).

| Level (threshold 0.77) | values extracted | correct | kept | wrong among kept |
| --- | ---: | ---: | ---: | ---: |
| clean | 300 | 297 | 299 | 3 |
| noise1 | 288 | 279 | 275 | 3 |
| noise2 | 284 | 281 | 259 | 1 |
| noise3 | 300 | 298 | 297 | 1 |
| noise4 | 118 | 98 | 79 | 2 |
| noise5 (stress) | 129 | 95 | 57 | 2 |

- **Passed:** wrong values on held-out images drop from 5.4% to 0.9% with no extra model, on images the threshold was not chosen on. noise4 is no longer all-or-nothing: 79 of its values are kept (77 right) instead of the whole image being rejected.
- **What still gets through:** the three clean `3` → `2` misreads from EXP-007 (`702.00` for `703.00`). Tesseract is confident about them, so no confidence gate can catch them. Catching these needs a cross-check, for example total = sum of items, or cash − total = change.
- **Limitation:** the value-to-word match is by digits only, so a value that also appears elsewhere on the receipt (e.g. a total equal to an item price) may take the wrong word's confidence.

**Next:** add arithmetic cross-checks (cash − total = change, sum of items = total) to catch confident misreads, then try a Thai VLM.

## EXP-010: Arithmetic cross-checks

- **Problem:** confidence cannot catch values OCR misreads *confidently*: Tesseract reads `703.00` as `702.00` with high confidence (EXP-009).
- **Idea:** a receipt contains its own redundancy, so the amounts can check each other without another model. Script: `scripts/cross_check.py`.
  - **C1:** cash − total = change
  - **C2:** sum of item prices = total (item prices are the trailing amounts of the lines between the date line and the `Total` line)
  - **Sanity:** cash ≥ total, and an amount must be payable in Thai currency (a multiple of 0.25 baht, the smallest coin)
- **Each amount gets a status:** *confirmed* (part of a check that holds), *repaired* (missing or broken, recomputed from confirmed values), *flagged* (a check fails and cannot be resolved, so the user is asked), or *unchecked* (not enough values for any check, so the EXP-009 confidence gate decides).

**Iterations inside this experiment**

1. **First version: repaired by confidence.** When C1 failed but C2 confirmed the total, the lower-confidence of cash/change was recomputed. On Tesseract this fixed all three clean `702.00` misreads, but on EasyOCR it made 4 values wrong. In `bigc_noise2_06247`, EasyOCR read change `50.00` as `0.00`, and the rule "fixed" the correct cash `157.00` to `107.00`. Confidence ties and near-ties made the choice a coin flip.
2. **Item prices with a lost decimal point.** Only 137 of 350 item lists were read completely, because Tesseract drops the point on some prices (`5200` for `52.00`). On a line that starts with a quantity, a bare trailing number of 3+ digits is now read as having two decimals. A wrong guess can only make C2 fail, never create a false confirmation. Complete item lists: 137 → 202.
3. **Final: repair only when the broken value is impossible.** When C1 fails, repair only if exactly one of cash/change is not payable (`215.03` cannot be paid, so it must be the misread). Otherwise flag both and ask the user. Also flag when cash < total. This loses the three automatic clean-cash repairs on Tesseract (they are now flagged instead), but removes every wrong repair.

**Result (final version, amount fields only: total, cash, change; 350 receipts × 3 = 1,050 fields)**

| Engine | Policy | accepted | wrong among accepted | asked the user |
| --- | --- | ---: | ---: | ---: |
| Tesseract | confidence gate only (EXP-009, 0.77) | 656 | 9 | — |
| Tesseract | **cross-checks + confidence for unchecked** | 647 | **1** | 107 |
| EasyOCR | confidence gate only (0.77) | 211 | 3 | — |
| EasyOCR | **cross-checks + confidence for unchecked** | 511 | **0** | 67 |

| Status (Tesseract) | values | correct | wrong |
| --- | ---: | ---: | ---: |
| confirmed | 570 | 570 | 0 |
| repaired | 11 | 11 | 0 |
| unchecked, confidence ≥ 0.77 (accepted) | 66 | 65 | 1 |
| unchecked, low confidence (asked) | 32 | 23 | 9 |
| flagged (asked) | 75 | 52 | 23 |

On EasyOCR, all 497 confirmed and 13 repaired values are also correct.

- **Passed:** a value that passes an arithmetic check was right every time on both engines (1,091 values). Cross-checks also help EasyOCR, whose confidence scale differs from Tesseract's: it accepts 511 values instead of 211, with no errors.
- **Accuracy gains are small, trust gains are large.** Readable accuracy on Tesseract moves only a little (cash 75% → 77%, change 85% → 86%). The real change is that the app can now say which numbers it is sure of.
- **What still fails:**
  - **noise4 gets almost no checks** (1 confirmed value of 150). Tesseract usually loses the `Cash` line and most item lines there, so neither C1 nor C2 can run. Those values fall back to the confidence gate.
  - **The one wrong value accepted:** `bigc_noise5_05263`, total read as `303.00` (true `343.00`) with cash and change both missing, so no check could run and the confidence was high.
  - **Flagged includes many correct values** (52 of 75): when a check fails, the code cannot tell which value is wrong, so it asks about all of them. That costs the user a tap, not a wrong number.
- **Caveat:** these rules were designed while looking at this same sample. They have no tuned threshold, but the payable rule was added after seeing two EasyOCR failures. They need a check on another layout (Makro tax invoices) to show they generalise.

**Next:** test on the Makro split, whose tax invoices add VAT (subtotal + VAT = total) as a third check. Then try a Thai VLM on noise4, where the checks have nothing to work with.

> **Correction (found in EXP-014):** when only the total was confirmed (by the items) and change was missing, this version marked cash as *confirmed* and derived change from it, although nothing had checked cash. On Big C every one of those cash values happened to be right, so the tables above show no errors, but the logic was wrong, and on Makro with CLAHE it let 14 wrong values through. After the fix, Tesseract on Big C accepts 636 amounts with 1 wrong (was 647 with 1 wrong); the conclusions here are unchanged.

## EXP-011: Big C rules on Makro tax invoices

- **Question:** do the extractor and checks, built only on Big C, work on a different layout? This is the generalisation test EXP-005 and EXP-010 asked for.
- **Data:** 350 Makro tax invoices from `nectec/thairocr` (`makro` split, 50 per level, same sampling). These are A4 pages (2480 × 3508 px), not narrow slips. Labels are Thai (`รวมเงิน` total, `ทอน` change, `เวลา` time), dates are `dd-mm-yyyy`, receipt numbers have 12 digits and are printed twice, and a footer `TOTAL` row holds the amount before VAT, the VAT, and the total. `scripts/evaluate.py` gained `canonical_label()` to map the nested Makro labels to the six scored fields.
- **OCR:** Tesseract, same settings. 3.8 s per page.

| Level | total | cash | change | receipt no. | date | time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| clean | 0% | 100% | 0% | 94% | 0% | 96% |
| noise1 | 0% | 90% | 0% | 12% | 0% | 2% |
| noise2 | 0% | 90% | 0% | 80% | 0% | 80% |
| **Readable (clean–noise4)** | **0%** | 56% | **0%** | 37% | **0%** | 36% |

- **Failed, for the reasons expected:**
  - **total 0%:** the fuzzy `total` label matches the footer `TOTAL` row, whose first amount is the price *before* VAT (`TOTAL 45.79 3.21 49.00` for a 49.00 bill). This is a wrong value, not a missing one, which is the dangerous kind.
  - **change 0%:** the label is the Thai word `ทอน`. v3 only matches Latin labels.
  - **date 0%:** v3 only looks for `dd/mm/yyyy`.
- **What did transfer:** `CASH` is in English on both layouts (90–100%), and the receipt number and time partly match through the English header line.
- **Lesson:** label rules do not generalise across stores by themselves, and a fuzzy label can silently pick a different quantity with the same name.

## EXP-012: Extractor v4 and Makro checks

- **Change:** `extract_rules_v4` first detects the layout from the text (at least two of `แม็คโคร`, `makro`, `LEGAL AMOUNT`, `ใบกำกับภาษี`, `CASHIER`, `พนักงานเก็บเงิน`). Makro pages get their own rules, and anything else goes to v3. The Makro rules:
  - match whole Thai tokens by similarity (`รวมเงิน` for the total, falling back to `ยอดเงินชำระ`; `ทอน`; `CASH`);
  - repair Tesseract's split sara am (`ํา` → `ำ`) before matching;
  - read `dd-mm-yyyy` dates, the 12-digit receipt number, and `เวลา` / `TIME` for the time.
- **New checks in `scripts/cross_check.py`:**
  - **C3:** amount before VAT + VAT = total on the footer row. This gives a second independent estimate of the total, next to the item sum.
  - **Receipt number printed twice:** if both 12-digit copies agree, the number is confirmed.
- **Bugs fixed along the way:**
  - Makro article numbers can have 15 digits, so only 27 of 350 item lists were found at first. Accepting 12–16 digits raised that to 124.
  - Some misread labels returned the pre-VAT amount as the total (`279.44` for `299.00`, and 279.44 × 1.07 = 299.00). The payable rule from EXP-010 now also applies to values no check could reach. It flagged all 10 such cases, and wrong values that passed the confidence gate fell from 11 to 1.
- **Big C is unchanged:** v4 gives exactly the same output as v3 on all 350 Big C receipts, for both engines.

| Level | total v3 → v4 | cash | change v3 → v4 | receipt no. v3 → v4 | date v3 → v4 | time v3 → v4 |
| --- | --- | --- | --- | --- | --- | --- |
| clean | 0% → **100%** | 100% | 0% → **100%** | 94% → 94% | 0% → **82%** | 96% → 98% |
| noise1 (crumpled) | 0% → **84%** | 90% | 0% → **84%** | 12% → 14% | 0% → **76%** | 2% → 0% |
| noise2 (paper texture) | 0% → **86%** | 90% | 0% → **66%** | 80% → 80% | 0% → **86%** | 80% → 90% |
| noise3 (faded, yellow) | 0% → 0% | 0% | 0% → 0% | 0% → 26% | 0% → 10% | 0% → 20% |
| noise4 (blur) | 0% → 0% | 0% | 0% → 0% | 0% → 0% | 0% → 0% | 0% → 8% |
| **Readable** | 0% → **54%** | 56% | 0% → **50%** | 37% → 43% | 0% → **51%** | 36% → 43% |

**Cross-checks on Makro (amount fields, 1,050)**

| Policy | accepted | wrong among accepted | asked the user |
| --- | ---: | ---: | ---: |
| confidence gate only (0.77, tuned on Big C) | 353 | 16 | — |
| **cross-checks + payable rule + confidence** | 397 | **3** | 51 |

| Status | values | correct | wrong |
| --- | ---: | ---: | ---: |
| confirmed | 375 | 373 | **2** |
| repaired | 10 | 10 | 0 |
| unchecked, accepted | 12 | 11 | 1 |
| unchecked, low confidence (asked) | 5 | 3 | 2 |
| flagged (asked) | 46 | 14 | 32 |

| Receipt no. (printed twice) | receipts | correct |
| --- | ---: | ---: |
| both copies agree (confirmed) | 79 | **79** |
| copies disagree (flagged) | 40 | 16 |
| only one copy read | 113 | 12 |

**What passed**

- The checks carried over to a layout they were not designed on. Wrong accepted amounts fell from 16 to 3.
- The duplicate receipt number is a strong check: all 79 agreeing pairs were right.
- The confidence threshold tuned on Big C does *not* transfer (16 wrong with the gate alone). The arithmetic and payable rules have no tuned threshold, which is why they held up better.

**What failed, and why**

- **Two wrong "confirmed" values, the first ones in the project.** In `makro_noise2_06276`, Tesseract read the same digit wrong in both total and cash (`3047` → `3007`, `3340` → `3300`). Their difference, the change of 293, stays correct, so C1 holds. A check that subtracts two numbers cannot see an error shared by both. C2 or C3 would have caught it (items sum 3047), but only 4 of the 5 items were read, so neither check could run. **Lesson:** "confirmed" means "consistent", and the strongest claim needs two independent checks, not one.
- **noise3 (faded yellow) is 0%, unlike Big C, where it was easy.** The A4 page is much paler, and Tesseract loses the labels while still finding some amounts. Contrast preprocessing is tested in EXP-013.
- **noise4 (blur) is 0%.** The page is easy for a person to read at full size, but Tesseract returns noise. Downscaling to 50% or 35%, and page segmentation modes 3, 4 and 11, did not help (tried on 6 images). This is the case left for a VLM.
- **noise1 time is 0%:** the time is small header text, and the crumpled texture breaks its digits (`TIME 10.4`, `เวลา 5:6`).
- **The VAT row was usable on only 87 of 350 pages,** and complete item lists were found on 124. On degraded pages these long table rows lose digits first.

**Next:** contrast preprocessing for faded pages (EXP-013). Then require two independent checks before marking a total "confirmed".

## EXP-013: CLAHE contrast preprocessing

- **Why:** Makro noise3 (faded, yellow) was 0%, and the OCR text showed that the amounts were partly found while the pale labels were lost. Unlike blur (EXP-003, EXP-004), low contrast *can* be fixed by preprocessing.
- **Pilot (6 Makro noise3 pages, fields correct of 36):** grayscale 1, global autocontrast 1, adaptive threshold 5, **CLAHE (clip 3.0, 16 × 16 tiles) 23**. On 6 clean pages every method scored 35/36, so CLAHE did not hurt clean pages.
- **Full run:** `scripts/run_tesseract.py --preprocess clahe --engine-name tesseract-clahe` on both splits (700 images).

| Split / level | total raw → CLAHE | cash | change | receipt no. | date | time |
| --- | --- | --- | --- | --- | --- | --- |
| Makro clean | 100% → 100% | 100% → 100% | 100% → 98% | 94% → 98% | 82% → 84% | 98% → 100% |
| Makro noise1 (crumpled) | 84% → **68%** | 90% → **14%** | 84% → **0%** | 14% → 8% | 76% → 44% | 0% → 0% |
| Makro noise2 | 86% → 74% | 90% → 80% | 66% → **8%** | 80% → 86% | 86% → 72% | 90% → 96% |
| Makro noise3 (faded) | 0% → **84%** | 0% → **66%** | 0% → **52%** | 26% → **80%** | 10% → **70%** | 20% → **62%** |
| Makro noise4 (blur) | 0% → **44%** | 0% → **50%** | 0% → 0% | 0% → 32% | 0% → 2% | 8% → 30% |
| **Makro readable** | 54% → **74%** | 56% → 62% | 50% → **32%** | 43% → 61% | 51% → 54% | 43% → 58% |
| Big C clean | 100% → 100% | 94% → **100%** | 100% → 100% | 100% → 100% | 100% → 100% | 100% → 100% |
| Big C noise1 | 86% → 86% | 86% → 80% | 98% → 88% | 100% → 98% | 100% → 96% | 88% → **74%** |
| Big C noise4 (blur) | 84% → 80% | 6% → 8% | 34% → **68%** | 34% → **58%** | 10% → 14% | 28% → 42% |
| **Big C readable** | 93% → 92% | 75% → 76% | 85% → 90% | 86% → 90% | 82% → 80% | 81% → 78% |

- **Passed where contrast was the problem:** Makro faded pages go from unreadable to mostly readable, and even the Makro blur level reaches 44% on total, which downscaling and segmentation modes could not do (EXP-012). On Big C, CLAHE also fixes the three clean `3` → `2` misreads from EXP-007.
- **Failed where texture is the problem:** CLAHE amplifies local contrast everywhere, including the folds of crumpled paper. On Makro noise1, cash falls from 90% to 14% and change from 84% to 0%.
- **Conclusion:** neither setting is better overall, and they fail on different images. That is the setup for EXP-014: run both and let the checks pick.
- **Cost:** a second OCR pass doubles OCR time (Big C 1.0 s and Makro 4.0 s per image with CLAHE).

## EXP-014: Two passes, the checks choose, and a bug fix

- **Idea:** raw and CLAHE make *different* mistakes. Read each image twice and decide per field (`scripts/ensemble.py`):
  - **Amounts:** a value confirmed by the arithmetic checks in either pass wins. If both passes confirm different values, the field is flagged. Otherwise the two passes must read the same value. Otherwise it is flagged.
  - **Receipt no., date, time:** no arithmetic check exists, so the field is accepted only when both passes agree.
- **Bug found while doing this.** In CLAHE Makro, 7 "confirmed" cash values and 7 "repaired" change values were wrong. Cause: in `check()`, when the items confirmed the total and change was missing, cash was marked *confirmed* and change derived from it, although nothing had checked cash. Example: `makro_noise2_06230`, cash read `980.00` (true `280.00`), so change was "repaired" to `932.00`. **Fix:** a value is confirmed only if a check that holds includes it. When only one of cash/change is read, it stays unchecked and the other is not derived. All 14 wrong values disappeared. Accepted amounts on Big C Tesseract went from 647 to 636, with still 1 wrong; the EXP-010 entry has a correction note.

**Result: share of all receipts where the field is correct *and* accepted, and wrong values accepted (readable levels)**

| Split | total | cash | change | receipt no. | date | time | wrong accepted |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Big C, two passes | 92% | 77% | 84% | 82% | 78% | 72% | **1** of 1,500 |
| Makro, two passes | 66% | 60% | 55% | 38% | 38% | 42% | **6** of 1,500 |

For comparison, single-pass Tesseract on Makro readable got total 54%, cash 56%, change 50%, and accepted every value it read, right or wrong.

| Decision (both splits) | fields | correct |
| --- | ---: | ---: |
| confirmed by a check in either pass | 1,051 | 1,050 |
| both passes agree | 1,001 | 988 |
| flagged (asked) | 2,148 | — |

- **Passed:** on Big C, the system accepts 92% of totals with one wrong value in 1,500 readable fields. On Makro it recovers faded and some blurred pages that one pass could not read, without the crumpled-page losses of CLAHE alone.
- **Agreement is weaker than a check:** 13 wrong values passed because both passes made the *same* misread: 6 dates and 2 times (fields with no arithmetic check), and 5 amounts on receipts where no check could run. Two passes of the same engine are not fully independent.
- **Cost of caution:** many fields are flagged (2,148 of 4,200), mostly on noise4–6, where at least one pass reads nothing. In an app that means "please check these fields", which is better than a wrong number but not free.
- **Remaining wrong "confirmed" amount:** the correlated misread from EXP-012 (`3047` → `3007` in both total and cash), still 1 case.

**Next:** use the two receipt-number copies and the two passes together (four reads) to vote on IDs and dates. Try a VLM on the blur levels, where both passes fail.

## EXP-015: Voting on fields that have no arithmetic check

- **Problem (from EXP-014):** receipt no., date and time were accepted only when both passes read the same value. 8 of those agreed values were wrong, and on Makro only 38% of receipt numbers were accepted, although the number is printed twice on every invoice.
- **Look at the 8 wrong values first.** 5 are values no receipt can carry: years `2005` and `2075` (true `2025`), day `00`, time `00:93`. The other 3 are possible but wrong: `22/08` for `28/08`, `10/09` for `14/09`, `00:14` for `20:21`.

**Attempt 1: majority vote over 4 reads (failed).** Pool every read of the receipt number (2 printed copies × 2 passes) and accept the most common value with at least 2 votes.

- Makro receipt no. accepted rose (readable 38% → 50%), but wrong values accepted rose too, 6 → 9 (all levels).
- **Why it failed:** the two passes read the *same* printed copy from the same pixels, so they repeat the same misread. Example, `makro_noise2_06233`: reads `650432437268`, `650432437265`, `654432437268`, `650432437268`. The two copies of `650…268` are one copy read twice (raw and CLAHE), and they beat the correct `654…268`. Votes are only worth counting when they are independent.

**Attempt 2: count independent evidence only (passed).** `scripts/ensemble.py --rule vote`:

1. **Possible values only:** a real calendar date with year 2020–2026, a time with hh < 24 and mm < 60.
2. **Makro receipt no.:** if the two *printed copies* read the same in either pass, that value wins (two print locations are close to independent). If two passes confirm different values, ask the user.
3. Otherwise, as before: both passes extract the same value → accepted, else flagged.

**Result (wrong values accepted; correct and accepted in readable levels)**

| Split | rule | receipt no. | date | time | wrong, readable | wrong, all levels |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Big C | agree (EXP-014) | 82% | 78% | 72% | 1 | 5 |
| Big C | **vote** | 82% | 78% | 72% | **0** | **3** |
| Makro | agree (EXP-014) | 38% | 38% | 42% | 6 | 9 |
| Makro | majority of 4 reads (attempt 1) | 50% | 38% | 42% | 9 | 11 |
| Makro | **vote** | **50%** | 38% | 42% | 6 | **8** |

| Decision (both splits, all levels) | fields | correct |
| --- | ---: | ---: |
| confirmed by a check in either pass | 1,051 | 1,050 |
| agreed / voted | 1,027 | 1,017 |
| flagged (asked) | 2,122 | — |

- **Passed:** the possible-value rules removed the impossible dates and times without losing any correct value. The printed-copy rule raised Makro receipt numbers accepted on readable pages from 38% to 50% with no new wrong values on readable levels. Big C now accepts no wrong value at all in 1,500 readable fields.
- **Still wrong (11 of 2,078 accepted, all levels):**
  - 2 Makro receipt numbers on blurred pages (noise4–5) where the CLAHE pass misread the *same digit in both copies* (`8` → `0`, `8` → `2`): the same font blurred the same way gives the same error, so even two print locations are not fully independent under blur.
  - 3 possible-but-wrong dates and times (above). Nothing on the page can check them.
  - 6 amounts, mostly on noise5 where no arithmetic check could run.
- **Lesson:** the number of reads does not matter; the number of *independent* reads does. Two passes over the same pixels count as about one read.

**Next:** make the pipeline usable outside the benchmark: an API that takes a photo and returns each field with its status (EXP-016).

## EXP-016: From benchmark scripts to a service

- **Goal:** the benchmark scripts work on whole folders and CSV files. A user has one photo. Turn the best setup (two Tesseract passes, rules v4, checks, vote) into one function and an HTTP API, without changing what was measured.
- **Refactor:** `run_tesseract.ocr()`, `cross_check.check_item()` and `ensemble.decide_amount()` were split out of the batch loops, and `scripts/pipeline.py` chains them for one image. The two OCR passes run in parallel threads (each is its own Tesseract process).
- **How I checked that nothing changed:**
  - After the refactor, all `cross_check.csv` files were regenerated and are byte-identical to the committed ones. 7 images re-OCR'd with the new `ocr()` gave identical text and word confidences.
  - `tests/test_pipeline.py` runs the per-image pipeline on the stored OCR of all 700 benchmark images. Every amount gets the same decision as `ensemble.py`, and scoring the pipeline's accepted values against the labels gives exactly EXP-015's wrong counts (3 on Big C, 8 on Makro).
  - Unit tests pin the rules that earlier bugs broke: a lone cash value must stay unchecked (EXP-014), unpayable values, cash below total, impossible dates and times. 17 tests pass.
- **API** (`app/main.py`): `POST /read` takes an image and returns each field with `value`, `status` (`verified`, `agreed`, `needs_review`) and `candidates` (what each pass read, for the user to choose from). `GET /health` reports the Tesseract version and whether the Thai model is installed. `GET /` is a small upload page that shows the statuses and lets the user correct flagged fields.
- **Input safety:** uploads over 10 MB or with a side over 4,000 px are refused (413); bytes that do not decode as an image are refused (415). The image is decoded and re-encoded with OpenCV before Tesseract sees it, processed in a temporary folder, and deleted after the response. The log keeps only layout, time and status counts, never field values.

**Latency** (through HTTP, 3 images per noise level, Apple M5 CPU, both passes in parallel)

| Layout | images | median | p90 | max |
| --- | ---: | ---: | ---: | ---: |
| Big C slip | 21 | 1.11 s | 1.69 s | 1.90 s |
| Makro A4 invoice | 21 | 3.76 s | 4.78 s | 4.99 s |

- **Passed:** one call returns what the benchmark measured, with a trust level per field. Running the passes in parallel keeps the two-pass cost close to one pass (the same Makro image: 4.9 s with the passes one after the other, 2.6 s in parallel).
- **Not done yet:**
  - The `Dockerfile` (for a Hugging Face Docker Space) has not been built: Docker is not installed on this machine. Debian ships Tesseract 5.3 while the benchmark used 5.5.4, so the scores must be rechecked inside the image before quoting them for the deployed version.
  - No real phone photos have gone through it. Real photos are rotated, cropped and lit unevenly, which the synthetic data does not cover.

**Next:** build and deploy the image, then feed it real receipts and log the results as a new split.

