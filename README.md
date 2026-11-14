# Thai Receipt OCR Benchmark

How accurately can OCR systems read the fields that matter on Thai receipts (total, cash, change, receipt number, date, time), and how fast does that accuracy fall as the image gets worse?

This project measures that on the [nectec/thairocr](https://huggingface.co/datasets/nectec/thairocr) dataset, which provides synthetic Thai receipts with full JSON ground truth at seven noise levels (a clean render plus `noise1`–`noise6`).

> Status: work in progress. The first baseline is EasyOCR with rule-based field extraction on a 350-image Big C sample. Next: Typhoon OCR 1.5 (a Thai vision-language model) and a check against real receipts.

## Results so far

EasyOCR 1.7.2 on CPU (Apple M5), 50 Big C receipts per level, field extractor v2. Each cell is the share of receipts where the field was read exactly right.

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

### Key findings

1. **When EasyOCR can see the text, extraction is nearly perfect.** Clean and yellow-paper receipts score 98–100% on every field.
2. **Blur breaks EasyOCR completely.** Every noise4 receipt fails, although a person can read it. Median filtering, upscaling, and sharpening did not help ([EXP-003](EXPERIMENTS.md#exp-003-median-filter-on-noise4), [EXP-004](EXPERIMENTS.md#exp-004-upscale-and-sharpen-on-noise4)).
3. **Most other misses come from misread labels, not misread numbers.** EasyOCR turns `change:` into `chance:` and `time:` into `tme:`. Matching labels by similarity raised noise1 time from 72% to 96% with no loss on clean receipts ([EXP-005](EXPERIMENTS.md#exp-005-rule-extractor-v2)).
4. **"Take the largest amount" fails on receipts (12%).** That is the rule SaiJai uses for transfer slips, but on a receipt the cash paid is larger than the total.
5. **OCR knows when it has failed.** Rejecting images with mean confidence below 0.3 caught 100% of failed images and 0% of good ones on this sample ([EXP-006](EXPERIMENTS.md#exp-006-quality-gate)). The threshold was chosen on the same data, so it still needs a held-out check.

Every run, including the failed ones, is logged with its cause and the next step in **[EXPERIMENTS.md](EXPERIMENTS.md)**.

## Method

1. **Sample.** `scripts/fetch_subset.py` takes 50 receipts per noise level from the `bigc` split (350 images), using one contiguous window at a seeded random offset inside each 1,000-row block. Only the sample is downloaded, not the full 14.6 GB dataset.
2. **OCR.** `scripts/run_easyocr.py` runs EasyOCR 1.7.2 with Thai and English models and saves every text box with its position and confidence.
3. **Field extraction.** `scripts/extract.py` groups boxes into lines and reads each field from the label next to it ("Total", "Cash", "Receipt No", ...). v1 needs the exact label. v2 matches labels by similarity and maps Thai digits and look-alike letters (`o`, `d` → `0`). For comparison, it also applies the rule SaiJai's slip backend uses for amounts: take the largest number with two decimals.
4. **Scoring.** `scripts/evaluate.py` counts a field as correct only on an exact match (amounts within 0.005 baht), per noise level, and reports readable levels (clean–noise4) separately from the stress test (noise5–6).
5. **Quality gate.** `scripts/quality_gate.py` checks whether OCR confidence and image sharpness can flag failed images before their numbers are trusted.

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

## Data and license

The images and labels come from `nectec/thairocr` on Hugging Face. Its dataset card does not state a license, so this repository does not redistribute any images or labels. The scripts download them from the source. The receipts are synthetic: tax IDs, amounts, and references are generated, not taken from real purchases.

## Limitations

- Synthetic receipts may be easier or harder than real phone photos. A small set of real receipts is planned to check this.
- Product names are cut off with "..." on the printed receipt, so item lines are not scored yet.
- The noise levels are named `noise1`–`noise6` in the dataset, but the numbers don't mean increasing difficulty: noise3 (yellow paper) is easy, and noise4 (blur) is the first level EasyOCR cannot read. Each level is reported separately.
- All receipts in this sample use the same Big C layout. The Makro tax invoices and handwritten bills in the dataset are needed to test other layouts.
