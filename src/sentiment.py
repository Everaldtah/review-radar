"""Sentiment analysis for review text using TextBlob."""
from textblob import TextBlob


def analyze_sentiment(text: str) -> dict:
    """
    Returns polarity (-1 to 1) and label (positive/neutral/negative).
    """
    try:
        blob = TextBlob(text)
        polarity = blob.sentiment.polarity
        if polarity > 0.1:
            label = "positive"
        elif polarity < -0.1:
            label = "negative"
        else:
            label = "neutral"
        return {"score": round(polarity, 4), "label": label}
    except Exception:
        return {"score": 0.0, "label": "neutral"}


def extract_themes(reviews: list[dict], top_n: int = 10) -> list[dict]:
    """
    Simple frequency-based theme extraction from review text.
    Returns top N noun phrases by frequency.
    """
    phrase_counts = {}
    stop_phrases = {"the product", "this product", "the tool", "our team", "the app", "the platform"}

    for r in reviews:
        text = (r.get("title", "") + " " + r.get("body", "")).lower()
        try:
            blob = TextBlob(text)
            for phrase in blob.noun_phrases:
                phrase = phrase.strip()
                if len(phrase) > 3 and phrase not in stop_phrases:
                    phrase_counts[phrase] = phrase_counts.get(phrase, 0) + 1
        except Exception:
            continue

    sorted_phrases = sorted(phrase_counts.items(), key=lambda x: x[1], reverse=True)
    return [{"theme": p, "count": c} for p, c in sorted_phrases[:top_n]]
