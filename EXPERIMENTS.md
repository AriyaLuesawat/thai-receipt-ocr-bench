# Experiment log

Every run is recorded here, including the ones that failed: what was tried, what happened, why it passed or failed, and what changed next. Newest entries are at the bottom.

Scores are exact-match field accuracy on the Big C sample (50 receipts per noise level). "Readable" means clean–noise4, the levels a person can still read. noise5–6 are a stress test (see EXP-002).

| ID | Date | What | Result |
| --- | --- | --- | --- |
| EXP-001 | 2026-11-14 | Download sample one row per request | Failed: rate-limited (HTTP 429). Fixed by fetching one window per level. |
| EXP-002 | 2026-11-14 | EasyOCR + rule extractor v1, 350 receipts | Baseline. Readable total 75%. Clean 100%. noise4–6 0%. |
| EXP-003 | 2026-11-14 | Median filter before OCR on noise4 | Failed: 0/10. Wrong diagnosis (noise4 is blur, not speckle). |
| EXP-004 | 2026-11-14 | Upscale and sharpen before OCR on noise4 | Failed: 0/10 at every setting. Sharpening also hurt noise1. |
| EXP-005 | 2026-11-14 | Rule extractor v2 (fuzzy labels, Thai digits) | Passed: noise1 time 72% → 96%, receipt no. 82% → 96%, change 46% → 68%. No loss on clean. |
| EXP-006 | 2026-11-14 | Quality gate: detect failed OCR from its own confidence | Passed (in-sample): mean confidence < 0.3 rejects 100% of failed images and 0% of good ones. |

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
