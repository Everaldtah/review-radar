import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import hashlib


class ReviewDatabase:
    def __init__(self):
        data_dir = Path(os.getenv("DATA_DIR", "./data"))
        data_dir.mkdir(parents=True, exist_ok=True)
        self.businesses_file = data_dir / "businesses.json"
        self.reviews_dir = data_dir / "reviews"
        self.alerts_dir = data_dir / "alerts"
        self.reviews_dir.mkdir(exist_ok=True)
        self.alerts_dir.mkdir(exist_ok=True)
        if not self.businesses_file.exists():
            self.businesses_file.write_text("{}")

    def _load_businesses(self):
        return json.loads(self.businesses_file.read_text())

    def _save_businesses(self, data):
        self.businesses_file.write_text(json.dumps(data, indent=2))

    def upsert_business(self, profile: dict):
        businesses = self._load_businesses()
        businesses[profile["business_id"]] = profile
        self._save_businesses(businesses)

    def get_business(self, business_id: str) -> Optional[dict]:
        return self._load_businesses().get(business_id)

    def update_sync_time(self, business_id: str):
        businesses = self._load_businesses()
        if business_id in businesses:
            businesses[business_id]["last_synced"] = datetime.utcnow().isoformat()
            self._save_businesses(businesses)

    def _reviews_file(self, business_id: str) -> Path:
        return self.reviews_dir / f"{business_id}.json"

    def _load_reviews(self, business_id: str) -> list:
        f = self._reviews_file(business_id)
        return json.loads(f.read_text()) if f.exists() else []

    def _review_id(self, review: dict) -> str:
        key = f"{review.get('platform')}_{review.get('author')}_{review.get('text', '')[:50]}"
        return hashlib.md5(key.encode()).hexdigest()

    def save_review(self, review: dict) -> bool:
        reviews = self._load_reviews(review["business_id"])
        rev_id = self._review_id(review)
        review["id"] = rev_id
        review.setdefault("fetched_at", datetime.utcnow().isoformat())

        existing_ids = {r["id"] for r in reviews}
        if rev_id in existing_ids:
            return False

        reviews.insert(0, review)
        self._reviews_file(review["business_id"]).write_text(json.dumps(reviews, indent=2))
        return True

    def get_reviews(self, business_id: str, platform: str = None, min_stars: int = None, max_stars: int = None, days: int = 30) -> list:
        reviews = self._load_reviews(business_id)
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        result = []
        for r in reviews:
            if r.get("fetched_at", "") < cutoff:
                continue
            if platform and r.get("platform") != platform:
                continue
            if min_stars is not None and r.get("stars", 0) < min_stars:
                continue
            if max_stars is not None and r.get("stars", 5) > max_stars:
                continue
            result.append(r)
        return result

    def get_stats(self, business_id: str, days: int = 30) -> dict:
        reviews = self.get_reviews(business_id, days=days)
        if not reviews:
            return {"total": 0, "avg_stars": 0, "negative": 0, "positive": 0}

        total = len(reviews)
        stars = [r.get("stars", 0) for r in reviews]
        avg = sum(stars) / total if total else 0
        negative = sum(1 for s in stars if s <= 3)
        positive = sum(1 for s in stars if s >= 4)

        platform_counts = {}
        for r in reviews:
            p = r.get("platform", "unknown")
            platform_counts[p] = platform_counts.get(p, 0) + 1

        return {
            "total": total,
            "avg_stars": round(avg, 2),
            "negative": negative,
            "positive": positive,
            "by_platform": platform_counts,
        }

    def save_alert(self, alert: dict):
        alerts_file = self.alerts_dir / f"{alert['business_id']}.json"
        alerts = json.loads(alerts_file.read_text()) if alerts_file.exists() else []
        alerts.insert(0, alert)
        alerts_file.write_text(json.dumps(alerts[:500], indent=2))

    def get_alerts(self, business_id: str, limit: int = 50) -> list:
        alerts_file = self.alerts_dir / f"{business_id}.json"
        if not alerts_file.exists():
            return []
        return json.loads(alerts_file.read_text())[:limit]
