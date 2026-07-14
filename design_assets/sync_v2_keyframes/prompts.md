# Discord Sync V2 Sprite Prompt

Built-in image generation received the original 11-frame sync sheet as the network-state reference and the accepted Scanner V2 sheet as the character/style reference.

The brief requested exactly eight cells in a 4x2 atlas using one fixed shrine-style console with exactly three sockets: dim idle, reach, light left, connect center, connect right, press the brass commit button, confirm/nod, and return to dim idle. It locked console geometry, socket count/spacing, actor, camera, scale, and baseline; prohibited the original sheet's shifting lantern count and loose network montage; and required a flat `#00FF00` chroma-key background.

The chroma-key source is `design_assets/sync-v2-atlas-chromakey.png`. Background removal used the measured key color `#04F904` because the generated atlas had white grid borders that confused automatic border sampling. The transparent atlas is `design_assets/sync-v2-atlas-transparent.png`; `scripts/generate_sync_v2_sprite.py` crops inside those borders and exports the production frames, sheet, and GIF previews through the shared V2 sprite pipeline.
