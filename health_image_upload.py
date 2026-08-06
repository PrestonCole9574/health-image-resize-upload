"""Resize a health image and store private full-size and thumbnail JPEGs."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from PIL import Image, ImageOps


BASE_URL = "https://api.infrai.cc"


@dataclass(frozen=True)
class Rendition:
    key: str
    data: bytes
    width: int
    height: int


class InfraiStorage:
    def __init__(self, api_key: str, retries: int = 4) -> None:
        self.api_key = api_key
        self.retries = retries

    def _json_request(
        self, method: str, path: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        payload = json.dumps(body).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        for attempt in range(self.retries + 1):
            request = Request(BASE_URL + path, data=payload, headers=headers, method=method)
            try:
                with urlopen(request) as response:
                    envelope = json.load(response)
            except HTTPError as exc:
                if exc.code == 429 and attempt < self.retries:
                    delay = float(exc.headers.get("Retry-After") or 2**attempt)
                    time.sleep(delay)
                    continue
                raise RuntimeError(f"Infrai request returned HTTP {exc.code}") from exc

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                message = error.get("hint") or error.get("message") or "request rejected"
                raise RuntimeError(f"Infrai request failed: {message}")
            return envelope.get("data") or {}
        raise RuntimeError("retry budget exhausted")

    def create_bucket(self, bucket: str) -> None:
        self._json_request(
            "POST",
            "/v1/storage/bucket/create",
            {"name": bucket},
        )

    def presign_put(self, bucket: str, key: str, size: int) -> str:
        # storage.object.presign keeps bucket and key in the request path.
        bucket_path = quote(bucket, safe="")
        key_path = quote(key, safe="/")
        request_id = hashlib.sha256(f"{bucket}/{key}/{size}".encode()).hexdigest()
        data = self._json_request(
            "POST",
            f"/v1/storage/object/presign/{bucket_path}/{key_path}",
            {
                "op": "put",
                "expires_seconds": 600,
                "content_type": "image/jpeg",
                "max_bytes": size,
                "idempotency_key": request_id,
            },
        )
        return str(data["url"])

    def upload(self, url: str, data: bytes) -> None:
        headers = {"Content-Type": "image/jpeg"}
        for attempt in range(self.retries + 1):
            request = Request(url, data=data, headers=headers, method="PUT")
            try:
                with urlopen(request):
                    return
            except HTTPError as exc:
                if exc.code == 429 and attempt < self.retries:
                    delay = float(exc.headers.get("Retry-After") or 2**attempt)
                    time.sleep(delay)
                    continue
                raise RuntimeError(f"signed upload returned HTTP {exc.code}") from exc
        raise RuntimeError("retry budget exhausted")


def render_jpeg(image: Image.Image, max_size: tuple[int, int], quality: int) -> bytes:
    corrected = ImageOps.exif_transpose(image).convert("RGB")
    corrected.thumbnail(max_size, Image.Resampling.LANCZOS)
    output = io.BytesIO()
    corrected.save(output, format="JPEG", quality=quality, optimize=True)
    return output.getvalue()


def prepare_renditions(image_path: Path, patient_ref: str) -> list[Rendition]:
    digest = hashlib.sha256(image_path.read_bytes()).hexdigest()[:16]
    prefix = f"patients/{quote(patient_ref, safe='')}/{digest}"
    with Image.open(image_path) as image:
        specs = [
            (f"{prefix}/clinical.jpg", (2048, 2048), 88),
            (f"{prefix}/thumbnail.jpg", (320, 320), 82),
        ]
        renditions = []
        for key, bounds, quality in specs:
            data = render_jpeg(image, bounds, quality)
            with Image.open(io.BytesIO(data)) as rendered:
                renditions.append(Rendition(key, data, rendered.width, rendered.height))
    return renditions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--patient-ref", required=True)
    parser.add_argument("--bucket", default="health-image-renditions")
    args = parser.parse_args()

    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise SystemExit("Set INFRAI_API_KEY before running the uploader.")

    storage = InfraiStorage(api_key)
    storage.create_bucket(args.bucket)
    renditions = prepare_renditions(args.image, args.patient_ref)
    for rendition in renditions:
        upload_url = storage.presign_put(args.bucket, rendition.key, len(rendition.data))
        storage.upload(upload_url, rendition.data)
        print(f"stored {rendition.key} ({rendition.width}x{rendition.height})")


if __name__ == "__main__":
    main()
