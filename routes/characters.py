from flask import Blueprint, request, jsonify, abort
import base64, io, os, uuid, json, re
from PIL import Image
from core.database import db_cursor, now
from core import memory_manager, lorebook
from core.llm_engine import engine as text_engine
from core.character_visuals import fallback_image_prompt, extract_json_object

bp=Blueprint("characters",__name__,url_prefix="/api/characters")
FIELDS=("name","description","tags","personality","appearance","background","scenario","greeting","example_dialogue","system_prompt","creator_notes","avatar_path","visual_style","negative_prompt","preferred_lora","reference_images","initial_messages","image_preset")

@bp.get("")
def list_characters():
    with db_cursor() as cur:
        cur.execute("SELECT * FROM characters WHERE id!=0 ORDER BY updated_at DESC,id DESC")
        return jsonify([dict(r) for r in cur.fetchall()])

@bp.post("")
def create_character():
    data=request.get_json(force=True) or {}; name=(data.get("name") or "").strip()
    if not name: abort(400,"name is required")
    
    # Janitor-style initial messages are stored as a JSON array. Keep the old
    # single greeting field working for existing characters/imports.
    initial_messages=data.get("initial_messages", None)
    if initial_messages is None:
        initial_messages=[]
        if data.get("greeting"):
            initial_messages=[data.get("greeting")]
    elif isinstance(initial_messages, str):
        try: initial_messages=json.loads(initial_messages)
        except Exception: initial_messages=[initial_messages]
    initial_messages=[str(x).strip() for x in (initial_messages or []) if str(x).strip()][:10]
    data["initial_messages"]=json.dumps(initial_messages, ensure_ascii=False)
    if initial_messages and not data.get("greeting"):
        data["greeting"]=initial_messages[0]
    values=[name]+[data.get(k,"") for k in FIELDS[1:]]; t=now()
    with db_cursor() as cur:
        cur.execute(f"INSERT INTO characters({','.join(FIELDS)},created_at,updated_at) VALUES({','.join(['?']*len(FIELDS))},?,?)",(*values,t,t))
        cur.execute("SELECT * FROM characters WHERE id=?",(cur.lastrowid,)); row=dict(cur.fetchone())
    return jsonify(row),201


@bp.post("/avatar/crop")
def save_cropped_avatar():
    data=request.get_json(force=True) or {}
    data_url=(data.get("data_url") or "").strip()
    if not data_url.startswith("data:image/") or "," not in data_url:
        abort(400,"valid image data is required")
    try:
        raw=base64.b64decode(data_url.split(",",1)[1])
        image=Image.open(io.BytesIO(raw)).convert("RGB")
        if image.width < 1 or image.height < 1:
            abort(400,"invalid image")
        image.thumbnail((1024,1024), Image.Resampling.LANCZOS)
        os.makedirs("static/generated", exist_ok=True)
        filename=f"avatar_{uuid.uuid4().hex}.png"
        path=os.path.join("static","generated",filename)
        image.save(path,"PNG",optimize=True)
        return jsonify({"url":"/static/generated/"+filename})
    except Exception as e:
        abort(400,f"could not save cropped image: {e}")

@bp.get("/<int:char_id>")
def get_character(char_id):
    with db_cursor() as cur: cur.execute("SELECT * FROM characters WHERE id=?",(char_id,)); row=cur.fetchone()
    if not row: abort(404)
    return jsonify(dict(row))

@bp.put("/<int:char_id>")
def update_character(char_id):
    data=request.get_json(force=True) or {}; fields={k:data[k] for k in FIELDS if k in data}
    if "name" in fields:
        fields["name"]=(fields["name"] or "").strip()
        if not fields["name"]: abort(400,"name cannot be empty")
    if "initial_messages" in fields:
        raw=fields["initial_messages"]
        if isinstance(raw,str):
            try: raw=json.loads(raw)
            except Exception: raw=[raw]
        raw=[str(x).strip() for x in (raw or []) if str(x).strip()][:10]
        fields["initial_messages"]=json.dumps(raw,ensure_ascii=False)
        if raw and not fields.get("greeting"):
            fields["greeting"]=raw[0]
    if not fields: abort(400,"no updatable fields provided")
    fields["updated_at"]=now(); cols=", ".join(f"{k}=?" for k in fields)
    with db_cursor() as cur:
        cur.execute(f"UPDATE characters SET {cols} WHERE id=?",(*fields.values(),char_id))
        cur.execute("SELECT * FROM characters WHERE id=?",(char_id,)); row=cur.fetchone()
    if not row: abort(404)
    return jsonify(dict(row))

@bp.delete("/<int:char_id>")
def delete_character(char_id):
    if char_id==0: abort(400,"cannot delete assistant sentinel")
    with db_cursor() as cur: cur.execute("DELETE FROM characters WHERE id=?",(char_id,))
    return "",204

@bp.get("/<int:char_id>/memories")
def list_memories(char_id):
    q=request.args.get("q","")
    return jsonify(memory_manager.search_character_memories(char_id,q))

@bp.post("/<int:char_id>/memories")
def add_memory(char_id):
    data=request.get_json(force=True) or {}; fact=(data.get("fact") or "").strip()
    if not fact: abort(400,"fact is required")
    mid=memory_manager.add_character_memory(char_id,fact,data.get("category","general"),data.get("importance",1)); return jsonify({"id":mid,"fact":fact}),201

@bp.delete("/memories/<int:memory_id>")
def delete_memory(memory_id): memory_manager.delete_character_memory(memory_id); return "",204

@bp.get("/<int:char_id>/lorebook")
def list_lore(char_id): return jsonify(lorebook.get_entries(char_id))

@bp.post("/<int:char_id>/lorebook")
def create_lore(char_id):
    data=request.get_json(force=True) or {}; title=(data.get("title") or "").strip(); content=(data.get("content") or "").strip(); keywords=data.get("keywords") or []
    if not title or not content or not keywords: abort(400,"title, content, and at least one keyword are required")
    return jsonify({"id":lorebook.create_entry(char_id,title,keywords,content,priority=data.get("priority",0),enabled=data.get("enabled",True))}),201

@bp.put("/lorebook/<int:entry_id>")
def update_lore(entry_id):
    data=request.get_json(force=True) or {}; fields={k:data[k] for k in ("title","keywords","content","priority","enabled") if k in data}
    lorebook.update_entry(entry_id,**fields); return jsonify({"ok":True})

@bp.delete("/lorebook/<int:entry_id>")
def delete_lore(entry_id): lorebook.delete_entry(entry_id); return "",204

@bp.get("/<int:char_id>/personas")
def character_personas(char_id):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM personas ORDER BY updated_at DESC,id DESC")
        return jsonify([dict(r) for r in cur.fetchall()])


@bp.get("/<int:char_id>/visual-profile")
def visual_profile(char_id):
    import json
    with db_cursor() as cur:
        cur.execute("SELECT id,name,appearance,visual_style,negative_prompt,preferred_lora,reference_images,image_preset FROM characters WHERE id=?",(char_id,)); row=cur.fetchone()
    if not row: abort(404)
    d=dict(row)
    try:d["reference_images"]=json.loads(d.get("reference_images") or "[]")
    except Exception:d["reference_images"]=[]
    return jsonify(d)

@bp.post("/<int:char_id>/visual-profile")
def update_visual_profile(char_id):
    import json
    data=request.get_json(force=True) or {}
    fields={k:data[k] for k in ("visual_style","negative_prompt","preferred_lora","image_preset") if k in data}
    if "reference_images" in data: fields["reference_images"]=json.dumps(data["reference_images"] or [])
    if not fields: abort(400,"no visual profile fields provided")
    fields["updated_at"]=now()
    with db_cursor() as cur:
        cols=", ".join(f"{k}=?" for k in fields); cur.execute(f"UPDATE characters SET {cols} WHERE id=?",(*fields.values(),char_id))
        cur.execute("SELECT id,name,appearance,visual_style,negative_prompt,preferred_lora,reference_images,image_preset FROM characters WHERE id=?",(char_id,)); row=cur.fetchone()
    if not row: abort(404)
    d=dict(row)
    try:d["reference_images"]=json.loads(d.get("reference_images") or "[]")
    except Exception:d["reference_images"]=[]
    return jsonify(d)

def _ai_image_prompt(c, scene=""):
    fallback=fallback_image_prompt(c,scene)
    system=(
        "You are newAIr's local character-to-image art director. "
        "Convert a character definition into a concise, diffusion-ready visual prompt. "
        "Appearance is authoritative: preserve explicit age, hair, face, body, clothing, colors and other visual facts. "
        "Use personality, background and scenario to infer expression, posture, mood, styling and atmosphere, but do not contradict explicit facts. "
        "If appearance is sparse, creatively infer a plausible visual design from the personality and description without inventing a specific existing person. "
        "Do not mention the character's name in the final prompt unless it is useful as a trigger word. "
        "Do not write a story, dialogue, explanation or camera lecture. "
        "Return ONLY valid JSON with exactly two string keys: prompt and negative_prompt."
    )
    def clip(v,n=3500):
        v=str(v or "").strip()
        return v if len(v)<=n else v[:n]+"…"
    payload={
        "name":clip(c.get("name"),200),"description":clip(c.get("description")),
        "appearance":clip(c.get("appearance")),"personality":clip(c.get("personality")),
        "background":clip(c.get("background")),"scenario":clip(c.get("scenario")),
        "visual_style":clip(c.get("visual_style")),"requested_scene":clip(scene),
        "existing_negative_prompt":clip(c.get("negative_prompt"),1800)
    }
    try:
        text=text_engine.generate([
            {"role":"system","content":system},
            {"role":"user","content":json.dumps(payload,ensure_ascii=False)}
        ],temperature=.45,top_p=.9,max_tokens=320,stream=False)
        obj=extract_json_object(text)
        if obj and isinstance(obj.get("prompt"),str) and obj["prompt"].strip():
            neg=obj.get("negative_prompt") if isinstance(obj.get("negative_prompt"),str) else fallback["negative_prompt"]
            return {**fallback,"prompt":obj["prompt"].strip(),"negative_prompt":neg.strip() or fallback["negative_prompt"],"source":"llm"}
    except Exception:
        pass
    return fallback


@bp.route("/<int:char_id>/image-prompt", methods=["GET","POST"])
def image_prompt(char_id):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM characters WHERE id=?",(char_id,)); row=cur.fetchone()
    if not row: abort(404)
    c=dict(row)
    data=request.get_json(silent=True) or {}
    scene=(data.get("scene") or request.args.get("scene") or "").strip()
    use_ai=str(data.get("ai",request.args.get("ai","1"))).lower() not in ("0","false","no")
    refresh=str(data.get("refresh",request.args.get("refresh","0"))).lower() in ("1","true","yes")
    cached=(c.get("visual_prompt") or "").strip()
    cached_at=float(c.get("visual_prompt_updated_at") or 0)
    updated_at=float(c.get("updated_at") or 0)
    if use_ai and not scene and not refresh and cached and cached_at >= updated_at:
        return jsonify({"prompt":cached,"negative_prompt":c.get("visual_negative_prompt") or c.get("negative_prompt") or "","preset":c.get("image_preset") or "balanced","loras":c.get("preferred_lora") or "","source":"cache"})
    result=_ai_image_prompt(c,scene) if use_ai else fallback_image_prompt(c,scene)
    if use_ai and not scene:
        with db_cursor() as cur:
            cur.execute("UPDATE characters SET visual_prompt=?,visual_negative_prompt=?,visual_prompt_updated_at=? WHERE id=?",(result.get("prompt",""),result.get("negative_prompt",""),now(),char_id))
    return jsonify(result)


@bp.post("/<int:char_id>/avatar/from-image")
def set_avatar_from_image(char_id):
    """Fast avatar path: center-crop a generated/uploaded image to 512x512."""
    data=request.get_json(force=True) or {}
    data_url=(data.get("data_url") or "").strip()
    if not data_url.startswith("data:image/") or "," not in data_url:
        abort(400,"valid image data is required")
    try:
        raw=base64.b64decode(data_url.split(",",1)[1],validate=True)
        image=Image.open(io.BytesIO(raw)).convert("RGB")
        from PIL import ImageOps
        # Slightly upward-biased centering works better for portrait avatars.
        image=ImageOps.fit(image,(512,512),method=Image.Resampling.LANCZOS,centering=(0.5,0.42))
        os.makedirs("static/generated",exist_ok=True)
        filename=f"avatar_{uuid.uuid4().hex}.png"
        path=os.path.join("static","generated",filename)
        image.save(path,"PNG",optimize=True)
        url="/static/generated/"+filename
        with db_cursor() as cur:
            cur.execute("UPDATE characters SET avatar_path=?,updated_at=? WHERE id=?",(url,now(),char_id))
            if cur.rowcount==0: abort(404,"character not found")
        return jsonify({"url":url,"character_id":char_id,"auto_cropped":True})
    except Exception as e:
        abort(400,f"could not set avatar: {e}")

