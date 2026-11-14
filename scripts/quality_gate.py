"""Can we tell, before trusting the result, that OCR failed on an image? (EXP-006, EXP-009)

For every OCR result it records two cheap signals:
  - mean_conf: mean OCR confidence, scaled to 0-1
      EasyOCR: mean over text boxes; Tesseract: mean over recognised words (0-100 / 100)
  - laplacian_var: variance of the Laplacian, a standard sharpness measure
and the field accuracy (share of the 6 fields correct). It then tests the rule
"reject the image (ask for a retake) when mean_conf < threshold".

To avoid choosing the threshold on the data it is scored on, images are split in two
halves by a hash of the file name: the threshold is chosen on the "tune" half and the
result is reported on the "test" half.

Run evaluate.py first; it writes per_image.csv.
Output: results/<engine>/<split>/quality.csv and summary tables.
"""

import argparse
import csv
import hashlib
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

import cv2

from evaluate import NUMERIC
from extract import FIELDS

ROOT = Path(__file__).resolve().parent.parent
THRESHOLDS = [round(0.05 * i, 2) for i in range(1, 20)]


def mean_conf(item: dict) -> float:
    if "boxes" in item:
        return statistics.mean(b["conf"] for b in item["boxes"]) if item["boxes"] else 0.0
    words = item.get("words") or []
    return statistics.mean(w["conf"] for w in words) / 100 if words else 0.0


def half(file: str) -> str:
    return "tune" if int(hashlib.md5(file.encode()).hexdigest(), 16) % 2 == 0 else "test"


def rates(rows: list[dict], t: float) -> tuple[float, float, int, int]:
    good = [r for r in rows if r["field_accuracy"] >= 5 / 6]
    bad = [r for r in rows if r["field_accuracy"] < 0.5]
    caught = sum(r["mean_conf"] < t for r in bad) / len(bad) if bad else float("nan")
    lost = sum(r["mean_conf"] < t for r in good) / len(good) if good else float("nan")
    return caught, lost, len(bad), len(good)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--engine", default="easyocr")
    parser.add_argument("--split", default="bigc")
    parser.add_argument("--extractor", default="rules_v2")
    args = parser.parse_args()

    run = ROOT / "results" / args.engine / args.split
    per_image = {r["file"]: r for r in csv.DictReader((run / "per_image.csv").open(encoding="utf-8"))}
    rows = []
    for line in (run / "raw.jsonl").open(encoding="utf-8"):
        item = json.loads(line)
        gray = cv2.imread(str(ROOT / "data" / args.split / "images" / item["file"]), cv2.IMREAD_GRAYSCALE)
        sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        acc = sum(int(per_image[item["file"]][f"{args.extractor}:{f}:ok"]) for f in FIELDS) / len(FIELDS)
        rows.append({"file": item["file"], "receipt_type": item["receipt_type"], "half": half(item["file"]),
                     "mean_conf": round(mean_conf(item), 4), "laplacian_var": round(sharp, 1), "field_accuracy": round(acc, 4)})

    with (run / "quality.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    by_level = defaultdict(list)
    for r in rows:
        by_level[r["receipt_type"]].append(r)
    print(f"engine={args.engine} extractor={args.extractor}")
    print("| level | median conf | median sharpness | field accuracy |\n|---|---:|---:|---:|")
    for level in sorted(by_level, key=lambda s: int("".join(c for c in s if c.isdigit()) or 0)):
        v = by_level[level]
        print(f"| {level} | {statistics.median(r['mean_conf'] for r in v):.2f} | {statistics.median(r['laplacian_var'] for r in v):,.0f} | {statistics.mean(r['field_accuracy'] for r in v):.0%} |")

    print("\ngood = at least 5 of 6 fields right; failed = fewer than 3 right")
    print("| reject if conf < | failed rejected (all) | good rejected (all) |\n|---:|---:|---:|")
    for t in THRESHOLDS:
        caught, lost, nb, ng = rates(rows, t)
        print(f"| {t} | {caught:.0%} | {lost:.0%} |")
    print(f"(n failed={nb}, n good={ng})")

    tune = [r for r in rows if r["half"] == "tune"]
    test = [r for r in rows if r["half"] == "test"]
    # Best (failed caught - good lost) on the tune half. Several thresholds often tie; take the
    # middle one, so the cut sits away from both groups instead of on the edge of one.
    score = {t: rates(tune, t)[0] - rates(tune, t)[1] for t in THRESHOLDS}
    tied = [t for t in THRESHOLDS if score[t] == max(score.values())]
    best = tied[len(tied) // 2]
    tc, tl, tnb, tng = rates(tune, best)
    sc, sl, snb, sng = rates(test, best)
    print(f"\nheld-out: threshold chosen on tune half = {best}")
    print("| half | failed rejected | good rejected | n failed | n good |\n|---|---:|---:|---:|---:|")
    print(f"| tune | {tc:.0%} | {tl:.0%} | {tnb} | {tng} |")
    print(f"| test | {sc:.0%} | {sl:.0%} | {snb} | {sng} |")

    gaps = [r["mean_conf"] for r in rows if r["field_accuracy"] >= 5 / 6], [r["mean_conf"] for r in rows if r["field_accuracy"] < 0.5]
    print(f"margin: lowest good conf {min(gaps[0]):.3f} - highest failed conf {max(gaps[1]):.3f} = {min(gaps[0]) - max(gaps[1]):.3f}")

    if any("words" in json.loads(l) for l in (run / "raw.jsonl").open(encoding="utf-8")):
        field_gate(run, per_image, args.extractor)


def field_conf(words: list[dict], field: str, value: str) -> float:
    """Confidence of the OCR word that holds the extracted value (lowest if several match, 0 if none)."""
    key = re.sub(r"\D", "", f"{float(value):.2f}" if field in NUMERIC else value)
    if not key:
        return 0.0
    confs = [w["conf"] / 100 for w in words if key in (d := re.sub(r"\D", "", w["text"])) and len(d) <= len(key) + 2]
    return min(confs) if confs else 0.0


def field_gate(run: Path, per_image: dict, extractor: str) -> None:
    """EXP-009: accept or reject each field on its own, instead of the whole image."""
    recs = []
    for line in (run / "raw.jsonl").open(encoding="utf-8"):
        item = json.loads(line)
        p = per_image[item["file"]]
        for f in FIELDS:
            value = p[f"{extractor}:{f}"]
            if value:
                recs.append({"half": half(item["file"]), "conf": field_conf(item["words"], f, value), "ok": int(p[f"{extractor}:{f}:ok"])})

    def stats(rs: list[dict], t: float) -> tuple[int, float, int, int]:
        kept = [r for r in rs if r["conf"] >= t]
        right = sum(r["ok"] for r in kept)
        return len(kept), right / len(kept) if kept else float("nan"), len(kept) - right, sum(r["ok"] for r in rs) - right

    print(f"\nper-field gate: {len(recs)} extracted values, {sum(r['ok'] for r in recs)} correct")
    print("| keep field if conf >= | fields kept | correct among kept | wrong let through | correct thrown away |\n|---:|---:|---:|---:|---:|")
    for t in (0.0, 0.5, 0.7, 0.8, 0.85, 0.9, 0.93, 0.95):
        n, prec, wrong, lost = stats(recs, t)
        print(f"| {t} | {n} | {prec:.1%} | {wrong} | {lost} |")

    tune = [r for r in recs if r["half"] == "tune"]
    test = [r for r in recs if r["half"] == "test"]
    # Lowest threshold that keeps at least 99% of accepted values correct on the tune half.
    grid = [round(0.01 * i, 2) for i in range(101)]
    best = next((t for t in grid if stats(tune, t)[1] >= 0.99), 1.0)
    print(f"\nheld-out: field threshold chosen on tune half (>= 99% correct) = {best}")
    print("| half | fields kept | correct among kept | wrong let through | correct thrown away |\n|---|---:|---:|---:|---:|")
    for name, rs in (("tune", tune), ("test", test)):
        n, prec, wrong, lost = stats(rs, best)
        print(f"| {name} | {n}/{len(rs)} | {prec:.1%} | {wrong} | {lost} |")


if __name__ == "__main__":
    main()
