# Server/Channel Repair V2 Sprite Prompt

CLI fallback image generation used `gpt-image-2` at high quality. The original repair sheet was supplied as an action reference only, while the accepted Discord Sync V2 sheet controlled the actor identity, costume, proportions, rendering, palette, camera, and shrine-console design language.

The final brief requested exactly eight cells in a 4x2 atlas. It locked one cabinet on the left and one actor on the right throughout this action story: notice one red failed indicator; point to diagnose; open one hinged access panel; find one loose cyan cable plug and its empty socket; reconnect that plug with a compact contact spark; press one fixed verification button; close the panel and confirm three cyan indicators; return to a healthy idle pose.

The prompt required exactly three fixed circular indicators, one cabinet, one hinged panel, one cable, one plug, one socket, and one verification button. It prohibited cabinet redesigns, changing indicator counts, extra tools or cables, duplicate limbs, random glyphs, teleporting props, explosions, motion blur, text, logos, watermarks, and any variation in the flat `#00ff00` chroma-key background.

The CLI source is `output/imagegen/repair-v2-atlas-chromakey.png`, copied into the project as `design_assets/repair-v2-atlas-chromakey.png`. Automatic border sampling measured the generated key as `#07f80b`; the alpha result is `design_assets/repair-v2-atlas-transparent.png`.
