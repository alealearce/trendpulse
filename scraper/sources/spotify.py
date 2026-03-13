"""
sources/spotify.py

Pulls trending songs from Spotify using endpoints that work with
Client Credentials (no user auth required).

API restrictions (as of 2025-2026):
- GET /v1/playlists/{id}/tracks requires user OAuth (Nov 2023)
- GET /v1/recommendations deprecated (404)
- GET /v1/browse/new-releases returns 403
- search limit is capped at 10 per request (dev-mode apps)
- popularity field is null for Client Credentials requests

Strategy: search with 5 diverse queries at limit=10 each.
Score is rank-based (10 = top result, 1 = 10th).

Requires: SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET env vars
Free credentials at: developer.spotify.com → Create App
"""

import os
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Five diverse queries → up to 50 unique tracks
_QUERIES = [
    "pop 2026",
    "hip hop 2026",
    "top hits",
    "new music this week",
    "trending songs",
]


def get_viral_sounds(limit: int = 20) -> list[dict[str, Any]]:
    """
    Return trending songs from Spotify, normalized as trend dicts.

    Uses sp.search() which works with Client Credentials.
    Max limit per call is 10 (Spotify dev-mode restriction).
    Score is rank-based; popularity is unavailable without user auth.
    """
    sp = _client()
    if not sp:
        return []

    seen_ids: set[str] = set()
    results: list[dict[str, Any]] = []

    for query in _QUERIES:
        if len(results) >= limit:
            break
        try:
            resp = sp.search(q=query, type="track", limit=10, market="US")
            tracks = (resp.get("tracks") or {}).get("items") or []
            logger.info(f"Spotify search '{query}': {len(tracks)} tracks")

            for rank, track in enumerate(tracks, start=1):
                if not track:
                    continue
                track_id = track.get("id")
                if not track_id or track_id in seen_ids:
                    continue
                seen_ids.add(track_id)

                name     = track.get("name", "")
                artists  = track.get("artists") or [{}]
                artist   = artists[0].get("name", "Unknown")
                ext_urls = track.get("external_urls") or {}

                # Score: first result = 10, tenth result = 1
                raw_score = float(max(1, 10 - rank + 1))

                results.append({
                    "trend_name":   f"{name} – {artist}",
                    "trend_type":   "sound",
                    "category":     "general",
                    "source":       "spotify",
                    "raw_score":    raw_score,
                    "velocity_24h": None,
                    "total_uses":   0,
                    "views":        0,
                    "rank":         len(results) + 1,
                    "example_url":  ext_urls.get("spotify"),
                    "extra": {
                        "track_id":    track_id,
                        "artist":      artist,
                        "popularity":  None,
                        "playlist":    f"search:{query}",
                        "preview_url": track.get("preview_url"),
                    },
                })

        except Exception as exc:
            logger.warning(f"Spotify search '{query}' failed: {exc}")

    logger.info(f"Spotify: {len(results)} trending sounds")
    return results


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _client():
    """Lazily create and return a Spotipy client, or None if unconfigured."""
    client_id     = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

    if not client_id or not client_secret:
        logger.warning("Spotify credentials not set — skipping Spotify source")
        return None

    try:
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials

        return spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(
                client_id=client_id,
                client_secret=client_secret,
            )
        )
    except ImportError:
        logger.warning("spotipy not installed — skipping Spotify source")
        return None
    except Exception as exc:
        logger.warning(f"Spotify client init failed: {exc}")
        return None
