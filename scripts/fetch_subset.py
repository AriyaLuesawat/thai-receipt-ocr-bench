"""Download a small, seeded sample of nectec/thairocr through the Hugging Face datasets server.

The full dataset is about 14.6 GB, so this pulls only N receipts per noise level.
Rows in each split are stored in blocks of 1,000 per noise level; the block order
is discovered at run time instead of being hard-coded. For each block it takes one
contiguous window of N rows at a seeded random offset, so each level costs a single
API call (the datasets server rate-limits per-row requests).

Output:
  data/<split>/images/<receipt_type>_<row>.jpg
  data/<split>/labels.jsonl   one JSON object per image: file, row, receipt_type, label
"""

import argparse
import json
import random
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://datasets-server.huggingface.co/rows"
DATASET = "nectec/thairocr"
BLOCK = 1000
ROOT = Path(__file__).resolve().parent.parent


def fetch(url: str, tries: int = 8) -> bytes:
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                return response.read()
        except Exception as error:  # network hiccups and 5xx from the server
            if attempt == tries - 1:
                raise
            wait = min(60, 5 * 2 ** attempt) if "429" in str(error) else 2 ** attempt
            print(f"  retry in {wait}s ({error})")
            time.sleep(wait)
    raise RuntimeError("unreachable")


def get_json(params: dict) -> dict:
    return json.loads(fetch(f"{API}?{urllib.parse.urlencode(params)}"))


def rows(split: str, offset: int, length: int) -> list[dict]:
    data = get_json({"dataset": DATASET, "config": "default", "split": split, "offset": offset, "length": length})
    return data["rows"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", default="bigc", choices=["bigc", "makro", "Bill"])
    parser.add_argument("--per-level", type=int, default=50)
    parser.add_argument("--levels", type=int, default=7, help="number of 1,000-row blocks in the split")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    out = ROOT / "data" / args.split
    (out / "images").mkdir(parents=True, exist_ok=True)
    labels_path = out / "labels.jsonl"
    done = set()
    if labels_path.exists():
        done = {json.loads(line)["row"] for line in labels_path.open(encoding="utf-8")}

    rng = random.Random(args.seed)
    with labels_path.open("a", encoding="utf-8") as labels:
        for block in range(args.levels):
            start = block * BLOCK
            offset = start + rng.randrange(0, BLOCK - args.per_level + 1)
            window = rows(args.split, offset, args.per_level)
            level = window[0]["row"]["receipt_type"]
            print(f"block {block}: {level} — rows {offset}..{offset + len(window) - 1}")
            for i, item in enumerate(window):
                index, row = offset + i, item["row"]
                if index in done:
                    continue
                if row["receipt_type"] != level:
                    raise SystemExit(f"row {index} is {row['receipt_type']}, expected {level}: block layout changed")
                file_name = f"{row['receipt_type']}_{index:05d}.jpg"
                (out / "images" / file_name).write_bytes(fetch(row["image"]["src"]))
                labels.write(json.dumps({"file": file_name, "row": index, "receipt_type": row["receipt_type"], "label": json.loads(row["label"])}, ensure_ascii=False) + "\n")
                labels.flush()
                time.sleep(0.2)
    print(f"saved to {out}")


if __name__ == "__main__":
    main()
