# Default Scanner V2 Sprite Prompt

Built-in image generation received the original 16-frame scanner sheet as the magnifier/search reference and the accepted Posting V2 sheet as the character/style reference.

The brief requested exactly eight cells in a 4x2 atlas: alert idle, raise magnifier, inspect low-left, sweep center, inspect low-right, detect one cyan clue point, confirm with a nod, and return to idle. It locked the same actor, mask, costume, magnifier, hand, camera, scale, and ground baseline; prohibited the original sheet's lens/pose drift and decorative noise; and required a flat `#00FF00` chroma-key background.

The chroma-key source is `design_assets/scanner-v2-atlas-chromakey.png`. Background removal produced `design_assets/scanner-v2-atlas-transparent.png`. `scripts/generate_scanner_v2_sprite.py` exports the production frames, sheet, and GIF previews through the shared V2 sprite pipeline.
