import os
import sys
import json
import asyncio
from telethon import TelegramClient

async def main():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    with open(config_path, "r") as f:
        config = json.load(f)

    api_id = int(config.get("TELEGRAM_API_ID", "0"))
    api_hash = config.get("TELEGRAM_API_HASH", "")

    if not api_id or not api_hash:
        print("Missing TELEGRAM_API_ID or TELEGRAM_API_HASH in config.json")
        return

    session_path = os.path.join(os.path.dirname(__file__), "scraper_user")

    print("=" * 50)
    print("Scraper User Session Setup")
    print("=" * 50)
    print(f"API ID: {api_id}")
    print(f"Session will be saved to: {session_path}.session")
    print()

    client = TelegramClient(session_path, api_id, api_hash)

    await client.start()

    me = await client.get_me()
    print(f"\nAuthenticated as: {me.first_name} {me.last_name or ''} (@{me.username or 'N/A'})")
    print(f"User ID: {me.id}")
    print(f"\nSession saved successfully! The scraper will now use this account.")
    print("Make sure this account is a member of the groups/channels you want to scrape.")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
