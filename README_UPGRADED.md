# newAIr upgraded image studio

This build keeps the local-first architecture and adds a substantially richer image workflow.

## Added

- Model profiles for SDXL/Pony/SD 1.5
- Sampler selection: DPM++ 2M Karras, DPM++ SDE Karras, Euler A, Euler, DDIM, UniPC
- Fast / Balanced / High presets tuned for a 6 GB GPU
- Aspect-ratio presets
- Seed randomization and seed locking
- Batch generation up to 4 sequential images
- Hires refinement pass
- Local LoRA library and per-LoRA strength controls
- Prompt Studio and token budget meter
- Dolphin prompt enhancement
- Character visual identity fields
- Character-aware image prompt building
- Scene Builder
- Generation metadata database
- Generation gallery/history
- Favorite and remix workflows
- GPU status display
- Safer local model path handling
- Image upload size limits
- Memory categories/importance and search-ready memory API

## Optional future model packs

ControlNet, IP-Adapter and dedicated inpainting require additional local model weights. The current app deliberately does not download them automatically. The image-engine architecture leaves room for those adapters without changing the character/database layer.

## Run

```powershell
cd "C:\Users\srv00\Downloads\newAIr_v0.3_image_studio"
.\venv\Scripts\Activate.ps1
python app.py
```

Keep your existing `data/newair.db`, `models_dir`, `image_models`, `loras`, and `static/generated` when replacing the source files.
