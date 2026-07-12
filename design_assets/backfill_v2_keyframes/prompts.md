# History Backfill V2 Sprite Prompt

CLI fallback image generation used `gpt-image-2` at high quality. The original backfill sheet was supplied as an action reference only, while the accepted Repair V2 sheet controlled the actor identity, mask, costume, proportions, rendering, palette, camera, lighting, and prop quality.

The final brief requested exactly eight cells in a 4x2 atlas. It locked one archive cabinet on the left and one actor on the right throughout this action story: idle with a distinctive violet ledger filed in its fixed second slot; reach; pull that ledger halfway out; hold it open with the empty slot still visible; turn older pages backward with a restrained cyan page-edge glow; place one brass index tab; slide the closed ledger back into the original slot; return to a matching idle pose with the cabinet's small cyan ready light.

The prompt required exactly four fixed ledger slots, one violet ledger, one index tab, and one ready light. It prohibited cabinet redesigns, changing shelf/slot counts, duplicate or spawned books, teleporting props, extra characters, random glyphs, clocks, arrows, floating symbols, exaggerated magic, text, logos, watermarks, and any variation in the flat `#00ff00` chroma-key background.

The CLI source is `output/imagegen/backfill-v2-atlas-chromakey.png`, copied into the project as `design_assets/backfill-v2-atlas-chromakey.png`. Automatic border sampling measured the generated key as `#08f80c`; the alpha result is `design_assets/backfill-v2-atlas-transparent.png`.
