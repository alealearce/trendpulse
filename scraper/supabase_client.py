"""
supabase_client.py

All Supabase reads/writes for the TrendPulse scraper.
Uses the service role key so it bypasses RLS (server-side only).
"""

import os
import logging
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)

_client_instance = None


# ─── Connection ──────────────────────────────────────────────────────────────

def _get_client():
    global _client_instance
    if _client_instance is None:
        from supabase import create_client
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not url or not key:
            raise ValueError(
                "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set"
            )
        _client_instance = create_client(url, key)
    return _client_instance


# ─── Trends ──────────────────────────────────────────────────────────────────

def save_daily_trends(
    trends: list[dict[str, Any]],
    trend_date: str | None = None,
) -> int:
    """
    Upsert today's scored trends.
    Clears any existing rows for this date first (allows safe re-runs).
    Returns count of saved trends.
    """
    sb = _get_client()
    today = trend_date or date.today().isoformat()

    # Clear today's rows so re-runs are idempotent
    sb.table("tiktok_trends").delete().eq("date", today).execute()

    rows = []
    for rank, trend in enumerate(trends, start=1):
        rows.append({
            "date":                   today,
            "rank":                   rank,
            "trend_name":             trend.get("trend_name", ""),
            "trend_type":             trend.get("trend_type", "hashtag"),
            "category":               trend.get("category", "general"),
            "category_display":       trend.get("category_display", "General"),
            "early_score":            trend.get("early_score", 0),
            "score_label":            trend.get("score_label", ""),
            "type_emoji":             trend.get("type_emoji", "📈"),
            "source":                 trend.get("source", "unknown"),
            "cross_platform":         trend.get("cross_platform", False),
            "cross_platform_sources": trend.get("cross_platform_sources", []),
            "velocity_24h":           trend.get("velocity_24h"),
            "total_uses":             trend.get("total_uses", 0),
            "example_url":            trend.get("example_url"),
            "why_its_early":          trend.get("why_its_early"),
        })

    if not rows:
        return 0

    result = sb.table("tiktok_trends").insert(rows).execute()
    count = len(result.data) if result.data else 0
    logger.info(f"Supabase: saved {count} trends for {today}")
    return count


def get_today_trends(limit: int = 50) -> list[dict]:
    """Fetch today's ranked trends, ordered by score descending."""
    sb = _get_client()
    today = date.today().isoformat()

    result = (
        sb.table("tiktok_trends")
        .select("*")
        .eq("date", today)
        .order("early_score", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


# ─── Deduplication ───────────────────────────────────────────────────────────

def get_trends_sent_last_n_days(days: int = 14) -> set[str]:
    """
    Return the set of trend_names that were included in any digest
    in the last N days. Used to prevent duplicates across digests.
    """
    sb = _get_client()
    cutoff = (date.today() - timedelta(days=days)).isoformat()

    result = (
        sb.table("trend_sends")
        .select("trend_name")
        .gte("sent_at", cutoff)
        .execute()
    )
    return {row["trend_name"] for row in (result.data or [])}


# ─── Subscribers ─────────────────────────────────────────────────────────────

def get_subscribers(tier: str | None = None) -> list[dict]:
    """Fetch active (non-unsubscribed) subscribers."""
    sb = _get_client()

    query = (
        sb.table("trend_subscribers")
        .select("id, email, tier, niche_filter")
        .is_("unsubscribed_at", "null")
    )
    if tier:
        query = query.eq("tier", tier)

    return query.execute().data or []


# ─── Send tracking ───────────────────────────────────────────────────────────

def record_sends(sends: list[dict]) -> None:
    """
    Record which trends were included in each subscriber's digest.
    Each item: { subscriber_id, trend_id, trend_name, digest_date }
    """
    if not sends:
        return
    sb = _get_client()
    sb.table("trend_sends").insert(sends).execute()
    logger.info(f"Supabase: recorded {len(sends)} trend sends")


def log_digest(
    digest_date: str,
    total_trends: int,
    free_sends: int,
    pro_sends: int,
) -> None:
    """Write a summary row to daily_digests for monitoring."""
    sb = _get_client()
    sb.table("daily_digests").upsert({
        "digest_date":   digest_date,
        "total_trends":  total_trends,
        "free_sends":    free_sends,
        "pro_sends":     pro_sends,
    }, on_conflict="digest_date").execute()
