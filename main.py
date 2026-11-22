"""Minimal instagrapi starter: login, session persistence and a sample API call."""

import os

from dotenv import load_dotenv

from funcs.client import get_client

load_dotenv()

USERNAME = os.getenv("IG_USERNAME")
PASSWORD = os.getenv("IG_PASSWORD")


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
