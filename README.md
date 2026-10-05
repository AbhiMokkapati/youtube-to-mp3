# YouTube to MP3

Small Windows desktop GUI (Tkinter) and CLI that download a YouTube video or
playlist as MP3 using [yt-dlp](https://github.com/yt-dlp/yt-dlp) and ffmpeg.
Only download content you have the right to download.

## Setup

1. Python 3.10+ (with Tkinter) and [ffmpeg](https://ffmpeg.org/) on `PATH`.
2. Install yt-dlp into the (gitignored) `vendor/` folder the app loads from:

       python -m pip install --target vendor --upgrade -r requirements.txt

3. Optional: Node.js, used by yt-dlp to solve YouTube's JS challenges. The app
   also asks yt-dlp to fetch its challenge-solver component from GitHub
   (`remote_components: ejs:github`), i.e. it runs remotely sourced JS in node.
   Optionally install [bgutil-ytdlp-pot-provider](https://github.com/Brainicism/bgutil-ytdlp-pot-provider)
   to `~/bgutil-ytdlp-pot-provider`; the app starts its server automatically.

## Run

- GUI: `pythonw yt2mp3_gui.py` (or `Launch YT to MP3.vbs`, which assumes
  `C:\Python314\pythonw.exe` - edit the path if yours differs).
- CLI: `python yt2mp3.py <url> [-o DIR] [-q 192] [--start N --end M --limit N --workers 1-3]`

Tests: `python -m unittest discover tests`

No license has been chosen; all rights reserved by default.
