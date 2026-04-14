"""
Review Radar — Competitor review monitoring & sentiment tracking.
Scrapes G2, Capterra, and Trustpilot. Surfaces trends. Sends weekly digests.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date, timedelta
import sqlite3
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
import uvicorn

from src.database import init_db, get_conn
from src.scraper import scrape_competitor
from src.sentiment import analyze_sentiment, extract_themes

load_dotenv()
app = FastAPI(title="Review Radar", description="Competitor review monitoring & sentiment tracking", version="1.0.0")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USER)

init_db()


# ── Schemas ───────────────────────────────────────────────────────────────────

class TrackerCreate(BaseModel):
    name: str
    notify_email: str


class CompetitorAdd(BaseModel):
    tracker_id: int
    name: str
    g2_slug: Optional[str] = None
    capterra_slug: Optional[str] = None
    trustpilot_slug: Optional[str] = None


class KeywordAdd(BaseModel):
    tracker_id: int
    keyword: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def save_reviews(competitor_id: int, reviews: list[dict]):
    conn = get_conn()
    keywords = [dict(r) for r in conn.execute(
        "SELECT k.id, k.keyword FROM keywords k "
        "JOIN competitors c ON k.tracker_id = c.tracker_id WHERE c.id = ?", (competitor_id,)
    ).fetchall()]

    inserted = 0
    for r in reviews:
        sentiment = analyze_sentiment(r.get("body", ""))
        try:
            cur = conn.execute(
                "INSERT OR IGNORE INTO reviews (competitor_id, source, review_id, author, rating, title, body, published_date, sentiment_score, sentiment_label) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (competitor_id, r["source"], r["review_id"], r["author"], r["rating"],
                 r["title"], r["body"], r["published_date"], sentiment["score"], sentiment["label"])
            )
            if cur.rowcount:
                new_id = cur.lastrowid
                inserted += 1
                # Check keyword mentions
                body_lower = (r.get("title", "") + " " + r.get("body", "")).lower()
                for kw in keywords:
                    if kw["keyword"].lower() in body_lower:
                        conn.execute(
                            "INSERT INTO keyword_mentions (review_id, keyword_id) VALUES (?, ?)",
                            (new_id, kw["id"])
                        )
        except Exception as e:
            print(f"[DB] Insert error: {e}")
    conn.commit()
    conn.close()
    return inserted


def run_scrape_for_tracker(tracker_id: int) -> dict:
    conn = get_conn()
    competitors = [dict(r) for r in conn.execute(
        "SELECT * FROM competitors WHERE tracker_id=?", (tracker_id,)
    ).fetchall()]
    conn.close()

    total = 0
    for comp in competitors:
        reviews = scrape_competitor(comp)
        new_count = save_reviews(comp["id"], reviews)
        total += new_count
    return {"competitors": len(competitors), "new_reviews": total}


def build_digest_html(tracker: dict, since_date: str) -> str:
    conn = get_conn()
    competitors = [dict(r) for r in conn.execute(
        "SELECT * FROM competitors WHERE tracker_id=?", (tracker["id"],)
    ).fetchall()]

    sections = ""
    for comp in competitors:
        reviews = [dict(r) for r in conn.execute(
            "SELECT * FROM reviews WHERE competitor_id=? AND scraped_at >= ? ORDER BY scraped_at DESC",
            (comp["id"], since_date)
        ).fetchall()]

        if not reviews:
            continue

        avg_sentiment = sum(r["sentiment_score"] for r in reviews) / len(reviews)
        themes = extract_themes(reviews, top_n=5)
        neg_reviews = [r for r in reviews if r["sentiment_label"] == "negative"][:3]

        theme_tags = "".join(f'<span style="background:#eee;padding:3px 8px;border-radius:12px;margin:2px;display:inline-block;font-size:12px">{t["theme"]} ({t["count"]})</span>' for t in themes)
        neg_section = ""
        for r in neg_reviews:
            neg_section += f'<li style="color:#c0392b"><em>"{r["body"][:150]}..."</em> — {r["author"]} ({r["source"].upper()})</li>'

        sentiment_color = "#27ae60" if avg_sentiment > 0.1 else "#e74c3c" if avg_sentiment < -0.1 else "#f39c12"
        sections += f"""
        <div style="border:1px solid #eee;border-radius:8px;padding:16px;margin-bottom:16px">
          <h3 style="margin:0 0 8px">{comp['name']}</h3>
          <p>New reviews: <strong>{len(reviews)}</strong> &nbsp;|&nbsp;
             Avg sentiment: <strong style="color:{sentiment_color}">{avg_sentiment:+.2f}</strong></p>
          <div style="margin:8px 0">{theme_tags}</div>
          {f'<p><strong>Negative feedback:</strong></p><ul>{neg_section}</ul>' if neg_section else ''}
        </div>"""

    conn.close()
    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:800px;margin:auto;padding:20px">
    <h1 style="color:#2c3e50">📡 Review Radar — Weekly Digest</h1>
    <p style="color:#666">Week ending {date.today().isoformat()} &nbsp;|&nbsp; Tracker: {tracker['name']}</p>
    {sections or '<p style="color:#aaa">No new reviews this week.</p>'}
    <hr/><p style="color:#aaa;font-size:12px">Review Radar • Competitor intelligence, automated</p>
    </body></html>"""


def send_digest_email(tracker_id: int):
    conn = get_conn()
    tracker = dict(conn.execute("SELECT * FROM trackers WHERE id=?", (tracker_id,)).fetchone() or {})
    conn.close()
    if not tracker:
        return

    since = (date.today() - timedelta(days=7)).isoformat()
    html = build_digest_html(tracker, since)

    if not SMTP_USER or not SMTP_PASS:
        print(f"[EMAIL SKIPPED] Would send digest to {tracker['notify_email']}")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📡 Review Radar Digest — {tracker['name']} — {date.today().isoformat()}"
    msg["From"] = FROM_EMAIL
    msg["To"] = tracker["notify_email"]
    msg.attach(MIMEText(html, "html"))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(FROM_EMAIL, tracker["notify_email"], msg.as_string())
    print(f"[Email] Digest sent to {tracker['notify_email']}")


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <html><body style="font-family:Arial;max-width:600px;margin:60px auto;text-align:center">
    <h1>📡 Review Radar</h1>
    <p>Competitor review monitoring & sentiment tracking.</p>
    <p><a href="/docs">API Docs →</a></p>
    </body></html>"""


@app.post("/trackers", status_code=201)
def create_tracker(t: TrackerCreate):
    conn = get_conn()
    cur = conn.execute("INSERT INTO trackers (name, notify_email) VALUES (?, ?)", (t.name, t.notify_email))
    conn.commit()
    row = dict(conn.execute("SELECT * FROM trackers WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    return row


@app.get("/trackers")
def list_trackers():
    conn = get_conn()
    rows = [dict(r) for r in conn.execute("SELECT * FROM trackers").fetchall()]
    conn.close()
    return rows


@app.post("/competitors", status_code=201)
def add_competitor(c: CompetitorAdd):
    conn = get_conn()
    tracker = conn.execute("SELECT id FROM trackers WHERE id=?", (c.tracker_id,)).fetchone()
    if not tracker:
        raise HTTPException(404, "Tracker not found")
    cur = conn.execute(
        "INSERT INTO competitors (tracker_id, name, g2_slug, capterra_slug, trustpilot_slug) VALUES (?,?,?,?,?)",
        (c.tracker_id, c.name, c.g2_slug, c.capterra_slug, c.trustpilot_slug)
    )
    conn.commit()
    row = dict(conn.execute("SELECT * FROM competitors WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    return row


@app.get("/trackers/{tracker_id}/competitors")
def list_competitors(tracker_id: int):
    conn = get_conn()
    rows = [dict(r) for r in conn.execute("SELECT * FROM competitors WHERE tracker_id=?", (tracker_id,)).fetchall()]
    conn.close()
    return rows


@app.post("/keywords", status_code=201)
def add_keyword(kw: KeywordAdd):
    conn = get_conn()
    tracker = conn.execute("SELECT id FROM trackers WHERE id=?", (kw.tracker_id,)).fetchone()
    if not tracker:
        raise HTTPException(404, "Tracker not found")
    cur = conn.execute("INSERT INTO keywords (tracker_id, keyword) VALUES (?,?)", (kw.tracker_id, kw.keyword))
    conn.commit()
    conn.close()
    return {"id": cur.lastrowid, "keyword": kw.keyword}


@app.post("/trackers/{tracker_id}/scrape")
def trigger_scrape(tracker_id: int, background_tasks: BackgroundTasks):
    conn = get_conn()
    tracker = conn.execute("SELECT id FROM trackers WHERE id=?", (tracker_id,)).fetchone()
    conn.close()
    if not tracker:
        raise HTTPException(404, "Tracker not found")
    background_tasks.add_task(run_scrape_for_tracker, tracker_id)
    return {"status": "scraping started", "tracker_id": tracker_id}


@app.get("/trackers/{tracker_id}/reviews")
def get_reviews(tracker_id: int, source: Optional[str] = None, sentiment: Optional[str] = None, limit: int = 50):
    conn = get_conn()
    q = "SELECT r.* FROM reviews r JOIN competitors c ON r.competitor_id = c.id WHERE c.tracker_id=?"
    params = [tracker_id]
    if source:
        q += " AND r.source=?"; params.append(source)
    if sentiment:
        q += " AND r.sentiment_label=?"; params.append(sentiment)
    q += " ORDER BY r.scraped_at DESC LIMIT ?"
    params.append(limit)
    rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    conn.close()
    return rows


@app.get("/trackers/{tracker_id}/insights")
def get_insights(tracker_id: int, days: int = 30):
    conn = get_conn()
    since = (date.today() - timedelta(days=days)).isoformat()
    reviews = [dict(r) for r in conn.execute(
        "SELECT r.* FROM reviews r JOIN competitors c ON r.competitor_id=c.id WHERE c.tracker_id=? AND r.scraped_at>=?",
        (tracker_id, since)
    ).fetchall()]

    by_competitor = {}
    competitors = [dict(r) for r in conn.execute("SELECT * FROM competitors WHERE tracker_id=?", (tracker_id,)).fetchall()]
    for comp in competitors:
        comp_reviews = [r for r in reviews if r["competitor_id"] == comp["id"]]
        if not comp_reviews:
            continue
        avg_rating = sum(r["rating"] for r in comp_reviews) / len(comp_reviews)
        avg_sentiment = sum(r["sentiment_score"] for r in comp_reviews) / len(comp_reviews)
        by_competitor[comp["name"]] = {
            "total_reviews": len(comp_reviews),
            "avg_rating": round(avg_rating, 2),
            "avg_sentiment": round(avg_sentiment, 4),
            "positive": sum(1 for r in comp_reviews if r["sentiment_label"] == "positive"),
            "neutral": sum(1 for r in comp_reviews if r["sentiment_label"] == "neutral"),
            "negative": sum(1 for r in comp_reviews if r["sentiment_label"] == "negative"),
            "top_themes": extract_themes(comp_reviews, top_n=5),
        }
    conn.close()
    return {"period_days": days, "competitors": by_competitor}


@app.post("/trackers/{tracker_id}/digest")
def trigger_digest(tracker_id: int, background_tasks: BackgroundTasks):
    conn = get_conn()
    tracker = conn.execute("SELECT id FROM trackers WHERE id=?", (tracker_id,)).fetchone()
    conn.close()
    if not tracker:
        raise HTTPException(404, "Tracker not found")
    background_tasks.add_task(send_digest_email, tracker_id)
    return {"status": "digest queued", "tracker_id": tracker_id}


@app.get("/trackers/{tracker_id}/digest/preview", response_class=HTMLResponse)
def preview_digest(tracker_id: int):
    conn = get_conn()
    tracker = dict(conn.execute("SELECT * FROM trackers WHERE id=?", (tracker_id,)).fetchone() or {})
    conn.close()
    if not tracker:
        raise HTTPException(404, "Tracker not found")
    since = (date.today() - timedelta(days=7)).isoformat()
    return build_digest_html(tracker, since)


@app.get("/health")
def health():
    return {"status": "ok"}


# ── Scheduler ─────────────────────────────────────────────────────────────────
def weekly_digest_job():
    conn = get_conn()
    trackers = [dict(r) for r in conn.execute("SELECT * FROM trackers").fetchall()]
    conn.close()
    for tracker in trackers:
        send_digest_email(tracker["id"])


scheduler = BackgroundScheduler()
digest_hour = int(os.getenv("DIGEST_CRON_HOUR", "8"))
digest_dow = os.getenv("DIGEST_CRON_DAY_OF_WEEK", "mon")
scheduler.add_job(weekly_digest_job, "cron", day_of_week=digest_dow, hour=digest_hour)
scheduler.start()


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8001")), reload=True)
