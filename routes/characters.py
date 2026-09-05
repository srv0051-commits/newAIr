from flask import Blueprint, request, jsonify, abort
import base64, io, os, uuid
from PIL import Image
from core.database import db_cursor, now
from core import memory_manager, lorebook

bp=Blueprint("characters",__name__,url_prefix="/api/characters")
FIELDS=("name","description","tags","personality","appearance","background","scenario","greeting","example_dialogue","system_prompt","creator_notes","avatar_path")

@bp.get("")
def list_characters():
    with db_cursor() as cur:
        cur.execute("SELECT * FROM characters WHERE id!=0 ORDER BY updated_at DESC,id DESC")
        return jsonify([dict(r) for r in cur.fetchall()])

@bp.post("")
def create_character():
    data=request.get_json(force=True) or {}; name=(data.get("name") or "").strip()
    if not name: abort(400,"name is required")
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
def list_memories(char_id): return jsonify([{"fact":x} for x in memory_manager.get_character_memories(char_id)])

@bp.post("/<int:char_id>/memories")
def add_memory(char_id):
    fact=((request.get_json(force=True) or {}).get("fact") or "").strip()
    if not fact: abort(400,"fact is required")
    mid=memory_manager.add_character_memory(char_id,fact); return jsonify({"id":mid,"fact":fact}),201

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
