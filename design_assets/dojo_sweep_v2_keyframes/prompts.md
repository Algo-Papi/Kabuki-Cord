# Dojo Sweep V2 Monitor Animation

Dojo Sweep V2 replaces five independently generated full-scene poses and their full-frame crossfades with two stable sources:

- `../dojo-sweep-v2-background.png`: one locked 4:3 moonlit alley plate with no actor.
- `../dojo-sweep-v2-atlas-transparent.png`: one 2x4 atlas containing a consistent actor and broom across eight action beats.

The atlas sequence is ready, wind-up, left contact, center drive, right follow-through, dust separation, evidence reveal, and ready recovery. The production generator reuses the clean first pose for recovery and composites all frames over the same background, so the room and camera never drift.

## Generation

Both sources were generated through the previously selected CLI fallback using `gpt-image-2` at high quality.

The background edit removed the actor from the original monitor alley while preserving the camera, architecture, lighting, palette, and open floor.

The actor prompt required:

- exactly two columns by four rows and eight equal 4:3 cells;
- the accepted V2 actor identity, mask, costume, proportions, and pixel-art language;
- one consistent straw broom;
- locked scale, baseline, camera, and placement;
- a flat `#00FF00` background with no floor, shadows, gutters, labels, or UI;
- restrained dust and one small crimson evidence-seal reveal;
- no motion blur, ghosting, giant dust hoops, duplicate limbs, or extra characters.

The chroma-key source is retained as `../dojo-sweep-v2-atlas-chromakey.png`. Local matte removal produced the transparent atlas used by `scripts/generate_dojo_sweep_v2_frames.py`.

## Runtime output

The generator writes eight direct 640x480 WebP frames to:

`src/nhi_zues/web/assets/monitor_dojo_sweep_v2_frames/`

The runtime displays each frame for 300ms. It does not interpolate or crossfade full scenes.
