"""Run EasyOCR (Thai + English) on a downloaded split and save the raw text boxes.

Output: results/easyocr/<split>/raw.jsonl with, per image,
  file, receipt_type, seconds, boxes: [{text, conf, x, y, h}]
"""

import argparse
import json
import time
from pathlib import Path

import easyocr

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", default="bigc")
    parser.add_argument("--gpu", action="store_true", help="use GPU/MPS if available")
    args = parser.parse_args()

    data = ROOT / "data" / args.split
    out_dir = ROOT / "results" / "easyocr" / args.split
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "raw.jsonl"
    done = {json.loads(line)["file"] for line in out_path.open(encoding="utf-8")} if out_path.exists() else set()

    reader = easyocr.Reader(["th", "en"], gpu=args.gpu)
    items = [json.loads(line) for line in (data / "labels.jsonl").open(encoding="utf-8")]
    with out_path.open("a", encoding="utf-8") as out:
        for n, item in enumerate(items, 1):
            if item["file"] in done:
                continue
            start = time.perf_counter()
            result = reader.readtext(str(data / "images" / item["file"]), detail=1, paragraph=False)
            seconds = time.perf_counter() - start
            boxes = []
            for box, text, conf in result:
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                boxes.append({"text": text, "conf": round(float(conf), 4), "x": float(min(xs)), "y": float(min(ys)), "h": float(max(ys) - min(ys))})
            out.write(json.dumps({"file": item["file"], "receipt_type": item["receipt_type"], "seconds": round(seconds, 3), "boxes": boxes}, ensure_ascii=False) + "\n")
            out.flush()
            print(f"{n}/{len(items)} {item['file']} {seconds:.1f}s {len(boxes)} boxes")


if __name__ == "__main__":
    main()
