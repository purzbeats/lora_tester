"""
LoRA Testing Script (Comfy Cloud variant) — Generate images across prompts x strengths.

Same UX as lora_test.py, but runs on Comfy Cloud (cloud.comfy.org) instead of
a local server. Creates a self-contained project folder under cloud_projects/
that the gallery.html viewer can open.

Usage:
    python lora_test_cloud.py --list-loras
    python lora_test_cloud.py --lora "pixel_art_style_z_image_turbo.safetensors"
    python lora_test_cloud.py --lora "..." --strengths "0,0.25,0.5,0.75,1.0"
    python lora_test_cloud.py --name "my test"

Cloud-specific notes:
- Uses X-API-Key auth (key loaded from .env COMFY_API_KEY).
- 5 concurrent jobs run in parallel on Pro tier; submitting more queues them.
- Outputs downloaded via /api/view (302 → signed GCS URL, auth header required).
- Custom loras (e.g. zit-c64.safetensors) are NOT on cloud — only loras present
  in /api/object_info/LoraLoader can be used. Use --list-loras to see them.
"""
import json, urllib.request, urllib.parse, urllib.error, time, sys, argparse, os
from datetime import date

CLOUD_URL = "https://cloud.comfy.org"
DATE = date.today().strftime("%Y%m%d")
PROJECTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cloud_projects")

# ── API key ──────────────────────────────────────────────────────────────────

def load_api_key():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    with open(env_path) as f:
        for line in f:
            if line.startswith("COMFY_API_KEY="):
                return line.strip().split("=", 1)[1]
    sys.exit("ERROR: COMFY_API_KEY not found in .env")

API_KEY = load_api_key()
HEADERS = {"X-API-Key": API_KEY}

# ── Configuration (edit these or pass via CLI) ──────────────────────────────
# Run `python lora_test_cloud.py --list-loras` to see all 553 cloud-resident loras.
# Default below is a known-good cloud lora so this script runs out of the box.

LORA = "pixel_art_style_z_image_turbo.safetensors"   # cloud-resident; safe default
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

WIDTH = 1024
HEIGHT = 1024
STEPS = 8
CFG = 1
SAMPLER = "res_multistep"
SCHEDULER = "simple"
BASE_SEED = 42

# ── Cloud API helpers ───────────────────────────────────────────────────────

def cloud_get(path):
    req = urllib.request.Request(CLOUD_URL + path, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

def cloud_post(path, body):
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        CLOUD_URL + path, data=payload,
        headers={**HEADERS, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

def widget_options(node_def, input_name):
    """Cloud returns dropdowns as ['COMBO', {'options': [...]}]; locals use [[...]]."""
    spec = node_def["input"]["required"][input_name]
    if isinstance(spec[0], str) and spec[0] == "COMBO":
        return spec[1].get("options", [])
    if isinstance(spec[0], list):
        return spec[0]
    return []

def list_loras_and_exit():
    oi = cloud_get("/api/object_info")
    loras = widget_options(oi["LoraLoader"], "lora_name")
    print(f"Available cloud LoRAs ({len(loras)}):")
    for l in sorted(loras):
        print(f"  {l}")
    sys.exit(0)

def verify_lora_exists(lora_name):
    oi = cloud_get("/api/object_info")
    loras = widget_options(oi["LoraLoader"], "lora_name")
    if lora_name not in loras:
        print(f"ERROR: lora '{lora_name}' not found on cloud.")
        # Suggest near-matches
        lower = lora_name.lower()
        suggestions = [l for l in loras if lower in l.lower() or l.lower() in lower]
        if suggestions:
            print("\nDid you mean one of:")
            for s in suggestions[:10]:
                print(f"  {s}")
        print("\nRun with --list-loras to see all available cloud loras.")
        sys.exit(1)

# ── CLI ──────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="LoRA strength tester (Comfy Cloud)")
    p.add_argument("--lora", type=str, help="LoRA filename on cloud (overrides LORA config)")
    p.add_argument("--list-loras", action="store_true", help="List cloud loras and exit")
    p.add_argument("--strengths", type=str, help="Comma-separated strengths, e.g. '0,0.5,1.0'")
    p.add_argument("--name", type=str, help="Custom project name (default: lora slug)")
    p.add_argument("--notes", type=str, default="", help="Notes to save in manifest")
    return p.parse_args()

# ── Workflow builder (Z-Image Turbo, identical to local) ────────────────────

def build_workflow(prompt_text, lora_name, strength, seed, prefix):
    wf = {
        "1": {"class_type": "UNETLoader", "inputs": {
            "unet_name": "z_image_turbo_bf16.safetensors", "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": "qwen_3_4b.safetensors", "type": "lumina2", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "4": {"class_type": "ModelSamplingAuraFlow", "inputs": {"shift": 3, "model": ["1", 0]}},
    }

    if strength > 0 and lora_name:
        wf["5"] = {"class_type": "LoraLoader", "inputs": {
            "lora_name": lora_name,
            "strength_model": strength, "strength_clip": strength,
            "model": ["4", 0], "clip": ["2", 0]}}
        model_out, clip_out = ["5", 0], ["5", 1]
    else:
        model_out, clip_out = ["4", 0], ["2", 0]

    wf.update({
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt_text, "clip": clip_out}},
        "7": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["6", 0]}},
        "8": {"class_type": "EmptySD3LatentImage", "inputs": {
            "width": WIDTH, "height": HEIGHT, "batch_size": 1}},
        "9": {"class_type": "KSampler", "inputs": {
            "seed": seed, "control_after_generate": "fixed",
            "steps": STEPS, "cfg": CFG,
            "sampler_name": SAMPLER, "scheduler": SCHEDULER, "denoise": 1,
            "model": model_out, "positive": ["6", 0],
            "negative": ["7", 0], "latent_image": ["8", 0]}},
        "10": {"class_type": "VAEDecode", "inputs": {"samples": ["9", 0], "vae": ["3", 0]}},
        "11": {"class_type": "SaveImage", "inputs": {
            "filename_prefix": prefix, "images": ["10", 0]}},
    })
    return wf

# ── Output download (handles 302 → signed GCS URL) ──────────────────────────

def download_output(filename, dest_path, subfolder="", file_type="output"):
    q = urllib.parse.urlencode({
        "filename": filename, "subfolder": subfolder, "type": file_type})
    req = urllib.request.Request(f"{CLOUD_URL}/api/view?{q}", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        with open(dest_path, "wb") as f:
            f.write(r.read())

# Cloud status enums (observed; OpenAPI spec is wrong about these):
# /api/job/{id}/status returns lifecycle: queued_limited -> preprocessing -> executing -> success
# /api/jobs/{id} returns final state: status="completed" for the same job
TERMINAL_OK   = {"success", "completed"}
TERMINAL_FAIL = {"error", "failed", "cancelled"}
TERMINAL = TERMINAL_OK | TERMINAL_FAIL

def get_job_status(prompt_id):
    return cloud_get(f"/api/job/{prompt_id}/status")

def get_job_outputs(prompt_id):
    return cloud_get(f"/api/jobs/{prompt_id}")

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()
    if args.list_loras:
        list_loras_and_exit()

    lora = args.lora or LORA
    strengths = [float(s) for s in args.strengths.split(",")] if args.strengths else STRENGTHS

    # Verify lora exists on cloud before doing anything
    verify_lora_exists(lora)

    lora_slug = os.path.splitext(os.path.basename(lora))[0]
    project_name = args.name or lora_slug
    project_slug = project_name.replace(" ", "-").lower()[:40]
    project_dir = os.path.join(PROJECTS_DIR, f"{DATE}_{project_slug}")
    images_dir = os.path.join(project_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    total = len(PROMPTS) * len(strengths)
    print(f"Cloud LoRA test: {project_name}")
    print(f"  LoRA: {lora}")
    print(f"  {len(PROMPTS)} prompts x {len(strengths)} strengths = {total} images")
    print(f"  Project dir: {project_dir}\n")

    # Submit all jobs upfront — cloud Pro tier schedules 5 in parallel
    jobs = []  # (prompt_id, entry_dict)
    idx = 0
    for pi, prompt_text in enumerate(PROMPTS):
        prompt_slug = prompt_text.replace(" ", "-")[:40]
        for si, strength in enumerate(strengths):
            str_label = f"{strength:.2f}".replace(".", "")
            prefix = f"{DATE}_lt_{project_slug}_s{str_label}_{prompt_slug}"
            local_name = f"p{pi:02d}_s{str_label}.png"

            wf = build_workflow(prompt_text, lora, strength, BASE_SEED + pi, prefix)
            try:
                result = cloud_post("/api/prompt", {"prompt": wf})
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")
                print(f"  ERROR HTTP {e.code} submitting prompt {idx+1}: {body[:400]}")
                sys.exit(1)
            pid = result["prompt_id"]

            jobs.append((pid, {
                "prompt_id": pid, "prompt": prompt_text, "prompt_index": pi,
                "strength": strength, "seed": BASE_SEED + pi,
                "comfy_prefix": prefix, "comfy_filename": None,
                "local_filename": local_name,
            }))
            idx += 1
            print(f"  [{idx:3d}/{total}] Queued: str={strength:.2f}  {prompt_slug}")

    print(f"\nAll {total} queued. Waiting for completion (Pro tier = 5 concurrent)...\n")

    # Poll status only — cheap. Fetch full outputs only after each completes.
    completed = set()
    failed = set()
    manifest_entries = []

    while len(completed) + len(failed) < len(jobs):
        for pid, entry in jobs:
            if pid in completed or pid in failed:
                continue
            try:
                status_info = get_job_status(pid)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    # Job not yet visible; skip this round
                    continue
                print(f"  WARN: status check {pid}: HTTP {e.code}")
                continue
            except Exception as e:
                print(f"  WARN: status check {pid}: {e}")
                continue

            status = status_info.get("status")
            if status in TERMINAL_OK:
                # Fetch full outputs and download
                try:
                    detail = get_job_outputs(pid)
                    outputs = detail.get("outputs", {}) or {}
                    downloaded = False
                    for node_id, node_out in outputs.items():
                        for img in node_out.get("images", []):
                            comfy_fn = img["filename"]
                            entry["comfy_filename"] = comfy_fn
                            dest = os.path.join(images_dir, entry["local_filename"])
                            try:
                                download_output(
                                    comfy_fn, dest,
                                    subfolder=img.get("subfolder", ""),
                                    file_type=img.get("type", "output"))
                                downloaded = True
                            except Exception as ex:
                                print(f"  WARN: download {comfy_fn}: {ex}")
                            break  # one image per job
                        if downloaded:
                            break
                    if not downloaded:
                        print(f"  WARN: job {pid} completed with no image outputs")
                except Exception as ex:
                    print(f"  WARN: failed to fetch outputs for {pid}: {ex}")
                completed.add(pid)
                manifest_entries.append(entry)
            elif status in TERMINAL_FAIL:
                err_msg = status_info.get("error_message") or status
                print(f"  FAIL {pid[:8]} (str={entry['strength']:.2f}): {err_msg}")
                entry["error"] = err_msg
                failed.add(pid)
                manifest_entries.append(entry)
            # pending / in_progress / waiting_to_dispatch — keep polling

        done_count = len(completed) + len(failed)
        if done_count > 0 and done_count % 5 == 0:
            print(f"  Progress: {done_count}/{len(jobs)}  ({len(completed)} ok, {len(failed)} failed)")
        if done_count < len(jobs):
            time.sleep(3)

    # Write manifest (compatible with gallery.html)
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
            "width": WIDTH, "height": HEIGHT,
            "steps": STEPS, "cfg": CFG,
            "sampler": SAMPLER, "scheduler": SCHEDULER,
            "model": "z_image_turbo_bf16.safetensors",
            "clip": "qwen_3_4b.safetensors",
            "vae": "ae.safetensors",
            "backend": "comfy_cloud",
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
    print(f"  {len(completed)}/{total} complete, {len(failed)} failed.")
    print(f"\nOpen gallery.html and load this project folder to browse results.")

if __name__ == "__main__":
    main()
