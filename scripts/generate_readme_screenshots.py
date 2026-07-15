from __future__ import annotations

import base64
import mimetypes
import re
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "src" / "nhi_zues" / "web"
STYLE_PATH = WEB_ROOT / "styles.css"
ICON_STYLE_PATH = WEB_ROOT / "icons.css"
MONITOR_STYLE_PATH = WEB_ROOT / "monitor.css"
ASSET_DIR = WEB_ROOT / "assets"
OUTPUT_DIR = ROOT / "docs" / "screenshots"
VIEWPORT = {"width": 1440, "height": 900}


def app_styles() -> str:
    css = STYLE_PATH.read_text(encoding="utf-8")
    return inline_asset_urls(
        css,
        {"scanner-kabuki-v2-sheet.png", "update-mask-workshop-checking-v2-sheet.png"},
    )


def icon_styles() -> str:
    return ICON_STYLE_PATH.read_text(encoding="utf-8")


def monitor_styles() -> str:
    css = MONITOR_STYLE_PATH.read_text(encoding="utf-8")
    return inline_asset_urls(css, {"monitor-arigato-v2-sheet.png"})


def image_data_uri(path: Path) -> str:
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


def inline_asset_urls(css: str, selected: set[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        asset = ASSET_DIR / match.group(1)
        return (
            f'url("{image_data_uri(asset)}")'
            if asset.name in selected and asset.is_file()
            else match.group(0)
        )

    return re.sub(r'url\("/assets/([^"?]+)"\)', replace, css)


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

.screenshot-shell *,
.screenshot-shell *::before,
.screenshot-shell *::after,
.readme-help-shot .onboarding-overlay *,
.readme-help-shot .onboarding-overlay *::before,
.readme-help-shot .onboarding-overlay *::after,
.readme-update-shot .update-overlay *,
.readme-update-shot .update-overlay *::before,
.readme-update-shot .update-overlay *::after {
  animation: none !important;
  transition: none !important;
  caret-color: transparent !important;
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
.screenshot-shell .server-icon-frame .fixture-icon {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: linear-gradient(135deg, rgba(126, 216, 255, 0.22), rgba(149, 101, 255, 0.2));
  color: #eaf8ff;
  font-weight: 800;
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

.screenshot-shell .operation-status.scanning .scanner-sprite {
  animation: none !important;
  background-position: -204px 0;
}

.screenshot-shell .brand-mark img,
.screenshot-shell .runtime-avatar img {
  width: 100%;
  height: 100%;
  object-fit: contain;
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

.readme-help-shot,
.readme-update-shot {
  position: relative;
  width: 1440px;
  height: 900px;
  overflow: hidden;
}

.readme-help-shot .onboarding-overlay,
.readme-update-shot .update-overlay {
  position: absolute;
}

.readme-help-shot .onboarding-card {
  max-height: 844px;
}

.readme-update-shot .update-workshop-sprite,
.readme-update-shot .update-phase-bar > span.active::after {
  animation: none !important;
}

.readme-update-shot .update-workshop-sprite {
  background-position: -768px 0;
}
"""


MONITOR_FIXTURE_STYLES = """
body {
  width: 1440px;
  height: 900px;
  overflow: hidden;
}

.monitor-shell {
  width: min(1180px, calc(100vw - 36px));
  min-height: 0;
  margin: 0 auto;
  padding-bottom: 18px;
}

.spy-scene {
  aspect-ratio: auto;
  height: 270px;
  min-height: 0;
}

.action-history-panel {
  margin-bottom: 88px;
}

.spy-frame {
  opacity: 1 !important;
}

.spy-frame:not(.active),
.stage-transition,
.stage-glints,
.delivery-burst,
.monitor-toast {
  animation: none !important;
}

.monitor-toast {
  opacity: 1;
}

.monitor-shell *,
.monitor-shell *::before,
.monitor-shell *::after,
.monitor-toasts *,
.monitor-toasts *::before,
.monitor-toasts *::after {
  animation: none !important;
  transition: none !important;
  caret-color: transparent !important;
}

.delivery-character-toast {
  background-position: 100% 0;
}

.toast-stars span {
  opacity: 0;
}
"""


def document(body: str, *, mode: str = "runtime-mode-semi-auto") -> str:
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Kabuki-Cord README Fixture</title>
    <style>{icon_styles()}</style>
    <style>{app_styles()}</style>
    <style>{FIXTURE_STYLES}</style>
  </head>
  <body class="{mode}">
    {body}
  </body>
</html>"""


def monitor_document(body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Kabuki-Cord Scanner Monitor Fixture</title>
    <style>{monitor_styles()}</style>
    <style>{MONITOR_FIXTURE_STYLES}</style>
  </head>
  <body>
    {body}
  </body>
</html>"""


def rail(active: str = "Signal Lab") -> str:
    app_icon = image_data_uri(ASSET_DIR / "app-icon-64.png")
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
        <div class="brand-mark"><img src="{app_icon}" alt="" /></div>
        <div class="server-list">{''.join(bubbles)}</div>
        <button class="icon-button rail-add" title="Find newly joined servers"><i class="bi bi-plus-lg"></i></button>
      </aside>
    """


def server_panel() -> str:
    app_icon = image_data_uri(ASSET_DIR / "app-icon-64.png")
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
                <button class="icon-mini{' on' if name == 'night-shift' else ''}"><i class="bi bi-pin-angle-fill"></i></button>
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
          <button class="icon-button" title="Save server settings"><i class="bi bi-save2"></i></button>
        </header>
        <section class="panel-section">
          <div class="section-title">Server Settings</div>
          <label class="field"><span>Label</span><input value="Signal Lab" readonly /></label>
          <label class="field"><span>Character Card</span><select><option>Max Arcadia (sample_card.json)</option></select></label>
          <label class="safety-review-toggle">
            <input type="checkbox" />
            <span><strong>Dojo Sweep</strong><small>Deep review override for accessible channel history.</small></span>
          </label>
        </section>
        <section class="panel-section channels-section">
          <div class="section-title with-action">
            <span>Channels</span>
            <div class="button-row">
              <button class="small-button"><i class="bi bi-box-arrow-up-right"></i> Open</button>
              <button class="small-button"><i class="bi bi-wrench-adjustable"></i> Repair</button>
              <button class="small-button"><i class="bi bi-arrow-clockwise"></i> Latest</button>
              <button class="small-button"><i class="bi bi-clock-history"></i> Backfill</button>
              <button class="small-button"><i class="bi bi-plus"></i> Add</button>
            </div>
          </div>
          <div class="channel-list">{''.join(rows)}</div>
        </section>
        <footer class="account-footer">
          <div class="avatar-dot runtime-avatar"><img src="{app_icon}" alt="" /></div>
          <div><strong>Kabuki runtime</strong><span>scanner ready</span></div>
        </footer>
      </aside>
    """


def workspace() -> str:
    mask = image_data_uri(ASSET_DIR / "kabuki-mask-mark-v2.png")
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
            <div class="topbar-button-group">
              <button class="secondary-button"><i class="bi bi-question-circle"></i> Help</button>
              <button class="secondary-button"><i class="bi bi-pause-fill"></i> Pause</button>
              <button class="secondary-button"><i class="bi bi-binoculars"></i> Monitor</button>
              <button class="secondary-button"><i class="bi bi-diagram-3"></i> Sync Discord</button>
              <button class="secondary-button"><i class="bi bi-arrow-clockwise"></i> Refresh</button>
              <button class="primary-button"><i class="bi bi-check2"></i> Save Changes</button>
            </div>
          </div>
        </header>
        <section class="character-strip">
          <div class="character-cards">
            <article class="character-card" style="--card-accent:#7ed8ff;--card-accent-rgb:126,216,255">
              <div class="portrait"><img src="{mask}" alt="" /></div>
              <strong>Starter Mask</strong>
              <small>default.json</small>
            </article>
            <article class="character-card active" style="--card-accent:#ff64d8;--card-accent-rgb:255,100,216">
              <div class="portrait"><img src="{mask}" alt="" /></div>
              <strong>Max Arcadia</strong>
              <small>cards/sample_generalist.json</small>
            </article>
          </div>
          <button class="create-character"><i class="bi bi-plus-lg"></i><span>Create Character</span></button>
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
          <button class="preview-tab">Replies <span class="event-badge">2</span></button>
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


def help_body() -> str:
    return f"""
      <div class="readme-help-shot">
        {dashboard_body()}
        <div class="onboarding-overlay">
          <div class="onboarding-card help-center">
            <div class="onboarding-header">
              <div>
                <div class="eyebrow">Kabuki-Cord Field Manual</div>
                <h2>Help &amp; setup</h2>
                <p>Start safely, shape a character, and collect useful diagnostics without uploading anything.</p>
              </div>
              <button class="icon-button" aria-label="Close help"><i class="bi bi-x-lg"></i></button>
            </div>
            <div class="help-layout">
              <nav class="help-nav" aria-label="Help topics">
                <button class="active"><i class="bi bi-flag"></i><span>Quick start</span></button>
                <button><i class="bi bi-discord"></i><span>Discord sign-in</span></button>
                <button><i class="bi bi-person-vcard"></i><span>Character cards</span></button>
                <button><i class="bi bi-toggles"></i><span>Channel actions</span></button>
                <button><i class="bi bi-broadcast"></i><span>Response modes</span></button>
                <button><i class="bi bi-wrench-adjustable-circle"></i><span>Diagnostics</span></button>
              </nav>
              <div class="help-content">
                <section class="help-topic active">
                  <div class="help-topic-heading"><span>01</span><div><h3>Safe first run</h3><p>Complete these in order. Green items are already ready.</p></div></div>
                  <div class="onboarding-steps">
                    <article class="onboarding-step ready"><strong><i class="bi bi-check-circle"></i> App installed</strong><span>The local runtime and browser support are available.</span></article>
                    <article class="onboarding-step ready"><strong><i class="bi bi-check-circle"></i> API key saved</strong><span>Your OpenAI key is stored in the operating-system keyring.</span></article>
                    <article class="onboarding-step ready"><strong><i class="bi bi-check-circle"></i> Discord signed in</strong><span>The private Kabuki-Cord browser profile has an active session.</span></article>
                    <article class="onboarding-step pending"><strong><i class="bi bi-hourglass-split"></i> Sync channels</strong><span>Discover servers and explicitly enable only the channels you intend to observe.</span></article>
                    <article class="onboarding-step pending"><strong><i class="bi bi-person-vcard"></i> Create a character</strong><span>Observation works without one; persona-driven drafts need a useful custom card.</span></article>
                    <article class="onboarding-step pending"><strong><i class="bi bi-shield-check"></i> Start in Observe only</strong><span>Validate selectors, pacing, and memory before enabling sends.</span></article>
                  </div>
                  <div class="help-callout warning"><i class="bi bi-exclamation-triangle"></i><span>Personal-account browser automation is less stable and carries more platform risk than a supported integration. Keep manual review enabled while tuning.</span></div>
                </section>
              </div>
            </div>
            <div class="onboarding-actions">
              <button class="secondary-button"><i class="bi bi-sliders"></i> API &amp; Runtime</button>
              <button class="secondary-button"><i class="bi bi-diagram-3"></i> Sync Discord</button>
              <button class="primary-button"><i class="bi bi-check2"></i> Done</button>
            </div>
          </div>
        </div>
      </div>
    """


def update_body() -> str:
    return f"""
      <div class="readme-update-shot">
        {dashboard_body()}
        <div class="update-overlay">
          <div class="update-dialog" tabindex="-1" aria-busy="true" data-state="checking">
            <div class="update-dialog-heading">
              <div><div class="eyebrow">Mask workshop</div><h2>Inspecting Kabuki-Cord</h2></div>
              <span class="update-result-icon" aria-hidden="true"><i class="bi bi-cloud-arrow-down"></i></span>
            </div>
            <div class="update-workshop-stage" aria-hidden="true">
              <span class="update-stage-curtain update-stage-curtain-left"></span>
              <span class="update-stage-curtain update-stage-curtain-right"></span>
              <span class="update-workshop-sprite"></span>
              <span class="update-stage-footlights"></span>
            </div>
            <div class="update-progress-block">
              <div class="update-phase-bar" role="progressbar" aria-valuenow="58">
                <span class="complete"></span><span class="complete"></span><span class="active"></span><span></span>
              </div>
              <ol class="update-phase-list"><li class="complete">Validate</li><li class="complete">Fetch</li><li class="active">Compare</li><li>Apply</li></ol>
            </div>
            <div class="update-dialog-status" role="status">Fetching origin/main and comparing it with this Git checkout.</div>
            <div class="update-dialog-actions"><button class="secondary-button" disabled><i class="bi bi-hourglass-split"></i> Working…</button></div>
          </div>
        </div>
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


def monitor_body() -> str:
    spy_frame = image_data_uri(ASSET_DIR / "monitor_spy_v2_frames" / "frame_003.webp")
    return f"""
    <main class="monitor-shell">
      <header class="monitor-header">
        <div>
          <span class="eyebrow">Kabuki-Cord</span>
          <h1>Scanner Monitor</h1>
        </div>
        <div class="monitor-actions">
          <button class="sound-toggle" type="button" aria-pressed="true">Sound on</button>
          <div class="status-pill running">scanning</div>
        </div>
      </header>

      <section class="story-panel">
        <div class="spy-scene" aria-hidden="true">
          <img class="spy-frame active" src="{spy_frame}" alt="" />
          <img class="spy-frame" src="{spy_frame}" alt="" />
          <div class="stage-transition"></div>
          <div class="stage-glints"></div>
        </div>
        <div class="scan-board">
          <div class="scan-card current">
            <span>Current</span>
            <strong>Signal Lab</strong>
            <small>#general - 100000000000000001</small>
            <div class="countdown-line"><span>Est. done</span><strong>00:08</strong></div>
          </div>
          <div class="scan-card">
            <span>Next</span>
            <strong>Arcade Ops</strong>
            <small>#odd-links - 100000000000000002</small>
            <div class="countdown-line"><span>Next channel</span><strong>00:45</strong></div>
          </div>
          <div class="scan-card pace">
            <span>Pace</span>
            <strong>1 channel / cycle</strong>
            <small>12s settle, 45s rest, 12-35s channel pacing</small>
            <div class="countdown-line"><span>Rest after</span><strong>00:45</strong></div>
          </div>
          <div class="scan-card completed">
            <span>Last Completed</span>
            <strong>Field Notes</strong>
            <small>Reviewed 12 visible messages, 3 new remembered.</small>
          </div>
        </div>
      </section>

      <section class="queue-panel">
        <div class="section-title">Upcoming Channels</div>
        <div class="upcoming-list">
          <article class="queue-item"><strong>Arcade Ops</strong><span>#odd-links</span><small>due in 45s</small></article>
          <article class="queue-item"><strong>Sky Lantern</strong><span>#night-shift</span><small>due in 2m</small></article>
          <article class="queue-item"><strong>Signal Lab</strong><span>#field-notes</span><small>due in 3m</small></article>
          <article class="queue-item"><strong>Field Notes</strong><span>#archive-desk</span><small>due in 5m</small></article>
        </div>
      </section>

      <section class="action-history-panel">
        <div class="action-column">
          <div class="section-title">Responses</div>
          <div class="action-list">
            <details class="action-item response" open>
              <summary>
                <span class="action-badge">sent</span>
                <span class="action-summary"><strong>Rin Vale</strong><small>Signal Lab / #general</small></span>
              </summary>
              <div class="action-body">
                <p>yeah i would slow down on that one until someone posts the archive link</p>
                <div class="action-buttons"><button>Open</button><button>Copy link</button></div>
              </div>
            </details>
            <details class="action-item response" open>
              <summary>
                <span class="action-badge">queued</span>
                <span class="action-summary"><strong>Maple Desk</strong><small>Field Notes / #archive-desk</small></span>
              </summary>
              <div class="action-body">
                <p>interesting but not proven yet, the source chain is doing a lot of work</p>
                <div class="action-buttons"><button>Open</button><button>Copy link</button></div>
              </div>
            </details>
          </div>
        </div>
        <div class="action-column">
          <div class="section-title">Reactions</div>
          <div class="action-list">
            <details class="action-item reaction" open>
              <summary>
                <span class="action-badge">😂</span>
                <span class="action-summary"><strong>Byte Lantern</strong><small>Arcade Ops / #odd-links</small></span>
              </summary>
              <div class="action-body">
                <p>obvious joke cue in the latest thread</p>
                <div class="action-buttons"><button>Open</button><button>Copy link</button></div>
              </div>
            </details>
            <details class="action-item reaction" open>
              <summary>
                <span class="action-badge">👀</span>
                <span class="action-summary"><strong>Maple Desk</strong><small>Signal Lab / #general</small></span>
              </summary>
              <div class="action-body">
                <p>weird claim, low-commitment reaction selected</p>
                <div class="action-buttons"><button>Open</button><button>Copy link</button></div>
              </div>
            </details>
          </div>
        </div>
      </section>
    </main>
    <div class="monitor-toasts">
      <article class="monitor-toast">
        <div class="toast-stars"><span></span><span></span></div>
        <span class="delivery-character delivery-character-toast" aria-hidden="true"></span>
        <div><strong>Arigato</strong><span>Reply delivered in Signal Lab / #general</span><small>Just now</small></div>
        <button>&times;</button>
      </article>
    </div>
    """


def wait_for_assets(page: Page) -> None:
    page.evaluate(
        """async () => {
          await document.fonts.ready;
          await Promise.all(
            Array.from(document.images, (image) => image.decode().catch(() => undefined)),
          );
        }"""
    )


def capture(name: str, body: str, *, mode: str = "runtime-mode-semi-auto") -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_DIR / name
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=1)
        page.set_content(document(body, mode=mode), wait_until="networkidle")
        wait_for_assets(page)
        page.screenshot(path=str(output), full_page=False)
        browser.close()
    print(f"wrote {output}")


def capture_monitor(name: str, body: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_DIR / name
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport=VIEWPORT, device_scale_factor=1)
        page.set_content(monitor_document(body), wait_until="networkidle")
        wait_for_assets(page)
        page.screenshot(path=str(output), full_page=False)
        browser.close()
    print(f"wrote {output}")


def main() -> None:
    capture("kabuki-cord-dashboard.png", dashboard_body())
    capture("kabuki-cord-help.png", help_body(), mode="runtime-mode-dry")
    capture("kabuki-cord-update-check.png", update_body(), mode="runtime-mode-dry")
    capture("kabuki-cord-approvals.png", approvals_body(), mode="runtime-mode-live-fire")
    capture_monitor("kabuki-cord-monitor.png", monitor_body())


if __name__ == "__main__":
    main()
