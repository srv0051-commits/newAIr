from flask import Blueprint, request, jsonify, abort
from core.database import db_cursor, now
bp=Blueprint("personas",__name__,url_prefix="/api/personas")
FIELDS=("name","description","avatar_path","pronouns","age","appearance","personality","speaking_style","background","details")

@bp.get("")
def list_personas():
    with db_cursor() as cur:
        cur.execute("SELECT * FROM personas ORDER BY updated_at DESC,id DESC")
        return jsonify([dict(r) for r in cur.fetchall()])

@bp.post("")
def create_persona():
    data=request.get_json(force=True) or {}; name=(data.get("name") or "").strip()
    if not name: abort(400,"name is required")
    values=[name]+[data.get(k,"") for k in FIELDS[1:]]; t=now()
    with db_cursor() as cur:
        cur.execute(f"INSERT INTO personas({','.join(FIELDS)},created_at,updated_at) VALUES({','.join(['?']*len(FIELDS))},?,?)",(*values,t,t))
        cur.execute("SELECT * FROM personas WHERE id=?",(cur.lastrowid,)); return jsonify(dict(cur.fetchone())),201

@bp.put("/<int:persona_id>")
def update_persona(persona_id):
    data=request.get_json(force=True) or {}; fields={k:data[k] for k in FIELDS if k in data}
    if "name" in fields:
        fields["name"]=(fields["name"] or "").strip()
        if not fields["name"]: abort(400,"name cannot be empty")
    if not fields: abort(400,"no updatable fields provided")
    fields["updated_at"]=now(); cols=", ".join(f"{k}=?" for k in fields)
    with db_cursor() as cur:
        cur.execute(f"UPDATE personas SET {cols} WHERE id=?",(*fields.values(),persona_id))
        cur.execute("SELECT * FROM personas WHERE id=?",(persona_id,)); row=cur.fetchone()
    if not row: abort(404)
    return jsonify(dict(row))

@bp.delete("/<int:persona_id>")
def delete_persona(persona_id):
    with db_cursor() as cur: cur.execute("DELETE FROM personas WHERE id=?",(persona_id,))
    return "",204
