let apiToken = null;
let refreshTimer = null;
let spyFrameTimer = null;
let spyFrameIndex = 0;
let spyFrames = ["/assets/monitor_spy_frames/frame_000.png"];
let spyFrameMs = 180;

const $ = (id) => document.getElementById(id);

async function loadSession() {
  const response = await fetch("/api/session");
  if (!response.ok) throw new Error("Could not open Kabuki session.");
  const payload = await response.json();
  apiToken = payload.token;
}

async function api(path) {
  if (!apiToken) await loadSession();
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      "X-Kabuki-Token": apiToken,
    },
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

async function refresh() {
  try {
    const state = await api("/api/state");
    render(state);
  } catch (error) {
    $("monitorStatus").className = "status-pill error";
    $("monitorStatus").textContent = "Disconnected";
    $("currentTarget").textContent = "Kabuki-Cord unavailable";
    $("currentDetail").textContent = error.message || "Restart the app and reopen this monitor.";
  }
}

async function loadSpyAnimation() {
  try {
    const response = await fetch("/assets/monitor_spy_frames/manifest.json");
    if (response.ok) {
      const manifest = await response.json();
      const count = Number(manifest.frame_count || 1);
      spyFrameMs = Number(manifest.frame_ms || 180);
      spyFrames = Array.from({ length: count }, (_, index) =>
        `/assets/monitor_spy_frames/frame_${String(index).padStart(3, "0")}.png`
      );
    }
  } catch {
    spyFrames = ["/assets/monitor_spy_frames/frame_000.png"];
  }
  spyFrames.forEach((src) => {
    const image = new Image();
    image.src = src;
  });
  if (spyFrameTimer) clearInterval(spyFrameTimer);
  spyFrameTimer = setInterval(advanceSpyFrame, spyFrameMs);
}

function advanceSpyFrame() {
  const image = $("spySceneFrame");
  if (!image || !spyFrames.length) return;
  spyFrameIndex = (spyFrameIndex + 1) % spyFrames.length;
  image.src = spyFrames[spyFrameIndex];
}

function render(state) {
  const runtime = state.runtime || {};
  const scan = runtime.scan || {};
  const status = scan.status || runtime.phase || "idle";
  $("monitorStatus").className = `status-pill ${runtime.running ? "running" : "paused"}`;
  $("monitorStatus").textContent = runtime.running ? statusLabel(status) : "Paused";

  renderTarget("current", scan.current, {
    title: runtime.running ? currentTitle(status) : "Scanner paused",
    detail: runtime.running ? "No channel is active at this instant." : "Press Start in the main window.",
  });
  renderTarget("next", scan.next, {
    title: "None queued",
    detail: "The scanner is resting or waiting for a channel to become due.",
  });
  renderCompleted(scan.last_completed);
  renderUpcoming(scan.upcoming || []);
}

function renderTarget(kind, target, fallback) {
  const titleEl = kind === "current" ? $("currentTarget") : $("nextTarget");
  const detailEl = kind === "current" ? $("currentDetail") : $("nextDetail");
  if (!target) {
    titleEl.textContent = fallback.title;
    detailEl.textContent = fallback.detail;
    return;
  }
  titleEl.textContent = formatTargetTitle(target);
  detailEl.textContent = target.channel_id
    ? `#${target.channel_label || target.channel_id} - ${target.channel_id}`
    : fallback.detail;
}

function renderCompleted(target) {
  if (!target) {
    $("lastCompleted").textContent = "None yet";
    $("lastCompletedDetail").textContent = "No completed channel scan in this run.";
    return;
  }
  $("lastCompleted").textContent = formatTargetTitle(target);
  $("lastCompletedDetail").textContent =
    `${target.visible_messages || 0} visible, ${target.fresh_messages || 0} new to memory`;
}

function renderUpcoming(items) {
  const visible = items.slice(0, 5);
  $("upcomingList").innerHTML = visible.length
    ? visible.map((item, index) => `
      <div class="queue-item">
        <span>${index === 0 ? "Next" : `+${index}`}</span>
        <strong>${escapeHtml(item.channel_label || item.channel_id || "Unknown channel")}</strong>
        <span>${escapeHtml(item.server_label || item.server_id || "Unknown server")}</span>
      </div>
    `).join("")
    : `<div class="queue-empty">No upcoming due channels are queued right now.</div>`;
}

function formatTargetTitle(target) {
  const server = target.server_label || target.server_id || "Unknown server";
  const channel = target.channel_label || target.channel_id || "Unknown channel";
  return `${server} / ${channel}`;
}

function currentTitle(status) {
  return status === "waiting_for_discord_login" ? "Waiting for Discord sign-in" : "Between channels";
}

function statusLabel(status) {
  return {
    starting: "Starting",
    queued: "Queued",
    scanning: "Scanning",
    completed_channel: "Channel complete",
    resting: "Resting",
    waiting: "Waiting",
    waiting_for_discord_login: "Sign-in handoff",
    stopping: "Stopping",
    idle: "Idle",
  }[status] || status;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

loadSpyAnimation();
refresh();
refreshTimer = setInterval(refresh, 1800);
window.addEventListener("beforeunload", () => {
  if (refreshTimer) clearInterval(refreshTimer);
  if (spyFrameTimer) clearInterval(spyFrameTimer);
});
