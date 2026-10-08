# newAIr Image Quality Update

This build keeps the existing three local checkpoints and applies model-specific generation settings:

- `CyberRealisticPony_V18.0_F16.safetensors` -> Pony/SDXL profile, score conditioning, CLIP skip 2 when supported, CFG 5, DPM++ 2M Karras default.
- `RealVisXL_V5.0_f16.safetensors` -> SDXL profile, DPM++ SDE Karras default, targeted negative prompt.
- `realisticVisionV60B1_v60B1VAE.safetensors` -> SD 1.5 profile, DPM++ SDE Karras default, targeted negative prompt.

## New generation behavior

- Model-specific prompt conditioning instead of one generic prompt recipe.
- Model-specific negative prompts.
- Character identity lock based on the saved character appearance.
- Portrait/half-body/full-body/cinematic framing control.
- Optional localized face-refinement pass using the currently loaded checkpoint.
- Automatic one-time portrait retry if no face is detected.
- Quality ladder tuned for a 6 GB RTX 3050:
  - Fast: base generation.
  - Balanced: base + face refinement.
  - High: base + Hires refinement + face refinement.
- Hires refinement stays low-denoise to avoid destroying good facial structure.
- Existing database/history is not touched by these changes.

## Face refinement dependency

The face refinement pass uses OpenCV's bundled Haar cascade. If your existing venv does not already contain OpenCV, run from the project folder:

```powershell
python -m pip install opencv-python
```

A small fallback is built in: if face detection/refinement cannot run, the original generated image is kept instead of failing the generation.

## Important

Do not copy a new database into `data\`. Keep your existing `data\newair.db`, `newair.db-wal`, and `newair.db-shm`.
