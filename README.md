# Review Radar

**Multi-platform review monitoring + AI response suggestions for local businesses.**

Never miss a negative review again. Review Radar continuously monitors your Google and Yelp reviews, analyzes sentiment automatically, and generates AI-drafted responses you can post in one click.

---

## The Problem

Local businesses receive reviews across multiple platforms — Google, Yelp, TripAdvisor — but have no central dashboard to monitor them all. A single unanswered negative review can cost thousands in lost business. Most reputation management tools cost $150+/month and are built for enterprises.

## Features

- **Multi-platform monitoring** — Google Business (Places API) + Yelp Fusion API
- **Automatic sentiment analysis** — classifies reviews as positive / neutral / negative
- **AI-drafted responses** — GPT-4o-mini generates customized replies per review
- **Response tone settings** — professional, friendly, or brief
- **One-click "Mark Responded"** — track which reviews you've replied to
- **Negative review alerts** — instant Slack/webhook notification on bad reviews
- **Filter & sort** — filter by sentiment, platform, response status
- **Manual scan** — trigger an immediate review fetch from the dashboard
- **Demo mode** — works out of the box without API keys (uses realistic sample data)

## Tech Stack

- **Backend**: Python 3.11+ / FastAPI
- **Database**: SQLite (zero-config)
- **Templates**: Jinja2
- **Scheduler**: APScheduler (polls hourly)
- **AI**: OpenAI GPT-4o-mini (optional)
- **Review APIs**: Google Places API + Yelp Fusion API

## Installation

```bash
# Clone the repo
git clone https://github.com/Everaldtah/review-radar.git
cd review-radar

# Create virtual environment
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env — add API keys if you have them (optional for demo)

# Run the app
python main.py
# → http://localhost:8000
```

## Usage

1. Open `http://localhost:8000`
2. Click **Add Business** and enter your business name
3. Optionally add your **Google Place ID** and/or **Yelp Business ID**
4. Click **Scan Now** to fetch reviews immediately
5. Review the sentiment dashboard and AI-drafted responses
6. Copy a response and paste it into Google/Yelp, then mark as responded

### Finding Your Google Place ID

Visit the [Place ID Finder](https://developers.google.com/maps/documentation/javascript/examples/places-placeid-finder) and search for your business.

### Finding Your Yelp Business ID

Your Yelp Business ID is in your Yelp URL: `yelp.com/biz/YOUR-BUSINESS-ID`

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_PLACES_API_KEY` | No | Google Cloud API key with Places API enabled |
| `YELP_API_KEY` | No | Yelp Fusion API key |
| `OPENAI_API_KEY` | No | OpenAI key for AI response generation |
| `WEBHOOK_URL` | No | Slack/Discord webhook for negative review alerts |
| `POLL_INTERVAL_MINUTES` | No | How often to check for new reviews (default: 60) |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Business overview dashboard |
| `GET` | `/business/new` | Add business form |
| `POST` | `/business/new` | Create business |
| `GET` | `/business/{id}` | Business review dashboard |
| `POST` | `/business/{id}/scan` | Trigger immediate scan |
| `POST` | `/review/{id}/mark-responded` | Mark review as responded |
| `POST` | `/review/{id}/regenerate` | Regenerate AI response |
| `GET` | `/api/businesses` | JSON list of businesses |
| `GET` | `/api/business/{id}/reviews` | JSON review list |

## Monetization Model

- **Free**: 1 business location, last 7 days of reviews, basic sentiment
- **Starter ($19/mo)**: 3 locations, unlimited history, AI responses, email alerts
- **Pro ($49/mo)**: 10 locations, Slack alerts, response tracking, TripAdvisor integration, custom AI tone
- **Agency ($149/mo)**: Unlimited locations, white-label, API access, client reports

## Roadmap

- [ ] TripAdvisor and Facebook reviews
- [ ] Email alerts for owners
- [ ] Weekly sentiment trend reports
- [ ] Response template library
- [ ] Direct response posting via Google Business API
- [ ] Review velocity alerts (sudden spike in negative reviews)

## License

MIT
