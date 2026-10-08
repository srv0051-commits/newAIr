from core.character_visuals import fallback_image_prompt, extract_json_object


def test_fallback_prompt_uses_personality_and_appearance():
    c={
        'name':'Elena',
        'appearance':'27-year-old woman with dark wavy hair and hazel eyes',
        'personality':'observant, guarded, dry sense of humor',
        'visual_style':'cinematic realism',
        'negative_prompt':'plastic skin',
        'image_preset':'balanced',
        'preferred_lora':'cinestyle-25.safetensors'
    }
    r=fallback_image_prompt(c)
    assert 'dark wavy hair' in r['prompt']
    assert 'observant' in r['prompt']
    assert 'cinematic realism' in r['prompt']
    assert 'plastic skin' in r['negative_prompt']
    assert r['loras']=='cinestyle-25.safetensors'


def test_json_prompt_parser_accepts_fenced_json():
    r=extract_json_object('```json\n{"prompt":"portrait, rain","negative_prompt":"blurry"}\n```')
    assert r['prompt']=='portrait, rain'
    assert r['negative_prompt']=='blurry'
