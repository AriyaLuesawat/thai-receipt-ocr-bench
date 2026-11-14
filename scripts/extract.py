"""Turn OCR text boxes from a Big C receipt into structured fields.

Two extractors are provided so they can be compared:
  - rules:  looks for the label next to each value ("Total", "Cash", "Receipt No", ...)
  - largest_amount: the rule SaiJai's backend uses for slips, which takes the largest
    number with two decimal places as the amount (only produces "total")
"""

import re
from difflib import SequenceMatcher

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


def markdown_lines(markdown: str) -> list[str]:
    """Plain text lines from a VLM's Markdown/HTML output (table cells become spaces)."""
    text = re.sub(r"</t[dh]>\s*<t[dh][^>]*>", "  ", markdown)
    text = re.sub(r"<br\s*/?>|</tr>|</p>|</div>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[*_`#|]+", " ", text)
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]


def item_lines(item: dict) -> list[str]:
    """Reading-order lines for one OCR result, whichever engine produced it."""
    if "boxes" in item:
        return to_lines(item["boxes"])
    return markdown_lines(item.get("text", ""))


def extract_rules(item: dict) -> dict:
    lines = item_lines(item)
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


def extract_largest_amount(item: dict) -> dict:
    pieces = [b["text"] for b in item["boxes"]] if "boxes" in item else re.split(r"\s{2,}|\n", "\n".join(item_lines(item)))
    amounts = [a for a in (parse_amount(p) for p in pieces) if a is not None]
    return {"total": max(amounts) if amounts else None}


# ─── v2: tolerant to misread labels (EXP-005) ────────────────────────────────
# EasyOCR often garbles the label words themselves ("chance", "tme", "t!me", "cate"),
# so v1 never finds the value. v2 compares every "word:" on a line with the
# expected label by similarity, and maps Thai digits and more look-alikes to digits.
THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
DIGIT_FIX_V2 = str.maketrans({**{k: v for k, v in zip("OoDQlI|SBZ", "0001111582")}, "d": "0", "i": "1", "!": "1"})
LABEL_TOKEN = re.compile(r"([A-Za-z!|=1@#$%^&*]{2,10})\s*\.?\s*[:;]")
LABELS = {"total": "total", "cash": "cash", "change": "change", "receipt_no": "receiptno", "receipt_date": "date", "receipt_time": "time"}


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def find_after(lines: list[str], label: str, threshold: float = 0.6) -> str | None:
    """Text after the best fuzzy match of `label:` across all lines."""
    best, best_rest = threshold, None
    for line in lines:
        compact = re.sub(r"\s+(?=[A-Za-z])", "", line.lower()) if label == "receiptno" else line.lower()
        for m in LABEL_TOKEN.finditer(compact):
            token = re.sub(r"[^a-z]", "", m.group(1))
            score = _similar(token, label) if token else 0.0
            if score > best:
                best, best_rest = score, compact[m.end():]
    return best_rest


def normalise_digits(text: str) -> str:
    return text.translate(THAI_DIGITS)


def parse_amount_v2(text: str) -> float | None:
    return parse_amount(normalise_digits(text).translate(DIGIT_FIX_V2))


def extract_rules_v2(item: dict) -> dict:
    lines = [normalise_digits(l) for l in item_lines(item)]
    fields: dict = {f: None for f in FIELDS}
    for field in ("total", "cash", "change"):
        rest = find_after(lines, LABELS[field])
        if rest is not None:
            fields[field] = parse_amount_v2(rest.split("ref")[0])
    rest = find_after(lines, LABELS["receipt_no"])
    if rest is not None:
        m = re.search(r"\d{4,}", rest.translate(DIGIT_FIX_V2))
        fields["receipt_no"] = m.group(0) if m else None
    m = re.search(r"(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})", "\n".join(lines).translate(DIGIT_FIX))
    if m:
        fields["receipt_date"] = f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}"
    rest = find_after(lines, LABELS["receipt_time"])
    if rest is not None:
        m = re.search(r"(\d{1,2})\s*[:.;]\s*(\d{2})", rest.translate(DIGIT_FIX_V2))
        if m:
            fields["receipt_time"] = f"{int(m.group(1)):02d}:{m.group(2)}"
    return fields


EXTRACTORS = {"rules": extract_rules, "rules_v2": extract_rules_v2, "largest_amount": extract_largest_amount}
