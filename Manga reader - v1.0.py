import os
import json
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from PIL import Image, ImageTk, ImageDraw
import threading
import queue

# ── Tuneable constants ─────────────────────────────────────────────────────────
SUPPORTED_EXT   = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tiff"}
MEMORY_FILE     = os.path.join(os.path.expanduser("~"), ".manga_reader_memory.json")
SETTINGS_FILE   = os.path.join(os.path.expanduser("~"), ".manga_reader_settings.json")
BG_COLOR        = "#1a1a1a"
UI_BG           = "#2b2b2b"
UI_FG           = "#e0e0e0"
ACCENT          = "#e05c5c"
PLACEHOLDER_CLR = "#252525"
ZOOM_MAX        = 4.0
ZOOM_STEP       = 0.15
RENDER_BUFFER   = 1.5

EDGE_TRIGGER    = 15
FALLBACK_W      = 800
FALLBACK_H      = 1200

DEFAULT_SETTINGS = {
    "scroll_speed": 3,
    "zoom_min": 0.25,
    "chunk_size": 100,
}

LAUNCHER_W = 600
LAUNCHER_H = 520
READER_W   = 1100
READER_H   = 820


def load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for k, v in DEFAULT_SETTINGS.items():
                if k not in data:
                    data[k] = v
            return data
    except Exception:
        return dict(DEFAULT_SETTINGS)


def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception:
        pass


def load_memory():
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_memory(memory):
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory, f, indent=2)
    except Exception:
        pass


def natural_sort_key(name):
    base = os.path.splitext(name)[0]
    parts, buf, in_digit = [], "", False
    for ch in base:
        if ch.isdigit() != in_digit:
            if buf:
                parts.append((0, int(buf)) if in_digit else (1, buf.lower()))
            buf, in_digit = "", ch.isdigit()
        buf += ch
    if buf:
        parts.append((0, int(buf)) if in_digit else (1, buf.lower()))
    return parts


def collect_images(folder):
    files = [n for n in os.listdir(folder)
             if os.path.splitext(n)[1].lower() in SUPPORTED_EXT]
    files.sort(key=natural_sort_key)
    return [os.path.join(folder, f) for f in files]


def apply_red_titlebar(win):
    """Paint the native OS title bar #db4242 on Windows 11."""
    try:
        import ctypes
        HWND = ctypes.windll.user32.GetParent(win.winfo_id())
        # BGR little-endian for #db4242 = 0x004242db
        color = ctypes.c_int(0x004242db)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            HWND, 35, ctypes.byref(color), ctypes.sizeof(color))
    except Exception:
        pass


def make_book_icon():
    """Draw a simple red book as a 64x64 PIL image."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Cover
    d.rectangle([6, 4, 58, 60], fill="#db4242", outline="#8b1a1a", width=2)
    # Spine
    d.rectangle([6, 4, 16, 60], fill="#b02020", outline="#8b1a1a", width=2)
    # Page lines
    for y in range(18, 52, 7):
        d.line([(20, y), (54, y)], fill="#f5ddd0", width=2)
    return img


def read_header(path):
    try:
        with Image.open(path) as img:
            return img.width, img.height
    except Exception:
        return FALLBACK_W, FALLBACK_H


def load_pil_full(path):
    try:
        img = Image.open(path)
        img.load()
        return img.copy()
    except Exception:
        return None


# ── Settings Drawer ────────────────────────────────────────────────────────────
class SettingsDrawer:
    DRAWER_W = 270

    def __init__(self, parent, settings, on_save):
        self.parent   = parent
        self.settings = dict(settings)
        self.on_save  = on_save
        self._open    = False
        self._build()

    def _build(self):
        self._overlay = tk.Frame(self.parent, bg="#000000")
        self._overlay.place_forget()
        self._overlay.bind("<Button-1>", lambda e: self.close())

        self._frame = tk.Frame(self.parent, bg="#1e1e1e", bd=0)

        # Header
        hdr = tk.Frame(self._frame, bg=ACCENT)
        hdr.pack(fill="x")
        tk.Label(hdr, text="  Settings", font=("Helvetica", 13, "bold"),
                 bg=ACCENT, fg="white").pack(side="left", padx=10, pady=10)
        tk.Button(hdr, text="X", font=("Helvetica", 10, "bold"),
                  bg=ACCENT, fg="white", activebackground="#c04040",
                  relief="flat", cursor="hand2", bd=0,
                  command=self.close).pack(side="right", padx=10)

        def section(text):
            tk.Label(self._frame, text=text, bg="#1e1e1e", fg="#aaa",
                     font=("Helvetica", 9, "bold")).pack(
                         anchor="w", padx=14, pady=(12, 2))

        def slider_row(parent_frame, var, from_, to, resolution=1, fmt=None):
            row = tk.Frame(parent_frame, bg="#1e1e1e")
            row.pack(fill="x", padx=14, pady=(0, 8))
            sl = tk.Scale(row, from_=from_, to=to, resolution=resolution,
                          orient="horizontal", variable=var,
                          bg="#1e1e1e", fg=UI_FG, troughcolor="#3a3a3a",
                          activebackground=ACCENT, highlightthickness=0,
                          showvalue=False)
            sl.pack(side="left", fill="x", expand=True)
            if fmt:
                sv = tk.StringVar()
                def upd(*_):
                    sv.set(fmt(var.get()))
                var.trace_add("write", upd)
                upd()
                lbl = tk.Label(row, textvariable=sv, bg="#1e1e1e",
                               fg=ACCENT, font=("Helvetica", 10, "bold"), width=6)
            else:
                lbl = tk.Label(row, textvariable=var, bg="#1e1e1e",
                               fg=ACCENT, font=("Helvetica", 10, "bold"), width=6)
            lbl.pack(side="left", padx=(4, 0))

        # Scroll speed
        section("SCROLL SPEED")
        self._sv_speed = tk.IntVar(value=self.settings["scroll_speed"])
        slider_row(self._frame, self._sv_speed, 1, 10)

        # Zoom min
        section("MINIMUM ZOOM")
        self._sv_zmin = tk.DoubleVar(value=self.settings["zoom_min"])
        slider_row(self._frame, self._sv_zmin, 0.1, 1.0, 0.05,
                   fmt=lambda v: f"{v:.2f}x")

        # Chunk size
        section("CHUNK SIZE  (images in RAM)")
        self._sv_chunk = tk.IntVar(value=self.settings["chunk_size"])
        slider_row(self._frame, self._sv_chunk, 20, 300, 10)

        # Divider
        tk.Frame(self._frame, bg="#3a3a3a", height=1).pack(
            fill="x", padx=14, pady=(14, 4))

        # History buttons
        section("CLEAR HISTORY")
        bkw = dict(relief="flat", cursor="hand2", font=("Helvetica", 10),
                   pady=6, anchor="w", padx=12)
        tk.Button(self._frame, text="  Clear Page Memory",
                  bg="#2e2e2e", fg=UI_FG, activebackground="#444",
                  command=self._clear_pages, **bkw).pack(
                      fill="x", padx=14, pady=(0, 4))
        tk.Button(self._frame, text="  Clear Book Memory",
                  bg="#2e2e2e", fg=UI_FG, activebackground="#444",
                  command=self._clear_zoom, **bkw).pack(
                      fill="x", padx=14, pady=(0, 4))
        tk.Button(self._frame, text="  Clear ALL History",
                  bg="#5a1a1a", fg="white", activebackground="#7a2a2a",
                  command=self._clear_all, **bkw).pack(
                      fill="x", padx=14, pady=(0, 4))

        tk.Frame(self._frame, bg="#3a3a3a", height=1).pack(
            fill="x", padx=14, pady=(10, 6))

        tk.Button(self._frame, text="Save Settings",
                  bg=ACCENT, fg="white", activebackground="#c04040",
                  relief="flat", cursor="hand2",
                  font=("Helvetica", 11, "bold"), pady=8,
                  command=self._save).pack(fill="x", padx=14, pady=(0, 16))

    def _clear_pages(self):
        m = load_memory()
        for k in m:
            m[k].pop("page", None)
        save_memory(m)
        self._refresh_launcher(m)

    def _clear_zoom(self):
        m = load_memory()
        for k in m:
            m[k].pop("zoom", None)
        save_memory(m)
        self._refresh_launcher(m)

    def _clear_all(self):
        save_memory({})
        self._refresh_launcher({})

    def _refresh_launcher(self, new_memory):
        """Push updated memory back to the Launcher and rebuild its recent list."""
        # self.parent is either the Launcher itself or a ReaderWindow
        target = self.parent
        if isinstance(target, Launcher):
            launcher = target
        else:
            # ReaderWindow stores a reference to its launcher
            launcher = getattr(target, "launcher", None)
        if launcher is not None and isinstance(launcher, Launcher):
            launcher.memory = new_memory
            launcher._rebuild_recent(new_memory)

    def _save(self):
        self.settings["scroll_speed"] = self._sv_speed.get()
        self.settings["zoom_min"]     = round(self._sv_zmin.get(), 2)
        self.settings["chunk_size"]   = self._sv_chunk.get()
        save_settings(self.settings)
        self.on_save(self.settings)
        self.close()

    def toggle(self):
        self.close() if self._open else self.open()

    def open(self):
        if self._open:
            return
        self._open = True
        w = self.parent.winfo_width()
        h = self.parent.winfo_height()
        self._overlay.place(x=0, y=0, width=w, height=h)
        self._overlay.lift()
        self._frame.place(x=0, y=0, width=self.DRAWER_W, height=h)
        self._frame.lift()

    def close(self):
        if not self._open:
            return
        self._open = False
        self._overlay.place_forget()
        self._frame.place_forget()


# ── Launcher ───────────────────────────────────────────────────────────────────
class Launcher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Manga Reader")
        self.resizable(False, False)
        self.configure(bg=UI_BG)

        self.settings = load_settings()
        self.memory   = load_memory()
        self.folder   = tk.StringVar()

        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{LAUNCHER_W}x{LAUNCHER_H}+"
                      f"{(sw-LAUNCHER_W)//2}+{(sh-LAUNCHER_H)//2}")

        # Book icon
        try:
            self._icon = ImageTk.PhotoImage(make_book_icon())
            self.iconphoto(True, self._icon)
        except Exception:
            pass

        self._build_ui()

        # Red title bar — must come after window is visible
        self.update_idletasks()
        apply_red_titlebar(self)

        self._drawer = SettingsDrawer(self, self.settings, self._settings_saved)

    def _settings_saved(self, s):
        self.settings = s

    def _build_ui(self):
        # ── Top bar with cog ──
        topbar = tk.Frame(self, bg=UI_BG)
        topbar.pack(fill="x")
        tk.Button(topbar, text=" \u2699 ", font=("Helvetica", 16),
                  bg=UI_BG, fg="#bbb", activebackground="#444",
                  activeforeground=ACCENT, relief="flat", cursor="hand2", bd=0,
                  command=lambda: self._drawer.toggle()).pack(
                      side="left", padx=4, pady=4)

        # ── Title ──
        tk.Label(self, text="\U0001f4d6  Manga Reader",
                 font=("Helvetica", 22, "bold"),
                 bg=UI_BG, fg=ACCENT).pack(pady=(4, 2))
        tk.Label(self, text="Pages hold endless worlds",
                 font=("Helvetica", 11), bg=UI_BG, fg="#888").pack(pady=(0, 16))

        # ── Folder picker (centred) ──
        frm = tk.Frame(self, bg=UI_BG)
        frm.pack(pady=(0, 0))
        tk.Label(frm, text="Manga folder:", bg=UI_BG, fg=UI_FG,
                 font=("Helvetica", 11)).pack(anchor="w")
        row = tk.Frame(frm, bg=UI_BG)
        row.pack(pady=6)
        tk.Entry(row, textvariable=self.folder, width=54,
                 bg="#3a3a3a", fg=UI_FG, insertbackground=UI_FG,
                 relief="flat", font=("Helvetica", 10)).pack(
                     side="left", ipady=5, padx=(0, 6))
        tk.Button(row, text="Browse...", command=self._browse,
                  bg="#444", fg=UI_FG, activebackground="#555",
                  relief="flat", cursor="hand2", padx=10).pack(side="left")

        # ── Recently viewed ──
        self._recent_paths = list(self.memory.keys())
        self._recent_lb    = None
        if self._recent_paths:
            tk.Label(self, text="Recently viewed:", bg=UI_BG, fg="#aaa",
                     font=("Helvetica", 10)).pack(anchor="w", padx=68)
            lb = tk.Listbox(self, height=min(5, len(self._recent_paths)),
                            bg="#333", fg=UI_FG, selectbackground=ACCENT,
                            relief="flat", font=("Helvetica", 10), activestyle="none",
                            width=65)
            for path in self._recent_paths:
                data = self.memory[path]
                name = os.path.basename(path.rstrip("/\\")) or path
                lb.insert("end", f"{name}   [p.{data.get('page', 1)}]")
            lb.pack(pady=(0, 8))
            lb.bind("<<ListboxSelect>>", lambda e, l=lb: self._pick_recent(l))
            self._recent_lb = lb

        # ── Buttons ──
        bf = tk.Frame(self, bg=UI_BG)
        bf.pack(pady=(12, 24))
        tk.Button(bf, text="   Start   ", command=self._start,
                  bg=ACCENT, fg="white", activebackground="#c04040",
                  font=("Helvetica", 13, "bold"), relief="flat",
                  cursor="hand2", padx=20, pady=8).pack(side="left", padx=8)
        tk.Button(bf, text="Quit", command=self.destroy,
                  bg="#444", fg=UI_FG, activebackground="#555",
                  relief="flat", cursor="hand2", padx=16, pady=8).pack(side="left")

    def _browse(self):
        p = filedialog.askdirectory(title="Select manga folder")
        if p:
            self.folder.set(p)

    def _pick_recent(self, lb):
        sel = lb.curselection()
        if sel:
            idx = sel[0]
            if idx < len(self._recent_paths):
                self.folder.set(self._recent_paths[idx])

    def _start(self):
        folder = self.folder.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror("Error", "Please select a valid folder.")
            return
        images = collect_images(folder)
        if not images:
            messagebox.showerror("Error",
                "No supported images found.\nSupported: JPG, PNG, WebP, BMP, GIF, TIFF")
            return
        data       = self.memory.get(folder, {})
        start_page = max(1, min(data.get("page", 1), len(images)))
        start_zoom = data.get("zoom", 0.4)
        self.withdraw()
        r = ReaderWindow(self, folder, images, start_page, start_zoom,
                         self.memory, self.settings)
        r.protocol("WM_DELETE_WINDOW", lambda: self._close_reader(r))

        
    def _rebuild_recent(self, memory):
        """Refresh the recently-viewed listbox without restarting."""
        self._recent_paths = list(memory.keys())
        if self._recent_lb is not None:
            self._recent_lb.delete(0, "end")
            for path in self._recent_paths:
                data = memory.get(path, {})
                name = os.path.basename(path.rstrip("/\\")) or path
                self._recent_lb.insert("end", f"{name}   [p.{data.get('page', 1)}]")

    def _close_reader(self, r):
        r.close()
        self.deiconify()


# ── Reader ─────────────────────────────────────────────────────────────────────
class ReaderWindow(tk.Toplevel):
    def __init__(self, launcher, folder, images, start_page, start_zoom,
                 memory, settings):
        super().__init__(launcher)
        self.launcher    = launcher
        self.folder      = folder
        self.images      = images
        self.memory      = memory
        self.settings    = settings
        self.total       = len(images)
        self.zoom        = start_zoom
        self._start_page = start_page

        self._pil      = [None] * self.total
        self._photo    = [None] * self.total
        self._orig_w   = [FALLBACK_W] * self.total
        self._orig_h   = [FALLBACK_H] * self.total
        self._canvas_y = [0] * self.total
        self._canvas_h = [FALLBACK_H] * self.total
        self._item_id  = [None] * self.total
        self._ph_id    = [None] * self.total

        cs   = self.settings["chunk_size"]
        half = cs // 2
        self._win_start = max(0, start_page - 1 - half)
        self._win_end   = min(self.total, self._win_start + cs)
        self._win_start = max(0, self._win_end - cs)

        self._current_page  = start_page
        self._stop_flag     = threading.Event()
        self._load_queue    = queue.Queue()
        self._loader_thread = None

        self.title("Manga Reader")
        self.configure(bg=BG_COLOR)
        self.resizable(True, True)
        try:
            self.state('zoomed')        # Windows / macOS : normal window but full‑screen
        except Exception:               # In case the WM does not support it
            pass                        # you can fall back to a custom fullscreen size if you wish


        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{READER_W}x{READER_H}+"
                      f"{(sw-READER_W)//2}+{(sh-READER_H)//2}")

        # Book icon
        try:
            self._icon = ImageTk.PhotoImage(make_book_icon())
            self.iconphoto(True, self._icon)
        except Exception:
            pass

        self._build_ui()
        self._bind_events()
        self.update_idletasks()
        apply_red_titlebar(self)

        self._drawer = SettingsDrawer(self, self.settings, self._settings_saved)
        threading.Thread(target=self._scan_all_headers, daemon=True).start()

    def _settings_saved(self, s):
        self.settings = s
        self.launcher.settings = s

    # ── UI ──────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        bar = tk.Frame(self, bg=UI_BG, height=42)
        bar.pack(side="top", fill="x")
        bar.pack_propagate(False)

        # Cog at far left
        tk.Button(bar, text=" \u2699 ", font=("Helvetica", 16),
                  bg=UI_BG, fg="#bbb", activebackground="#444",
                  activeforeground=ACCENT, relief="flat", cursor="hand2", bd=0,
                  command=lambda: self._drawer.toggle()).pack(
                      side="left", padx=4)

        tk.Label(bar,
                 text=f"\U0001f4c1 {os.path.basename(self.folder) or self.folder}",
                 bg=UI_BG, fg="#999", font=("Helvetica", 10)).pack(
                     side="left", padx=6)

        self.page_var = tk.StringVar(value="Scanning...")
        tk.Label(bar, textvariable=self.page_var, bg=UI_BG, fg=UI_FG,
                 font=("Helvetica", 11, "bold")).pack(side="right", padx=16)

        zf = tk.Frame(bar, bg=UI_BG)
        zf.pack(side="right", padx=4)
        b = dict(bg="#444", fg=UI_FG, activebackground="#555",
                 relief="flat", cursor="hand2")
        tk.Button(zf, text="-", font=("Helvetica", 14), width=2,
                  command=self._zoom_out, **b).pack(side="left")
        self.zoom_lbl = tk.Label(zf, text=f"{int(self.zoom*100)}%",
                                  bg=UI_BG, fg=UI_FG,
                                  font=("Helvetica", 10), width=5)
        self.zoom_lbl.pack(side="left", padx=2)
        tk.Button(zf, text="+", font=("Helvetica", 14), width=2,
                  command=self._zoom_in, **b).pack(side="left")
        tk.Button(zf, text="Fit", font=("Helvetica", 9), padx=6,
                  command=self._zoom_fit, **b).pack(side="left", padx=(6, 0))

        bot = tk.Frame(self, bg=UI_BG)
        bot.pack(side="bottom", fill="x")
        self.status_var = tk.StringVar(value="Scanning image sizes...")
        tk.Label(bot, textvariable=self.status_var, bg=UI_BG, fg="#777",
                 font=("Helvetica", 9), anchor="w").pack(
                     side="left", fill="x", expand=True, padx=8, pady=2)
        self._chunk_lbl = tk.Label(bot, text="", bg=UI_BG, fg=ACCENT,
                                    font=("Helvetica", 9, "bold"))
        self._chunk_lbl.pack(side="right", padx=8)

        cf = tk.Frame(self, bg=BG_COLOR)
        cf.pack(fill="both", expand=True)
        self.sb = ttk.Scrollbar(cf, orient="vertical")
        self.sb.pack(side="right", fill="y")
        self.canvas = tk.Canvas(cf, bg=BG_COLOR, highlightthickness=0,
                                yscrollcommand=self.sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.sb.config(command=self._on_sb_scroll)

    # ── Events ──────────────────────────────────────────────────────────────────
    def _bind_events(self):
        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>",
                         lambda e: self._scroll_by(-self.settings["scroll_speed"]))
        self.canvas.bind("<Button-5>",
                         lambda e: self._scroll_by(self.settings["scroll_speed"]))
        self.bind("<Prior>",  lambda e: self._jump_page(-1))
        self.bind("<Next>",   lambda e: self._jump_page(1))
        self.bind("<Up>",     lambda e: self._scroll_by(-self.settings["scroll_speed"]))
        self.bind("<Down>",   lambda e: self._scroll_by(self.settings["scroll_speed"]))
        self.bind("<Control-equal>", lambda e: self._zoom_in())
        self.bind("<Control-plus>",  lambda e: self._zoom_in())
        self.bind("<Control-minus>", lambda e: self._zoom_out())
        self.bind("<Control-0>",     lambda e: self._zoom_fit())

    def _on_wheel(self, event):
        if event.state & 0x0004:
            self._zoom_in() if event.delta > 0 else self._zoom_out()
            return "break"
        self._scroll_by((-1 if event.delta > 0 else 1) * self.settings["scroll_speed"])
        return "break"

    def _scroll_by(self, units):
        self.canvas.yview_scroll(units, "units")
        self._after_scroll()

    def _on_sb_scroll(self, *args):
        self.canvas.yview(*args)
        self._after_scroll()

    def _after_scroll(self):
        self._update_page()
        self.after_idle(self._lazy_render)
        self.after_idle(self._maybe_slide_window)

    def _on_resize(self, _e):
        self._rebuild_layout()

    # ── Header scan ─────────────────────────────────────────────────────────────
    def _scan_all_headers(self):
        for i, path in enumerate(self.images):
            if self._stop_flag.is_set():
                return
            w, h = read_header(path)
            self._orig_w[i] = w
            self._orig_h[i] = h
            if i % 100 == 0 or i == self.total - 1:
                n = i + 1
                self.after(0, lambda n=n: self._on_headers_progress(n))
        self.after(0, self._on_all_headers_done)

    def _on_headers_progress(self, n):
        self.status_var.set(f"Scanning sizes... {n}/{self.total}")
        self._rebuild_layout()
        if n >= min(50, self.total) and self._loader_thread is None:
            self._start_chunk_load(self._win_start, self._win_end)
            self._poll_load_queue()
            self.after(150, lambda: self._jump_to_page(self._start_page))

    def _on_all_headers_done(self):
        self._rebuild_layout()
        self.status_var.set(
            f"+ {self.total} images  |  Ctrl+scroll = zoom  |  PgUp/PgDn = jump")

    # ── Chunk loading ────────────────────────────────────────────────────────────
    def _start_chunk_load(self, new_start, new_end):
        cs = self.settings["chunk_size"]
        new_start = max(0, new_start)
        new_end   = min(self.total, new_end)
        for i in range(self._win_start, self._win_end):
            if i < new_start or i >= new_end:
                self._unload_pil(i)
        self._win_start = new_start
        self._win_end   = new_end
        self._update_chunk_label()
        to_load = [i for i in range(new_start, new_end) if self._pil[i] is None]
        if not to_load:
            return
        self._stop_flag.set()
        if self._loader_thread and self._loader_thread.is_alive():
            self._loader_thread.join(timeout=0.5)
        self._stop_flag.clear()
        while not self._load_queue.empty():
            try:
                self._load_queue.get_nowait()
            except queue.Empty:
                break
        def loader():
            centre = self._current_page - 1
            for i in sorted(to_load, key=lambda i: abs(i - centre)):
                if self._stop_flag.is_set():
                    return
                pil = load_pil_full(self.images[i])
                if pil:
                    self._load_queue.put((i, pil))
        self._loader_thread = threading.Thread(target=loader, daemon=True)
        self._loader_thread.start()

    def _poll_load_queue(self):
        try:
            for _ in range(8):
                i, pil = self._load_queue.get_nowait()
                if self._win_start <= i < self._win_end:
                    self._pil[i] = pil
                    if self._is_near_viewport(i):
                        self._ensure_rendered(i)
        except queue.Empty:
            pass
        if not self._stop_flag.is_set():
            self.after(60, self._poll_load_queue)

    def _maybe_slide_window(self):
        cs    = self.settings["chunk_size"]
        page  = self._current_page - 1
        ahead = self._win_end - 1 - page
        behind = page - self._win_start
        if ahead < EDGE_TRIGGER and self._win_end < self.total:
            ns = max(0, page - cs // 3)
            ne = min(self.total, ns + cs)
            ns = max(0, ne - cs)
            if ns != self._win_start or ne != self._win_end:
                self._start_chunk_load(ns, ne)
            return
        if behind < EDGE_TRIGGER and self._win_start > 0:
            ne = min(self.total, page + cs // 3)
            ns = max(0, ne - cs)
            ne = min(self.total, ns + cs)
            if ns != self._win_start or ne != self._win_end:
                self._start_chunk_load(ns, ne)

    def _unload_pil(self, i):
        self._evict_rendered(i)
        self._pil[i] = None

    def _update_chunk_label(self):
        self._chunk_lbl.config(
            text=f"Loaded: {self._win_start+1}-{self._win_end} / {self.total}")

    # ── Layout ──────────────────────────────────────────────────────────────────
    def _scaled_dims(self, i):
        cw = max(self.canvas.winfo_width(), 200)
        ow, oh = self._orig_w[i], self._orig_h[i]
        tw = int(cw * self.zoom)
        if ow == 0:
            return tw, FALLBACK_H
        return tw, max(1, int(oh * tw / ow))

    def _rebuild_layout(self):
        cw = max(self.canvas.winfo_width(), 200)
        y  = 0
        for i in range(self.total):
            w, h = self._scaled_dims(i)
            self._canvas_y[i] = y
            self._canvas_h[i] = h
            x0, x1 = (cw - w) // 2, (cw - w) // 2 + w
            if self._ph_id[i] is None:
                self._ph_id[i] = self.canvas.create_rectangle(
                    x0, y, x1, y+h, fill=PLACEHOLDER_CLR, outline="", tags="ph")
            else:
                self.canvas.coords(self._ph_id[i], x0, y, x1, y+h)
            if self._item_id[i] is not None:
                self._evict_rendered(i)
            y += h
        self.canvas.configure(scrollregion=(0, 0, cw, y))
        self._lazy_render()
        self._update_page()

    # ── Lazy render ──────────────────────────────────────────────────────────────
    def _viewport(self):
        ft, fb = self.canvas.yview()
        sr = self.canvas.cget("scrollregion")
        if not sr:
            return 0, self.canvas.winfo_height()
        th = int(sr.split()[3])
        return int(ft*th), int(fb*th)

    def _is_near_viewport(self, i):
        vt, vb = self._viewport()
        buf = int(max(vb-vt, 1) * RENDER_BUFFER)
        return (self._canvas_y[i]+self._canvas_h[i] >= vt-buf and
                self._canvas_y[i] <= vb+buf)

    def _lazy_render(self):
        vt, vb = self._viewport()
        buf = int(max(vb-vt, 1) * RENDER_BUFFER)
        for i in range(self.total):
            if (self._canvas_y[i]+self._canvas_h[i] >= vt-buf and
                    self._canvas_y[i] <= vb+buf):
                self._ensure_rendered(i)
            else:
                self._evict_rendered(i)

    def _ensure_rendered(self, i):
        if self._item_id[i] is not None:
            return
        pil = self._pil[i]
        if pil is None:
            return
        cw = max(self.canvas.winfo_width(), 200)
        tw, th = self._scaled_dims(i)
        try:
            photo = ImageTk.PhotoImage(pil.resize((tw, th), Image.LANCZOS))
        except Exception:
            return
        self._photo[i]   = photo
        self._item_id[i] = self.canvas.create_image(
            cw//2, self._canvas_y[i], anchor="n", image=photo)
        if self._ph_id[i] is not None:
            self.canvas.itemconfig(self._ph_id[i], state="hidden")

    def _evict_rendered(self, i):
        if self._item_id[i] is not None:
            self.canvas.delete(self._item_id[i])
            self._item_id[i] = None
            self._photo[i]   = None
        if self._ph_id[i] is not None:
            self.canvas.itemconfig(self._ph_id[i], state="normal")

    # ── Page tracking ────────────────────────────────────────────────────────────
    def _update_page(self):
        vt, _ = self._viewport()
        mid   = vt + self.canvas.winfo_height() // 2
        page  = 1
        for i in range(self.total):
            if self._canvas_y[i] <= mid:
                page = i + 1
            else:
                break
        self._current_page = page
        self.page_var.set(f"Page {page} / {self.total}")
        self.memory[self.folder] = {"page": page, "zoom": self.zoom}
        save_memory(self.memory)

    # ── Navigation ───────────────────────────────────────────────────────────────
    def _jump_to_page(self, page):
        page = max(1, min(page, self.total))
        sr   = self.canvas.cget("scrollregion")
        if not sr:
            return
        th = int(sr.split()[3])
        if th:
            self.canvas.yview_moveto(self._canvas_y[page-1] / th)
        self._after_scroll()

    def _jump_page(self, delta):
        self._jump_to_page(self._current_page + delta)

    # ── Zoom ─────────────────────────────────────────────────────────────────────
    def _set_zoom(self, z):
        page = self._current_page
        zmin = self.settings["zoom_min"]
        self.zoom = round(max(zmin, min(ZOOM_MAX, z)), 2)
        self.zoom_lbl.config(text=f"{int(self.zoom*100)}%")
        entry = self.memory.get(self.folder, {})
        entry["zoom"] = self.zoom
        self.memory[self.folder] = entry
        save_memory(self.memory)
        self._rebuild_layout()
        self.after(80, lambda: self._jump_to_page(page))

    def _zoom_in(self):  self._set_zoom(self.zoom + ZOOM_STEP)
    def _zoom_out(self): self._set_zoom(self.zoom - ZOOM_STEP)
    def _zoom_fit(self): self._set_zoom(1.0)

    # ── Close ────────────────────────────────────────────────────────────────────
    def close(self):
        self._stop_flag.set()
        save_memory(self.memory)
        self.destroy()


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    app = Launcher()
    app.mainloop()


if __name__ == "__main__":
    main()