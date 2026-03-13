"""
sources/spotify.py

Pulls trending songs from Spotify chart playlists.

Spotify is a strong LEADING indicator for TikTok sounds —
a song typically goes viral on Spotify's charts 24-72 hours before
it explodes on TikTok. Top songs on hot playlists with high popularity
scores are the prime early signals.

Note: Viral 50 playlists were discontinued in 2023 and now require
user authentication. We use currently accessible chart playlists instead.

Requires: SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET env vars
Free credentials at: developer.spotify.com → Create App
"""

import os
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Playlist IDs — publicly accessible Spotify editorial playlists
TARGET_PLAYLISTS = {
    "top_hits_global": "37i9dQZF1DXcBWIGoYBM5M",  # Today's Top Hits
    "hot_hits_usa":    "37i9dQZF1DXcF6B6QPhFDv",  # Hot Hits USA
    "new_friday":      "37i9dQZF1DX4JAvHpjipBk",  # New Music Friday
    "pop_rising":      "37i9dQZF1DWUa8ZRTfalHk",  # Pop Rising
}


def get_viral_sounds(limit: int = 20) -> list[dict[str, Any]]:
    """
    Return songs from Spotify chart playlists, normalized as trend dicts.
    Pulls from multiple playlists, deduplicating by track ID.
    Falls back to search if playlists yield too few results.
    """
    sp = _client()
    if not sp:
        return []

    seen_ids: set[str] = set()
    results: list[dict[str, Any]] = []

    for playlist_key, playlist_id in TARGET_PLAYLISTS.items():
        try:
            data = sp.playlist_tracks(
                playlist_id,
                limit=limit,
                fields="items(track(id,name,artists,external_urls,popularity,preview_url))",
            )
            items = data.get("items", [])

            for rank, item in enumerate(items, start=1):
                track = item.get("track")
                if not track:
                    continue

                track_id = track.get("id")
                if not track_id or track_id in seen_ids:
                    continue
                seen_ids.add(track_id)

                name       = track.get("name", "")
                artist     = (track.get("artists") or [{}])[0].get("name", "Unknown")
                popularity = track.get("popularity", 50) or 50

                # Songs ranked 1-10 on hot playlists = strongest signal
                rank_bonus = max(0, (limit - rank) / limit * 35)

                results.append({
                    "trend_name":   f"{name} – {artist}",
                    "trend_type":   "sound",
                    "category":     "general",
                    "source":       "spotify",
                    "raw_score":    rank_bonus + (popularity * 0.25),
                    "velocity_24h": None,
                    "total_uses":   0,       # no TikTok use count from Spotify
                    "views":        0,
                    "rank":         rank,
                    "example_url":  track.get("external_urls", {}).get("spotify"),
                    "extra": {
                        "track_id":    track_id,
                        "artist":      artist,
                        "popularity":  popularity,
                        "playlist":    playlist_key,
                        "preview_url": track.get("preview_url"),
                    },
                })

        except Exception as exc:
            logger.warning(f"Spotify playlist {playlist_key} failed: {exc}")

    # Search fallback: if playlists yielded too few results, search for
    # popular recent tracks directly
    if len(results) < 10:
        logger.info("Spotify playlists yielded few results, trying search fallback")
        try:
            search_data = sp.search(
                q="year:2025-2026",
                type="track",
                market="US",
                limit=50,
            )
            tracks = (search_data.get("tracks") or {}).get("items", [])
            # Sort by popularity descending
            tracks.sort(key=lambda t: t.get("popularity", 0), reverse=True)

            for rank, track in enumerate(tracks[:limit], start=1):
                track_id = track.get("id")
                if not track_id or track_id in seen_ids:
                    continue
                seen_ids.add(track_id)

                name       = track.get("name", "")
                artist     = (track.get("artists") or [{}])[0].get("name", "Unknown")
                popularity = track.get("popularity", 50) or 50

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
                    "example_url":  track.get("external_urls", {}).get("spotify"),
                    "extra": {
                        "track_id":    track_id,
                        "artist":      artist,
                        "popularity":  popularity,
                        "playlist":    "search_fallback",
                        "preview_url": track.get("preview_url"),
                    },
                })

        except Exception as exc:
            logger.warning(f"Spotify search fallback failed: {exc}")

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
