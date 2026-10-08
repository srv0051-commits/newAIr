# newAIr Face → Full Scene setup

This build adds a **Face → Full Scene** Image Studio tab. It is designed for the local SD 1.5 RealisticVision model and IP-Adapter FaceID Plus V2.

## 1. Adapter files

Put the two FaceID files you already downloaded here:

```text
models\ip_adapter\faceid\
    ip-adapter-faceid-plusv2_sd15.bin
    ip-adapter-faceid-plusv2_sd15_lora.safetensors
```

## 2. CLIP image encoder

Put the `config.json` and `model.safetensors` you downloaded from the CLIP ViT-H image encoder page here:

```text
models\ip_adapter\faceid\image_encoder\
    config.json
    model.safetensors
```

Do **not** download `pytorch_model.bin` if you already have `model.safetensors`.

## 3. Python packages

Activate your existing newAIr venv and run:

```powershell
python -m pip install -U diffusers transformers accelerate safetensors opencv-python insightface onnxruntime-gpu
```

If `onnxruntime-gpu` causes a CUDA/runtime issue, use the CPU fallback instead:

```powershell
python -m pip uninstall -y onnxruntime-gpu
python -m pip install -U onnxruntime
```

## 4. InsightFace buffalo_l

The FaceID implementation uses InsightFace's `buffalo_l` face model to extract the identity embedding. The first time InsightFace initializes it may download `buffalo_l`; after that it can be used locally.

newAIr expects the InsightFace root at:

```text
models\insightface\
```

InsightFace normally stores the model under:

```text
models\insightface\models\buffalo_l\
```

If `buffalo_l` is already installed in your normal InsightFace cache, the application can use that cache instead.

## 5. Base image model

The Face → Full Scene tab uses your existing **RealisticVision V6.0 SD 1.5** checkpoint. You do not need another diffusion checkpoint for this first version.

## What the feature does

Upload a clear face and describe a completely new scene, for example:

```text
Full-body photograph of the person standing barefoot on a tropical beach at sunset,
wearing a loose white linen shirt and beige trousers, relaxed natural pose,
ocean behind them, realistic proportions and natural lighting.
```

The face is used as the identity reference. The body, clothes, pose and environment are generated from the prompt.

## Important limitation

A single face image does not contain the person's real body information. The generated body is therefore invented by the diffusion model. FaceID improves identity consistency, but it cannot guarantee a pixel-perfect reproduction of the person's real face or body in every generation.

## Database safety

This feature does not require a database migration. Keep your existing `data\newair.db`, `newair.db-wal`, and `newair.db-shm` untouched.


## Switching the Face -> Full Scene generation model

FaceID Plus V2 uses a model-family-specific adapter. The current SD1.5 adapter works with RealisticVision V6.0. For CyberRealisticPony and RealVisXL, which are SDXL-family checkpoints, also download:

- `ip-adapter-faceid-plusv2_sdxl.bin`
- `ip-adapter-faceid-plusv2_sdxl_lora.safetensors`

Put both files directly in `models\ip_adapter\faceid\`. The same CLIP image encoder and InsightFace/buffalo_l setup are shared. The Face -> Full Scene panel will then let you choose among compatible local generation models and will disable models whose matching FaceID adapter is not installed.
