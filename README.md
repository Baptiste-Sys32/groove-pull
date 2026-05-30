# csv_to_mp3

Read a CSV of songs, search YouTube with `yt-dlp`, and optionally save the
matched audio as MP3 files.

Only download media you have permission to save. This tool does not bypass
copyright law, YouTube's terms, or local restrictions.

## Requirements

- Python 3.10+
- ffmpeg available on your `PATH`
- Optional but recommended: a JavaScript runtime supported by `yt-dlp`, such as
  Deno, for more reliable YouTube extraction
- Python dependencies from `requirements.txt`

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

## CSV Format

Create a CSV with `song` and `artist` columns:

```csv
song,artist
wouldn't it be nice,the beach boys
astral plane,valerie june
```

## Usage

Preview the matches without downloading anything:

```bash
python3 csv_to_mp3.py --csv songs.csv
```

Download the previewed matches as MP3 files:

```bash
python3 csv_to_mp3.py --csv songs.csv --download
```

Skip the confirmation prompt:

```bash
python3 csv_to_mp3.py --csv songs.csv --download --yes
```

Write MP3 files to a custom directory:

```bash
python3 csv_to_mp3.py --csv songs.csv --out-dir music --download
```

Process only the first few rows:

```bash
python3 csv_to_mp3.py --csv songs.csv --limit 3
```

## Safety Notes

- The default mode is a dry run so you can inspect matched videos first.
- Downloads are written to `downloads/` unless `--out-dir` is provided.
- The script uses `yt-dlp` instead of scraping YouTube HTML directly.
- Empty CSV rows are skipped and missing required columns fail fast.
