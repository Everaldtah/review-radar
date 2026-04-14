# 📡 Review Radar

> Competitor review monitoring & sentiment tracking — know what customers say about your competitors before your next sprint.

## The Problem

Product teams spend hours manually reading competitor reviews on G2, Capterra, and Trustpilot, copy-pasting into spreadsheets, trying to spot patterns. They miss emerging complaints, feature requests that competitors can't deliver, and sentiment shifts that signal market opportunities.

**Review Radar** automates this entirely. Point it at your competitors' review profiles, and it continuously scrapes new reviews, runs sentiment analysis, surfaces trending themes, and emails your team a weekly intelligence digest.

## Features

- **Multi-Source Scraping** — G2, Capterra, Trustpilot in one place
- **Sentiment Analysis** — TextBlob NLP scores every review positive/neutral/negative
- **Theme Extraction** — surfaces recurring noun phrases across competitor reviews
- **Keyword Alerts** — flag reviews mentioning specific terms ("slow", "expensive", "missing feature")
- **Weekly Email Digests** — automated HTML reports with insights
- **Trend Insights API** — 30/60/90-day sentiment trends per competitor
- **Multi-Tracker Support** — track multiple competitor groups

## Tech Stack

- **Python 3.11+** / FastAPI
- **SQLite** (zero-config storage)
- **httpx** + **BeautifulSoup4** (web scraping)
- **TextBlob** (sentiment NLP)
- **APScheduler** (weekly cron)

## Installation

```bash
# Clone
git clone https://github.com/Everaldtah/review-radar
cd review-radar

# Install deps
pip install -r requirements.txt
python -m textblob.download_corpora  # download NLP data

# Configure
cp .env.example .env

# Run
python main.py
```

API at `http://localhost:8001`, docs at `http://localhost:8001/docs`

## Usage

### 1. Create a tracker
```bash
curl -X POST http://localhost:8001/trackers \
  -H "Content-Type: application/json" \
  -d '{"name": "CRM Competitors", "notify_email": "product@yourco.com"}'
```

### 2. Add competitors to track
```bash
curl -X POST http://localhost:8001/competitors \
  -H "Content-Type: application/json" \
  -d '{
    "tracker_id": 1,
    "name": "HubSpot",
    "g2_slug": "hubspot-crm",
    "trustpilot_slug": "hubspot.com"
  }'
```

### 3. Add keywords to flag
```bash
curl -X POST http://localhost:8001/keywords \
  -H "Content-Type: application/json" \
  -d '{"tracker_id": 1, "keyword": "too expensive"}'
```

### 4. Trigger a scrape
```bash
curl -X POST http://localhost:8001/trackers/1/scrape
```

### 5. Get insights
```bash
curl http://localhost:8001/trackers/1/insights?days=30
```

### 6. Preview weekly digest
```bash
open http://localhost:8001/trackers/1/digest/preview
```

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/trackers` | Create tracker |
| GET | `/trackers` | List trackers |
| POST | `/competitors` | Add competitor |
| GET | `/trackers/{id}/competitors` | List competitors |
| POST | `/keywords` | Add keyword alert |
| POST | `/trackers/{id}/scrape` | Trigger scrape |
| GET | `/trackers/{id}/reviews` | Get reviews |
| GET | `/trackers/{id}/insights` | Sentiment insights |
| POST | `/trackers/{id}/digest` | Send digest email |
| GET | `/trackers/{id}/digest/preview` | HTML preview |

## Monetization Model

| Tier | Price | Limits |
|------|-------|--------|
| Free | $0/mo | 2 competitors, weekly scrape |
| Starter | $29/mo | 10 competitors, daily scrape |
| Growth | $79/mo | Unlimited competitors, Slack alerts, CSV export |
| Agency | $199/mo | Multiple trackers, white-label reports, API access |

**Target users:** Product managers, competitive intelligence teams, SaaS founders. Market size: 500K+ product teams globally.
