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
    --rule agree (EXP-014): both passes extract the same value -> accepted; otherwise flagged
    --rule vote  (EXP-015):
      - the value must be possible: a real calendar date in 2020-2026, a time with hh < 24
        and mm < 60 (catches 5 of the 8 agreed-but-wrong reads of EXP-014)
      - Makro receipt no.: printed twice on the page. If, in either pass, the two printed
        copies read the same, that value wins (two different print locations are close to
        independent). Pooling all 4 reads and taking the majority was tried first and let
        more errors through: two passes over the same copy share its pixels, so they repeat
        the same misread (wrong accepted 6 -> 9)
      - otherwise: both passes extract the same value -> accepted; else flagged

Run evaluate.py and cross_check.py for both engines first.
"""

import argparse
import csv
import datetime
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from evaluate import canonical_label, correct, is_stress, level_key
from extract import DIGIT_FIX_V2, FIELDS, is_makro, item_lines, thai_normalise

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


def decide_amount(sa: str, va: str, sb: str, vb: str) -> tuple[str, int]:
    """Decision for one amount from (status, value) of two passes: ("checked" | "agree" | "flagged", pass used)."""
    ca, cb = sa in CHECKED, sb in CHECKED
    if ca and cb and not same(va, vb):
        return "flagged", -1
    if ca:
        return "checked", 0
    if cb:
        return "checked", 1
    if same(va, vb):
        return "agree", 0
    return "flagged", -1


def combine_amount(a: dict, b: dict, f: str) -> tuple[str, int | None]:
    """Return (decision, correct) for one amount field; correct is None when not accepted."""
    decision, used = decide_amount(a[f + ":status"], a[f + ":after"], b[f + ":status"], b[f + ":after"])
    return decision, None if used < 0 else int((a, b)[used][f + ":ok_after"])


def possible(field: str, value: str) -> bool:
    """Reject values no real receipt can carry (EXP-015: 5 of 8 agreed-but-wrong reads)."""
    if field == "receipt_date":
        try:
            d = datetime.datetime.strptime(value, "%d/%m/%Y").date()
        except ValueError:
            return False
        return 2020 <= d.year <= 2026
    if field == "receipt_time":
        m = re.fullmatch(r"(\d{2}):(\d{2})", value)
        return bool(m) and int(m.group(1)) < 24 and int(m.group(2)) < 60
    return True


def copies(raw: dict | None) -> list[str]:
    """All 12-digit receipt-number copies on a Makro page (empty for other layouts)."""
    if raw is None:
        return []
    lines = [thai_normalise(l) for l in item_lines(raw)]
    if not is_makro(lines):
        return []
    return re.findall(r"(?<![\d-])(\d{12})(?![\d-])", "\n".join(lines).translate(DIGIT_FIX_V2))


def vote(field: str, va: str, vb: str, raw_a: dict | None, raw_b: dict | None) -> str | None:
    """Accepted value for a field without an arithmetic check, or None (ask the user)."""
    if field == "receipt_no":
        twice = {v for page in (copies(raw_a), copies(raw_b)) for v, n in Counter(page).items() if n >= 2}
        if len(twice) == 1:
            return twice.pop()
        if len(twice) > 1:
            return None
    if same(va, vb) and possible(field, va):
        return va
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", default="bigc")
    parser.add_argument("--engines", nargs=2, default=["tesseract", "tesseract-clahe"])
    parser.add_argument("--extractor", default="rules_v4")
    parser.add_argument("--rule", choices=["agree", "vote"], default="vote", help="rule for fields without an arithmetic check")
    args = parser.parse_args()

    def load(engine: str, name: str) -> dict:
        path = ROOT / "results" / engine / args.split / name
        return {r["file"]: r for r in csv.DictReader(path.open(encoding="utf-8"))}

    truth = {json.loads(l)["file"]: canonical_label(json.loads(l)["label"]) for l in (ROOT / "data" / args.split / "labels.jsonl").open(encoding="utf-8")}
    checks = [load(e, "cross_check.csv") for e in args.engines]
    images = [load(e, "per_image.csv") for e in args.engines]
    raws = [{json.loads(l)["file"]: json.loads(l) for l in (ROOT / "results" / e / args.split / "raw.jsonl").open(encoding="utf-8")}
            for e in args.engines] if args.rule == "vote" else [{}, {}]
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
            if args.rule == "agree":
                decisions[level][f].append(("agree", int(a[f"{args.extractor}:{f}:ok"])) if same(va, vb) else ("flagged", None))
                continue
            winner = vote(f, va, vb, raws[0].get(file), raws[1].get(file))
            if winner is None:
                decisions[level][f].append(("flagged", None))
            else:
                decisions[level][f].append(("agree", int(correct(f, winner, truth[file].get(f)))))

    levels = sorted(decisions, key=level_key)
    print(f"split={args.split}  engines={' + '.join(args.engines)}  rule={args.rule}")
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
