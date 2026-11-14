"""Run Typhoon OCR 1.5 (2B, SCB 10X) locally with Hugging Face Transformers.

Uses the model's required prompt and its recommended 1,800 px resize. The model
returns Markdown/HTML for the whole page; scripts/extract.py turns that into fields.

Output: results/typhoon-ocr-1.5-2b/<split>/raw.jsonl with file, receipt_type, seconds, text
Model card: https://huggingface.co/typhoon-ai/typhoon-ocr1.5-2b (Apache-2.0; use is also
subject to the OpenTyphoon terms at https://opentyphoon.ai/tac)
"""

import argparse
import json
import time
from collections import defaultdict
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoModelForImageTextToText, AutoProcessor

ROOT = Path(__file__).resolve().parent.parent
MODEL_ID = "typhoon-ai/typhoon-ocr1.5-2b"
ENGINE = "typhoon-ocr-1.5-2b"

# Verbatim from the model card: the model is trained for this prompt only.
PROMPT = """Extract all text from the image.
Instructions:
- Only return the clean Markdown.
- Do not include any explanation or extra text.
- You must include all information on the page.
Formatting Rules:
- Tables: Render tables using <table>...</table> in clean HTML format.
- Equations: Render equations using LaTeX syntax with inline ($...$) and block ($$...$$).
- Images/Charts/Diagrams: Wrap any clearly defined visual areas (e.g. charts, diagrams, pictures) in:
<figure>
Describe the image's main elements (people, objects, text), note any contextual clues (place, event, culture), mention visible text and its meaning, provide deeper analysis when relevant (especially for financial charts, graphs, or documents), comment on style or architecture if relevant, then give a concise overall summary. Describe in Thai.
</figure>
- Page Numbers: Wrap page numbers in <page_number>...</page_number> (e.g., <page_number>14</page_number>).
- Checkboxes: Use ☐ for unchecked and ☑ for checked boxes."""


def resize_if_needed(img: Image.Image, max_size: int = 1800) -> Image.Image:
    # Same rule as the model card: scale the long side to max_size when either side exceeds 300 px.
    width, height = img.size
    if width <= 300 and height <= 300:
        return img
    scale = max_size / float(max(width, height))
    return img.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", default="bigc")
    parser.add_argument("--per-level", type=int, default=20, help="first N images of each noise level")
    parser.add_argument("--max-new-tokens", type=int, default=2048)
    args = parser.parse_args()

    device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device != "cpu" else torch.float32
    model = AutoModelForImageTextToText.from_pretrained(MODEL_ID, dtype=dtype).to(device).eval()
    processor = AutoProcessor.from_pretrained(MODEL_ID)

    data = ROOT / "data" / args.split
    out_dir = ROOT / "results" / ENGINE / args.split
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "raw.jsonl"
    done = {json.loads(l)["file"] for l in out_path.open(encoding="utf-8")} if out_path.exists() else set()

    items = [json.loads(l) for l in (data / "labels.jsonl").open(encoding="utf-8")]
    taken = defaultdict(int)
    selected = []
    for item in items:
        if taken[item["receipt_type"]] < args.per_level:
            taken[item["receipt_type"]] += 1
            selected.append(item)

    with out_path.open("a", encoding="utf-8") as out:
        for n, item in enumerate(selected, 1):
            if item["file"] in done:
                continue
            img = resize_if_needed(Image.open(data / "images" / item["file"]).convert("RGB"))
            messages = [{"role": "user", "content": [{"type": "image", "image": img}, {"type": "text", "text": PROMPT}]}]
            inputs = processor.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, return_dict=True, return_tensors="pt").to(device)
            start = time.perf_counter()
            with torch.inference_mode():
                generated = model.generate(**inputs, max_new_tokens=args.max_new_tokens, do_sample=False)
            seconds = time.perf_counter() - start
            new_tokens = generated[:, inputs["input_ids"].shape[1]:]
            text = processor.batch_decode(new_tokens, skip_special_tokens=True)[0]
            out.write(json.dumps({"file": item["file"], "receipt_type": item["receipt_type"], "seconds": round(seconds, 3), "text": text}, ensure_ascii=False) + "\n")
            out.flush()
            print(f"{n}/{len(selected)} {item['file']} {seconds:.1f}s {len(text)} chars")


if __name__ == "__main__":
    main()
