# Kabuki-Cord Sprite Inventory

This is the replacement checklist for animated and sprite-like visual assets currently used by the app.

## Active Animated Sprites

| Asset | Purpose | Used by |
| --- | --- | --- |
| `web/assets/monitor_spy_frames/frame_000.png` through `frame_047.png` | Scanner Monitor popup activity animation: kabuki actor sneaks between buildings, drops mail, and peeks into windows. | `web/monitor.html`, `web/monitor.js`, `web/monitor.css` |
| `web/assets/scanner-kabuki-sheet.png` | Default topbar operation/status sprite, including idle/working/scanning fallback. | `web/styles.css`, `web/app.js` |
| `web/assets/scanner-kabuki-sync-sheet.png` | Topbar animation while syncing Discord servers/channels. | `web/styles.css`, `web/app.js` |
| `web/assets/scanner-kabuki-repair-sheet.png` | Topbar animation while repairing/reloading a server channel list. | `web/styles.css`, `web/app.js` |
| `web/assets/scanner-kabuki-backfill-sheet.png` | Topbar animation while backfilling older channel history. | `web/styles.css`, `web/app.js` |
| `web/assets/scanner-kabuki-latest-sheet.png` | Topbar animation while refreshing the latest visible messages. | `web/styles.css`, `web/app.js` |
| `web/assets/scanner-kabuki-refresh-sheet.png` | Topbar animation while refreshing local app state. | `web/styles.css`, `web/app.js` |
| `web/assets/scanner-kabuki-posting-sheet.png` | Topbar animation while posting an approved reply. | `web/styles.css`, `web/app.js` |
| `web/assets/scanner-kabuki-discord-blocked-sheet.png` | Topbar animation for Discord sign-in blocked/waiting/denied states. | `web/styles.css`, `web/app.js` |
| `web/assets/mode-kabuki-dry-sheet.png` | Response mode transition animation for Dry Mode. | `web/styles.css`, `web/app.js` |
| `web/assets/mode-kabuki-full-auto-sheet.png` | Response mode transition animation for Full Auto. | `web/styles.css`, `web/app.js` |
| `web/assets/mode-kabuki-semi-auto-sheet.png` | Response mode transition animation for Semi Auto. | `web/styles.css`, `web/app.js` |
| `web/assets/mode-kabuki-live-fire-sheet.png` | Response mode transition animation for Live Fire. | `web/styles.css`, `web/app.js` |

## Static Sprite-Like Assets

| Asset | Purpose | Used by |
| --- | --- | --- |
| `web/assets/source/kabuki-actor-reference.png` | High-resolution actor reference for regenerating upgraded sprite frames. | `scripts/generate_monitor_spy_frames.py` |
| `web/assets/runtime-mask-pixel.png` | Small pixel mask icon in the runtime footer. | `web/index.html` |
| `web/assets/app-icon-*.png`, `web/assets/app-icon.png` | Window/fav/taskbar app icons at multiple sizes. | `web/index.html`, packaging/runtime shell |
| `web/assets/app-icon-badge-32.png` | Red-dot/badged favicon for activity attention. | `web/app.js` |
| `web/assets/placeholders/server.svg` | Generic server placeholder icon. | `web/app.js`, `web/index.html` |
| `web/assets/placeholders/user.svg` | Generic remembered-user placeholder icon. | `web/app.js` |
| `web/assets/placeholders/channel.svg` | Generic channel placeholder icon. | Static asset reserve |
| `web/assets/placeholders/character.svg` | Generic character placeholder icon. | Static asset reserve |
| `web/assets/placeholders/runtime.svg` | Generic runtime placeholder icon. | Static asset reserve |

## Legacy / Candidate Cleanup

| Asset | Status |
| --- | --- |
| `web/assets/scanner-kabuki-spy-story-sheet.png` | Previous Scanner Monitor single-sheet animation. Replaced by frame-by-frame monitor sequence but kept for now as a fallback/reference. |
| `web/assets/scanner-kabuki-cutout.png` | Older cutout/reference asset. Not currently referenced by app code. |

## Generators

| Script | Output |
| --- | --- |
| `scripts/generate_monitor_spy_frames.py` | Regenerates the high-resolution frame-by-frame Scanner Monitor animation from `web/assets/source/kabuki-actor-reference.png`. |
| `scripts/generate_spy_story_sprite.py` | Generates the legacy single-sheet Scanner Monitor animation. |
| `scripts/generate_discord_blocked_sprite.py` | Regenerates `scanner-kabuki-discord-blocked-sheet.png`. |
