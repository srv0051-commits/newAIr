"""Character-to-image prompt helpers used by Character Studio."""
import json
import re


def fallback_image_prompt(c, scene=""):
    parts=[]
    name=(c.get("name") or "character").strip()
    appearance=(c.get("appearance") or "").strip()
    personality=(c.get("personality") or "").strip()
    description=(c.get("description") or "").strip()
    visual=(c.get("visual_style") or "").strip()
    background=(c.get("background") or "").strip()
    scenario=(c.get("scenario") or "").strip()
    if appearance: parts.append(appearance)
    elif description: parts.append(description)
    if personality: parts.append("visual expression and body language reflecting this personality: " + personality)
    if background and not appearance: parts.append("visual character concept informed by this background: " + background)
    if visual: parts.append(visual)
    if scenario: parts.append("scene context: " + scenario)
    if scene: parts.append("requested scene: " + scene)
    parts.append("single character portrait, coherent facial identity, natural anatomy, detailed face, detailed eyes, polished local diffusion artwork")
    if not parts: parts.insert(0, f"a visually distinctive character named {name}")
    negative=(c.get("negative_prompt") or "").strip()
    default="low quality, blurry, distorted face, bad anatomy, extra fingers, extra limbs, duplicate person, text, watermark"
    negative=(negative + ", " + default).strip(", ")
    return {"prompt":", ".join(parts),"negative_prompt":negative,"preset":c.get("image_preset") or "balanced","loras":c.get("preferred_lora") or "","source":"fallback"}


def extract_json_object(text):
    text=(text or "").strip()
    if text.startswith("```"):
        text=re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text=re.sub(r"\s*```$", "", text)
    try: return json.loads(text)
    except Exception: pass
    m=re.search(r"\{.*\}", text, flags=re.S)
    if m:
        try: return json.loads(m.group(0))
        except Exception: pass
    return None
