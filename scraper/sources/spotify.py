"""
sources/spotify.py

Pulls songs from Spotify's Viral 50 and New Music Friday playlists.

Spotify is the single best LEADING indicator for TikTok sounds —
a song typically goes viral on Spotify's charts 24-72 hours before
it explodes on TikTok. Songs in the top 10 of the Viral 50 that
have under 50K TikTok uses are the prime early signals.

Requires: SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET env vars
Free credentials at: developer.spotify.com → Create App
"""

import os
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Playlist IDs — Spotify maintains these official charts
VIRAL_PLAYLISTS = {
    "viral_global": "37i9dQZEVXbMDoHDwVN2tF",   # Viral 50 - Global
    "viral_us":     "37i9dQZEVXbKuITLyxMdLs",   # Viral 50 - USA
    "viral_ca":     "37i9dQZEVXbKLMSCGPuX8Up",   # Viral 50 - Canada
    "new_friday":   "37i9dQZF1DX4JAvHpjipBk",    # New Music Friday
}


def get_viral_sounds(limit: int = 20) -> list[dict[str, Any]]:
    """
    Return songs from Spotify Viral playlists, normalized as trend dicts.
    Pulls from Global + US + Canada charts, deduplicating by track ID.
    """
    sp = _client()
    if not sp:
        return []

    seen_ids: set[str] = set()
    results: list[dict[str, Any]] = []

    targets = [
        ("viral_global", VIRAL_PLAYLISTS["viral_global"]),
        ("viral_us",     VIRAL_PLAYLISTS["viral_us"]),
        ("viral_ca",     VIRAL_PLAYLISTS["viral_ca"]),
    ]

    for playlist_key, playlist_id in targets:
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

                # Songs ranked 1-10 on viral charts = strongest signal
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

    logger.info(f"Spotify: {len(results)} viral sounds")
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
