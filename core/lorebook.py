"""
Lorebook / world-info — static facts that only enter the prompt when
recent chat text mentions one of their trigger keywords. This keeps
the always-on context (character card) small while still letting a
character "know" a large body of lore.
"""
import json
from core.database import db_cursor
import config


def get_entries(character_id):
    with db_cursor() as cur:
        cur.execute(
            """SELECT * FROM lorebook_entries
               WHERE (character_id = ? OR character_id IS NULL) AND enabled = 1
               ORDER BY priority DESC, id ASC""",
            (character_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        r["keywords"] = json.loads(r["keywords"])
    return rows


def create_entry(character_id, title, keywords, content, priority=0, enabled=True):
    from core.database import now
    with db_cursor() as cur:
        cur.execute(
            """INSERT INTO lorebook_entries
               (character_id, title, keywords, content, enabled, priority, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (character_id, title, json.dumps(keywords), content, int(enabled), priority, now()),
        )
        return cur.lastrowid


def update_entry(entry_id, **fields):
    if "keywords" in fields:
        fields["keywords"] = json.dumps(fields["keywords"])
    if "enabled" in fields:
        fields["enabled"] = int(fields["enabled"])
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    with db_cursor() as cur:
        cur.execute(f"UPDATE lorebook_entries SET {cols} WHERE id = ?",
                    (*fields.values(), entry_id))


def delete_entry(entry_id):
    with db_cursor() as cur:
        cur.execute("DELETE FROM lorebook_entries WHERE id = ?", (entry_id,))


def scan_and_select(character_id, recent_text, max_entries=None, max_tokens=None):
    """Return the lorebook entries whose keywords appear in
    `recent_text` (case-insensitive substring match), highest priority
    first, capped by count and by a token budget."""
    max_entries = max_entries or config.MAX_LOREBOOK_ENTRIES_INJECTED
    haystack = recent_text.lower()
    entries = get_entries(character_id)

    matched = []
    for e in entries:
        if any(kw.strip().lower() in haystack for kw in e["keywords"] if kw.strip()):
            matched.append(e)

    matched = matched[:max_entries]

    if max_tokens is not None:
        from core.llm_engine import engine
        budget = max_tokens
        selected = []
        for e in matched:
            t = engine.count_tokens(e["content"])
            if t > budget:
                break
            selected.append(e)
            budget -= t
        matched = selected

    return matched
