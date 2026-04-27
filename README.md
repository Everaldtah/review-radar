# review-radar

> Multi-platform review monitor with real-time alerts and weekly digest reports for local businesses.

## The Problem

Local business owners miss negative reviews for days or weeks because they'd have to manually check Google, Yelp, and app stores individually. One unanswered 1-star review costs an average of **22 potential customers**. Reputation management tools exist but cost $200-$500/month — far too expensive for small businesses.

**review-radar** monitors all your review platforms in one place, instantly alerts you to negative reviews, and delivers weekly performance digests — for a fraction of the cost.

## Features

- **Multi-platform monitoring** — Google Places, Yelp, Apple App Store
- **Instant negative review alerts** — email notification when a bad review lands
- **Configurable alert threshold** — alert on ≤2, ≤3, or ≤4 stars
- **Weekly digest emails** — every week: total reviews, avg rating, platform breakdown
- **Review analytics** — avg stars, positive vs negative ratio, trend by platform
- **Multi-business** — manage multiple locations from one instance
- **Webhook support** — pipe alerts to Slack, Teams, or any webhook
- **No vendor lock-in** — self-hostable, your data stays yours

## Tech Stack

- Python 3.11+ / FastAPI
- Google Places API, Yelp Fusion API, App Store RSS
- JSON file storage (swappable to PostgreSQL)
- SMTP email delivery

## Installation

```bash
git clone https://github.com/Everaldtah/review-radar.git
cd review-radar
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Add your API keys

uvicorn app.main:app --reload --port 8000
```

## Usage

### Register a business
```bash
curl -X POST http://localhost:8000/businesses \
  -H "Content-Type: application/json" \
  -d '{
    "business_id": "joes-pizza-nyc",
    "name": "Joe'\''s Pizza NYC",
    "alert_email": "joe@joespizza.com",
    "google_place_id": "ChIJxxxxxxxxxxxxxxxx",
    "yelp_business_id": "joes-pizza-new-york",
    "alert_on_negative": true,
    "alert_threshold_stars": 3,
    "weekly_digest": true
  }'
```

### Sync reviews from all platforms
```bash
curl -X POST http://localhost:8000/businesses/joes-pizza-nyc/sync \
  -H "Authorization: Bearer your-secret-api-token"
```

### Get review stats
```bash
curl http://localhost:8000/businesses/joes-pizza-nyc/stats?days=30 \
  -H "Authorization: Bearer your-secret-api-token"
```

### Get recent negative reviews
```bash
curl "http://localhost:8000/businesses/joes-pizza-nyc/reviews?max_stars=3&days=7" \
  -H "Authorization: Bearer your-secret-api-token"
```

### Trigger weekly digest email
```bash
curl -X POST http://localhost:8000/businesses/joes-pizza-nyc/digest \
  -H "Authorization: Bearer your-secret-api-token"
```

### View alerts history
```bash
curl http://localhost:8000/businesses/joes-pizza-nyc/alerts \
  -H "Authorization: Bearer your-secret-api-token"
```

## Demo Mode

Without API keys configured, the scrapers return realistic sample data so you can test the full system immediately. Set real API keys in `.env` for production.

## Monetization Model

| Plan | Price | Features |
|------|-------|---------|
| Starter | $19/mo | 1 business, email alerts, weekly digest |
| Growth | $49/mo | 5 businesses, instant alerts, analytics dashboard |
| Agency | $149/mo | Unlimited businesses, white-label, API access, Slack integration |

**Revenue drivers:** Target restaurant owners, retail stores, salons, hotels. Bundle with "respond to review" AI feature. Integrate with Google My Business API for response suggestions (upsell). Partner with local marketing agencies as resellers.

## License

MIT
