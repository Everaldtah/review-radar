"""
Google Places API integration for fetching reviews.
Requires GOOGLE_PLACES_API_KEY environment variable.
"""

import os
import httpx
from datetime import datetime


def fetch_google_reviews(place_id: str) -> list:
    api_key = os.getenv("GOOGLE_PLACES_API_KEY")
    if not api_key:
        print("[google-places] GOOGLE_PLACES_API_KEY not set — skipping")
        return _demo_reviews(place_id)

    try:
        resp = httpx.get(
            "https://maps.googleapis.com/maps/api/place/details/json",
            params={
                "place_id": place_id,
                "fields": "name,rating,reviews",
                "key": api_key,
                "reviews_sort": "newest",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        result = data.get("result", {})
        raw_reviews = result.get("reviews", [])

        reviews = []
        for r in raw_reviews:
            reviews.append({
                "platform": "google",
                "author": r.get("author_name", "Anonymous"),
                "stars": r.get("rating", 0),
                "text": r.get("text", ""),
                "date": datetime.fromtimestamp(r.get("time", 0)).isoformat(),
                "source_url": r.get("author_url", ""),
            })
        return reviews

    except Exception as e:
        print(f"[google-places] Error fetching reviews for {place_id}: {e}")
        return []


def _demo_reviews(place_id: str) -> list:
    """Returns sample data when no API key is configured — for demo/testing."""
    return [
        {
            "platform": "google",
            "author": "John D.",
            "stars": 5,
            "text": "Excellent service! Will definitely come back.",
            "date": datetime.utcnow().isoformat(),
            "source_url": "",
        },
        {
            "platform": "google",
            "author": "Sarah M.",
            "stars": 2,
            "text": "Waited 45 minutes and nobody acknowledged us. Very disappointed.",
            "date": datetime.utcnow().isoformat(),
            "source_url": "",
        },
        {
            "platform": "google",
            "author": "Mike T.",
            "stars": 4,
            "text": "Good food, friendly staff. Parking can be tricky.",
            "date": datetime.utcnow().isoformat(),
            "source_url": "",
        },
    ]
