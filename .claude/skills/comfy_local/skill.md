---
name: comfy_local
description: Generate images and videos via the local ComfyUI server on port 8188. Use when the user wants to generate, create, or render images/video using a locally-running ComfyUI installation.
argument-hint: [prompt or description of what to generate]
allowed-tools: Bash, Read, Write, Glob, Grep, Agent, WebFetch
---

# ComfyUI Local Server Skill

You interact with a local ComfyUI server at `http://localhost:8188` to generate images and video headlessly via the REST API. **No auth** — the server is open on localhost.

## Read These First

This skill covers only what's local-specific. **Before doing any pipeline work, also read:**
- `.claude/skills/comfy_workflows/skill.md` — workflow API format, model discovery, proven pipelines (Z-Image Turbo, LTX 2.3 i2v + t2v, Wan 2.2 t2v), batch pattern, file naming, 24fps default. **Workflow JSON is identical between local and cloud — that skill is the source of truth.**
- `.claude/skills/lora_tester/skill.md` — for any LoRA testing/comparison task, use `lora_test.py` (the local script).

## Local API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/prompt` | POST | Submit a workflow (`{"prompt": {...}}`) → `{"prompt_id": "..."}` |
| `/queue` | GET | Check queue status |
| `/history/{prompt_id}` | GET | Get job result/status (poll this) |
| `/object_info` | GET | List all available nodes (legacy COMBO format `[[opt, ...]]`) |
| `/object_info/{NodeType}` | GET | Get a single node's inputs/options |
| `/view?filename=X&type=output` | GET | Download output file (no auth, no redirect) |
| `/upload/image` | POST | Upload input image (multipart) |
| `/system_stats` | GET | GPU info, VRAM, ComfyUI version |

## Submitting & Polling

```python
import json, urllib.request, time

LOCAL = "http://localhost:8188"

def submit(workflow):
    payload = json.dumps({"prompt": workflow}).encode("utf-8")
    req = urllib.request.Request(f"{LOCAL}/prompt", data=payload,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())  # {"prompt_id": "..."}

def wait_for_job(prompt_id, timeout=240, interval=2):
    """Poll /history/{id}; returns the history entry once available + complete."""
    start = time.time()
    while time.time() - start < timeout:
        with urllib.request.urlopen(f"{LOCAL}/history/{prompt_id}") as r:
            history = json.loads(r.read())
        if prompt_id in history:
            status = history[prompt_id].get("status", {})
            if status.get("completed") or status.get("status_str") in ("success", "error"):
                return history[prompt_id]
        time.sleep(interval)
    raise TimeoutError(f"Job {prompt_id} timed out")
```

For batch jobs, poll every 3s and report progress every ~20 completions. Local processes one job at a time on the GPU.

## After Submission

After submitting, poll `/history/{prompt_id}` to confirm success. **Do NOT download or display outputs by default** — the user manages their own output folder. Just confirm the job completed and report any errors. Output files live in `C:/ai/ComfyUI/output/`.

For single jobs: 4-min timeout (images) or 30-min timeout (videos).

## Local Object Info COMBO Format

Local `/object_info` uses the **legacy nested-list format** (`[[opt, opt, ...], {...}]`), not the wrapped COMBO format that cloud uses. The `widget_options()` helper in `comfy_workflows` handles both — use it. Quick local-only snippet:

```bash
# List loras (legacy format reads index [0] as the list)
curl -s http://localhost:8188/object_info/LoraLoader | python -c "
import json,sys; d=json.load(sys.stdin)
for l in d['LoraLoader']['input']['required']['lora_name'][0]: print(l)"
```

## Output File Naming

See `comfy_workflows` for the full convention. Local-specific: ComfyUI writes to `C:/ai/ComfyUI/output/<prefix>_00001_.png`. For video outputs, prefix with `video/` to land in `output/video/`.

## To Use an Existing Output Image as Input

```python
# Download from output, re-upload to /upload/image as multipart
img = urllib.request.urlopen(f"{LOCAL}/view?filename=NAME&type=output").read()
# POST as multipart to /upload/image — returns {"name": ..., "subfolder": ..., "type": "input"}
```

## Error Handling

- **Server down:** tell the user to start ComfyUI
- **Missing node type:** check `/object_info` to see if it's installed
- **Missing model file:** use the Missing Model Resolver (below)
- **HTTP 400 from `/prompt`:** read the body — it contains `node_errors` with specific input validation failures
- **Validate node inputs against `/object_info/{NodeType}`** before first use — template parameter names are often wrong (see `comfy_workflows` for known divergences)

## Missing Model Resolver

When a workflow fails because a model file is missing, or when the user asks you to check/install models for a workflow:

### Step 1: Identify required models

Check the workflow JSON for **MarkdownNote** nodes (often titled "Model Links"):

```python
import json
wf = json.load(open("workflow.json"))
for node in wf.get("nodes", []):
    if node.get("type") == "MarkdownNote":
        print(node.get("title", ""), node["widgets_values"][0])
```

If no MarkdownNote, check the loader nodes (`UNETLoader`, `CheckpointLoaderSimple`, `CLIPLoader`, `VAELoader`, `LoraLoader`, etc.) — their `widgets_values` contain the expected filenames.

### Step 2: Check what's installed

```bash
ls C:/ai/ComfyUI/models/diffusion_models/
ls C:/ai/ComfyUI/models/vae/
ls C:/ai/ComfyUI/models/text_encoders/
ls C:/ai/ComfyUI/models/loras/
ls C:/ai/ComfyUI/models/latent_upscale_models/
```

Or query the API loader nodes via the helper in `comfy_workflows`.

### Step 3: Download missing models from HuggingFace

**Critical:** Convert HuggingFace URLs from `/blob/main/` to `/resolve/main/` for direct download. Use `curl -L` to follow redirects.

```bash
curl -L --progress-bar -o "C:/ai/ComfyUI/models/<subfolder>/<filename>" "<resolve_url>"
```

**Always confirm with the user before downloading** — model files are large (often 1-20+ GB). Show them the list of missing models and URLs first.

After download, ComfyUI auto-detects new files — no restart needed for most loaders. If it still doesn't appear, the user may need to restart.

### ComfyUI models directory layout

```
C:/ai/ComfyUI/models/
├── diffusion_models/        # UNETLoader, CheckpointLoaderSimple
├── vae/                     # VAELoader, LTXVAudioVAELoader
├── text_encoders/           # CLIPLoader, LTXAVTextEncoderLoader
├── loras/                   # LoraLoader, LoraLoaderModelOnly
├── latent_upscale_models/   # LatentUpscaleModelLoader
├── checkpoints/             # CheckpointLoaderSimple (alternative)
└── clip/                    # CLIPLoader (alternative)
```

### Common HuggingFace repos

| Repo | Models |
|------|--------|
| `Kijai/LTX2.3_comfy` | LTX 2.3 diffusion, VAE, text encoders, loras (fp8 scaled variants) |
| `Lightricks/LTX-2.3` | LTX 2.3 official upscalers |
| `Comfy-Org/Wan_2.2_ComfyUI_Repackaged` | Wan 2.2 t2v/i2v + lightning loras + VAE |
| `Comfy-Org/Wan_2.1_ComfyUI_repackaged` | Wan 2.1 (umt5_xxl text encoder lives here) |
| `Comfy-Org/ltx-2` | LTX split files (text encoders) |
| `Comfy-Org/workflow_templates` | Workflow references |

## Local Key Principles

1. **No auth, no header, no redirects** — local is the simple case.
2. **`/history/{id}` for polling** — has both status and outputs in one response.
3. **Output `filename` IS the saved filename** (no content hash), straight from the `filename_prefix` you set.
4. **Sequential queue** — one job runs at a time. Submit hundreds; they process in order.
5. **For pipelines, batching, file naming, video defaults — see `comfy_workflows`.**
6. **For LoRA testing — see `lora_tester` (use `lora_test.py`).**
