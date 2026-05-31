# csv2mp3 🎵

A blazing fast, robust CLI tool to turn Spotify CSV exports into a perfectly tagged offline MP3 library, complete with official high-res cover art and synchronized scrolling lyrics (`.lrc`).

No boilerplate, no-nonsense. Just high-speed extraction and automated library tagging.

---

## Features

- **Fast Incremental Sync**: Instantly skips already-downloaded tracks in a split second, downloading only new additions to your CSV.
- **Official Spotify Album Art**: Automatically queries Spotify CDN to grab official, 640x640 square cover art and embeds it into your MP3 tags natively.
- **Synchronized Scrolling Lyrics (`.lrc`)**: Grabs companion timestamped lyrics from the community LRC database for real-time scrolling display on mobile/tablet audio players.
- **Metadata Tagging**: Autopopulates standard ID3v2 frames: Title, Artist, Album, Release Year, and Genre.
- **exFAT/MTP Safe Naming**: Sanitizes track names and automatically structures filenames as `Artist - Track Name.mp3` for perfect compatibility with Android/Windows filesystems.
- **Anti-Bot Cookie Support**: Native `cookies.txt` support to bypass YouTube extraction blocks.

---

## Requirements

- **Python 3.10+**
- **FFmpeg** (installed and available on your system `PATH`)
- Mutagen and Requests libraries

```bash
pip install mutagen requests yt-dlp
```

---

## Usage

### Simple Download
Download all tracks from the CSV to the `downloads/` directory, skipping confirmation and going straight to extraction:
```bash
python3 csv_to_mp3.py --csv playlist.csv --download --yes --no-preview
```

### Dry Run (Preview Matches)
See what YouTube videos the script will resolve and download without writing any files:
```bash
python3 csv_to_mp3.py --csv playlist.csv
```

### Advanced Options
Write to a custom folder and limit to the first 50 tracks:
```bash
python3 csv_to_mp3.py --csv playlist.csv --download --yes --no-preview --out-dir "/my/music/folder" --limit 50
```

Skip the first 100 songs (useful for manually resuming/skipping chunks):
```bash
python3 csv_to_mp3.py --csv playlist.csv --download --yes --no-preview --skip 100
```

---

## CSV Format

The script supports standard custom formats (`song` and `artist` columns) or official **Spotify Playlist Exports**:

```csv
Track Name,Artist Name(s),Album Name,Release Date,Genres,Track URI
Levitating,Dua Lipa,Future Nostalgia,2020-03-27,pop,spotify:track:3PfIrDoz19wva0Zq7V0n5w
```

*Note: For the best results, include the `Track URI` column so the script fetches 100% accurate Spotify cover art instantly.*
