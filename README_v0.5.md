# newAIr v0.5 Stability & Performance

This build upgrades the v0.4 image/character studio with a stronger runtime layer focused on reliability on 6 GB GPUs.

## Main upgrades

- Exact model profiles for the model selector instead of always falling back to SDXL defaults.
- Explicit database schema version marker and in-place migrations.
- SQLite WAL + busy timeout + application-context connection cleanup.
- Accurate random seed generation. The actual seed used is returned and stored.
- LoRA adapter caching. Repeated generations with the same LoRA configuration reuse the loaded adapters.
- Safer LoRA activation. Incompatible adapters are rejected without calling `set_adapters()` on missing names.
- GPU memory recovery: generation can retry at a reduced resolution after CUDA OOM.
- Hires refinement can gracefully fall back to the base image if the second pass exceeds VRAM.
- Atomic PNG saving to prevent gallery/database entries from pointing at half-written files.
- Generation progress endpoint and cancellation endpoint.
- Img2img now receives sampler, LoRAs, character and parent-generation metadata from the UI.
- Img2img and Hires use fresh pipelines from shared components and clean them up after the operation.
- JSON API error responses instead of Flask HTML tracebacks for `/api/*` failures.
- Built-in image diagnostics endpoint and UI button.
- Safer GGUF model path handling.
- Added dependency-free syntax validation checks.

## Upgrade existing installation

Back up your existing project first. Copy the application files from this package into the existing newAIr folder. Keep these folders from your current installation:

- `venv/`
- `data/`
- `image_models/`
- `models_dir/`
- `loras/`
- `static/generated/`

Do not overwrite `data/newair.db`. The application migrates it in place.

Start with:

```powershell
cd "D:\newAIr_v0.3_image_studio"
.\venv\Scripts\Activate.ps1
python app.py
```

## Diagnostics

In Image Studio, use **Run diagnostics**. It checks the local image backend, loaded model, Diffusers/Transformers/Accelerate versions, GPU availability, current LoRAs and generation state.

## Optional tests

```powershell
python -m pytest
```

The package source is also safe to compile with:

```powershell
python -m compileall -q .
```
