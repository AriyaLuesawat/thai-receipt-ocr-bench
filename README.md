# Thai Receipt OCR Benchmark

How accurately can OCR systems read the fields that matter on Thai receipts (total, cash, change, receipt number, date, time), and how fast does that accuracy fall as the image gets worse?

This project measures that on the [nectec/thairocr](https://huggingface.co/datasets/nectec/thairocr) dataset, which provides synthetic Thai receipts with full JSON ground truth at seven noise levels (a clean render plus `noise1`–`noise6`).

> Status: work in progress. Two OCR engines (EasyOCR and Tesseract) have been compared with rule-based field extraction on a 350-image Big C sample. Next: Typhoon OCR 1.5 (a Thai vision-language model) and a check against real receipts.

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

### Key findings

1. **When EasyOCR can see the text, extraction is nearly perfect.** Clean and yellow-paper receipts score 98–100% on every field.
2. **Blur breaks EasyOCR completely, but not Tesseract.** Every noise4 receipt fails with EasyOCR, and median filtering, upscaling, and sharpening did not help ([EXP-003](EXPERIMENTS.md#exp-003-median-filter-on-noise4), [EXP-004](EXPERIMENTS.md#exp-004-upscale-and-sharpen-on-noise4)). Tesseract reads the total on 84% of the same images ([EXP-007](EXPERIMENTS.md#exp-007-tesseract-instead-of-easyocr)). Its remaining noise4 errors are lost colons, which extractor v3 partly handles ([EXP-008](EXPERIMENTS.md#exp-008-rule-extractor-v3)), and misread digits, which it cannot.
3. **No engine is perfect on clean receipts.** Tesseract reads `3` as `2` in this font (`Cash: 702.00` for `703.00`) on 3 of 50 clean receipts, which EasyOCR reads correctly.
4. **Most other misses come from misread labels, not misread numbers.** EasyOCR turns `change:` into `chance:` and `time:` into `tme:`. Matching labels by similarity raised noise1 time from 72% to 96% with no loss on clean receipts ([EXP-005](EXPERIMENTS.md#exp-005-rule-extractor-v2)).
5. **"Take the largest amount" fails on receipts (12%).** That is the rule SaiJai uses for transfer slips, but on a receipt the cash paid is larger than the total.
6. **OCR knows when it has failed, mostly.** For EasyOCR, rejecting images with mean confidence below 0.35 caught 100% of failed images and 0% of good ones, also on held-out images ([EXP-006](EXPERIMENTS.md#exp-006-quality-gate), [EXP-009](EXPERIMENTS.md#exp-009-quality-gate-for-tesseract-checked-on-held-out-images)). Tesseract stays confident when it is wrong, so a whole-image check barely works (margin 0.03). Checking confidence **per field** works better: keeping values with word confidence ≥ 0.77 raised the share of correct values on held-out images from 94.6% to 99.1%. The confident `3` → `2` misreads still get through, so the next step is an arithmetic check (cash − total = change).

Every run, including the failed ones, is logged with its cause and the next step in **[EXPERIMENTS.md](EXPERIMENTS.md)**.

## Method

1. **Sample.** `scripts/fetch_subset.py` takes 50 receipts per noise level from the `bigc` split (350 images), using one contiguous window at a seeded random offset inside each 1,000-row block. Only the sample is downloaded, not the full 14.6 GB dataset.
2. **OCR.** `scripts/run_easyocr.py` runs EasyOCR 1.7.2 with Thai and English models and saves every text box with its position and confidence. `scripts/run_tesseract.py` runs Tesseract 5 with the `tessdata_best` Thai and English models and saves the page text.
3. **Field extraction.** `scripts/extract.py` groups boxes into lines and reads each field from the label next to it ("Total", "Cash", "Receipt No", ...). v1 needs the exact label. v2 matches labels by similarity and maps Thai digits and look-alike letters (`o`, `d` → `0`). v3 also accepts a label without its colon (`Cash 243.00`). For comparison, it also applies the rule SaiJai's slip backend uses for amounts: take the largest number with two decimals.
4. **Scoring.** `scripts/evaluate.py` counts a field as correct only on an exact match (amounts within 0.005 baht), per noise level, and reports readable levels (clean–noise4) separately from the stress test (noise5–6).
5. **Quality gate.** `scripts/quality_gate.py` checks whether OCR confidence and image sharpness can flag failed images, or single wrong fields, before their numbers are trusted. The threshold is chosen on one half of the images and reported on the other half.

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
```

## Data and license

The images and labels come from `nectec/thairocr` on Hugging Face. Its dataset card does not state a license, so this repository does not redistribute any images or labels. The scripts download them from the source. The receipts are synthetic: tax IDs, amounts, and references are generated, not taken from real purchases.

## Limitations

- Synthetic receipts may be easier or harder than real phone photos. A small set of real receipts is planned to check this.
- Product names are cut off with "..." on the printed receipt, so item lines are not scored yet.
- The noise levels are named `noise1`–`noise6` in the dataset, but the numbers don't mean increasing difficulty: noise3 (yellow paper) is easy, and noise4 (blur) is the first level EasyOCR cannot read, while Tesseract still reads most totals on it. Each level is reported separately.
- All receipts in this sample use the same Big C layout. The Makro tax invoices and handwritten bills in the dataset are needed to test other layouts.
