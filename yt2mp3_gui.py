#!/usr/bin/env python3
"""
yt2mp3_gui.py — simple desktop GUI for downloading a YouTube video or
playlist as MP3 file(s), built on yt2mp3_core.py (yt-dlp + ffmpeg).

Launch by double-clicking "Launch YT to MP3.vbs" on the Desktop, or run:
    pythonw yt2mp3_gui.py
"""

import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    from yt2mp3_core import DownloadCancelled, run_download, validate_url
except ImportError as e:
    diag_path = Path(__file__).with_name("launch_diagnostics.log")
    vendor_dir = Path(__file__).with_name("vendor")
    diag = [
        f"error: {e}",
        f"sys.executable: {sys.executable}",
        f"sys.version: {sys.version}",
        f"vendor dir: {vendor_dir} (exists: {vendor_dir.is_dir()})",
        "sys.path:",
        *[f"  {p}" for p in sys.path],
    ]
    diag_path.write_text("\n".join(diag), encoding="utf-8")

    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "YouTube to MP3 — missing dependency",
        f"Could not start: {e}\n\n"
        f"This usually means the bundled 'vendor' folder next to this "
        f"script is missing or incomplete.\n\n"
        f"To reinstall it, run this in a command prompt:\n"
        f'    cd "{Path(__file__).parent}"\n'
        f'    "{sys.executable}" -m pip install --target vendor --upgrade yt-dlp\n\n'
        f"Diagnostics written to launch_diagnostics.log",
    )
    raise


class YT2MP3App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("YouTube to MP3")
        self.geometry("640x520")
        self.minsize(560, 460)
        try:
            self.iconbitmap(str(Path(__file__).with_name("icon.ico")))
        except tk.TclError:
            pass

        self.output_dir = tk.StringVar(value=str(Path.home() / "Music" / "yt2mp3"))
        self.quality = tk.StringVar(value="192")
        self.workers = tk.StringVar(value="2")
        self.status_text = tk.StringVar(value="Ready.")

        self.msg_queue = queue.Queue()
        self.cancel_flag = threading.Event()
        self.worker = None

        self._build_ui()
        self.after(100, self._poll_queue)

    # ---------- UI ----------
    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        frm_url = ttk.Frame(self)
        frm_url.pack(fill="x", **pad)
        ttk.Label(frm_url, text="YouTube video or playlist URL:").pack(anchor="w")
        self.url_entry = ttk.Entry(frm_url, font=("Segoe UI", 10))
        self.url_entry.pack(fill="x", pady=(2, 0))
        self.url_entry.focus_set()

        frm_opts = ttk.Frame(self)
        frm_opts.pack(fill="x", **pad)

        ttk.Label(frm_opts, text="Save to:").grid(row=0, column=0, sticky="w")
        out_entry = ttk.Entry(frm_opts, textvariable=self.output_dir)
        out_entry.grid(row=0, column=1, sticky="ew", padx=(6, 6))
        ttk.Button(frm_opts, text="Browse...", command=self._browse).grid(row=0, column=2)

        ttk.Label(frm_opts, text="Quality (kbps):").grid(row=1, column=0, sticky="w", pady=(8, 0))
        quality_combo = ttk.Combobox(
            frm_opts, textvariable=self.quality, values=["128", "192", "256", "320"],
            width=8, state="readonly",
        )
        quality_combo.grid(row=1, column=1, sticky="w", pady=(8, 0))

        ttk.Label(frm_opts, text="Parallel downloads:").grid(row=2, column=0, sticky="w", pady=(8, 0))
        workers_combo = ttk.Combobox(
            frm_opts, textvariable=self.workers, values=["1", "2", "3"],
            width=8, state="readonly",
        )
        workers_combo.grid(row=2, column=1, sticky="w", pady=(8, 0))

        frm_opts.columnconfigure(1, weight=1)

        frm_range = ttk.Frame(self)
        frm_range.pack(fill="x", **pad)
        ttk.Label(frm_range, text="Playlist range (optional):").grid(row=0, column=0, columnspan=6, sticky="w")
        ttk.Label(frm_range, text="Start:").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.start_entry = ttk.Entry(frm_range, width=6)
        self.start_entry.grid(row=1, column=1, sticky="w", padx=(4, 16), pady=(4, 0))
        ttk.Label(frm_range, text="End:").grid(row=1, column=2, sticky="w", pady=(4, 0))
        self.end_entry = ttk.Entry(frm_range, width=6)
        self.end_entry.grid(row=1, column=3, sticky="w", padx=(4, 16), pady=(4, 0))
        ttk.Label(frm_range, text="Limit:").grid(row=1, column=4, sticky="w", pady=(4, 0))
        self.limit_entry = ttk.Entry(frm_range, width=6)
        self.limit_entry.grid(row=1, column=5, sticky="w", padx=(4, 0), pady=(4, 0))

        frm_buttons = ttk.Frame(self)
        frm_buttons.pack(fill="x", **pad)
        self.start_btn = ttk.Button(frm_buttons, text="Download", command=self._start_download)
        self.start_btn.pack(side="left")
        self.cancel_btn = ttk.Button(frm_buttons, text="Cancel", command=self._cancel_download, state="disabled")
        self.cancel_btn.pack(side="left", padx=(8, 0))
        ttk.Button(frm_buttons, text="Open folder", command=self._open_output_folder).pack(side="left", padx=(8, 0))

        frm_progress = ttk.Frame(self)
        frm_progress.pack(fill="x", **pad)
        self.progress = ttk.Progressbar(frm_progress, mode="determinate", maximum=100)
        self.progress.pack(fill="x")
        ttk.Label(frm_progress, textvariable=self.status_text).pack(anchor="w", pady=(4, 0))

        frm_log = ttk.Frame(self)
        frm_log.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log_box = tk.Text(frm_log, height=12, wrap="word", state="disabled",
                                font=("Consolas", 10), bg="#111", fg="#ddd")
        scroll = ttk.Scrollbar(frm_log, command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=scroll.set)
        self.log_box.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _browse(self):
        chosen = filedialog.askdirectory(initialdir=self.output_dir.get() or str(Path.home()))
        if chosen:
            self.output_dir.set(chosen)

    def _open_output_folder(self):
        path = Path(self.output_dir.get()).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    def _log(self, msg: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg.rstrip("\n") + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    # ---------- download control ----------
    def _parse_int(self, entry: ttk.Entry):
        return self._parse_int_str(entry.get())

    def _parse_int_str(self, val: str):
        val = (val or "").strip()
        if not val:
            return None
        try:
            return int(val)
        except ValueError:
            return None

    def _start_download(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Please paste a YouTube video or playlist URL.")
            return
        if self.worker and self.worker.is_alive():
            return

        out_dir = self.output_dir.get().strip() or str(Path.home() / "Music" / "yt2mp3")
        quality = self.quality.get()
        workers = self._parse_int_str(self.workers.get()) or 1
        start = self._parse_int(self.start_entry)
        end = self._parse_int(self.end_entry)
        limit = self._parse_int(self.limit_entry)
        for label, entry, val in (("Start", self.start_entry, start),
                                  ("End", self.end_entry, end),
                                  ("Limit", self.limit_entry, limit)):
            if entry.get().strip() and (val is None or val < 1):
                messagebox.showwarning("Invalid range", f"{label} must be a whole number of 1 or more.")
                return
        try:
            validate_url(url)
        except ValueError as e:
            messagebox.showwarning("Invalid URL", str(e))
            return

        self.cancel_flag.clear()
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self.progress.configure(value=0)
        self.status_text.set("Starting...")
        self.start_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")

        self.worker = threading.Thread(
            target=self._download_worker,
            args=(url, out_dir, quality, start, end, limit, workers),
            daemon=True,
        )
        self.worker.start()

    def _cancel_download(self):
        self.cancel_flag.set()
        self.status_text.set("Cancelling...")
        self.cancel_btn.configure(state="disabled")

    def _download_worker(self, url, out_dir, quality, start, end, limit, workers):
        def progress_hook(d):
            if d["status"] == "downloading":
                pct_str = (d.get("_percent_str") or "0%").strip().rstrip("%")
                try:
                    pct = float(pct_str)
                except ValueError:
                    pct = 0.0
                title = (d.get("info_dict") or {}).get("title", "video")
                speed = (d.get("_speed_str") or "").strip()
                eta = (d.get("_eta_str") or "").strip()
                self.msg_queue.put(("progress", pct, f"Downloading '{title}' — {pct_str}% at {speed}, ETA {eta}"))
            elif d["status"] == "finished":
                self.msg_queue.put(("progress", 100, "Converting to MP3..."))
            elif d["status"] == "error":
                self.msg_queue.put(("log", "Error downloading this item.", None))

        def log_callback(msg):
            self.msg_queue.put(("log", msg, None))

        def cancel_check():
            return self.cancel_flag.is_set()

        try:
            final_dir, failures = run_download(
                url, out_dir, quality, start=start, end=end, limit=limit,
                workers=workers, progress_hook=progress_hook, log_callback=log_callback,
                cancel_check=cancel_check,
            )
            self.msg_queue.put(("done", str(final_dir), failures))
        except DownloadCancelled:
            self.msg_queue.put(("cancelled", None, None))
        except Exception as e:
            self.msg_queue.put(("error", str(e), None))

    # ---------- queue polling (keeps Tk on the main thread) ----------
    def _poll_queue(self):
        try:
            while True:
                kind, a, b = self.msg_queue.get_nowait()
                if kind == "progress":
                    self.progress.configure(value=a)
                    self.status_text.set(b)
                elif kind == "log":
                    self._log(a)
                elif kind == "done":
                    self.progress.configure(value=100)
                    self.status_text.set("Done.")
                    self._log(f"\nDone. MP3 files saved in: {a}")
                    if b:
                        self._log(f"{len(b)} item(s) failed:")
                        for f in b:
                            self._log(f"  - {f}")
                    self._finish()
                elif kind == "cancelled":
                    self.status_text.set("Cancelled.")
                    self._log("\nCancelled by user.")
                    self._finish()
                elif kind == "error":
                    self.status_text.set("Error.")
                    self._log(f"\nERROR: {a}")
                    messagebox.showerror("Download failed", a)
                    self._finish()
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _finish(self):
        self.start_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")


if __name__ == "__main__":
    app = YT2MP3App()
    app.mainloop()
