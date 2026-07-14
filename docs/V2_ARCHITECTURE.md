# Kabuki-Cord V2 Architecture

V2 keeps the personal-account browser transport requested by the project owner, but treats it as an unreliable adapter rather than the application core.

## Boundaries

- `transport.py` defines the async chat transport contract. The runner depends on this protocol; `DiscordWebSession` is the current browser adapter.
- Routing, approvals, budgets, duplicate prevention, safety review, and memory do not depend on Playwright types.
- The local HTTP UI remains loopback-only and requires a per-process token, same-origin requests, JSON bodies, bounded request sizes, traversal-safe static paths, and restrictive security headers.

## Local data

- User data defaults to `%LOCALAPPDATA%\Kabuki-Cord` on Windows and can be isolated with `KABUKI_CORD_DATA_DIR` for development/testing.
- Existing `.state`, `.profiles/nhi-zues`, config, cards, and non-secret `.env` settings are migrated once. Copy operations use temporary targets so interrupted profile migrations do not leave a partial destination.
- Discord and OpenAI credentials live in the operating system keyring. The UI exposes explicit clear actions and never returns credential values.

## Persistence

- `state.db` is the authoritative SQLite/WAL document store.
- Mutations use `BEGIN IMMEDIATE` transactions and process-local canonical-path locks. This prevents concurrent scanner, monitor, and operator actions from overwriting one another.
- JSON mirrors remain for readable recovery and V1 tooling compatibility.

## Delivery policy

- The global response mode is an upper bound on automation.
- A channel must also have Observe, Engage, and Auto enabled before any unattended message is eligible.
- Unknown model pricing fails closed. Daily limits and one shared runtime-session/call budget apply to scanner and manual generation paths.

## Packaging and release

- Web, native icon, and first-run default assets are package resources; runtime path resolution never depends on the launch working directory.
- Source keyframes live in `design_assets/` and are excluded from wheels/releases.
- Runtime monitor frames are size-appropriate WebP assets and heavy sweep frames load only when needed.
- CI verifies Python 3.11/3.13, full Ruff, unit/UI contracts, JavaScript syntax, dependency audit, secret scanning, and wheel contents.
- Windows releases use an explicit allowlist, optional Authenticode signing, and a SHA-256 sidecar.
