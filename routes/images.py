from flask import Blueprint, request, jsonify, abort
from core.image_engine import image_engine

bp=Blueprint("images",__name__,url_prefix="/api/images")

@bp.get("")
def status():
    return jsonify({"backend_available":image_engine.available,"models":image_engine.list_models(),"loaded":image_engine.model_path,"error":image_engine.error})

@bp.post("/load")
def load():
    data=request.get_json(force=True) or {}; name=data.get("name")
    if not name: abort(400,"name is required")
    return jsonify({"loaded":image_engine.load(name)})

@bp.post("/unload")
def unload():
    image_engine.unload(); return jsonify({"unloaded":True})

@bp.post("/generate")
def generate():
    data=request.get_json(force=True) or {}; prompt=(data.get("prompt") or "").strip()
    if not prompt: abort(400,"prompt is required")
    url=image_engine.generate(prompt,data.get("negative_prompt", ""),int(data.get("width",512)),int(data.get("height",512)),int(data.get("steps",24)),float(data.get("guidance",5.0)),int(data.get("seed",-1)))
    return jsonify({"url":url})


@bp.post("/img2img")
def img2img():
    data=request.get_json(force=True) or {}
    prompt=(data.get("prompt") or "").strip()
    image_data=data.get("image_data") or ""
    if not prompt: abort(400,"prompt is required")
    if not image_data: abort(400,"image_data is required")
    url=image_engine.img2img(
        prompt, data.get("negative_prompt",""), image_data,
        float(data.get("strength",0.55)), int(data.get("steps",20)),
        float(data.get("guidance",5.0)), int(data.get("seed",-1))
    )
    return jsonify({"url":url})

@bp.post("/inpaint")
def inpaint():
    data=request.get_json(force=True) or {}
    prompt=(data.get("prompt") or "").strip()
    image_data=data.get("image_data") or ""
    mask_data=data.get("mask_data") or ""
    if not prompt: abort(400,"prompt is required")
    if not image_data: abort(400,"image_data is required")
    if not mask_data: abort(400,"mask_data is required")

    url=image_engine.inpaint(
        prompt,
        data.get("negative_prompt",""),
        image_data,
        mask_data,
        float(data.get("strength",0.75)),
        int(data.get("steps",24)),
        float(data.get("guidance",5.0)),
        int(data.get("seed",-1))
    )
    return jsonify({"url":url})
