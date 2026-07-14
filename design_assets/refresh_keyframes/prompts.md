# Refresh Action Sprite Prompts

Generated with the built-in image generation tool as ten separate chroma-key keyframes, then cleaned with `remove_chroma_key.py`, normalized to 256px transparent source frames, and assembled with `scripts/generate_refresh_sprite.py`.

Common style constraints:

- Use the Kabuki-Cord HD kabuki actor reference: white/red mask, black hair mass, dark robe with red and purple trim, scarf/fan, readable chibi action-game silhouette.
- Use a perfectly flat solid `#00ff00` chroma-key background with no shadow, floor, gradients, or texture.
- Keep the subject fully separated from the background with generous padding.
- No readable text, logos, or watermarks.
- Polished GBA-era / modern high-detail pixel-art sprite style.

Frame sequence:

1. Actor idle beside a small Japanese lacquered app-state console/mirror shrine with a dim cyan refresh ring.
2. Actor leans in and grips a circular refresh wheel/rope attached to the console.
3. Actor pulls the wheel hard; cyan refresh ring rotates with motion streaks.
4. Actor sweeps stale gray dust/static motes away from the console with fan and sleeve.
5. Actor flips glowing tile shutters/lantern switches on the console as panels light up.
6. Actor spins a floating cyan circular refresh ring around the console with a sweeping fan motion.
7. Console bursts with clean cyan/purple light while stale motes vanish.
8. Actor stamps a small glowing state seal on the console's lower panel.
9. Actor presents the refreshed console/mirror with an open fan gesture.
10. Actor returns to a calm ready stance beside the refreshed console, looping toward frame 1.
