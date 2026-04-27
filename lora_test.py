"""
LoRA Testing Script — Generate images across prompts x strengths.

Creates a self-contained project folder with downloaded images and manifest.

Usage:
    python lora_test.py                          # edit config below
    python lora_test.py --lora "z_image_turbo\\my-lora.safetensors"
    python lora_test.py --list-loras             # show available loras
    python lora_test.py --name "my test"         # custom project name
    python lora_test.py --strengths "0,0.25,0.5,0.75,1.0"
"""
import json, urllib.request, time, sys, argparse, os, shutil
from datetime import date

COMFY_URL = "http://localhost:8188"
DATE = date.today().strftime("%Y%m%d")
PROJECTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects")

# ── Configuration ────────────────────────────────────────────────────────────
# Edit these before running, OR pass --lora / --strengths on the CLI.
# Run `python lora_test.py --list-loras` first to see what's installed locally.
# If your lora has a trigger word (e.g. "c64, "), prepend it to each prompt.

LORA = "REPLACE_WITH_YOUR_LORA.safetensors"   # e.g. "z_image_turbo\\my-lora.safetensors"

STRENGTHS = [0.0, 0.25, 0.5, 0.75, 1.0]

# Generic prompts covering varied subjects so any lora's effect is visible.
# Replace with subject matter your lora was trained on.
PROMPTS = [
    "a portrait of a person looking thoughtfully into the distance",
    "a wide mountain landscape at golden hour with a river running through it",
    "a futuristic city street at night with neon lights and rain reflections",
    "a fox curled up among autumn leaves in a forest clearing",
    "a cozy interior with bookshelves, a fireplace, and warm afternoon light",
]

# Image dimensions
WIDTH = 1024
HEIGHT = 1024

# Sampler settings
STEPS = 8
CFG = 1
SAMPLER = "res_multistep"
SCHEDULER = "simple"
BASE_SEED = 42  # same seed across strengths for fair comparison

# ── CLI ──────────────────────────────────────────────────────────────────────

def list_loras():
    resp = urllib.request.urlopen(f"{COMFY_URL}/object_info/LoraLoader")
    data = json.loads(resp.read())
    loras = data["LoraLoader"]["input"]["required"]["lora_name"][0]
    print(f"Available LoRAs ({len(loras)}):")
    for l in sorted(loras):
        print(f"  {l}")
    sys.exit(0)

def parse_args():
    p = argparse.ArgumentParser(description="LoRA strength tester")
    p.add_argument("--lora", type=str, help="LoRA filename (overrides LORA config)")
    p.add_argument("--list-loras", action="store_true", help="List available loras and exit")
    p.add_argument("--strengths", type=str, help="Comma-separated strengths, e.g. '0,0.5,1.0'")
    p.add_argument("--name", type=str, help="Custom project name (default: lora slug)")
    p.add_argument("--notes", type=str, default="", help="Notes to save in manifest")
    return p.parse_args()

# ── Workflow builder ─────────────────────────────────────────────────────────

def build_workflow(prompt_text, lora_name, strength, seed, prefix):
    """Build Z-Image Turbo workflow with optional LoRA."""
    wf = {
        "1": {"class_type": "UNETLoader", "inputs": {
            "unet_name": "z_image_turbo_bf16.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": "qwen_3_4b.safetensors", "type": "lumina2", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {
            "vae_name": "ae.safetensors"}},
        "4": {"class_type": "ModelSamplingAuraFlow", "inputs": {
            "shift": 3, "model": ["1", 0]}},
    }

    if strength > 0 and lora_name:
        wf["5"] = {"class_type": "LoraLoader", "inputs": {
            "lora_name": lora_name,
            "strength_model": strength, "strength_clip": strength,
            "model": ["4", 0], "clip": ["2", 0]}}
        model_out = ["5", 0]
        clip_out = ["5", 1]
    else:
        model_out = ["4", 0]
        clip_out = ["2", 0]

    wf.update({
        "6": {"class_type": "CLIPTextEncode", "inputs": {
            "text": prompt_text, "clip": clip_out}},
        "7": {"class_type": "ConditioningZeroOut", "inputs": {
            "conditioning": ["6", 0]}},
        "8": {"class_type": "EmptySD3LatentImage", "inputs": {
            "width": WIDTH, "height": HEIGHT, "batch_size": 1}},
        "9": {"class_type": "KSampler", "inputs": {
            "seed": seed, "control_after_generate": "fixed",
            "steps": STEPS, "cfg": CFG,
            "sampler_name": SAMPLER, "scheduler": SCHEDULER,
            "denoise": 1,
            "model": model_out, "positive": ["6", 0],
            "negative": ["7", 0], "latent_image": ["8", 0]}},
        "10": {"class_type": "VAEDecode", "inputs": {
            "samples": ["9", 0], "vae": ["3", 0]}},
        "11": {"class_type": "SaveImage", "inputs": {
            "filename_prefix": prefix, "images": ["10", 0]}},
    })
    return wf

# ── Download image from ComfyUI ─────────────────────────────────────────────

def download_image(filename, subfolder, dest_path):
    """Download an output image from ComfyUI server to local path."""
    url = f"{COMFY_URL}/view?filename={urllib.request.quote(filename)}&type=output"
    if subfolder:
        url += f"&subfolder={urllib.request.quote(subfolder)}"
    resp = urllib.request.urlopen(url)
    with open(dest_path, "wb") as f:
        f.write(resp.read())

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()
    if args.list_loras:
        list_loras()

    lora = args.lora or LORA
    strengths = [float(s) for s in args.strengths.split(",")] if args.strengths else STRENGTHS

    lora_slug = os.path.splitext(os.path.basename(lora))[0]
    project_name = args.name or lora_slug
    project_slug = project_name.replace(" ", "-").lower()[:40]
    project_dir = os.path.join(PROJECTS_DIR, f"{DATE}_{project_slug}")
    images_dir = os.path.join(project_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    total = len(PROMPTS) * len(strengths)
    print(f"LoRA test: {project_name}")
    print(f"  LoRA: {lora}")
    print(f"  {len(PROMPTS)} prompts x {len(strengths)} strengths = {total} images")
    print(f"  Project dir: {project_dir}\n")

    # Submit all jobs
    jobs = []  # (prompt_id, entry_dict)
    idx = 0
    for pi, prompt_text in enumerate(PROMPTS):
        prompt_slug = prompt_text.replace(" ", "-")[:40]
        for si, strength in enumerate(strengths):
            str_label = f"{strength:.2f}".replace(".", "")
            prefix = f"{DATE}_lt_{project_slug}_s{str_label}_{prompt_slug}"
            # Local filename: p{index}_s{strength}.png (clean, predictable)
            local_name = f"p{pi:02d}_s{str_label}.png"

            wf = build_workflow(prompt_text, lora, strength, BASE_SEED + pi, prefix)
            payload = json.dumps({"prompt": wf}).encode("utf-8")
            req = urllib.request.Request(
                f"{COMFY_URL}/prompt", data=payload,
                headers={"Content-Type": "application/json"})
            resp = urllib.request.urlopen(req)
            result = json.loads(resp.read())
            pid = result["prompt_id"]

            entry = {
                "prompt_id": pid,
                "prompt": prompt_text,
                "prompt_index": pi,
                "strength": strength,
                "seed": BASE_SEED + pi,
                "comfy_prefix": prefix,
                "comfy_filename": None,
                "local_filename": local_name,
            }
            jobs.append((pid, entry))
            idx += 1
            print(f"  [{idx:3d}/{total}] Queued: str={strength:.2f}  {prompt_slug}")

    print(f"\nAll {total} queued. Waiting for completion...\n")

    # Poll for completion and download images
    completed = set()
    manifest_entries = []
    while len(completed) < len(jobs):
        for pid, entry in jobs:
            if pid in completed:
                continue
            resp = urllib.request.urlopen(f"{COMFY_URL}/history/{pid}")
            history = json.loads(resp.read())
            if pid in history:
                status = history[pid].get("status", {})
                if status.get("completed") or status.get("status_str") in ("success", "error"):
                    ok = status.get("status_str") == "success"
                    if ok:
                        outputs = history[pid].get("outputs", {})
                        for node_id, node_out in outputs.items():
                            images = node_out.get("images", [])
                            if images:
                                comfy_fn = images[0]["filename"]
                                subfolder = images[0].get("subfolder", "")
                                entry["comfy_filename"] = comfy_fn
                                # Download to project folder
                                dest = os.path.join(images_dir, entry["local_filename"])
                                try:
                                    download_image(comfy_fn, subfolder, dest)
                                except Exception as ex:
                                    print(f"  WARN: Failed to download {comfy_fn}: {ex}")
                    tag = "Done" if ok else "FAIL"
                    completed.add(pid)
                    manifest_entries.append(entry)
                    if len(completed) % 5 == 0 or len(completed) == len(jobs):
                        print(f"  Progress: {len(completed)}/{len(jobs)}")
        if len(completed) < len(jobs):
            time.sleep(2)

    # Write manifest
    manifest = {
        "version": 1,
        "name": project_name,
        "date": DATE,
        "lora": lora,
        "lora_slug": lora_slug,
        "strengths": strengths,
        "prompts": PROMPTS,
        "base_seed": BASE_SEED,
        "settings": {
            "width": WIDTH,
            "height": HEIGHT,
            "steps": STEPS,
            "cfg": CFG,
            "sampler": SAMPLER,
            "scheduler": SCHEDULER,
            "model": "z_image_turbo_bf16.safetensors",
            "clip": "qwen_3_4b.safetensors",
            "vae": "ae.safetensors",
        },
        "notes": args.notes,
        "images": sorted(manifest_entries, key=lambda e: (e["prompt_index"], e["strength"])),
    }
    manifest_path = os.path.join(project_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nProject saved: {project_dir}")
    print(f"  Manifest: {manifest_path}")
    print(f"  Images:   {images_dir}")
    print(f"  {len(completed)}/{total} complete.")
    print(f"\nOpen gallery.html and load this project folder to browse results.")

if __name__ == "__main__":
    main()
