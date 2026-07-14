# Dojo Sweep Monitor Animation

The Dojo Sweep monitor animation uses five generated pose keyframes rather than a single static reference.

## Keyframes

- `key_000.png`: sweep wind-up / left-side pull
- `key_001.png`: left-to-center sweep in-between
- `key_002.png`: center low sweep
- `key_003.png`: center-to-right sweep in-between
- `key_004.png`: right-side follow-through

The deterministic generator at `scripts/generate_dojo_sweep_frames.py` crossfades those poses into a 48-frame loop and adds:

- red-eye pulse
- broom-path dust vortex
- impact flash at the broom head
- drifting dust particles
- small leaf flecks
- red sweep-mode vignette

Output:

`web/assets/monitor_dojo_sweep_frames/frame_000.png` through `frame_047.png`

## Prompt Family

The source keyframes were generated with the built-in image generation tool using this structure:

```text
Create one high-quality pixel-art keyframe of the Kabuki-Cord kabuki theater actor aggressively sweeping a stone path with a straw broom, glowing red eyes, in a dark Japanese alley/dojo entrance at night.
Pose: [wind-up / left-to-center / center sweep / center-to-right / right follow-through].
Chibi but detailed kabuki actor, black robe with dark purple and red trim, white kabuki mask with red markings, black theatrical hair, scarf tails, glowing red eyes, straw broom.
Polished late-16-bit/GBA-plus pixel art, crisp readable silhouette, 20-40% more detail than Game Boy Advance sprites.
No text, no watermark, no UI, no logos, no gore, no weapon, no extra characters.
```

The monitor loops the 48-frame sweep cycle while the current scanner target is a Dojo Sweep target. The scan countdown still reports the dwell timing, but the actor continues sweeping at animation speed instead of stretching one broom stroke across the whole dwell.
