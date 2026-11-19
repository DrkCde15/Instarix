"""Minimal instagrapi starter: login, session persistence and a sample API call."""

import os
from pathlib import Path

from dotenv import load_dotenv
from instagrapi import Client

load_dotenv()

USERNAME = os.getenv("IG_USERNAME")
PASSWORD = os.getenv("IG_PASSWORD")
SESSION_FILE = Path(os.getenv("IG_SESSION_FILE", "session.json"))


def get_client() -> Client:
    """Return a logged-in client, reusing a saved session when possible."""
    cl = Client()
    cl.delay_range = [1, 3]  # throttle requests a little to look less bot-like

    if SESSION_FILE.exists():
        cl.load_settings(SESSION_FILE)

    # login() validates a loaded session and falls back to a fresh
    # username/password login only if the session is no longer valid.
    cl.login(USERNAME, PASSWORD)
    cl.dump_settings(SESSION_FILE)
    return cl


def main() -> None:
    if not USERNAME or not PASSWORD:
        raise SystemExit(
            "Missing credentials. Copy .env.example to .env and set "
            "IG_USERNAME / IG_PASSWORD."
        )

    cl = get_client()
    print(f"Logged in as @{USERNAME} (user id: {cl.user_id})")

    medias = cl.user_medias(cl.user_id, amount=5)
    print(f"Fetched {len(medias)} recent post(s):")
    for media in medias:
        caption = (media.caption_text or "").strip().splitlines()
        title = caption[0][:60] if caption else "(no caption)"
        print(f" - {media.code} | type {media.media_type} | {title}")


if __name__ == "__main__":
    main()
