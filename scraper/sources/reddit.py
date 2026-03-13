"""
sources/reddit.py

Monitors TikTok and trend-adjacent subreddits for early signals.

Reddit is an "early adopter" indicator — by the time a trend is
discussed on Reddit, it's typically still in the first 20% of its
TikTok lifecycle. High-upvote posts in these communities are strong
pre-virality signals.

Requires: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET env vars
Free credentials at: reddit.com/prefs/apps → Create App → script
"""

import os
import re
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Subreddits to monitor — ordered by signal quality
SUBREDDITS = [
    "TikTok",
    "OutOfTheLoop",
    "entrepreneur",
    "dropshipping",
    "Flipping",
    "ecommerce",
    "food",
    "FoodPorn",
    "beauty",
    "streetwear",
]

# Keywords that suggest a post is about a trend breaking out
TREND_SIGNALS = [
    "tiktok", "going viral", "trend", "trending", "viral",
    "everyone is", "people are", "have you seen", "blowing up",
    "tiktok made me", "saw on tiktok", "all over my fyp",
    "fyp", "for you page",
]

FOOD_KW    = ["recipe", "food", "cook", "eat", "drink", "restaurant"]
PRODUCT_KW = ["product", "sell", "buy", "shop", "amazon", "dropship"]
BEAUTY_KW  = ["makeup", "beauty", "skincare", "hair"]


def get_reddit_trends(limit_per_sub: int = 15) -> list[dict[str, Any]]:
    """
    Scan hot posts across trend-related subreddits.
    Returns normalized trend dicts for posts that mention viral/trend signals.
    """
    reddit = _client()
    if not reddit:
        return []

    results: list[dict[str, Any]] = []
    seen_titles: set[str] = set()

    for sub_name in SUBREDDITS:
        try:
            subreddit = reddit.subreddit(sub_name)

            for post in subreddit.hot(limit=limit_per_sub):
                title       = post.title
                title_lower = title.lower()

                # Only include posts with trend-related language
                if not any(kw in title_lower for kw in TREND_SIGNALS):
                    continue

                # Deduplicate
                if title in seen_titles:
                    continue
                seen_titles.add(title)

                trend_name = _extract_trend_name(title)
                if not trend_name:
                    continue

                # Score based on upvotes (capped at 25 pts) + recency bonus
                vote_score  = min(25.0, post.score / 500)
                ratio_bonus = 5.0 if post.upvote_ratio >= 0.9 else 0.0
                raw_score   = vote_score + ratio_bonus

                results.append({
                    "trend_name":   trend_name,
                    "trend_type":   _classify_type(title_lower),
                    "category":     _classify_category(title_lower, sub_name),
                    "source":       "reddit",
                    "raw_score":    raw_score,
                    "velocity_24h": None,
                    "total_uses":   post.score,
                    "views":        0,
                    "rank":         0,
                    "example_url":  f"https://reddit.com{post.permalink}",
                    "extra": {
                        "subreddit":    sub_name,
                        "post_id":      post.id,
                        "upvote_ratio": post.upvote_ratio,
                        "full_title":   title,
                    },
                })

        except Exception as exc:
            logger.warning(f"Reddit r/{sub_name} failed: {exc}")

    logger.info(f"Reddit: {len(results)} trend signals")
    return results


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _client():
    """Create a read-only PRAW Reddit client, or None if unconfigured."""
    client_id     = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")

    if not client_id or not client_secret:
        logger.warning("Reddit credentials not set — skipping Reddit source")
        return None

    try:
        import praw
        return praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=os.getenv("REDDIT_USER_AGENT", "TrendPulse:v1.0"),
            read_only=True,
        )
    except ImportError:
        logger.warning("praw not installed — skipping Reddit source")
        return None
    except Exception as exc:
        logger.warning(f"Reddit client init failed: {exc}")
        return None


def _extract_trend_name(title: str) -> str | None:
    """Strip common Reddit filler phrases to get the core trend name."""
    strip_patterns = [
        r"^what is\s+",       r"^why is\s+",
        r"^why are\s+",       r"^anyone else\s+",
        r"^has anyone\s+",    r"^does anyone\s+",
        r"^is anyone\s+",
        r"\s*\?$",            r"\s*\!$",
        r"\s*\.\.\.$",
    ]
    name = title
    for pattern in strip_patterns:
        name = re.sub(pattern, "", name, flags=re.IGNORECASE).strip()

    # Too short (noise) or too long (not a trend name)
    if not name or len(name) < 4 or len(name) > 80:
        return None

    return name[:70]


def _classify_category(title_lower: str, subreddit: str) -> str:
    if subreddit in ("food", "FoodPorn") or any(kw in title_lower for kw in FOOD_KW):
        return "food"
    if subreddit in ("dropshipping", "Flipping", "ecommerce") or any(kw in title_lower for kw in PRODUCT_KW):
        return "product"
    if subreddit in ("beauty",) or any(kw in title_lower for kw in BEAUTY_KW):
        return "beauty"
    return "general"


def _classify_type(title_lower: str) -> str:
    if "dance" in title_lower or "choreo" in title_lower:
        return "dance"
    if "challenge" in title_lower:
        return "challenge"
    if any(kw in title_lower for kw in FOOD_KW):
        return "food"
    if any(kw in title_lower for kw in PRODUCT_KW):
        return "product"
    return "hashtag"
