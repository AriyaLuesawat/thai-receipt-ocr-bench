"""Can we tell, before trusting the result, that OCR failed on an image? (EXP-006)

For every EasyOCR result it records two cheap signals:
  - mean_conf: the mean EasyOCR confidence over all text boxes
  - laplacian_var: variance of the Laplacian, a standard sharpness measure
and the v2 field accuracy (share of the 6 fields correct). It then tests the rule
"reject the image (ask for a retake) when mean_conf < threshold".

Run evaluate.py first; it writes per_image.csv.
Output: results/easyocr/<split>/quality.csv and a summary table.
"""

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

import cv2

from extract import FIELDS

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", default="bigc")
    parser.add_argument("--extractor", default="rules_v2")
    args = parser.parse_args()

    run = ROOT / "results" / "easyocr" / args.split
    per_image = {r["file"]: r for r in csv.DictReader((run / "per_image.csv").open(encoding="utf-8"))}
    rows = []
    for line in (run / "raw.jsonl").open(encoding="utf-8"):
        item = json.loads(line)
        conf = statistics.mean(b["conf"] for b in item["boxes"]) if item["boxes"] else 0.0
        gray = cv2.imread(str(ROOT / "data" / args.split / "images" / item["file"]), cv2.IMREAD_GRAYSCALE)
        sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        acc = sum(int(per_image[item["file"]][f"{args.extractor}:{f}:ok"]) for f in FIELDS) / len(FIELDS)
        rows.append({"file": item["file"], "receipt_type": item["receipt_type"], "mean_conf": round(conf, 4), "laplacian_var": round(sharp, 1), "field_accuracy": round(acc, 4)})

    with (run / "quality.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    by_level = defaultdict(list)
    for r in rows:
        by_level[r["receipt_type"]].append(r)
    print("| level | median conf | median sharpness | field accuracy |\n|---|---:|---:|---:|")
    for level in sorted(by_level, key=lambda s: int("".join(c for c in s if c.isdigit()) or 0)):
        v = by_level[level]
        print(f"| {level} | {statistics.median(r['mean_conf'] for r in v):.2f} | {statistics.median(r['laplacian_var'] for r in v):,.0f} | {statistics.mean(r['field_accuracy'] for r in v):.0%} |")

    good = [r for r in rows if r["field_accuracy"] >= 5 / 6]
    bad = [r for r in rows if r["field_accuracy"] < 0.5]
    print(f"\ngood = at least 5 of 6 fields right (n={len(good)}); failed = fewer than 3 right (n={len(bad)})")
    print("| reject if mean conf < | failed images rejected | good images rejected |\n|---:|---:|---:|")
    for t in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6):
        print(f"| {t} | {sum(r['mean_conf'] < t for r in bad) / len(bad):.0%} | {sum(r['mean_conf'] < t for r in good) / len(good):.0%} |")


if __name__ == "__main__":
    main()
