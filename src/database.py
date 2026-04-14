"""Database setup and models for Review Radar."""
import sqlite3
import os

DB_PATH = os.getenv("DB_PATH", "review_radar.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS trackers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            notify_email TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS competitors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tracker_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            g2_slug TEXT,
            capterra_slug TEXT,
            trustpilot_slug TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (tracker_id) REFERENCES trackers(id)
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            competitor_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            review_id TEXT,
            author TEXT,
            rating REAL,
            title TEXT,
            body TEXT,
            published_date TEXT,
            sentiment_score REAL,
            sentiment_label TEXT,
            scraped_at TEXT DEFAULT (datetime('now')),
            UNIQUE(source, review_id),
            FOREIGN KEY (competitor_id) REFERENCES competitors(id)
        );

        CREATE TABLE IF NOT EXISTS keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tracker_id INTEGER NOT NULL,
            keyword TEXT NOT NULL,
            FOREIGN KEY (tracker_id) REFERENCES trackers(id)
        );

        CREATE TABLE IF NOT EXISTS keyword_mentions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_id INTEGER NOT NULL,
            keyword_id INTEGER NOT NULL,
            FOREIGN KEY (review_id) REFERENCES reviews(id),
            FOREIGN KEY (keyword_id) REFERENCES keywords(id)
        );
    """)
    conn.commit()
    conn.close()
