"""
Apple App Store RSS feed integration for fetching app reviews.
No API key required — uses public RSS feeds.
"""

import httpx
import json
from datetime import datetime


def fetch_app_store_reviews(app_id: str, country: str = "us") -> list:
    url = f"https://itunes.apple.com/{country}/rss/customerreviews/id={app_id}/sortBy=mostRecent/json"
    try:
        resp = httpx.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        entries = data.get("feed", {}).get("entry", [])
        if not entries:
            return []

        # First entry is the app metadata, skip it
        reviews = []
        for entry in entries[1:]:
            try:
                stars = int(entry.get("im:rating", {}).get("label", "0"))
                reviews.append({
                    "platform": "app_store",
                    "author": entry.get("author", {}).get("name", {}).get("label", "Anonymous"),
                    "stars": stars,
                    "text": entry.get("content", {}).get("label", ""),
                    "title": entry.get("title", {}).get("label", ""),
                    "date": entry.get("updated", {}).get("label", datetime.utcnow().isoformat()),
                    "source_url": entry.get("link", {}).get("attributes", {}).get("href", ""),
                })
            except Exception:
                continue

        return reviews

    except Exception as e:
        print(f"[app-store] Error fetching reviews for app {app_id}: {e}")
        return []
