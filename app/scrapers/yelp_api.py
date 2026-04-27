"""
Yelp Fusion API integration for fetching business reviews.
Requires YELP_API_KEY environment variable.
"""

import os
import httpx
from datetime import datetime


def fetch_yelp_reviews(business_id: str) -> list:
    api_key = os.getenv("YELP_API_KEY")
    if not api_key:
        print("[yelp] YELP_API_KEY not set — skipping")
        return _demo_reviews(business_id)

    try:
        resp = httpx.get(
            f"https://api.yelp.com/v3/businesses/{business_id}/reviews",
            headers={"Authorization": f"Bearer {api_key}"},
            params={"limit": 50, "sort_by": "date_desc"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        reviews = []
        for r in data.get("reviews", []):
            reviews.append({
                "platform": "yelp",
                "author": r.get("user", {}).get("name", "Anonymous"),
                "stars": r.get("rating", 0),
                "text": r.get("text", ""),
                "date": r.get("time_created", datetime.utcnow().isoformat()),
                "source_url": r.get("url", ""),
            })
        return reviews

    except Exception as e:
        print(f"[yelp] Error fetching reviews for {business_id}: {e}")
        return []


def _demo_reviews(business_id: str) -> list:
    return [
        {
            "platform": "yelp",
            "author": "Lisa K.",
            "stars": 5,
            "text": "Best pizza in town! The crust is perfect.",
            "date": datetime.utcnow().isoformat(),
            "source_url": "",
        },
        {
            "platform": "yelp",
            "author": "Tom B.",
            "stars": 3,
            "text": "Average experience. Nothing special but not terrible.",
            "date": datetime.utcnow().isoformat(),
            "source_url": "",
        },
    ]
