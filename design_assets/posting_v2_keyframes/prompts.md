# Posting V2 Sprite Prompt

Built-in image generation received the original posting sheet as the semantic reference and the accepted Discord Blocked V2 sheet as the character/style reference.

The production brief requested exactly eight cells in a 4x2 atlas: idle with sealed envelope, crouch and raise, extend, halfway insert, complete insertion with mailbox flag, confirmation pulse, satisfied recovery, and return to idle. It locked the actor, mailbox geometry, camera, scale, and left/right placement; prohibited the original sequence's changing desks/boxes and excessive fireworks; and required a flat `#00FF00` chroma-key background with no green in the subject.

The chroma-key source is `design_assets/posting-v2-atlas-chromakey.png`. Background removal produced `design_assets/posting-v2-atlas-transparent.png`. `scripts/generate_posting_v2_sprite.py` exports transparent frames, the app sheet, and GIF previews through the shared V2 sprite pipeline.
