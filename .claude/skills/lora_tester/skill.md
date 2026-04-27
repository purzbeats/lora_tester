---
name: lora_tester
description: Systematically test LoRAs across multiple prompts and strength values to compare them visually. Creates self-contained project folders with a manifest and downloaded images, viewable in a single-file HTML gallery (grid, side-by-side, A/B slider, PNG export). Use when the user wants to test, compare, or evaluate a LoRA. Two backends: lora_test.py (local ComfyUI) and lora_test_cloud.py (Comfy Cloud).
allowed-tools: Bash, Read, Write, Glob, Grep
---

# LoRA Testing Toolkit

A pair of Python scripts plus a single-file HTML viewer for systematic LoRA testing. Creates self-contained, portable project folders that the gallery viewer can open without any server.

**Two flavors:**
- **`lora_test.py`** — runs against local ComfyUI (`http://localhost:8188`). Use when the LoRA is on your local disk.
- **`lora_test_cloud.py`** — runs against Comfy Cloud (`https://cloud.comfy.org`). Use when you want to compare cloud-resident LoRAs without using your own GPU.

Both produce **identical project folder structures** so the gallery viewer doesn't care which backend you used. Both use the **Z-Image Turbo** pipeline internally (~2s per image local, similar on cloud).

For pipeline details (Z-Image Turbo workflow JSON, model discovery, etc.), see `/comfy_workflows`.

## Choosing a Backend

| Want to test… | Use |
|---|---|
| A custom LoRA on your local disk (e.g. `z_image_turbo\\zit-c64.safetensors`) | `lora_test.py` |
| A cloud-resident LoRA (`pixel_art_style_z_image_turbo.safetensors`, etc.) | `lora_test_cloud.py` |
| The same LoRA in both environments to compare | Run both, open both project folders in the gallery |

`lora_test_cloud.py --list-loras` enumerates all 553 cloud-resident LoRAs. For custom LoRAs not on cloud, see `/comfy_cloud` → "Custom Assets" for upload paths.

## `lora_test.py` (Local) — Usage

```bash
# Edit PROMPTS list in the script first, then run:
python lora_test.py --lora "z_image_turbo\\zit-c64.safetensors" --strengths "0,0.5,1.0" --name "c64 lora test"

# List available local loras:
python lora_test.py --list-loras

# All options:
python lora_test.py --lora LORA --strengths "0,0.25,0.5,0.75,1.0" --name "project name" --notes "any notes"
```

### Configuration (edit at top of script)
- `LORA` — default lora filename (with subfolder, e.g. `z_image_turbo\\zit-c64.safetensors`)
- `PROMPTS` — list of test prompts (prefix with style trigger word, e.g. `"c64, a wizard"`)
- `STRENGTHS` — list of strength values (default: `[0.0, 0.25, 0.5, 0.75, 1.0]`)
- `WIDTH`, `HEIGHT` — image dimensions (default: 1024×1024)
- `BASE_SEED` — same seed per prompt across strengths for fair comparison (default: 42)

## `lora_test_cloud.py` (Cloud) — Usage

```bash
# List cloud-resident loras (553 of them):
python lora_test_cloud.py --list-loras

# Run a test:
python lora_test_cloud.py --lora "pixel_art_style_z_image_turbo.safetensors" --strengths "0,0.5,1.0" --name "pixel art test"

# Same flags as the local version:
python lora_test_cloud.py --lora LORA --strengths "0,0.25,0.5,0.75,1.0" --name "project name" --notes "notes"
```

### Cloud-specific behavior
- Loads `COMFY_API_KEY` from `.env` for `X-API-Key` auth
- Verifies the requested lora exists on cloud **before** submitting; suggests near-matches on miss
- Uses `/api/job/{id}/status` for cheap polling, then `/api/jobs/{id}` for outputs
- Downloads via `/api/view` (auth-required, follows GCS redirect)
- Saves to `cloud_projects/` (sibling of `projects/`) so cloud and local results don't mix
- Manifest includes `"backend": "comfy_cloud"` field

## How Both Scripts Work

1. **Build workflows:** one Z-Image Turbo workflow per (prompt × strength) pair, all sharing `BASE_SEED + prompt_index` so the same prompt at different strengths uses the same seed (apples-to-apples comparison).
2. **Strength 0.00 = baseline** — skips the LoraLoader node entirely. This gives you the no-lora reference.
3. **Submit all jobs upfront** to the queue. Local processes them sequentially; cloud runs N in parallel based on tier.
4. **Poll for completion** in a single loop, downloading each image as it finishes.
5. **Write manifest** at the end with all metadata (prompts, strengths, settings, file paths).

## Project Folder Structure

Each run creates a self-contained project. Local goes to `projects/`, cloud goes to `cloud_projects/`:

```
projects/                           (or cloud_projects/)
  20260323_c64-lora-test/
    manifest.json                   # metadata, prompts, strengths, settings
    images/
      p00_s000.png                  # prompt 0, strength 0.00
      p00_s050.png                  # prompt 0, strength 0.50
      p00_s100.png                  # prompt 0, strength 1.00
      p01_s000.png                  # prompt 1, strength 0.00
      p01_s050.png
      ...
```

Filename scheme: `p{prompt_index:02d}_s{strength_x100:03d}.png`. Strength `0.50` becomes `s050`, `1.00` becomes `s100`. This sorts naturally by prompt then strength.

Images are downloaded into the project folder so it's fully portable — you can move it, share it, or open the gallery viewer from any path.

## Gallery Viewer (`gallery.html`)

A single-file HTML app for browsing and comparing LoRA test results. **Open in any browser — no server needed.**

### Opening a Project
1. Open `gallery.html` in your browser
2. Click "Open Project" and select a project folder from `projects/` or `cloud_projects/`
3. The folder must contain `manifest.json` and an `images/` subfolder

### View Modes
- **Grid** — rows = prompts, columns = strengths. The classic comparison matrix.
- **Strips** — each prompt as a horizontal strip with strength badges overlay.
- **Side-by-Side** — pick any two strengths to compare for a selected prompt.
- **A/B Slider** — drag handle to reveal between two strengths for pixel-level comparison.

### Exporting PNGs for Socials
Click "Export PNG" to open the export panel with these layout options:
- **Full Grid** — all prompts × strengths in one shareable image
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
- Project info bar showing lora name, date, image count, backend (local vs cloud)

## Customizing the Pipeline

Both scripts use Z-Image Turbo by default. To test a LoRA against a different base model:

1. Open the script's `build_workflow()` function
2. Replace the loader nodes (UNETLoader/CLIPLoader/VAELoader) with the target model's loaders
3. Adjust the LoraLoader's `lora_name` if the target model uses a different lora subfolder convention
4. Adjust sampler settings (steps, cfg, sampler_name, scheduler) to match the target model's recipe

For pipeline reference, see `/comfy_workflows` (Z-Image Turbo, LTX 2.3, Wan 2.2, etc.) — those are the proven workflow JSON shapes you can swap in.
