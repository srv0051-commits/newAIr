import re
from core.database import db_cursor
from core import lorebook, memory_manager
from core.llm_engine import engine
import config

def replace_placeholders(text, character, persona=None):
    if not text:
        return text
    char=character.get("name","the character")
    user=persona.get("name") if persona else "the user"
    text=re.sub(r"\{\{\s*char\s*\}\}",char,text,flags=re.I)
    text=re.sub(r"\{\{\s*user\s*\}\}",user,text,flags=re.I)
    text=re.sub(r"<CHAR>",char,text,flags=re.I)
    text=re.sub(r"<USER>",user,text,flags=re.I)
    return text

def _build_system_block(character,char_memories,convo_summary,lore_entries,persona=None):
    rp=lambda x:replace_placeholders(x or "",character,persona).strip()
    cn=character["name"]
    un=persona["name"] if persona else "the user"
    parts=[
        f"You are {cn}.",
        f"CHARACTER NAME: {cn}",
        f"USER NAME: {un}",
        "The active character is {{char}} and the active user persona is {{user}}."
    ]
    for key,label in [
        ("description","CHARACTER DESCRIPTION"),
        ("personality","PERSONALITY"),
        ("appearance","APPEARANCE"),
        ("background","BACKGROUND"),
        ("scenario","SCENARIO")
    ]:
        if character.get(key):
            parts.append(label+":\n"+rp(character[key]))
    if persona:
        lines=[]
        for key,label in [
            ("description","Description"),("pronouns","Pronouns"),("age","Age"),
            ("appearance","Appearance"),("personality","Personality"),
            ("speaking_style","Speaking style"),("background","Background"),
            ("details","Additional details")
        ]:
            if persona.get(key):
                lines.append(f"{label}: {rp(persona[key])}")
        if lines:
            parts.append("ACTIVE USER PERSONA:\n"+"\n".join(lines))
    if character.get("example_dialogue"):
        parts.append(
            "EXAMPLE DIALOGUE:\n"+rp(character["example_dialogue"])+
            "\nUse this as style and behavior guidance."
        )
    if character.get("system_prompt"):
        parts.append("ADVANCED CHARACTER DEFINITION:\n"+rp(character["system_prompt"]))
    if char_memories:
        parts.append("PERSISTENT CHARACTER MEMORIES:\n- "+"\n- ".join(rp(x) for x in char_memories))
    if convo_summary:
        parts.append("EARLIER CONVERSATION SUMMARY:\n"+rp(convo_summary))
    if lore_entries:
        parts.append(
            "RELEVANT WORLD INFORMATION:\n"+
            "\n".join(f"- {rp(e['title'])}: {rp(e['content'])}" for e in lore_entries)
        )
    parts.append(
        "ROLEPLAY RULES:\n"
        "- Stay in character as {{char}}.\n"
        "- Never speak for or control {{user}}.\n"
        "- Do not invent {{user}}'s actions, thoughts, dialogue, or identity.\n"
        "- Keep established personality and scenario details consistent.\n"
        "- Respond naturally to the latest message."
    )
    return replace_placeholders("\n\n".join(parts),character,persona)

def _fit_history(history,budget):
    kept=[]
    used=0
    for m in reversed(history):
        n=engine.count_tokens(m["content"])+4
        if used+n>budget:
            break
        kept.append(m)
        used+=n
    kept.reverse()
    return kept

def build_messages(conversation_id,character,new_user_message=None):
    with db_cursor() as cur:
        cur.execute(
            "SELECT role,content FROM messages WHERE conversation_id=? ORDER BY id ASC",
            (conversation_id,)
        )
        history=[dict(r) for r in cur.fetchall()]
        cur.execute("SELECT persona_id FROM conversations WHERE id=?",(conversation_id,))
        conv=cur.fetchone()
        persona=None
        if conv and conv["persona_id"]:
            cur.execute("SELECT * FROM personas WHERE id=?",(conv["persona_id"],))
            row=cur.fetchone()
            persona=dict(row) if row else None

    recent=" ".join(m["content"] for m in history[-6:])
    if new_user_message:
        recent+=" "+new_user_message
    memories=memory_manager.get_character_memories(character["id"])
    summary=memory_manager.get_conversation_summary(conversation_id)
    lore=lorebook.scan_and_select(
        character["id"],recent,
        max_tokens=config.MAX_STATIC_CONTEXT_TOKENS//3
    )
    system=_build_system_block(character,memories,summary,lore,persona)
    while engine.count_tokens(system)>config.MAX_STATIC_CONTEXT_TOKENS and lore:
        lore.pop()
        system=_build_system_block(character,memories,summary,lore,persona)
    budget=max(
        config.N_CTX-config.RESERVED_FOR_REPLY-engine.count_tokens(system)-
        (engine.count_tokens(new_user_message) if new_user_message else 0),
        256
    )
    fitted=_fit_history(history,budget)
    messages=[{"role":"system","content":system}]
    messages += [{"role":m["role"],"content":m["content"]} for m in fitted]
    if not fitted and character.get("greeting"):
        messages.append({
            "role":"assistant",
            "content":replace_placeholders(character["greeting"],character,persona)
        })
    if new_user_message:
        messages.append({"role":"user","content":new_user_message})
    return messages
