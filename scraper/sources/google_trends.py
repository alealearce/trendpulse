"""
sources/google_trends.py

Pulls real-time trending searches from Google Trends and measures
keyword velocity (recent interest vs 7-day average).

Used in two ways:
  1. get_trending_topics()   — today's top trending searches
  2. check_keyword_velocity() — validate TikTok trends with search lift

Free, no API key required. Uses the pytrends library.
"""

import time
import logging
from typing import Any

logger = logging.getLogger(__name__)

FOOD_KW    = ["recipe", "food", "cook", "eat", "drink", "restaurant", "bake"]
PRODUCT_KW = ["buy", "sale", "deal", "review", "amazon", "dupes", "haul"]
BEAUTY_KW  = ["makeup", "skincare", "beauty", "hair", "nails"]
FITNESS_KW = ["workout", "gym", "yoga", "fitness", "exercise"]


def get_trending_topics(geo: str = "US") -> list[dict[str, Any]]:
    """
    Pull today's top 20 real-time trending searches from Google.
    Returns them normalized as trend dicts.
    """
    pytrends = _client()
    if not pytrends:
        return []

    try:
        pn = "united_states" if geo == "US" else "canada"
        # trending_searches() endpoint is deprecated/broken in 2025+.
        # realtime_trending_searches() hits a different, working endpoint.
        try:
            df = pytrends.realtime_trending_searches(pn=geo)
            topics: list[str] = df["title"].tolist()[:20]
        except Exception:
            # Last-resort fallback to legacy endpoint
            df = pytrends.trending_searches(pn=pn)
            topics = df[0].tolist()[:20]

        results = []
        for rank, term in enumerate(topics, start=1):
            term_lower = term.lower()

            # Classify category from search term
            if any(kw in term_lower for kw in FOOD_KW):
                category, trend_type = "food", "food"
            elif any(kw in term_lower for kw in PRODUCT_KW):
                category, trend_type = "product", "product"
            elif any(kw in term_lower for kw in BEAUTY_KW):
                category, trend_type = "beauty", "hashtag"
            elif any(kw in term_lower for kw in FITNESS_KW):
                category, trend_type = "fitness", "hashtag"
            else:
                category, trend_type = "general", "hashtag"

            results.append({
                "trend_name":   term,
                "trend_type":   trend_type,
                "category":     category,
                "source":       "google_trends",
                "raw_score":    float(max(0, 20 - rank)),
                "velocity_24h": None,
                "total_uses":   0,
                "views":        0,
                "rank":         rank,
                "example_url":  f"https://trends.google.com/trends/explore?q={term.replace(' ', '+')}",
                "extra":        {"geo": geo, "type": "realtime"},
            })

        logger.info(f"Google Trends: {len(results)} trending topics")
        return results

    except Exception as exc:
        logger.warning(f"Google Trends trending_searches failed: {exc}")
        return []


def check_keyword_velocity(
    keywords: list[str],
    timeframe: str = "now 7-d",
    geo: str = "US",
) -> dict[str, float]:
    """
    For a list of trend names, return a dict of keyword → velocity score.
    Velocity = (most recent day's interest / 7-day average - 1) * 100
    A score of 50 means "50% above the weekly average today" = rising fast.

    Used by the scorer to boost trends that are also spiking on Google.
    """
    if not keywords:
        return {}

    pytrends = _client()
    if not pytrends:
        return {}

    scores: dict[str, float] = {}
    # pytrends allows max 5 keywords per request
    batches = [keywords[i:i + 5] for i in range(0, len(keywords), 5)]

    for batch in batches:
        try:
            pytrends.build_payload(batch, timeframe=timeframe, geo=geo)
            data = pytrends.interest_over_time()
            if data.empty:
                continue

            for kw in batch:
                if kw in data.columns:
                    recent = float(data[kw].iloc[-1])
                    avg    = float(data[kw].mean())
                    if avg > 0:
                        scores[kw] = round((recent / avg - 1) * 100, 1)

            time.sleep(1.2)  # respect rate limits

        except Exception as exc:
            logger.warning(f"Velocity check batch {batch} failed: {exc}")

    return scores


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _client():
    """Return a TrendReq instance, or None if pytrends isn't installed."""
    try:
        from pytrends.request import TrendReq
        return TrendReq(
            hl="en-US",
            tz=360,
            timeout=(10, 25),
            retries=3,
            backoff_factor=0.5,
        )
    except ImportError:
        logger.warning("pytrends not installed — skipping Google Trends source")
        return None
    except Exception as exc:
        logger.warning(f"Google Trends client init failed: {exc}")
        return None
