import os

from flask import Blueprint, jsonify, request, abort

import config
from core.llm_engine import engine, LLAMA_CPP_AVAILABLE, LLAMA_CPP_ERROR

bp = Blueprint("models", __name__, url_prefix="/api/models")


@bp.get("")
def list_models():
    os.makedirs(config.MODELS_DIR, exist_ok=True)
    files = [f for f in os.listdir(config.MODELS_DIR) if f.lower().endswith(".gguf")]
    return jsonify({
        "models_dir": config.MODELS_DIR,
        "available": sorted(files),
        "loaded": engine.model_path,
        "llama_cpp_installed": LLAMA_CPP_AVAILABLE,
        "llama_cpp_error": LLAMA_CPP_ERROR,
        "gpu_layers": config.N_GPU_LAYERS,
        "context_tokens": config.N_CTX,
        "last_load_error": getattr(engine, "last_error", ""),
    })


@bp.post("/load")
def load_model():
    data = request.get_json(force=True) or {}
    filename = data.get("filename")
    if not filename:
        abort(400, "filename is required")
    path = os.path.join(config.MODELS_DIR, filename)
    if not os.path.isfile(path):
        abort(404, f"{filename} not found in {config.MODELS_DIR}")
    try:
        loaded = engine.load_model(path)
        return jsonify({"loaded": loaded, "message": f"Loaded {os.path.basename(loaded)}", "load_warning": engine.last_error or None})
    except Exception as exc:
        return jsonify({"error": "model_load_failed", "message": str(exc), "filename": filename}), 500
