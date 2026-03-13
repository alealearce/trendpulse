"""
sources/spotify.py

Pulls trending songs from Spotify using endpoints that work with
Client Credentials (no user auth required).

Note: As of Nov 2023, Spotify restricted GET /v1/playlists/{id}/tracks
to require user OAuth even for public playlists. We use search +
recommendations instead, which still work with Client Credentials.

Requires: SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET env vars
Free credentials at: developer.spotify.com → Create App
"""

import os
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Popular seed genres for recommendations endpoint
SEED_GENRES = ["pop", "hip-hop", "dance", "r-n-b", "latin"]


def get_viral_sounds(limit: int = 20) -> list[dict[str, Any]]:
    """
    Return trending songs from Spotify, normalized as trend dicts.
    Uses search + recommendations (both work with Client Credentials).
    """
    sp = _client()
    if not sp:
        return []

    seen_ids: set[str] = set()
    results: list[dict[str, Any]] = []

    # ── Strategy 1: Search for popular tracks released this year ─────────────
    for query in ["year:2026", "year:2025", "genre:pop"]:
        if len(results) >= limit:
            break
        try:
            resp = sp.search(
                q=query,
                type="track",
                market="US",
                limit=50,
            )
            tracks = (resp.get("tracks") or {}).get("items") or []
            # Sort by popularity descending
            tracks.sort(key=lambda t: (t or {}).get("popularity", 0), reverse=True)
            logger.info(f"Spotify search '{query}': {len(tracks)} candidates")

            for rank, track in enumerate(tracks[:limit], start=1):
                if not track:
                    continue
                track_id = track.get("id")
                if not track_id or track_id in seen_ids:
                    continue
                seen_ids.add(track_id)

                name       = track.get("name", "")
                artists    = track.get("artists") or [{}]
                artist     = artists[0].get("name", "Unknown")
                popularity = track.get("popularity") or 50
                ext_urls   = track.get("external_urls") or {}

                results.append({
                    "trend_name":   f"{name} – {artist}",
                    "trend_type":   "sound",
                    "category":     "general",
                    "source":       "spotify",
                    "raw_score":    popularity * 0.5,
                    "velocity_24h": None,
                    "total_uses":   0,
                    "views":        0,
                    "rank":         rank,
                    "example_url":  ext_urls.get("spotify"),
                    "extra": {
                        "track_id":    track_id,
                        "artist":      artist,
                        "popularity":  popularity,
                        "playlist":    f"search:{query}",
                        "preview_url": track.get("preview_url"),
                    },
                })

        except Exception as exc:
            logger.warning(f"Spotify search '{query}' failed: {exc}")

    # ── Strategy 2: Recommendations if search gave too few results ────────────
    if len(results) < 10:
        logger.info(f"Search gave {len(results)} tracks — trying recommendations")
        try:
            rec = sp.recommendations(
                seed_genres=SEED_GENRES[:5],
                limit=50,
                market="US",
                min_popularity=60,
            )
            tracks = (rec or {}).get("tracks") or []
            tracks.sort(key=lambda t: (t or {}).get("popularity", 0), reverse=True)
            logger.info(f"Spotify recommendations: {len(tracks)} candidates")

            for rank, track in enumerate(tracks[:limit], start=1):
                if not track:
                    continue
                track_id = track.get("id")
                if not track_id or track_id in seen_ids:
                    continue
                seen_ids.add(track_id)

                name       = track.get("name", "")
                artists    = track.get("artists") or [{}]
                artist     = artists[0].get("name", "Unknown")
                popularity = track.get("popularity") or 50
                ext_urls   = track.get("external_urls") or {}

                results.append({
                    "trend_name":   f"{name} – {artist}",
                    "trend_type":   "sound",
                    "category":     "general",
                    "source":       "spotify",
                    "raw_score":    popularity * 0.5,
                    "velocity_24h": None,
                    "total_uses":   0,
                    "views":        0,
                    "rank":         rank,
                    "example_url":  ext_urls.get("spotify"),
                    "extra": {
                        "track_id":    track_id,
                        "artist":      artist,
                        "popularity":  popularity,
                        "playlist":    "recommendations",
                        "preview_url": track.get("preview_url"),
                    },
                })

        except Exception as exc:
            logger.warning(f"Spotify recommendations failed: {exc}")

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
