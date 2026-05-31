#!/usr/bin/env python3
"""Download audio for songs listed in a CSV file.

The CSV must include `song` and `artist` columns, or Spotify export columns
named `Track Name` and `Artist Name(s)`. By default the script prints the
videos it would download. Pass `--download` to actually write MP3 files.
Only download media you have the rights to save.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import requests
import yt_dlp
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, TCON, APIC, error

# Default cookies.txt path — export from Brave via "Get cookies.txt LOCALLY"
# extension while logged into YouTube, then save alongside this script.
_DEFAULT_COOKIES_FILE = Path(__file__).parent / "cookies.txt"


def _find_node() -> str | None:
    """Return the absolute path to a Node.js binary, or None."""
    # Prefer the user's nvm installation which is likely more up-to-date.
    nvm_node = Path.home() / ".nvm/versions/node"
    if nvm_node.is_dir():
        for version_dir in sorted(nvm_node.iterdir(), reverse=True):
            candidate = version_dir / "bin/node"
            if candidate.is_file():
                return str(candidate)
    return shutil.which("node")


@dataclass(frozen=True)
class Song:
    row_number: int
    song: str
    artist: str
    album: str = "Unknown Album"
    date: str = ""
    genre: str = "Pop"
    uri: str = ""

    @property
    def query(self) -> str:
        return f"{self.artist} {self.song} audio".strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search YouTube for songs from a CSV and save them as MP3 files."
    )
    parser.add_argument(
        "--csv",
        default="songs.csv",
        type=Path,
        help="CSV file with song and artist columns. Default: songs.csv",
    )
    parser.add_argument(
        "--out-dir",
        default=Path("downloads"),
        type=Path,
        help="Directory for downloaded MP3 files. Default: downloads",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Actually download files. Without this, the script runs in dry-run mode.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the final confirmation prompt when --download is used.",
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        dest="no_preview",
        help="Skip the preview phase and go straight to downloading.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Process at most this many songs.",
    )
    parser.add_argument(
        "--skip",
        type=int,
        default=0,
        help="Skip the first N songs (useful for resuming a interrupted run).",
    )
    parser.add_argument(
        "--cookies",
        type=Path,
        default=_DEFAULT_COOKIES_FILE,
        help="Path to a Netscape-format cookies.txt file for YouTube auth.",
    )
    return parser.parse_args()


def require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required but was not found on PATH.")


def load_songs(csv_path: Path, limit: int | None = None) -> list[Song]:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    songs: list[Song] = []
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        if {"song", "artist"} <= columns:
            song_column = "song"
            artist_column = "artist"
        elif {"Track Name", "Artist Name(s)"} <= columns:
            song_column = "Track Name"
            artist_column = "Artist Name(s)"
        else:
            raise ValueError(
                "CSV must include either song/artist columns or Spotify export "
                "columns Track Name/Artist Name(s)."
            )

        for row_number, row in enumerate(reader, start=2):
            song = (row.get(song_column) or "").strip()
            artist = (row.get(artist_column) or "").strip()

            if not song or not artist:
                print(f"Skipping row {row_number}: song and artist are required.", file=sys.stderr)
                continue

            # Load Spotify columns if present, otherwise use defaults
            album = (row.get("Album Name") or "Unknown Album").strip()
            date = (row.get("Release Date") or "").strip()
            genres = (row.get("Genres") or "").strip()
            uri = (row.get("Track URI") or "").strip()

            genre = genres.split(",")[0].strip().title() if genres else "Pop"
            year = date[:4] if date else ""

            songs.append(Song(
                row_number=row_number,
                song=song,
                artist=artist,
                album=album,
                date=year,
                genre=genre,
                uri=uri
            ))
            if limit is not None and len(songs) >= limit:
                break

    return songs


def ydl_options(out_dir: Path, *, simulate: bool, cookies: Path | None = None) -> dict:
    options: dict = {
        "default_search": "ytsearch1",
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "restrictfilenames": True,
        "outtmpl": str(out_dir / "%(artist,uploader|unknown)s - %(title)s.%(ext)s"),
        "simulate": simulate,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }

    # --- JS runtime (needed for YouTube signature/n-challenge solving) -------
    # The Python API uses a dict: {"node": {"path": "/path/to/node"}}
    node_path = _find_node()
    if node_path:
        options["js_runtimes"] = {"node": {"path": node_path}}
        options["remote_components"] = {"ejs:github"}

    # --- Cookies file (stable export beats live browser DB) ------------------
    if cookies and cookies.is_file():
        options["cookiefile"] = str(cookies)

    if simulate:
        options["extract_flat"] = "in_playlist"
        options["skip_download"] = True
    return options


def preview_matches(songs: list[Song], cookies: Path | None = None) -> bool:
    found_any = False
    with yt_dlp.YoutubeDL(ydl_options(Path("."), simulate=True, cookies=cookies)) as ydl:
        for index, song in enumerate(songs, start=1):
            result = ydl.extract_info(song.query, download=False)
            entries = result.get("entries") or []
            if not entries:
                print(f"{index}. {song.artist} - {song.song}: no match found")
                continue

            found_any = True
            match = entries[0]
            title = match.get("title", "unknown title")
            uploader = match.get("uploader", "unknown uploader")
            webpage_url = match.get("webpage_url") or match.get("url") or "unknown URL"
            if webpage_url != "unknown URL" and not str(webpage_url).startswith("http"):
                webpage_url = f"https://www.youtube.com/watch?v={webpage_url}"
            print(f"{index}. {song.artist} - {song.song}")
            print(f"   match: {title} ({uploader})")
            print(f"   url:   {webpage_url}")
    return found_any


def sanitize_filename(name: str) -> str:
    """Sanitize track/artist names to be valid on exFAT/Windows/Android filesystems."""
    name = re.sub(r"[\\/]", "-", name)
    name = name.replace(":", " -")
    name = re.sub(r'[?*|"<>]', "", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip()

def fetch_spotify_cover(uri: str) -> str | None:
    """Fetch official album cover URL from Spotify OEmbed."""
    if not uri or not uri.startswith("spotify:track:"):
        return None
    try:
        resp = requests.get("https://open.spotify.com/oembed", params={"url": uri}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            thumb_url = data.get("thumbnail_url")
            if thumb_url:
                # Upgrade to 640x640 resolution
                return thumb_url.replace("ab67616d00001e02", "ab67616d0000b273")
    except Exception:
        pass
    return None

def fetch_itunes_cover(artist: str, track: str) -> str | None:
    """Fetch album cover URL from iTunes Search API as a fallback."""
    query = f"{artist} {track}"
    params = {
        "term": query,
        "entity": "song",
        "limit": 1
    }
    try:
        resp = requests.get("https://itunes.apple.com/search", params=params, timeout=10)
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            if results:
                artwork_url = results[0].get("artworkUrl100")
                if artwork_url:
                    # Upgrade to 600x600 resolution
                    return artwork_url.replace("100x100bb.jpg", "600x600bb.jpg")
    except Exception:
        pass
    return None

def fetch_lrclib_lyrics(artist: str, track: str) -> str | None:
    """Fetch synchronized LRC lyrics from lrclib.net search."""
    params = {
        "track_name": track,
        "artist_name": artist
    }
    for attempt in range(3):
        try:
            resp = requests.get("https://lrclib.net/api/search", params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    for entry in data:
                        synced = entry.get("syncedLyrics")
                        if synced:
                            return synced.strip()
                return None
            elif resp.status_code == 429:
                time.sleep((attempt + 1) * 2)
            else:
                return None
        except Exception:
            time.sleep(1)
    return None

def download_songs(songs: list[Song], out_dir: Path, cookies: Path | None = None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    failed: list[Song] = []
    with yt_dlp.YoutubeDL(ydl_options(out_dir, simulate=False, cookies=cookies)) as ydl:
        for index, song in enumerate(songs, start=1):
            print(f"[{index}/{len(songs)}] Downloading: {song.artist} - {song.song}")
            try:
                # Check if this song already exists locally under its normalized name
                clean_artist = sanitize_filename(song.artist.split(";")[0])
                clean_track = sanitize_filename(song.song)
                clean_fn = f"{clean_artist} - {clean_track}.mp3"
                target_path = out_dir / clean_fn
                
                if target_path.exists() and target_path.stat().st_size > 0:
                    print(f"  -> ALREADY DOWNLOADED (skipping)")
                    continue

                # 1. Download the song and get the matched info_dict
                info_dict = ydl.extract_info(song.query, download=True)
                
                # If doing a search query, extract the inner downloaded video entry
                if info_dict and "entries" in info_dict and info_dict["entries"]:
                    video_info = info_dict["entries"][0]
                else:
                    video_info = info_dict
                    
                prep_fn = ydl.prepare_filename(video_info)
                mp3_path = Path(prep_fn).with_suffix(".mp3")
                
                # 2. Check if final file exists
                if not mp3_path.exists():
                    print(f"  Warning: Target MP3 file not found: {mp3_path}", file=sys.stderr)
                    continue

                # 3. Normalize metadata fields
                clean_artist = sanitize_filename(song.artist.split(";")[0])
                clean_track = sanitize_filename(song.song)
                
                # Standard normalized filename
                clean_fn = f"{clean_artist} - {clean_track}.mp3"
                target_path = out_dir / clean_fn
                
                # Handle collision if file already exists
                if target_path.exists() and target_path != mp3_path:
                    clean_fn = f"{clean_artist} - {clean_track} ({song.row_number}).mp3"
                    target_path = out_dir / clean_fn

                # 4. Fetch Cover Art (Spotify OEmbed with iTunes Search & YouTube thumbnail fallback)
                image_bytes = None
                cover_url = None
                if song.uri:
                    cover_url = fetch_spotify_cover(song.uri)
                
                # Fallback to iTunes if Spotify failed
                if not cover_url:
                    cover_url = fetch_itunes_cover(clean_artist, clean_track)
                    
                if cover_url:
                    try:
                        img_resp = requests.get(cover_url, timeout=10)
                        if img_resp.status_code == 200:
                            image_bytes = img_resp.content
                    except Exception:
                        pass
                
                # Ultimate fallback to YouTube video thumbnail
                if not image_bytes:
                    yt_thumb_url = video_info.get("thumbnail")
                    if yt_thumb_url:
                        try:
                            img_resp = requests.get(yt_thumb_url, timeout=10)
                            if img_resp.status_code == 200:
                                image_bytes = img_resp.content
                        except Exception:
                            pass
                
                # 5. Fetch Synchronized Lyrics
                lrc_status = "LRC Not Available"
                lrc_filename = clean_fn.replace(".mp3", ".lrc")
                lrc_path = out_dir / lrc_filename
                
                lrc_text = fetch_lrclib_lyrics(clean_artist, clean_track)
                if lrc_text:
                    try:
                        lrc_path.write_text(lrc_text, encoding="utf-8")
                        lrc_status = "LRC Saved"
                    except Exception:
                        lrc_status = "LRC Write Error"

                # 6. Embed ID3 Tags
                try:
                    try:
                        audio = MP3(mp3_path, ID3=ID3)
                    except error:
                        audio = MP3(mp3_path)
                        audio.add_tags()
                    
                    audio.tags.add(TIT2(encoding=3, text=clean_track))
                    audio.tags.add(TPE1(encoding=3, text=clean_artist))
                    audio.tags.add(TALB(encoding=3, text=song.album))
                    if song.date:
                        audio.tags.add(TDRC(encoding=3, text=song.date))
                    audio.tags.add(TCON(encoding=3, text=song.genre))

                    if image_bytes:
                        audio.tags.add(APIC(
                            encoding=3,
                            mime="image/jpeg",
                            type=3,  # Front Cover
                            desc="Cover",
                            data=image_bytes
                        ))
                    audio.save()
                except Exception as e:
                    print(f"  Warning: Failed embedding tags: {e}", file=sys.stderr)

                # 7. Rename the MP3 to clean filename
                try:
                    os.rename(mp3_path, target_path)
                    print(f"  -> Normalized: {clean_fn} (Art: {image_bytes is not None}, Lyrics: {lrc_status})")
                except Exception as e:
                    print(f"  Warning: Failed renaming file to {clean_fn}: {e}", file=sys.stderr)
                    
            except Exception as exc:
                print(f"  FAILED: {exc}", file=sys.stderr)
                failed.append(song)

    if failed:
        print(f"\n{len(failed)} song(s) could not be downloaded:", file=sys.stderr)
        for song in failed:
            print(f"  - {song.artist} - {song.song}", file=sys.stderr)


def confirm_download() -> bool:
    answer = input("Download these matches? Type 'yes' to continue: ")
    return answer.strip().lower() == "yes"


def main() -> int:
    args = parse_args()
    if args.limit is not None and args.limit < 1:
        print("--limit must be greater than zero.", file=sys.stderr)
        return 2

    try:
        songs = load_songs(args.csv, limit=None)
        if not songs:
            print("No valid songs found.", file=sys.stderr)
            return 1

        if args.skip > 0:
            print(f"Skipping first {args.skip} song(s) as requested.")
            songs = songs[args.skip:]

        if args.limit is not None:
            songs = songs[: args.limit]

        cookies = args.cookies if args.cookies.is_file() else None
        if cookies:
            print(f"Using cookies file: {cookies}")
        else:
            print("Warning: no cookies.txt found — downloads may be blocked by YouTube.", file=sys.stderr)

        require_ffmpeg()
        if not args.no_preview:
            found_any = preview_matches(songs, cookies=cookies)
            if not args.download:
                print("\nDry run only. Re-run with --download to save MP3 files.")
                return 0
            if not found_any:
                print("No downloadable matches found.", file=sys.stderr)
                return 1
            if not args.yes and not confirm_download():
                print("Cancelled.")
                return 0
        elif not args.download:
            print("--no-preview requires --download. Nothing to do.")
            return 1

        download_songs(songs, args.out_dir, cookies=cookies)
    except (FileNotFoundError, RuntimeError, ValueError, yt_dlp.utils.DownloadError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
