(function (global) {
  "use strict";

  const runtimeModeClassNames = Object.freeze([
    "runtime-mode-dry",
    "runtime-mode-full-auto",
    "runtime-mode-semi-auto",
    "runtime-mode-live-fire",
  ]);

  const runtimeModeLabels = Object.freeze({
    dry: "observe only",
    full_auto: "autonomous live",
    semi_auto: "limited autonomous",
    live_fire: "review every draft",
  });

  const runtimeModeTransitionLabels = Object.freeze({
    dry: Object.freeze(["Observe only", "Scanning only. Sends are blocked."]),
    full_auto: Object.freeze(["Autonomous live", "Eligible replies may send in opted-in channels."]),
    semi_auto: Object.freeze(["Limited autonomous", "Regular replies may send; new starts need review."]),
    live_fire: Object.freeze(["Review every draft", "Every live reply stays approval-gated."]),
  });

  const reactionTypes = Object.freeze([
    "reaction_added",
    "reaction_already_present",
    "reaction_failed",
    "reaction_scan",
    "reaction_skipped",
    "reaction_suggested",
  ]);

  const reactionTypeSet = new Set(reactionTypes);

  const eventTypeLabels = Object.freeze({
    channel_checked: "Channel checked",
    channel_unavailable: "Channel unavailable",
    discord_account_challenge: "Discord account challenge",
    approval_queued: "Approval queued",
    manual_approval_created: "Draft queued",
    approval_regenerated: "Draft regenerated",
    approval_updated: "Draft edited",
    approval_discarded: "Draft discarded",
    approvals_cleared: "Approvals cleared",
    approval_send_started: "Delivery started",
    duplicate_reply_blocked: "Duplicate blocked",
    reply_guard_blocked: "Auto reply blocked",
    output_guard_blocked: "Output guard blocked",
    approval_sent: "Approved response sent",
    approval_send_failed: "Send failed",
    message_sent: "Auto response sent",
    dry_run: "Dry-run draft",
    auto_respond_dry_run: "Auto dry-run draft",
    discord_repair: "Discord repair",
    channel_backfilled: "Channel backfilled",
    channel_refreshed: "Channel refreshed",
    reaction_suggested: "Reaction suggested",
    reaction_added: "Reaction made",
    reaction_already_present: "Reaction already present",
    reaction_failed: "Reaction failed",
    reaction_scan: "Reaction scan",
    reaction_skipped: "Reaction skipped",
    unresponded_reply_dismissed: "Reply notice dismissed",
    safety_review_scan: "Dojo sweep scan",
    safety_review_flagged: "Dojo sweep flagged",
    safety_review_dismissed: "Dojo sweep dismissed",
  });

  const failedEventTypes = new Set([
    "approval_send_failed",
    "channel_unavailable",
    "reaction_failed",
    "discord_account_challenge",
    "output_guard_blocked",
    "safety_review_flagged",
  ]);

  const sentEventTypes = new Set(["message_sent", "approval_sent"]);
  const reactionEventClassTypes = new Set(["reaction_added"]);

  const attentionEventTypes = new Set([
    "approval_queued",
    "manual_approval_created",
    "approval_send_started",
    "duplicate_reply_blocked",
    "reply_guard_blocked",
    "reaction_already_present",
    "reaction_scan",
    "reaction_skipped",
    "reaction_suggested",
    "safety_review_scan",
    "safety_review_dismissed",
  ]);

  const notifiableEventTypes = new Set([
    "approval_queued",
    "manual_approval_created",
    "approval_send_started",
    "duplicate_reply_blocked",
    "reply_guard_blocked",
    "output_guard_blocked",
    "approval_sent",
    "approval_send_failed",
    "message_sent",
    "channel_unavailable",
    "reaction_added",
    "reaction_failed",
    "safety_review_flagged",
  ]);

  function compactServerRailLabel(label, index) {
    const cleaned = String(label || "").replace(/\s+/g, " ").trim();
    if (!cleaned) return `Server ${index + 1}`.slice(0, 10);
    return Array.from(cleaned).slice(0, 10).join("");
  }

  function isDiscordBlockedError(value) {
    return /discord/i.test(String(value || ""))
      && /(password reset|security action|verification|verify|2fa|authentication code|login screen|not signed in|human|not a robot|account)/i.test(String(value || ""));
  }

  function filterRememberedUsers(users, searchQuery, noteTextByUser) {
    const query = String(searchQuery || "").trim().toLowerCase();
    if (!query) return users;
    return users.filter((user) => rememberedUserMatchesQuery(user, query, noteTextByUser));
  }

  function rememberedUserMatchesQuery(user, query, noteTextByUser) {
    const haystack = [
      user.user_key,
      user.display_name,
      user.stable_user_id,
      user.summary,
      ...(user.recent_topics || []),
      noteTextByUser?.get(user.user_key) || "",
    ]
      .join(" ")
      .toLowerCase();
    return haystack.includes(query);
  }

  function sortRememberedUsers(users, sortMode) {
    const rows = [...users];
    if (sortMode === "name") {
      return rows.sort((left, right) => userDisplayName(left).localeCompare(userDisplayName(right)));
    }
    if (sortMode === "messages") {
      return rows.sort((left, right) =>
        Number(right.message_count || 0) - Number(left.message_count || 0)
        || userDisplayName(left).localeCompare(userDisplayName(right))
      );
    }
    return rows.sort((left, right) =>
      userSeenMillis(right.last_seen_at) - userSeenMillis(left.last_seen_at)
      || Number(right.message_count || 0) - Number(left.message_count || 0)
      || userDisplayName(left).localeCompare(userDisplayName(right))
    );
  }

  function userDisplayName(user) {
    return String(user.display_name || user.user_key || "").toLowerCase();
  }

  function userSeenMillis(value) {
    const parsed = Date.parse(value || "");
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function userSortLabel(mode) {
    return {
      recent: "recently seen",
      messages: "most messages",
      name: "name",
    }[mode] || "recently seen";
  }

  function formatUserLastSeen(value) {
    const parsed = Date.parse(value || "");
    if (!Number.isFinite(parsed)) return "never seen";
    return new Date(parsed).toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  }

  function strBool(value, fallback) {
    if (value === undefined || value === null || value === "") return fallback;
    return String(value).toLowerCase() === "true";
  }

  function runtimeModeLabel(mode) {
    return runtimeModeLabels[mode] || "dry mode";
  }

  function runtimeModeCssClass(mode) {
    return `runtime-mode-${String(mode || "dry").replaceAll("_", "-")}`;
  }

  function transitionModeCssClass(mode) {
    return `mode-${String(mode || "dry").replaceAll("_", "-")}`;
  }

  function runtimeModeTransitionCopy(mode) {
    return runtimeModeTransitionLabels[mode] || runtimeModeTransitionLabels.dry;
  }

  function reactionEventTypes() {
    return [...reactionTypes];
  }

  function eventMatchesFilter(event, filterMode) {
    if (filterMode === "reactions") return reactionTypeSet.has(event.event_type);
    if (filterMode === "reaction_added") return event.event_type === "reaction_added";
    return true;
  }

  function emptyEventFilterMessage(filterMode) {
    if (filterMode === "reactions") return "No reaction events recorded yet.";
    if (filterMode === "reaction_added") return "No reactions made yet.";
    return "No runtime events recorded yet.";
  }

  function eventKey(event) {
    return [
      event.created_at || "",
      event.event_type || "",
      event.server_id || "",
      event.channel_id || "",
      event.summary || "",
      event.draft || "",
    ].join("|");
  }

  function eventTypeLabel(event) {
    return eventTypeLabels[event.event_type] || event.event_type || "Event";
  }

  function eventClass(event) {
    if (failedEventTypes.has(event.event_type)) return "failed";
    if (sentEventTypes.has(event.event_type)) return "sent";
    if (reactionEventClassTypes.has(event.event_type)) return "reaction";
    if (attentionEventTypes.has(event.event_type)) return "attention";
    return "";
  }

  function isNotifiableEvent(event) {
    return notifiableEventTypes.has(event.event_type);
  }

  function truncateText(value, maxLength) {
    const text = String(value || "").trim();
    if (text.length <= maxLength) return text;
    return `${text.slice(0, maxLength - 3)}...`;
  }

  function userInstructionMatchesScope(item, currentServer, currentChannel) {
    if (item.server_id && item.server_id !== currentServer?.server_id) return false;
    if (item.channel_id && item.channel_id !== currentChannel?.channel_id) return false;
    return true;
  }

  function compareText(left, right) {
    return String(left || "").localeCompare(String(right || ""), undefined, {
      numeric: true,
      sensitivity: "base",
    });
  }

  function formatTime(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  }

  function formatRuntimeTime(value) {
    if (!value) return "never";
    const date = typeof value === "number" ? new Date(value * 1000) : new Date(value);
    if (Number.isNaN(date.getTime())) return "unknown";
    return date.toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  }

  function channelTypeLabel(type) {
    if (type === "thread") return "discussion thread";
    if (type === "forum") return "forum channel";
    if (type === "announcement") return "announcement channel";
    if (type === "voice") return "voice channel";
    if (type === "stage") return "stage channel";
    if (type === "text") return "text channel";
    return "";
  }

  function formatChannelName(name, type) {
    if (!name) return "";
    if ((type === "text" || type === "forum" || type === "announcement" || type === "thread" || !type) && !String(name).startsWith("#")) {
      return `# ${name}`;
    }
    return name;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function escapeAttr(value) {
    return escapeHtml(value).replaceAll("'", "&#39;");
  }

  function cssEscape(value) {
    if (global.CSS?.escape) return global.CSS.escape(value || "");
    return String(value || "").replaceAll('"', '\\"');
  }

  global.KabukiUiHelpers = Object.freeze({
    runtimeModeClassNames,
    compactServerRailLabel,
    isDiscordBlockedError,
    filterRememberedUsers,
    sortRememberedUsers,
    userSortLabel,
    formatUserLastSeen,
    strBool,
    runtimeModeLabel,
    runtimeModeCssClass,
    transitionModeCssClass,
    runtimeModeTransitionCopy,
    reactionEventTypes,
    eventMatchesFilter,
    emptyEventFilterMessage,
    eventKey,
    eventTypeLabel,
    eventClass,
    isNotifiableEvent,
    truncateText,
    userInstructionMatchesScope,
    compareText,
    formatTime,
    formatRuntimeTime,
    channelTypeLabel,
    formatChannelName,
    escapeHtml,
    escapeAttr,
    cssEscape,
  });
})(window);
