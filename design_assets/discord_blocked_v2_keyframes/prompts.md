# Discord Blocked V2 Sprite Prompt

Built-in image generation was given the existing 10-frame sheet as a visual reference, then asked to create a new asset rather than copy its poses.

The production brief requested exactly eight equal cells in a 4x2 atlas: alert idle, raise key, turn key, ward glow, denial impact, recoil, recover, and return to idle. It locked the same actor, mask, gate, camera, scale, and left/right placement across the sequence; required readable body-weight and scarf follow-through; prohibited text and extra icons; and used a flat `#00FF00` chroma-key background with no green in the subject.

The generated chroma-key source is `design_assets/discord-blocked-v2-atlas-chromakey.png`. Background removal produced `design_assets/discord-blocked-v2-atlas-transparent.png`, and `scripts/generate_discord_blocked_v2_sprite.py` crops the eight cells into production frames, a horizontal app sheet, a standalone GIF, and a side-by-side comparison GIF.
