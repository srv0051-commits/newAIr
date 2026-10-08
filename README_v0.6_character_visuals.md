# newAIr v0.6 Character Visuals

This upgrade connects Character Studio directly to Image Studio.

## Character -> image workflow

1. Create/save a character with its personality, appearance, description, background, scenario and visual style.
2. Open Image Studio and select the character.
3. Click **Generate character image**.
4. Dolphin converts the character definition into a diffusion-ready visual prompt automatically.
5. The generated prompt is cached until the character definition changes, avoiding unnecessary LLM calls.
6. Preferred character LoRAs and the character's negative prompt are applied automatically.
7. The portrait uses a 3:4 layout and the character's image preset.
8. **Set as avatar** automatically creates a 512x512 portrait crop and updates the character. No crop dialog is required for the normal workflow.
9. **Adjust crop** remains available when manual framing is needed.

## Character editor shortcut

For an existing character, **Generate portrait from this character** closes the editor, opens Image Studio and starts the same workflow automatically.

## Fallback behavior

If Dolphin is unavailable or its output cannot be parsed, newAIr uses a deterministic local prompt builder based on the character fields. Generation can still proceed.

## Database migration

Existing databases automatically receive:
- `characters.visual_prompt`
- `characters.visual_negative_prompt`
- `characters.visual_prompt_updated_at`

Do not replace your existing `data/` directory when installing this source update.
