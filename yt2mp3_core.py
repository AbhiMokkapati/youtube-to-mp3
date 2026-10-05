"""
yt2mp3_core.py — shared download logic used by the GUI (yt2mp3_gui.py) and
the CLI (yt2mp3.py). Requires yt-dlp (vendored in ./vendor — see the
sys.path setup below) and ffmpeg on PATH.

Only download content you have the right to download (your own uploads,
Creative Commons / public-domain material, or content you otherwise have
permission for).
"""

import re
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# yt-dlp is vendored into ./vendor (via `pip install --target vendor yt-dlp`)
# rather than relying on the normal per-user site-packages install. That
# folder (under %APPDATA%\Roaming\Python\...) turned out to be unreliable
# for this app specifically: on this machine it's silently virtualized by
# Windows for some process contexts, so a `pip install --user` done from
# one context can be invisible to a process started a different way (e.g.
# the desktop-icon launcher), producing an intermittent
# "No module named 'yt_dlp'". Vendoring next to the script sidesteps that
# entirely, since both this script and its own dependencies live in one
# real, unambiguous folder.
_vendor_dir = str(Path(__file__).with_name("vendor"))
if _vendor_dir not in sys.path:
    sys.path.insert(0, _vendor_dir)

import yt_dlp

# Local PO-token server (bgutil-ytdlp-pot-provider) that YouTube now
# effectively requires for reliable audio-stream access. See
# https://github.com/Brainicism/bgutil-ytdlp-pot-provider
POT_SERVER_DIR = Path.home() / "bgutil-ytdlp-pot-provider" / "server"
POT_SERVER_URL = "http://127.0.0.1:4416/ping"


def _pot_server_alive(timeout=1.0) -> bool:
    try:
        with urllib.request.urlopen(POT_SERVER_URL, timeout=timeout):
            return True
    except Exception:
        return False


def ensure_pot_server(log_callback=None):
    """Start the local PO-token server if it isn't already running."""
    def log(msg):
        if log_callback:
            log_callback(msg)

    if _pot_server_alive():
        return
    build_main = POT_SERVER_DIR / "build" / "main.js"
    if not build_main.exists():
        log("Note: PO-token server not installed; some YouTube audio streams may 403.")
        return

    log("Starting local PO-token server (bgutil)...")
    subprocess.Popen(
        ["node", str(build_main)],
        cwd=str(POT_SERVER_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    for _ in range(20):
        if _pot_server_alive():
            log("PO-token server is up.")
            return
        time.sleep(0.5)
    log("Warning: PO-token server did not come up in time.")


_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL",
                   *(f"COM{i}" for i in range(1, 10)),
                   *(f"LPT{i}" for i in range(1, 10))}


def sanitize_filename(name: str) -> str:
    """Make a string safe to use as a single folder name.

    Strips path separators, control characters, Windows-illegal characters,
    leading/trailing dots and spaces (so ".." can never traverse out of the
    output directory), reserved device names, and caps the length.
    """
    name = re.sub(r'[\\/*?:"<>|\x00-\x1f]', "_", name or "")
    name = name.strip(" .")[:120].rstrip(" .")
    if not name:
        return "downloads"
    if name.split(".")[0].upper() in _RESERVED_NAMES:
        return f"_{name}"
    return name


def validate_url(url: str) -> str:
    """Accept only http(s) URLs (blocks file:// and other local schemes)."""
    url = (url or "").strip()
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Please enter a full http(s) URL.")
    return url


def validate_quality(quality) -> str:
    """MP3 bitrate must be a plain number of kbps (passed through to ffmpeg)."""
    q = str(quality).strip()
    if not (q.isdigit() and 32 <= int(q) <= 320):
        raise ValueError("Quality must be a bitrate between 32 and 320 kbps.")
    return q


def validate_range(start=None, end=None, limit=None):
    """Playlist start/end/limit must each be None or a whole number >= 1."""
    for label, val in (("start", start), ("end", end), ("limit", limit)):
        if val is not None and (isinstance(val, bool) or not isinstance(val, int) or val < 1):
            raise ValueError(f"{label} must be a whole number of 1 or more.")
    if start is not None and end is not None and end < start:
        raise ValueError("end must not be less than start.")


def escape_template(text: str) -> str:
    """Escape '%' so yt-dlp doesn't treat part of a path as an output template.

    Folder names come from remote playlist titles (and the user's own paths),
    so a literal '%(...)s' there must not be expanded.
    """
    return str(text).replace("%", "%%")


class DownloadCancelled(Exception):
    pass


def build_opts(output_dir: Path, quality: str, archive_path: Path,
                start, end, limit, progress_hook, logger, is_playlist: bool,
                outtmpl: str = None):
    if outtmpl is None:
        if is_playlist:
            outtmpl = escape_template(output_dir) + "/%(playlist_index)02d - %(title)s.%(ext)s"
        else:
            outtmpl = escape_template(output_dir) + "/%(title)s.%(ext)s"

    opts = {
        "format": "bestaudio/best",
        "outtmpl": {"default": outtmpl},
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": quality,
            },
            {"key": "FFmpegMetadata", "add_metadata": True},
            {"key": "EmbedThumbnail"},
        ],
        "writethumbnail": True,
        "ignoreerrors": True,
        "download_archive": str(archive_path),
        "progress_hooks": [progress_hook],
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": logger,
        # YouTube now requires solving a JS/PO-token challenge for most
        # clients; "web_music" plus a JS runtime + the bgutil PO token
        # server (see README) reliably avoids HTTP 403s on audio streams.
        "js_runtimes": {"node": {}},
        "remote_components": ["ejs:github"],
        "extractor_args": {"youtube": {"player_client": ["web_music"]}},
    }

    if start is not None:
        opts["playliststart"] = start
    if end is not None:
        opts["playlistend"] = end
    if limit is not None:
        # playlistend caps the *index*, not the count; combine sensibly with start.
        first = start or 1
        capped_end = first + limit - 1
        opts["playlistend"] = capped_end if end is None else min(end, capped_end)

    return opts


def probe(url: str):
    """Fetch metadata (flat, no download) to determine if this is a playlist."""
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "extract_flat": True}) as ydl:
        return ydl.extract_info(url, download=False)


def run_download(url: str, output_dir: Path, quality: str, start=None, end=None,
                  limit=None, workers=1, progress_hook=None, log_callback=None,
                  cancel_check=None):
    """
    Download `url` (video or playlist) as MP3(s) into output_dir.

    progress_hook(d): called with yt-dlp's raw progress dict on each update.
        May be called from multiple threads at once when workers > 1.
    log_callback(msg): called with human-readable log lines. May also be
        called from multiple threads at once.
    cancel_check(): called periodically; if it returns True, raises DownloadCancelled.
    workers: for playlists, how many videos to download concurrently (1-3
        recommended; higher values are more likely to trigger YouTube
        rate-limiting).

    Returns (final_output_dir, failures: list[str]).
    """
    url = validate_url(url)
    quality = validate_quality(quality)
    validate_range(start, end, limit)
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    def log(msg):
        if log_callback:
            log_callback(msg)

    ensure_pot_server(log_callback=log)

    log(f"Fetching info for: {url}")
    try:
        info = probe(url)
    except Exception as e:
        raise RuntimeError(f"Could not read this URL: {e}") from e

    is_playlist = bool(info.get("entries")) and info.get("_type") == "playlist"

    if is_playlist:
        title = sanitize_filename(info.get("title") or "playlist")
        output_dir = output_dir / title
        output_dir.mkdir(parents=True, exist_ok=True)
        entry_count = len(list(info.get("entries") or []))
        log(f"Playlist detected: '{info.get('title')}' ({entry_count} videos)")
    else:
        log(f"Single video detected: '{info.get('title')}'")

    log(f"Saving to: {output_dir}")
    archive_path = output_dir / ".downloaded_archive.txt"

    failures = []
    failures_lock = threading.Lock()

    class TrackingLogger:
        def debug(self, msg):
            if msg.startswith("[") and log_callback:
                log_callback(msg)

        def warning(self, msg):
            log(f"WARNING: {msg}")

        def error(self, msg):
            with failures_lock:
                failures.append(msg)
            log(f"ERROR: {msg}")

    def hook(d):
        if cancel_check and cancel_check():
            raise DownloadCancelled()
        if progress_hook:
            progress_hook(d)

    workers = min(max(1, int(workers or 1)), 3)

    if is_playlist and workers > 1:
        entries = list(info.get("entries") or [])
        first = start or 1
        last = len(entries)
        if limit is not None:
            last = min(last, first + limit - 1)
        if end is not None:
            last = min(last, end)
        selected = [(i, e) for i, e in enumerate(entries, start=1)
                    if first <= i <= last and e]

        log(f"Downloading {len(selected)} track(s) with {workers} parallel worker(s)...")

        cancelled = threading.Event()

        def download_one(index, entry):
            if cancel_check and cancel_check():
                cancelled.set()
                return
            video_url = entry.get("url") or entry.get("webpage_url") or entry.get("id")
            if entry.get("id") and not str(video_url).startswith("http"):
                video_url = f"https://www.youtube.com/watch?v={entry['id']}"
            outtmpl = escape_template(output_dir) + f"/{index:02d} - %(title)s.%(ext)s"
            opts = build_opts(output_dir, quality, archive_path, None, None, None,
                               hook, TrackingLogger(), is_playlist=False, outtmpl=outtmpl)
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([video_url])
            except DownloadCancelled:
                cancelled.set()
            except Exception as e:
                with failures_lock:
                    failures.append(str(e))
                log(f"ERROR: {e}")

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(download_one, i, e) for i, e in selected]
            for fut in as_completed(futures):
                fut.result()

        if cancelled.is_set():
            raise DownloadCancelled()
    else:
        opts = build_opts(output_dir, quality, archive_path, start, end, limit,
                           hook, TrackingLogger(), is_playlist)
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

    # With ignoreerrors on, yt-dlp can swallow the exception our progress hook
    # raises to cancel, so honour the cancel request explicitly here.
    if cancel_check and cancel_check():
        raise DownloadCancelled()

    return output_dir, failures
