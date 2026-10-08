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

def _build_system_block(character,char_memories,convo_summary,lore_entries,persona=None,response_tokens=None):
    rp=lambda x:replace_placeholders(x or "",character,persona).strip()
    cn=character["name"]
    un=persona["name"] if persona else "the user"
    parts=[
        f"You are {cn}.",
        f"CHARACTER NAME: {cn}",
        f"USER NAME: {un}",
        "The active character is {{char}} and the active user persona is {{user}}."
    ]
    for key,label in [("description","CHARACTER DESCRIPTION"),("personality","PERSONALITY"),("appearance","APPEARANCE"),("background","BACKGROUND"),("scenario","SCENARIO")]:
        if character.get(key): parts.append(label+":\n"+rp(character[key]))
    if persona:
        lines=[]
        for key,label in [("description","Description"),("pronouns","Pronouns"),("age","Age"),("appearance","Appearance"),("personality","Personality"),("speaking_style","Speaking style"),("background","Background"),("details","Additional details")]:
            if persona.get(key): lines.append(f"{label}: {rp(persona[key])}")
        if lines: parts.append("ACTIVE USER PERSONA:\n"+"\n".join(lines))
    if character.get("example_dialogue"):
        parts.append("EXAMPLE DIALOGUE:\n"+rp(character["example_dialogue"])+"\nUse this as style and behavior guidance.")
    if character.get("system_prompt"):
        parts.append("ADVANCED CHARACTER DEFINITION:\n"+rp(character["system_prompt"]))
    if char_memories:
        parts.append("PERSISTENT CHARACTER MEMORIES:\n- "+"\n- ".join(rp(x) for x in char_memories))
    if convo_summary:
        parts.append("EARLIER CONVERSATION SUMMARY:\n"+rp(convo_summary))
    if lore_entries:
        parts.append("RELEVANT WORLD INFORMATION:\n"+"\n".join(f"- {rp(e['title'])}: {rp(e['content'])}" for e in lore_entries))
    parts.append(_response_length_instruction(response_tokens))
    parts.append(
        "ROLEPLAY RULES:\n"
        "- Stay in character as {{char}}.\n"
        "- Never speak for or control {{user}}.\n"
        "- Do not invent {{user}}'s actions, thoughts, dialogue, or identity.\n"
        "- Keep established personality and scenario details consistent.\n"
        "- Use plain text for spoken dialogue. Do NOT wrap spoken dialogue in quotation marks unless the character would naturally do so.\n"
        "- Put physical actions, gestures, expressions, movements, scene actions, and non-spoken narration inside single asterisks, for example: *She looks toward the window and smiles.*\n"
        "- Never use double asterisks for roleplay actions.\n"
        "- Keep spoken dialogue and actions clearly separated: dialogue is normal text, actions are *italicized*.\n"
        "- Do not put the user's actions, thoughts, or dialogue inside asterisks. Only describe {{char}}'s actions and narration you control.\n"
        "- Respond naturally to the latest message."
    )
    return replace_placeholders("\n\n".join(parts),character,persona)

def _fit_history(history,budget):
    kept=[]; used=0
    for m in reversed(history):
        n=engine.count_tokens(m["content"])+4
        if used+n>budget: break
        kept.append(m); used+=n
    kept.reverse(); return kept

def _response_length_instruction(response_tokens):
    """Tell the roleplay model to aim for the selected reply length.

    max_tokens is only a hard ceiling. Without an explicit target, a model can
    legally stop after a short answer even when the ceiling is much larger.
    """
    if response_tokens is None:
        return "RESPONSE LENGTH: Give a natural, moderately detailed reply and finish at a sensible point."
    n=max(64,int(response_tokens))
    if n <= 200:
        lo,hi="90",str(max(120,n))
        style="Keep it concise, usually 1-3 short paragraphs."
    elif n <= 400:
        lo,hi="180",str(max(240,min(n,360)))
        style="Give a moderate, natural roleplay response with enough action and dialogue to feel complete."
    elif n <= 700:
        lo,hi="350",str(max(450,min(n,620)))
        style="Give a detailed roleplay response with several beats of action and dialogue; do not rush the scene."
    else:
        lo,hi="650",str(max(750,min(n,950)))
        style="Give a long, immersive roleplay response with multiple natural beats, actions, reactions, and dialogue; develop the scene before ending."
    return (f"RESPONSE LENGTH: Aim for roughly {lo}-{hi} generated tokens. "
            f"{style} Finish naturally rather than padding or repeating yourself.")

def build_messages(conversation_id,character,new_user_message=None,response_tokens=None):
    # Compress before reading the active context. Full history remains in DB.
    memory_manager.ensure_context_budget(conversation_id,new_user_message or "")
    with db_cursor() as cur:
        cur.execute("SELECT role,content FROM messages WHERE conversation_id=? AND summarized=0 ORDER BY id ASC",(conversation_id,))
        history=[dict(r) for r in cur.fetchall()]
        cur.execute("SELECT persona_id FROM conversations WHERE id=?",(conversation_id,))
        conv=cur.fetchone(); persona=None
        if conv and conv["persona_id"]:
            cur.execute("SELECT * FROM personas WHERE id=?",(conv["persona_id"],)); row=cur.fetchone(); persona=dict(row) if row else None

    recent=" ".join(m["content"] for m in history[-8:])
    if new_user_message: recent+=" "+new_user_message
    memories=memory_manager.get_character_memories(character["id"])
    summary=memory_manager.get_conversation_summary(conversation_id)
    lore=lorebook.scan_and_select(character["id"],recent,max_tokens=config.MAX_STATIC_CONTEXT_TOKENS//3)
    system=_build_system_block(character,memories,summary,lore,persona,response_tokens)
    while engine.count_tokens(system)>config.MAX_STATIC_CONTEXT_TOKENS and lore:
        lore.pop(); system=_build_system_block(character,memories,summary,lore,persona,response_tokens)
    reserve=max(64,int(response_tokens or config.RESERVED_FOR_REPLY))
    prompt_tokens=engine.count_tokens(system)+(engine.count_tokens(new_user_message) if new_user_message else 0)
    budget=max(config.N_CTX-reserve-prompt_tokens-config.CONTEXT_SAFETY_MARGIN,256)
    fitted=_fit_history(history,budget)
    messages=[{"role":"system","content":system}]
    messages += [{"role":m["role"],"content":m["content"]} for m in fitted]
    if not fitted and character.get("greeting"):
        messages.append({"role":"assistant","content":replace_placeholders(character["greeting"],character,persona)})
    if new_user_message: messages.append({"role":"user","content":new_user_message})
    return messages
