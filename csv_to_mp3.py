#!/usr/bin/env python3
"""Download audio for songs listed in a CSV file.

The CSV must include `song` and `artist` columns. By default the script prints
the videos it would download. Pass `--download` to actually write MP3 files.
Only download media you have the rights to save.
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import yt_dlp


@dataclass(frozen=True)
class Song:
    row_number: int
    song: str
    artist: str

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
        "--limit",
        type=int,
        help="Process at most this many songs.",
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
        missing = {"song", "artist"} - columns
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise ValueError(f"CSV is missing required column(s): {missing_list}")

        for row_number, row in enumerate(reader, start=2):
            song = (row.get("song") or "").strip()
            artist = (row.get("artist") or "").strip()
            if not song or not artist:
                print(f"Skipping row {row_number}: song and artist are required.", file=sys.stderr)
                continue
            songs.append(Song(row_number=row_number, song=song, artist=artist))
            if limit is not None and len(songs) >= limit:
                break

    return songs


def ydl_options(out_dir: Path, *, simulate: bool) -> dict:
    return {
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


def preview_matches(songs: list[Song]) -> bool:
    found_any = False
    with yt_dlp.YoutubeDL(ydl_options(Path("."), simulate=True)) as ydl:
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
            webpage_url = match.get("webpage_url", "unknown URL")
            print(f"{index}. {song.artist} - {song.song}")
            print(f"   match: {title} ({uploader})")
            print(f"   url:   {webpage_url}")
    return found_any


def download_songs(songs: list[Song], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with yt_dlp.YoutubeDL(ydl_options(out_dir, simulate=False)) as ydl:
        for song in songs:
            print(f"Downloading: {song.artist} - {song.song}")
            ydl.download([song.query])


def confirm_download() -> bool:
    answer = input("Download these matches? Type 'yes' to continue: ")
    return answer.strip().lower() == "yes"


def main() -> int:
    args = parse_args()
    if args.limit is not None and args.limit < 1:
        print("--limit must be greater than zero.", file=sys.stderr)
        return 2

    try:
        songs = load_songs(args.csv, args.limit)
        if not songs:
            print("No valid songs found.", file=sys.stderr)
            return 1

        require_ffmpeg()
        found_any = preview_matches(songs)
        if not args.download:
            print("\nDry run only. Re-run with --download to save MP3 files.")
            return 0
        if not found_any:
            print("No downloadable matches found.", file=sys.stderr)
            return 1
        if not args.yes and not confirm_download():
            print("Cancelled.")
            return 0

        download_songs(songs, args.out_dir)
    except (FileNotFoundError, RuntimeError, ValueError, yt_dlp.utils.DownloadError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
