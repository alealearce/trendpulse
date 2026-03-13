"""
sources/spotify.py

Pulls trending songs from Spotify using endpoints that work with
Client Credentials (no user auth required).

API changes to work around:
- Nov 2023: GET /v1/playlists/{id}/tracks requires user OAuth
- Late 2024: GET /v1/recommendations deprecated (404)
- 2025+: search with field filters (year:, genre:) returns 400

We now use:
  1. browse/new-releases → album_tracks → tracks (for popularity scores)
  2. Simple search queries (no field filters, limit ≤ 20) as fallback

Requires: SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET env vars
Free credentials at: developer.spotify.com → Create App
"""

import os
import logging
from typing import Any

logger = logging.getLogger(__name__)


def get_viral_sounds(limit: int = 20) -> list[dict[str, Any]]:
    """
    Return trending songs from Spotify, normalized as trend dicts.
    Uses new_releases + simple search (both work with Client Credentials).
    """
    sp = _client()
    if not sp:
        return []

    seen_ids: set[str] = set()
    results: list[dict[str, Any]] = []

    # ── Strategy 1: New releases → album tracks → full track objects ─────────
    try:
        nr = sp.new_releases(country="US", limit=20)
        albums = (nr.get("albums") or {}).get("items") or []
        logger.info(f"Spotify new releases: {len(albums)} albums")

        # Collect track IDs from each album (up to 3 tracks per album)
        track_ids: list[str] = []
        for album in albums:
            if not album:
                continue
            album_id = album.get("id")
            if not album_id:
                continue
            try:
                at = sp.album_tracks(album_id, market="US", limit=3)
                for t in (at or {}).get("items") or []:
                    if t and t.get("id") and t["id"] not in seen_ids:
                        track_ids.append(t["id"])
                        seen_ids.add(t["id"])
            except Exception as exc:
                logger.debug(f"album_tracks({album_id}) failed: {exc}")

        # Fetch full track objects with popularity (max 50 per call)
        for i in range(0, min(len(track_ids), 100), 50):
            chunk = track_ids[i : i + 50]
            if not chunk:
                continue
            try:
                resp = sp.tracks(chunk, market="US")
                tracks = [t for t in (resp or {}).get("tracks") or [] if t]
                tracks.sort(key=lambda t: t.get("popularity", 0), reverse=True)
                for track in tracks:
                    tid = track.get("id")
                    if not tid:
                        continue
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
                        "rank":         len(results) + 1,
                        "example_url":  ext_urls.get("spotify"),
                        "extra": {
                            "track_id":    tid,
                            "artist":      artist,
                            "popularity":  popularity,
                            "playlist":    "new_releases",
                            "preview_url": track.get("preview_url"),
                        },
                    })
            except Exception as exc:
                logger.warning(f"Spotify tracks() call failed: {exc}")

        logger.info(f"Spotify new_releases strategy: {len(results)} tracks")

    except Exception as exc:
        logger.warning(f"Spotify new_releases failed: {exc}")

    # ── Strategy 2: Simple search queries as fallback ─────────────────────────
    if len(results) < limit:
        for query in ["pop", "hip hop", "top hits"]:
            if len(results) >= limit:
                break
            try:
                resp = sp.search(q=query, type="track", limit=20)
                tracks = (resp.get("tracks") or {}).get("items") or []
                tracks.sort(key=lambda t: (t or {}).get("popularity", 0), reverse=True)
                logger.info(f"Spotify search '{query}': {len(tracks)} candidates")

                for track in tracks:
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
                        "rank":         len(results) + 1,
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
