# Refresh Latest Messages V2 Sprite Prompt

CLI fallback image generation used `gpt-image-2` at high quality. The original Latest sheet was supplied as an action reference only, while the accepted Backfill V2 sheet controlled the actor identity, mask, costume, proportions, rendering, palette, camera, lighting, and prop quality.

The final brief requested exactly eight cells in a 4x2 atlas. It locked one message kiosk on the left and one actor on the right throughout this action story: idle with a cyan-edged message seated in one fixed slot; turn one brass recency dial; advance the same slip halfway; pull it out; inspect it with no readable writing; press the same dial to verify while holding the slip; return the slip to the same slot; recover to matching idle with the ready lamp cyan.

The prompt required exactly one kiosk, one message slip, one horizontal slot, one recency dial, and one ready lamp. It prohibited kiosk redesigns, moving controls, duplicate messages, scrolls, books, stamps, clocks, hourglasses, extra panels, teleporting props, random glyphs, floating symbols, exaggerated magic, text, logos, watermarks, and any variation in the flat `#00ff00` chroma-key background.

The CLI source is `output/imagegen/latest-v2-atlas-chromakey.png`, copied into the project as `design_assets/latest-v2-atlas-chromakey.png`. Automatic border sampling measured the generated key as `#0af80c`; the alpha result is `design_assets/latest-v2-atlas-transparent.png`.
