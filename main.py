"""
Review Radar — Multi-platform review monitoring + AI response suggestions for local businesses.
Monitors Google Business (via Places API), Yelp, and custom sources for new reviews,
performs sentiment analysis, and generates AI-drafted responses.
"""

import os
import json
import sqlite3
import logging
import asyncio
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, Request, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "reviews.db")
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "")
YELP_API_KEY = os.getenv("YELP_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
POLL_INTERVAL_MINUTES = int(os.getenv("POLL_INTERVAL_MINUTES", "60"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")  # Optional Slack/Discord webhook


# ── Database ──────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS businesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            google_place_id TEXT,
            yelp_business_id TEXT,
            owner_email TEXT,
            notify_negative INTEGER DEFAULT 1,
            notify_all INTEGER DEFAULT 0,
            response_tone TEXT DEFAULT 'professional',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL REFERENCES businesses(id),
            platform TEXT NOT NULL,
            external_id TEXT,
            author_name TEXT,
            rating INTEGER,
            text TEXT,
            published_at TIMESTAMP,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            sentiment TEXT,
            sentiment_score REAL,
            ai_response TEXT,
            responded INTEGER DEFAULT 0,
            UNIQUE(platform, external_id)
        );

        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_id INTEGER NOT NULL REFERENCES businesses(id),
            review_id INTEGER REFERENCES reviews(id),
            message TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            channel TEXT DEFAULT 'webhook'
        );
    """)
    conn.commit()
    conn.close()
    logger.info("Database initialized.")


# ── Sentiment Analysis ────────────────────────────────────────────────────────

def analyze_sentiment_basic(rating: int, text: str) -> tuple[str, float]:
    """Simple rule-based sentiment from star rating + keyword scan."""
    if rating is None:
        rating = 3

    score = (rating - 1) / 4.0  # normalize 1-5 to 0-1

    negative_words = ["terrible", "awful", "horrible", "worst", "never", "disgusting",
                      "rude", "bad", "disappointing", "waste", "scam", "dirty", "broken"]
    positive_words = ["amazing", "excellent", "fantastic", "perfect", "best", "great",
                      "wonderful", "love", "awesome", "outstanding", "incredible", "highly recommend"]

    text_lower = (text or "").lower()
    neg_hits = sum(1 for w in negative_words if w in text_lower)
    pos_hits = sum(1 for w in positive_words if w in text_lower)
    score = min(1.0, max(0.0, score + (pos_hits - neg_hits) * 0.05))

    if score >= 0.65:
        sentiment = "positive"
    elif score >= 0.4:
        sentiment = "neutral"
    else:
        sentiment = "negative"

    return sentiment, round(score, 3)


async def generate_ai_response(review: dict, business_name: str, tone: str = "professional") -> str:
    """Generate an AI-drafted response to a review."""
    if not OPENAI_API_KEY:
        return _template_response(review, business_name)

    tone_map = {
        "professional": "formal and professional",
        "friendly": "warm, friendly, and conversational",
        "brief": "short and concise (2-3 sentences max)",
    }
    tone_desc = tone_map.get(tone, "professional")

    prompt = (
        f"You are writing a response on behalf of '{business_name}' to a customer review. "
        f"Be {tone_desc}. Do NOT use generic templates. Be specific to the review content.\n\n"
        f"Star rating: {review.get('rating', '?')}/5\n"
        f"Reviewer: {review.get('author_name', 'A customer')}\n"
        f"Review: {review.get('text', '')}\n\n"
        f"Write a response in 2-4 sentences. If negative, acknowledge the issue and offer to make it right."
    )

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 200,
                }
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning(f"AI response failed: {e}")
        return _template_response(review, business_name)


def _template_response(review: dict, business_name: str) -> str:
    rating = review.get("rating", 3)
    name = review.get("author_name", "valued customer")
    if rating >= 4:
        return (f"Thank you so much, {name}! We're thrilled to hear you had a great experience at "
                f"{business_name}. We hope to see you again soon!")
    elif rating == 3:
        return (f"Thank you for your feedback, {name}. We appreciate you taking the time to share "
                f"your experience and will use it to improve our service.")
    else:
        return (f"We sincerely apologize for your experience, {name}. This is not the standard we "
                f"hold ourselves to at {business_name}. Please contact us directly so we can make this right.")


# ── Platform Fetchers ─────────────────────────────────────────────────────────

async def fetch_google_reviews(place_id: str) -> list[dict]:
    """Fetch reviews from Google Places API."""
    if not GOOGLE_PLACES_API_KEY or not place_id:
        return []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            url = "https://maps.googleapis.com/maps/api/place/details/json"
            resp = await client.get(url, params={
                "place_id": place_id,
                "fields": "reviews",
                "key": GOOGLE_PLACES_API_KEY,
            })
            resp.raise_for_status()
            data = resp.json()
            reviews = data.get("result", {}).get("reviews", [])
            return [
                {
                    "platform": "google",
                    "external_id": f"google_{place_id}_{i}_{r.get('time', 0)}",
                    "author_name": r.get("author_name", ""),
                    "rating": r.get("rating"),
                    "text": r.get("text", ""),
                    "published_at": datetime.fromtimestamp(r.get("time", 0)).isoformat() if r.get("time") else None,
                }
                for i, r in enumerate(reviews)
            ]
    except Exception as e:
        logger.error(f"Google fetch error: {e}")
        return []


async def fetch_yelp_reviews(business_id: str) -> list[dict]:
    """Fetch reviews from Yelp Fusion API."""
    if not YELP_API_KEY or not business_id:
        return []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"https://api.yelp.com/v3/businesses/{business_id}/reviews",
                headers={"Authorization": f"Bearer {YELP_API_KEY}"},
                params={"limit": 20, "sort_by": "yelp_sort"}
            )
            resp.raise_for_status()
            reviews = resp.json().get("reviews", [])
            return [
                {
                    "platform": "yelp",
                    "external_id": r.get("id", ""),
                    "author_name": r.get("user", {}).get("name", ""),
                    "rating": r.get("rating"),
                    "text": r.get("text", ""),
                    "published_at": r.get("time_created"),
                }
                for r in reviews
            ]
    except Exception as e:
        logger.error(f"Yelp fetch error: {e}")
        return []


async def generate_mock_reviews(business_id: int) -> list[dict]:
    """Generate realistic mock reviews for demo/testing (when no API keys set)."""
    import random
    templates = [
        (5, "Emily R.", "Absolutely loved this place! The service was outstanding and the quality exceeded my expectations. Will definitely be back!"),
        (4, "Marcus T.", "Really good experience overall. Staff was friendly and attentive. Only minor issue was the wait time, but worth it."),
        (2, "Sarah K.", "Disappointed with my visit. The service was slow and the staff seemed disinterested. Not what I expected based on reviews."),
        (5, "James W.", "Best in the area hands down. I've been coming here for years and they never disappoint. Highly recommend to anyone!"),
        (1, "Donna M.", "Terrible experience. Had to wait 45 minutes despite having a reservation. Will not be returning."),
        (3, "Chris B.", "It was okay. Nothing special but nothing terrible either. Average experience for an average price."),
        (5, "Priya L.", "Such a wonderful place! The team went above and beyond to make sure we had a perfect experience. 10/10!"),
    ]
    now = datetime.now()
    results = []
    for i, (rating, author, text) in enumerate(random.sample(templates, min(4, len(templates)))):
        published = (now - timedelta(days=random.randint(0, 30))).isoformat()
        results.append({
            "platform": "demo",
            "external_id": f"demo_{business_id}_{i}_{int(now.timestamp())}",
            "author_name": author,
            "rating": rating,
            "text": text,
            "published_at": published,
        })
    return results


# ── Monitor Job ───────────────────────────────────────────────────────────────

async def monitor_business(business: dict):
    """Fetch new reviews for a business and store any not seen before."""
    conn = get_db()
    business_id = business["id"]

    reviews = []
    if business["google_place_id"]:
        reviews += await fetch_google_reviews(business["google_place_id"])
    if business["yelp_business_id"]:
        reviews += await fetch_yelp_reviews(business["yelp_business_id"])
    if not reviews:
        # Use demo reviews if no API keys configured
        reviews = await generate_mock_reviews(business_id)

    new_count = 0
    for r in reviews:
        existing = conn.execute(
            "SELECT id FROM reviews WHERE platform=? AND external_id=?",
            (r["platform"], r["external_id"])
        ).fetchone()
        if existing:
            continue

        sentiment, score = analyze_sentiment_basic(r.get("rating", 3), r.get("text", ""))
        ai_response = await generate_ai_response(r, business["name"], business.get("response_tone", "professional"))

        conn.execute("""
            INSERT OR IGNORE INTO reviews
              (business_id, platform, external_id, author_name, rating, text, published_at,
               sentiment, sentiment_score, ai_response)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (business_id, r["platform"], r["external_id"], r.get("author_name"),
              r.get("rating"), r.get("text"), r.get("published_at"),
              sentiment, score, ai_response))
        conn.commit()
        new_count += 1

        # Alert on negative reviews
        if sentiment == "negative" and business.get("notify_negative"):
            await send_alert(business, r, sentiment, conn)
        elif business.get("notify_all"):
            await send_alert(business, r, sentiment, conn)

    if new_count:
        logger.info(f"[MONITOR] {business['name']}: {new_count} new review(s)")
    conn.close()


async def send_alert(business: dict, review: dict, sentiment: str, conn):
    """Send a webhook alert for a new review."""
    if not WEBHOOK_URL:
        return
    stars = "⭐" * (review.get("rating") or 3)
    emoji = "🔴" if sentiment == "negative" else "🟡" if sentiment == "neutral" else "🟢"
    msg = {
        "text": (
            f"{emoji} New {sentiment} review for *{business['name']}*\n"
            f"{stars} — {review.get('author_name', 'Anonymous')}\n"
            f"_{review.get('text', '')[:200]}_"
        )
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(WEBHOOK_URL, json=msg)
    except Exception as e:
        logger.warning(f"Webhook alert failed: {e}")


async def run_monitor_job():
    logger.info("[MONITOR] Running scheduled review check...")
    conn = get_db()
    businesses = conn.execute("SELECT * FROM businesses").fetchall()
    conn.close()
    await asyncio.gather(*[monitor_business(dict(b)) for b in businesses])


# ── Scheduler ─────────────────────────────────────────────────────────────────

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler.add_job(run_monitor_job, IntervalTrigger(minutes=POLL_INTERVAL_MINUTES), id="monitor")
    scheduler.start()
    logger.info(f"Monitor scheduler started (every {POLL_INTERVAL_MINUTES}min).")
    yield
    scheduler.shutdown()


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Review Radar", lifespan=lifespan)
templates = Jinja2Templates(directory="templates")


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    conn = get_db()
    businesses = conn.execute("SELECT * FROM businesses ORDER BY created_at DESC").fetchall()
    stats = []
    for b in businesses:
        s = conn.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN sentiment='positive' THEN 1 ELSE 0 END) as positive,
                   SUM(CASE WHEN sentiment='negative' THEN 1 ELSE 0 END) as negative,
                   AVG(rating) as avg_rating
            FROM reviews WHERE business_id=?
        """, (b["id"],)).fetchone()
        stats.append(dict(s))
    conn.close()
    return templates.TemplateResponse("index.html", {
        "request": request, "businesses": businesses, "stats": stats
    })


@app.get("/business/new", response_class=HTMLResponse)
async def new_business_form(request: Request):
    return templates.TemplateResponse("new_business.html", {"request": request})


@app.post("/business/new")
async def create_business(
    name: str = Form(...),
    google_place_id: str = Form(""),
    yelp_business_id: str = Form(""),
    owner_email: str = Form(""),
    notify_negative: bool = Form(True),
    response_tone: str = Form("professional"),
):
    conn = get_db()
    conn.execute("""
        INSERT INTO businesses (name, google_place_id, yelp_business_id, owner_email,
                                notify_negative, response_tone)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (name, google_place_id, yelp_business_id, owner_email,
          1 if notify_negative else 0, response_tone))
    conn.commit()
    conn.close()
    return RedirectResponse("/", status_code=303)


@app.get("/business/{biz_id}", response_class=HTMLResponse)
async def business_dashboard(request: Request, biz_id: int,
                              sentiment: str = "", platform: str = ""):
    conn = get_db()
    biz = conn.execute("SELECT * FROM businesses WHERE id=?", (biz_id,)).fetchone()
    if not biz:
        raise HTTPException(404, "Business not found")

    query = "SELECT * FROM reviews WHERE business_id=?"
    params = [biz_id]
    if sentiment:
        query += " AND sentiment=?"
        params.append(sentiment)
    if platform:
        query += " AND platform=?"
        params.append(platform)
    query += " ORDER BY published_at DESC, fetched_at DESC"

    reviews = conn.execute(query, params).fetchall()
    stats = conn.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN sentiment='positive' THEN 1 ELSE 0 END) as positive,
               SUM(CASE WHEN sentiment='negative' THEN 1 ELSE 0 END) as negative,
               SUM(CASE WHEN sentiment='neutral' THEN 1 ELSE 0 END) as neutral,
               AVG(rating) as avg_rating,
               SUM(CASE WHEN responded=1 THEN 1 ELSE 0 END) as responded_count
        FROM reviews WHERE business_id=?
    """, (biz_id,)).fetchone()
    conn.close()
    return templates.TemplateResponse("business.html", {
        "request": request, "biz": biz, "reviews": reviews,
        "stats": stats, "sentiment_filter": sentiment, "platform_filter": platform
    })


@app.post("/business/{biz_id}/scan")
async def trigger_scan(biz_id: int, background_tasks: BackgroundTasks):
    conn = get_db()
    biz = conn.execute("SELECT * FROM businesses WHERE id=?", (biz_id,)).fetchone()
    conn.close()
    if not biz:
        raise HTTPException(404)
    background_tasks.add_task(monitor_business, dict(biz))
    return JSONResponse({"ok": True, "msg": "Scan triggered. Refresh in a few seconds."})


@app.post("/review/{review_id}/mark-responded")
async def mark_responded(review_id: int):
    conn = get_db()
    conn.execute("UPDATE reviews SET responded=1 WHERE id=?", (review_id,))
    conn.commit()
    conn.close()
    return JSONResponse({"ok": True})


@app.post("/review/{review_id}/regenerate")
async def regenerate_response(review_id: int):
    conn = get_db()
    review = conn.execute("""
        SELECT r.*, b.name as business_name, b.response_tone
        FROM reviews r JOIN businesses b ON r.business_id = b.id
        WHERE r.id=?
    """, (review_id,)).fetchone()
    if not review:
        raise HTTPException(404)
    new_response = await generate_ai_response(dict(review), review["business_name"], review["response_tone"])
    conn.execute("UPDATE reviews SET ai_response=? WHERE id=?", (new_response, review_id))
    conn.commit()
    conn.close()
    return JSONResponse({"ok": True, "response": new_response})


# ── API ───────────────────────────────────────────────────────────────────────

@app.get("/api/businesses")
async def api_businesses():
    conn = get_db()
    data = [dict(b) for b in conn.execute("SELECT * FROM businesses").fetchall()]
    conn.close()
    return data


@app.get("/api/business/{biz_id}/reviews")
async def api_reviews(biz_id: int, limit: int = 50):
    conn = get_db()
    reviews = conn.execute(
        "SELECT * FROM reviews WHERE business_id=? ORDER BY published_at DESC LIMIT ?",
        (biz_id, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in reviews]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
