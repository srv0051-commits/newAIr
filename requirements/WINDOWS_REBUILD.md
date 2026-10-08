# Windows rebuild guide

## Prerequisites
- Windows 10/11, Git for Windows, Python 3.12
- NVIDIA graphics driver if using the GPU
- Local model weights for the features you want to run

## Clone / update source
```powershell
git clone https://github.com/srv0051-commits/newAIr.git D:\\newAIr_v0.3_image_studio
cd D:\\newAIr_v0.3_image_studio
```
If already cloned, use `git pull` instead.

## Create a fresh venv
```powershell
py -3.12 -m venv venv
.\\venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
```
If activation is blocked:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\\venv\\Scripts\\Activate.ps1
```

## Capture the exact environment BEFORE deleting the old venv
Run these while the existing venv still works:
```powershell
python --version
python -m pip freeze > requirements\\pip-freeze-current.txt
python -m pip list --format=json > requirements\\pip-list-current.json
python -m pip show torch torchvision torchaudio diffusers transformers accelerate peft llama-cpp-python insightface onnxruntime-gpu
nvidia-smi
```
This exact snapshot is more reliable than the starter lists in this folder. Native CUDA runtimes and special llama.cpp builds may still need separate notes.

## Install starter requirements
```powershell
python -m pip install -r requirements\\requirements-core.txt
python -m pip install -r requirements\\requirements-llm.txt
python -m pip install -r requirements\\requirements-faceid.txt
```
Note: default `llama-cpp-python` installation may be CPU-only. Do not assume this restores GPU acceleration.

## Restore data and models
Restore your backed-up `data\\newair.db` and any associated WAL/SHM files while the app is stopped. Restore only the model weights required for the features you want. Never replace your database with a blank one.

## Launch and smoke-test
```powershell
python -m pip check
python -m compileall core routes
python app.py
```
Manually test character chat, initial messages, response length, rolling memory, image generation, inpainting, and FaceID after restoring their models.
