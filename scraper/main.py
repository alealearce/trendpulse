"""
main.py — TrendPulse Daily Scraper

Runs once per day (triggered by Railway Cron at 5 AM Pacific / 13:00 UTC).

Pipeline:
  1. Collect raw signals from TikTok CC, Spotify, Google Trends, Reddit
  2. Score + deduplicate → ranked list of early trends
  3. Save top 50 trends to Supabase
  4. Exit (Railway Cron restarts it tomorrow)

To run manually:
  python main.py

To test without saving to Supabase:
  DRY_RUN=1 python main.py
"""

import logging
import os
import sys
from datetime import date

from dotenv import load_dotenv
load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("trendpulse")


def run() -> bool:
    """
    Full daily scrape → score → save pipeline.
    Returns True on success, False on critical failure.
    """
    dry_run = os.getenv("DRY_RUN", "").lower() in ("1", "true", "yes")

    logger.info("════════════════════════════════════════════")
    logger.info(f"  TrendPulse Scraper  |  {date.today()}  {'[DRY RUN]' if dry_run else ''}")
    logger.info("════════════════════════════════════════════")

    # ── 1. Collect from all sources ───────────────────────────────────────────
    all_raw: list[dict] = []

    # TikTok Creative Center — hashtags
    logger.info("▶ TikTok Creative Center: hashtags...")
    try:
        from sources.tiktok import get_trending_hashtags
        hashtags = get_trending_hashtags(period=7, limit=30, country="US")
        logger.info(f"  ✓ {len(hashtags)} hashtags")
        all_raw.extend(hashtags)
    except Exception as exc:
        logger.error(f"  ✗ TikTok hashtags failed: {exc}")

    # TikTok Creative Center — sounds
    logger.info("▶ TikTok Creative Center: sounds...")
    try:
        from sources.tiktok import get_trending_sounds
        sounds_cc = get_trending_sounds(period=7, limit=20, country="US")
        logger.info(f"  ✓ {len(sounds_cc)} sounds")
        all_raw.extend(sounds_cc)
    except Exception as exc:
        logger.error(f"  ✗ TikTok sounds failed: {exc}")

    # Spotify Viral Charts — best leading indicator for sounds
    logger.info("▶ Spotify Viral 50...")
    try:
        from sources.spotify import get_viral_sounds
        spotify_sounds = get_viral_sounds(limit=20)
        logger.info(f"  ✓ {len(spotify_sounds)} viral sounds")
        all_raw.extend(spotify_sounds)
    except Exception as exc:
        logger.error(f"  ✗ Spotify failed: {exc}")

    # Google Trends — cross-platform validation
    logger.info("▶ Google Trends...")
    try:
        from sources.google_trends import get_trending_topics
        google = get_trending_topics(geo="US")
        logger.info(f"  ✓ {len(google)} trending topics")
        all_raw.extend(google)
    except Exception as exc:
        logger.error(f"  ✗ Google Trends failed: {exc}")

    # Reddit — early adopter signal
    logger.info("▶ Reddit signals...")
    try:
        from sources.reddit import get_reddit_trends
        reddit = get_reddit_trends(limit_per_sub=15)
        logger.info(f"  ✓ {len(reddit)} Reddit signals")
        all_raw.extend(reddit)
    except Exception as exc:
        logger.error(f"  ✗ Reddit failed: {exc}")

    logger.info(f"Total raw signals: {len(all_raw)}")

    if not all_raw:
        logger.warning(
            "No data collected from any source — skipping save. "
            "TikTok CC requires browser auth (code 40101). "
            "Check Spotify/Google Trends logs above."
        )
        # Exit 0 so Railway does not mark the run as crashed.
        # The scraper will retry on the next scheduled run.
        return True

    # ── 2. Score + deduplicate ────────────────────────────────────────────────
    logger.info("▶ Scoring and ranking...")
    from scorer import score_all
    scored = score_all(all_raw)

    # ── 3. Log top 15 to console ──────────────────────────────────────────────
    logger.info("══ Top 15 trends today ══════════════════════")
    for i, t in enumerate(scored[:15], start=1):
        cross = "✦" if t.get("cross_platform") else " "
        logger.info(
            f"  {i:2}. [{t['early_score']:5.1f}] {cross} "
            f"{t['type_emoji']} {t['trend_name'][:45]:<45} "
            f"({t['category_display']})"
        )
    logger.info("════════════════════════════════════════════")

    # ── 4. Save to Supabase ───────────────────────────────────────────────────
    if dry_run:
        logger.info("DRY RUN — skipping Supabase write")
        return True

    logger.info("▶ Saving to Supabase...")
    try:
        from supabase_client import save_daily_trends
        saved = save_daily_trends(scored[:50])   # keep top 50 in DB
        logger.info(f"  ✓ Saved {saved} trends")
    except Exception as exc:
        logger.error(f"  ✗ Supabase save failed: {exc}")
        return False

    logger.info("════════════════════════════════════════════")
    logger.info("  Scraper complete ✓")
    logger.info("════════════════════════════════════════════")
    return True


if __name__ == "__main__":
    success = run()
    sys.exit(0 if success else 1)
