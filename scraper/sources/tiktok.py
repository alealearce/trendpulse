"""
sources/tiktok.py

Scrapes TikTok Creative Center for trending hashtags and sounds.
Uses the same API endpoints the Creative Center web UI calls —
no API key required.

Endpoints:
  /popular_trend/hashtag/list  → trending hashtags
  /popular_trend/music/list    → trending sounds
"""

import time
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

CREATIVE_CENTER_BASE = "https://ads.tiktok.com/creative_radar_api/v1"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://ads.tiktok.com",
    "Referer": (
        "https://ads.tiktok.com/business/creativecenter/"
        "inspiration/popular/hashtag/pc/en"
    ),
}

# Keyword → category mapping
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "food":    ["food", "recipe", "cook", "eat", "drink", "meal", "snack",
                "restaurant", "bake", "grill", "taco", "burger", "pizza",
                "sushi", "bread", "dessert", "coffee", "brunch"],
    "beauty":  ["makeup", "beauty", "skincare", "hair", "nails", "glow",
                "routine", "blush", "serum", "lash"],
    "fashion": ["outfit", "fashion", "style", "ootd", "fit", "wear",
                "clothes", "thrift", "vintage", "streetwear"],
    "fitness": ["workout", "gym", "fitness", "exercise", "yoga", "run",
                "pilates", "weights", "protein"],
    "home":    ["home", "decor", "diy", "organize", "clean", "hack",
                "interior", "room", "apartment", "aesthetic"],
    "product": ["shop", "buy", "haul", "unbox", "review", "must have",
                "tiktok shop", "amazon", "deal", "dupes"],
}

# Keyword → trend_type mapping
TYPE_KEYWORDS: dict[str, list[str]] = {
    "dance":     ["dance", "choreo", "choreography", "moves", "dancing"],
    "challenge": ["challenge"],
    "food":      ["recipe", "cook", "food", "eat", "drink", "bake"],
    "product":   ["shop", "buy", "haul", "unbox", "amazon", "tiktok shop"],
}


# ─── Public API ──────────────────────────────────────────────────────────────

def get_trending_hashtags(
    period: int = 7,
    limit: int = 30,
    country: str = "US",
) -> list[dict[str, Any]]:
    """Fetch trending hashtags from TikTok Creative Center."""
    url = f"{CREATIVE_CENTER_BASE}/popular_trend/hashtag/list"
    params = {
        "period":       period,
        "page":         1,
        "limit":        limit,
        "country_code": country,
        "sort_by":      "popular",
    }
    data = _fetch(url, params)
    raw = data.get("data", {}).get("list", [])

    results = []
    for item in raw:
        name      = item.get("hashtag_name", "")
        use_count = item.get("publish_cnt", 0) or 0
        views     = item.get("video_views", 0) or 0
        rank      = item.get("rank", 99)
        raw_score = float(item.get("trend", 50) or 50)

        results.append({
            "trend_name":   f"#{name}",
            "trend_type":   _classify_type(name),
            "category":     _classify_category(name),
            "source":       "tiktok_cc",
            "raw_score":    raw_score,
            "velocity_24h": None,
            "total_uses":   use_count,
            "views":        views,
            "rank":         rank,
            "example_url":  f"https://www.tiktok.com/tag/{name}",
            "extra": {
                "hashtag_id": item.get("hashtag_id"),
                "period":     period,
                "country":    country,
            },
        })

    logger.info(f"TikTok CC: {len(results)} trending hashtags")
    return results


def get_trending_sounds(
    period: int = 7,
    limit: int = 20,
    country: str = "US",
) -> list[dict[str, Any]]:
    """Fetch trending music/sounds from TikTok Creative Center."""
    url = f"{CREATIVE_CENTER_BASE}/popular_trend/music/list"
    params = {
        "period":       period,
        "page":         1,
        "limit":        limit,
        "country_code": country,
    }
    data = _fetch(url, params)
    raw = data.get("data", {}).get("music_list", [])

    results = []
    for item in raw:
        music_name = item.get("music_name", "")
        author     = item.get("author", "Unknown") or "Unknown"
        use_count  = item.get("use_count", 0) or item.get("video_count", 0) or 0
        rank       = item.get("rank", 99)

        results.append({
            "trend_name":   f"{music_name} – {author}",
            "trend_type":   "sound",
            "category":     "general",
            "source":       "tiktok_cc",
            "raw_score":    float(max(0, 100 - rank)),
            "velocity_24h": None,
            "total_uses":   use_count,
            "views":        item.get("video_views", 0) or 0,
            "rank":         rank,
            "example_url":  item.get("link") or None,
            "extra": {
                "music_id":  item.get("music_id") or item.get("id"),
                "author":    author,
                "cover_url": item.get("cover"),
                "country":   country,
            },
        })

    logger.info(f"TikTok CC: {len(results)} trending sounds")
    return results


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _fetch(url: str, params: dict, max_retries: int = 3) -> dict:
    for attempt in range(max_retries):
        try:
            resp = httpx.get(url, params=params, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.warning(f"TikTok fetch attempt {attempt + 1}/{max_retries} failed: {exc}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
    return {}


def _classify_category(name: str) -> str:
    name_lower = name.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in name_lower for kw in keywords):
            return category
    return "general"


def _classify_type(name: str) -> str:
    name_lower = name.lower()
    for trend_type, keywords in TYPE_KEYWORDS.items():
        if any(kw in name_lower for kw in keywords):
            return trend_type
    return "hashtag"
