import json
from flask import Blueprint, request, jsonify, abort, Response, stream_with_context
from core.database import db_cursor, now
from core import prompt_builder, memory_manager
from core.llm_engine import engine

bp=Blueprint("chat",__name__,url_prefix="/api")

@bp.get("/characters/<int:char_id>/conversations")
def list_conversations(char_id):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM conversations WHERE character_id=? ORDER BY updated_at DESC,id DESC",(char_id,))
        return jsonify([dict(r) for r in cur.fetchall()])

@bp.post("/characters/<int:char_id>/conversations")
def create_conversation(char_id):
    data=request.get_json(silent=True) or {}; pid=data.get("persona_id"); title=(data.get("title") or "").strip()
    with db_cursor() as cur:
        cur.execute("SELECT * FROM characters WHERE id=?",(char_id,)); row=cur.fetchone()
        character=dict(row) if row else None
        if not character: abort(404,"character not found")
        if pid:
            cur.execute("SELECT id FROM personas WHERE id=?",(pid,))
            if not cur.fetchone(): pid=None
        t=now()
        cur.execute("INSERT INTO conversations(character_id,persona_id,mode,title,created_at,updated_at) VALUES(?,?, 'character',?,?,?)",(char_id,pid,title,t,t))
        cid=cur.lastrowid
        persona=None
        if pid:
            cur.execute("SELECT * FROM personas WHERE id=?",(pid,)); prow=cur.fetchone(); persona=dict(prow) if prow else None

    _seed_initial_messages(cid, character, persona)
    return jsonify({"id":cid,"character_id":char_id,"persona_id":pid,"title":title}),201


def _get_initial_messages(character):
    initial=[]
    try:
        initial=json.loads(character.get("initial_messages") or "[]")
    except Exception:
        initial=[]
    if isinstance(initial,str):
        initial=[initial]
    initial=[str(x).strip() for x in (initial or []) if str(x).strip()][:10]
    if not initial and character.get("greeting"):
        initial=[str(character["greeting"]).strip()]
    return initial


def _seed_initial_messages(conv_id, character, persona=None):
    """Insert a character's opening messages into an empty conversation only.

    This is deliberately idempotent so older empty conversations created by
    previous newAIr versions can still receive their configured greeting.
    Existing conversations are never modified.
    """
    initial=_get_initial_messages(character)
    if not initial:
        return False
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM messages WHERE conversation_id=?",(conv_id,))
        row=cur.fetchone()
        if row and int(row["n"] or 0)>0:
            return False
        for item in initial:
            greeting=prompt_builder.replace_placeholders(item,character,persona)
            cur.execute("INSERT INTO messages(conversation_id,role,content,created_at) VALUES(?,'assistant',?,?)",(conv_id,greeting,now()))
        cur.execute("UPDATE conversations SET updated_at=? WHERE id=?",(now(),conv_id))
    return True


@bp.get("/conversations/<int:conv_id>")
def get_conversation(conv_id):
    with db_cursor() as cur:
        cur.execute("SELECT * FROM conversations WHERE id=?",(conv_id,)); row=cur.fetchone()
    if not row: abort(404,"conversation not found")
    return jsonify(dict(row))

@bp.put("/conversations/<int:conv_id>")
def update_conversation(conv_id):
    data=request.get_json(force=True) or {}; fields={}
    if "title" in data: fields["title"]=data["title"] or ""
    if "persona_id" in data:
        pid=data["persona_id"]
        if pid:
            with db_cursor() as cur:
                cur.execute("SELECT id FROM personas WHERE id=?",(pid,))
                if not cur.fetchone(): abort(400,"persona not found")
        fields["persona_id"]=pid
    if not fields: abort(400,"no updatable fields provided")
    fields["updated_at"]=now()
    with db_cursor() as cur:
        cur.execute(f"UPDATE conversations SET {', '.join(k+'=?' for k in fields)} WHERE id=?",(*fields.values(),conv_id))
        cur.execute("SELECT * FROM conversations WHERE id=?",(conv_id,)); row=cur.fetchone()
    if not row: abort(404,"conversation not found")
    return jsonify(dict(row))

@bp.get("/conversations/<int:conv_id>/messages")
def get_messages(conv_id):
    # Repair empty conversations created by older builds. This does not touch
    # conversations that already contain messages.
    with db_cursor() as cur:
        cur.execute("SELECT c.*, conv.persona_id FROM characters c JOIN conversations conv ON conv.character_id=c.id WHERE conv.id=?",(conv_id,))
        row=cur.fetchone()
        if not row: abort(404,"conversation not found")
        data=dict(row)
    persona=None
    if data.get("persona_id"):
        with db_cursor() as cur:
            cur.execute("SELECT * FROM personas WHERE id=?",(data["persona_id"],)); prow=cur.fetchone()
            persona=dict(prow) if prow else None
    _seed_initial_messages(conv_id,data,persona)
    with db_cursor() as cur:
        cur.execute("SELECT id,role,content,created_at,edited FROM messages WHERE conversation_id=? ORDER BY id ASC",(conv_id,))
        return jsonify([dict(r) for r in cur.fetchall()])

@bp.delete("/conversations/<int:conv_id>")
def delete_conversation(conv_id):
    with db_cursor() as cur: cur.execute("DELETE FROM conversations WHERE id=?",(conv_id,))
    return "",204

def _get_character_for_conversation(cur,conv_id):
    cur.execute("SELECT c.* FROM characters c JOIN conversations conv ON conv.character_id=c.id WHERE conv.id=?",(conv_id,))
    row=cur.fetchone(); return dict(row) if row else None

def _persist_message(conv_id,role,content):
    with db_cursor() as cur:
        cur.execute("INSERT INTO messages(conversation_id,role,content,created_at) VALUES(?,?,?,?)",(conv_id,role,content,now()))
        cur.execute("UPDATE conversations SET updated_at=? WHERE id=?",(now(),conv_id))
        return cur.lastrowid

def _stream_reply(conv_id,messages,persist_user_content=None,max_tokens=None):
    if persist_user_content is not None: _persist_message(conv_id,"user",persist_user_content)
    def event_stream():
        full=[]
        try:
            for piece in engine.generate(messages,stream=True,max_tokens=max_tokens):
                full.append(piece); yield f"data: {json.dumps({'delta':piece})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error':str(e)})}\n\n"; return
        msg_id=_persist_message(conv_id,"assistant","".join(full))
        yield f"data: {json.dumps({'done':True,'message_id':msg_id})}\n\n"
        memory_manager.maybe_summarize(conv_id)
    return Response(stream_with_context(event_stream()),mimetype="text/event-stream")

@bp.post("/conversations/<int:conv_id>/chat")
def send_message(conv_id):
    text=((request.get_json(force=True) or {}).get("message") or "").strip()
    if not text: abort(400,"message is required")
    with db_cursor() as cur: character=_get_character_for_conversation(cur,conv_id)
    if not character: abort(404,"conversation not found")
    data=request.get_json(force=True) or {}
    max_tokens=data.get("max_tokens")
    try: max_tokens=max(64,min(2048,int(max_tokens))) if max_tokens is not None else None
    except (TypeError,ValueError): max_tokens=None
    return _stream_reply(conv_id,prompt_builder.build_messages(conv_id,character,new_user_message=text,response_tokens=max_tokens),persist_user_content=text,max_tokens=max_tokens)

@bp.post("/conversations/<int:conv_id>/regenerate")
def regenerate(conv_id):
    with db_cursor() as cur:
        character=_get_character_for_conversation(cur,conv_id)
        if not character: abort(404,"conversation not found")
        cur.execute("SELECT id,role FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT 1",(conv_id,)); last=cur.fetchone()
        if last and last["role"]=="assistant": cur.execute("DELETE FROM messages WHERE id=?",(last["id"],))
    data=request.get_json(silent=True) or {}
    max_tokens=data.get("max_tokens")
    try: max_tokens=max(64,min(2048,int(max_tokens))) if max_tokens is not None else None
    except (TypeError,ValueError): max_tokens=None
    return _stream_reply(conv_id,prompt_builder.build_messages(conv_id,character,response_tokens=max_tokens),max_tokens=max_tokens)

@bp.post("/conversations/<int:conv_id>/continue")
def continue_reply(conv_id):
    data=request.get_json(silent=True) or {}
    max_tokens=data.get("max_tokens")
    try: max_tokens=max(64,min(2048,int(max_tokens))) if max_tokens is not None else None
    except (TypeError,ValueError): max_tokens=None
    with db_cursor() as cur: character=_get_character_for_conversation(cur,conv_id)
    if not character: abort(404,"conversation not found")
    messages=prompt_builder.build_messages(conv_id,character,response_tokens=max_tokens)
    messages.append({"role":"user","content":"[Continue your previous reply. Do not repeat what you already said.]"})
    return _stream_reply(conv_id,messages,max_tokens=max_tokens)

@bp.post("/conversations/<int:conv_id>/writing-assist")
def writing_assist(conv_id):
    data=request.get_json(silent=True) or {}
    action=(data.get("action") or "").strip().lower()
    draft=(data.get("draft") or "").strip()
    instruction=(data.get("instruction") or "").strip()
    if action not in {"enhance","write","summarize"}: abort(400,"unsupported writing action")
    with db_cursor() as cur:
        character=_get_character_for_conversation(cur,conv_id)
        if not character: abort(404,"conversation not found")
    if action=="enhance":
        if not draft: abort(400,"draft is required")
        msgs=[{"role":"system","content":"Rewrite the user's draft for naturalness, clarity, flow and voice. Preserve the user's meaning, intent and level of intensity. Return ONLY the rewritten draft, with no commentary."},{"role":"user","content":draft}]
    elif action=="write":
        context=prompt_builder.build_messages(conv_id,character)
        context.append({"role":"user","content":("Help the user write a message for this conversation. " + (instruction or "Write a natural next message that fits the conversation."))})
        msgs=context
    else:
        with db_cursor() as cur:
            cur.execute("SELECT role,content FROM messages WHERE conversation_id=? ORDER BY id ASC",(conv_id,))
            hist=[dict(r) for r in cur.fetchall()]
        text="\n".join(f"{m['role'].upper()}: {m['content']}" for m in hist[-80:])
        msgs=[{"role":"system","content":"Summarize the conversation accurately and concisely. Preserve important facts, relationships, decisions, unresolved threads and character state. Return only the summary."},{"role":"user","content":text}]
    try:
        result=engine.generate(msgs,temperature=.45,top_p=.9,max_tokens=700,stream=False)
    except Exception as e:
        abort(500,f"writing assistant failed: {e}")
    return jsonify({"text":str(result or "").strip(),"action":action})

@bp.put("/messages/<int:message_id>")
def edit_message(message_id):
    text=((request.get_json(force=True) or {}).get("content") or "").strip()
    if not text: abort(400,"content is required")
    with db_cursor() as cur: cur.execute("UPDATE messages SET content=?,edited=1,summarized=0 WHERE id=?",(text,message_id))
    return jsonify({"ok":True})

@bp.delete("/messages/<int:message_id>")
def delete_message(message_id):
    with db_cursor() as cur: cur.execute("DELETE FROM messages WHERE id=?",(message_id,))
    return "",204
