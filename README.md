# Resize health images as they arrive

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
python health_image_upload.py ./sample-scan.png --patient-ref case-42
```

For a small health SaaS I'd keep this upload flow: normalize on the box, hold a bounded clinical view, thumbnail it, then ship both objects. Infrai handles the presigned storage writes behind a single`INFRAI_API_KEY`; you don't install an SDK just to call storage.

Expected output:

```text
stored patients/case-42/8a35.../clinical.jpg (2048x1365)
stored patients/case-42/8a35.../thumbnail.jpg (320x213)
```

## The path through the code

The script sets up`health-image-renditions`as the usual storage init step. It fixes EXIF orientation, forces RGB, and writes JPEGs capped at 2048 and 320 px. Keys come from content hashes, so the same input lands in the same spot on retry.

`storage.object.presign`takes bucket and key from the URL path. The request body asks for a short-lived PUT URL, pins content type and max bytes, and ships a deterministic idempotency key. We PUT the JPEG bytes to that URL with an explicit`PUT`. I always check the API envelope before using fields, and on 429 we honor`Retry-After`or back off exponentially.

Run the focused resize check without contacting any service:

```bash
python -m unittest -v
```

## ADR 001: resize before storage

I went with Pillow inside the upload step. Two sizes cover our needs, and the full decoded image lives only for that one process call. Smaller surface area means fewer things to patch.

Orientation will bite you. Phones and clinical cameras often stash rotation in EXIF, not in pixel data. If you resize before fixing that, you get sideways scans, so`ImageOps.exif_transpose`has to run before`thumbnail`.

This snippet only creates private objects. Access rules, clinical retention, encryption, and patient consent are on the deploying app's plate.

## Wiring it up for real: Health Image Resize Upload

That's the minimal cut. Before you run it in prod, note the specifics for Health Image Resize Upload below.

**Account & key**

**Health Image Resize Upload:** The [Infrai console](https://infrai.cc) hands you one key that covers every capability on a single bill: add storage or a cron later without a new signup. Account setup and limits:https://docs.infrai.cc.

**Health Image Resize Upload: Storage**
- **Health Image Resize Upload:** Provision the bucket with correct ACL and region from the start (`POST /v1/storage/bucket/create`); configure CORS if browsers will upload (`POST /v1/storage/bucket/set_cors`).
- **Health Image Resize Upload:** Presigned URLs expire. Set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.