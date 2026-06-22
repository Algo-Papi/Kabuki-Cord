# Security Policy

Kabuki-Cord is a local desktop/control-panel application. Treat browser profiles, runtime memory, API keys, and Discord account credentials as sensitive local data.

## Supported Version

Security fixes target the current `main` branch until formal releases are cut.

## Secret Handling

- Do not commit `.env`, `.local/`, `.state/`, `.profiles/`, logs, databases, screenshots, or browser profile data.
- OpenAI API keys are stored only in the ignored local `.env` file when configured through the app.
- Discord credentials are stored through the operating system keyring. They are not returned by the GUI API.
- If a secret is pasted into chat, logs, or a commit by mistake, rotate it immediately.

## Local API Boundary

The GUI binds to `127.0.0.1` by default. Do not expose the GUI server to a public interface. The self-update endpoint runs only fixed Git commands and refuses to update when the working tree has local changes.

## Safe Defaults

- Message sending starts in dry-run mode.
- LLM drafting is disabled by default.
- Channel engagement is disabled in the public example config.
- Per-channel auto-respond is disabled by default.
- Proactive drafts require approval unless explicitly changed by the operator.

## Reporting

Open a private issue or contact the maintainer directly for security-sensitive reports. Include reproduction steps, affected version/commit, and impact.
