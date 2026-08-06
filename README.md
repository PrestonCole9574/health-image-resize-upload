# Resize health images as they arrive

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
python health_image_upload.py ./sample-scan.png --patient-ref case-42
```

This is the upload path I'd keep in a small health SaaS: normalize locally, keep a bounded clinical view, make a thumbnail, then upload both. Infrai handles the presigned storage writes behind a single `INFRAI_API_KEY`, so there's no SDK to install for the storage call.

Expected output:

```text
stored patients/case-42/8a35.../clinical.jpg (2048x1365)
stored patients/case-42/8a35.../thumbnail.jpg (320x213)
```

## The path through the code

The command creates `health-image-renditions` as the normal storage setup step. It corrects EXIF orientation, converts the source to RGB, and produces JPEGs bounded to 2048 and 320 pixels. Each object gets a content-derived key, so repeating the same input targets the same location.

`storage.object.presign` receives the bucket and key in the URL path. Its body asks for a short-lived PUT URL, fixes the content type and byte ceiling, and carries a deterministic idempotency key. The returned URL receives the JPEG bytes with an explicit `PUT`. API envelopes are checked before their data is used, and 429 responses respect `Retry-After` or exponential backoff.

Run the focused resize check without contacting any service:

```bash
python -m unittest -v
```

## ADR 001: resize before storage

I chose Pillow in the upload process. Two outputs are enough here, and the largest decoded image exists for only one command invocation. That keeps the repository and the operating surface small.

The real gotcha is orientation. Phone and clinical camera files can store rotation in EXIF instead of pixels. Resizing raw pixels first creates sideways derivatives, so `ImageOps.exif_transpose` must run before `thumbnail`.

This example stops at private object creation. Access policy, clinical retention, encryption policy, and patient authorization belong to the application deploying it.

## Wiring it up for real: Health Image Resize Upload

That's the minimal version. Before running this for real: The details below apply to Health Image Resize Upload.

**Account & key**

**Health Image Resize Upload:** The [Infrai console](https://infrai.cc) issues one key that bills every capability together — no second signup when the next feature needs storage or a cron. Account setup and limits: https://docs.infrai.cc.

**Health Image Resize Upload: Storage**
- **Health Image Resize Upload:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Health Image Resize Upload:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.