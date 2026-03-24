# LoRA Tester

A toolkit for systematically testing LoRA models across multiple prompts and strength values using a local [ComfyUI](https://github.com/comfyanonymous/ComfyUI) server. Includes a batch generation script and a browser-based gallery for comparing results.

Built to work with [Claude Code](https://claude.ai/claude-code) via the included `comfy_local` skill, but the Python script and gallery work standalone too.

## What's in the box

| File | What it does |
|------|-------------|
| `lora_test.py` | Batch-generates images across a matrix of prompts and LoRA strengths via the ComfyUI API |
| `gallery.html` | Single-file browser app for browsing, comparing, and exporting results |
| `.claude/skills/comfy_local/skill.md` | Claude Code skill for headless ComfyUI interaction (text-to-image, image-to-video, LoRA testing) |

## Prerequisites

- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) running locally on port 8188
- **Z-Image Turbo** model files installed:
  - `z_image_turbo_bf16.safetensors` (diffusion model)
  - `qwen_3_4b.safetensors` (CLIP text encoder)
  - `ae.safetensors` (VAE)
- Python 3.8+ (no pip dependencies -- uses only stdlib)

## Quick Start

### 1. Configure your test

Edit the top of `lora_test.py` to set your prompts and default LoRA:

```python
LORA = "z_image_turbo\\my-lora.safetensors"

PROMPTS = [
    "a wizard casting a spell",
    "a sunset over mountains",
    "a cat sitting on a windowsill",
]

STRENGTHS = [0.0, 0.25, 0.5, 0.75, 1.0]
```

### 2. Run the test

```bash
# Use defaults from the script config:
python lora_test.py

# Or override via CLI:
python lora_test.py --lora "z_image_turbo\\my-lora.safetensors" --strengths "0,0.5,1.0" --name "my lora test"

# List available LoRAs on your ComfyUI server:
python lora_test.py --list-loras
```

### 3. Browse results

Open `gallery.html` in your browser and click **Open Project** to select the generated project folder from `projects/`.

No server needed -- it runs entirely in the browser using local file access.

## CLI Options

```
python lora_test.py [options]

--lora FILENAME     LoRA file path (e.g. "z_image_turbo\\my-lora.safetensors")
--strengths LIST    Comma-separated strength values (e.g. "0,0.25,0.5,0.75,1.0")
--name NAME         Project name (defaults to LoRA filename slug)
--notes TEXT        Optional notes saved to the manifest
--list-loras        List all available LoRAs on the ComfyUI server and exit
```

## How it works

The script submits one ComfyUI job per (prompt, strength) combination using the Z-Image Turbo pipeline. All jobs are queued at once and processed sequentially by ComfyUI (~2 seconds per image on an RTX 5090).

- **Strength 0.00** generates a baseline image with no LoRA applied (the LoraLoader node is skipped entirely)
- The **same seed** is used per prompt across all strengths, so you get an apples-to-apples comparison of just the LoRA's effect

Each run creates a self-contained project folder:

```
projects/
  20260323_my-lora-test/
    manifest.json          # all metadata, prompts, strengths, settings
    images/
      p00_s000.png         # prompt 0, strength 0.00 (baseline)
      p00_s025.png         # prompt 0, strength 0.25
      p00_s050.png         # prompt 0, strength 0.50
      ...
```

## Gallery Features

The gallery is a single HTML file with no dependencies. Open it in any browser.

<img width="925" height="781" alt="image" src="https://github.com/user-attachments/assets/94d5cea1-4777-4920-9137-bcf6796d4501" />

### View Modes

- **Grid** -- rows = prompts, columns = strengths. The classic comparison matrix.
- **Strips** -- each prompt as a horizontal filmstrip with strength badges.
- **Side-by-Side** -- pick any two strengths to compare for a selected prompt.
- **A/B Slider** -- drag a handle to reveal between two strengths for pixel-level comparison.

<img width="2535" height="1268" alt="image" src="https://github.com/user-attachments/assets/dbc7affe-6c25-482e-b5a2-25abd8f36adf" />

### Exporting

Click **Export PNG** to generate shareable comparison images with these layout options:

- Full Grid (all prompts x strengths)
- Single Prompt Strip
- Two-Strength Comparison
- Three-Strength Comparison
- Before/After (baseline vs max strength)

Export settings include background color, label visibility, and optional title text. Download as PNG or copy to clipboard.

## Using with Claude Code

The included `.claude/skills/comfy_local/skill.md` gives Claude Code full knowledge of:

- The ComfyUI REST API
- The Z-Image Turbo text-to-image pipeline
- The LTX 2.3 image-to-video pipeline
- LoRA testing workflows
- Batch generation patterns

To use it, open this repo in Claude Code and ask it to generate images, test LoRAs, or create videos. The skill is loaded automatically when relevant.

## License

MIT
