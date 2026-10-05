#!/usr/bin/env python3
"""
yt2mp3.py — download a YouTube video OR an entire playlist as MP3 files
from the command line. Requires yt-dlp (vendored in ./vendor) and ffmpeg on PATH.

Usage:
    python yt2mp3.py <youtube-url> [options]

Examples:
    python yt2mp3.py "https://www.youtube.com/playlist?list=PLxxxxxx"
    python yt2mp3.py "https://www.youtube.com/watch?v=xxxxxxxx" -o ~/Music -q 320
    python yt2mp3.py "<playlist-url>" --start 5 --end 10   # only entries 5-10
    python yt2mp3.py "<playlist-url>" --limit 20            # cap total downloads

Notes:
    - Only download content you have the right to download (your own uploads,
      Creative Commons / public-domain material, or content you otherwise
      have permission for). Downloading copyrighted videos may violate
      YouTube's Terms of Service and copyright law depending on your use.
    - A per-run "archive" file is written to the output folder so re-running
      the same command later will skip videos already downloaded.

For a point-and-click version, run yt2mp3_gui.py instead.
"""

import argparse
import sys
from pathlib import Path

from yt2mp3_core import run_download


class ProgressPrinter:
    def __init__(self):
        self.current_title = None

    def hook(self, d):
        if d["status"] == "downloading":
            title = (d.get("info_dict") or {}).get("title", "video")
            if title != self.current_title:
                self.current_title = title
                print(f"\n  Downloading: {title}")
            pct = (d.get("_percent_str") or "").strip()
            speed = (d.get("_speed_str") or "").strip()
            eta = (d.get("_eta_str") or "").strip()
            print(f"\r  {pct} at {speed}, ETA {eta}   ", end="", flush=True)
        elif d["status"] == "finished":
            print("\r  Download complete, converting to MP3...          ")


def main():
    parser = argparse.ArgumentParser(
        description="Download a YouTube video or playlist as MP3 file(s)."
    )
    parser.add_argument("url", help="YouTube video or playlist URL")
    parser.add_argument("-o", "--output", default="./downloads",
                         help="Output directory (default: ./downloads)")
    parser.add_argument("-q", "--quality", default="192",
                         help="MP3 bitrate in kbps, e.g. 128, 192, 320 (default: 192)")
    parser.add_argument("--start", type=int, default=None,
                         help="Playlist start index (1-based, inclusive)")
    parser.add_argument("--end", type=int, default=None,
                         help="Playlist end index (1-based, inclusive)")
    parser.add_argument("--limit", type=int, default=None,
                         help="Maximum number of videos to download")
    parser.add_argument("--workers", type=int, default=1,
                         help="Number of playlist tracks to download in parallel (default: 1)")
    args = parser.parse_args()

    progress = ProgressPrinter()

    try:
        final_dir, failures = run_download(
            args.url, args.output, args.quality,
            start=args.start, end=args.end, limit=args.limit, workers=args.workers,
            progress_hook=progress.hook, log_callback=print,
        )
    except (RuntimeError, ValueError) as e:  # bad input or unreadable URL
        sys.exit(str(e))

    print("\n\nDone.")
    print(f"MP3 files saved in: {final_dir}")
    if failures:
        print(f"\n{len(failures)} item(s) failed to download:")
        for f in failures:
            print(f"  - {f}")


if __name__ == "__main__":
    main()
