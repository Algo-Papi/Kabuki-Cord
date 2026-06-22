from __future__ import annotations

import asyncio
import argparse
import logging

from .approvals import ApprovalQueue
from .budget import BudgetManager
from .config import load_config
from .character_memory import CharacterMemoryStore
from .user_instructions import UserInstructionStore


def main() -> None:
    parser = argparse.ArgumentParser(prog="kabuki-cord")
    parser.add_argument("--once", action="store_true", help="Process configured channels once and exit.")
    parser.add_argument("--login", action="store_true", help="Open Discord and save a persistent browser login session.")
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
                return await session.login_if_needed(
                    email=credentials.email,
                    password=credentials.password,
                    timeout_seconds=240,
                )

        logged_in = asyncio.run(login())
        print("Discord login session saved." if logged_in else "Discord login was not completed.")
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


if __name__ == "__main__":
    main()
