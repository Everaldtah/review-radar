"""
Review scraper — fetches reviews from G2, Capterra, and Trustpilot.
Uses httpx + BeautifulSoup for HTML parsing.
"""
import httpx
import time
import os
import hashlib
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Optional

SCRAPE_DELAY = float(os.getenv("SCRAPE_DELAY", "2.0"))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def make_review_id(source: str, text: str) -> str:
    return hashlib.sha256(f"{source}:{text}".encode()).hexdigest()[:16]


def scrape_g2(slug: str) -> list[dict]:
    """Scrape reviews from G2 for a given product slug."""
    url = f"https://www.g2.com/products/{slug}/reviews"
    reviews = []
    try:
        with httpx.Client(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                print(f"[G2] Non-200 for {slug}: {resp.status_code}")
                return reviews
            soup = BeautifulSoup(resp.text, "lxml")
            review_cards = soup.select(".paper.paper--white.paper--box.mb-2")
            if not review_cards:
                # Try alternate selector
                review_cards = soup.select("[itemprop='review']")

            for card in review_cards[:20]:
                try:
                    rating_el = card.select_one("[class*='stars']")
                    title_el = card.select_one("h3, .review-title")
                    body_el = card.select_one(".formatted-text p, [itemprop='reviewBody']")
                    author_el = card.select_one(".name, [itemprop='author']")
                    date_el = card.select_one("time, [itemprop='datePublished']")

                    body = body_el.get_text(strip=True) if body_el else ""
                    if not body:
                        continue

                    review = {
                        "source": "g2",
                        "review_id": make_review_id("g2", body),
                        "author": author_el.get_text(strip=True) if author_el else "Anonymous",
                        "rating": 4.0,  # Default if star parsing fails
                        "title": title_el.get_text(strip=True) if title_el else "",
                        "body": body,
                        "published_date": date_el.get("datetime", "") if date_el else "",
                    }
                    reviews.append(review)
                except Exception:
                    continue
    except Exception as e:
        print(f"[G2] Scrape error for {slug}: {e}")
    time.sleep(SCRAPE_DELAY)
    return reviews


def scrape_capterra(slug: str) -> list[dict]:
    """Scrape reviews from Capterra for a given product slug."""
    url = f"https://www.capterra.com/p/{slug}/"
    reviews = []
    try:
        with httpx.Client(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                print(f"[Capterra] Non-200 for {slug}: {resp.status_code}")
                return reviews
            soup = BeautifulSoup(resp.text, "lxml")
            cards = soup.select("[data-testid='review-card'], .review-listing")

            for card in cards[:20]:
                try:
                    body_el = card.select_one("[class*='prose'], .review-body, p")
                    title_el = card.select_one("h3, .review-title, [class*='title']")
                    author_el = card.select_one("[class*='reviewer'], .reviewer-name")

                    body = body_el.get_text(strip=True) if body_el else ""
                    if not body or len(body) < 20:
                        continue

                    review = {
                        "source": "capterra",
                        "review_id": make_review_id("capterra", body),
                        "author": author_el.get_text(strip=True) if author_el else "Anonymous",
                        "rating": 4.0,
                        "title": title_el.get_text(strip=True) if title_el else "",
                        "body": body,
                        "published_date": "",
                    }
                    reviews.append(review)
                except Exception:
                    continue
    except Exception as e:
        print(f"[Capterra] Scrape error for {slug}: {e}")
    time.sleep(SCRAPE_DELAY)
    return reviews


def scrape_trustpilot(slug: str) -> list[dict]:
    """Scrape reviews from Trustpilot for a given company slug."""
    url = f"https://www.trustpilot.com/review/{slug}"
    reviews = []
    try:
        with httpx.Client(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                print(f"[Trustpilot] Non-200 for {slug}: {resp.status_code}")
                return reviews
            soup = BeautifulSoup(resp.text, "lxml")
            cards = soup.select("[data-service-review-card-paper], article[class*='review']")

            for card in cards[:20]:
                try:
                    body_el = card.select_one("p[class*='review-content'], [data-service-review-text]")
                    title_el = card.select_one("h2[class*='title'], [data-service-review-title]")
                    author_el = card.select_one("[class*='consumer-info__name'], span[class*='typography_display']")
                    rating_el = card.select_one("[data-service-review-rating], img[alt*='Rated']")
                    date_el = card.select_one("time[datetime]")

                    body = body_el.get_text(strip=True) if body_el else ""
                    if not body or len(body) < 20:
                        continue

                    # Extract rating from alt text like "Rated 4 out of 5 stars"
                    rating = 4.0
                    if rating_el and rating_el.get("alt"):
                        try:
                            rating = float(rating_el["alt"].split()[1])
                        except Exception:
                            pass

                    review = {
                        "source": "trustpilot",
                        "review_id": make_review_id("trustpilot", body),
                        "author": author_el.get_text(strip=True) if author_el else "Anonymous",
                        "rating": rating,
                        "title": title_el.get_text(strip=True) if title_el else "",
                        "body": body,
                        "published_date": date_el.get("datetime", "") if date_el else "",
                    }
                    reviews.append(review)
                except Exception:
                    continue
    except Exception as e:
        print(f"[Trustpilot] Scrape error for {slug}: {e}")
    time.sleep(SCRAPE_DELAY)
    return reviews


def scrape_competitor(competitor: dict) -> list[dict]:
    """Scrape all configured sources for a competitor."""
    all_reviews = []
    if competitor.get("g2_slug"):
        all_reviews.extend(scrape_g2(competitor["g2_slug"]))
    if competitor.get("capterra_slug"):
        all_reviews.extend(scrape_capterra(competitor["capterra_slug"]))
    if competitor.get("trustpilot_slug"):
        all_reviews.extend(scrape_trustpilot(competitor["trustpilot_slug"]))
    print(f"[Scraper] {competitor['name']}: scraped {len(all_reviews)} reviews")
    return all_reviews
