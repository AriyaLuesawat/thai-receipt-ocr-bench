"""Read one receipt image end to end, with the setup the benchmark found best (EXP-016).

  1. OCR twice with Tesseract: the raw image and a CLAHE contrast-enhanced copy (EXP-013/014)
  2. extract fields with rules v4, which detects the Makro layout (EXP-012)
  3. run the arithmetic checks on each pass (EXP-010)
  4. combine the two passes per field, voting on fields without a check (EXP-014/015)

Every field comes back with a status:
  verified      an arithmetic check that holds includes this value (in either pass)
  agreed        independent reads agree (both passes, or the two printed receipt-number copies)
  needs_review  not enough evidence; `candidates` holds what each pass read, for the user to pick

On the benchmark, `verified` values were 1,050 of 1,051 correct and `agreed` values
1,017 of 1,027 (EXP-015). The rest should be shown to the user, not trusted.

Usage: python pipeline.py IMAGE [IMAGE ...]   (prints JSON)
"""

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from cross_check import AMOUNTS, check_item
from ensemble import decide_amount, vote
from extract import EXTRACTORS, FIELDS, is_makro, item_lines, thai_normalise
from run_tesseract import ocr

PASSES = ("none", "clahe")
STATUS = {"checked": "verified", "agree": "agreed", "flagged": "needs_review"}


def as_cell(value) -> str:
    """The value as per_image.csv / cross_check.csv store it, so the combine rules see the same input."""
    return "" if value is None else str(value)


def combine(passes: list[dict]) -> dict:
    """Combine two already-OCR'd passes ({"text", "words"}) into fields with a status."""
    extracted = [EXTRACTORS["rules_v4"](p) for p in passes]
    checked = [check_item(p, e) for p, e in zip(passes, extracted)]
    fields = {}
    for f in FIELDS:
        reads = [as_cell(e[f]) for e in extracted]
        if f in AMOUNTS:
            (_, fa, sa, _, _, _), (_, fb, sb, _, _, _) = checked
            decision, used = decide_amount(sa[f], as_cell(fa[f]), sb[f], as_cell(fb[f]))
            value = None if used < 0 else (fa, fb)[used][f]
            reads = [as_cell(fa[f]), as_cell(fb[f])]
        else:
            value = vote(f, reads[0], reads[1], passes[0], passes[1])
            decision = "agree" if value else "flagged"
        fields[f] = {"value": float(value) if f in AMOUNTS and value not in (None, "") else (value or None),
                     "status": STATUS[decision],
                     "candidates": sorted({r for r in reads if r})}
    lines = [thai_normalise(l) for l in item_lines(passes[0])]
    return {"layout": "makro" if is_makro(lines) else "slip", "fields": fields}


def read_receipt(image: Path) -> dict:
    start = time.perf_counter()
    # The two Tesseract runs are separate processes, so threads run them in parallel.
    with ThreadPoolExecutor(len(PASSES)) as pool:
        passes = list(pool.map(lambda preprocess: ocr(Path(image), preprocess), PASSES))
    result = combine(passes)
    result["seconds"] = round(time.perf_counter() - start, 2)
    return result


if __name__ == "__main__":
    for path in sys.argv[1:]:
        print(json.dumps({"file": path, **read_receipt(Path(path))}, ensure_ascii=False, indent=2))
