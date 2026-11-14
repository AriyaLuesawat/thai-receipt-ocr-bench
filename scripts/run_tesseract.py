"""Run Tesseract 5 (LSTM, tessdata_best Thai + English) on every image of a split.

A second classic OCR engine to compare with EasyOCR (EXP-007). Tesseract uses a
different detector and recogniser, so it tells us whether the noise4 failure is
EasyOCR-specific or a limit of non-VLM OCR on this data.

Needs: `brew install tesseract`, then tha.traineddata and eng.traineddata from
https://github.com/tesseract-ocr/tessdata_best in data/tessdata/ (or --tessdata).
Output: results/tesseract/<split>/raw.jsonl with file, receipt_type, seconds, text, and
words (each recognised word with Tesseract's 0-100 confidence, used by quality_gate.py)
"""

import argparse
import csv
import json
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", default="bigc")
    parser.add_argument("--tessdata", default=str(ROOT / "data" / "tessdata"))
    parser.add_argument("--psm", default="6", help="page segmentation mode (6 = one uniform block of text)")
    parser.add_argument("--engine-name", default="tesseract", help="results folder name, to keep variants apart")
    args = parser.parse_args()

    data = ROOT / "data" / args.split
    out_dir = ROOT / "results" / args.engine_name / args.split
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "raw.jsonl"
    done = {json.loads(l)["file"] for l in out_path.open(encoding="utf-8")} if out_path.exists() else set()
    items = [json.loads(l) for l in (data / "labels.jsonl").open(encoding="utf-8")]

    with out_path.open("a", encoding="utf-8") as out:
        for n, item in enumerate(items, 1):
            if item["file"] in done:
                continue
            start = time.perf_counter()
            with tempfile.TemporaryDirectory() as tmp:
                # One call writes both the page text and a TSV with per-word confidence.
                subprocess.run(
                    ["tesseract", str(data / "images" / item["file"]), f"{tmp}/out", "-l", "tha+eng", "--psm", args.psm, "--tessdata-dir", args.tessdata, "-c", "tessedit_create_txt=1", "-c", "tessedit_create_tsv=1"],
                    capture_output=True, text=True, check=True,
                )
                text = Path(f"{tmp}/out.txt").read_text(encoding="utf-8")
                with open(f"{tmp}/out.tsv", encoding="utf-8", newline="") as f:
                    words = [
                        {"text": r["text"], "conf": round(float(r["conf"]), 1)}
                        for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
                        if r["level"] == "5" and float(r["conf"]) >= 0 and (r["text"] or "").strip()
                    ]
            seconds = time.perf_counter() - start
            out.write(json.dumps({"file": item["file"], "receipt_type": item["receipt_type"], "seconds": round(seconds, 3), "text": text, "words": words}, ensure_ascii=False) + "\n")
            out.flush()
            if n % 50 == 0:
                print(f"{n}/{len(items)}")


if __name__ == "__main__":
    main()
