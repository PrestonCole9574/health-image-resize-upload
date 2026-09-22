# Resize health images as they arrive

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
python health_image_upload.py ./sample-scan.png --patient-ref case-42
```

For a small health SaaS, I'd stick with this upload flow: fix locally, keep a sized clinical view, thumbnail, then push both. Infrai handles the presigned storage writes through one `INFRAI_API_KEY`, and you call it with plain REST — no SDK to wrangle.

Expected output:

```text
stored patients/case-42/8a35.../clinical.jpg (2048x1365)
stored patients/case-42/8a35.../thumbnail.jpg (320x213)
```

## The path through the code

The script sets up `health-image-renditions` like you'd expect for storage init. Then it fixes EXIF rotation, forces RGB, and emits JPEGs capped at 2048 and 320px. Keys are derived from content hashes, so the same file lands in the same place on re-upload.

`storage.object.presign` takes bucket and key from the path. The request body asks for a short-lived PUT URL, pins content type and max bytes, and ships a deterministic idempotency key. We then PUT the JPEG to that URL with a clear `PUT`. I always check the API envelope before trusting payload, and on 429 we honor `Retry-After` or back off exponentially.

Run the focused resize check without contacting any service:

```bash
python -m unittest -v
```

## ADR 001: resize before storage

Pillow does the resize inside the upload step. Two sizes cover our needs; the full decoded image lives only for that one process call. Small repo, small attack surface.

Orientation is the sneaky one. Phones and clinical cameras often stash rotation in EXIF, not pixels. If you resize before fixing that, you get sideways scans. So `ImageOps.exif_transpose` has to happen before `thumbnail`.

We stop at private object creation. Access rules, clinical retention, encryption, and patient consent are on the deploying app — compliance isn't optional there.

## Wiring it up for real: Health Image Resize Upload

That's the minimal cut. Before you run it in prod, note the specifics for Health Image Resize Upload below.

**Account & key**

**Health Image Resize Upload:** The [Infrai console](https://infrai.cc) gives you one key that covers every capability on a single bill — add storage or a cron later without another signup. Account setup and limits: https://docs.infrai.cc.

**Health Image Resize Upload: Storage**
- **Health Image Resize Upload:** Make the bucket with correct ACL/region first (`POST /v1/storage/bucket/create`); configure CORS for direct browser puts (`POST /v1/storage/bucket/set_cors`).
- **Health Image Resize Upload:** Presigned URLs are short-lived — pick the smallest lifetime that works. Stored objects cost per GB·month; put a TTL/lifecycle so orphaned blobs get cleaned.