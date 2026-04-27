---
name: comfy_workflows
description: Shared best practices and proven workflow recipes for ComfyUI (Z-Image Turbo, LTX 2.3, Wan 2.2, etc.). Backend-agnostic — workflow JSON is identical between local and cloud. Loaded by /comfy_local and /comfy_cloud; can also be used standalone for workflow-building reference.
allowed-tools: Bash, Read, Write, Glob, Grep, Agent, WebFetch
---

# ComfyUI Workflows — Shared Knowledge

This skill documents **what's the same** across local ComfyUI and Comfy Cloud: the workflow JSON format, model discovery patterns, proven pipelines, file naming, and global defaults. It's loaded automatically by `/comfy_local` and `/comfy_cloud`, but can also be referenced standalone.

For backend-specific concerns (auth, polling, downloads), see:
- `/comfy_local` — `http://localhost:8188`, no auth, files on disk
- `/comfy_cloud` — `https://cloud.comfy.org`, X-API-Key, content-addressed storage

## Workflow API Format

Workflows submitted to `/prompt` (local) or `/api/prompt` (cloud) must be in **API format** — a flat dict keyed by string node IDs. Each node has `class_type` and `inputs`. References to other nodes use `["node_id", output_index]`.

```python
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
```

**When submitting via bash heredoc:** avoid single quotes inside the Python code — they break the heredoc. Write a `.py` file instead and run it with `python filename.py`. Better yet, `Write` the script with the `Write` tool then `Bash` execute it.

## Saving Workflows (Two Formats)

When asked to save a workflow file (not just submit and discard), save **both** formats:

- **`name_workflow.json`** — Graph format for the ComfyUI UI. Contains `nodes` array with id/type/pos/size/widgets_values, plus `links` array and `groups`. This is what humans open in the UI.
- **`name_workflow-api.json`** — API format (`{"prompt": {...}}`) for headless batch submission.

### Graph Format Structure
```json
{
  "last_node_id": 63, "last_link_id": 64,
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
  "groups": [{"title": "Stage Name", "bounding": [x, y, w, h], "color": "#3f789e", "font_size": 24}],
  "version": 0.4
}
```

Use a Python builder script to generate graph-format workflows — hand-crafting the JSON is error-prone.

## Discovering Models & Loras (Both Formats)

`/object_info` returns dropdowns in two different shapes depending on backend version:
- **Wrapped (newer, used by cloud):** `["COMBO", {"options": [...], "multiselect": false}]`
- **Legacy (older, used by local):** `[[opt1, opt2, ...], {...}]`

Use this helper to handle both:

```python
def widget_options(node_def, input_name):
    """Extract dropdown options from a node's input spec, handling both
    the wrapped COMBO format and the legacy nested-list format."""
    spec = node_def["input"]["required"][input_name]
    if isinstance(spec[0], str) and spec[0] == "COMBO":
        return spec[1].get("options", [])
    if isinstance(spec[0], list):  # legacy [[opt, opt, ...], {...}]
        return spec[0]
    return []

# Usage (substitute your backend's URL + auth as needed)
import json, urllib.request
oi = json.loads(urllib.request.urlopen(BASE + "/object_info", ...).read())
loras = widget_options(oi["LoraLoader"], "lora_name")
unets = widget_options(oi["UNETLoader"], "unet_name")
ckpts = widget_options(oi["CheckpointLoaderSimple"], "ckpt_name")
clips = widget_options(oi["CLIPLoader"], "clip_name")
vaes  = widget_options(oi["VAELoader"], "vae_name")
```

**Always discover models via API first** — never hardcode filenames from another machine, since local and cloud have different model sets.

## Workflow Sources of Truth (Priority Order)

When building a workflow type for the first time, check in this order:

1. **Cloud `/api/global_subgraphs`** (cloud only) — 31 prefab subgraph blueprints maintained by Comfy. Best for cloud since they reference cloud-resident models. Fetch full JSON via `/api/global_subgraphs/{id}`. Format: wrapped graph-format JSON with the actual nodes inside `definitions.subgraphs[0].nodes` — convert to API format before submitting. Available IDs include `text_to_image_z_image_turbo`, `text_to_video_wan_2_2`, `image_to_video_wan_2_2`, `image_edit_flux_2_dev`, `image_edit_qwen_2511`, `controlnet_z_image_turbo`, etc.
2. **`Comfy-Org/workflow_templates` GitHub repo** — broader catalog. Fetch via `https://raw.githubusercontent.com/Comfy-Org/workflow_templates/main/templates/<name>.json`. Browse with `gh api repos/Comfy-Org/workflow_templates/contents/templates`. Most templates use the wrapped subgraph format too.
3. **The proven pipelines documented below** — already battle-tested for known types.

**Two dead-end endpoints to skip:**
- `/api/workflow_templates` (cloud) — currently returns `{}`, not wired up.

**Caveat for repo templates:** some "t2v" templates (e.g. `video_ltx2_3_t2v.json`) actually include image-conditioning nodes (`LoadImage` → `LTXVImgToVideoInplace`) — they expect a "first frame" still. For pure text-to-video, skip the image branch and wire `EmptyLTXVLatentVideo` straight into `LTXVConcatAVLatent`.

**Validate template names against `/object_info`** — template parameter names sometimes diverge from actual API names. Examples that have bitten us:
- `ResizeImageMaskNode`: use `resize_type` and `scale_method` (not `crop`/`interpolation`)
- `LTXVPreprocess`: use `img_compression` (not `num_latent_frames`)
- `LTXVImgToVideoInplace`: use `strength` (not `image_denoise_strength`)

## Output File Naming

**Always use descriptive filename prefixes:**
```
YYYYMMDD_descriptive-slug
```
Example: `20260322_c64-hello-world` → ComfyUI auto-appends `_00001_.png`.

**Never use generic prefixes** like "ComfyUI" or "output". For batch runs, derive slug from prompt:

```python
slug = text.replace("c64, ", "").replace(" ", "-")[:40]
prefix = f"{DATE}_{slug}"
```

**Video outputs:** prefix with `video/` so they save to a `video/` subfolder: `video/20260322_c64-hello-world`.

## Video Output Defaults

**Default fps for all video outputs: 24** (cinema standard, smoother than 16, clean for editing). Apply everywhere `fps` or `frame_rate` appears in a video pipeline:

- `CreateVideo.fps` — always 24
- `LTXVConditioning.frame_rate` — set to 24 (LTX is trained at 25, but 24 works fine; conditioning + audio + create must all match or audio drifts)
- `LTXVEmptyLatentAudio.frame_rate` — set to 24 to match
- `EmptyHunyuanLatentVideo` (Wan): no fps input on the model — only `CreateVideo` needs the bump

Override per-job only when there's a specific reason (e.g. matching a 30fps social platform spec). Frame count (`length`) is independent — adjust to control video duration.

## Batch Generation Pattern

For generating many images from a prompt list, use this shape:

```python
# 1. Submit all jobs upfront
prompt_ids = []
for i, text in enumerate(prompts):
    slug = text.replace("style_word, ", "").replace(" ", "-")[:40]
    wf = build_workflow(text, seed=42 + i, prefix=f"{DATE}_{slug}")
    res = submit(wf)              # backend-specific submit helper
    prompt_ids.append((res["prompt_id"], slug))

# 2. Poll in a single loop, report progress every ~20 items
done = set()
while len(done) < len(prompt_ids):
    for pid, slug in prompt_ids:
        if pid in done: continue
        # check status using the backend's polling endpoint, mark done if terminal
    if len(done) % 20 == 0 and done:
        print(f"  Progress: {len(done)}/{len(prompt_ids)}")
    time.sleep(3)
```

Key details:
- Use `"control_after_generate": "fixed"` in KSampler for batch (not "randomize") so each prompt gets its own deterministic seed
- Increment seed per prompt: `"seed": 42 + i`
- It's safe to submit hundreds of prompts at once — the queue handles them
- Models stay cached across the queue; only the first job pays the load cost
- **Local:** jobs run sequentially (one GPU). **Cloud:** N concurrent jobs run in parallel based on tier (Pro = 5).

For **API/partner nodes** (Gemini, Flux Pro, Kling, ByteDance, etc.) the parallelism is *per-node* not *per-job* — see the API Nodes section below.

## API Nodes (Cloud-Based Generation, Both Backends)

API nodes (`GeminiNanoBanana2`, `Flux2ProImageNode`, `FluxKontextProImageNode`, `KlingTextToVideoNode`, `ByteDanceSeedreamNode`, full ElevenLabs suite, Bria, etc.) run on remote servers via Comfy.org regardless of whether the *workflow* is submitted local or cloud. They require the Comfy.org API key in `extra_data` (the same `COMFY_API_KEY` you use for cloud auth).

```python
payload = json.dumps({
    "prompt": wf,
    "extra_data": {"api_key_comfy_org": api_key}
}).encode("utf-8")
```

- **Always load the key from `.env`** — never hardcode it
- Goes in `extra_data.api_key_comfy_org`, NOT inside the workflow nodes
- Generate keys at https://platform.comfy.org/login
- Only needed for API nodes — local model nodes (KSampler, VAEDecode, etc.) don't need it

### Nano Banana 2 (Gemini Image Gen)

Cloud-based image generation via Google Gemini 3.1 Flash. Supports text-to-image and image editing. Costs ~$0.07-0.15 per image depending on resolution.

```python
wf = {
    "1": {"class_type": "GeminiNanoBanana2", "inputs": {
        "prompt": PROMPT,
        "model": "Nano Banana 2 (Gemini 3.1 Flash Image)",
        "seed": 42,
        "aspect_ratio": "16:9",   # auto, 1:1, 2:3, 3:2, 3:4, 4:3, 4:5, 5:4, 9:16, 16:9, 21:9
        "resolution": "2K",       # 1K, 2K, 4K
        "response_modalities": "IMAGE",   # IMAGE or IMAGE+TEXT
        "thinking_level": "MINIMAL"       # MINIMAL or HIGH
    }},
    "2": {"class_type": "SaveImage", "inputs": {
        "filename_prefix": PREFIX,
        "images": ["1", 0]
    }},
}
```

Optional inputs:
- `images` — reference image(s) for editing (wire from LoadImage or other IMAGE output)
- `system_prompt` — override the default system prompt
- Outputs: `IMAGE` (index 0), `STRING` (index 1), `thought_image` (index 2, only with HIGH thinking + IMAGE+TEXT)

### API Node Parallelism

API nodes execute concurrently on remote servers, unlike local GPU nodes which run sequentially.

**IMPORTANT:** When generating multiple images with API nodes, put all generators in a **single workflow job**, not separate jobs. Use one shared LoadImage node and wire it to multiple generator nodes, each with its own SaveImage. ComfyUI will execute the independent API nodes in parallel within one job.

```python
# Single workflow with N parallel API generators
wf = {"1": {"class_type": "LoadImage", "inputs": {"image": "input.png"}}}
for i, prompt in enumerate(PROMPTS):
    gen_id, save_id = str(10 + i), str(20 + i)
    wf[gen_id] = {"class_type": "GeminiNanoBanana2", "inputs": {
        "prompt": prompt, "model": "Nano Banana 2 (Gemini 3.1 Flash Image)",
        "seed": 42 + i, "aspect_ratio": "16:9", "resolution": "2K",
        "response_modalities": "IMAGE", "thinking_level": "MINIMAL",
        "images": ["1", 0]  # all share the same input image
    }}
    wf[save_id] = {"class_type": "SaveImage", "inputs": {
        "filename_prefix": f"{DATE}_output-{i:02d}", "images": [gen_id, 0]
    }}
# Submit as ONE job — all generators run in parallel
```

This is faster than N separate jobs and only requires polling one prompt_id.

## Z-Image Turbo (Text to Image) — Proven Pipeline

Fast text-to-image. ~2 seconds per image on RTX 5090 (local) or cloud. Identical workflow JSON between backends — only model availability differs (cloud has the base models pre-loaded; local needs them downloaded).

```python
wf = {
    "1": {"class_type": "UNETLoader", "inputs": {
        "unet_name": "z_image_turbo_bf16.safetensors", "weight_dtype": "default"}},
    "2": {"class_type": "CLIPLoader", "inputs": {
        "clip_name": "qwen_3_4b.safetensors", "type": "lumina2", "device": "default"}},
    "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
    "4": {"class_type": "ModelSamplingAuraFlow", "inputs": {"shift": 3, "model": ["1", 0]}},
    # Optional LoraLoader as node "5" — see "Adding a LoRA" below
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": PROMPT, "clip": ["2", 0]}},
    "7": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["6", 0]}},
    "8": {"class_type": "EmptySD3LatentImage", "inputs": {
        "width": 1024, "height": 1024, "batch_size": 1}},
    "9": {"class_type": "KSampler", "inputs": {
        "seed": 42, "control_after_generate": "fixed",
        "steps": 8, "cfg": 1, "sampler_name": "res_multistep",
        "scheduler": "simple", "denoise": 1,
        "model": ["4", 0], "positive": ["6", 0],
        "negative": ["7", 0], "latent_image": ["8", 0]}},
    "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["3", 0]}},
    "11": {"class_type": "SaveImage", "inputs": {"filename_prefix": PREFIX, "images": ["10", 0]}},
}
```

### Adding a LoRA

Splice a `LoraLoader` between `ModelSamplingAuraFlow` and the `CLIPTextEncode`+`KSampler` consumers:

```python
wf["5"] = {"class_type": "LoraLoader", "inputs": {
    "lora_name": LORA_FILENAME,
    "strength_model": 1.0, "strength_clip": 1.0,
    "model": ["4", 0], "clip": ["2", 0]}}
# Then redirect node 6's clip to ["5", 1] and node 9's model to ["5", 0]
wf["6"]["inputs"]["clip"] = ["5", 1]
wf["9"]["inputs"]["model"] = ["5", 0]
```

If `strength == 0` or no lora, skip the LoraLoader node entirely — wire CLIPLoader directly to CLIPTextEncode and ModelSamplingAuraFlow directly to KSampler.

### LoRA Subfolder Conventions (local)
- Z-Image Turbo loras: `z_image_turbo\\name.safetensors`
- Z-Image Base loras: `z_image\\name.safetensors`
- LTX loras: `ltx2\\name.safetensors` or root level
- Use double backslash in Python strings on Windows

(Cloud uses a flat namespace — no subfolder prefix.)

## Wan 2.2 Text-to-Video — Proven Pipeline

Built directly from the cloud subgraph `text_to_video_wan_2_2`. Two-stage diffusion (high-noise UNet → low-noise UNet), each with a 4-step lightning lora. ~30s for a 5-second 640×640 video on cloud.

```python
wf = {
    "71": {"class_type": "CLIPLoader", "inputs": {
        "clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors",
        "type": "wan", "device": "default"}},
    "73": {"class_type": "VAELoader", "inputs": {"vae_name": "wan_2.1_vae.safetensors"}},
    "75": {"class_type": "UNETLoader", "inputs": {
        "unet_name": "wan2.2_t2v_high_noise_14B_fp8_scaled.safetensors", "weight_dtype": "default"}},
    "76": {"class_type": "UNETLoader", "inputs": {
        "unet_name": "wan2.2_t2v_low_noise_14B_fp8_scaled.safetensors", "weight_dtype": "default"}},
    "83": {"class_type": "LoraLoaderModelOnly", "inputs": {
        "model": ["75", 0],
        "lora_name": "wan2.2_t2v_lightx2v_4steps_lora_v1.1_high_noise.safetensors",
        "strength_model": 1.0}},
    "85": {"class_type": "LoraLoaderModelOnly", "inputs": {
        "model": ["76", 0],
        "lora_name": "wan2.2_t2v_lightx2v_4steps_lora_v1.1_low_noise.safetensors",
        "strength_model": 1.0}},
    "82": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["83", 0], "shift": 5.0}},
    "86": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["85", 0], "shift": 5.0}},
    "89": {"class_type": "CLIPTextEncode", "inputs": {"text": PROMPT, "clip": ["71", 0]}},
    "72": {"class_type": "CLIPTextEncode", "inputs": {"text": NEG, "clip": ["71", 0]}},
    "74": {"class_type": "EmptyHunyuanLatentVideo", "inputs": {
        "width": 640, "height": 640, "length": 81, "batch_size": 1}},
    # High-noise pass: steps 0-2 of 4
    "81": {"class_type": "KSamplerAdvanced", "inputs": {
        "add_noise": "enable", "noise_seed": 42, "control_after_generate": "fixed",
        "steps": 4, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple",
        "start_at_step": 0, "end_at_step": 2, "return_with_leftover_noise": "enable",
        "model": ["82", 0], "positive": ["89", 0], "negative": ["72", 0],
        "latent_image": ["74", 0]}},
    # Low-noise pass: steps 2-4 of 4
    "78": {"class_type": "KSamplerAdvanced", "inputs": {
        "add_noise": "disable", "noise_seed": 0, "control_after_generate": "fixed",
        "steps": 4, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple",
        "start_at_step": 2, "end_at_step": 4, "return_with_leftover_noise": "disable",
        "model": ["86", 0], "positive": ["89", 0], "negative": ["72", 0],
        "latent_image": ["81", 0]}},
    "87": {"class_type": "VAEDecode", "inputs": {"samples": ["78", 0], "vae": ["73", 0]}},
    "114": {"class_type": "CreateVideo", "inputs": {"images": ["87", 0], "fps": 24.0}},
    "200": {"class_type": "SaveVideo", "inputs": {
        "video": ["114", 0], "filename_prefix": PREFIX,
        "format": "mp4", "codec": "h264"}},
}
```

Tradeoff: the lightning loras cut steps from 20 to 4 but reduce dynamic range. For higher motion fidelity, drop the loras and bump `steps` to 20.

## LTX 2.3 Text-to-Video — Proven Pipeline (single-pass)

**Caveat:** the official `video_ltx2_3_t2v.json` template in the workflow_templates repo includes a `LoadImage`+`LTXVImgToVideoInplace` branch — it's actually i2v with a "first frame" still. For pure text-to-video, omit the image branch and feed `EmptyLTXVLatentVideo` straight into `LTXVConcatAVLatent`. Single-pass (no upscaler) — ~60s for a ~4-second 768×512 video on cloud.

```python
LTX_CKPT     = "ltx-2.3-22b-dev-fp8.safetensors"
LTX_LORA     = "ltx-2.3-22b-distilled-lora-384.safetensors"
LTX_TEXT_ENC = "gemma_3_12B_it_fp4_mixed.safetensors"

wf = {
    "1":  {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": LTX_CKPT}},
    "2":  {"class_type": "LoraLoaderModelOnly", "inputs": {
        "model": ["1", 0], "lora_name": LTX_LORA, "strength_model": 0.5}},
    "3":  {"class_type": "LTXAVTextEncoderLoader", "inputs": {
        "text_encoder": LTX_TEXT_ENC, "ckpt_name": LTX_CKPT, "device": "default"}},
    "4":  {"class_type": "LTXVAudioVAELoader", "inputs": {"ckpt_name": LTX_CKPT}},
    "5":  {"class_type": "CLIPTextEncode", "inputs": {"text": PROMPT, "clip": ["3", 0]}},
    "6":  {"class_type": "CLIPTextEncode", "inputs": {"text": NEG, "clip": ["3", 0]}},
    "7":  {"class_type": "LTXVConditioning", "inputs": {
        "positive": ["5", 0], "negative": ["6", 0], "frame_rate": 24.0}},
    "8":  {"class_type": "EmptyLTXVLatentVideo", "inputs": {
        "width": 768, "height": 512, "length": 97, "batch_size": 1}},
    "9":  {"class_type": "LTXVEmptyLatentAudio", "inputs": {
        "frames_number": 97, "frame_rate": 24, "batch_size": 1, "audio_vae": ["4", 0]}},
    "10": {"class_type": "LTXVConcatAVLatent", "inputs": {
        "video_latent": ["8", 0], "audio_latent": ["9", 0]}},
    "11": {"class_type": "RandomNoise", "inputs": {
        "noise_seed": 42, "control_after_generate": "fixed"}},
    "12": {"class_type": "CFGGuider", "inputs": {
        "model": ["2", 0], "positive": ["7", 0], "negative": ["7", 1], "cfg": 1.0}},
    "13": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler_ancestral_cfg_pp"}},
    "14": {"class_type": "ManualSigmas", "inputs": {
        "sigmas": "1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0"}},
    "15": {"class_type": "SamplerCustomAdvanced", "inputs": {
        "noise": ["11", 0], "guider": ["12", 0],
        "sampler": ["13", 0], "sigmas": ["14", 0],
        "latent_image": ["10", 0]}},
    "16": {"class_type": "LTXVSeparateAVLatent", "inputs": {"av_latent": ["15", 0]}},
    "17": {"class_type": "VAEDecodeTiled", "inputs": {
        "samples": ["16", 0], "vae": ["1", 2],
        "tile_size": 768, "overlap": 64, "temporal_size": 4096, "temporal_overlap": 4}},
    "18": {"class_type": "LTXVAudioVAEDecode", "inputs": {
        "samples": ["16", 1], "audio_vae": ["4", 0]}},
    "19": {"class_type": "CreateVideo", "inputs": {
        "images": ["17", 0], "audio": ["18", 0], "fps": 24.0}},
    "20": {"class_type": "SaveVideo", "inputs": {
        "video": ["19", 0], "filename_prefix": PREFIX,
        "format": "mp4", "codec": "h264"}},
}
```

## LTX 2.3 (Image to Video) — Proven Pipeline (two-pass)

Two-pass: low-res sample → 2x latent upsample → high-res refine. ~3-5 min per 121-frame 1280×720 video on RTX 5090 / cloud.

### Models required
- **Checkpoint:** `ltx-2.3-22b-dev-fp8.safetensors`
- **Distilled LoRA:** `ltx-2.3-22b-distilled-lora-384.safetensors` (strength 0.5)
- **Text encoder:** `gemma_3_12B_it_fp4_mixed.safetensors`
- **Latent upscaler:** `ltx-2.3-spatial-upscaler-x2-1.0.safetensors` (a v1.1 also exists on cloud)

### Node chain

```
Models:        CheckpointLoaderSimple -> LoraLoaderModelOnly (distilled, 0.5)
               LTXAVTextEncoderLoader -> CLIPTextEncode (pos) + CLIPTextEncode (neg)
               LTXVAudioVAELoader
               LatentUpscaleModelLoader

Image prep:    [input IMAGE] -> ResizeImageMaskNode (1280x720)
                              -> ResizeImagesByLongerEdge (1536)
                              -> LTXVPreprocess (img_compression=18)

Conditioning:  CLIPTextEncode (pos/neg) -> LTXVConditioning (frame_rate=24)

Low-res pass:  EmptyLTXVLatentVideo (640x360, 121 frames)
               LTXVEmptyLatentAudio (121 frames, 24fps)
               LTXVImgToVideoInplace (strength=0.7, bypass=False)   [skip for t2v]
               LTXVConcatAVLatent
               CFGGuider (cfg=1) + KSamplerSelect (euler_ancestral_cfg_pp)
               ManualSigmas ("1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0")
               SamplerCustomAdvanced -> LTXVSeparateAVLatent

Upscale:       LTXVLatentUpsampler (2x, on video latent only)

High-res pass: LTXVImgToVideoInplace (strength=1.0, bypass=False)   [skip for t2v]
               LTXVCropGuides (re-aligns conditioning to upsampled latent dims)
               LTXVConcatAVLatent
               CFGGuider (cfg=1) + KSamplerSelect (euler_cfg_pp)
               ManualSigmas ("0.85, 0.7250, 0.4219, 0.0")
               SamplerCustomAdvanced -> LTXVSeparateAVLatent

Decode:        VAEDecodeTiled (tile=768, overlap=64, temporal=4096, temporal_overlap=4)
               LTXVAudioVAEDecode

Output:        CreateVideo (fps=24) -> SaveVideo (format=mp4, codec=h264)
```

### Chaining image gen → video
To feed a generated image into i2v without saving/reloading:
- Connect VAEDecode output directly to ResizeImageMaskNode input
- No need to save, upload, and LoadImage — just wire the node outputs

### To use an existing output image as input (local)
Upload it to ComfyUI's input folder first via `POST /upload/image` (multipart). On cloud, use `/api/upload/image` — same multipart shape.

## Key Workflow Principles

1. **Workflow JSON is identical across local and cloud** — only the URL, headers, and polling endpoints differ. Build once, run anywhere.
2. **Always discover models via API first** — never hardcode filenames from another machine.
3. **Validate node inputs against `/object_info/{NodeType}`** — template parameter names sometimes diverge.
4. **Mix and match** — chain pipelines by wiring node outputs directly (e.g. VAEDecode → ResizeImageMaskNode for image-then-video).
5. **Batch efficiently** — submit all prompts up front, poll in a single loop, models stay cached.
6. **Write `.py` files** for batch runs and complex workflows — avoid bash heredocs with embedded Python.
7. **Save both formats** when persisting workflows — graph for UI, API for headless.
8. **Descriptive filenames** with date prefix.
9. **Default to 24fps** for any video output unless told otherwise.
