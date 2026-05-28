# -*- coding: utf-8 -*-
"""
RPG Decrypter (Windows 10/11) — Lite build

Native-tkinter rewrite of the previous CustomTkinter UI:
    * No bundled fonts (uses the Windows system Gothic)
    * No dark/light theme — single medium-gray palette
    * No keyboard shortcuts (cancel via the in-flight Run button)
    * Decryption-target / language / worker-count / process-priority
      live in a real menu bar at the top of the window.
    * Log textbox spans the full bottom of the window.

Security policy (unchanged):
    The decryption key is NEVER persisted to disk; it lives in process
    memory only. Old config files containing a saved key are auto-purged.

Threading model (unchanged):
    Decryption work runs in a ThreadPoolExecutor on a worker thread.
    Worker -> UI updates are marshalled through ``root.after(0, ...)``.
    A ``threading.Event`` is the cooperative cancellation signal.
"""

from __future__ import annotations

import concurrent.futures
import ctypes
import os
import pathlib
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

from config_store import load_config_data, save_config_data
from lang import LANGUAGE_CODES_BY_LABEL, LANGUAGE_OPTIONS, TEXT
from rpg_core import (
    EXT_MAP,
    KNOWN_UNSUPPORTED_EXT,
    PLAIN_MEDIA_EXT,
    SystemJsonScan,
    decrypt_asset,
    encrypt_asset,
    restore_png_no_key,
    RGSSArchive,
    RGSSCoder,
    extract_key_from_system_json,
    get_target_extensions,
    mask_key,
    unique_output_path,
    validate_key,
    validate_paths,
    IMAGE_EXTS,
)

# =====================================================================
# Platform guard
# =====================================================================
if sys.platform != "win32":
    raise SystemExit("This application currently supports Windows 10/11 only.")

APP_VERSION = "2.2.0"


# =====================================================================
# HiDPI awareness  (kept — the customtkinter UI is gone but the call
# itself is essentially free and prevents blurry text on 4K displays)
# =====================================================================
def _enable_dpi_awareness() -> None:
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _apply_tk_dpi_scaling(root: tk.Tk) -> None:
    """Scale Tk's font/widget size to match the real system DPI.

    Tk does not auto-detect HiDPI when the process is DPI-aware, so on a
    4K display its widgets render at 100 % size (tiny). Multiplying its
    scaling factor by (sys_dpi / 96) restores readable sizing.
    """
    try:
        sys_dpi = float(ctypes.windll.user32.GetDpiForSystem())
    except Exception:
        sys_dpi = 96.0
    if sys_dpi <= 0:
        return
    factor = sys_dpi / 96.0
    if abs(factor - 1.0) < 0.01:
        return
    try:
        current = float(root.tk.call("tk", "scaling"))
        root.tk.call("tk", "scaling", current * factor)
    except Exception:
        pass


_enable_dpi_awareness()


# =====================================================================
# Resource path helper (works in dev and PyInstaller --onedir/--onefile)
# =====================================================================
def resource_path(relative: str) -> str:
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(base, relative))


# =====================================================================
# Color tokens — single medium-gray palette
# =====================================================================
COLORS = {
    "bg":         "#2b2b2b",
    "surface":    "#1e1e1e",   # log textbox bg, slightly darker
    "entry_bg":   "#3a3a3a",
    "entry_fg":   "#ffffff",
    "fg":         "#d0d0d0",
    "fg_dim":     "#9e9e9e",
    "border":     "#4a4a4a",
    "btn_bg":     "#3a3a3a",
    "btn_active": "#4a4a4a",
    "btn_fg":     "#ffffff",
    "menu_bg":    "#2b2b2b",
    "menu_fg":    "#d0d0d0",
    "menu_active_bg": "#4a4a4a",
    "log_info":     "#6daee6",
    "log_success":  "#7fc97f",
    "log_warning":  "#e6b86d",
    "log_error":    "#e67c7c",
}


# =====================================================================
# App-level constants
# =====================================================================
PROGRESS_LOG_BUCKET    = 5
UI_THROTTLE_SEC        = 0.05
LOG_MAX_LINES          = 5000
LOG_TRIM_TARGET        = 2500
CLOSE_POLL_INTERVAL_MS = 100
# Capped at 4 — RPG Maker assets are small and I/O bound; more workers
# trash HDD seek time without helping SSDs measurably past this point.
DECRYPT_WORKERS        = min(os.cpu_count() or 4, 4)

SEVERITY_PREFIXES: dict[str, tuple[str, ...]] = {
    "info":    ("[i]",),
    "success": ("[OK]", "[Done]", "[*]"),
    "error":   ("[X]", "[Failed]", "[Fatal]"),
    "warning": ("[!]", "[Cancelled]", "[취소]"),
}

TARGET_MODE_ORDER = ("both", "image", "audio")
TARGET_MODE_TEXT_KEYS = {
    "both":  "target_both",
    "image": "target_image",
    "audio": "target_audio",
}
PLAIN_MEDIA_EXTS_BY_TARGET = {
    "both":  {".png", ".ogg", ".m4a"},
    "image": {".png"},
    "audio": {".ogg", ".m4a"},
}

RPG_FOLDER_INDICATORS = ("data", "www", "img", "audio", "js")

SKIP_REASONS = {
    "too_small",
    "already_png",
    "already_ogg",
    "already_m4a",
    "not_encrypted",
}


# =====================================================================
# Bundled language font loader
# =====================================================================
# The file names below must match assets/fonts exactly.
# Font family names are the internal names exposed to Tk after registration.
BUNDLED_FONT_FILES: dict[str, str] = {
    "a2z": "A2Z-4Regular.ttf",
    "zh":  "NotoSansSC-Regular.ttf",
    "ja":  "ZenKakuGothicNew-Regular.ttf",
}

FONT_FAMILY_CANDIDATES: dict[str, tuple[str, ...]] = {
    # A2Z's internal family name can vary by file build, so keep candidates.
    "a2z": ("A2Z 4 Regular", "A2Z-4Regular", "A2Z-4", "A2Z 4", "A2Z"),
    "zh":  ("Noto Sans SC", "NotoSansSC", "Noto Sans CJK SC"),
    "ja":  ("Zen Kaku Gothic New", "ZenKakuGothicNew", "Zen Kaku Gothic"),
}

_LOADED_BUNDLED_FONTS = False


def _load_private_font_file(filename: str) -> None:
    """Register one bundled TTF privately for this process on Windows."""
    font_path = resource_path(os.path.join("assets", "fonts", filename))
    if not os.path.isfile(font_path):
        sys.stderr.write(f"[font] Missing bundled font: {font_path}")
        return
    try:
        # FR_PRIVATE (0x10): font is available only to this process.
        ctypes.windll.gdi32.AddFontResourceExW(font_path, 0x10, None)
    except Exception as e:
        sys.stderr.write(f"[font] Failed to load {font_path}: {e}")


def _load_bundled_fonts() -> None:
    """Load A2Z, Chinese, and Japanese bundled fonts once."""
    global _LOADED_BUNDLED_FONTS
    if _LOADED_BUNDLED_FONTS:
        return
    for filename in BUNDLED_FONT_FILES.values():
        _load_private_font_file(filename)
    _LOADED_BUNDLED_FONTS = True


def _first_available_family(candidates: tuple[str, ...]) -> str | None:
    try:
        families = set(tkfont.families())
    except Exception:
        return None

    # Exact match first.
    for candidate in candidates:
        if candidate in families:
            return candidate

    # Loose match second, useful when the family name contains spacing variants.
    normalized = {name.lower().replace(" ", "").replace("-", ""): name for name in families}
    for candidate in candidates:
        key = candidate.lower().replace(" ", "").replace("-", "")
        if key in normalized:
            return normalized[key]
    return None


# =====================================================================
# Default font helper
# =====================================================================
def _pick_default_family(lang: str = "ko") -> str:
    """Return the best bundled/system font for the selected UI language.

    ko/en -> A2Z bundled font
    zh    -> Noto Sans SC bundled font
    ja    -> Zen Kaku Gothic New bundled font
    """
    _load_bundled_fonts()

    if lang in ("ko", "en"):
        family = _first_available_family(FONT_FAMILY_CANDIDATES["a2z"])
        if family:
            return family
        for candidate in ("Malgun Gothic", "맑은 고딕", "Segoe UI"):
            if _first_available_family((candidate,)):
                return candidate

    if lang in ("zh", "zh_cn", "zh-CN", "cn"):
        family = _first_available_family(FONT_FAMILY_CANDIDATES["zh"])
        if family:
            return family
        for candidate in ("Microsoft YaHei UI", "Microsoft YaHei", "Malgun Gothic", "맑은 고딕"):
            if _first_available_family((candidate,)):
                return candidate

    if lang in ("ja", "jp"):
        family = _first_available_family(FONT_FAMILY_CANDIDATES["ja"])
        if family:
            return family
        for candidate in ("Yu Gothic UI", "Yu Gothic", "Meiryo UI", "Meiryo", "Malgun Gothic", "맑은 고딕"):
            if _first_available_family((candidate,)):
                return candidate

    return "TkDefaultFont"


def get_toplevel_hwnd(root) -> int:
    hwnd = root.winfo_id()
    try:
        parent = ctypes.windll.user32.GetAncestor(hwnd, 2)  # GA_ROOT = 2
        if parent:
            return parent
    except Exception:
        pass
    # fallback
    try:
        GetParent = ctypes.windll.user32.GetParent
        current = hwnd
        while True:
            p = GetParent(current)
            if not p:
                break
            current = p
        return current
    except Exception:
        return hwnd


# =====================================================================
# Main application
# =====================================================================
class DecrypterApp:
    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"RPG Decrypter v{APP_VERSION}")
        self.set_window_icon()

        _apply_tk_dpi_scaling(self.root)

        # Pick a reasonable, non-resizable window size.
        self.root.geometry("750x750")
        self.root.resizable(False, False)
        self.root.configure(bg=COLORS["bg"])

        # Runtime state must exist before any helper uses it.
        # In particular, _pick_default_family(self.current_lang) and t()
        # both read current_lang during startup.
        self.current_lang        = "ko"
        self.current_target_mode = "both"
        self.current_task_mode   = "decrypt"
        self.is_processing       = False
        self.processed_files     = 0
        self.total_files         = 0

        # Threading state
        self._cancel_event         = threading.Event()
        self._closing_after_cancel = False
        self._key_shown            = False
        self._last_ui_update       = 0.0
        self._counter_lock         = threading.Lock()

        # Menu variables lazily initialized or None
        self._lang_var             = None
        self._mode_var             = None
        self._task_mode_var        = None

        # Status-label state.
        self._status_key:  str | None = None
        self._status_args: dict       = {}

        # Tk variables (key_var is in-memory only — never written to disk).
        # load_config() writes into output_dir_var / auto_open_var, so these
        # must be created before load_config() is called.
        self.key_var        = tk.StringVar()
        self.input_dir_var  = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.auto_open_var  = tk.BooleanVar(value=False)
        self.no_key_png_var = tk.BooleanVar(value=False)
        self.flatten_var    = tk.BooleanVar(value=False)

        # Load persisted (non-sensitive) settings BEFORE font/UI setup so a
        # saved language can affect the initial font choice and menu labels.
        self.load_config(silent=True)

        # Default font for ALL widgets (TkDefaultFont propagates).
        self._default_family = _pick_default_family(self.current_lang)
        self._apply_fonts()
        # Body font for the key entry; the log uses a size that is compact but readable.
        self._mono_font  = (self._default_family, 10)
        self._log_font   = (self._default_family, 8)
        self._small_font = (self._default_family, 8)

        self._build_menubar()
        self._build_body()
        self._configure_log_tags()
        self._setup_key_context_menu()
        self._setup_placeholders()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Setup drag & drop hook after window is mapped/ready
        self.root.after(100, self._setup_dnd)

        # First language pass: no log entry, no config write.
        self.apply_language(log_change=False, save=False)
        self._set_status("idle_status")


    def _apply_fonts(self) -> None:
        """Push the current language's best font into Tk's named font objects."""
        try:
            tkfont.nametofont("TkDefaultFont").configure(
                family=self._default_family, size=10
            )
            tkfont.nametofont("TkTextFont").configure(
                family=self._default_family, size=10
            )
            tkfont.nametofont("TkMenuFont").configure(
                family=self._default_family, size=10
            )
        except Exception:
            pass

    def set_window_icon(self) -> None:
        for rel in (
            os.path.join("assets", "myicon.ico"),
            os.path.join("assets", "icon", "myicon.ico"),
            "myicon.ico",
        ):
            icon_path = resource_path(rel)
            if os.path.isfile(icon_path):
                try:
                    self.root.iconbitmap(icon_path)
                    return
                except Exception as e:
                    sys.stderr.write(f"[icon] iconbitmap failed: {e}\n")
        sys.stderr.write("[icon] No icon file found in any candidate path.\n")

    # ------------------------------------------------------------------
    # Translation
    # ------------------------------------------------------------------
    def _t_lang(self, lang: str, key: str, **kwargs) -> str:
        template = TEXT.get(lang, TEXT["ko"]).get(
            key, TEXT["ko"].get(key, key)
        )
        try:
            return template.format(**kwargs) if kwargs else template
        except (KeyError, IndexError):
            return template

    def t(self, key: str, **kwargs) -> str:
        return self._t_lang(self.current_lang, key, **kwargs)

    # ------------------------------------------------------------------
    # Placeholder management
    # ------------------------------------------------------------------
    def _setup_placeholders(self) -> None:
        self.entry_key.bind("<FocusIn>", self._on_key_focus_in)
        self.entry_key.bind("<FocusOut>", self._on_key_focus_out)

        self.input_dir_var.trace_add("write", lambda *args: self._update_input_placeholder())
        self.output_dir_var.trace_add("write", lambda *args: self._update_output_placeholder())

        self._update_key_placeholder()
        self._update_input_placeholder()
        self._update_output_placeholder()

    def _update_key_placeholder(self) -> None:
        val = self.key_var.get()
        placeholder = self.t("key_placeholder")
        is_placeholder = not val
        if val:
            for l in TEXT:
                if val == TEXT[l].get("key_placeholder"):
                    is_placeholder = True
                    break
        if is_placeholder:
            self.key_var.set(placeholder)
            self.entry_key.configure(fg=COLORS["fg_dim"])
            self.entry_key.configure(show="")
        else:
            self.entry_key.configure(fg=COLORS["entry_fg"])
            if not self._key_shown:
                self.entry_key.configure(show="*")

    def _on_key_focus_in(self, event) -> None:
        val = self.key_var.get()
        is_placeholder = False
        for l in TEXT:
            if val == TEXT[l].get("key_placeholder"):
                is_placeholder = True
                break
        if is_placeholder:
            self.key_var.set("")
            self.entry_key.configure(fg=COLORS["entry_fg"])
            if not self._key_shown:
                self.entry_key.configure(show="*")

    def _on_key_focus_out(self, event) -> None:
        val = self.key_var.get().strip()
        if not val:
            self.key_var.set(self.t("key_placeholder"))
            self.entry_key.configure(fg=COLORS["fg_dim"])
            self.entry_key.configure(show="")

    def _update_input_placeholder(self) -> None:
        val = self.input_dir_var.get()
        placeholder = self.t("input_placeholder")
        is_placeholder = not val
        if val:
            for l in TEXT:
                if val == TEXT[l].get("input_placeholder"):
                    is_placeholder = True
                    break
        if is_placeholder:
            if val != placeholder:
                self.input_dir_var.set(placeholder)
            self.entry_input.configure(fg=COLORS["fg_dim"])
        else:
            self.entry_input.configure(fg=COLORS["entry_fg"])

    def _update_output_placeholder(self) -> None:
        val = self.output_dir_var.get()
        placeholder = self.t("output_placeholder")
        is_placeholder = not val
        if val:
            for l in TEXT:
                if val == TEXT[l].get("output_placeholder"):
                    is_placeholder = True
                    break
        if is_placeholder:
            if val != placeholder:
                self.output_dir_var.set(placeholder)
            self.entry_output.configure(fg=COLORS["fg_dim"])
        else:
            self.entry_output.configure(fg=COLORS["entry_fg"])


    # ------------------------------------------------------------------
    # Config (no key persistence)
    # ------------------------------------------------------------------
    def load_config(self, silent: bool = False) -> None:
        data, error = load_config_data()
        if error is not None:
            if not silent:
                self.log(self.t("config_loaded_fail", error=error))
            return

        output_dir = data.get("output_dir", "") or ""
        if output_dir:
            self.output_dir_var.set(output_dir)

        lang = data.get("language", "ko")
        if lang in TEXT:
            self.current_lang = lang

        target_mode = data.get("target_mode", "both")
        if target_mode in TARGET_MODE_TEXT_KEYS:
            self.current_target_mode = target_mode

        self.auto_open_var.set(bool(data.get("auto_open", False)))
        self.no_key_png_var.set(bool(data.get("no_key_png", False)))
        self.flatten_var.set(bool(data.get("flatten", False)))

    def save_config(self) -> bool:
        out_dir = self.output_dir_var.get()
        for l in TEXT:
            if out_dir == TEXT[l].get("output_placeholder"):
                out_dir = ""
                break
        ok, error = save_config_data(
            output_dir=out_dir,
            language=self.current_lang,
            target_mode=self.current_target_mode,
            auto_open=self.auto_open_var.get(),
            no_key_png=self.no_key_png_var.get(),
            flatten=self.flatten_var.get(),
        )
        if not ok:
            self.log(self.t("config_saved_fail", error=error))
        return ok


    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------
    def _build_menubar(self) -> None:
        # tk's option DB lets us style every cascade menu in one shot.
        self.root.option_add("*Menu.background",       COLORS["menu_bg"])
        self.root.option_add("*Menu.foreground",       COLORS["menu_fg"])
        self.root.option_add("*Menu.activeBackground", COLORS["menu_active_bg"])
        self.root.option_add("*Menu.activeForeground", COLORS["btn_fg"])
        self.root.option_add("*Menu.borderWidth",      0)
        self.root.option_add("*Menu.relief",           "flat")

        menubar = tk.Menu(self.root, tearoff=0,
                          bg=COLORS["menu_bg"], fg=COLORS["menu_fg"],
                          activebackground=COLORS["menu_active_bg"],
                          activeforeground=COLORS["btn_fg"],
                          borderwidth=0)
        self.root.configure(menu=menubar)
        self._menubar = menubar

        # Each cascade is rebuilt in apply_language(); stash references.
        self._menu_lang = tk.Menu(menubar, tearoff=0)
        self._menu_mode = tk.Menu(menubar, tearoff=0)
        self._menu_task_mode = tk.Menu(menubar, tearoff=0)

        # Index of each cascade so apply_language can re-label it.
        menubar.add_cascade(label="", menu=self._menu_lang)  # idx 0
        menubar.add_cascade(label="", menu=self._menu_mode)  # idx 1
        menubar.add_cascade(label="", menu=self._menu_task_mode) # idx 2

        self._populate_menus()

    def _populate_menus(self) -> None:
        """Fill the menubar cascades with their current items."""
        # Language
        self._menu_lang.delete(0, "end")
        for code, label in LANGUAGE_OPTIONS.items():
            self._menu_lang.add_radiobutton(
                label=label,
                value=code,
                variable=self._lang_radio_var(),
                command=lambda c=code: self.on_language_changed(c),
            )

        # Target mode
        self._menu_mode.delete(0, "end")
        for mode in TARGET_MODE_ORDER:
            self._menu_mode.add_radiobutton(
                label=self.t(TARGET_MODE_TEXT_KEYS[mode]),
                value=mode,
                variable=self._mode_radio_var(),
                command=lambda m=mode: self.on_target_mode_changed(m),
            )

        # Task mode
        self._menu_task_mode.delete(0, "end")
        for mode in ("decrypt", "encrypt", "unpack"):
            self._menu_task_mode.add_radiobutton(
                label=self.t(f"task_mode_{mode}"),
                value=mode,
                variable=self._task_mode_radio_var(),
                command=lambda m=mode: self.on_task_mode_changed(m),
            )

    # Lazily-allocated radio-button variables (one per menu).
    def _lang_radio_var(self) -> tk.StringVar:
        if self._lang_var is None:
            self._lang_var = tk.StringVar(value=self.current_lang)
        return self._lang_var

    def _mode_radio_var(self) -> tk.StringVar:
        if self._mode_var is None:
            self._mode_var = tk.StringVar(value=self.current_target_mode)
        return self._mode_var

    def _task_mode_radio_var(self) -> tk.StringVar:
        if self._task_mode_var is None:
            self._task_mode_var = tk.StringVar(value=self.current_task_mode)
        return self._task_mode_var


    def _refresh_current_language_fonts(self) -> None:
        """Apply the selected language font to widgets using explicit font tuples."""
        self._default_family = _pick_default_family(self.current_lang)
        self._mono_font  = (self._default_family, 10)
        self._log_font   = (self._default_family, 8)
        self._small_font = (self._default_family, 8)
        self._apply_fonts()

        # These widgets were created with explicit font tuples, so named-font
        # updates alone do not change them after a language switch.
        for widget, font in (
            (getattr(self, "entry_key", None), self._mono_font),
            (getattr(self, "log_area", None), self._log_font),
            (getattr(self, "chk_auto_open", None), self._small_font),
            (getattr(self, "chk_no_key_png", None), self._small_font),
            (getattr(self, "chk_flatten", None), self._small_font),
        ):
            if widget is not None:
                try:
                    widget.configure(font=font)
                except Exception:
                    pass

    # Menu handlers
    def on_language_changed(self, code: str) -> None:
        if code not in TEXT:
            return
        self.current_lang = code
        self._lang_radio_var().set(code)
        self._refresh_current_language_fonts()
        self.apply_language(log_change=True, save=True)
    def on_target_mode_changed(self, mode: str) -> None:
        if mode not in TARGET_MODE_TEXT_KEYS:
            return
        self.current_target_mode = mode
        self._mode_radio_var().set(mode)
        self.log(
            self.t("mode_changed", label=self.t(TARGET_MODE_TEXT_KEYS[mode]))
        )
        self.save_config()

    def on_task_mode_changed(self, mode: str) -> None:
        if mode not in ("decrypt", "encrypt", "unpack"):
            return
        self.current_task_mode = mode
        self._task_mode_radio_var().set(mode)
        self.log(
            self.t("mode_changed", label=self.t(f"task_mode_{mode}"))
        )
        self.save_config()

    # ------------------------------------------------------------------
    # Body layout
    # ------------------------------------------------------------------
    def _build_body(self) -> None:
        bg = COLORS["bg"]

        # Outer container — small uniform padding around everything.
        outer = tk.Frame(self.root, bg=bg)
        outer.pack(fill="both", expand=True, padx=10, pady=8)

        # ── Top: input fields grid ───────────────────────────────────
        form = tk.Frame(outer, bg=bg)
        form.pack(fill="x")
        form.grid_columnconfigure(1, weight=1)

        # Row 0: source game folder
        self.lbl_section_game = tk.Label(
            form, text="", bg=bg, fg=COLORS["fg"], anchor="w",
        )
        self.lbl_section_game.grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)

        self.entry_input = self._make_entry(form, textvariable=self.input_dir_var,
                                            state="readonly")
        self.entry_input.grid(row=0, column=1, sticky="ew", pady=4)

        self.btn_input = self._make_button(
            form, command=self.select_game_folder,
        )
        self.btn_input.grid(row=0, column=2, sticky="nsew", padx=(8, 0), pady=4)

        # Row 1: key
        self.lbl_section_key = tk.Label(
            form, text="", bg=bg, fg=COLORS["fg"], anchor="w",
        )
        self.lbl_section_key.grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)

        self.entry_key = self._make_entry(form, textvariable=self.key_var,
                                          font=self._mono_font, show="*")
        self.entry_key.grid(row=1, column=1, sticky="ew", pady=4)

        self.btn_toggle_key = self._make_button(
            form, command=self.toggle_key_visibility,
        )
        self.btn_toggle_key.grid(row=1, column=2, sticky="nsew", padx=(8, 0), pady=4)

        # Row 2: output folder
        self.lbl_section_output = tk.Label(
            form, text="", bg=bg, fg=COLORS["fg"], anchor="w",
        )
        self.lbl_section_output.grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)

        self.entry_output = self._make_entry(form, textvariable=self.output_dir_var,
                                             state="readonly")
        self.entry_output.grid(row=2, column=1, sticky="ew", pady=4)

        self.btn_output = self._make_button(
            form, command=self.select_output_folder,
        )
        self.btn_output.grid(row=2, column=2, sticky="nsew", padx=(8, 0), pady=4)

        # Force a consistent label-column width so all three rows align.
        form.grid_columnconfigure(0, minsize=70)
        form.grid_columnconfigure(2, minsize=60)

        # ── Checkboxes ────────────────────────────────────────────────
        chk_frame = tk.Frame(outer, bg=bg)
        chk_frame.pack(fill="x", pady=(8, 0))

        self.chk_auto_open = tk.Checkbutton(
            chk_frame, text="", variable=self.auto_open_var,
            bg=bg, fg=COLORS["fg"],
            activebackground=bg, activeforeground=COLORS["fg"],
            selectcolor=COLORS["entry_bg"],
            highlightthickness=0, bd=0, anchor="w",
            font=self._small_font,
            command=self.save_config,
        )
        self.chk_auto_open.pack(side="left", padx=(0, 20))

        self.chk_no_key_png = tk.Checkbutton(
            chk_frame, text="", variable=self.no_key_png_var,
            bg=bg, fg=COLORS["fg"],
            activebackground=bg, activeforeground=COLORS["fg"],
            selectcolor=COLORS["entry_bg"],
            highlightthickness=0, bd=0, anchor="w",
            font=self._small_font,
            command=self.save_config,
        )
        self.chk_no_key_png.pack(side="left", padx=(0, 20))

        self.chk_flatten = tk.Checkbutton(
            chk_frame, text="", variable=self.flatten_var,
            bg=bg, fg=COLORS["fg"],
            activebackground=bg, activeforeground=COLORS["fg"],
            selectcolor=COLORS["entry_bg"],
            highlightthickness=0, bd=0, anchor="w",
            font=self._small_font,
            command=self.save_config,
        )
        self.chk_flatten.pack(side="left", padx=(0, 20))

        # ── Run button ───────────────────────────────────────────────
        self.btn_run = self._make_button(outer, command=self.start_processing,
                                          height=2)
        self.btn_run.pack(fill="x", pady=(10, 4))

        # ── Progress bar ─────────────────────────────────────────────
        self._setup_progressbar_style()
        self.progress_bar = ttk.Progressbar(
            outer, mode="determinate", style="Decrypter.Horizontal.TProgressbar",
        )
        self.progress_bar.pack(fill="x", pady=(0, 2))

        # ── Status label ─────────────────────────────────────────────
        self.lbl_status = tk.Label(
            outer, text="", bg=bg, fg=COLORS["fg_dim"], anchor="w",
        )
        self.lbl_status.pack(fill="x", pady=(0, 8))

        # ── Log header (LOG  Copy  Clear) ────────────────────────────
        log_header = tk.Frame(outer, bg=bg)
        log_header.pack(fill="x")

        self.lbl_log_header = tk.Label(
            log_header, text="", bg=bg, fg=COLORS["fg"], anchor="w",
        )
        self.lbl_log_header.pack(side="left")

        self.btn_log_clear = self._make_button(log_header, command=self.clear_log,
                                                width=8)
        self.btn_log_clear.pack(side="right", padx=(4, 0))

        self.btn_log_copy = self._make_button(log_header, command=self.copy_log,
                                               width=8)
        self.btn_log_copy.pack(side="right")

        # ── Log textbox (fills remaining space) ──────────────────────
        log_frame = tk.Frame(outer, bg=COLORS["surface"], bd=1, relief="flat",
                              highlightthickness=1,
                              highlightbackground=COLORS["border"])
        log_frame.pack(fill="both", expand=True, pady=(4, 0))

        scrollbar = tk.Scrollbar(log_frame)
        scrollbar.pack(side="right", fill="y")

        self.log_area = tk.Text(
            log_frame, wrap="word", state="disabled",
            bg=COLORS["surface"], fg=COLORS["fg"],
            insertbackground=COLORS["fg"],
            selectbackground=COLORS["btn_active"],
            selectforeground=COLORS["btn_fg"],
            relief="flat", bd=0, padx=6, pady=4,
            font=self._log_font,
            yscrollcommand=scrollbar.set,
        )
        self.log_area.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.log_area.yview)


    # ------------------------------------------------------------------
    # Widget factories (consistent gray styling)
    # ------------------------------------------------------------------
    def _make_entry(self, parent, **kwargs) -> tk.Entry:
        defaults = dict(
            bg=COLORS["entry_bg"], fg=COLORS["entry_fg"],
            disabledbackground=COLORS["entry_bg"],
            disabledforeground=COLORS["fg_dim"],
            readonlybackground=COLORS["entry_bg"],
            insertbackground=COLORS["entry_fg"],
            selectbackground=COLORS["btn_active"],
            selectforeground=COLORS["btn_fg"],
            relief="flat", bd=2,
            highlightthickness=1,
            highlightbackground=COLORS["border"],
            highlightcolor=COLORS["border"],
        )
        defaults.update(kwargs)
        return tk.Entry(parent, **defaults)

    def _make_button(self, parent, **kwargs) -> tk.Button:
        # Zero padding + zero border so the button renders at the absolute
        # minimum height (matches adjacent tk.Entry rows). The Run button
        # gets its own prominence via an explicit `height=2` override.
        defaults = dict(
            text="", bg=COLORS["btn_bg"], fg=COLORS["btn_fg"],
            activebackground=COLORS["btn_active"],
            activeforeground=COLORS["btn_fg"],
            disabledforeground=COLORS["fg_dim"],
            relief="flat", bd=0,
            padx=6, pady=0,
            highlightthickness=0,
        )
        defaults.update(kwargs)
        return tk.Button(parent, **defaults)

    def _setup_progressbar_style(self) -> None:
        style = ttk.Style(self.root)
        # 'clam' is the only built-in theme that respects custom colors
        # for ttk.Progressbar trough/bar.
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "Decrypter.Horizontal.TProgressbar",
            troughcolor=COLORS["entry_bg"],
            background=COLORS["btn_active"],
            bordercolor=COLORS["border"],
            lightcolor=COLORS["btn_active"],
            darkcolor=COLORS["btn_active"],
        )

    # ------------------------------------------------------------------
    # Language application — re-text everything in one pass
    # ------------------------------------------------------------------
    def apply_language(self, log_change: bool = True, save: bool = True) -> None:
        self.root.title(f"{self.t('window_title')} v{APP_VERSION}")

        # Menubar cascade titles
        self._menubar.entryconfigure(0, label=self.t("menu_language"))
        self._menubar.entryconfigure(1, label=self.t("menu_mode"))
        self._menubar.entryconfigure(2, label=self.t("menu_task_mode"))

        # Repopulate so target_mode items pick up the new language.
        self._populate_menus()
        self._lang_radio_var().set(self.current_lang)
        self._mode_radio_var().set(self.current_target_mode)
        self._task_mode_radio_var().set(self.current_task_mode)

        # Update placeholders if they are active
        for var, key in (
            (self.input_dir_var, "input_placeholder"),
            (self.output_dir_var, "output_placeholder"),
            (self.key_var, "key_placeholder"),
        ):
            val = var.get()
            is_placeholder = not val
            if not is_placeholder:
                for l in TEXT:
                    if val == TEXT[l].get(key):
                        is_placeholder = True
                        break
            if is_placeholder:
                var.set(self.t(key))

        # Section labels + buttons
        self.lbl_section_game.configure(text=self.t("section_game"))
        self.lbl_section_key.configure(text=self.t("key_label"))
        self.lbl_section_output.configure(text=self.t("section_output"))

        self.btn_input.configure(text=self.t("folder_button_game"))
        self.btn_output.configure(text=self.t("folder_button_output"))
        self.btn_toggle_key.configure(
            text=self.t("key_hide" if self._key_shown else "key_show")
        )

        self.chk_auto_open.configure(text=self.t("auto_open_label"))
        self.chk_no_key_png.configure(text=self.t("no_key_png_label"))
        self.chk_flatten.configure(text=self.t("flatten_label"))

        # Run / Cancel button — keep current state's text.
        if not self.is_processing:
            self.btn_run.configure(text=self.t("run_button"))
        elif self._cancel_event.is_set():
            self.btn_run.configure(text=self.t("cancelling_button"))
        else:
            self.btn_run.configure(text=self.t("cancel_button"))

        # Log header
        self.lbl_log_header.configure(text=self.t("log_header"))
        self.btn_log_copy.configure(text=self.t("log_copy"))
        self.btn_log_clear.configure(text=self.t("log_clear"))

        # Status label re-render in the new language.
        self._render_status()

        if log_change:
            self.log(self.t("lang_changed"))
        if save:
            self.save_config()

    # ------------------------------------------------------------------
    # Status label
    # ------------------------------------------------------------------
    def _set_status(self, key: str | None = None, **kwargs) -> None:
        self._status_key  = key
        self._status_args = kwargs
        self._render_status()

    def _render_status(self) -> None:
        if self._status_key is None:
            text = ""
        else:
            text = (
                self.t(self._status_key, **self._status_args)
                if self._status_args
                else self.t(self._status_key)
            )
        # Color by status: success -> green, cancel -> warning, else neutral.
        if self._status_key == "complete_status":
            color = COLORS["log_success"]
        elif self._status_key == "cancel_status":
            color = COLORS["log_warning"]
        else:
            color = COLORS["fg_dim"]
        try:
            self.lbl_status.configure(text=text, fg=color)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Right-click context menu on key entry (Cut / Copy / Paste)
    # ------------------------------------------------------------------
    def _setup_key_context_menu(self) -> None:
        self._key_context_menu = tk.Menu(self.entry_key, tearoff=0)
        self._key_context_menu.add_command(label="", command=self._ctx_cut)
        self._key_context_menu.add_command(label="", command=self._ctx_copy)
        self._key_context_menu.add_command(label="", command=self._ctx_paste)
        self.entry_key.bind("<Button-3>", self._show_key_context_menu)

    def _show_key_context_menu(self, event) -> None:
        self._key_context_menu.entryconfigure(0, label=self.t("ctx_cut"))
        self._key_context_menu.entryconfigure(1, label=self.t("ctx_copy"))
        self._key_context_menu.entryconfigure(2, label=self.t("ctx_paste"))
        try:
            self._key_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._key_context_menu.grab_release()

    def _ctx_cut(self) -> None:
        try:
            self.entry_key.event_generate("<<Cut>>")
        except Exception:
            pass

    def _ctx_copy(self) -> None:
        try:
            self.entry_key.event_generate("<<Copy>>")
        except Exception:
            pass

    def _ctx_paste(self) -> None:
        try:
            self.entry_key.event_generate("<<Paste>>")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Folder selection / key auto-detect
    # ------------------------------------------------------------------
    def select_output_folder(self) -> None:
        folder = filedialog.askdirectory(
            parent=self.root, title=self.t("select_output_dialog")
        )
        if folder:
            self.output_dir_var.set(folder)
            self.save_config()

    def open_output_folder(self, subdir: str = "") -> None:
        base = self.output_dir_var.get().strip()
        for l in TEXT:
            if base == TEXT[l].get("output_placeholder"):
                base = ""
                break
        if not base:
            return
        target = os.path.join(base, subdir) if subdir else base
        if os.path.isdir(target):
            os.startfile(target)
        elif os.path.isdir(base):
            os.startfile(base)


    def select_game_folder(self) -> None:
        if self.current_task_mode == "unpack":
            selected_file = filedialog.askopenfilename(
                parent=self.root,
                title=self.t("select_game_dialog"),
                filetypes=[
                    ("RPG Maker Archive", "*.rgss3a *.rgss2a *.rgssad"),
                    ("All Files", "*.*")
                ]
            )
            if not selected_file:
                return
            self.input_dir_var.set(selected_file)
            return

        selected_dir = filedialog.askdirectory(
            parent=self.root, title=self.t("select_game_dialog")
        )
        if not selected_dir:
            return

        if not self._looks_like_rpg_folder(selected_dir):
            if not messagebox.askyesno(
                self.t("not_rpg_folder_title"),
                self.t("not_rpg_folder_msg"),
                parent=self.root,
                icon="warning",
            ):
                return

        # Autocorrect: if "<root>/www/img" exists this is an MV layout.
        input_dir = (
            os.path.join(selected_dir, "www")
            if os.path.exists(os.path.join(selected_dir, "www", "img"))
            else selected_dir
        )
        self.input_dir_var.set(input_dir)

        scan: SystemJsonScan = extract_key_from_system_json(selected_dir)

        self.log(self.t("key_search_header"))
        for path, status_key, extra in scan.attempts:
            status_text = self._format_key_status(status_key, extra)
            self.log(self.t("key_search_path_check", path=path, status=status_text))

        if scan.key:
            self.key_var.set(scan.key)
            self.log(self.t("key_found", key=mask_key(scan.key)))
        else:
            # Try to recover key from PNG
            from rpg_core import recover_key_from_png
            recovered_key = None
            for r, _, files in os.walk(input_dir):
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in (".rpgmvp", ".png_"):
                        test_path = os.path.join(r, f)
                        recovered_key = recover_key_from_png(test_path)
                        if recovered_key:
                            break
                if recovered_key:
                    break
            if recovered_key:
                self.key_var.set(recovered_key)
                self.log(self.t("key_recovered_log", key=mask_key(recovered_key)))
            elif scan.found_system_json:
                if not scan.has_encrypted_images and not scan.has_encrypted_audio:
                    self.log(self.t("unencrypted_game"))
                else:
                    self.log(self.t("encrypted_no_key"))
            else:
                self.log(self.t("key_recovery_fail_log"))

    @staticmethod
    def _looks_like_rpg_folder(path: str) -> bool:
        try:
            return any(
                os.path.isdir(os.path.join(path, ind))
                for ind in RPG_FOLDER_INDICATORS
            )
        except Exception:
            return False

    _KEY_STATUS_TRANS = {
        "not_found":   "status_not_found",
        "key_missing": "status_key_missing",
        "key_empty":   "status_key_empty",
        "key_non_hex": "status_key_non_hex",
        "ok":          "status_ok",
    }

    def _format_key_status(self, status: str, extra) -> str:
        if status == "read_error":
            return self.t("status_read_error", error=extra)
        if status == "key_bad_length":
            return self.t("status_key_bad_length", length=extra)
        text_key = self._KEY_STATUS_TRANS.get(status)
        return self.t(text_key) if text_key else status

    def _format_decrypt_error(self, reason: tuple[str, str], run_lang: str) -> str:
        code, detail = reason
        if code == "io_error":
            return self._t_lang(run_lang, "io_error", error=detail)
        if code == "raw_error":
            if detail in ("unknown_error", "key_too_short"):
                return self._t_lang(run_lang, detail)
            return str(detail)
        if code in ("bad_png", "bad_ogg", "bad_m4a", "unknown_error"):
            return self._t_lang(run_lang, code)
        return str(code)


    # ------------------------------------------------------------------
    # Key visibility toggle
    # ------------------------------------------------------------------
    def toggle_key_visibility(self) -> None:
        self._key_shown = not self._key_shown
        # Empty show="" means "render the actual character".
        try:
            self.entry_key.configure(show="" if self._key_shown else "*")
        except Exception:
            pass
        self.btn_toggle_key.configure(
            text=self.t("key_hide" if self._key_shown else "key_show")
        )

    # ------------------------------------------------------------------
    # Log helpers
    # ------------------------------------------------------------------
    def copy_log(self) -> None:
        try:
            self.log_area.configure(state="normal")
            content = self.log_area.get("1.0", tk.END)
            self.log_area.configure(state="disabled")
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
        except Exception:
            pass

    def clear_log(self) -> None:
        """Erase all log text. No confirm prompt — the user explicitly asked
        for a one-click clear; bringing the log back is just re-running."""
        try:
            self.log_area.configure(state="normal")
            self.log_area.delete("1.0", tk.END)
            self.log_area.configure(state="disabled")
        except Exception:
            pass

    def log(self, message: str) -> None:
        self.root.after(0, lambda: self._append_log(message))

    @staticmethod
    def _detect_severity(message: str) -> str | None:
        msg = message.lstrip()
        for severity, prefixes in SEVERITY_PREFIXES.items():
            for prefix in prefixes:
                if msg.startswith(prefix):
                    return severity
        return None

    def _configure_log_tags(self) -> None:
        if not hasattr(self, "log_area"):
            return
        for severity, color_key in (
            ("info",    "log_info"),
            ("warning", "log_warning"),
            ("error",   "log_error"),
            ("success", "log_success"),
        ):
            try:
                self.log_area.tag_config(severity, foreground=COLORS[color_key])
            except Exception:
                pass

    def _append_log(self, message: str) -> None:
        try:
            self.log_area.configure(state="normal")
            severity   = self._detect_severity(message)
            line_start = self.log_area.index("end-1c")
            self.log_area.insert(tk.END, message + "\n")
            if severity:
                line_end = self.log_area.index("end-1c")
                try:
                    self.log_area.tag_add(severity, line_start, line_end)
                except Exception:
                    pass
            try:
                line_count = int(self.log_area.index("end-1c").split(".")[0])
                if line_count > LOG_MAX_LINES:
                    delete_to = line_count - LOG_TRIM_TARGET
                    self.log_area.delete("1.0", f"{delete_to}.0")
            except Exception:
                pass
            self.log_area.see(tk.END)
            self.log_area.configure(state="disabled")
        except Exception as e:
            sys.stderr.write(f"[log] Error appending log: {e}\n")

    # ------------------------------------------------------------------
    # Run / cancel / worker thread
    # ------------------------------------------------------------------
    def start_processing(self) -> None:
        key        = self.key_var.get().strip()
        input_dir  = self.input_dir_var.get().strip()
        output_dir = self.output_dir_var.get().strip()

        # Filter out placeholder strings
        for l in TEXT:
            if key == TEXT[l].get("key_placeholder"):
                key = ""
            if input_dir == TEXT[l].get("input_placeholder"):
                input_dir = ""
            if output_dir == TEXT[l].get("output_placeholder"):
                output_dir = ""

        # Validate input/output based on task mode
        if self.current_task_mode == "unpack":
            if not input_dir or not output_dir:
                messagebox.showwarning(
                    self.t("warning_title"), self.t("missing_fields"), parent=self.root
                )
                return
            if not os.path.isfile(input_dir):
                messagebox.showwarning(
                    self.t("warning_title"), self.t("invalid_input_dir"), parent=self.root
                )
                return
            try:
                os.makedirs(output_dir, exist_ok=True)
            except Exception:
                messagebox.showwarning(
                    self.t("warning_title"), self.t("invalid_output_dir"), parent=self.root
                )
                return
        else:
            # decrypt or encrypt
            # If no_key_png is enabled in decrypt, key can be empty or invalid
            allow_missing_key = (self.current_task_mode == "decrypt" and self.no_key_png_var.get())
            if not input_dir or not output_dir or (not key and not allow_missing_key):
                messagebox.showwarning(
                    self.t("warning_title"), self.t("missing_fields"), parent=self.root
                )
                return

            if key:
                key_ok, key_msg = validate_key(key)
                if not key_ok and not allow_missing_key:
                    messagebox.showwarning(
                        self.t("warning_title"), self.t(key_msg), parent=self.root
                    )
                    return

            path_ok, path_msg = validate_paths(input_dir, output_dir)
            if not path_ok:
                messagebox.showwarning(
                    self.t("warning_title"), self.t(path_msg), parent=self.root
                )
                return

        self.is_processing   = True
        with self._counter_lock:
            self.processed_files = 0
        self.total_files     = 0
        self._last_ui_update = 0.0
        self._cancel_event.clear()

        # Re-purpose the run button as a cancel button.
        self.btn_run.configure(
            text=self.t("cancel_button"),
            command=self.cancel_processing,
        )

        # Indeterminate scanning phase.
        try:
            self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start(20)
        except Exception:
            pass
        self._set_status("scan_status")

        self.save_config()

        worker = threading.Thread(
            target=self.process_files,
            args=(
                key,
                input_dir,
                output_dir,
                self.current_target_mode,
                self.current_lang,
                self.current_task_mode,
                self.no_key_png_var.get(),
                self.flatten_var.get()
            ),
            daemon=True,
        )
        worker.start()


    def cancel_processing(self) -> None:
        self._cancel_event.set()
        try:
            self.btn_run.configure(state="disabled", text=self.t("cancelling_button"))
        except Exception:
            pass

    def process_files(
        self,
        key: str,
        input_dir: str,
        output_dir: str,
        target_mode: str,
        run_lang: str,
        task_mode: str = "decrypt",
        no_key_png: bool = False,
        flatten: bool = False,
    ) -> None:
        """Worker entry point: scan, process, summarise based on task_mode."""
        if task_mode == "decrypt":
            self.log(self._t_lang(run_lang, "start_log"))
        elif task_mode == "encrypt":
            self.log(self._t_lang(run_lang, "encrypt_start_log"))
        elif task_mode == "unpack":
            self.log(self._t_lang(run_lang, "unpack_start_log"))

        try:
            if task_mode == "unpack":
                self._run_unpack_loop(input_dir, output_dir, run_lang, flatten)
            elif task_mode == "encrypt":
                self._run_encrypt_loop(key, input_dir, output_dir, target_mode, run_lang, flatten)
            else:
                # decrypt mode
                target_files, unsupported_count, plain_media_counts = self._scan_files(
                    input_dir, target_mode, run_lang
                )

                if any(plain_media_counts.values()):
                    self.log(
                        self._t_lang(
                            run_lang,
                            "plain_media_summary",
                            png=plain_media_counts[".png"],
                            ogg=plain_media_counts[".ogg"],
                            m4a=plain_media_counts[".m4a"],
                        )
                    )

                self.total_files = len(target_files)
                self.root.after(0, self._end_scan_phase)

                if self.total_files == 0:
                    self.log(self._t_lang(run_lang, "no_files"))
                    return

                self.log(self._t_lang(run_lang, "count_log", total=self.total_files))
                self.log(
                    self._t_lang(run_lang, "progress_log", percent=0, processed=0, total=self.total_files)
                )

                stats = self._run_decrypt_loop(
                    target_files, key, input_dir, output_dir, run_lang, no_key_png, flatten
                )

                if not stats["cancelled_in_loop"]:
                    self._log_summary(stats, unsupported_count, run_lang)
                    self.root.after(
                        0,
                        lambda s=stats: self._show_completion_notification(s),
                    )
        except Exception as e:
            err_msg = self._t_lang(run_lang, "fatal_error", error=e)
            self.log(err_msg)
            self.root.after(
                0,
                lambda m=err_msg: messagebox.showerror(
                    self._t_lang(run_lang, "error_title"), m, parent=self.root
                ),
            )
        finally:
            self.finish_processing()

    def _run_encrypt_loop(
        self,
        key: str,
        input_dir: str,
        output_dir: str,
        target_mode: str,
        run_lang: str,
        flatten: bool = False,
    ) -> None:
        self.log(self._t_lang(run_lang, "scan_log"))
        
        target_exts = PLAIN_MEDIA_EXTS_BY_TARGET.get(target_mode, PLAIN_MEDIA_EXTS_BY_TARGET["both"])
        target_files = []
        
        for root_dir, _, files in os.walk(input_dir):
            if self._cancel_event.is_set():
                break
            for filename in files:
                ext = os.path.splitext(filename)[1].lower()
                if ext in target_exts:
                    full_path = os.path.join(root_dir, filename)
                    if os.path.islink(full_path):
                        continue
                    target_files.append((root_dir, filename, ext))
                    
        self.total_files = len(target_files)
        self.root.after(0, self._end_scan_phase)
        
        if self.total_files == 0:
            self.log(self._t_lang(run_lang, "no_files"))
            return
            
        self.log(self._t_lang(run_lang, "count_log", total=self.total_files))
        self.log(
            self._t_lang(run_lang, "progress_log", percent=0, processed=0, total=self.total_files)
        )
        
        # Auto-detect MV vs MZ layout
        is_mz = False
        for r, _, files in os.walk(input_dir):
            for f in files:
                e = os.path.splitext(f)[1].lower()
                if e in (".png_", ".ogg_", ".m4a_"):
                    is_mz = True
                    break
                elif e in (".rpgmvp", ".rpgmvo", ".rpgmvm"):
                    break
            if is_mz:
                break
                
        if is_mz:
            enc_map = {".png": ".png_", ".ogg": ".ogg_", ".m4a": ".m4a_"}
        else:
            enc_map = {".png": ".rpgmvp", ".ogg": ".rpgmvo", ".m4a": ".rpgmvm"}
            
        try:
            key_bytes = bytes.fromhex(key)
        except Exception:
            key_bytes = b"\x00" * 16
        game_name = self._compute_game_name(input_dir)
        tasks = self._prepare_tasks(
            target_files, input_dir, output_dir, game_name, flatten, enc_map
        )
        
        success_count = fail_count = skip_count = 0
        failed_files = []
        last_bucket = 0
        cancelled_in_loop = False
        start_time = time.monotonic()
        total = self.total_files
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=DECRYPT_WORKERS) as ex:
            futures = {
                ex.submit(encrypt_asset, ip, op, key_bytes): (ip, op, ext)
                for ip, op, ext in tasks
            }
            try:
                for fut in concurrent.futures.as_completed(futures):
                    if self._cancel_event.is_set():
                        cancelled_in_loop = True
                        self.log(self._t_lang(run_lang, "cancel_log"))
                        break
                        
                    input_path, output_path, ext = futures[fut]
                    try:
                        ok, reason = fut.result()
                    except Exception as e:
                        ok, reason = False, ("raw_error", str(e) or "unknown_error")
                        
                    with self._counter_lock:
                        self.processed_files += 1
                        
                    if ok:
                        success_count += 1
                    else:
                        fail_count += 1
                        failed_files.append((input_path, self._format_decrypt_error(reason, run_lang)))
                        
                    last_bucket = self._maybe_log_progress(total, last_bucket, run_lang)
                    self._maybe_emit_ui_update(total, start_time)
            finally:
                if cancelled_in_loop:
                    ex.shutdown(wait=False, cancel_futures=True)
                    
        stats = {
            "success_count": success_count,
            "fail_count": fail_count,
            "skip_count": skip_count,
            "failed_files": failed_files,
            "cancelled_in_loop": cancelled_in_loop,
            "total": total,
            "game_name": game_name,
        }
        
        if not cancelled_in_loop:
            self._log_summary(stats, 0, run_lang)
            self.root.after(0, lambda: self._show_completion_notification(stats))

    def _run_unpack_loop(
        self,
        archive_path: str,
        output_dir: str,
        run_lang: str,
        flatten: bool = False,
    ) -> None:
        self.log(self._t_lang(run_lang, "unpack_status", processed=0, total=0).split("...")[0] + "...")
        
        with RGSSArchive.open(archive_path) as archive:
            entries = archive.entries
            self.total_files = len(entries)
            self.root.after(0, self._end_scan_phase)
            
            if self.total_files == 0:
                self.log(self._t_lang(run_lang, "no_files"))
                return
                
            self.log(self._t_lang(run_lang, "count_log", total=self.total_files))
            
            success_count = 0
            coder = RGSSCoder()
            start_time = time.monotonic()
            
            for idx, entry in enumerate(entries):
                if self._cancel_event.is_set():
                    self.log(self._t_lang(run_lang, "cancel_log"))
                    break
                    
                name = entry.name
                if flatten:
                    name = os.path.basename(name)
                    
                out_path = os.path.join(output_dir, name)
                out_path = unique_output_path(out_path)
                
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                
                try:
                    with open(out_path, "wb") as fout:
                        coder.copy(archive.stream, fout, entry.data, self._cancel_event)
                    if self._cancel_event.is_set():
                        if os.path.exists(out_path):
                            try:
                                os.remove(out_path)
                            except Exception:
                                pass
                        break
                    success_count += 1
                except Exception as e:
                    self.log(f"[!] {entry.name} extraction failed: {e}")
                    
                with self._counter_lock:
                    self.processed_files += 1
                    
                # UI progress updates
                if idx % 10 == 0 or idx == self.total_files - 1:
                    self._maybe_emit_ui_update(self.total_files, start_time)
            
            if not self._cancel_event.is_set():
                self.log(self._t_lang(run_lang, "unpack_success_log", success=success_count))
                self.root.after(0, lambda: self._show_completion_notification({"game_name": ""}))


    def _scan_files(
        self, input_dir: str, target_mode: str, run_lang: str
    ) -> tuple[list[tuple[str, str, str]], int, dict[str, int]]:
        self.log(self._t_lang(run_lang, "scan_log"))

        target_exts      = get_target_extensions(target_mode)
        plain_media_exts = PLAIN_MEDIA_EXTS_BY_TARGET.get(
            target_mode, PLAIN_MEDIA_EXTS_BY_TARGET["both"]
        )

        target_files: list[tuple[str, str, str]] = []
        unsupported_count                        = 0
        plain_media_counts                       = {".png": 0, ".ogg": 0, ".m4a": 0}

        for root_dir, _, files in os.walk(input_dir):
            if self._cancel_event.is_set():
                return [], 0, {".png": 0, ".ogg": 0, ".m4a": 0}
            for filename in files:
                ext       = os.path.splitext(filename)[1].lower()
                full_path = os.path.join(root_dir, filename)

                if ext in EXT_MAP:
                    if ext not in target_exts:
                        continue
                    if os.path.islink(full_path):
                        continue
                    target_files.append((root_dir, filename, ext))
                elif ext in KNOWN_UNSUPPORTED_EXT:
                    unsupported_count += 1
                elif ext in PLAIN_MEDIA_EXT and ext in plain_media_exts:
                    plain_media_counts[ext] += 1

        return target_files, unsupported_count, plain_media_counts


    @staticmethod
    def _compute_game_name(input_dir: str) -> str:
        base = os.path.basename(input_dir)
        name = os.path.basename(os.path.dirname(input_dir)) if base == "www" else base
        return "" if name in ("", ".", "..") else name

    @staticmethod
    def _compute_target_dir(
        input_dir: str, output_dir: str, root_dir: str, game_name: str
    ) -> str:
        relative_dir = os.path.relpath(root_dir, input_dir)
        parts = pathlib.PurePath(relative_dir).parts
        new_parts = list(parts)
        if game_name:
            for i, p in enumerate(parts):
                if p in ("img", "audio"):
                    new_parts.insert(i, game_name)
                    break
        sub = os.path.join(*new_parts) if new_parts else relative_dir
        return os.path.join(output_dir, sub)

    def _prepare_tasks(
        self,
        target_files: list[tuple[str, str, str]],
        input_dir: str,
        output_dir: str,
        game_name: str,
        flatten: bool = False,
        custom_ext_map: dict[str, str] | None = None,
    ) -> list[tuple[str, str, str]]:
        """Build (input_path, output_path, ext) tuples and ensure target dirs exist.

        Always uses unique_output_path: with the overwrite option removed,
        same-name outputs always get a `_1`, `_2`... suffix to preserve
        prior runs.
        """
        ext_map = custom_ext_map or EXT_MAP
        tasks: list[tuple[str, str, str]] = []
        for root_dir, filename, ext in target_files:
            input_path = os.path.join(root_dir, filename)
            if flatten:
                target_dir = output_dir
            else:
                target_dir = self._compute_target_dir(
                    input_dir, output_dir, root_dir, game_name
                )
            if os.path.islink(target_dir):
                continue
            os.makedirs(target_dir, exist_ok=True)
            stem, _   = os.path.splitext(filename)
            desired   = os.path.join(target_dir, stem + ext_map.get(ext, ext))
            if os.path.islink(desired):
                continue
            output_path = unique_output_path(desired)
            tasks.append((input_path, output_path, ext))
        return tasks


    def _maybe_log_progress(self, total: int, last_bucket: int, run_lang: str) -> int:
        with self._counter_lock:
            processed = self.processed_files
        percent = int((processed / total) * 100)
        bucket  = (percent // PROGRESS_LOG_BUCKET) * PROGRESS_LOG_BUCKET
        if bucket > last_bucket or processed == total:
            self.log(
                self._t_lang(
                    run_lang,
                    "progress_log",
                    percent=percent,
                    processed=processed,
                    total=total,
                )
            )
            return bucket
        return last_bucket


    def _maybe_emit_ui_update(self, total: int, start_time: float) -> None:
        now = time.monotonic()
        with self._counter_lock:
            processed = self.processed_files
        if (
            now - self._last_ui_update < UI_THROTTLE_SEC
            and processed != total
        ):
            return
        self._last_ui_update = now

        elapsed = now - start_time
        if processed >= 3 and elapsed > 0:
            avg = elapsed / processed
            eta_seconds = max(0, (total - processed) * avg)
        else:
            eta_seconds = None

        pct       = processed / total
        percent   = int(pct * 100)
        self.root.after(
            0,
            lambda v=pct, p=processed, t=total, pc=percent, e=eta_seconds:
                self._update_progress(v, p, t, pc, e),
        )


    def _run_decrypt_loop(
        self,
        target_files: list[tuple[str, str, str]],
        key: str,
        input_dir: str,
        output_dir: str,
        run_lang: str,
        no_key_png: bool = False,
        flatten: bool = False,
    ) -> dict:
        """Decrypt every file in *target_files* using a thread pool."""
        success_count = fail_count = skip_count = 0
        failed_files: list[tuple[str, str]] = []
        last_bucket = 0
        cancelled_in_loop = False

        start_time = time.monotonic()
        try:
            key_bytes = bytes.fromhex(key)
        except Exception:
            key_bytes = b"\x00" * 16
        game_name  = self._compute_game_name(input_dir)
        tasks      = self._prepare_tasks(
            target_files, input_dir, output_dir, game_name, flatten
        )
        total = self.total_files

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=DECRYPT_WORKERS
        ) as ex:
            futures = {
                ex.submit(decrypt_asset, ip, op, key_bytes): (ip, op, ext)
                for ip, op, ext in tasks
            }
            try:
                for fut in concurrent.futures.as_completed(futures):
                    if self._cancel_event.is_set():
                        cancelled_in_loop = True
                        self.log(self._t_lang(run_lang, "cancel_log"))
                        break

                    input_path, output_path, ext = futures[fut]
                    try:
                        ok, reason = fut.result()
                    except Exception as e:
                        ok, reason = False, ("raw_error", str(e) or "unknown_error")

                    if not ok and no_key_png and ext in IMAGE_EXTS:
                        ok, reason = restore_png_no_key(input_path, output_path)

                    with self._counter_lock:
                        self.processed_files += 1
                    if ok:
                        success_count += 1
                    elif reason[0] in SKIP_REASONS:
                        skip_count += 1
                    else:
                        fail_count += 1
                        failed_files.append(
                            (input_path, self._format_decrypt_error(reason, run_lang))
                        )

                    last_bucket = self._maybe_log_progress(total, last_bucket, run_lang)
                    self._maybe_emit_ui_update(total, start_time)
            finally:
                if cancelled_in_loop:
                    ex.shutdown(wait=False, cancel_futures=True)

        return {
            "success_count":     success_count,
            "fail_count":        fail_count,
            "skip_count":        skip_count,
            "failed_files":      failed_files,
            "cancelled_in_loop": cancelled_in_loop,
            "total":             total,
            "game_name":         game_name,
        }


    def _log_summary(self, stats: dict, unsupported_count: int, run_lang: str) -> None:
        self.log(
            self._t_lang(
                run_lang,
                "done_log",
                success=stats["success_count"],
                failed=stats["fail_count"],
                skipped=stats["skip_count"] + unsupported_count,
                total=stats["total"],
            )
        )
        if stats["fail_count"] == 0:
            self.log(self._t_lang(run_lang, "done_all_success"))
        else:
            self.log(self._t_lang(run_lang, "done_some_failed"))
            self.log(self._t_lang(run_lang, "failed_files_header"))
            for path, reason in stats["failed_files"]:
                self.log(self._t_lang(run_lang, "file_failed", path=path, reason=reason))


    def _update_progress(
        self,
        value: float,
        processed: int,
        total: int,
        percent: int,
        eta_seconds: float | None,
    ) -> None:
        try:
            # ttk progressbar is 0..100 in determinate mode.
            self.progress_bar.configure(value=value * 100.0)
        except Exception:
            pass
        if self.current_task_mode == "unpack":
            self._set_status(
                "unpack_status",
                processed=processed,
                total=total,
            )
        elif self.current_task_mode == "encrypt":
            self._set_status(
                "encrypt_status",
                processed=processed,
                total=total,
                percent=percent,
                eta=self._format_eta(eta_seconds),
            )
        else:
            self._set_status(
                "decrypt_status",
                processed=processed,
                total=total,
                percent=percent,
                eta=self._format_eta(eta_seconds),
            )

    def _format_eta(self, seconds: float | None) -> str:
        if seconds is None or seconds < 0:
            return self.t("eta_unknown")
        s_total = int(seconds)
        if s_total < 60:
            return self.t("eta_seconds", s=s_total)
        m, s = divmod(s_total, 60)
        if m < 60:
            return self.t("eta_min_sec", m=m, s=s)
        h, m = divmod(m, 60)
        return self.t("eta_hour_min", h=h, m=m)

    def _end_scan_phase(self) -> None:
        try:
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate", value=0)
        except Exception:
            pass

    def _show_completion_notification(self, stats: dict) -> None:
        if self._closing_after_cancel:
            return

        self.root.bell()

        if self.auto_open_var.get():
            self.open_output_folder(subdir=stats.get("game_name", ""))

    def finish_processing(self) -> None:
        def _reset() -> None:
            cancelled = self._cancel_event.is_set()
            self.is_processing = False

            try:
                self.progress_bar.stop()
                self.progress_bar.configure(mode="determinate")
                self.progress_bar.configure(
                    value=0 if (cancelled or self.total_files == 0) else 100.0
                )
            except Exception:
                pass

            self.btn_run.configure(
                state="normal",
                text=self.t("run_button"),
                command=self.start_processing,
            )

            if cancelled:
                self._set_status("cancel_status")
            elif self.total_files > 0:
                if self.current_task_mode == "unpack":
                    self._set_status("unpack_complete_status")
                elif self.current_task_mode == "encrypt":
                    self._set_status("encrypt_complete_status")
                else:
                    self._set_status("complete_status")
            else:
                self._set_status("idle_status")

        self.root.after(0, _reset)

    # ------------------------------------------------------------------
    # Window close
    # ------------------------------------------------------------------
    def on_close(self) -> None:
        if self.is_processing:
            answer = messagebox.askyesno(
                self.t("close_confirm_title"),
                self.t("close_confirm_msg"),
                parent=self.root,
            )
            if not answer:
                return
            self.cancel_processing()
            self._closing_after_cancel = True
            self.root.after(CLOSE_POLL_INTERVAL_MS, self._poll_for_close)
            return

        # Restore WndProc subclassing
        if hasattr(self, "_old_wndproc") and self._old_wndproc:
            try:
                import platform
                is_64bit = platform.architecture()[0] == '64bit'
                try:
                    SetWindowLong = ctypes.windll.user32.SetWindowLongPtrW
                except AttributeError:
                    SetWindowLong = ctypes.windll.user32.SetWindowLongW
                SetWindowLong(self._hwnd, -4, self._old_wndproc)
            except Exception:
                pass

        self.root.destroy()

    def _poll_for_close(self) -> None:
        if self.is_processing:
            self.root.after(CLOSE_POLL_INTERVAL_MS, self._poll_for_close)
            return
        # Restore WndProc subclassing
        if hasattr(self, "_old_wndproc") and self._old_wndproc:
            try:
                import platform
                is_64bit = platform.architecture()[0] == '64bit'
                try:
                    SetWindowLong = ctypes.windll.user32.SetWindowLongPtrW
                except AttributeError:
                    SetWindowLong = ctypes.windll.user32.SetWindowLongW
                SetWindowLong(self._hwnd, -4, self._old_wndproc)
            except Exception:
                pass
        self.root.destroy()

    def _setup_dnd(self) -> None:
        try:
            self._hwnd = get_toplevel_hwnd(self.root)
            if self._hwnd:
                ctypes.windll.shell32.DragAcceptFiles(self._hwnd, True)
                
                # Setup WndProc subclassing
                import platform
                is_64bit = platform.architecture()[0] == '64bit'
                
                if is_64bit:
                    WPARAM = ctypes.c_uint64
                    LPARAM = ctypes.c_int64
                    LRESULT = ctypes.c_int64
                    try:
                        SetWindowLong = ctypes.windll.user32.SetWindowLongPtrW
                    except AttributeError:
                        SetWindowLong = ctypes.windll.user32.SetWindowLongW
                    SetWindowLong.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
                    SetWindowLong.restype = ctypes.c_void_p
                else:
                    WPARAM = ctypes.c_uint32
                    LPARAM = ctypes.c_int32
                    LRESULT = ctypes.c_int32
                    SetWindowLong = ctypes.windll.user32.SetWindowLongW
                    SetWindowLong.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
                    SetWindowLong.restype = ctypes.c_void_p

                CallWindowProc = ctypes.windll.user32.CallWindowProcW
                CallWindowProc.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, WPARAM, LPARAM]
                CallWindowProc.restype = LRESULT
                
                WNDPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_void_p, ctypes.c_uint, WPARAM, LPARAM)
                
                class POINT(ctypes.Structure):
                    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

                def wndproc(hwnd, msg, wparam, lparam):
                    try:
                        if msg == 0x0233:  # WM_DROPFILES
                            hDrop = wparam
                            pt = POINT()
                            ctypes.windll.shell32.DragQueryPoint(hDrop, ctypes.byref(pt))
                            ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt))
                            
                            num_files = ctypes.windll.shell32.DragQueryFileW(hDrop, 0xFFFFFFFF, None, 0)
                            paths = []
                            for idx in range(num_files):
                                length = ctypes.windll.shell32.DragQueryFileW(hDrop, idx, None, 0)
                                buf = ctypes.create_unicode_buffer(length + 1)
                                ctypes.windll.shell32.DragQueryFileW(hDrop, idx, buf, length + 1)
                                paths.append(buf.value)
                            ctypes.windll.shell32.DragFinish(hDrop)
                            if paths:
                                self.root.after(0, lambda p=paths, px=pt.x, py=pt.y: self._on_files_dropped(p, px, py))
                            return 0
                    except Exception as e:
                        sys.stderr.write(f"[dnd] Error in WndProc: {e}\n")
                    return CallWindowProc(self._old_wndproc, hwnd, msg, wparam, lparam)
                
                self._wndproc_callback = WNDPROC(wndproc)
                self._old_wndproc = SetWindowLong(self._hwnd, -4, self._wndproc_callback) # GWL_WNDPROC = -4
        except Exception as e:
            sys.stderr.write(f"[dnd] Failed to hook DragAcceptFiles: {e}\n")

    def _on_files_dropped(self, paths: list[str], mouse_x: int = -1, mouse_y: int = -1) -> None:
        if not paths:
            return
        path = paths[0]

        # Identify which widget received the drop
        is_output_target = False
        if mouse_x != -1 and mouse_y != -1:
            try:
                widget = self.root.winfo_containing(mouse_x, mouse_y)
                w = widget
                while w:
                    if w in (self.entry_output, self.btn_output, getattr(self, "lbl_section_output", None)):
                        is_output_target = True
                        break
                    parent_name = w.winfo_parent()
                    if not parent_name:
                        break
                    w = w.nametowidget(parent_name)
            except Exception:
                pass

        if is_output_target:
            if os.path.isdir(path):
                self.output_dir_var.set(path)
                self.save_config()
                self.log(self.t("output_folder_dropped", path=path))
            return

        # Check if it's a legacy archive file
        ext = os.path.splitext(path)[1].lower()
        if ext in (".rgss3a", ".rgss2a", ".rgssad"):
            self.current_task_mode = "unpack"
            self._task_mode_radio_var().set("unpack")
            self.input_dir_var.set(path)
            self.log(self.t("mode_changed", label=self.t("task_mode_unpack")))
            return
            
        # If it's a directory, set as input folder
        if os.path.isdir(path):
            # Autocorrect for MV/MZ layout
            input_dir = (
                os.path.join(path, "www")
                if os.path.exists(os.path.join(path, "www", "img"))
                else path
            )
            self.input_dir_var.set(input_dir)
            
            # If in unpack mode, switch back to decrypt.
            if self._looks_like_rpg_folder(path) or self._looks_like_rpg_folder(input_dir):
                if self.current_task_mode == "unpack":
                    self.current_task_mode = "decrypt"
                    self._task_mode_radio_var().set("decrypt")
                    self.log(self.t("mode_changed", label=self.t("task_mode_decrypt")))
            
            # Perform automatic key recovery!
            if self.current_task_mode in ("decrypt", "encrypt"):
                self.log(self.t("key_search_header"))
                scan: SystemJsonScan = extract_key_from_system_json(path)
                for p, status_key, extra in scan.attempts:
                    status_text = self._format_key_status(status_key, extra)
                    self.log(self.t("key_search_path_check", path=p, status=status_text))

                if scan.key:
                    self.key_var.set(scan.key)
                    self.log(self.t("key_found", key=mask_key(scan.key)))
                else:
                    # Try image recovery
                    from rpg_core import recover_key_from_png
                    recovered_key = None
                    for r, _, files in os.walk(input_dir):
                        for f in files:
                            fext = os.path.splitext(f)[1].lower()
                            if fext in (".rpgmvp", ".png_"):
                                test_path = os.path.join(r, f)
                                recovered_key = recover_key_from_png(test_path)
                                if recovered_key:
                                    break
                        if recovered_key:
                            break
                    if recovered_key:
                        self.key_var.set(recovered_key)
                        self.log(self.t("key_recovered_log", key=mask_key(recovered_key)))
                    elif scan.found_system_json:
                        if not scan.has_encrypted_images and not scan.has_encrypted_audio:
                            self.log(self.t("unencrypted_game"))
                        else:
                            self.log(self.t("encrypted_no_key"))
                    else:
                        self.log(self.t("key_recovery_fail_log"))
        else:
            self.input_dir_var.set(path)


# =====================================================================
# Entry point
# =====================================================================
if __name__ == "__main__":
    root = tk.Tk()
    DecrypterApp(root)
    root.mainloop()
