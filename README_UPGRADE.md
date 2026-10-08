# newAIr Image Studio upgrade

This build adds a larger local Image Studio around the existing newAIr character/assistant app.

## Added

- Model profiles for SDXL, Pony and SD 1.5
- Sampler/scheduler selector
- Safe resolution/pixel budgets for a 6 GB GPU
- Aspect-ratio presets
- Prompt Studio with structured fields
- Prompt token meter
- Local Dolphin prompt enhancement
- Seed randomization/locking
- Batch generation (2 variations)
- Hires second-pass generation
- Local LoRA discovery and weight controls
- Image generation metadata in SQLite
- Gallery with favorites
- Reopen/reuse previous generation settings
- VRAM status
- Safer local model paths
- Request upload-size limit
- Flask DB connection cleanup
- Image model and LoRA directories configurable through environment variables

## Folders

Put base image checkpoints in:

    image_models/

Put LoRA `.safetensors` files in:

    lora_models/

Put GGUF chat models in:

    models_dir/

## GPU notes

The defaults are deliberately conservative for an RTX 3050 6 GB laptop GPU.
The Hires pass is a second diffusion pass, so it is slower, but it avoids trying to
generate a huge image in one VRAM-heavy pass.

## Optional weighted-prompt / ControlNet / IP-Adapter extensions

The current build keeps those behind optional model/dependency requirements rather than
silently downloading anything. This preserves the local/offline design and avoids
turning a working 6 GB setup into a dependency swamp.
