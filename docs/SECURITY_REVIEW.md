# Kabuki-Cord Security Review

Date: 2026-06-22
Scope: v1.0 public repository baseline.

## Fixed Before v1.0 Publish

- Static file serving now resolves requested paths and rejects traversal outside `web/`.
- Local GUI API calls require a per-run token, JSON requests, localhost `Host`, and same-origin `Origin`/`Referer` when present.
- Discord credentials are stored in the operating system keyring instead of `.env`.
- Public server/channel config uses placeholders; local real config is kept under ignored `.local/`.
- GitHub self-update checks only allow the exact `Algo-Papi/Kabuki-Cord` GitHub remote and refuses dirty working trees.
- CI uses read-only contents permission and runs compile plus a secret-pattern scan.
- Secret scanning includes extensionless files and force-added `.env` style files.

## Current Residual Risks

- The GUI is a local privileged control surface. It must remain bound to loopback and should not be exposed on a LAN/public interface.
- The self-update feature still follows the mutable `main` branch. A future installer-grade updater should use signed release artifacts and checksum verification.
- When LLM drafting is enabled, recent Discord messages, user memory summaries, character memory, and per-user instructions may be sent to OpenAI. This is opt-in, but the UI should continue making this visible before paid drafting is enabled.
- Browser profile data can contain active session cookies. It is ignored by Git, but users should never force-add `.profiles/`.

## Recommended Next Hardening

- Add a pre-commit hook that runs `python scripts/secret_scan.py`.
- Add a release build workflow that creates signed installer artifacts.
- Add an explicit privacy disclosure modal before enabling LLM drafting for the first time.
- Add event logging for security-sensitive actions: credential save, login launch, update check, update apply, dry-run disable, and auto-respond enable.
- Consider redacting Discord IDs from the default `/api/state` response unless the UI is on the relevant server/channel view.
