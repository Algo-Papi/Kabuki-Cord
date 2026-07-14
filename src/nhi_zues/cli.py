from __future__ import annotations

import asyncio
import argparse
import logging
from typing import TYPE_CHECKING

from .approvals import ApprovalQueue
from .budget import BudgetManager
from .config import load_config
from .diagnostics import configure_diagnostic_logging
from .character_memory import CharacterMemoryStore
from .user_instructions import UserInstructionStore

if TYPE_CHECKING:
    from .browser import DiscordWebSession


def main() -> None:
    parser = argparse.ArgumentParser(prog="kabuki-cord")
    parser.add_argument("--once", action="store_true", help="Process configured channels once and exit.")
    parser.add_argument("--login", action="store_true", help="Open Discord and save a persistent browser login session.")
    parser.add_argument("--open-channel", nargs=2, metavar=("SERVER_ID", "CHANNEL_ID"), help="Open one Discord channel in the persistent browser profile and keep it visible.")
    parser.add_argument("--message-id", help="When opening a channel, jump to this Discord message id if available.")
    parser.add_argument("--usage", action="store_true", help="Print recorded API usage and exit.")
    parser.add_argument("--approvals", action="store_true", help="Print queued proactive drafts and exit.")
    parser.add_argument("--remember-story", help="Add a story/claim continuity note to the active character.")
    parser.add_argument("--remember-behavior", help="Add a behavior adjustment note to the active character.")
    parser.add_argument("--remember-user", nargs=2, metavar=("USER_KEY", "NOTE"), help="Add a behavior note for one Discord user key.")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = load_config()
    configure_diagnostic_logging(config.state_dir)
    if args.login:
        from .browser import DiscordWebSession
        from .secrets import get_discord_credentials

        credentials = get_discord_credentials()
        async def login() -> bool:
            async with DiscordWebSession(
                config.profile_dir,
                browser_channel=config.browser_channel,
                headless=False,
            ) as session:
                await session.open_home()
                if await session._is_logged_in():
                    await session.page.wait_for_timeout(3000)
                    return True
                await _fill_login_form_if_available(session, credentials.email, credentials.password)
                return await _wait_for_manual_discord_login(session)

        logged_in = asyncio.run(login())
        print("Discord login session saved." if logged_in else "Discord login was not completed.")
        return

    if args.open_channel:
        from .browser import DiscordWebSession
        from .secrets import get_discord_credentials

        server_id, channel_id = args.open_channel
        credentials = get_discord_credentials()

        async def open_channel() -> bool:
            async with DiscordWebSession(
                config.profile_dir,
                browser_channel=config.browser_channel,
                headless=False,
            ) as session:
                logged_in = await session.login_if_needed(
                    email=credentials.email,
                    password=credentials.password,
                    timeout_seconds=240,
                )
                if not logged_in:
                    return False
                await session.navigate_channel(server_id, channel_id, message_id=args.message_id or "")
                print(f"Opened Discord channel: https://discord.com/channels/{server_id}/{channel_id}")
                try:
                    await session.page.wait_for_event("close", timeout=0)
                except Exception:
                    pass
                return True

        opened = asyncio.run(open_channel())
        print("Discord channel window closed." if opened else "Discord channel was not opened.")
        return

    if args.usage:
        budget = BudgetManager(
            config.state_dir / "usage.json",
            model=config.openai_model,
            max_daily_usd=config.max_daily_usd,
            max_session_usd=config.max_session_usd,
            max_calls_per_run=config.max_llm_calls_per_run,
        )
        for key, value in budget.summary().items():
            if isinstance(value, float):
                print(f"{key}: {value:.6f}")
            else:
                print(f"{key}: {value}")
        return

    if args.approvals:
        approvals = ApprovalQueue(config.state_dir / "approvals.json").list()
        if not approvals:
            print("No queued approvals.")
            return
        for item in approvals:
            print(f"{item.approval_id} | server={item.server_id} channel={item.channel_id}")
            print(f"character={item.character_name} type={item.engagement_type}")
            print(f"reason={item.reason}")
            print(f"draft={item.draft}")
            print()
        return

    if args.remember_story or args.remember_behavior:
        store = CharacterMemoryStore(config.state_dir / "character_memory")
        if args.remember_story:
            memory = store.add_story_claim(config.character_card, args.remember_story)
        else:
            memory = store.add_behavior_note(config.character_card, args.remember_behavior or "")
        print(f"character_memory: {config.character_card}")
        print(f"story_claims: {len(memory.story_claims)}")
        print(f"behavior_notes: {len(memory.behavior_notes)}")
        return

    if args.remember_user:
        user_key, note = args.remember_user
        item = UserInstructionStore(config.state_dir / "user_instructions.json").add(user_key, note)
        print(f"user_instruction: {item.user_key}")
        print(f"note: {item.note}")
        return

    from .runner import NhiZuesRunner

    runner = NhiZuesRunner(config)
    if args.once:
        asyncio.run(runner.run_once())
    else:
        asyncio.run(runner.run_forever())


async def _wait_for_manual_discord_login(session: "DiscordWebSession") -> bool:
    while not session.page.is_closed():
        if await session._is_logged_in():
            await session.page.wait_for_timeout(3000)
            return True
        try:
            await session.page.wait_for_event("close", timeout=1000)
        except Exception:
            pass
    return False


async def _fill_login_form_if_available(session: "DiscordWebSession", email: str | None, password: str | None) -> None:
    if not email or not password:
        return
    login_form = session.page.locator('input[name="email"], input[type="email"]').first
    try:
        await login_form.wait_for(state="visible", timeout=15_000)
        password_input = session.page.locator('input[name="password"], input[type="password"]').first
        await password_input.wait_for(state="visible", timeout=15_000)
        await login_form.fill(email)
        await password_input.fill(password)
        await password_input.press("Enter")
    except Exception:
        return


if __name__ == "__main__":
    main()
