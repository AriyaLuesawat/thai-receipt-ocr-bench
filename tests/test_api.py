"""API tests. The /read test on a real receipt needs the downloaded sample (data/, not in git)."""

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402

client = TestClient(app)


def test_health():
    assert client.get("/health").json()["ok"] is True


def test_index_page():
    r = client.get("/")
    assert r.status_code == 200 and "Thai Receipt Reader" in r.text


def test_rejects_non_image():
    r = client.post("/read", files={"file": ("x.jpg", b"not an image", "image/jpeg")})
    assert r.status_code == 415


def test_rejects_huge_file():
    r = client.post("/read", files={"file": ("x.jpg", b"0" * (10 * 1024 * 1024 + 1), "image/jpeg")})
    assert r.status_code == 413


def test_blank_image_needs_review():
    ok, png = cv2.imencode(".png", np.full((400, 300, 3), 255, np.uint8))
    fields = client.post("/read", files={"file": ("blank.png", png.tobytes(), "image/png")}).json()["fields"]
    assert all(v["status"] == "needs_review" and v["value"] is None for v in fields.values())


def test_clean_bigc_receipt():
    image = ROOT / "data" / "bigc" / "images" / "bigc_02025.jpg"
    if not image.exists():
        pytest.skip("sample not downloaded")
    fields = client.post("/read", files={"file": (image.name, image.read_bytes(), "image/jpeg")}).json()["fields"]
    assert fields["total"]["status"] == "verified"
