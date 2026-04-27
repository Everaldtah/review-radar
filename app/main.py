"""
review-radar — Multi-platform review monitor for local businesses.
Aggregates reviews from Google, Yelp, and App Stores.
Sends alerts on new reviews, generates weekly digest reports.
"""

import os
import json
import smtplib
import httpx
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from app.database import ReviewDatabase
from app.scrapers.google_places import fetch_google_reviews
from app.scrapers.yelp_api import fetch_yelp_reviews
from app.scrapers.app_store import fetch_app_store_reviews

app = FastAPI(title="Review Radar", description="Multi-platform review monitor", version="1.0.0")
security = HTTPBearer()
db = ReviewDatabase()

# ── Models ────────────────────────────────────────────────────────────────────

class BusinessProfile(BaseModel):
    business_id: str
    name: str
    alert_email: str
    google_place_id: Optional[str] = None
    yelp_business_id: Optional[str] = None
    app_store_app_id: Optional[str] = None
    alert_on_negative: bool = True
    alert_threshold_stars: int = 3
    weekly_digest: bool = True

class AlertConfig(BaseModel):
    business_id: str
    webhook_url: Optional[str] = None
    slack_webhook: Optional[str] = None

# ── Auth ─────────────────────────────────────────────────────────────────────

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials.credentials != os.getenv("API_TOKEN", "dev-token"):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return credentials.credentials

# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

@app.post("/businesses")
def register_business(profile: BusinessProfile):
    db.upsert_business(profile.dict())
    return {"message": "Business registered", "business_id": profile.business_id}

@app.get("/businesses/{business_id}")
def get_business(business_id: str, token: str = Depends(verify_token)):
    biz = db.get_business(business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="Business not found")
    return biz

@app.post("/businesses/{business_id}/sync")
def sync_reviews(business_id: str, background_tasks: BackgroundTasks, token: str = Depends(verify_token)):
    biz = db.get_business(business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="Business not found")
    background_tasks.add_task(_sync_all_platforms, business_id)
    return {"message": "Sync started", "business_id": business_id}

@app.get("/businesses/{business_id}/reviews")
def get_reviews(
    business_id: str,
    platform: Optional[str] = None,
    min_stars: Optional[int] = None,
    max_stars: Optional[int] = None,
    days: int = 30,
    token: str = Depends(verify_token),
):
    reviews = db.get_reviews(business_id, platform=platform, min_stars=min_stars, max_stars=max_stars, days=days)
    return {"business_id": business_id, "count": len(reviews), "reviews": reviews}

@app.get("/businesses/{business_id}/stats")
def get_stats(business_id: str, days: int = 30, token: str = Depends(verify_token)):
    return db.get_stats(business_id, days)

@app.post("/businesses/{business_id}/digest")
def generate_digest(business_id: str, background_tasks: BackgroundTasks, token: str = Depends(verify_token)):
    background_tasks.add_task(_send_digest, business_id)
    return {"message": "Digest generation started"}

@app.get("/businesses/{business_id}/alerts")
def get_alerts(business_id: str, limit: int = 50, token: str = Depends(verify_token)):
    return db.get_alerts(business_id, limit)

# ── Sync logic ────────────────────────────────────────────────────────────────

def _sync_all_platforms(business_id: str):
    biz = db.get_business(business_id)
    if not biz:
        return

    new_reviews = []

    if biz.get("google_place_id"):
        reviews = fetch_google_reviews(biz["google_place_id"])
        for r in reviews:
            r["platform"] = "google"
            r["business_id"] = business_id
        new_reviews.extend(reviews)

    if biz.get("yelp_business_id"):
        reviews = fetch_yelp_reviews(biz["yelp_business_id"])
        for r in reviews:
            r["platform"] = "yelp"
            r["business_id"] = business_id
        new_reviews.extend(reviews)

    if biz.get("app_store_app_id"):
        reviews = fetch_app_store_reviews(biz["app_store_app_id"])
        for r in reviews:
            r["platform"] = "app_store"
            r["business_id"] = business_id
        new_reviews.extend(reviews)

    saved_new = 0
    for review in new_reviews:
        is_new = db.save_review(review)
        if is_new:
            saved_new += 1
            _check_and_alert(biz, review)

    db.update_sync_time(business_id)
    print(f"[review-radar] Synced {business_id}: {len(new_reviews)} fetched, {saved_new} new")

def _check_and_alert(biz: dict, review: dict):
    threshold = biz.get("alert_threshold_stars", 3)
    stars = review.get("stars", 5)

    if biz.get("alert_on_negative") and stars <= threshold:
        alert = {
            "business_id": biz["business_id"],
            "type": "negative_review",
            "platform": review["platform"],
            "stars": stars,
            "review_text": review.get("text", "")[:200],
            "author": review.get("author", "Anonymous"),
            "timestamp": datetime.utcnow().isoformat(),
        }
        db.save_alert(alert)

        if biz.get("alert_email"):
            _send_alert_email(biz, review)

def _send_alert_email(biz: dict, review: dict):
    smtp_host = os.getenv("SMTP_HOST")
    if not smtp_host:
        return

    stars_display = "⭐" * review.get("stars", 1)
    body = f"""
<h2>⚠️ New {review.get('stars', '?')}-star review on {review['platform'].title()}</h2>
<p><strong>Business:</strong> {biz['name']}</p>
<p><strong>Rating:</strong> {stars_display} ({review.get('stars', '?')}/5)</p>
<p><strong>Author:</strong> {review.get('author', 'Anonymous')}</p>
<p><strong>Review:</strong><br><em>"{review.get('text', '(no text)')}"</em></p>
<hr>
<p><small>Powered by Review Radar</small></p>
"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"⚠️ {review.get('stars', '?')}-star review on {review['platform'].title()} — {biz['name']}"
    msg["From"] = os.getenv("SMTP_USER", "alerts@reviewradar.io")
    msg["To"] = biz["alert_email"]
    msg.attach(MIMEText(body, "html"))

    try:
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        with smtplib.SMTP(os.getenv("SMTP_HOST"), smtp_port) as server:
            server.starttls()
            server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASS"))
            server.sendmail(os.getenv("SMTP_USER"), biz["alert_email"], msg.as_string())
    except Exception as e:
        print(f"[review-radar] Email alert failed: {e}")

def _send_digest(business_id: str):
    biz = db.get_business(business_id)
    stats = db.get_stats(business_id, days=7)
    reviews = db.get_reviews(business_id, days=7)

    if not biz or not reviews:
        return

    platform_breakdown = {}
    for r in reviews:
        p = r["platform"]
        platform_breakdown.setdefault(p, {"count": 0, "total_stars": 0})
        platform_breakdown[p]["count"] += 1
        platform_breakdown[p]["total_stars"] += r.get("stars", 0)

    platform_html = ""
    for platform, data in platform_breakdown.items():
        avg = data["total_stars"] / data["count"] if data["count"] else 0
        platform_html += f"<li><strong>{platform.title()}:</strong> {data['count']} reviews, avg {avg:.1f}⭐</li>"

    recent_html = ""
    for r in reviews[:5]:
        stars = "⭐" * r.get("stars", 0)
        recent_html += f"""
<div style="border-left: 3px solid #ddd; padding: 10px; margin: 10px 0;">
  <strong>{r.get('author', 'Anonymous')}</strong> — {stars} on {r.get('platform', '').title()}<br>
  <em>"{r.get('text', '(no text)')[:150]}"</em>
</div>"""

    body = f"""
<h2>📊 Weekly Review Digest — {biz['name']}</h2>
<p><strong>Period:</strong> Last 7 days</p>

<h3>Summary</h3>
<ul>
  <li><strong>Total new reviews:</strong> {stats.get('total', 0)}</li>
  <li><strong>Average rating:</strong> {stats.get('avg_stars', 0):.1f} ⭐</li>
  <li><strong>Negative reviews (≤{biz.get('alert_threshold_stars', 3)}⭐):</strong> {stats.get('negative', 0)}</li>
</ul>

<h3>By Platform</h3>
<ul>{platform_html}</ul>

<h3>Recent Reviews</h3>
{recent_html}

<hr><p><small>Powered by Review Radar</small></p>
"""
    smtp_host = os.getenv("SMTP_HOST")
    if not smtp_host:
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📊 Weekly Review Digest — {biz['name']}"
    msg["From"] = os.getenv("SMTP_USER", "digest@reviewradar.io")
    msg["To"] = biz["alert_email"]
    msg.attach(MIMEText(body, "html"))

    try:
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASS"))
            server.sendmail(os.getenv("SMTP_USER"), biz["alert_email"], msg.as_string())
    except Exception as e:
        print(f"[review-radar] Digest email failed: {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
