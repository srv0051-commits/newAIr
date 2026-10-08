# newAIr Pause / Rebuild Kit

Project: `D:\\newAIr_v0.3_image_studio`
Python: 3.12
GPU: NVIDIA RTX 3050 Laptop GPU, 6 GB VRAM
Launch: activate `venv`, then run `python app.py`

## Before deleting anything
1. Stop the app.
2. Back up `data\\newair.db`; if present, also preserve `newair.db-wal` and `newair.db-shm` together while the app is stopped.
3. Keep this folder, your source code, and a private copy of `.env` if used.
4. Do not commit database files, secrets, model weights, generated images, or the venv to GitHub.

## Safe space-saving options
- Delete the project `venv\\` only after recording `pip freeze` and `pip list`.
- Delete model weights only if you're happy to download them again before resuming.
- Hugging Face and InsightFace caches can be downloaded again later.
- Keep `data\\newair.db` to preserve characters, conversations, memory, lore, and history.
- Keep the NVIDIA graphics driver.

## CUDA caution
Do not manually delete CUDA folders or DLLs from Program Files. PyTorch wheels may ship their own CUDA runtime, and llama.cpp GPU support has its own build requirements. For the safest cleanup, remove the project venv and AI model/cache files first. Only uninstall a separately installed CUDA Toolkit through Windows Installed Apps if you know no other software needs it. Never uninstall the NVIDIA display driver as part of this cleanup.
