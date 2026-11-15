# Thai Receipt OCR Benchmark

How accurately can OCR systems read the fields that matter on Thai receipts (total, cash, change, receipt number, date, time), and how fast does that accuracy fall as the image gets worse?

This project measures that on the [nectec/thairocr](https://huggingface.co/datasets/nectec/thairocr) dataset, which provides synthetic Thai receipts with full JSON ground truth at seven noise levels (a clean render plus `noise1`–`noise6`).

> Status: work in progress. Two OCR engines (EasyOCR and Tesseract), rule-based field extraction, and self-checks have been tested on two receipt layouts: 350 Big C slips and 350 Makro A4 tax invoices. Next: a Thai vision-language model for blurred images, and a check against real receipts.

## Results so far

### Engine comparison

50 Big C receipts per level, CPU (Apple M5), same field extractor (v3) for both engines. Each cell is the share of receipts where the field was read exactly right. Readable = clean–noise4.

| Engine | total | cash | change | receipt no. | date | time | noise4 total | s/img |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| EasyOCR 1.7.2 | 77% | 74% | 70% | 79% | 80% | 78% | 0% | 5.7 |
| **Tesseract 5.5.4** | **93%** | **75%** | **85%** | **86%** | **82%** | **81%** | **84%** | **1.6** |

Tesseract is better on every readable field and 3.5× faster, mainly because it still reads blurred receipts (noise4) where EasyOCR returns nothing ([EXP-007](EXPERIMENTS.md#exp-007-tesseract-instead-of-easyocr)).

### EasyOCR by noise level

EasyOCR 1.7.2, field extractor v2.

| Level | What the noise looks like | total | cash | change | receipt no. | date | time | s/img |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| clean | none | 100% | 100% | 100% | 100% | 100% | 100% | 5.5 |
| noise1 | crumpled paper | 86% | 72% | 68% | 96% | 100% | 96% | 4.7 |
| noise2 | faded text | 98% | 92% | 82% | 98% | 98% | 92% | 4.9 |
| noise3 | yellow paper | 100% | 98% | 100% | 98% | 100% | 100% | 4.8 |
| noise4 | blur | 0% | 0% | 0% | 0% | 0% | 0% | 8.6 |
| **Readable (clean–noise4)** | | **77%** | **72%** | **70%** | **78%** | **80%** | **78%** | 5.7 |
| noise5 | very faded ink (stress test) | 0% | 0% | 0% | 0% | 0% | 0% | 9.3 |
| noise6 | pixelated (stress test) | 0% | 0% | 0% | 0% | 0% | 0% | 7.9 |

noise5 and noise6 are hard for a person to read, so they are reported separately and left out of the main score.

### Tesseract by noise level

Tesseract 5.5.4 (`tessdata_best` Thai + English), field extractor v3.

| Level | total | cash | change | receipt no. | date | time | s/img |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| clean | 100% | 94% | 100% | 100% | 100% | 100% | 1.6 |
| noise1 | 86% | 86% | 98% | 100% | 100% | 88% | 1.6 |
| noise2 | 96% | 92% | 92% | 94% | 98% | 90% | 1.6 |
| noise3 | 100% | 96% | 100% | 100% | 100% | 100% | 1.5 |
| noise4 | 84% | 6% | 34% | 34% | 10% | 28% | 1.9 |
| **Readable (clean–noise4)** | **93%** | **75%** | **85%** | **86%** | **82%** | **81%** | 1.6 |
| noise5 (stress) | 64% | 30% | 62% | 2% | 2% | 30% | 2.0 |
| noise6 (stress) | 0% | 0% | 0% | 0% | 0% | 0% | 2.7 |

### Second layout: Makro tax invoices

Tesseract, 50 Makro A4 tax invoices per level, readable levels (clean–noise4). Details in [EXP-011](EXPERIMENTS.md#exp-011-big-c-rules-on-makro-tax-invoices) to [EXP-014](EXPERIMENTS.md#exp-014-two-passes-the-checks-choose-and-a-bug-fix).

| Setup | total | cash | change | receipt no. | date | time | wrong values accepted |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Big C rules, unchanged (v3) | 0% | 56% | 0% | 37% | 0% | 36% | all read values |
| Layout-aware rules (v4) | 54% | 56% | 50% | 43% | 51% | 43% | all read values |
| v4 + CLAHE contrast | 74% | 62% | 32% | 61% | 54% | 58% | all read values |
| **v4, two passes (raw + CLAHE), checks decide** | **66%** | **60%** | **55%** | 38% | 38% | 42% | **6 of 1,500** |

In the last row a value counts only if it is correct *and* accepted. Everything else goes back to the user to check.

### Key findings

1. **When EasyOCR can see the text, extraction is nearly perfect.** Clean and yellow-paper receipts score 98–100% on every field.
2. **Blur breaks EasyOCR completely, but not Tesseract.** Every noise4 receipt fails with EasyOCR, and median filtering, upscaling, and sharpening did not help ([EXP-003](EXPERIMENTS.md#exp-003-median-filter-on-noise4), [EXP-004](EXPERIMENTS.md#exp-004-upscale-and-sharpen-on-noise4)). Tesseract reads the total on 84% of the same images ([EXP-007](EXPERIMENTS.md#exp-007-tesseract-instead-of-easyocr)). Its remaining noise4 errors are lost colons, which extractor v3 partly handles ([EXP-008](EXPERIMENTS.md#exp-008-rule-extractor-v3)), and misread digits, which it cannot.
3. **No engine is perfect on clean receipts.** Tesseract reads `3` as `2` in this font (`Cash: 702.00` for `703.00`) on 3 of 50 clean receipts, which EasyOCR reads correctly.
4. **Most other misses come from misread labels, not misread numbers.** EasyOCR turns `change:` into `chance:` and `time:` into `tme:`. Matching labels by similarity raised noise1 time from 72% to 96% with no loss on clean receipts ([EXP-005](EXPERIMENTS.md#exp-005-rule-extractor-v2)).
5. **"Take the largest amount" fails on receipts (12%).** That is the rule SaiJai uses for transfer slips, but on a receipt the cash paid is larger than the total.
6. **OCR knows when it has failed, mostly.** For EasyOCR, rejecting images with mean confidence below 0.35 caught 100% of failed images and 0% of good ones, also on held-out images ([EXP-006](EXPERIMENTS.md#exp-006-quality-gate), [EXP-009](EXPERIMENTS.md#exp-009-quality-gate-for-tesseract-checked-on-held-out-images)). Tesseract stays confident when it is wrong, so a whole-image check barely works (margin 0.03). Checking confidence **per field** works better: keeping values with word confidence ≥ 0.77 raised the share of correct values on held-out images from 94.6% to 99.1%. The confident `3` → `2` misreads still get through.
7. **The receipt can check itself.** Using cash − total = change and sum of items = total, every amount that passed a check was correct on both engines (1,091 values in EXP-010). Combined with the confidence gate for the rest, Tesseract's wrong accepted amounts fell from 9 to 1 of about 650, and EasyOCR's to 0 of 511 ([EXP-010](EXPERIMENTS.md#exp-010-arithmetic-cross-checks)). The remaining doubtful values go back to the user instead of being guessed.
8. **Rules built on one store fail on another, and fail silently.** On Makro tax invoices, the Big C rules read the `TOTAL` row, which is the amount *before* VAT, so every total was wrong rather than missing. Layout detection plus Makro rules raised readable totals from 0% to 54% without changing any Big C output ([EXP-011](EXPERIMENTS.md#exp-011-big-c-rules-on-makro-tax-invoices), [EXP-012](EXPERIMENTS.md#exp-012-extractor-v4-and-makro-checks)).
9. **Preprocessing is not one-size-fits-all.** CLAHE contrast enhancement rescued faded Makro pages (total 0% → 84%) but wrecked crumpled ones (change 84% → 0%). Reading each image both ways and letting the checks choose kept most of the gain and accepted only 6 wrong values in 1,500 fields ([EXP-013](EXPERIMENTS.md#exp-013-clahe-contrast-preprocessing), [EXP-014](EXPERIMENTS.md#exp-014-two-passes-the-checks-choose-and-a-bug-fix)).
10. **"Consistent" is not "correct".** One Makro receipt had the same digit misread in both total and cash, so cash − total = change still held. A check that subtracts two numbers cannot see an error they share. Also, a bug marked unchecked values as confirmed. It was invisible on Big C and only showed up on the second layout, which is one more reason to test on more than one layout.

Every run, including the failed ones, is logged with its cause and the next step in **[EXPERIMENTS.md](EXPERIMENTS.md)**.

## Method

1. **Sample.** `scripts/fetch_subset.py` takes 50 receipts per noise level from the `bigc` split (350 images), using one contiguous window at a seeded random offset inside each 1,000-row block. Only the sample is downloaded, not the full 14.6 GB dataset.
2. **OCR.** `scripts/run_easyocr.py` runs EasyOCR 1.7.2 with Thai and English models and saves every text box with its position and confidence. `scripts/run_tesseract.py` runs Tesseract 5 with the `tessdata_best` Thai and English models and saves the page text.
3. **Field extraction.** `scripts/extract.py` groups boxes into lines and reads each field from the label next to it ("Total", "Cash", "Receipt No", ...). v1 needs the exact label. v2 matches labels by similarity and maps Thai digits and look-alike letters (`o`, `d` → `0`). v3 also accepts a label without its colon (`Cash 243.00`). For comparison, it also applies the rule SaiJai's slip backend uses for amounts: take the largest number with two decimals.
4. **Scoring.** `scripts/evaluate.py` counts a field as correct only on an exact match (amounts within 0.005 baht), per noise level, and reports readable levels (clean–noise4) separately from the stress test (noise5–6).
5. **Quality gate.** `scripts/quality_gate.py` checks whether OCR confidence and image sharpness can flag failed images, or single wrong fields, before their numbers are trusted. The threshold is chosen on one half of the images and reported on the other half.
6. **Cross-checks.** `scripts/cross_check.py` checks the amounts against each other (cash − total = change, sum of items = total, before-VAT + VAT = total on Makro, cash ≥ total, payable to 0.25 baht) and marks each one confirmed, repaired, flagged, or unchecked. Makro receipt numbers are printed twice, so the two copies are compared too.
7. **Two passes.** `scripts/run_tesseract.py --preprocess clahe` reads each image again after contrast enhancement, and `scripts/ensemble.py` keeps, per field, a value a check confirmed in either pass, or one both passes agree on.

## Reproduce

```bash
python3.12 -m venv .venv
.venv/bin/pip install easyocr==1.7.2
.venv/bin/python scripts/fetch_subset.py --split bigc --per-level 50
.venv/bin/python scripts/run_easyocr.py --split bigc
cd scripts
../.venv/bin/python evaluate.py --engine easyocr --split bigc
../.venv/bin/python quality_gate.py --split bigc
```

Tesseract (`brew install tesseract`, then put `tha.traineddata` and `eng.traineddata` from [tessdata_best](https://github.com/tesseract-ocr/tessdata_best) in `data/tessdata/`):

```bash
.venv/bin/python scripts/run_tesseract.py --split bigc
cd scripts && ../.venv/bin/python evaluate.py --engine tesseract --split bigc
../.venv/bin/python quality_gate.py --engine tesseract --extractor rules_v3
../.venv/bin/python cross_check.py --engine tesseract --extractor rules_v4
```

Makro and the two-pass setup (repeat for `--split bigc`):

```bash
.venv/bin/python scripts/fetch_subset.py --split makro --per-level 50
.venv/bin/python scripts/run_tesseract.py --split makro
.venv/bin/python scripts/run_tesseract.py --split makro --preprocess clahe --engine-name tesseract-clahe
cd scripts
for e in tesseract tesseract-clahe; do
  ../.venv/bin/python evaluate.py --engine $e --split makro
  ../.venv/bin/python cross_check.py --engine $e --split makro --extractor rules_v4
done
../.venv/bin/python ensemble.py --split makro
```

## Data and license

The images and labels come from `nectec/thairocr` on Hugging Face. Its dataset card does not state a license, so this repository does not redistribute any images or labels. The scripts download them from the source. The receipts are synthetic: tax IDs, amounts, and references are generated, not taken from real purchases.

## Limitations

- Synthetic receipts may be easier or harder than real phone photos. A small set of real receipts is planned to check this.
- Product names are cut off with "..." on the printed receipt, so item lines are not scored yet.
- The noise levels are named `noise1`–`noise6` in the dataset, but the numbers don't mean increasing difficulty: noise3 (yellow paper) is easy, and noise4 (blur) is the first level EasyOCR cannot read, while Tesseract still reads most totals on it. Each level is reported separately.
- Two layouts are tested (Big C slips and Makro tax invoices). The handwritten bills in the dataset are not tested yet, and new stores still need their own rules.
