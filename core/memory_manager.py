"""Persistent and rolling conversation memory for Character Mode.

The full transcript stays in ``messages``.  Only a compact rolling summary
and a small window of recent unsummarized messages are sent to the LLM.
This keeps long roleplays usable even when the GGUF has a small context
window such as 4096 tokens.
"""
from core.database import db_cursor, now
import config


def get_conversation_summary(conversation_id):
    """Return the newest rolling summary for a conversation."""
    with db_cursor() as cur:
        cur.execute(
            "SELECT summary FROM conversation_memories WHERE conversation_id=? "
            "ORDER BY id DESC LIMIT 1",
            (conversation_id,),
        )
        row = cur.fetchone()
    return (row["summary"] if row else "") or ""


def get_character_memories(character_id):
    with db_cursor() as cur:
        cur.execute(
            "SELECT fact FROM character_memories WHERE character_id=? "
            "ORDER BY importance DESC, id ASC",
            (character_id,),
        )
        rows = cur.fetchall()
    return [r["fact"] for r in rows]


def search_character_memories(character_id, query="", limit=20):
    q=(query or "").strip()
    with db_cursor() as cur:
        if q:
            cur.execute("SELECT id,fact,category,importance,created_at FROM character_memories WHERE character_id=? AND fact LIKE ? ORDER BY importance DESC,id DESC LIMIT ?",(character_id,f"%{q}%",limit))
        else:
            cur.execute("SELECT id,fact,category,importance,created_at FROM character_memories WHERE character_id=? ORDER BY importance DESC,id DESC LIMIT ?",(character_id,limit))
        return [dict(r) for r in cur.fetchall()]


def add_character_memory(character_id, fact, category="general", importance=1):
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO character_memories (character_id, fact, category, importance, created_at) VALUES (?, ?, ?, ?, ?)",
            (character_id, fact, category or "general", max(1,min(int(importance),5)), now()),
        )
        return cur.lastrowid


def delete_character_memory(memory_id):
    with db_cursor() as cur:
        cur.execute("DELETE FROM character_memories WHERE id = ?", (memory_id,))


def _token_count(text):
    try:
        from core.llm_engine import engine
        return engine.count_tokens(text or "")
    except Exception:
        return max(1, len(text or "") // 4)


def _unsummarized_messages(cur, conversation_id):
    cur.execute(
        """SELECT * FROM messages
           WHERE conversation_id=? AND summarized=0 AND role!='system'
           ORDER BY id ASC""",
        (conversation_id,),
    )
    return [dict(r) for r in cur.fetchall()]


def _summarize_chunk(conversation_id, chunk, existing):
    """Create one compact merged summary without allowing the summary job
    itself to approach the model context limit."""
    if not chunk:
        return None
    transcript="\n".join(f"{m['role'].upper()}: {m['content']}" for m in chunk)
    # Keep the previous memory bounded before putting it into the summarizer.
    if existing:
        max_existing_chars=9000
        existing=existing[-max_existing_chars:]
    summary_prompt=[
        {"role":"system","content":(
            "Maintain a compact rolling memory of a roleplay conversation. "
            "Merge the existing memory with the new excerpt. Preserve durable "
            "facts, names, relationships, promises, discoveries, important "
            "events, emotional state, unresolved threads, current situation, "
            "and continuity details. Remove repetition and trivial wording. "
            "Use concise bullet points. Never invent facts. Return ONLY the "
            "updated memory.\n\nEXISTING MEMORY:\n"+(existing or "(none)")
        )},
        {"role":"user","content":"NEW EXCERPT:\n"+transcript},
    ]
    from core.llm_engine import engine
    return str(engine.generate(
        summary_prompt,
        stream=False,
        max_tokens=config.MEMORY_SUMMARY_MAX_TOKENS,
        temperature=0.25,
        top_p=0.85,
    ) or "").strip()


def ensure_context_budget(conversation_id, extra_text=""):
    """Compress old messages before a turn whenever the active context is
    getting large. The full transcript remains stored in the DB.

    A single rolling summary replaces older summary chunks, preventing the
    summary itself from growing forever. Recent raw messages remain verbatim.
    """
    with db_cursor() as cur:
        pending=_unsummarized_messages(cur,conversation_id)

    extra_tokens=_token_count(extra_text)
    total=sum(_token_count(m["content"])+4 for m in pending)+extra_tokens
    target=config.RAW_HISTORY_TARGET_TOKENS
    if total <= target:
        return False

    # Preserve enough recent messages for natural turn-to-turn continuity.
    keep_count=max(4, config.KEEP_RAW_MESSAGES)
    if len(pending) <= keep_count:
        return False

    cut=max(1, len(pending)-keep_count)
    running=0
    cut_count=0
    for m in pending[:cut]:
        n=_token_count(m["content"])+4
        if cut_count and running+n > max(1,total-target):
            break
        running+=n
        cut_count+=1
        if total-running <= target:
            break
    if cut_count <= 0:
        return False

    chunk=pending[:cut_count]
    existing=get_conversation_summary(conversation_id)
    try:
        new_summary=_summarize_chunk(conversation_id,chunk,existing)
    except Exception:
        return False
    if not new_summary:
        return False

    last_id=chunk[-1]["id"]
    with db_cursor() as cur:
        # Keep one rolling summary row, rather than accumulating summary rows.
        cur.execute("DELETE FROM conversation_memories WHERE conversation_id=?",(conversation_id,))
        cur.execute(
            "INSERT INTO conversation_memories(conversation_id,summary,covers_up_to_message_id,created_at) VALUES(?,?,?,?)",
            (conversation_id,new_summary,last_id,now()),
        )
        cur.execute(
            "UPDATE messages SET summarized=1 WHERE conversation_id=? AND id<=? AND role!='system'",
            (conversation_id,last_id),
        )
    return True


def maybe_summarize(conversation_id):
    """Backward-compatible entry point used after a response."""
    return ensure_context_budget(conversation_id)
