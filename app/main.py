"""HTTP API and demo page for the receipt reader (EXP-016).

  GET  /         upload page (app/static/index.html)
  GET  /health   Tesseract version and whether the Thai model is installed
  POST /read     multipart "file" (JPEG/PNG/WebP, max 10 MB) -> fields with a status each

Images are processed in a temporary directory and deleted after the response; nothing
is stored or logged except timing and the status counts.

Run: .venv/bin/uvicorn app.main:app --port 8000
"""

import logging
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from pipeline import read_receipt  # noqa: E402
from run_tesseract import TESSDATA  # noqa: E402

MAX_BYTES = 10 * 1024 * 1024
MAX_SIDE = 4000
log = logging.getLogger("receipt-api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
app = FastAPI(title="Thai receipt reader", version="0.1.0")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/health")
def health() -> dict:
    try:
        version = subprocess.run(["tesseract", "--version"], capture_output=True, text=True, check=True).stdout.split("\n")[0]
    except (OSError, subprocess.CalledProcessError):
        version = None
    models = all((TESSDATA / f"{lang}.traineddata").exists() for lang in ("tha", "eng"))
    return {"ok": bool(version) and models, "tesseract": version, "thai_model": models}


@app.post("/read")
def read(file: UploadFile) -> dict:
    # A plain def: FastAPI runs it in a worker thread, so a slow OCR call does not block other requests.
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "image larger than 10 MB")
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(415, "not a readable JPEG, PNG or WebP image")
    if max(image.shape[:2]) > MAX_SIDE:
        raise HTTPException(413, f"image side longer than {MAX_SIDE} px")
    start = time.perf_counter()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "receipt.png"
        cv2.imwrite(str(path), image)  # re-encode: Tesseract never sees the uploaded bytes
        try:
            result = read_receipt(path)
        except subprocess.CalledProcessError as e:
            log.error("tesseract failed: %s", e.stderr[-300:] if e.stderr else e)
            raise HTTPException(500, "OCR failed") from None
    counts = {s: sum(v["status"] == s for v in result["fields"].values()) for s in ("verified", "agreed", "needs_review")}
    log.info("read layout=%s seconds=%.2f %s", result["layout"], time.perf_counter() - start, counts)
    return result
