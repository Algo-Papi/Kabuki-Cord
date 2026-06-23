from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
STYLE_PATH = ROOT / "web" / "styles.css"
ASSET_DIR = ROOT / "web" / "assets"
OUTPUT_DIR = ROOT / "docs" / "screenshots"
VIEWPORT = {"width": 1440, "height": 900}


def app_styles() -> str:
    css = STYLE_PATH.read_text(encoding="utf-8")
    return css.replace('url("/assets/', f'url("{ASSET_DIR.as_uri()}/')


FIXTURE_STYLES = """
body::before,
body::after {
  display: none !important;
  animation: none !important;
}

body {
  width: 1440px;
  height: 900px;
  overflow: hidden;
}

.screenshot-shell {
  width: 1440px;
  height: 900px;
  min-height: 900px;
  opacity: 1 !important;
  transform: none !important;
  filter: none !important;
  animation: none !important;
  overflow: hidden;
}

.screenshot-shell::before {
  display: none !important;
}

.screenshot-shell .workspace,
.screenshot-shell .server-panel,
.screenshot-shell .preview-panel {
  height: 900px;
}

.screenshot-shell .topbar {
  position: static;
}

.screenshot-shell .topbar-button-group {
  justify-content: flex-end;
}

.screenshot-shell .topbar-actions {
  gap: 9px;
}

.screenshot-shell .secondary-button,
.screenshot-shell .primary-button,
.screenshot-shell .small-button {
  white-space: nowrap;
}

.screenshot-shell .channel-list {
  padding-bottom: 12px;
}

.screenshot-shell .channel-name .hash-icon,
.screenshot-shell .server-icon-frame .fixture-icon,
.screenshot-shell .brand-mark .fixture-icon {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: linear-gradient(135deg, rgba(126, 216, 255, 0.22), rgba(149, 101, 255, 0.2));
  color: #eaf8ff;
  font-weight: 800;
}

.screenshot-shell .brand-mark .fixture-icon {
  width: 100%;
  height: 100%;
  border-radius: 16px;
  font-size: 18px;
}

.screenshot-shell .server-icon-frame .fixture-icon {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  font-size: 15px;
}

.screenshot-shell .character-card {
  cursor: default;
}

.screenshot-shell textarea {
  resize: none;
}

.screenshot-shell .preview-panel {
  border-right: 0;
}

.screenshot-shell .observed-actions .small-button {
  font-size: 12px;
}

.readme-approval-shot .approval-list {
  margin: 16px 18px;
}

.readme-approval-shot .approval-review-overlay {
  position: absolute;
  inset: 92px 42px 38px 112px;
  padding: 0;
  background: rgba(5, 8, 12, 0.54);
}

.readme-approval-shot .approval-review-dialog {
  width: min(1020px, 100%);
  max-height: 100%;
}

.readme-approval-shot .approval-review-body {
  padding: 18px;
}
"""


def document(body: str, *, mode: str = "runtime-mode-semi-auto") -> str:
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Kabuki-Cord README Fixture</title>
    <style>{app_styles()}</style>
    <style>{FIXTURE_STYLES}</style>
  </head>
  <body class="{mode}">
    {body}
  </body>
</html>"""


def rail(active: str = "Signal Lab") -> str:
    servers = [
        ("Signal Lab", "SL"),
        ("Arcade Ops", "AO"),
        ("Field Notes", "FN"),
        ("Sky Lantern", "SK"),
    ]
    bubbles = []
    for label, initials in servers:
        active_class = " active" if label == active else ""
        bubbles.append(
            f"""
            <button class="server-bubble{active_class}">
              <span class="server-icon-frame"><span class="fixture-icon">{initials}</span></span>
              <span class="server-bubble-label">{label[:10]}</span>
            </button>
            """
        )
    return f"""
      <aside class="server-rail">
        <div class="brand-mark"><span class="fixture-icon">KC</span></div>
        <div class="server-list">{''.join(bubbles)}</div>
        <button class="icon-button rail-add" title="Find newly joined servers">+</button>
      </aside>
    """


def server_panel() -> str:
    channels = [
        ("general", "12 remembered", True, True, False, False),
        ("field-notes", "8 remembered", False, True, True, False),
        ("odd-links", "3 remembered", False, True, False, False),
        ("night-shift", "Pinned", False, True, True, True),
        ("announcements", "Observe only", False, True, False, False),
    ]
    rows = []
    for name, meta, active, observe, engage, auto in channels:
        rows.append(
            f"""
            <div class="channel-row{' active' if active else ''}">
              <div class="channel-name">
                <span class="hash-icon">#</span>
                <div><strong>{name}</strong><span>{meta}</span></div>
              </div>
              <div class="channel-actions">
                <button class="icon-mini{' on' if name == 'night-shift' else ''}">★</button>
                <button class="pill-toggle{' on observe' if observe else ''}">Observe</button>
                <button class="pill-toggle{' on engage' if engage else ''}">Engage</button>
                <button class="pill-toggle{' on auto' if auto else ''}">Auto</button>
              </div>
            </div>
            """
        )
    return f"""
      <aside class="server-panel">
        <header class="server-header">
          <div>
            <div class="eyebrow">Selected Server</div>
            <h1>Signal Lab</h1>
          </div>
          <button class="icon-button">✓</button>
        </header>
        <section class="panel-section">
          <div class="section-title">Server Settings</div>
          <label class="field"><span>Label</span><input value="Signal Lab" readonly /></label>
          <label class="field"><span>Character Card</span><select><option>Max Arcadia (sample_card.json)</option></select></label>
          <label class="field">
            <span>Scan Cadence</span>
            <div class="inline-input"><input value="180" readonly /><span>seconds</span></div>
          </label>
        </section>
        <section class="panel-section channels-section">
          <div class="section-title with-action">
            <span>Channels</span>
            <div class="button-row">
              <button class="small-button">Open</button>
              <button class="small-button">Repair</button>
              <button class="small-button">Latest</button>
              <button class="small-button">Backfill</button>
            </div>
          </div>
          <div class="channel-list">{''.join(rows)}</div>
        </section>
        <footer class="account-footer">
          <div class="avatar-dot runtime-avatar">K</div>
          <div><strong>Kabuki runtime</strong><span>scanner ready</span></div>
        </footer>
      </aside>
    """


def workspace() -> str:
    return f"""
      <main class="workspace">
        <header class="topbar">
          <div class="topbar-title">
            <div class="eyebrow">Server Studio</div>
            <h2>Character & automation</h2>
          </div>
          <div class="topbar-actions">
            <div class="operation-status scanning">
              <span class="scanner-sprite scan-sprite"></span>
              <span>Scanning</span>
              <small>general</small>
            </div>
            <span class="status-pill ok">API key set</span>
            <button class="secondary-button">Start</button>
            <button class="secondary-button">Sync Discord</button>
            <button class="secondary-button">Refresh</button>
            <button class="primary-button">Save Changes</button>
          </div>
        </header>
        <section class="character-strip">
          <div class="character-cards">
            <article class="character-card">
              <div class="portrait">M</div>
              <strong>Max Arcadia</strong>
              <small>default.json</small>
            </article>
            <article class="character-card active">
              <div class="portrait">M</div>
              <strong>Max Arcadia</strong>
              <small>cards/sample_generalist.json</small>
            </article>
          </div>
          <button class="create-character"><span>+</span><span>Create Character</span></button>
        </section>
        <nav class="tabs">
          <button class="tab active">Identity</button>
          <button class="tab">Behavior</button>
          <button class="tab">Growth</button>
          <button class="tab">History</button>
          <button class="tab">API & Runtime</button>
        </nav>
        <section class="tab-pane active">
          <div class="form-grid">
            <label class="field span-2"><span>Character Name</span><input value="Max Arcadia" readonly /></label>
            <label class="field span-2">
              <span>System Prompt</span>
              <textarea rows="7" readonly>Max is a fictional overconfident forum regular who claims expertise across every topic, speaks casually, and occasionally mixes up details. He asks for sources when challenged and backs off when a topic needs care.</textarea>
            </label>
            <label class="field"><span>Aliases</span><textarea rows="4" readonly>max
arcadia
field guy</textarea></label>
            <label class="field"><span>Trigger Keywords</span><textarea rows="4" readonly>mystery
evidence
archive
weird signal</textarea></label>
          </div>
        </section>
      </main>
    """


def preview_panel() -> str:
    return """
      <aside class="preview-panel">
        <div class="preview-tabs">
          <button class="preview-tab active">Preview</button>
          <button class="preview-tab">Events</button>
          <span class="api-spend-pill"><span>$0.01842</span><small>42 calls</small></span>
        </div>
        <section class="preview-mode active">
          <div class="preview-block">
            <div class="section-title">Observed Conversation</div>
            <div class="observed-list">
              <article class="observed-card">
                <div class="observed-copy"><strong>Rin Vale</strong><span>Talking about old archives, missing context, and whether the latest source is reliable enough to cite.</span></div>
                <div class="observed-actions">
                  <button class="small-button observed-open-action"><span>Open Latest Post</span></button>
                  <button class="small-button"><span>React</span></button>
                  <button class="small-button"><span>Suggest Reply</span></button>
                  <button class="small-button"><span>Guide User</span></button>
                </div>
              </article>
              <article class="observed-card">
                <div class="observed-copy"><strong>Byte Lantern</strong><span>Comparing two theories and asking if anyone has a cleaner timeline.</span></div>
                <div class="observed-actions">
                  <button class="small-button observed-open-action"><span>Open Latest Post</span></button>
                  <button class="small-button"><span>React</span></button>
                  <button class="small-button"><span>Suggest Reply</span></button>
                  <button class="small-button"><span>Guide User</span></button>
                </div>
              </article>
            </div>
          </div>
        </section>
      </aside>
    """


def dashboard_body() -> str:
    return f"""
      <div class="shell screenshot-shell">
        {rail()}
        {server_panel()}
        {workspace()}
        {preview_panel()}
      </div>
    """


def approvals_body() -> str:
    approval_card = """
      <section class="approval-server-group">
        <div class="approval-group-header"><strong>Signal Lab</strong><span>2 queued</span></div>
        <section class="approval-channel-group">
          <div class="approval-channel-header"><span># general</span><small>1 approval</small></div>
          <div class="approval-item">
            <div class="approval-item-top">
              <div class="approval-meta"><strong>Max Arcadia</strong><span># general · Jun 23, 9:42 AM</span></div>
              <span class="approval-type">reply</span>
            </div>
            <div class="approval-reason"><i></i><span>Recent thread contains a direct question and a useful opening for a cautious answer.</span></div>
            <details class="approval-source approval-source-collapsible">
              <summary class="approval-source-title"><span><i></i> Context collapsed</span><small>4 messages</small></summary>
              <div class="approval-source-body"></div>
            </details>
            <div class="approval-target-summary"><i></i><span>Replying to <strong>Rin Vale</strong>: Is there an actual archive link for that claim?</span></div>
            <label class="approval-field-label">Draft to send</label>
            <textarea class="approval-draft" rows="5" readonly>yeah i would slow down on that one. i remember seeing a scan but not the clean source chain, so i would call it interesting not proven until someone posts the archive link</textarea>
            <div class="approval-actions">
              <button class="small-button">Review</button>
              <button class="small-button">Save</button>
              <button class="small-button">Regenerate</button>
              <button class="small-button">Open Conversation</button>
              <button class="primary-button approval-send">Approve & Send</button>
            </div>
          </div>
        </section>
      </section>
    """
    review_modal = """
      <div class="approval-review-overlay">
        <div class="approval-review-dialog">
          <div class="approval-review-header">
            <div>
              <div class="eyebrow">Approval Review</div>
              <h2>Max Arcadia approval</h2>
              <span id="approvalReviewSubtitle">Signal Lab / # general / Jun 23, 9:42 AM</span>
            </div>
            <button class="icon-button">×</button>
          </div>
          <div class="approval-review-body">
            <div class="approval-review-layout">
              <section class="approval-review-context">
                <div class="approval-reason"><i></i><span>Recent thread contains a direct question and a useful opening for a cautious answer.</span></div>
                <div class="approval-source approval-source-expanded">
                  <div class="approval-source-title"><span>Source context</span><small>4 messages</small></div>
                  <div class="approval-source-body">
                    <article class="approval-source-message"><div class="approval-source-message-head"><strong>Byte Lantern</strong><span>9:37 AM</span></div><p>The timeline is messy. Two people are citing the same screenshot but the dates do not line up.</p></article>
                    <article class="approval-source-message target"><div class="approval-source-message-head"><strong>Rin Vale</strong><span>9:40 AM - reply target</span></div><p>Is there an actual archive link for that claim or are we just passing around summaries?</p></article>
                    <article class="approval-source-message"><div class="approval-source-message-head"><strong>Maple Desk</strong><span>9:41 AM</span></div><p>I found a mirror, but not the first upload. Could still be useful if someone checks it.</p></article>
                  </div>
                </div>
                <div class="approval-target-summary"><i></i><span>Replying to <strong>Rin Vale</strong>: Is there an actual archive link for that claim?</span></div>
                <div class="poster-chips"><span>Reply to</span><button class="active">Rin Vale</button><button>Byte Lantern</button><button>Maple Desk</button></div>
              </section>
              <section class="approval-review-editor">
                <label class="approval-field-label">Draft to send</label>
                <textarea class="approval-draft approval-review-draft" rows="9" readonly>yeah i would slow down on that one. i remember seeing a scan but not the clean source chain, so i would call it interesting not proven until someone posts the archive link</textarea>
                <label class="approval-field-label">Regeneration note</label>
                <textarea class="approval-instruction" rows="4" readonly>Make it more direct and less polished. Keep the caveat.</textarea>
                <div class="approval-review-actions">
                  <button class="small-button">Save</button>
                  <button class="small-button">Regenerate</button>
                  <button class="small-button">Open Conversation</button>
                  <button class="small-button">Discard</button>
                  <button class="primary-button approval-send">Approve & Send</button>
                </div>
              </section>
            </div>
          </div>
        </div>
      </div>
    """
    return f"""
      <div class="shell screenshot-shell readme-approval-shot">
        {rail()}
        <aside class="server-panel">
          <header class="server-header"><div><div class="eyebrow">Approvals</div><h1>Review Queue</h1></div></header>
          <div class="approval-list">{approval_card}</div>
        </aside>
        <main class="workspace">
          <header class="topbar"><div class="topbar-title"><div class="eyebrow">Approval Queue</div><h2>Grouped by server and channel</h2></div></header>
          <div class="approval-list">{approval_card}</div>
        </main>
        {preview_panel()}
        {review_modal}
      </div>
    """


def capture(name: str, body: str, *, mode: str = "runtime-mode-semi-auto") -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_DIR / name
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=1)
        page.set_content(document(body, mode=mode), wait_until="networkidle")
        page.screenshot(path=str(output), full_page=False)
        browser.close()
    print(f"wrote {output}")


def main() -> None:
    capture("kabuki-cord-dashboard.png", dashboard_body())
    capture("kabuki-cord-approvals.png", approvals_body(), mode="runtime-mode-live-fire")


if __name__ == "__main__":
    main()
