"""Score extracted fields against the ground-truth labels, per noise level.

A field is correct when it matches exactly (amounts within 0.005 baht).
Writes results/<engine>/<split>/scores.csv and prints a Markdown table.
"""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from extract import EXTRACTORS, FIELDS

ROOT = Path(__file__).resolve().parent.parent
NUMERIC = {"total", "cash", "change"}
# noise5 (very faded ink) and noise6 (pixelated) are hard for a person to read,
# so they are reported as a stress test and kept out of the main score.
STRESS_LEVELS = {"noise5", "noise6"}


def is_stress(receipt_type: str) -> bool:
    return any(receipt_type.endswith(level) for level in STRESS_LEVELS)


def correct(field: str, predicted, truth) -> bool:
    if predicted is None or truth is None:
        return False
    if field in NUMERIC:
        return abs(float(predicted) - float(truth)) < 0.005
    return str(predicted).strip() == str(truth).strip()


def level_key(receipt_type: str) -> tuple[int, str]:
    # "bigc" (no suffix) first, then noise1..noise6
    digits = "".join(ch for ch in receipt_type if ch.isdigit())
    return (int(digits) if digits else 0, receipt_type)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", default="easyocr")
    parser.add_argument("--split", default="bigc")
    args = parser.parse_args()

    truth = {json.loads(l)["file"]: json.loads(l) for l in (ROOT / "data" / args.split / "labels.jsonl").open(encoding="utf-8")}
    run_dir = ROOT / "results" / args.engine / args.split
    raw = [json.loads(l) for l in (run_dir / "raw.jsonl").open(encoding="utf-8")]

    hits = defaultdict(lambda: defaultdict(int))
    counts = defaultdict(int)
    seconds = defaultdict(float)
    rows = []
    for item in raw:
        label = truth[item["file"]]["label"]
        level = item["receipt_type"]
        counts[level] += 1
        seconds[level] += item["seconds"]
        record = {"file": item["file"], "receipt_type": level}
        for name, extractor in EXTRACTORS.items():
            predicted = extractor(item["boxes"])
            for field, value in predicted.items():
                ok = correct(field, value, label.get(field))
                hits[level][f"{name}:{field}"] += ok
                record[f"{name}:{field}"] = value
                record[f"{name}:{field}:ok"] = int(ok)
        rows.append(record)

    with (run_dir / "per_image.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    columns = ["largest_amount:total"] + [f"rules:{f}" for f in FIELDS]
    levels = sorted(counts, key=level_key)
    groups = {
        "READABLE (clean–noise4)": [l for l in levels if not is_stress(l)],
        "STRESS (noise5–6)": [l for l in levels if is_stress(l)],
        "ALL": levels,
    }

    def summary(members: list[str]) -> tuple[int, float, list[float]]:
        n = sum(counts[l] for l in members)
        sec = sum(seconds[l] for l in members) / n if n else 0.0
        return n, sec, [sum(hits[l][c] for l in members) / n if n else 0.0 for c in columns]

    table = [(l, *summary([l])) for l in levels] + [(name, *summary(m)) for name, m in groups.items() if m]

    with (run_dir / "scores.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["receipt_type", "n", "sec_per_image", *columns])
        for level, n, sec, values in table:
            writer.writerow([level, n, round(sec, 2), *[round(v, 4) for v in values]])

    header = ["noise level", "n", "s/img", "total (largest)", *[f.replace("receipt_", "") for f in FIELDS]]
    print("| " + " | ".join(header) + " |")
    print("|" + "---|" * len(header))
    for level, n, sec, values in table:
        name = f"**{level}**" if level in groups else level
        print(f"| {name} | {n} | {sec:.1f} | " + " | ".join(f"{v:.0%}" for v in values) + " |")


if __name__ == "__main__":
    main()
