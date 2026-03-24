---
name: comfy_local
description: Generate images and videos via the local ComfyUI server on port 8188. Use when the user wants to generate, create, or render images/video using ComfyUI, diffusion models, loras, or AI image generation.
argument-hint: [prompt or description of what to generate]
allowed-tools: Bash, Read, Write, Glob, Grep, Agent, WebFetch
---

# ComfyUI Local Server Skill

You interact with a local ComfyUI server at `http://localhost:8188` to generate images and video headlessly via the REST API.

## Workflow Templates (Source of Truth)

Use the official Comfy-Org workflow templates as your source of truth for building workflows:
- **Repository:** https://github.com/Comfy-Org/workflow_templates/tree/main/templates
- Fetch the relevant template JSON from this repo when building a NEW workflow type you haven't done before
- Mix and match templates to achieve what the user requests
- Convert the visual workflow format to the **API format** (node-id keyed dict) before submitting
- **IMPORTANT:** Template node input names may differ from the actual API. Always validate against `/object_info/{NodeType}` before submitting.

## API Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/prompt` | POST | Submit a workflow (`{"prompt": {...}}`) |
| `/queue` | GET | Check queue status |
| `/history/{prompt_id}` | GET | Get job result/status |
| `/object_info` | GET | List all available nodes |
| `/object_info/{NodeType}` | GET | Get node inputs/options (use to discover available models, loras, etc.) |
| `/view?filename=X&type=output` | GET | Download output file |
| `/upload/image` | POST | Upload input image |
| `/system_stats` | GET | System info (GPU, VRAM, versions) |

## Discovering Available Models & Loras

Before building a workflow, query the API to find exact model/lora filenames:

```python
# List all available loras
curl -s http://localhost:8188/object_info/LoraLoader | python -c "
import json,sys; data=json.load(sys.stdin)
for l in data['LoraLoader']['input']['required']['lora_name'][0]: print(l)
"

# List available checkpoints
curl -s http://localhost:8188/object_info/CheckpointLoaderSimple | python -c "
import json,sys; data=json.load(sys.stdin)
for m in data['CheckpointLoaderSimple']['input']['required']['ckpt_name'][0]: print(m)
"

# List available diffusion models (for split-file workflows like z-image)
curl -s http://localhost:8188/object_info/UNETLoader | python -c "
import json,sys; data=json.load(sys.stdin)
for m in data['UNETLoader']['input']['required']['unet_name'][0]: print(m)
"
```

## Submitting Workflows (API Format)

Workflows must be in **API format** — a flat dict keyed by string node IDs. Each node has `class_type` and `inputs`. References to other nodes use `["node_id", output_index]`.

```python
import json, urllib.request

prompt = {
    "1": {
        "class_type": "NodeType",
        "inputs": {
            "param": "value",
            "model": ["other_node_id", 0]  # reference to another node's output
        }
    },
    # ... more nodes
}

payload = json.dumps({"prompt": prompt}).encode("utf-8")
req = urllib.request.Request("http://localhost:8188/prompt", data=payload, headers={"Content-Type": "application/json"})
resp = urllib.request.urlopen(req)
result = json.loads(resp.read())
print(json.dumps(result, indent=2))
```

**When submitting via bash heredoc:** Avoid single quotes inside the Python code — they break the heredoc. Write a `.py` file instead and run it with `python filename.py`.

## Saving Workflows (Two Formats)

Always save workflows in **both** formats:

- **`workflow.json`** — Graph format for the ComfyUI UI. Contains `nodes` array with id, type, pos, size, inputs, outputs, widgets_values, plus `links` array and `groups`. This is what humans open in the UI. Build with a Python generator script (see `build_graph_workflow.py` for reference).
- **`workflow-api.json`** — API format (`{"prompt": {...}}`) for headless batch submission.

Name them: `name_workflow.json` and `name_workflow-api.json`.

### Graph Format Structure
```json
{
  "last_node_id": 63,
  "last_link_id": 64,
  "nodes": [
    {
      "id": 1, "type": "NodeType",
      "pos": [x, y], "size": [w, h],
      "flags": {}, "order": 0, "mode": 0,
      "inputs": [{"name": "model", "type": "MODEL", "link": 1}],
      "outputs": [{"name": "MODEL", "type": "MODEL", "links": [2, 3]}],
      "widgets_values": ["value1", 1.0],
      "title": "Human-Readable Title",
      "properties": {"Node name for S&R": "NodeType"}
    }
  ],
  "links": [
    [link_id, origin_node_id, origin_slot, target_node_id, target_slot, "TYPE"]
  ],
  "groups": [
    {"title": "Stage Name", "bounding": [x, y, w, h], "color": "#3f789e", "font_size": 24}
  ],
  "version": 0.4
}
```

Use a Python builder script to generate graph-format workflows — hand-crafting the JSON is error-prone. See `build_graph_workflow.py` in the project for the pattern.

## Batch Generation

For generating many images from a prompt list, write a standalone Python script that:
1. Defines the prompt list inline
2. Builds the workflow dict per prompt (reuse the same node structure, just swap text/seed/filename)
3. Submits all prompts to the queue up front
4. Polls for completion in a single loop with progress reporting every ~20 items

```python
# Batch pattern — submit all, then poll
prompt_ids = []
for i, text in enumerate(prompts):
    slug = text.replace("c64, ", "").replace(" ", "-")[:40]
    prefix = f"{DATE}_{slug}"
    wf = { ... }  # build workflow with text and prefix
    # submit and collect prompt_id
    prompt_ids.append((result["prompt_id"], slug))

# Poll loop
completed = set()
while len(completed) < len(prompt_ids):
    for pid, slug in prompt_ids:
        if pid in completed: continue
        # check history, add to completed if done
    time.sleep(3)
```

Key details:
- Use `"control_after_generate": "fixed"` in KSampler for batch (not "randomize") so each prompt gets its own deterministic seed
- Increment seed per prompt: `"seed": 42 + i`
- ComfyUI queues all prompts and processes them sequentially — safe to submit hundreds at once
- Report progress every 20 completions, not per-item
- Models only load once and stay cached across the queue

## Z-Image Turbo (Text to Image) — Proven Pipeline

This is the fast text-to-image pipeline. ~2 seconds per image on RTX 5090.

```python
wf = {
    "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "z_image_turbo_bf16.safetensors", "weight_dtype": "default"}},
    "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_4b.safetensors", "type": "lumina2", "device": "default"}},
    "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
    "4": {"class_type": "ModelSamplingAuraFlow", "inputs": {"shift": 3, "model": ["1", 0]}},
    "5": {"class_type": "LoraLoader", "inputs": {"lora_name": "z_image_turbo\\zit-c64.safetensors", "strength_model": 1.0, "strength_clip": 1.0, "model": ["4", 0], "clip": ["2", 0]}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": PROMPT, "clip": ["5", 1]}},
    "7": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["6", 0]}},
    "8": {"class_type": "EmptySD3LatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
    "9": {"class_type": "KSampler", "inputs": {"seed": 42, "control_after_generate": "fixed", "steps": 8, "cfg": 1, "sampler_name": "res_multistep", "scheduler": "simple", "denoise": 1, "model": ["5", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["8", 0]}},
    "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["3", 0]}},
    "11": {"class_type": "SaveImage", "inputs": {"filename_prefix": PREFIX, "images": ["10", 0]}},
}
```

### Lora subfolder conventions
- Z-Image Turbo loras: `z_image_turbo\\name.safetensors`
- Z-Image Base loras: `z_image\\name.safetensors`
- LTX loras: `ltx2\\name.safetensors` or root level
- Use double backslash in Python strings on Windows

### Skip the LoraLoader node entirely if no lora is needed
Wire CLIPLoader directly to CLIPTextEncode and ModelSamplingAuraFlow directly to KSampler.

## LTX 2.3 (Image to Video) — Proven Pipeline

Two-pass pipeline: low-res sampling -> latent 2x upscale -> high-res refinement. ~3-5 min per video on RTX 5090 for 121 frames at 25fps (1280x720).

### Models required
- **Checkpoint:** `ltx-2.3-22b-dev-fp8.safetensors`
- **Distilled LoRA:** `ltx-2.3-22b-distilled-lora-384.safetensors` (strength 0.5)
- **Text encoder:** `gemma_3_12B_it_fp4_mixed.safetensors`
- **Latent upscaler:** `ltx-2.3-spatial-upscaler-x2-1.0.safetensors`
- **NOT installed:** `gemma-3-12b-it-abliterated_lora_rank64_bf16.safetensors` — skip this node, wire CLIP directly

### Node chain (API format node IDs from proven workflow)
```
Models:        CheckpointLoaderSimple -> LoraLoaderModelOnly (distilled, 0.5)
               LTXAVTextEncoderLoader -> CLIPTextEncode (pos) + CLIPTextEncode (neg)
               LTXVAudioVAELoader
               LatentUpscaleModelLoader

Image prep:    [input IMAGE] -> ResizeImageMaskNode (1280x720) -> ResizeImagesByLongerEdge (1536) -> LTXVPreprocess (img_compression=18)

Conditioning:  CLIPTextEncode (pos) + CLIPTextEncode (neg) -> LTXVConditioning (frame_rate=25)

Low-res pass:  EmptyLTXVLatentVideo (640x360, 121 frames)
               LTXVEmptyLatentAudio (121 frames, 25fps)
               LTXVImgToVideoInplace (strength=0.7, bypass=False)
               LTXVConcatAVLatent
               CFGGuider (cfg=1) + KSamplerSelect (euler_ancestral_cfg_pp)
               ManualSigmas ("1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0")
               SamplerCustomAdvanced -> LTXVSeparateAVLatent

Upscale:       LTXVLatentUpsampler (2x)

High-res pass: LTXVImgToVideoInplace (strength=1.0, bypass=False)
               LTXVCropGuides
               LTXVConcatAVLatent
               CFGGuider (cfg=1) + KSamplerSelect (euler_cfg_pp)
               ManualSigmas ("0.85, 0.7250, 0.4219, 0.0")
               SamplerCustomAdvanced -> LTXVSeparateAVLatent

Decode:        VAEDecodeTiled (tile=768, overlap=64, temporal=4096, temporal_overlap=4)
               LTXVAudioVAEDecode

Output:        CreateVideo (fps=25) -> SaveVideo
```

### Critical API input names (differ from template!)
These caused validation errors when using template names — use these exact names:
- `ResizeImageMaskNode`: use `resize_type.crop` (not `crop`), `scale_method` (not `interpolation`)
- `LTXVPreprocess`: use `img_compression` (not `num_latent_frames`)
- `LTXVImgToVideoInplace`: use `strength` (not `image_denoise_strength`)

### Chaining image gen -> video
To feed a generated image into i2v without saving/reloading:
- Connect VAEDecode output directly to ResizeImageMaskNode input
- No need to save, upload, and LoadImage — just wire the node outputs

### To use an existing output image as input
Upload it to ComfyUI's input folder first:
```python
# Download from output, re-upload to input
img_data = urllib.request.urlopen("http://localhost:8188/view?filename=NAME&type=output").read()
# POST as multipart to /upload/image
```

## Output File Naming

**IMPORTANT:** Always use descriptive filename prefixes in this format:
```
YYYYMMDD_descriptive-slug
```
Example: `20260322_c64-hello-world`

ComfyUI auto-appends `_00001_` etc. for frame numbers. Never use generic prefixes like "ComfyUI" or "output".

For video outputs, prefix with `video/`: `video/20260322_c64-hello-world`

For batch runs, derive slug from prompt:
```python
slug = text.replace("c64, ", "").replace(" ", "-")[:40]
prefix = f"{DATE}_{slug}"
```

## Post-Submission

After submitting, poll `/history/{prompt_id}` to confirm success. Do NOT download or display outputs — the user manages their own output folder. Just confirm the job completed and report any errors.

For single jobs, poll every 2s with a 4-min timeout (images) or 30-min timeout (videos).
For batch jobs, poll every 3s and report progress every ~20 completions.

## Error Handling

- If a node type is missing, check `/object_info` to see if it's installed
- If a model/lora file isn't found, query the specific loader's `object_info` to get exact available filenames
- If the server is down, tell the user to start ComfyUI
- On HTTP 400, read the error body — it contains `node_errors` with specific input validation failures
- **Always validate node inputs** against `/object_info/{NodeType}` before first use — template parameter names are often wrong
- **If a model file is missing**, use the Missing Model Resolver (below) to find and download it

## Missing Model Resolver

When a workflow fails because a model file is missing, or when the user asks you to check/install models for a workflow, follow this procedure.

### Step 1: Identify required models

Check the workflow JSON for **MarkdownNote** nodes (often titled "Model Links"). These contain:
- HuggingFace download URLs for each model
- A **Model Folder Structure** section mapping filenames to ComfyUI subdirectories

```python
# Find MarkdownNote nodes in a workflow JSON
import json
wf = json.load(open("workflow.json"))
for node in wf.get("nodes", []):
    if node.get("type") == "MarkdownNote":
        print(node.get("title", ""), node["widgets_values"][0])
```

If the workflow has no MarkdownNote, check the loader nodes (`UNETLoader`, `CheckpointLoaderSimple`, `CLIPLoader`, `VAELoader`, `LoraLoader`, `LoraLoaderModelOnly`, `LatentUpscaleModelLoader`, etc.) — their `widgets_values` contain the expected model filenames.

### Step 2: Check what's installed

Query the ComfyUI API to see what models are currently available:

```bash
# Check specific loader types
curl -s http://localhost:8188/object_info/UNETLoader | python -c "
import json,sys; data=json.load(sys.stdin)
for m in data['UNETLoader']['input']['required']['unet_name'][0]: print(m)"

curl -s http://localhost:8188/object_info/CheckpointLoaderSimple | python -c "
import json,sys; data=json.load(sys.stdin)
for m in data['CheckpointLoaderSimple']['input']['required']['ckpt_name'][0]: print(m)"
```

Or list files directly on disk:

```bash
ls C:/ai/ComfyUI/models/diffusion_models/
ls C:/ai/ComfyUI/models/vae/
ls C:/ai/ComfyUI/models/text_encoders/
ls C:/ai/ComfyUI/models/loras/
ls C:/ai/ComfyUI/models/latent_upscale_models/
```

### Step 3: Download missing models from HuggingFace

**Critical:** Convert HuggingFace URLs from `/blob/main/` to `/resolve/main/` for direct download. Use `curl -L` to follow redirects.

```bash
# Pattern: curl -L -o <dest_path> <resolve_url>
curl -L -o "C:/ai/ComfyUI/models/vae/LTX23_audio_vae_bf16.safetensors" \
  "https://huggingface.co/Kijai/LTX2.3_comfy/resolve/main/vae/LTX23_audio_vae_bf16.safetensors"
```

**Always confirm with the user before downloading** — model files are large (often 1-20+ GB). Show them the list of missing models and URLs first.

### ComfyUI models directory

```
C:/ai/ComfyUI/models/
├── diffusion_models/    # UNETLoader, CheckpointLoaderSimple
├── vae/                 # VAELoader, LTXVAudioVAELoader
├── text_encoders/       # CLIPLoader, LTXAVTextEncoderLoader
├── loras/               # LoraLoader, LoraLoaderModelOnly
├── latent_upscale_models/  # LatentUpscaleModelLoader
├── checkpoints/         # CheckpointLoaderSimple (alternative)
└── clip/                # CLIPLoader (alternative)
```

### Common HuggingFace repos for ComfyUI models

| Repo | Models |
|------|--------|
| `Kijai/LTX2.3_comfy` | LTX 2.3 diffusion, VAE, text encoders, loras (fp8 scaled variants) |
| `Lightricks/LTX-2.3` | LTX 2.3 official upscalers |
| `Comfy-Org/ltx-2` | LTX split files (text encoders) |
| `Comfy-Org/workflow_templates` | Workflow references |

### Handling "model not found" errors at runtime

When ComfyUI returns an error like `"xyz.safetensors" not found`:

1. Search the workflow's MarkdownNote for the filename to find the HuggingFace URL
2. If no MarkdownNote, search HuggingFace: `https://huggingface.co/models?search=<filename>`
3. Identify the correct models subfolder by checking which loader node references it
4. Confirm with the user, then download:
   ```bash
   curl -L --progress-bar -o "C:/ai/ComfyUI/models/<subfolder>/<filename>" "<resolve_url>"
   ```
5. After download, ComfyUI auto-detects new files — no restart needed for most loaders. If the model still isn't found, the user may need to restart ComfyUI.

## LoRA Testing Tool (`lora_test.py`)

A dedicated script for systematically testing LoRAs across multiple prompts and strength values. Creates self-contained project folders for use with the gallery viewer.

### Usage
```bash
# Edit PROMPTS list in the script first, then run:
python lora_test.py --lora "z_image_turbo\\zit-c64.safetensors" --strengths "0,0.5,1.0" --name "c64 lora test"

# List available loras:
python lora_test.py --list-loras

# All options:
python lora_test.py --lora LORA --strengths "0,0.25,0.5,0.75,1.0" --name "project name" --notes "any notes"
```

### Configuration
Edit these variables at the top of `lora_test.py`:
- `LORA` — default lora filename (with subfolder, e.g. `z_image_turbo\\zit-c64.safetensors`)
- `PROMPTS` — list of test prompts (prefix with style trigger word, e.g. `"c64, a wizard"`)
- `STRENGTHS` — list of strength values to test (default: `[0.0, 0.25, 0.5, 0.75, 1.0]`)
- `WIDTH`, `HEIGHT` — image dimensions (default: 1024x1024)
- `BASE_SEED` — consistent seed per prompt across strengths for fair comparison

### Project Folder Structure
Each run creates a self-contained project:
```
projects/
  20260323_c64-lora-test/
    manifest.json          # metadata, prompts, strengths, settings
    images/
      p00_s000.png         # prompt 0, strength 0.00
      p00_s050.png         # prompt 0, strength 0.50
      p00_s100.png         # prompt 0, strength 1.00
      p01_s000.png         # prompt 1, strength 0.00
      ...
```

Images are downloaded from ComfyUI into the project folder so it's fully portable. The manifest contains all metadata needed by the gallery viewer.

### How It Works
- Strength 0.00 = baseline (no LoRA, skips LoraLoader node entirely)
- Same seed per prompt across all strengths for apples-to-apples comparison
- Uses Z-Image Turbo pipeline (~2s per image)
- Submits all jobs to ComfyUI queue at once, then polls for completion

## LoRA Gallery Viewer (`gallery.html`)

A single-file HTML app for browsing and comparing LoRA test results. Open in any browser — no server needed.

### Opening a Project
1. Open `gallery.html` in your browser
2. Click "Open Project" and select a project folder from `projects/`
3. The folder must contain `manifest.json` and an `images/` subfolder

### View Modes
- **Grid** — rows = prompts, columns = strengths. The classic comparison matrix.
- **Strips** — each prompt as a horizontal strip with strength badges overlay.
- **Side-by-Side** — pick any two strengths to compare for a selected prompt.
- **A/B Slider** — drag handle to reveal between two strengths for pixel-level comparison.

### Exporting PNGs for Socials
Click "Export PNG" to open the export panel with these layout options:
- **Full Grid** — all prompts x strengths in one shareable image
- **Single Prompt Strip** — one prompt across all strengths
- **Two-Strength Comparison** — pick two strengths side by side
- **Three-Strength Comparison** — pick three strengths
- **Before/After** — clean baseline vs max strength

Export settings:
- Background color (dark/white/black/transparent)
- Label options (strengths, prompts, both, none)
- Optional title text
- Download as PNG or copy to clipboard

### Other Features
- Lightbox with left/right arrow key navigation
- Adjustable thumbnail sizes (S/M/L/XL)
- Project info bar showing lora name, date, image count

## Key Principles

1. **Always query the API** for available models/loras — don't assume filenames
2. **Validate node inputs** against `/object_info` — template names diverge from actual API names
3. **Fetch templates** from the workflow_templates repo only for NEW workflow types — use proven pipelines documented here for known types
4. **Mix and match** — chain pipelines by wiring node outputs directly (e.g., VAEDecode -> ResizeImageMaskNode)
5. **Batch efficiently** — submit all prompts up front, poll in a single loop, models stay cached
6. **Write .py files** for batch runs and complex workflows — avoid bash heredocs with embedded Python
7. **Save both formats** — graph format for UI, API format for headless use
8. **Descriptive filenames** with date prefix, no output display
9. **Don't include loras/models that aren't installed** — always verify with the API first
