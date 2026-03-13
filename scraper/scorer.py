"""
scorer.py

Converts raw signals from all sources into a single 0–100 "early_score".

The score answers one question: "How likely is this trend to explode
on TikTok in the next 48–72 hours?"

Scoring pillars:
  1. Source quality  — Spotify is the best leading indicator
  2. Use-count sweet spot — 5K–200K uses = real but not peaked
  3. Raw signal      — the source's own ranking/score
  4. Cross-platform  — same trend on 2+ sources = strong confirmation
  5. Rank bonus      — top 3 on any chart = extra weight
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# How much each source's signal is trusted (multiplier)
SOURCE_WEIGHTS: dict[str, float] = {
    "spotify":       1.5,   # Best leading indicator — Spotify → TikTok in 48–72h
    "tiktok_cc":     1.0,   # Direct signal, but may already be trending
    "google_trends": 0.8,   # Cross-platform lift confirmation
    "reddit":        0.6,   # Early-adopter signal, noisier
}

# TikTok use-count ranges and their score impact
#  < 1K     → likely noise / bot activity
#  1K–5K    → too small to call (slight penalty)
#  5K–200K  → sweet spot (early and real) ← we want these
#  200K–1M  → mid-wave (still actionable, slight penalty)
#  > 1M     → likely peaked (larger penalty)
USE_COUNT_TIERS = [
    (0,       1_000,   -15),
    (1_000,   5_000,    -5),
    (5_000,   200_000,  20),  # sweet spot
    (200_000, 1_000_000, -5),
    (1_000_000, 5_000_000, -12),
    (5_000_000, float("inf"), -20),
]

# Display labels and emojis
SCORE_LABELS = [
    (88, "🚀 Early Signal"),
    (74, "📈 Rising Fast"),
    (58, "🔥 Gaining Steam"),
    (0,  "👀 Watch This"),
]

TYPE_EMOJI: dict[str, str] = {
    "sound":     "🎵",
    "dance":     "💃",
    "challenge": "🏆",
    "food":      "🍕",
    "product":   "🛍️",
    "hashtag":   "📈",
}

CATEGORY_DISPLAY: dict[str, str] = {
    "food":    "Food & Recipes",
    "beauty":  "Beauty",
    "fashion": "Fashion",
    "fitness": "Fitness",
    "home":    "Home & Lifestyle",
    "product": "Products",
    "general": "General",
}


# ─── Main entry point ────────────────────────────────────────────────────────

def score_all(raw_trends: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Full pipeline:
      1. Score each raw trend individually
      2. Deduplicate + apply cross-platform bonus
      3. Enrich with display metadata
      4. Return sorted by early_score descending
    """
    # Step 1 — individual scores
    scored = [dict(t, early_score=_score(t)) for t in raw_trends]

    # Step 2 — cross-reference and deduplicate
    merged = _cross_reference(scored)

    # Step 3 — enrich with display fields
    enriched = [_enrich(t) for t in merged]

    # Step 4 — sort
    enriched.sort(key=lambda t: t["early_score"], reverse=True)

    logger.info(f"Scorer: {len(raw_trends)} raw → {len(enriched)} unique trends")
    return enriched


# ─── Scoring logic ───────────────────────────────────────────────────────────

def _score(trend: dict[str, Any]) -> float:
    score = 38.0  # base

    # 1. Source quality (0–15 pts)
    weight = SOURCE_WEIGHTS.get(trend.get("source", ""), 0.5)
    score += weight * 10

    # 2. Use-count sweet spot (-20 to +20 pts)
    uses = trend.get("total_uses") or 0
    for lo, hi, pts in USE_COUNT_TIERS:
        if lo <= uses < hi:
            score += pts
            break

    # 3. Raw signal from source (0–20 pts)
    raw = float(trend.get("raw_score") or 0)
    score += min(20.0, raw * 0.2)

    # 4. Rank bonus — top 3 on any chart (0–10 pts)
    rank = trend.get("rank") or 99
    if rank <= 3:
        score += 10
    elif rank <= 10:
        score += 5
    elif rank <= 20:
        score += 2

    return round(min(100.0, max(0.0, score)), 1)


# ─── Cross-platform deduplication ────────────────────────────────────────────

def _cross_reference(trends: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Group trends with similar names, keep the best-scored version,
    and apply a bonus for trends appearing across multiple sources.
    """
    groups: dict[str, list[dict]] = {}

    for trend in trends:
        key = _normalize(trend["trend_name"])
        groups.setdefault(key, []).append(trend)

    merged = []
    for group in groups.values():
        # Take the version with the highest score as the base
        best = dict(max(group, key=lambda t: t["early_score"]))

        # Cross-platform bonus: +8 pts per additional source, max +24
        unique_sources = {t["source"] for t in group}
        if len(unique_sources) > 1:
            bonus = min(24, (len(unique_sources) - 1) * 8)
            best["early_score"] = round(min(100.0, best["early_score"] + bonus), 1)
            best["cross_platform"] = True
            best["cross_platform_sources"] = sorted(unique_sources)
        else:
            best["cross_platform"] = False
            best["cross_platform_sources"] = [best.get("source", "")]

        merged.append(best)

    return merged


# ─── Enrichment ──────────────────────────────────────────────────────────────

def _enrich(trend: dict[str, Any]) -> dict[str, Any]:
    """Add display-friendly fields."""
    t = dict(trend)
    t["score_label"]      = _label(t.get("early_score", 0))
    t["type_emoji"]       = TYPE_EMOJI.get(t.get("trend_type", "hashtag"), "📈")
    t["category_display"] = CATEGORY_DISPLAY.get(t.get("category", "general"), "General")
    return t


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _normalize(name: str) -> str:
    """Normalize trend name for grouping/deduplication."""
    return name.lower().strip().lstrip("#").strip()


def _label(score: float) -> str:
    for threshold, label in SCORE_LABELS:
        if score >= threshold:
            return label
    return "👀 Watch This"
