import ctypes
import io
import os
import re
import sys
import time
import threading
import uuid
import tkinter as tk
from tkinter import ttk, messagebox
from urllib.parse import urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None


def resource_path(*parts):
    """Resolve a bundled resource path, working both from source and from a
    PyInstaller --onefile build (where data files are unpacked to a temp
    dir referenced by sys._MEIPASS)."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


TICK_MS = 100
DEFAULT_RUNTIME = 2 * 60 * 60
DEFAULT_WARNING_SECONDS = 20
MIN_WARNING_SECONDS = 1
MAX_WARNING_SECONDS = 600
DEFAULT_DUCK_PERCENT = 15
DEFAULT_RESTORE_SECONDS = 10
MAX_RESTORE_SECONDS = 600
VOLUME_RESTORE_RAMP_SECONDS = 5.0

# Chime note patterns as (frequency Hz, duration ms).
# Minor = short rising "ding-ding", Major = slightly longer happy arpeggio.
CHIME_NOTE_GAP = 0.055
CHIME_MINOR = [
    (523, 80),   # C5
    (659, 80),   # E5
    (784, 80),   # G5
    (1047, 100),  # C6
]
CHIME_MAJOR = CHIME_MINOR + [
    (784, 80),   # G5
    (659, 80),   # E5
    (523, 100),   # C5
]

# Modern dark palette
BG = "#131414"
PANEL = "#232425"
PANEL_2 = "#252525"
BORDER = "#25314a"
SETTINGS_BORDER = "#34405a"
TEXT = "#edf2ff"
MUTED = "#9aa9c2"
ACCENT = "#416fb4"
ACCENT_HOVER = "#6887b4"
MAJOR = "#ff5d73"
MINOR = "#ffb454"
SUCCESS = "#55d6a6"
SUCCESS_HOVER = "#7fe3bd"
TRACK = "#33405b"


def hms_to_seconds(value: str) -> int:
    parts = [int(x) for x in value.strip().split(":")]
    if len(parts) != 3:
        raise ValueError(f"Invalid timestamp: {value}")
    h, m, s = parts
    return h * 3600 + m * 60 + s


def seconds_to_hms(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def scrape_notscare(url: str):
    if requests is None or BeautifulSoup is None:
        raise RuntimeError(
            "Missing dependencies. Run:\n\n"
            "    py -m pip install requests beautifulsoup4 pillow"
        )

    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if host != "notscare.me" and not host.endswith(".notscare.me"):
        raise ValueError("Please enter a notscare.me movie URL.")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/152 Safari/537.36"
        )
    }

    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text("\n", strip=True)

    title = "NotScare Movie"
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(" ", strip=True)
        title = re.sub(r"\s*-\s*Jumpscare Guide\s*$", "", title, flags=re.I)

    runtime = None
    runtime_match = re.search(
        r"\b(?:19|20)\d{2}\s+(\d{1,2}:\d{2}:\d{2})\b.*?\bJumpscares?\b",
        text,
        flags=re.I | re.S,
    )
    if runtime_match:
        runtime = hms_to_seconds(runtime_match.group(1))

    # Try OpenGraph first, then use the first TMDB image that looks like the movie poster.
    poster_url = None
    og_image = soup.find("meta", attrs={"property": "og:image"})
    if og_image and og_image.get("content"):
        candidate = og_image.get("content").strip()
        if candidate.startswith("http"):
            poster_url = candidate

    if not poster_url:
        title_key = re.sub(r"\s*\(\d{4}\)\s*$", "", title).strip().lower()
        tmdb_candidates = []
        for img in soup.find_all("img"):
            src = (img.get("src") or img.get("data-src") or "").strip()
            alt = (img.get("alt") or "").strip().lower()
            if "image.tmdb.org" in src:
                score = 0
                if title_key and title_key in alt:
                    score += 10
                if "/w500/" in src or "/w342/" in src:
                    score += 3
                tmdb_candidates.append((score, src))
        if tmdb_candidates:
            tmdb_candidates.sort(key=lambda x: x[0], reverse=True)
            poster_url = tmdb_candidates[0][1]

    details_match = re.search(r"Jumpscare Details(.*)", text, flags=re.I | re.S)
    details = details_match.group(1) if details_match else text

    stamp_re = re.compile(r"(?m)^\s*(\d{2}:\d{2}:\d{2})\s*$")
    matches = list(stamp_re.finditer(details))

    scares = []
    seen = set()
    for i, match in enumerate(matches):
        stamp = match.group(1)
        if stamp in seen:
            continue

        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(details)
        block = details[start:end].strip()

        severity_match = re.search(r"\b(Major|Minor)\b", block, flags=re.I)
        if not severity_match:
            continue

        severity = severity_match.group(1).title()
        desc = block[severity_match.end():].strip()
        desc = re.split(
            r"\n(?:Jump to|Report|Submitted by:|Add Jumpscare)\b",
            desc,
            maxsplit=1,
            flags=re.I,
        )[0].strip()
        desc = re.sub(r"\s+", " ", desc)
        if len(desc) > 190:
            desc = desc[:187] + "..."

        sec = hms_to_seconds(stamp)
        scares.append(
            {
                "time": sec,
                "timestamp": stamp,
                "severity": severity,
                "description": desc,
            }
        )
        seen.add(stamp)

    scares.sort(key=lambda x: x["time"])
    if not scares:
        raise RuntimeError(
            "No jump-scare timestamps were found. The site's page structure may have changed."
        )

    if runtime is None:
        runtime = max(DEFAULT_RUNTIME, scares[-1]["time"] + 60)

    poster_bytes = None
    if poster_url:
        try:
            poster_response = requests.get(poster_url, headers=headers, timeout=15)
            poster_response.raise_for_status()
            poster_bytes = poster_response.content
        except requests.RequestException:
            poster_bytes = None

    return {
        "title": title,
        "runtime": runtime,
        "scares": scares,
        "poster_url": poster_url,
        "poster_bytes": poster_bytes,
    }


def enable_windows_dark_title_bar(window):
    """Ask Windows to use a dark native title bar/border when supported."""
    if not sys.platform.startswith("win"):
        return

    try:
        import ctypes

        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())

        # DWMWA_USE_IMMERSIVE_DARK_MODE:
        # 20 on current Windows 10/11 builds, 19 on some older Windows 10 builds.
        value = ctypes.c_int(1)
        for attribute in (20, 19):
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                attribute,
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
            if result == 0:
                break

        # Also request a dark caption/border color where supported.
        # COLORREF is 0x00BBGGRR.
        dark_caption = ctypes.c_int(0x000d0d0e)
        dark_border = ctypes.c_int(0x00171718)

        # DWMWA_CAPTION_COLOR = 35, DWMWA_BORDER_COLOR = 34
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 35, ctypes.byref(dark_caption), ctypes.sizeof(dark_caption)
        )
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 34, ctypes.byref(dark_border), ctypes.sizeof(dark_border)
        )
    except Exception:
        # The app should still run normally if the Windows API call is unavailable.
        pass


class WindowsMasterVolume:
    """Tiny ctypes wrapper around the Windows Core Audio master volume.

    Avoids extra dependencies (pycaw/comtypes). Each call looks up the current
    default output device, so switching to headphones mid-movie still works.
    Call from the Tk main thread only (COM is initialized there).
    """

    CLSID_MMDEVICE_ENUMERATOR = "BCDE0395-E52F-467C-8E3D-C4579291692E"
    IID_IMMDEVICE_ENUMERATOR = "A95664D2-9614-4F35-A746-DE8DB63617E6"
    IID_IAUDIO_ENDPOINT_VOLUME = "5CDF2C82-841E-4546-9722-0CF74078229A"
    CLSCTX_ALL = 23
    COINIT_APARTMENTTHREADED = 2

    def __init__(self):
        if not sys.platform.startswith("win"):
            raise OSError("System volume control is only supported on Windows.")
        # S_FALSE / RPC_E_CHANGED_MODE just mean COM is already initialized here.
        ctypes.windll.ole32.CoInitializeEx(None, self.COINIT_APARTMENTTHREADED)
        self.get()  # Fail early if there is no usable output device.

    @staticmethod
    def _guid(text):
        return (ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID(text).bytes_le)

    @staticmethod
    def _method(obj, index, restype, *argtypes):
        vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        func = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtable[index])
        return lambda *args: func(obj, *args)

    def _with_endpoint(self, action):
        enumerator = ctypes.c_void_p()
        device = ctypes.c_void_p()
        endpoint = ctypes.c_void_p()
        try:
            hr = ctypes.windll.ole32.CoCreateInstance(
                ctypes.byref(self._guid(self.CLSID_MMDEVICE_ENUMERATOR)),
                None,
                self.CLSCTX_ALL,
                ctypes.byref(self._guid(self.IID_IMMDEVICE_ENUMERATOR)),
                ctypes.byref(enumerator),
            )
            if hr < 0:
                raise OSError(f"CoCreateInstance failed (0x{hr & 0xFFFFFFFF:08X})")

            # IMMDeviceEnumerator::GetDefaultAudioEndpoint(eRender, eConsole, &device)
            self._method(enumerator, 4, ctypes.HRESULT, ctypes.c_int, ctypes.c_int,
                         ctypes.POINTER(ctypes.c_void_p))(0, 0, ctypes.byref(device))

            # IMMDevice::Activate(IID_IAudioEndpointVolume, CLSCTX_ALL, NULL, &endpoint)
            self._method(device, 3, ctypes.HRESULT, ctypes.c_void_p, ctypes.c_ulong,
                         ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(
                ctypes.byref(self._guid(self.IID_IAUDIO_ENDPOINT_VOLUME)),
                self.CLSCTX_ALL,
                None,
                ctypes.byref(endpoint),
            )
            return action(endpoint)
        finally:
            for obj in (endpoint, device, enumerator):
                if obj:
                    self._method(obj, 2, ctypes.c_ulong)()  # IUnknown::Release

    def get(self):
        """Return the master volume as a 0.0-1.0 scalar."""
        def action(endpoint):
            level = ctypes.c_float()
            # IAudioEndpointVolume::GetMasterVolumeLevelScalar
            self._method(endpoint, 9, ctypes.HRESULT, ctypes.POINTER(ctypes.c_float))(
                ctypes.byref(level)
            )
            return level.value

        return self._with_endpoint(action)

    def set(self, level):
        """Set the master volume from a 0.0-1.0 scalar."""
        level = max(0.0, min(1.0, float(level)))
        # IAudioEndpointVolume::SetMasterVolumeLevelScalar
        self._with_endpoint(
            lambda endpoint: self._method(
                endpoint, 7, ctypes.HRESULT, ctypes.c_float, ctypes.c_void_p
            )(level, None)
        )


class JumpScareApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Spooky Lite - NotScare Companion")
        self.geometry("1180x780")
        self.minsize(940, 650)
        self.configure(bg=BG)
        self._set_app_icon()

        self.movie_title = ""
        self.duration = DEFAULT_RUNTIME
        self.scares = []
        self.position = 0.0
        self.playing = False
        self.last_tick = None
        self.warned = set()
        self.warning_seconds = DEFAULT_WARNING_SECONDS
        self.active_warning_index = None
        self.warning_overlay_dismissed = False
        self.poster_photo = None

        self.duck_percent = DEFAULT_DUCK_PERCENT
        self.restore_seconds = DEFAULT_RESTORE_SECONDS
        self.volume_ducked = False
        self.saved_volume = None
        self.duck_hold_until = 0.0  # Let the chime finish at full volume before ducking.
        self.ramp_active = False
        self.ramp_start_time = 0.0
        self.ramp_start_volume = 0.0
        self.ramp_target_volume = 0.0
        try:
            self.volume = WindowsMasterVolume()
        except Exception:
            self.volume = None

        self.timeline_left = 34
        self.timeline_right = 34
        self.timeline_y = 72
        self.timeline_marker_info = []

        self.url_var = tk.StringVar(
            value="https://notscare.me/movies/jump-scares-in-weapons-2025"
        )
        self.warning_seconds_var = tk.StringVar(value=str(DEFAULT_WARNING_SECONDS))
        self.duck_percent_var = tk.StringVar(value=str(DEFAULT_DUCK_PERCENT))
        self.restore_seconds_var = tk.StringVar(value=str(DEFAULT_RESTORE_SECONDS))
        self.time_var = tk.StringVar(value="00:00:00 / 02:00:00")
        self.status_var = tk.StringVar(value="Paste a NotScare movie URL and load it.")
        self.next_var = tk.StringVar(value="Next scare  —")

        self._setup_style()
        self._build_ui()
        self.bind("<Escape>", lambda _e: self.dismiss_warning_overlay())
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(TICK_MS, self._tick)

    def on_close(self):
        self.restore_volume()
        self.destroy()

    def _setup_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("Panel2.TFrame", background=PANEL_2)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        style.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
        style.configure("PanelMuted.TLabel", background=PANEL, foreground=MUTED)
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Segoe UI Semibold", 21))
        style.configure("Clock.TLabel", background=BG, foreground=ACCENT, font=("Consolas", 15, "bold"))

        style.configure(
            "TButton",
            background=PANEL_2,
            foreground=TEXT,
            borderwidth=0,
            focusthickness=0,
            padding=(14, 9),
            font=("Segoe UI Semibold", 10),
        )
        style.map("TButton", background=[("active", BORDER), ("pressed", ACCENT)])

        style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground="#071120",
            padding=(16, 9),
            font=("Segoe UI Semibold", 10),
        )
        style.map("Accent.TButton", background=[("active", ACCENT_HOVER)])

        # Play/pause toggle: green while stopped, blue while the timer is rolling.
        style.configure(
            "Play.TButton",
            background=SUCCESS,
            foreground="#06130e",
            padding=(16, 9),
            font=("Segoe UI Semibold", 10),
        )
        style.map("Play.TButton", background=[("active", SUCCESS_HOVER)])
        style.configure(
            "Pause.TButton",
            background=ACCENT,
            foreground=TEXT,
            padding=(16, 9),
            font=("Segoe UI Semibold", 10),
        )
        style.map("Pause.TButton", background=[("active", ACCENT_HOVER)])

        style.configure(
            "TEntry",
            fieldbackground=PANEL_2,
            foreground=TEXT,
            insertcolor=TEXT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=8,
        )

        # Compact entries for the settings card, with an accent border on focus.
        style.configure(
            "Setting.TEntry",
            fieldbackground=BG,
            foreground=TEXT,
            insertcolor=TEXT,
            bordercolor=SETTINGS_BORDER,
            lightcolor=SETTINGS_BORDER,
            darkcolor=SETTINGS_BORDER,
            padding=(4, 3),
        )
        style.map(
            "Setting.TEntry",
            bordercolor=[("focus", ACCENT)],
            lightcolor=[("focus", ACCENT)],
            fieldbackground=[("disabled", PANEL)],
            foreground=[("disabled", MUTED)],
        )
        style.configure(
            "SettingTag.TLabel",
            background=PANEL,
            foreground=ACCENT,
            font=("Segoe UI Semibold", 8),
        )

        style.configure(
            "Treeview",
            background=PANEL,
            fieldbackground=PANEL,
            foreground=TEXT,
            rowheight=30,
            borderwidth=0,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Treeview.Heading",
            background=PANEL_2,
            foreground=MUTED,
            relief="flat",
            font=("Segoe UI Semibold", 9),
        )
        style.map("Treeview", background=[("selected", "#24456f")])
        style.map("Treeview.Heading", background=[("active", BORDER)])

    def _set_app_icon(self):
        """Set the window/taskbar icon to the cartoon ghost in assets/.
        Best-effort: missing assets or an unsupported platform just falls
        back to Tk's default icon instead of crashing the app."""
        ico_path = resource_path("assets", "icon.ico")
        try:
            self.iconbitmap(ico_path)
            return
        except Exception:
            pass
        png_path = resource_path("assets", "icon.png")
        if Image is not None and ImageTk is not None:
            try:
                self._app_icon_img = ImageTk.PhotoImage(Image.open(png_path))
                self.iconphoto(True, self._app_icon_img)
            except Exception:
                pass

    def _build_ui(self):
        self.main = ttk.Frame(self, padding=(18, 16))
        self.main.pack(fill="both", expand=True)

        top = ttk.Frame(self.main)
        top.pack(fill="x")

        brand = ttk.Frame(top)
        brand.pack(side="left", fill="x", expand=True)
        ttk.Label(brand, text="Spooky Lite - NOTSCARE COMPANION", foreground=ACCENT,
                  font=("Segoe UI Semibold", 10)).pack(anchor="w")
        ttk.Label(brand, text="Jump-scare warning timer", style="Title.TLabel").pack(anchor="w")

        # Settings card: a bordered panel with one labelled row per setting group.
        settings = tk.Frame(top, bg=PANEL, highlightthickness=1, highlightbackground=SETTINGS_BORDER)
        settings.pack(side="right", padx=(16, 0))
        settings_body = ttk.Frame(settings, style="Panel.TFrame", padding=(14, 8))
        settings_body.pack()

        def setting_entry(parent, var, command):
            entry = ttk.Entry(
                parent,
                textvariable=var,
                width=4,
                justify="center",
                style="Setting.TEntry",
                font=("Segoe UI Semibold", 10),
            )
            entry.bind("<Return>", command)
            entry.bind("<FocusOut>", command)
            return entry

        def setting_row(row, tag, parts):
            ttk.Label(settings_body, text=tag, style="SettingTag.TLabel").grid(
                row=row, column=0, sticky="w", padx=(0, 16)
            )
            line = ttk.Frame(settings_body, style="Panel.TFrame")
            line.grid(row=row, column=1, sticky="w")
            for i, part in enumerate(parts):
                if isinstance(part, str):
                    widget = ttk.Label(line, text=part, style="PanelMuted.TLabel")
                else:
                    widget = setting_entry(line, *part)
                widget.pack(side="left", padx=(0 if i == 0 else 6, 0))
            return line

        setting_row(0, "ALERT", [
            "Warn me",
            (self.warning_seconds_var, self.commit_warning_seconds),
            "seconds before",
        ])
        tk.Frame(settings_body, bg=SETTINGS_BORDER, height=1).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=7
        )
        volume_line = setting_row(2, "VOLUME", [
            "Drop to",
            (self.duck_percent_var, self.commit_duck_percent),
            "% until",
            (self.restore_seconds_var, self.commit_restore_seconds),
            "seconds after",
        ])
        if self.volume is None:
            for child in volume_line.winfo_children():
                if isinstance(child, ttk.Entry):
                    child.state(["disabled"])
            ttk.Label(volume_line, text="(unavailable)", style="PanelMuted.TLabel").pack(side="left", padx=(6, 0))

        url_panel = ttk.Frame(self.main, style="Panel.TFrame", padding=12)
        url_panel.pack(fill="x", pady=(16, 12))

        self.url_entry = ttk.Entry(url_panel, textvariable=self.url_var)
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.load_btn = ttk.Button(url_panel, text="Load movie", style="Accent.TButton", command=self.load_movie)
        self.load_btn.pack(side="right")

        hero = ttk.Frame(self.main, style="Panel.TFrame", padding=14)
        hero.pack(fill="x", pady=(0, 12))

        self.poster_box = tk.Frame(hero, bg=PANEL_2, width=116, height=174, highlightthickness=1,
                                   highlightbackground=BORDER)
        self.poster_box.pack(side="left", padx=(0, 16))
        self.poster_box.pack_propagate(False)
        self.poster_label = tk.Label(
            self.poster_box,
            text="POSTER",
            bg=PANEL_2,
            fg=MUTED,
            font=("Segoe UI Semibold", 10),
        )
        self.poster_label.pack(fill="both", expand=True)

        movie_info = ttk.Frame(hero, style="Panel.TFrame")
        movie_info.pack(side="left", fill="both", expand=True)

        self.movie_label = ttk.Label(
            movie_info,
            text="No movie loaded",
            style="Panel.TLabel",
            font=("Segoe UI Semibold", 22),
        )
        self.movie_label.pack(anchor="w", pady=(6, 2))

        self.movie_meta = ttk.Label(
            movie_info,
            text="Load a NotScare page to populate the timeline.",
            style="PanelMuted.TLabel",
            font=("Segoe UI", 10),
        )
        self.movie_meta.pack(anchor="w")

        ttk.Label(movie_info, textvariable=self.next_var, style="Panel.TLabel",
                  font=("Segoe UI Semibold", 12)).pack(anchor="w", pady=(18, 2))
        ttk.Label(movie_info, textvariable=self.time_var, background=PANEL, foreground=ACCENT,
                  font=("Consolas", 18, "bold")).pack(anchor="w")

        timeline_panel = ttk.Frame(self.main, style="Panel.TFrame", padding=(12, 10))
        timeline_panel.pack(fill="x", pady=(0, 12))
        ttk.Label(timeline_panel, text="Timeline", style="Panel.TLabel",
                  font=("Segoe UI Semibold", 11)).pack(anchor="w", padx=4)

        self.canvas = tk.Canvas(
            timeline_panel,
            height=120,
            bg=PANEL,
            highlightthickness=0,
            cursor="hand2",
        )
        self.canvas.pack(fill="x", expand=True)
        self.canvas.bind("<Button-1>", self.on_timeline_click)
        self.canvas.bind("<Motion>", self.on_timeline_hover)
        self.canvas.bind("<Leave>", lambda _e: self.status_var.set("Click the timeline to seek."))
        self.canvas.bind("<Configure>", lambda _e: self.draw_timeline())

        controls = ttk.Frame(self.main)
        controls.pack(fill="x", pady=(0, 12))
        ttk.Button(controls, text="-15 sec", command=lambda: self.seek_relative(-15)).pack(side="left", padx=(0, 7))
        ttk.Button(controls, text="-1 sec", command=lambda: self.seek_relative(-1)).pack(side="left", padx=(0, 7))
        self.play_btn = ttk.Button(controls, width=11, command=self.toggle_play)
        self.set_play_button(False)
        self.play_btn.pack(side="left", padx=(0, 7))
        ttk.Button(controls, text="+1 sec", command=lambda: self.seek_relative(1)).pack(side="left", padx=(0, 7))
        ttk.Button(controls, text="+15 sec", command=lambda: self.seek_relative(15)).pack(side="left", padx=(0, 7))
        ttk.Button(controls, text="Restart", command=self.restart).pack(side="left")

        table_panel = ttk.Frame(self.main, style="Panel.TFrame", padding=8)
        table_panel.pack(fill="both", expand=True)

        columns = ("time", "severity", "warning", "description")
        self.tree = ttk.Treeview(table_panel, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("time", text="SCARE")
        self.tree.heading("severity", text="LEVEL")
        self.tree.heading("warning", text="WARNING")
        self.tree.heading("description", text="DESCRIPTION")
        self.tree.column("time", width=100, anchor="center", stretch=False)
        self.tree.column("severity", width=90, anchor="center", stretch=False)
        self.tree.column("warning", width=100, anchor="center", stretch=False)
        self.tree.column("description", width=650, anchor="w")

        scroll = ttk.Scrollbar(table_panel, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", self.jump_to_selected_scare)

        status_row = ttk.Frame(self.main)
        status_row.pack(fill="x", pady=(8, 0))
        ttk.Label(status_row, textvariable=self.status_var, style="Muted.TLabel").pack(side="left")
        ttk.Label(status_row, text="Major", foreground=MAJOR).pack(side="right", padx=(12, 0))
        ttk.Label(status_row, text="Minor", foreground=MINOR).pack(side="right")

        # Full-app warning overlay. It is created once, then raised/lowered as needed.
        self.overlay = tk.Frame(self, bg="#190b11")
        self.overlay_title = tk.Label(
            self.overlay,
            text="JUMP SCARE IN",
            bg="#190b11",
            fg="#ffb6c1",
            font=("Segoe UI Semibold", 28),
        )
        self.overlay_title.pack(pady=(85, 4))

        self.overlay_countdown = tk.Label(
            self.overlay,
            text="30",
            bg="#190b11",
            fg="white",
            font=("Segoe UI Black", 112),
        )
        self.overlay_countdown.pack()

        self.overlay_seconds_label = tk.Label(
            self.overlay,
            text="SECONDS",
            bg="#190b0b",
            fg="#ffb6c1",
            font=("Segoe UI Semibold", 20),
        )
        self.overlay_seconds_label.pack()

        self.overlay_detail = tk.Label(
            self.overlay,
            text="",
            bg="#190b0b",
            fg="white",
            font=("Segoe UI", 15),
        )
        self.overlay_detail.pack(pady=(18, 4))

        self.overlay_description = tk.Label(
            self.overlay,
            text="",
            bg="#190b0b",
            fg="#d8c3c3",
            font=("Segoe UI", 11),
            wraplength=760,
            justify="center",
        )
        self.overlay_description.pack(pady=(0, 26))

        tk.Button(
            self.overlay,
            text="Dismiss  (Esc)",
            command=self.dismiss_warning_overlay,
            bg="#342020",
            fg="white",
            activebackground="#4a2a36",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=22,
            pady=10,
            font=("Segoe UI Semibold", 11),
            cursor="hand2",
        ).pack()

    def commit_warning_seconds(self, _event=None):
        raw = self.warning_seconds_var.get().strip()
        try:
            value = int(raw)
            if not MIN_WARNING_SECONDS <= value <= MAX_WARNING_SECONDS:
                raise ValueError
        except ValueError:
            self.warning_seconds_var.set(str(self.warning_seconds))
            self.status_var.set(
                f"Warning lead time must be {MIN_WARNING_SECONDS}-{MAX_WARNING_SECONDS} seconds."
            )
            return "break"

        if value == self.warning_seconds:
            return "break"

        self.warning_seconds = value
        self.warning_seconds_var.set(str(value))

        # Re-arm only future warning points so changing the value does not produce a stale alert.
        for i, scare in enumerate(self.scares):
            warning_at = max(0, scare["time"] - self.warning_seconds)
            if warning_at > self.position:
                self.warned.discard(i)
            else:
                self.warned.add(i)

        self.refresh_tree()
        self.status_var.set(f"Warnings set to {self.warning_seconds} seconds before each scare.")
        return "break"

    def _parse_int_setting(self, var, current, low, high, label):
        """Return the entry's int value, or None (and revert it) if out of range."""
        try:
            value = int(var.get().strip())
            if not low <= value <= high:
                raise ValueError
        except ValueError:
            var.set(str(current))
            self.status_var.set(f"{label} must be {low}-{high}.")
            return None
        var.set(str(value))
        return value

    def commit_duck_percent(self, _event=None):
        value = self._parse_int_setting(
            self.duck_percent_var, self.duck_percent, 0, 100, "Warning volume percent"
        )
        if value is not None and value != self.duck_percent:
            self.duck_percent = value
            if self.volume_ducked:
                self._set_volume(min(self.saved_volume, value / 100))
            self.status_var.set(f"Volume drops to {value}% during warnings.")
        return "break"

    def commit_restore_seconds(self, _event=None):
        value = self._parse_int_setting(
            self.restore_seconds_var, self.restore_seconds, 0, MAX_RESTORE_SECONDS,
            "Volume restore delay",
        )
        if value is not None and value != self.restore_seconds:
            self.restore_seconds = value
            self.update_volume_duck()
            self.status_var.set(f"Volume restores {value} seconds after each scare.")
        return "break"

    def _set_volume(self, level):
        try:
            self.volume.set(level)
            return True
        except Exception as exc:
            self.status_var.set(f"Could not change system volume: {exc}")
            return False

    def in_duck_window(self):
        return any(
            scare["time"] - self.warning_seconds <= self.position < scare["time"] + self.restore_seconds
            for scare in self.scares
        )

    def update_volume_duck(self):
        """Lower the system volume while inside any scare's warning/restore window."""
        if self.volume is None:
            return

        if self.in_duck_window():
            # Only start ducking while the timer is rolling, and not until the chime ends.
            if self.volume_ducked or not self.playing or time.monotonic() < self.duck_hold_until:
                return
            self.ramp_active = False
            try:
                self.saved_volume = self.volume.get()
            except Exception as exc:
                self.status_var.set(f"Could not read system volume: {exc}")
                return
            # Never raise the volume if it was already below the warning level.
            if self._set_volume(min(self.saved_volume, self.duck_percent / 100)):
                self.volume_ducked = True
        else:
            self.restore_volume()

    def restore_volume(self):
        if not self.volume_ducked:
            return
        self.volume_ducked = False
        try:
            # If the user changed the volume by hand during the warning, keep their choice.
            current = self.volume.get()
            if abs(current - min(self.saved_volume, self.duck_percent / 100)) < 0.01:
                self.ramp_active = True
                self.ramp_start_time = time.monotonic()
                self.ramp_start_volume = current
                self.ramp_target_volume = self.saved_volume
            else:
                self.ramp_active = False
        except Exception as exc:
            self.status_var.set(f"Could not restore system volume: {exc}")

    def update_volume_ramp(self):
        """Ease the volume back up to its pre-warning level instead of snapping to it."""
        if not self.ramp_active or self.volume is None:
            return
        elapsed = time.monotonic() - self.ramp_start_time
        if elapsed >= VOLUME_RESTORE_RAMP_SECONDS:
            self._set_volume(self.ramp_target_volume)
            self.ramp_active = False
            return
        fraction = elapsed / VOLUME_RESTORE_RAMP_SECONDS
        level = self.ramp_start_volume + (self.ramp_target_volume - self.ramp_start_volume) * fraction
        self._set_volume(level)

    def load_movie(self):
        self.commit_warning_seconds()
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Missing URL", "Enter a NotScare movie URL.")
            return

        self.load_btn.config(state="disabled")
        self.status_var.set("Loading movie, poster, and jump-scare data...")

        def worker():
            try:
                result = scrape_notscare(url)
                self.after(0, lambda: self.finish_loading(result))
            except Exception as exc:
                self.after(0, lambda: self.load_failed(str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def finish_loading(self, result):
        self.movie_title = result["title"]
        self.duration = result["runtime"]
        self.scares = result["scares"]
        self.position = 0.0
        self.playing = False
        self.last_tick = None
        self.warned.clear()
        self.active_warning_index = None
        self.warning_overlay_dismissed = False
        self.hide_warning_overlay()
        self.restore_volume()

        self.movie_label.config(text=self.movie_title)
        majors = sum(1 for s in self.scares if s["severity"].lower() == "major")
        minors = len(self.scares) - majors
        self.movie_meta.config(
            text=f"{seconds_to_hms(self.duration)} runtime  •  {len(self.scares)} scares  •  {majors} major  •  {minors} minor"
        )
        self.set_play_button(False)

        self.set_poster(result.get("poster_bytes"))
        self.refresh_tree()
        self.load_btn.config(state="normal")
        self.status_var.set(
            f"Loaded {len(self.scares)} jump scares. Start this timer when the movie starts."
        )
        self.update_display()
        self.draw_timeline()

    def set_poster(self, poster_bytes):
        self.poster_photo = None
        if not poster_bytes:
            self.poster_label.config(image="", text="NO POSTER")
            return
        if Image is None or ImageTk is None:
            self.poster_label.config(image="", text="INSTALL\nPILLOW\nFOR POSTER")
            return

        try:
            image = Image.open(io.BytesIO(poster_bytes)).convert("RGB")
            box_w, box_h = 114, 172
            image.thumbnail((box_w, box_h), Image.Resampling.LANCZOS)

            canvas = Image.new("RGB", (box_w, box_h), PANEL_2)
            x = (box_w - image.width) // 2
            y = (box_h - image.height) // 2
            canvas.paste(image, (x, y))

            self.poster_photo = ImageTk.PhotoImage(canvas)
            self.poster_label.config(image=self.poster_photo, text="")
        except Exception:
            self.poster_label.config(image="", text="NO POSTER")

    def refresh_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for index, scare in enumerate(self.scares):
            warning_at = max(0, scare["time"] - self.warning_seconds)
            self.tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    scare["timestamp"],
                    scare["severity"],
                    seconds_to_hms(warning_at),
                    scare["description"],
                ),
            )

    def load_failed(self, error):
        self.load_btn.config(state="normal")
        self.status_var.set("Could not load movie.")
        messagebox.showerror("Load Failed", error)

    def set_play_button(self, playing):
        if playing:
            if not hasattr(self, "pause_icon"):
                # Drawn as an image so the two bars sit a fixed, tight distance apart
                # (font glyphs space them very differently between fonts).
                self.pause_icon = tk.PhotoImage(width=10, height=12)
                self.pause_icon.put(TEXT, to=(1, 1, 4, 12))
                self.pause_icon.put(TEXT, to=(6, 1, 9, 12))
            self.play_btn.config(text=" Pause", image=self.pause_icon, compound="left",
                                 style="Pause.TButton")
        else:
            self.play_btn.config(text="▶  Start", image="", style="Play.TButton")

    def toggle_play(self):
        if not self.scares:
            messagebox.showinfo("Load a Movie", "Load a NotScare movie first.")
            return

        self.commit_warning_seconds()

        if self.position >= self.duration:
            self.position = 0.0
            self.warned.clear()

        self.playing = not self.playing
        self.last_tick = time.monotonic()
        self.set_play_button(self.playing)
        self.status_var.set("Timer running." if self.playing else "Timer paused.")

    def restart(self):
        self.playing = False
        self.position = 0.0
        self.warned.clear()
        self.last_tick = None
        self.active_warning_index = None
        self.warning_overlay_dismissed = False
        self.set_play_button(False)
        self.hide_warning_overlay()
        self.restore_volume()
        self.update_display()
        self.draw_timeline()

    def seek_relative(self, delta):
        self.seek_to(self.position + delta)

    def seek_to(self, new_position):
        old_position = self.position
        self.position = max(0.0, min(float(new_position), float(self.duration)))

        if self.position < old_position:
            for i, scare in enumerate(self.scares):
                warning_at = max(0, scare["time"] - self.warning_seconds)
                if self.position < warning_at:
                    self.warned.discard(i)
        elif self.position > old_position:
            for i, scare in enumerate(self.scares):
                warning_at = max(0, scare["time"] - self.warning_seconds)
                if old_position < warning_at <= self.position:
                    self.warned.add(i)

        self.active_warning_index = None
        self.warning_overlay_dismissed = False
        self.hide_warning_overlay()
        self.last_tick = time.monotonic()
        self.update_volume_duck()
        self.update_display()
        self.draw_timeline()

    def jump_to_selected_scare(self, _event=None):
        selected = self.tree.selection()
        if selected:
            self.seek_to(self.scares[int(selected[0])]["time"])

    def _tick(self):
        now = time.monotonic()
        if self.playing:
            if self.last_tick is None:
                self.last_tick = now

            old_position = self.position
            self.position = min(self.duration, self.position + (now - self.last_tick))
            self.last_tick = now

            self.check_warnings(old_position, self.position)
            self.update_warning_overlay()
            self.update_volume_duck()

            if self.position >= self.duration:
                self.playing = False
                self.set_play_button(False)
                self.restore_volume()
                self.status_var.set("Movie timer finished.")

            self.update_display()
            self.draw_timeline()

        self.update_volume_ramp()
        self.after(TICK_MS, self._tick)

    def check_warnings(self, old_position, new_position):
        for i, scare in enumerate(self.scares):
            warning_at = max(0, scare["time"] - self.warning_seconds)
            if i not in self.warned and old_position < warning_at <= new_position:
                self.warned.add(i)
                self.trigger_warning(i)
                break

    def trigger_warning(self, index):
        scare = self.scares[index]
        self.active_warning_index = index
        self.warning_overlay_dismissed = False
        self.show_warning_overlay()
        self.play_alert_sound(scare["severity"])

        if self.tree.exists(str(index)):
            self.tree.selection_set(str(index))
            self.tree.see(str(index))

        self.status_var.set(
            f"Warning: {scare['severity']} scare at {scare['timestamp']}."
        )

    def show_warning_overlay(self):
        if self.active_warning_index is None or self.warning_overlay_dismissed:
            return
        self.overlay.place(x=0, y=0, relwidth=1, relheight=1)
        self.overlay.lift()
        self.update_warning_overlay()

    def hide_warning_overlay(self):
        self.overlay.place_forget()

    def dismiss_warning_overlay(self):
        if self.active_warning_index is not None:
            self.warning_overlay_dismissed = True
        self.hide_warning_overlay()

    def update_warning_overlay(self):
        if self.active_warning_index is None:
            return

        scare = self.scares[self.active_warning_index]
        remaining = scare["time"] - self.position

        if remaining < -1.0:
            self.active_warning_index = None
            self.warning_overlay_dismissed = False
            self.hide_warning_overlay()
            return

        if self.warning_overlay_dismissed:
            return

        display_remaining = max(0, int(remaining + 0.999))
        severity = scare["severity"].upper()
        color = MAJOR if severity == "MAJOR" else MINOR
        overlay_bg = "#190b11" if severity == "MAJOR" else "#1c1408"

        for widget in (
            self.overlay,
            self.overlay_title,
            self.overlay_countdown,
            self.overlay_seconds_label,
            self.overlay_detail,
            self.overlay_description,
        ):
            widget.configure(bg=overlay_bg)

        self.overlay_title.config(fg=color)
        self.overlay_seconds_label.config(fg=color)
        self.overlay_countdown.config(text=str(display_remaining))
        self.overlay_detail.config(
            text=f"{severity} SCARE  •  {scare['timestamp']}"
        )
        self.overlay_description.config(text=scare["description"] or "")

    def play_alert_sound(self, severity):
        """Play a cheerful chime instead of a harsh alarm."""
        try:
            if sys.platform.startswith("win"):
                import winsound

                sequence = CHIME_MAJOR if severity.lower() == "major" else CHIME_MINOR

                # The chime shares the master volume, so hold off ducking until it ends.
                chime_seconds = sum(d for _f, d in sequence) / 1000 + CHIME_NOTE_GAP * len(sequence)
                self.duck_hold_until = time.monotonic() + chime_seconds + 0.2

                def beep():
                    for freq, duration in sequence:
                        winsound.Beep(freq, duration)
                        time.sleep(CHIME_NOTE_GAP)

                threading.Thread(target=beep, daemon=True).start()
            else:
                # Dependency-free fallback on non-Windows systems.
                self.bell()
                self.after(180, self.bell)
        except Exception:
            try:
                self.bell()
            except Exception:
                pass

    def update_display(self):
        self.time_var.set(
            f"{seconds_to_hms(self.position)}  /  {seconds_to_hms(self.duration)}"
        )

        next_scare = next((s for s in self.scares if s["time"] > self.position), None)
        if next_scare:
            remaining = next_scare["time"] - self.position
            self.next_var.set(
                f"Next scare  {next_scare['timestamp']}  •  "
                f"{seconds_to_hms(remaining)} away  •  {next_scare['severity']}"
            )
        else:
            self.next_var.set("Next scare  —")

    def draw_timeline(self):
        self.canvas.delete("all")
        self.timeline_marker_info.clear()

        width = max(220, self.canvas.winfo_width())
        left = self.timeline_left
        right = width - self.timeline_right
        y = self.timeline_y

        self.canvas.create_line(left, y, right, y, width=5, fill=TRACK)
        if self.duration <= 0:
            return

        interval = 1800
        tick = 0
        while tick <= self.duration:
            x = left + (tick / self.duration) * (right - left)
            self.canvas.create_line(x, y - 6, x, y + 6, fill=MUTED)
            self.canvas.create_text(
                x, y + 18,
                text=seconds_to_hms(tick),
                anchor="n",
                font=("Consolas", 8),
                fill=MUTED,
            )
            tick += interval

        for i, scare in enumerate(self.scares):
            x = left + (scare["time"] / self.duration) * (right - left)
            color = MAJOR if scare["severity"].lower() == "major" else MINOR
            self.canvas.create_polygon(
                x, y - 25,
                x - 7, y - 11,
                x + 7, y - 11,
                fill=color,
                outline=color,
            )
            self.timeline_marker_info.append((i, x))

        pos_x = left + (self.position / self.duration) * (right - left)
        self.canvas.create_line(pos_x, y - 34, pos_x, y + 14, width=3, fill=ACCENT)
        self.canvas.create_oval(
            pos_x - 6, y - 6, pos_x + 6, y + 6,
            fill=ACCENT,
            outline="#dce9ff",
            width=2,
        )

    def on_timeline_click(self, event):
        if not self.scares:
            return
        width = max(220, self.canvas.winfo_width())
        left = self.timeline_left
        right = width - self.timeline_right
        x = min(max(event.x, left), right)
        ratio = (x - left) / max(1, right - left)
        self.seek_to(ratio * self.duration)

    def on_timeline_hover(self, event):
        if not self.scares:
            return

        nearest = None
        nearest_distance = 12
        for index, x in self.timeline_marker_info:
            distance = abs(event.x - x)
            if distance < nearest_distance:
                nearest = index
                nearest_distance = distance

        if nearest is not None:
            scare = self.scares[nearest]
            desc = scare["description"] or "No description"
            self.status_var.set(f"{scare['timestamp']}  •  {scare['severity']}  •  {desc}")
        else:
            width = max(220, self.canvas.winfo_width())
            left = self.timeline_left
            right = width - self.timeline_right
            x = min(max(event.x, left), right)
            ratio = (x - left) / max(1, right - left)
            self.status_var.set(
                f"Seek to {seconds_to_hms(ratio * self.duration)} — click to jump."
            )


if __name__ == "__main__":
    app = JumpScareApp()
    app.mainloop()
