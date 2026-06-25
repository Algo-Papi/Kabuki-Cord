from __future__ import annotations

import asyncio
import json
import threading
import time

from .browser import DiscordWebSession
from .config import AppConfig, load_config
from .events import EventLog
from .redaction import redact_secret_text
from .runner import NhiZuesRunner
from .scan_estimates import estimated_channel_scan_seconds, estimated_loop_seconds


class RuntimeController:
    def __init__(self, session_lock: threading.Lock) -> None:
        self._session_lock = session_lock
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._running = False
        self._last_started_at: float | None = None
        self._last_run_at: float | None = None
        self._last_error: str = ""
        self._phase = "idle"
        self._scan = self._empty_scan()
        self._resume_loop = {"cursor": 0, "completed_loops": 0}

    def start(self) -> None:
        with self._lock:
            self._stop.clear()
            if self._thread and self._thread.is_alive():
                self._running = True
                _record_runtime_event("runtime_start_requested", "Scanner was already running.")
                return
            self._running = True
            self._last_started_at = time.time()
            self._last_error = ""
            self._phase = "starting"
            self._scan = self._empty_scan("starting")
            self._thread = threading.Thread(target=self._loop, name="kabuki-runtime", daemon=True)
            self._thread.start()
        _record_runtime_event("runtime_started", "Scanner start requested.")

    def start_with_discord_handoff(self) -> None:
        with self._lock:
            self._stop.clear()
            if self._thread and self._thread.is_alive():
                self._running = True
                _record_runtime_event("runtime_signin_handoff_requested", "Scanner was already running.")
                return
            self._running = True
            self._last_started_at = time.time()
            self._last_error = ""
            self._phase = "waiting_for_discord_login"
            self._scan = self._empty_scan("waiting_for_discord_login")
            self._thread = threading.Thread(
                target=self._login_handoff_loop,
                name="kabuki-runtime-login-handoff",
                daemon=True,
            )
            self._thread.start()
        _record_runtime_event(
            "runtime_signin_handoff_started",
            "Visible Discord sign-in handoff started. Complete Discord login in that window.",
        )

    def pause(self, *, wait: bool = False, timeout: float = 10.0) -> None:
        thread: threading.Thread | None = None
        with self._lock:
            self._running = False
            self._stop.set()
            self._phase = "stopping"
            self._remember_resume_loop_from_scan_locked()
            self._scan = self._empty_scan("stopping")
            thread = self._thread
        _record_runtime_event("runtime_paused", "Scanner pause requested.")
        if wait and thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=timeout)

    def state(self) -> dict:
        with self._lock:
            thread_alive = bool(self._thread and self._thread.is_alive())
            running = self._running and thread_alive
            return {
                "running": running,
                "paused": not running,
                "last_started_at": self._last_started_at,
                "last_run_at": self._last_run_at,
                "last_error": self._last_error,
                "phase": self._phase if running else "idle",
                "scan": self._copy_scan() if running else self._empty_scan(),
            }

    def _set_phase(self, phase: str) -> None:
        with self._lock:
            self._phase = phase

    def _loop(self) -> None:
        acquired = False
        try:
            config = load_config()
            if not config.channels:
                self._last_error = "No channels are enabled for Observe."
                _record_runtime_event("runtime_error", self._last_error)
                return
            acquired = self._session_lock.acquire(blocking=False)
            if not acquired:
                self._last_error = "Discord browser profile is busy."
                _record_runtime_event("runtime_error", self._last_error)
                return
            self._set_phase("running")
            try:
                asyncio.run(
                    self._runner(config).run_until_stopped(
                        self._stop,
                        on_cycle=self._mark_cycle_complete,
                        on_targets_planned=self._mark_targets_planned,
                        on_target_start=self._mark_target_start,
                        on_target_complete=self._mark_target_complete,
                    )
                )
                if self._stop.is_set():
                    self._last_error = ""
                    _record_runtime_event("runtime_stopped", "Scanner stopped cleanly.")
            finally:
                if acquired:
                    self._session_lock.release()
        except Exception as exc:
            self._last_error = redact_secret_text(str(exc))
            _record_runtime_event("runtime_error", self._last_error)
        finally:
            with self._lock:
                self._running = False
                self._phase = "idle"
                self._scan = self._empty_scan()

    def _login_handoff_loop(self) -> None:
        acquired = False
        try:
            config = load_config()
            if not config.channels:
                self._last_error = "No channels are enabled for Observe."
                _record_runtime_event("runtime_error", self._last_error)
                return
            acquired = self._session_lock.acquire(blocking=False)
            if not acquired:
                self._last_error = "Discord browser profile is busy."
                _record_runtime_event("runtime_error", self._last_error)
                return
            asyncio.run(self._run_login_handoff(config))
            if self._stop.is_set():
                self._last_error = ""
                _record_runtime_event("runtime_stopped", "Scanner stopped cleanly.")
        except Exception as exc:
            self._last_error = redact_secret_text(str(exc))
            _record_runtime_event("runtime_error", self._last_error)
        finally:
            if acquired:
                self._session_lock.release()
            with self._lock:
                self._running = False
                self._phase = "idle"
                self._scan = self._empty_scan()

    async def _run_login_handoff(self, config: AppConfig) -> None:
        async with DiscordWebSession(
            config.profile_dir,
            browser_channel=config.browser_channel,
            headless=False,
        ) as session:
            self._set_phase("waiting_for_discord_login")
            await session.show_for_human()
            await session.open_home()
            _record_runtime_event(
                "runtime_waiting_for_discord_login",
                "Waiting for manual Discord sign-in in the visible browser window.",
            )
            while not self._stop.is_set():
                if await session.is_logged_in():
                    break
                await asyncio.sleep(1.0)
            if self._stop.is_set():
                return
            self._last_error = ""
            self._set_phase("running")
            _record_runtime_event(
                "runtime_discord_login_ready",
                "Discord sign-in completed; scanner is continuing in the same browser session.",
            )
            if config.headless:
                await session.hide_for_automation()
            await self._runner(config).run_until_stopped_in_session(
                session,
                self._stop,
                on_cycle=self._mark_cycle_complete,
                on_targets_planned=self._mark_targets_planned,
                on_target_start=self._mark_target_start,
                on_target_complete=self._mark_target_complete,
            )

    def _mark_cycle_complete(self, sleep_seconds: float | None = None, loop_state: dict | None = None) -> None:
        self._last_run_at = time.time()
        self._last_error = ""
        self._set_phase("running")
        now = time.time()
        sleep_value = max(0.0, float(sleep_seconds or 0.0))
        with self._lock:
            self._scan = {
                **self._scan,
                "status": "resting",
                "current": None,
                "next": self._scan.get("next"),
                "upcoming": self._scan.get("upcoming", []),
                "next_scan_at": now + sleep_value if sleep_value else None,
                "current_started_at": None,
                "current_estimated_done_at": None,
                "loop": self._loop_payload(loop_state, status="resting"),
                "updated_at": now,
            }
            self._remember_resume_loop_locked(loop_state)

    def _mark_targets_planned(self, targets, loop_state: dict | None = None) -> None:
        planned = [self._target_payload(target) for target in targets]
        now = time.time()
        with self._lock:
            self._scan = {
                **self._scan,
                "status": "queued" if planned else "waiting",
                "current": None,
                "next": planned[0] if planned else None,
                "upcoming": planned[:5],
                "planned_count": len(planned),
                "next_scan_at": now if planned else None,
                "current_started_at": None,
                "current_estimated_done_at": None,
                "loop": self._loop_payload(loop_state, status="queued"),
                "updated_at": now,
            }
            self._remember_resume_loop_locked(loop_state)

    def _mark_target_start(self, target, index: int, targets, loop_state: dict | None = None) -> None:
        remaining = [self._target_payload(item) for item in list(targets)[index + 1 : index + 6]]
        now = time.time()
        with self._lock:
            self._scan = {
                **self._scan,
                "status": "scanning",
                "current": self._target_payload(target),
                "next": remaining[0] if remaining else None,
                "upcoming": remaining,
                "planned_count": len(targets),
                "next_scan_at": None,
                "current_started_at": now,
                "current_estimated_done_at": now + self._estimated_target_seconds(),
                "loop": self._loop_payload(loop_state, status="scanning"),
                "updated_at": now,
            }
            self._remember_resume_loop_locked(loop_state)

    def _mark_target_complete(
        self,
        target,
        visible_count: int,
        fresh_count: int,
        loop_state: dict | None = None,
    ) -> None:
        completed = {
            **self._target_payload(target),
            "visible_messages": int(visible_count or 0),
            "fresh_messages": int(fresh_count or 0),
        }
        with self._lock:
            self._scan = {
                **self._scan,
                "status": "completed_channel",
                "current": None,
                "last_completed": completed,
                "current_started_at": None,
                "current_estimated_done_at": None,
                "loop": self._loop_payload(loop_state, status="completed_channel"),
                "updated_at": time.time(),
            }
            self._remember_resume_loop_locked(loop_state)

    def _copy_scan(self) -> dict:
        return json.loads(json.dumps(self._scan))

    @staticmethod
    def _empty_scan(status: str = "idle") -> dict:
        return {
            "status": status,
            "current": None,
            "next": None,
            "upcoming": [],
            "last_completed": None,
            "planned_count": 0,
            "next_scan_at": None,
            "current_started_at": None,
            "current_estimated_done_at": None,
            "loop": {
                "current_loop": 0,
                "completed_loops": 0,
                "total_channels": 0,
                "cursor": 0,
                "completed_in_loop": 0,
                "remaining_channels": 0,
                "estimated_loop_seconds": 0,
                "estimated_remaining_seconds": 0,
                "estimated_complete_at": None,
            },
            "updated_at": time.time(),
        }

    @staticmethod
    def _target_payload(target) -> dict:
        return {
            "server_id": str(getattr(target, "server_id", "") or ""),
            "server_label": str(getattr(target, "server_label", "") or getattr(target, "server_id", "") or ""),
            "channel_id": str(getattr(target, "channel_id", "") or ""),
            "channel_label": str(getattr(target, "label", "") or getattr(target, "channel_id", "") or ""),
            "safety_review_enabled": bool(getattr(target, "safety_review_enabled", False)),
        }

    @staticmethod
    def _estimated_target_seconds() -> float:
        try:
            return estimated_channel_scan_seconds(load_config())
        except Exception:
            return 45.0

    def _loop_payload(self, loop_state: dict | None, *, status: str) -> dict:
        try:
            config = load_config()
            total = int((loop_state or {}).get("total_channels") or len(config.channels) or 0)
            cursor = int((loop_state or {}).get("cursor") or 0)
            completed_in_loop = int((loop_state or {}).get("completed_in_loop") or 0)
            completed_in_loop = max(0, min(completed_in_loop, total))
            remaining = max(0, total - completed_in_loop)
            if status == "scanning" and remaining == 0 and total:
                remaining = 1
            loop_seconds = estimated_loop_seconds(config, total)
            remaining_seconds = estimated_loop_seconds(config, remaining)
            current_loop = int((loop_state or {}).get("current_loop") or 0)
            completed_loops = int((loop_state or {}).get("completed_loops") or 0)
            if not current_loop and total:
                current_loop = completed_loops + 1
            return {
                "current_loop": current_loop,
                "completed_loops": completed_loops,
                "total_channels": total,
                "cursor": max(0, min(cursor, total)) if total else 0,
                "position": int((loop_state or {}).get("position") or 0),
                "completed_in_loop": completed_in_loop,
                "remaining_channels": remaining,
                "estimated_loop_seconds": loop_seconds,
                "estimated_remaining_seconds": remaining_seconds,
                "estimated_complete_at": time.time() + remaining_seconds if remaining else time.time(),
            }
        except Exception:
            return self._empty_scan()["loop"]

    def _runner(self, config: AppConfig) -> NhiZuesRunner:
        with self._lock:
            resume = dict(self._resume_loop)
        return NhiZuesRunner(
            config,
            start_cursor=int(resume.get("cursor") or 0),
            completed_loop_count=int(resume.get("completed_loops") or 0),
        )

    def _remember_resume_loop_locked(self, loop_state: dict | None) -> None:
        if not loop_state:
            return
        total = int((loop_state or {}).get("total_channels") or 0)
        cursor = int((loop_state or {}).get("cursor") or 0)
        completed_loops = int((loop_state or {}).get("completed_loops") or 0)
        self._resume_loop = {
            "cursor": max(0, min(cursor, total)) if total else 0,
            "completed_loops": max(0, completed_loops),
        }

    def _remember_resume_loop_from_scan_locked(self) -> None:
        loop = self._scan.get("loop") if isinstance(self._scan, dict) else {}
        if not isinstance(loop, dict):
            return
        total = int(loop.get("total_channels") or 0)
        if total <= 0:
            return
        cursor = int(loop.get("cursor") or 0)
        completed_loops = int(loop.get("completed_loops") or 0)
        self._resume_loop = {
            "cursor": max(0, min(cursor, total)),
            "completed_loops": max(0, completed_loops),
        }


def _record_runtime_event(event_type: str, summary: str) -> None:
    try:
        config = load_config()
        EventLog(config.state_dir / "events.json").add(
            event_type=event_type,
            server_id="",
            channel_id="",
            summary=redact_secret_text(summary),
        )
    except Exception:
        return
