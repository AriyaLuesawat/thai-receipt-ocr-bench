"""Turn OCR text boxes from a Big C receipt into structured fields.

Two extractors are provided so they can be compared:
  - rules:  looks for the label next to each value ("Total", "Cash", "Receipt No", ...)
  - largest_amount: the rule SaiJai's backend uses for slips, which takes the largest
    number with two decimal places as the amount (only produces "total")
"""

import re

FIELDS = ["total", "cash", "change", "receipt_no", "receipt_date", "receipt_time"]

# Common OCR confusions inside numbers.
DIGIT_FIX = str.maketrans({"O": "0", "o": "0", "D": "0", "Q": "0", "l": "1", "I": "1", "|": "1", "S": "5", "B": "8", "Z": "2"})
AMOUNT = re.compile(r"\d{1,3}(?:[,.\s]\d{3})*[.,]\d{2}|\d+[.,]\d{2}")


def to_lines(boxes: list[dict]) -> list[str]:
    """Group boxes whose vertical centres are close into reading-order lines."""
    if not boxes:
        return []
    boxes = sorted(boxes, key=lambda b: (b["y"] + b["h"] / 2, b["x"]))
    lines, current, centre = [], [boxes[0]], boxes[0]["y"] + boxes[0]["h"] / 2
    for box in boxes[1:]:
        c = box["y"] + box["h"] / 2
        if abs(c - centre) <= max(box["h"], current[-1]["h"]) * 0.5:
            current.append(box)
        else:
            lines.append(current)
            current, centre = [box], c
    lines.append(current)
    return [" ".join(b["text"] for b in sorted(line, key=lambda b: b["x"])) for line in lines]


def parse_amount(text: str) -> float | None:
    match = AMOUNT.search(text.translate(DIGIT_FIX))
    if not match:
        return None
    raw = re.sub(r"[\s,]", "", match.group(0))
    # "1.914.00" style: keep the last separator as the decimal point.
    if raw.count(".") > 1:
        head, tail = raw.rsplit(".", 1)
        raw = head.replace(".", "") + "." + tail
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None


def after_label(lines: list[str], pattern: str) -> str | None:
    for line in lines:
        m = re.search(pattern, line, re.IGNORECASE)
        if m:
            return line[m.end():]
    return None


def extract_rules(boxes: list[dict]) -> dict:
    lines = to_lines(boxes)
    text = "\n".join(lines)
    fields: dict = {f: None for f in FIELDS}

    for field, pattern in (("total", r"t[o0]ta[l1i]\s*[:;.]?"), ("cash", r"cash\s*[:;.]?"), ("change", r"chang[e]?\s*[:;.]?")):
        rest = after_label(lines, pattern)
        if rest is not None:
            fields[field] = parse_amount(rest)

    rest = after_label(lines, r"rece[i1l]pt\s*n[o0]\.?\s*[:;.]?")
    if rest is not None:
        m = re.search(r"\d{4,}", rest.translate(DIGIT_FIX))
        fields["receipt_no"] = m.group(0) if m else None

    m = re.search(r"(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})", text.translate(DIGIT_FIX))
    if m:
        fields["receipt_date"] = f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}"

    rest = after_label(lines, r"t[i1l]me\s*[:;.]?")
    if rest is not None:
        m = re.search(r"(\d{1,2})\s*[:.;]\s*(\d{2})", rest.translate(DIGIT_FIX))
        if m:
            fields["receipt_time"] = f"{int(m.group(1)):02d}:{m.group(2)}"
    return fields


def extract_largest_amount(boxes: list[dict]) -> dict:
    amounts = [a for a in (parse_amount(b["text"]) for b in boxes) if a is not None]
    return {"total": max(amounts) if amounts else None}


EXTRACTORS = {"rules": extract_rules, "largest_amount": extract_largest_amount}
