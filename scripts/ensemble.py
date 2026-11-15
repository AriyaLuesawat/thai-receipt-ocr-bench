"""Combine two OCR passes of the same image (EXP-014).

CLAHE helps some images and hurts others (EXP-013), and the two passes make different
mistakes. Instead of picking one preprocessing, read every image twice and let the
checks decide, per field:

  amounts (total, cash, change), using cross_check.csv of each pass:
    1. a value confirmed or repaired by the arithmetic checks in either pass wins
       (if both passes confirm different values, the field is flagged)
    2. otherwise, both passes reading the same value counts as agreement
    3. otherwise the field is flagged and the user is asked
  receipt no., date, time (no arithmetic check exists):
    both passes agree -> accepted; otherwise flagged

Run evaluate.py and cross_check.py for both engines first.
"""

import argparse
import csv
from collections import defaultdict
from pathlib import Path

from evaluate import is_stress, level_key
from extract import FIELDS

ROOT = Path(__file__).resolve().parent.parent
AMOUNTS = ["total", "cash", "change"]
CHECKED = ("confirmed", "repaired")


def same(a: str, b: str) -> bool:
    if not a or not b:
        return False
    try:
        return abs(float(a) - float(b)) < 0.005
    except ValueError:
        return a.strip() == b.strip()


def combine_amount(a: dict, b: dict, f: str) -> tuple[str, int | None]:
    """Return (decision, correct) for one amount field; correct is None when not accepted."""
    ca, cb = a[f + ":status"] in CHECKED, b[f + ":status"] in CHECKED
    va, vb = a[f + ":after"], b[f + ":after"]
    if ca and cb and not same(va, vb):
        return "flagged", None
    if ca:
        return "checked", int(a[f + ":ok_after"])
    if cb:
        return "checked", int(b[f + ":ok_after"])
    if same(va, vb):
        return "agree", int(a[f + ":ok_after"])
    return "flagged", None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", default="bigc")
    parser.add_argument("--engines", nargs=2, default=["tesseract", "tesseract-clahe"])
    parser.add_argument("--extractor", default="rules_v4")
    args = parser.parse_args()

    def load(engine: str, name: str) -> dict:
        path = ROOT / "results" / engine / args.split / name
        return {r["file"]: r for r in csv.DictReader(path.open(encoding="utf-8"))}

    checks = [load(e, "cross_check.csv") for e in args.engines]
    images = [load(e, "per_image.csv") for e in args.engines]
    files = sorted(set(checks[0]) & set(checks[1]))

    # decisions[level][field] -> list of (decision, correct)
    decisions = defaultdict(lambda: defaultdict(list))
    for file in files:
        level = checks[0][file]["receipt_type"]
        for f in AMOUNTS:
            decisions[level][f].append(combine_amount(checks[0][file], checks[1][file], f))
        for f in FIELDS:
            if f in AMOUNTS:
                continue
            a, b = images[0][file], images[1][file]
            va, vb = a[f"{args.extractor}:{f}"], b[f"{args.extractor}:{f}"]
            decisions[level][f].append(("agree", int(a[f"{args.extractor}:{f}:ok"])) if same(va, vb) else ("flagged", None))

    levels = sorted(decisions, key=level_key)
    print(f"split={args.split}  engines={' + '.join(args.engines)}")
    print("Correct and accepted (share of all receipts) / wrong values accepted\n")
    print("| level | " + " | ".join(FIELDS) + " | wrong accepted |\n|---|" + "---:|" * (len(FIELDS) + 1))
    groups = [(l, [l]) for l in levels] + [("READABLE", [l for l in levels if not is_stress(l)]), ("ALL", levels)]
    for name, members in groups:
        cells, wrong = [], 0
        for f in FIELDS:
            ds = [d for l in members for d in decisions[l][f]]
            right = sum(1 for d, ok in ds if ok == 1)
            wrong += sum(1 for d, ok in ds if ok == 0)
            cells.append(f"{right / len(ds):.0%}")
        print(f"| {name} | " + " | ".join(cells) + f" | {wrong} |")

    total = defaultdict(lambda: [0, 0])
    for l in levels:
        for f in FIELDS:
            for d, ok in decisions[l][f]:
                total[d][0] += 1
                total[d][1] += ok or 0
    print("\n| decision | fields | correct |\n|---|---:|---:|")
    for d in ("checked", "agree", "flagged"):
        n, ok = total.get(d, [0, 0])
        print(f"| {d} | {n} | {ok if d != 'flagged' else '-'} |")


if __name__ == "__main__":
    main()
