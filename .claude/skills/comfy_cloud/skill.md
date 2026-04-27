---
name: comfy_cloud
description: Generate images and videos via Comfy Cloud (cloud.comfy.org) instead of a local server. Use when the user wants to run ComfyUI workflows on cloud infrastructure, or when local GPU isn't available.
argument-hint: [prompt or description of what to generate]
allowed-tools: Bash, Read, Write, Glob, Grep, Agent, WebFetch
---

# ComfyUI Cloud Skill

You interact with the **Comfy Cloud** API at `https://cloud.comfy.org` to run ComfyUI workflows on cloud GPUs. Workflow JSON is identical to local — only auth, polling, downloads, and a few endpoint paths differ.

## Read These First

This skill covers only what's cloud-specific. **Before doing any pipeline work, also read:**
- `.claude/skills/comfy_workflows/skill.md` — workflow API format, model discovery (with the COMBO+legacy unwrap helper), proven pipelines (Z-Image Turbo, LTX 2.3 i2v + t2v, Wan 2.2 t2v), batch pattern, file naming, 24fps default. **The workflow JSON is identical between local and cloud — that skill is the source of truth.**
- `.claude/skills/lora_tester/skill.md` — for any LoRA testing/comparison task, use `lora_test_cloud.py`.

## Auth & Setup

All requests require `X-API-Key: <key>` header. The key is in `.env` as `COMFY_API_KEY` (same key used for partner nodes' `api_key_comfy_org`). **NEVER commit or log the key.**

```python
api_key = open("C:/code/lora_tester/.env").read().split("COMFY_API_KEY=")[1].strip().split("\n")[0]
HEADERS = {"X-API-Key": api_key}
```

Account info:
- **Tier:** Pro (5 concurrent jobs)
- Generate keys at https://platform.comfy.org/profile/api-keys

## Cloud API Endpoints

`BASE = "https://cloud.comfy.org"`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/prompt` | POST | Submit a workflow `{"prompt": {...}}` → `{"prompt_id": "<uuid>"}` |
| `/api/job/{id}/status` | GET | Cheap poll: `{id, status, ...}` — see status-enum gotcha below |
| `/api/jobs/{id}` | GET | Full job details + outputs (call after status terminal) |
| `/api/history_v2/{id}` | GET | Alt route for full history (matches local `/history/{id}`) |
| `/api/object_info` | GET | All node defs (3,400+ on cloud). **Wrapped COMBO format** |
| `/api/experiment/models` | GET | List of model folders |
| `/api/experiment/models/{folder}` | GET | List of models in a folder (no COMBO wrapper) |
| `/api/global_subgraphs` | GET | 31 prefab subgraph blueprints — see `comfy_workflows` |
| `/api/global_subgraphs/{id}` | GET | Full JSON for one subgraph |
| `/api/upload/image` | POST | Multipart image upload (50MB max, 64MP max) |
| `/api/view?filename=...` | GET | **Returns 302 → signed GCS URL** — pass header, follow redirect |
| `/api/queue` | GET / POST | View queue / cancel pending jobs |
| `/api/interrupt` | POST | Interrupt running jobs |
| `/api/system_stats` | GET | Cloud version, no GPU info (`devices: []`) |
| `/api/user` | GET | `{id, status}` |
| `/api/assets` | POST | Upload custom asset (lora, model, etc.) — see "Custom Assets" |
| `/api/assets/download` | POST | Cloud pulls a file from HuggingFace/CivitAI server-side |

## Cloud Gotchas (Things That Will Bite You)

1. **Auth header on every request** including `/api/view` downloads.
2. **Job status: two endpoints, two enums** — the OpenAPI spec is wrong about both. **Observed actual behavior:**
   - `/api/job/{id}/status` (lifecycle, cheap) transient values seen: `queued_limited`, `queued_waiting`, `preparing`, `preprocessing`, `allocated`, `executing`. Terminal: **`success`**, plus `error`, `failed`, `cancelled`.
   - `/api/jobs/{id}` (full detail) returns: `status: "completed"` for the same successful job. **NOT `success`.**
   - Treat **both `success` and `completed`** as terminal-OK. Treat `error`, `failed`, `cancelled` as terminal-fail. Anything else is transient — keep polling. Outputs only appear in `/api/jobs/{id}` once the job is terminal.
3. **`/api/view` returns 302 → signed URL.** When using `urllib`, follow redirects (default behavior) but pass the header. With `curl`, use `-L`.
4. **`subfolder` and `overwrite` are silently ignored** on uploads/views — cloud uses content-addressed (hash-based) storage.
5. **Output `filename` is a Blake3 content hash, not your `filename_prefix`.** SaveImage's `filename_prefix` is preserved in the output's `display_name` field; the actual `filename` is something like `ad80ae50e4e49a3d6fb...png`. **For `/api/view` you must pass the hash filename** (that's the cloud-side ID). **When saving locally, always use `display_name`** — the hash filename is an ugly byproduct of content-addressed storage and shouldn't end up on the user's disk. Fall back to `filename` only if `display_name` is missing. Example output structure:
   ```json
   "outputs": {"11": {"images": [{
     "filename": "ad80ae50e4e49a3d6fb...png",
     "display_name": "20260426_cloud-smoke-tree_00001_.png",
     "subfolder": "", "type": "output"
   }]}}
   ```
6. **`SaveVideo` MP4s come back under the `images` key**, not `video`. They have an `animated: [true]` flag. Iterate `images + video + gifs` to be safe.
7. **`display_name` may contain a subfolder** (e.g. `video/20260426_foo.mp4`). Always `os.makedirs(os.path.dirname(dest), exist_ok=True)` before opening the file or the write fails.
8. **Concurrency: 5 jobs run in parallel** (Pro tier). Submitting more is fine — they queue.
9. **Cloud has a different (much larger) model set than local.** Your local custom loras are NOT on cloud. Always discover via API; never hardcode model names from local.
10. **No GPU info** — `system_stats` returns `devices: []`. Don't rely on it for VRAM checks.
11. **COMBO format is the wrapped version** (`["COMBO", {"options": [...]}]`), unlike local's legacy nested-list. Use the `widget_options()` helper from `comfy_workflows` — it handles both.

## Submitting Workflows

```python
import json, urllib.request

CLOUD = "https://cloud.comfy.org"

def submit(workflow, extra_data=None):
    body = {"prompt": workflow}
    if extra_data:
        body["extra_data"] = extra_data
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(f"{CLOUD}/api/prompt", data=payload,
        headers={**HEADERS, "Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())  # {"prompt_id": "<uuid>", ...}
```

For partner API nodes (Nano Banana 2, Gemini, Flux Pro, Kling, ByteDance, etc.) pass the same key in `extra_data`:
```python
submit(wf, extra_data={"api_key_comfy_org": api_key})
```

## Polling (Single Job)

```python
import time
TERMINAL_OK   = {"success", "completed"}
TERMINAL_FAIL = {"error", "failed", "cancelled"}
TERMINAL = TERMINAL_OK | TERMINAL_FAIL

def wait_for_job(prompt_id, timeout=240, interval=2):
    """Cheap status-only poll. Lifecycle: queued_* -> preparing -> executing -> success."""
    start = time.time()
    while time.time() - start < timeout:
        req = urllib.request.Request(f"{CLOUD}/api/job/{prompt_id}/status", headers=HEADERS)
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read())
        if data["status"] in TERMINAL:
            return data["status"], data
        time.sleep(interval)
    raise TimeoutError(f"Job {prompt_id} timed out after {timeout}s")

def get_job_outputs(prompt_id):
    """Call after status is terminal to harvest outputs dict."""
    req = urllib.request.Request(f"{CLOUD}/api/jobs/{prompt_id}", headers=HEADERS)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())  # has "outputs" dict keyed by node_id
```

## Polling (Batch — Pro Tier 5 Concurrent)

Submit all upfront; cloud's fair scheduler runs 5 at a time. Poll status (not full jobs) to keep traffic light. The general batch pattern is in `comfy_workflows` — cloud-specific bit:

```python
done = {}  # pid -> status
while len(done) < len(prompt_ids):
    for pid in prompt_ids:
        if pid in done: continue
        try:
            req = urllib.request.Request(f"{CLOUD}/api/job/{pid}/status", headers=HEADERS)
            with urllib.request.urlopen(req) as r:
                d = json.loads(r.read())
            if d["status"] in TERMINAL:
                done[pid] = d["status"]
        except Exception as e:
            print(f"  WARN: status check {pid}: {e}")
    if len(done) % 5 == 0 and done:
        print(f"  Progress: {len(done)}/{len(prompt_ids)}")
    if len(done) < len(prompt_ids):
        time.sleep(3)
```

For each completed pid, call `/api/jobs/{pid}` once to harvest outputs.

## Downloading Outputs

`/api/view` returns a **302 redirect to a GCS signed URL**. `urllib.request.urlopen` follows redirects automatically and the header is passed through; `curl` needs `-L`.

```python
import os, urllib.parse

def download_output(cloud_filename, dest_path, subfolder="", file_type="output"):
    """cloud_filename = the hash filename (used to look up the file).
    dest_path = where to save it locally — derive from display_name for readability."""
    q = urllib.parse.urlencode({
        "filename": cloud_filename, "subfolder": subfolder, "type": file_type})
    req = urllib.request.Request(f"{CLOUD}/api/view?{q}", headers=HEADERS)
    with urllib.request.urlopen(req) as r:
        with open(dest_path, "wb") as f:
            f.write(r.read())

# Iterate outputs and save with display_name (human-readable)
job = get_job_outputs(pid)
for node_out in (job.get("outputs") or {}).values():
    for media in node_out.get("images", []) + node_out.get("video", []) + node_out.get("gifs", []):
        cloud_fn = media["filename"]                          # hash, used for /api/view
        local_fn = media.get("display_name") or cloud_fn       # human-readable for disk
        dest = os.path.join("cloud_outputs", local_fn)
        os.makedirs(os.path.dirname(dest), exist_ok=True)      # display_name may have a subfolder
        download_output(cloud_fn, dest,
            subfolder=media.get("subfolder", ""),
            file_type=media.get("type", "output"))
```

**Convention:** place downloaded files under `cloud_outputs/` at the project root so they don't mix with local `output/` from the local skill.

## Uploading Input Images

```python
def upload_image(file_path):
    """Upload an input image. Returns the cloud-side filename to reference in workflows."""
    import io, mimetypes, uuid
    boundary = uuid.uuid4().hex
    body = io.BytesIO()
    fname = os.path.basename(file_path)
    mime = mimetypes.guess_type(fname)[0] or "application/octet-stream"

    body.write(f'--{boundary}\r\n'.encode())
    body.write(f'Content-Disposition: form-data; name="image"; filename="{fname}"\r\n'.encode())
    body.write(f'Content-Type: {mime}\r\n\r\n'.encode())
    body.write(open(file_path, "rb").read())
    body.write(f'\r\n--{boundary}\r\n'.encode())
    body.write(b'Content-Disposition: form-data; name="type"\r\n\r\noutput\r\n')
    body.write(f'--{boundary}--\r\n'.encode())

    req = urllib.request.Request(f"{CLOUD}/api/upload/image",
        data=body.getvalue(),
        headers={**HEADERS, "Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["name"]  # use this in LoadImage nodes
```

Image limits: **50 MB, 16384 px per edge, 64 megapixels total.**

## Custom Assets (Loras / Models You Want On Cloud)

For local custom loras (e.g. `zit-c64.safetensors`) that aren't pre-loaded on cloud, two upload paths:

### Option A: Direct upload via Assets API
```
POST /api/assets
  multipart fields: file, name, tags=["models", "lora"], mime_type
```
Returns `AssetCreated`. Tag with `"models"` so it appears in model loaders. Hash-based dedup means re-uploads of identical content are no-ops.

### Option B: Server-side download from HuggingFace/CivitAI
```
POST /api/assets/download
  json: {"source_url": "https://huggingface.co/.../resolve/main/file.safetensors",
         "tags": ["models", "lora"]}
```
Cloud pulls the file directly — no local bandwidth needed. Returns `202` + `task_id`; poll `/api/tasks/{task_id}` for progress. If the file's hash already exists, returns `200` immediately.

**This skill does NOT auto-upload.** If a workflow references a lora that isn't on cloud, the API returns a validation error. Surface it to the user with the list of available loras (from `widget_options(oi["LoraLoader"], "lora_name")`) and let them decide on upload strategy.

## Cloud Error Handling

Cloud-specific HTTP codes:

| Code | Meaning | What to do |
|------|---------|------------|
| 401 | Invalid / missing X-API-Key | Check `.env` |
| 402 | Insufficient credits | User needs to top up |
| 403 | Job belongs to another user | Wrong key or wrong ID |
| 429 | Subscription inactive | User needs to reactivate |
| 400 | Validation error in workflow | Read body — `node_errors` dict |

Execution-time error types (in `execution_error.exception_type`):
- `ValidationError` — bad workflow/inputs
- `ModelDownloadError` — cloud couldn't fetch a referenced model
- `ImageDownloadError` — input image fetch failed
- `OOMError` — out of GPU memory (try smaller resolution / fewer frames)
- `InsufficientFundsError` / `InactiveSubscriptionError` — billing
- `PanicError` / `ServiceError` — cloud-side issue, retry later

Always read the error body — it contains structured info:

```python
try:
    submit(wf)
except urllib.error.HTTPError as e:
    body = json.loads(e.read())
    print(f"HTTP {e.code}: {body}")
```

## Cloud Inventory Notes

- **Z-Image Turbo:** all models pre-loaded. 5 z-image style loras (`pixel_art_style_z_image_turbo.safetensors`, etc.).
- **LTX 2.3:** all models pre-loaded, plus a newer 1.1 spatial upscaler. 55 LTX loras (camera control, IC-LoRAs for canny/depth/pose, style loras).
- **Wan 2.2:** t2v + i2v UNets, lightning loras, VAE, umt5_xxl text encoder all pre-loaded.
- **Partner nodes:** ~180 available — `GeminiNanoBanana2`, `Flux2ProImageNode`, `FluxKontextProImageNode`, `KlingTextToVideoNode`, `ByteDanceSeedreamNode`, full ElevenLabs suite, Bria editing, etc. Use the same `extra_data.api_key_comfy_org` pattern from local. See `comfy_workflows` for the pattern.

For workflow JSON for any of these, see `comfy_workflows`.

## Cloud Key Principles

1. **Workflow JSON is identical to local** — only the URL, headers, and polling endpoints differ. Reuse pipeline knowledge from `comfy_workflows`.
2. **Always discover models via API** — your local model list ≠ cloud's. Use `widget_options()` from `comfy_workflows` (handles wrapped COMBO).
3. **Status first, jobs second** — `/api/job/{id}/status` is cheap; `/api/jobs/{id}` returns the heavy payload only after completion.
4. **Pass the X-API-Key header on `/api/view` too** — downloads are not public.
5. **Save outputs with `display_name`, not `filename`** — the hash is for cloud lookup, not for disk.
6. **`mkdir -p` before saving** — `display_name` may include a subfolder.
7. **Custom loras need explicit upload** — never assume a local model exists on cloud. List + error rather than fail mysteriously.
8. **5 concurrent (Pro tier)** — submit all upfront; cloud schedules fairly.
9. **Cloud uses content-addressed storage** — `subfolder` and `overwrite` are accepted but ignored.
10. **For LoRA testing — see `lora_tester` (use `lora_test_cloud.py`).**
