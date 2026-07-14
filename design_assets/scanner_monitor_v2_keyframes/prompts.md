# Scanner Monitor V2 Animation

Scanner Monitor V2 replaces six independently generated alley scenes and long transition overlays with one fixed monitor plate and one consistent eight-pose magnifier atlas.

## Sources

- `../dojo-sweep-v2-background.png`: shared locked 4:3 monitor alley plate.
- `../scanner-monitor-v2-atlas-transparent.png`: transparent 2x4 actor/magnifier atlas.
- `../scanner-monitor-v2-atlas-chromakey.png`: retained flat-green generation source.

## Action story

The eight direct beats are alert crouch, raise magnifier, inspect low left, sweep low center, inspect low right, cyan clue detection, compact confirmation, and crouched recovery.

The generation brief required one actor, one magnifier, one camera, one scale, one feet baseline, a consistent mask/costume, and generous internal cell padding. It prohibited full scenes, cell overlap, duplicate lenses, magic swirls, text, motion blur, crossfades, and identity or prop drift.

The atlas was generated through the previously selected CLI fallback with `gpt-image-2` at high quality, then converted from the sampled green key (`#06F810`) to soft-matted alpha locally.

## Runtime output

`scripts/generate_scanner_monitor_v2_frames.py` composites the actor poses over the fixed background and writes eight direct 640x480 WebPs to:

`src/nhi_zues/web/assets/monitor_spy_v2_frames/`

The runtime displays each frame for 350ms without opacity blending or stage-transition overlays.
