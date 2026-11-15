"""Arithmetic cross-checks on the amounts of a receipt (EXP-010).

A confidence gate cannot catch values OCR misreads *confidently* (Tesseract reads
703.00 as 702.00 with high confidence, EXP-009). The receipt itself has redundancy:

  C1  cash - total = change
  C2  sum of item prices = total      (item lines are read from the OCR text)
  C3  amount before VAT + VAT = total (Makro tax invoices: footer TOTAL row)
  plus two sanity rules: cash >= total, and amounts must be payable (multiples of 0.25 baht)

For each receipt the three amounts (total, cash, change) get one status each:
  confirmed  the value takes part in a check that holds
  repaired   the value was missing or broke a check, and was recomputed from values a
             check confirmed (e.g. total confirmed by C2, so cash = total + change)
  flagged    a check fails and cannot be resolved -> ask the user
  unchecked  not enough values to run any check -> fall back to the confidence gate

Run evaluate.py first; it writes per_image.csv.
Output: results/<engine>/<split>/cross_check.csv and summary tables.
"""

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from evaluate import canonical_label, correct, is_stress, level_key
from extract import (DIGIT_FIX_V2, LABEL_TOKEN_V3, _similar, is_makro, item_lines, makro_item_amounts,
                     makro_vat_row, normalise_digits, thai_normalise)
from quality_gate import field_conf

ROOT = Path(__file__).resolve().parent.parent
AMOUNTS = ["total", "cash", "change"]
TRAILING_AMOUNT = re.compile(r"(\d[\d,]*[.,]\d{2})\s*\S{0,4}\s*$")
# Tesseract sometimes drops the decimal point on item prices ("5200" for "52.00").
# On an item line (starts with a quantity) a bare trailing number of 3+ digits is read as
# having two decimals. A wrong guess only makes C2 fail, so it cannot create a confirmation.
TRAILING_NO_POINT = re.compile(r"^\d{1,2}\s.*\s(\d{3,7})\s*$")
EPS = 0.005


def eq(a: float, b: float) -> bool:
    return abs(a - b) < EPS


def payable(amount: float) -> bool:
    """True if the amount can be paid in Thai currency (smallest coin 0.25 baht)."""
    return abs(amount * 4 - round(amount * 4)) < 0.02


def is_label_line(line: str, label: str) -> bool:
    return any(_similar(re.sub(r"[^a-z]", "", m.group(1)), label) >= 0.6 for m in LABEL_TOKEN_V3.finditer(line.lower()))


def item_amounts(lines: list[str]) -> list[float] | None:
    """Trailing amounts of the lines between the date line and the Total line, or None."""
    start = next((i for i, l in enumerate(lines) if re.search(r"\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{4}", l)), None)
    end = next((i for i, l in enumerate(lines) if start is not None and i > start and is_label_line(l, "total")), None)
    if start is None or end is None:
        return None
    amounts = []
    for line in lines[start + 1:end]:
        fixed = normalise_digits(line).translate(DIGIT_FIX_V2)
        m = TRAILING_AMOUNT.search(fixed)
        if m:
            amounts.append(float(m.group(1).replace(",", "")))
        elif m := TRAILING_NO_POINT.search(fixed):
            amounts.append(int(m.group(1)) / 100)
    return amounts or None


def check(values: dict, items: list[float] | None, conf: dict, vat_total: float | None = None) -> tuple[dict, dict]:
    """Return (final values, status per amount field).

    `items` gives one independent estimate of the total (C2). `vat_total` gives another (C3,
    Makro only): the footer row's total, used only when its own net + VAT adds up.
    """
    t, c, g = values["total"], values["cash"], values["change"]
    witnesses = ([round(sum(items), 2)] if items else []) + ([vat_total] if vat_total is not None else [])
    s = next((w for w in witnesses if t is not None and eq(w, t)), witnesses[0] if witnesses else None)
    out = dict(values)
    status = {f: "unchecked" for f in AMOUNTS}

    c1 = None not in (t, c, g) and eq(c - t, g)
    c2 = s is not None and t is not None and eq(s, t)

    if c1:
        status.update(total="confirmed", cash="confirmed", change="confirmed")
        return out, status

    if c2:
        status["total"] = "confirmed"
        if c is not None and g is not None:
            # C1 fails with total confirmed, so cash or change is wrong. Repair only when exactly
            # one of them is not a payable amount (Thai coins go down to 0.25 baht, so 215.03 is
            # impossible). Otherwise ask the user: picking by OCR confidence was wrong in EXP-010.
            bad = [f for f in ("cash", "change") if not payable(values[f])]
            if len(bad) == 1:
                wrong = bad[0]
                out[wrong] = round(t + g, 2) if wrong == "cash" else round(c - t, 2)
                status[wrong] = "repaired"
                status["change" if wrong == "cash" else "cash"] = "confirmed"
            else:
                status.update(cash="flagged", change="flagged")
        # With only one of cash/change read, nothing checks that value, so it stays unchecked
        # and the missing one is not derived from it. (Until EXP-014 it was marked confirmed
        # and used to derive the other; that let 7 wrong values through on Makro + CLAHE.)
        if out["change"] is not None and out["change"] < -EPS:
            status.update(cash="flagged", change="flagged")
        for f in ("cash", "change"):
            if status[f] == "unchecked" and values[f] is not None and not payable(values[f]):
                status[f] = "flagged"
        return out, status

    s = next((w for w in witnesses if c is not None and g is not None and eq(c - g, w)), s)
    if s is not None and c is not None and g is not None and eq(c - g, s):
        # Total missing or misread, but cash - change matches the items: total = items sum.
        out["total"] = s
        status.update(total="repaired", cash="confirmed", change="confirmed")
        return out, status

    # Some check could run but failed, and nothing resolves it. Also: cash below the total
    # is impossible, even when change is missing and C1 cannot run.
    if None not in (t, c, g) or (witnesses and t is not None) or (t is not None and c is not None and c < t - EPS):
        for f in AMOUNTS:
            if values[f] is not None:
                status[f] = "flagged"
    # An amount paid in cash must be payable (multiple of 0.25 baht). On Makro, a misread
    # label sometimes returns the pre-VAT amount (279.44 instead of 299.00), which this catches.
    for f in AMOUNTS:
        if status[f] == "unchecked" and values[f] is not None and not payable(values[f]):
            status[f] = "flagged"
    return out, status


def receipt_no_status(lines: list[str]) -> str:
    """Makro prints the 12-digit receipt number twice. Both copies equal -> confirmed."""
    copies = re.findall(r"(?<![\d-])(\d{12})(?![\d-])", "\n".join(lines).translate(DIGIT_FIX_V2))
    if len(copies) >= 2:
        return "confirmed" if copies[0] == copies[1] else "flagged"
    return "single"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--engine", default="tesseract")
    parser.add_argument("--split", default="bigc")
    parser.add_argument("--extractor", default="rules_v3")
    parser.add_argument("--conf", type=float, default=0.77, help="per-field confidence threshold for unchecked values (EXP-009)")
    args = parser.parse_args()

    run = ROOT / "results" / args.engine / args.split
    truth = {json.loads(l)["file"]: canonical_label(json.loads(l)["label"]) for l in (ROOT / "data" / args.split / "labels.jsonl").open(encoding="utf-8")}
    per_image = {r["file"]: r for r in csv.DictReader((run / "per_image.csv").open(encoding="utf-8"))}

    rows = []
    for line in (run / "raw.jsonl").open(encoding="utf-8"):
        item = json.loads(line)
        p = per_image[item["file"]]
        words = item.get("words") or [{"text": b["text"], "conf": b["conf"] * 100} for b in item.get("boxes", [])]
        values = {f: float(p[f"{args.extractor}:{f}"]) if p[f"{args.extractor}:{f}"] else None for f in AMOUNTS}
        conf = {f: field_conf(words, f, str(v)) for f, v in values.items() if v is not None}
        lines = [thai_normalise(l) for l in item_lines(item)]
        vat_total = None
        if is_makro(lines):
            items = makro_item_amounts(lines)
            row = makro_vat_row(lines)
            if row and eq(row[0] + row[1], row[2]):  # C3: amount before VAT + VAT = total
                vat_total = row[2]
        else:
            items = item_amounts(item_lines(item))
        final, status = check(values, items, conf, vat_total)
        receipt_status = receipt_no_status(lines) if is_makro(lines) else "unchecked"
        label = truth[item["file"]]
        row = {"file": item["file"], "receipt_type": item["receipt_type"], "n_items_read": len(items or []), "n_items_true": len(label["items"]),
               "vat_check": int(vat_total is not None), "receipt_no:status": receipt_status,
               "receipt_no:ok": int(correct("receipt_no", p[f"{args.extractor}:receipt_no"] or None, label.get("receipt_no")))}
        for f in AMOUNTS:
            # Without a check, fall back to the per-field confidence gate.
            if status[f] == "unchecked" and final[f] is not None:
                status[f] = "unchecked_kept" if conf.get(f, 0) >= args.conf else "unchecked_low_conf"
            row.update({f"{f}:before": values[f], f"{f}:after": final[f], f"{f}:status": status[f],
                        f"{f}:ok_before": int(correct(f, values[f], label.get(f))), f"{f}:ok_after": int(correct(f, final[f], label.get(f)))})
        rows.append(row)

    with (run / "cross_check.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"engine={args.engine}  item lists read completely: {sum(r['n_items_read'] == r['n_items_true'] for r in rows)}/{len(rows)}")

    # 1. Accuracy before and after repair, per level.
    levels = sorted({r["receipt_type"] for r in rows}, key=level_key)
    print("\n| level | " + " | ".join(f"{f} before → after" for f in AMOUNTS) + " |\n|---|" + "---|" * len(AMOUNTS))
    groups = [(l, [l]) for l in levels] + [("READABLE", [l for l in levels if not is_stress(l)])]
    for name, members in groups:
        rs = [r for r in rows if r["receipt_type"] in members]
        cells = [f"{sum(r[f + ':ok_before'] for r in rs) / len(rs):.0%} → {sum(r[f + ':ok_after'] for r in rs) / len(rs):.0%}" for f in AMOUNTS]
        print(f"| {name} | " + " | ".join(cells) + " |")

    # 2. What each status means for trust: share correct, per status.
    print("\n| status | values | correct | wrong |\n|---|---:|---:|---:|")
    by_status = defaultdict(lambda: [0, 0])
    for r in rows:
        for f in AMOUNTS:
            if r[f + ":after"] is not None:
                by_status[r[f + ":status"]][0] += 1
                by_status[r[f + ":status"]][1] += r[f + ":ok_after"]
    for st in ("confirmed", "repaired", "unchecked_kept", "unchecked_low_conf", "flagged"):
        n, ok = by_status.get(st, [0, 0])
        print(f"| {st} | {n} | {ok} | {n - ok} |")

    # Makro prints the receipt number twice (English and Thai header lines): agreement check.
    if any(r["receipt_no:status"] != "unchecked" for r in rows):
        print("\n| receipt no. (printed twice) | receipts | correct |\n|---|---:|---:|")
        for st in ("confirmed", "flagged", "single"):
            rs = [r for r in rows if r["receipt_no:status"] == st]
            print(f"| {st} | {len(rs)} | {sum(r['receipt_no:ok'] for r in rs)} |")
        print(f"VAT row usable (net + VAT = total): {sum(r['vat_check'] for r in rows)}/{len(rows)}")

    # 3. Final policy: accept confirmed, repaired and unchecked_kept; ask the user for the rest.
    accepted = [(r[f + ":ok_after"]) for r in rows for f in AMOUNTS if r[f + ":status"] in ("confirmed", "repaired", "unchecked_kept")]
    asked = sum(1 for r in rows for f in AMOUNTS if r[f + ":status"] in ("flagged", "unchecked_low_conf"))
    missing = sum(1 for r in rows for f in AMOUNTS if r[f + ":after"] is None)
    print(f"\nfinal policy over {len(rows) * 3} amount fields: accepted {len(accepted)} ({sum(accepted)} correct, {len(accepted) - sum(accepted)} wrong), "
          f"asked the user {asked}, not found {missing}")
    print("confirmed-or-repaired per level:", dict(Counter(r["receipt_type"] for r in rows for f in AMOUNTS if r[f + ':status'] in ('confirmed', 'repaired'))))


if __name__ == "__main__":
    main()
