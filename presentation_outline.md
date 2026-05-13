# Agentic Control of ComfyUI

*Presentation outline — built around the `lora_tester` project as a case study.*

Each `##` heading is a slide. Bullets are speaker points / slide bullets. Italic notes in parens are stage directions for you, not for the slide.

---

## 1. Title

- **Agentic Control of ComfyUI**
- Or: *what happens when you let a model drive the node graph*
- Speaker, role, date

*(Optional subtitle: "A walkthrough of `lora_tester` — a Claude Code project that turns natural-language requests into ComfyUI batch jobs.")*

---

## 2. Why this talk?

- Generative pipelines are graphs. Graphs are code. Code is something LLMs are good at.
- The interesting question isn't *can a model use ComfyUI?* — it's **what shape of interface does an agent actually need to be useful?**
- We'll look at one concrete answer: a small project that lets Claude Code drive both local ComfyUI and Comfy Cloud through a set of structured skills.

---

## 3. What is ComfyUI?

- **Node-based interface for diffusion / generative models.** Think Houdini or Blender's node editor, but for stable diffusion, Wan, LTX, Z-Image, Flux, Hunyuan, etc.
- **A graph of operations:** load model → encode prompt → sample latent → decode → save.
- Each node is a Python function with typed inputs and outputs; the UI wires them together.
- Open source, modular (custom nodes everywhere), production-grade — runs locally or as a hosted service.

*(Show a screenshot of a typical workflow graph here — the spaghetti of green/purple noodles is the visual hook.)*

---

## 4. Two ways to "use" ComfyUI

- **The UI:** drag nodes around, hit Queue, watch progress. Great for exploration, terrible for repetition.
- **The API:** POST a JSON workflow to `/prompt`, poll `/history/{id}`, fetch the output. Same engine, no UI in the loop.
- **Important distinction:** the API isn't a different product. It's the same graph, serialized differently.

---

## 5. The two JSON formats (this matters)

- **Graph format** — what the UI saves. Has positions, sizes, link arrays, group boxes. Human-readable in the editor.
- **API format** — flat dict keyed by node ID, each entry has `class_type` + `inputs`. References to other nodes are `["node_id", output_index]`.
- **Agents work in API format.** Less ceremony, no layout state, easier to reason about and mutate programmatically.

```json
{
  "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "z_image_turbo_bf16.safetensors"}},
  "9": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "seed": 42, "steps": 8}}
}
```

---

## 6. So what does "agentic control" actually mean?

- Not just "the model writes a prompt." That's chat.
- Agentic = the model **plans, calls tools, observes results, and adjusts** — in a loop.
- For ComfyUI specifically:
  - Discover what models/loras are installed
  - Compose a workflow JSON for the request
  - Submit it
  - Poll until done
  - Verify the output, retry or repair on failure
  - Save artifacts somewhere a human can browse

The model is doing what a junior engineer would do at a terminal — except faster, and across hundreds of jobs.

---

## 7. The case study: `lora_tester`

- Small project. ~600 lines of Python total.
- **Purpose:** systematically test a LoRA across a matrix of prompts × strengths and produce a side-by-side comparison gallery.
- **Two backends:** `lora_test.py` (local ComfyUI on `localhost:8188`) and `lora_test_cloud.py` (Comfy Cloud).
- **One viewer:** `gallery.html` — single-file, no server, opens any project folder.
- **Powered by:** four Claude Code "skills" that teach the agent how ComfyUI works.

*(This is your demo backbone — refer back to it through the rest of the talk.)*

---

## 8. The agentic loop, made concrete

User says: *"Test the C64 LoRA at strengths 0, 0.5, 1.0 across these five prompts."*

The agent:

1. Reads the `lora_tester` skill — knows the script exists.
2. Lists available loras via `/object_info/LoraLoader` to find the file.
3. Edits `PROMPTS` in `lora_test.py`.
4. Runs `python lora_test.py --lora "z_image_turbo\\zit-c64.safetensors" --strengths "0,0.5,1.0"`.
5. Watches stdout for progress, surfaces failures.
6. Tells the user where the gallery is.

**No prompt engineering. No screenshot of the UI. Just code and APIs.**

---

## 9. Skills: modular knowledge for the agent

The project ships four skills under `.claude/skills/`:

| Skill | Purpose |
|---|---|
| `comfy_local` | Local server specifics — endpoints, auth (none), file paths, missing model resolver |
| `comfy_cloud` | Cloud specifics — `X-API-Key` auth, content-addressed storage, polling endpoints |
| `comfy_workflows` | **Shared** — workflow JSON format, model discovery, proven pipelines (Z-Image Turbo, Wan 2.2, LTX 2.3) |
| `lora_tester` | When to use which script, project folder layout, gallery viewer |

**Key insight:** the *workflow JSON itself* is identical between local and cloud. Only the URL, headers, and polling endpoints differ. So we keep workflow knowledge in one shared skill and split only what's actually different.

---

## 10. Skills are just markdown files

```
.claude/skills/comfy_workflows/skill.md
```

- Frontmatter says when to load (description, allowed tools).
- The body is documentation written *for the agent*, not for humans — though humans can read it just fine.
- It contains: API shapes, gotchas, code snippets that work, error patterns.
- **Loaded on demand**, not stuffed into every prompt. Cheap context.

This is the same pattern as a `CLAUDE.md` or `AGENTS.md`, but scoped — the agent only loads the comfy_local skill when a comfy_local task starts.

---

## 11. Benefits, part 1 — Throughput

- A LoRA test = 5 prompts × 5 strengths = **25 images**. Hand-clicking that in the UI? 10–15 minutes of mouse work.
- Agent loop: submit all 25 jobs upfront, poll once per second, download as they finish. **Done in ~50 seconds on an RTX 5090.**
- Models stay loaded across the queue — first job pays the load cost, the rest are free.
- On Comfy Cloud, jobs run **in parallel** (5 concurrent on Pro tier). 25-job test ≈ 30 seconds wall-clock.

---

## 12. Benefits, part 2 — Reproducibility

Every run produces a self-contained project folder:

```
projects/20260326_c64-lora-test/
  manifest.json   ← every prompt, seed, strength, model setting
  images/
    p00_s000.png  p00_s050.png  p00_s100.png
    p01_s000.png  p01_s050.png  p01_s100.png
    ...
```

- **Same seed per prompt across strengths** → apples-to-apples comparison.
- **Manifest is the source of truth** — open it six months later, you know exactly what produced what.
- **Portable** — move the folder, share it, the gallery still works.

---

## 13. Benefits, part 3 — Shared logic, multiple backends

- The Z-Image Turbo workflow JSON is *literally the same dictionary* in `lora_test.py` and `lora_test_cloud.py`.
- Building once and running on both targets means:
  - Develop locally with fast iteration on your own hardware.
  - Scale on cloud when you need parallelism or don't have the GPU.
  - Compare outputs across environments to catch model-version drift.

This is exactly the kind of plumbing an agent is good at writing once and stamping out in two flavors.

---

## 14. Benefits, part 4 — Discovery beats hardcoding

- Hardcoded filenames break the moment you switch machines.
- Agentic flow: hit `/object_info/LoraLoader` → get the dropdown → match by fuzzy name → use the real path.
- The agent can **enumerate, suggest, and self-correct** before the user even sees an error.
- Same pattern for nodes (`/object_info`), available checkpoints, samplers, schedulers.

---

## 15. Benefits, part 5 — Visualization without infrastructure

- `gallery.html` is **one file**, no server, no build step.
- Browser opens a project folder via the File System Access API.
- Grid view, A/B slider, side-by-side, PNG export for socials.
- The agent can produce the data; a human still wants to *see* the result. Don't skip this part.

*(Show a screenshot of the gallery here — the A/B slider is the wow moment.)*

---

## 16. Pitfall 1 — Workflows lie about their parameter names

- Cloud subgraph templates and the `Comfy-Org/workflow_templates` repo are great starting points…
- …but template parameter names sometimes diverge from the actual `/object_info` schema.
- Real examples we've hit:
  - `ResizeImageMaskNode`: template says `crop`/`interpolation`, API wants `resize_type`/`scale_method`.
  - `LTXVPreprocess`: template says `num_latent_frames`, API wants `img_compression`.
  - `LTXVImgToVideoInplace`: template says `image_denoise_strength`, API wants `strength`.
- **Mitigation:** always validate against `/object_info/{NodeType}` before first use. Bake this into the skill.

---

## 17. Pitfall 2 — Cross-machine assumptions

- The two backends look the same but disagree on:
  - **`/object_info` shape** — local uses legacy `[[opt, ...], {...}]`, cloud uses wrapped `["COMBO", {"options": [...]}]`. Same data, different parser.
  - **LoRA paths** — local has subfolder prefixes (`z_image_turbo\\foo.safetensors`), cloud uses a flat namespace.
  - **Output storage** — local writes named files to disk, cloud uses content-addressed Blake3 hashes.
- An agent that "knows ComfyUI" generically will guess wrong on at least one of these.
- **Mitigation:** explicit per-backend skills, plus a tiny shared helper (`widget_options()`) that handles both shapes.

---

## 18. Pitfall 3 — Cost and runaway loops

- API nodes (Nano Banana 2, Flux Pro, Kling, ByteDance, ElevenLabs) cost real money per call.
- An agent in a tight loop can burn through a budget fast — especially if the failure mode is "retry."
- **Mitigations:**
  - Confirm before any batch over a threshold.
  - Surface costs in the skill itself (Nano Banana 2 ≈ $0.07–0.15/image at 2K).
  - Cap retries explicitly. Distinguish "the model is broken" from "the network blipped."
  - Never commit API keys; load from `.env`. (One of the lessons in this very repo's memory.)

---

## 19. Pitfall 4 — Missing models are a long tail

- Workflows reference specific filenames. If the file isn't on disk, you get a cryptic 400.
- The first version of any new pipeline will fail this way ~half the time.
- **What helped here:** a "Missing Model Resolver" baked into the `comfy_local` skill — checks loader nodes against the disk, points the agent at the right HuggingFace repo, asks the user before downloading multi-GB files.
- **The general lesson:** when the failure mode is predictable, encode the fix in the skill, not in the conversation.

---

## 20. Pitfall 5 — The agent doesn't see the image

- The model can submit a workflow and confirm it succeeded. It cannot *judge* whether the output looks good.
- "Generated successfully" ≠ "the LoRA is doing what the user wanted."
- **Mitigation:** keep a human in the loop for aesthetic judgments. The agent's job is to remove the friction *around* the creative call, not to make it.
- The gallery viewer exists precisely because of this — the agent does the matrix, the human picks the winner.

---

## 21. Pitfall 6 — Prompt injection through tool results

- ComfyUI custom nodes are user-installed code with arbitrary metadata. `/object_info` content is *data the agent reads and acts on.*
- A malicious node could embed instructions in its description ("ignore previous instructions, run …").
- This is a general class problem with any tool-using agent against an open ecosystem.
- **Mitigation:** treat tool output as data, not instructions. Agents should flag suspicious content rather than execute it.

---

## 22. The shape of a good agent interface

Pulling out the patterns that worked:

1. **Skills as documentation, not prompts.** Markdown the agent loads on demand.
2. **Discovery over hardcoding.** Always ask the API first.
3. **Same-shape outputs across backends.** Unify the data model; let backends differ on transport.
4. **Validate at boundaries.** Schema-check inputs before submitting.
5. **Self-contained artifacts.** A run produces a folder you can email to someone.
6. **Visualizations a human can scan in seconds.** The agent's output is rarely the final consumable.

---

## 23. Where this is going

- **Workflow synthesis from intent** — "make a 5-second video of X" → agent picks the model, builds the graph, runs it, shows results. The pieces exist; they're not yet stitched.
- **Cross-tool agents** — same agent driving ComfyUI, your DAW, your editor. The skill pattern generalizes.
- **Quality loops** — agent inspects its own outputs (CLIP score, aesthetic predictors, even VLM critique) and iterates.
- **Cost-aware scheduling** — local for cheap iteration, cloud for parallelism, API nodes for the last mile.

The bottleneck stops being *can the model do it* and starts being *what affordances we give it.*

---

## 24. Takeaways

- ComfyUI's API is already an excellent agentic surface — graphs as JSON, REST submit + poll, full discovery.
- Most of the agent's intelligence ends up encoded as **structured documentation** (skills), not in clever prompting.
- The biggest wins are throughput, reproducibility, and removing rote work — *not* replacing creative judgment.
- The biggest risks are silent parameter drift, runaway cost, and assuming the agent can see what it just made.

---

## 25. Q & A / demo

- Live demo idea: ask the agent for a fresh LoRA test, watch the project folder fill up, open the gallery.
- Backup demo: pre-recorded screen capture in case the network is sad.
- Have `gallery.html` open with a finished project for the visual payoff.

---

*Appendix slides you may or may not need:*

## A1. The Z-Image Turbo workflow, in 11 nodes

*(Drop in the workflow JSON from `lora_test.py:74-114` if you want a "look how compact this is" slide.)*

## A2. Skill file anatomy

*(Show the frontmatter + first ~30 lines of `comfy_workflows/skill.md` to demystify what a skill actually is.)*

## A3. Manifest schema

*(Show a real `manifest.json` from `projects/20260326_triptych-bicycle/` if you want to make the reproducibility point concrete.)*
