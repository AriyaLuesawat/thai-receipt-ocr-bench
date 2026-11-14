# Thai Receipt OCR Benchmark

How accurately can OCR systems read the fields that matter on Thai receipts (total, cash, change, receipt number, date, time), and how fast does that accuracy fall as the image gets worse?

This project measures that on the [nectec/thairocr](https://huggingface.co/datasets/nectec/thairocr) dataset, which provides synthetic Thai receipts with full JSON ground truth at seven noise levels (a clean render plus `noise1`–`noise6`).

> Status: work in progress. The first baseline is EasyOCR with rule-based field extraction on a 350-image Big C sample. More engines (Tesseract, open vision-language models, and a commercial Thai receipt API) and a check against real receipts are planned.

## Results

_Filled in by `scripts/evaluate.py`; see [Results so far](#results-so-far)._

## Method

1. **Sample.** `scripts/fetch_subset.py` takes 50 receipts per noise level from the `bigc` split (350 images), using one contiguous window at a seeded random offset inside each 1,000-row block. Only the sample is downloaded, not the full 14.6 GB dataset.
2. **OCR.** `scripts/run_easyocr.py` runs EasyOCR 1.7.2 with Thai and English models and saves every text box with its position and confidence.
3. **Field extraction.** `scripts/extract.py` groups boxes into lines and reads each field from the label next to it ("Total", "Cash", "Receipt No", ...). It fixes common digit confusions such as `o` → `0`. For comparison, it also applies the rule SaiJai's slip backend uses for amounts: take the largest number with two decimals.
4. **Scoring.** `scripts/evaluate.py` counts a field as correct only on an exact match (amounts within 0.005 baht), per noise level.

## Reproduce

```bash
python3.12 -m venv .venv
.venv/bin/pip install easyocr==1.7.2
.venv/bin/python scripts/fetch_subset.py --split bigc --per-level 50
.venv/bin/python scripts/run_easyocr.py --split bigc
cd scripts && ../.venv/bin/python evaluate.py --engine easyocr --split bigc
```

## Data and license

The images and labels come from `nectec/thairocr` on Hugging Face. Its dataset card does not state a license, so this repository does not redistribute any images or labels. The scripts download them from the source. The receipts are synthetic: tax IDs, amounts, and references are generated, not taken from real purchases.

## Limitations

- Synthetic receipts may be easier or harder than real phone photos. A small set of real receipts is planned to check this.
- Product names are cut off with "..." on the printed receipt, so item lines are not scored yet.
- The noise levels are named `noise1`–`noise6` in the dataset, and their numbers may not mean increasing difficulty. The results report each level separately.
