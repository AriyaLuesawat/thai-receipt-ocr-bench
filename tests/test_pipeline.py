"""Tests for the checks, the vote and the end-to-end pipeline.

The unit tests need no data. The consistency test needs the benchmark outputs
(data/<split>/labels.jsonl and results/tesseract*/<split>/raw.jsonl, not in git) and is
skipped without them: it proves the per-image pipeline used by the API makes exactly the
decisions that the benchmark scripts scored.
"""

import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from cross_check import check, payable  # noqa: E402
from ensemble import combine_amount, possible, vote  # noqa: E402
from pipeline import combine  # noqa: E402


def test_c1_confirms_all_three():
    _, status = check({"total": 299.0, "cash": 440.0, "change": 141.0}, None, {})
    assert status == {"total": "confirmed", "cash": "confirmed", "change": "confirmed"}


def test_items_confirm_total_but_not_a_lone_cash_value():
    # EXP-014 bug: cash must stay unchecked when change was not read.
    _, status = check({"total": 52.0, "cash": 100.0, "change": None}, [20.0, 32.0], {})
    assert status["total"] == "confirmed"
    assert status["cash"] == "unchecked"


def test_unpayable_value_is_repaired_from_confirmed_total():
    out, status = check({"total": 52.0, "cash": 100.03, "change": 48.0}, [52.0], {})
    assert status["cash"] == "repaired" and out["cash"] == 100.0


def test_cash_below_total_is_flagged():
    _, status = check({"total": 300.0, "cash": 200.0, "change": None}, None, {})
    assert status["total"] == status["cash"] == "flagged"


def test_payable():
    assert payable(10.25) and payable(0.0) and not payable(279.44)


def test_possible_dates_and_times():
    assert possible("receipt_date", "23/09/2025")
    assert not possible("receipt_date", "23/09/2075")
    assert not possible("receipt_date", "00/09/2025")
    assert not possible("receipt_time", "00:93")
    assert possible("receipt_time", "20:21")


def test_vote_needs_agreement():
    assert vote("receipt_date", "02/10/2025", "02/10/2025", None, None) == "02/10/2025"
    assert vote("receipt_date", "02/10/2025", "02/10/2026", None, None) is None
    assert vote("receipt_date", "02/10/2075", "02/10/2075", None, None) is None


@pytest.mark.parametrize("split", ["bigc", "makro"])
def test_pipeline_matches_benchmark(split):
    runs = [ROOT / "results" / e / split for e in ("tesseract", "tesseract-clahe")]
    if not all((r / "raw.jsonl").exists() for r in runs):
        pytest.skip("benchmark OCR outputs not present")
    raws = [{json.loads(l)["file"]: json.loads(l) for l in (r / "raw.jsonl").open(encoding="utf-8")} for r in runs]
    checks = [{r["file"]: r for r in csv.DictReader((run / "cross_check.csv").open(encoding="utf-8"))} for run in runs]
    for file in raws[0]:
        result = combine([raws[0][file], raws[1][file]])["fields"]
        for f in ("total", "cash", "change"):
            decision, _ = combine_amount(checks[0][file], checks[1][file], f)
            expected = {"checked": "verified", "agree": "agreed", "flagged": "needs_review"}[decision]
            assert result[f]["status"] == expected, (file, f)


@pytest.mark.parametrize("split,wrong_expected", [("bigc", 3), ("makro", 8)])
def test_pipeline_reproduces_exp015_wrong_count(split, wrong_expected):
    """Accepted values from the pipeline, scored against the labels, give EXP-015's numbers."""
    from evaluate import canonical_label, correct

    runs = [ROOT / "results" / e / split for e in ("tesseract", "tesseract-clahe")]
    if not all((r / "raw.jsonl").exists() for r in runs):
        pytest.skip("benchmark OCR outputs not present")
    truth = {json.loads(l)["file"]: canonical_label(json.loads(l)["label"]) for l in (ROOT / "data" / split / "labels.jsonl").open(encoding="utf-8")}
    raws = [{json.loads(l)["file"]: json.loads(l) for l in (r / "raw.jsonl").open(encoding="utf-8")} for r in runs]
    wrong = 0
    for file in raws[0]:
        for f, v in combine([raws[0][file], raws[1][file]])["fields"].items():
            if v["status"] != "needs_review":
                wrong += not correct(f, v["value"], truth[file].get(f))
    assert wrong == wrong_expected
