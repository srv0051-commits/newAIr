import json, os
from flask import Blueprint, request, jsonify, abort
from core.image_engine import image_engine, MODEL_PROFILES, SCHEDULERS
from core.database import db_cursor, now
from core.llm_engine import engine as text_engine
import config

bp=Blueprint("images",__name__,url_prefix="/api/images")

def _save_meta(result,data,character_id=None,parent_id=None):
    with db_cursor() as cur:
        cur.execute("""INSERT INTO image_generations
        (filename,model,model_family,prompt,negative_prompt,width,height,steps,guidance,sampler,seed,quality,hires_enabled,hires_scale,hires_denoise,strength,loras,character_id,parent_id,generation_ms,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (result["url"].split("/")[-1],result.get("model",""),result.get("model_family",""),data.get("prompt","")[:12000],data.get("negative_prompt","")[:8000],int(result.get("width",data.get("width",512))),int(result.get("height",data.get("height",512))),int(data.get("steps",24)),float(data.get("guidance",5)),result.get("sampler",data.get("sampler","")),int(result.get("seed",data.get("seed",-1))),data.get("quality","balanced"),int(bool(data.get("hires",False))),float(data.get("hires_scale",1.5)),float(data.get("hires_denoise",.35)),data.get("strength"),json.dumps(result.get("loras",data.get("loras",[]))),character_id,parent_id,int(result.get("generation_ms",0)),now()))
        return cur.lastrowid

def _row(r):
    d=dict(r); d["url"]="/static/generated/"+d.pop("filename")
    try:d["loras"]=json.loads(d.get("loras") or "[]")
    except Exception:d["loras"]=[]
    return d

@bp.get("")
def status():
    return jsonify({"backend_available":image_engine.available,"models":image_engine.list_models(),"loras":image_engine.list_loras(),"loaded":image_engine.model_path,"profile":image_engine.profile(),"gpu":image_engine.gpu_status(),"samplers":list(SCHEDULERS),"error":image_engine.error})

@bp.get("/profiles")
def profiles(): return jsonify(MODEL_PROFILES)

@bp.get("/loras")
def loras(): return jsonify(image_engine.list_loras())

@bp.get("/gpu")
def gpu(): return jsonify(image_engine.gpu_status())

@bp.post("/load")
def load():
    name=(request.get_json(force=True) or {}).get("name")
    if not name: abort(400,"name is required")
    if str(name).strip().lower() == "inpainting":
        abort(400,"The inpainting model is not a normal generation model. Open the Inpaint tab and use the dedicated inpainting action.")
    return jsonify({"loaded":image_engine.load(name),"profile":image_engine.profile()})

@bp.post("/unload")
def unload(): image_engine.unload(); return jsonify({"unloaded":True})

@bp.post("/token-info")
def token_info(): return jsonify(image_engine.token_info((request.get_json(force=True) or {}).get("text","")[:20000]))

@bp.post("/enhance-prompt")
def enhance_prompt():
    data=request.get_json(force=True) or {}; prompt=(data.get("prompt") or "").strip()
    if not prompt: abort(400,"prompt is required")
    if data.get("mode") == "edit":
        system=("You are a local image-edit prompt compressor. Convert the user's edit instruction into a concise comma-separated diffusion prompt. "
                "Preserve exactly what the user wants changed and explicitly preserve everything they say should remain. "
                "Do not invent objects, people, clothing, actions, locations or style changes. Remove filler and repetition. "
                "Keep the result under 65 CLIP tokens when practical. Return only the final prompt, no commentary.")
    else:
        system=("You are a local image prompt director. Expand the user's visual idea into one concise diffusion prompt. "
                "Preserve every explicit subject and constraint. Add only useful details for composition, lighting, camera, materials and environment. "
                "Do not add characters, clothing, actions or story facts that contradict the user. Return only the final prompt, no commentary.")
    try:
        text=text_engine.generate([{"role":"system","content":system},{"role":"user","content":prompt}],temperature=.55,top_p=.9,max_tokens=220,stream=False)
        return jsonify({"prompt":text.strip()})
    except Exception as e: abort(500,f"Prompt enhancer failed: {e}")

@bp.post("/generate")
def generate():
    data=request.get_json(force=True) or {}; prompt=(data.get("prompt") or "").strip()
    if not prompt: abort(400,"prompt is required")
    count=max(1,min(int(data.get("batch",1)),4)); results=[]; parent=None
    for i in range(count):
        d=dict(data)
        if int(d.get("seed",-1))>=0: d["seed"]=int(d["seed"])+i
        result=image_engine.generate(prompt,d.get("negative_prompt",""),int(d.get("width",1024)),int(d.get("height",576)),int(d.get("steps",28)),float(d.get("guidance",5.5)),int(d.get("seed",-1)),d.get("sampler","DPM++ 2M Karras"),d.get("quality","balanced"),d.get("loras",[]),bool(d.get("hires",False)),float(d.get("hires_scale",1.5)),float(d.get("hires_denoise",.30)),character_mode=bool(d.get("character_id")),style=d.get("style",""))
        gid=_save_meta(result,d,d.get("character_id") or None,parent); result["id"]=gid; parent=gid; results.append(result)
    return jsonify({"results":results,**results[0]})

@bp.post("/img2img")
def img2img():
    data=request.get_json(force=True) or {}; prompt=(data.get("prompt") or "").strip(); image_data=data.get("image_data") or ""
    if not prompt or not image_data: abort(400,"prompt and image_data are required")
    result=image_engine.img2img(prompt,data.get("negative_prompt",""),image_data,float(data.get("strength",.55)),int(data.get("steps",20)),float(data.get("guidance",5)),int(data.get("seed",-1)),data.get("sampler","DPM++ 2M Karras"),data.get("loras",[]),data.get("style",""),data.get("edit_mode","general"))
    result["id"]=_save_meta(result,data,data.get("character_id") or None,data.get("parent_id") or None)
    return jsonify(result)

@bp.post("/outpaint")
def outpaint():
    data=request.get_json(force=True) or {}
    prompt=(data.get("prompt") or "").strip(); image_data=data.get("image_data") or ""
    if not prompt: abort(400,"prompt is required")
    if not image_data: abort(400,"source image is required")
    result=image_engine.outpaint(prompt,image_data,data.get("direction","down"),int(data.get("pixels",512)),int(data.get("steps",30)),float(data.get("guidance",5.2)),int(data.get("seed",-1)),data.get("sampler","DPM++ 2M Karras"),data.get("style",""))
    result["id"]=_save_meta(result,data,data.get("character_id") or None,data.get("parent_id") or None)
    return jsonify(result)


@bp.get("/faceid/status")
def faceid_status(): return jsonify(image_engine.faceid_status())

@bp.post("/face-to-scene")
def face_to_scene():
    data=request.get_json(force=True) or {}
    prompt=(data.get("prompt") or "").strip(); image_data=data.get("image_data") or ""
    if not prompt or not image_data: abort(400,"prompt and face image are required")
    result=image_engine.face_to_scene(prompt,data.get("negative_prompt",""),image_data,float(data.get("identity_strength",.9)),int(data.get("steps",28)),float(data.get("guidance",5.5)),int(data.get("seed",-1)),data.get("style","photorealistic"),int(data.get("width",768)),int(data.get("height",1024)),data.get("model_name") or None)
    result["id"]=_save_meta(result,data,data.get("character_id") or None,data.get("parent_id") or None)
    return jsonify(result)

@bp.get("/inpaint/status")
def inpaint_status(): return jsonify(image_engine.inpaint_status())

@bp.post("/inpaint")
def inpaint():
    data=request.get_json(force=True) or {}
    prompt=(data.get("prompt") or "").strip(); image_data=data.get("image_data") or ""; mask_data=data.get("mask_data") or ""
    if not prompt: abort(400,"prompt is required")
    if not image_data: abort(400,"source image is required")
    if not mask_data: abort(400,"mask is required")
    result=image_engine.inpaint(prompt,data.get("negative_prompt",""),image_data,mask_data,int(data.get("steps",30)),float(data.get("guidance",5.5)),int(data.get("seed",-1)),data.get("sampler","DPM++ 2M Karras"),int(data.get("padding",96)),int(data.get("feather",4)),int(data.get("mask_expand",8)))
    result["id"]=_save_meta(result,data,data.get("character_id") or None,data.get("parent_id") or None)
    return jsonify(result)

@bp.get("/history")
def history():
    limit=max(1,min(int(request.args.get("limit",40)),200)); offset=max(0,int(request.args.get("offset",0)))
    with db_cursor() as cur:
        cur.execute("SELECT * FROM image_generations ORDER BY created_at DESC LIMIT ? OFFSET ?",(limit,offset)); rows=cur.fetchall()
    return jsonify([_row(r) for r in rows])

@bp.get("/history/<int:gid>")
def history_one(gid):
    with db_cursor() as cur: cur.execute("SELECT * FROM image_generations WHERE id=?",(gid,)); r=cur.fetchone()
    if not r: abort(404)
    return jsonify(_row(r))

@bp.put("/history/<int:gid>")
def history_update(gid):
    data=request.get_json(force=True) or {}; favorite=data.get("favorite")
    if favorite is None: abort(400,"favorite is required")
    with db_cursor() as cur: cur.execute("UPDATE image_generations SET favorite=? WHERE id=?",(int(bool(favorite)),gid))
    return jsonify({"ok":True,"favorite":bool(favorite)})

@bp.delete("/history/<int:gid>")
def history_delete(gid):
    with db_cursor() as cur:
        cur.execute("SELECT filename FROM image_generations WHERE id=?",(gid,)); r=cur.fetchone()
        if not r: abort(404)
        cur.execute("DELETE FROM image_generations WHERE id=?",(gid,))
    path=os.path.realpath(os.path.join(config.GENERATED_IMAGES_DIR,os.path.basename(r["filename"])))
    root=os.path.realpath(config.GENERATED_IMAGES_DIR)
    if os.path.commonpath([root,path])==root:
        try: os.remove(path)
        except OSError: pass
    return "",204
