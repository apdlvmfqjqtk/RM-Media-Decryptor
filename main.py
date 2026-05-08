# -*- coding: utf-8 -*-
"""
RPG Decrypter (Windows 10/11)

A CustomTkinter desktop utility that decrypts RPG Maker MV/MZ encrypted
image and media assets (.rpgmvp, .png_, .rpgmvo, .ogg_, .rpgmvm, .m4a_).

Security policy:
    - The decryption key is NEVER persisted to disk.
    - It exists only in process memory while the app is running.
    - Old config files containing a saved key are auto-purged on load.
    - Saved settings only contain non-sensitive UI preferences.

Threading model:
    All decryption work runs on a single daemon worker thread.
    The worker's status updates (log, progress, status label) are
    marshalled to the main Tk thread via ``root.after(0, ...)``.
    A ``threading.Event`` is used as a cooperative cancellation signal.

Keyboard shortcuts:
    F5            -> Start decryption (Run)
    Enter         -> Start decryption when key entry has focus
    Escape        -> Cancel a running decryption
    Ctrl+L        -> Clear log

Designed for PyInstaller --onedir --windowed packaging.
"""

import os
import pathlib
import sys
import threading
import time
import ctypes
from ctypes import wintypes
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from config_store import load_config_data, save_config_data
from lang import LANGUAGE_CODES_BY_LABEL, LANGUAGE_OPTIONS, TEXT
from rpg_core import (
    EXT_MAP,
    KNOWN_UNSUPPORTED_EXT,
    PLAIN_MEDIA_EXT,
    SystemJsonScan,
    decrypt_asset,
    extract_key_from_system_json,
    get_target_extensions,
    mask_key,
    unique_output_path,
    validate_key,
    validate_paths,
)

# =====================================================================
# 0. Platform guard
# =====================================================================
if sys.platform != "win32":
    raise SystemExit("This application currently supports Windows 10/11 only.")

# =====================================================================
# 1. HiDPI awareness (Windows 10/11)
# =====================================================================
try:
    # Per-Monitor v2 (Win10 1703+); falls back to System DPI on older builds.
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


# =====================================================================
# 2. Resource path helper (works in dev and PyInstaller --onedir/--onefile)
# =====================================================================
def resource_path(relative: str) -> str:
    """Resolve the absolute path for a bundled resource.

    - In a PyInstaller bundle, ``sys._MEIPASS`` is set:
        * --onefile: temp extraction directory.
        * --onedir : the bundle's _internal directory.
    - When running from source, the .py's directory is used.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(base, relative))


# =====================================================================
# 3. Private font loading (Windows: AddFontResourceExW + FR_PRIVATE)
# =====================================================================
FR_PRIVATE     = 0x10
WM_FONTCHANGE  = 0x001D
HWND_BROADCAST = 0xFFFF

_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
_gdi32.AddFontResourceExW.argtypes    = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
_gdi32.AddFontResourceExW.restype     = ctypes.c_int
_gdi32.RemoveFontResourceExW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
_gdi32.RemoveFontResourceExW.restype  = wintypes.BOOL

_user32 = ctypes.WinDLL("user32", use_last_error=True)

PRETENDARD_FAMILY    = "Pretendard"
PRETENDARD_JP_FAMILY = "Pretendard JP"

FONT_FILES = [
    ("Pretendard-Regular.ttf",   PRETENDARD_FAMILY),
    ("Pretendard-Medium.ttf",    PRETENDARD_FAMILY),
    ("Pretendard-SemiBold.ttf",  PRETENDARD_FAMILY),
    ("Pretendard-Bold.ttf",      PRETENDARD_FAMILY),
    ("PretendardJP-Regular.ttf", PRETENDARD_JP_FAMILY),
    ("PretendardJP-Medium.ttf",  PRETENDARD_JP_FAMILY),
    ("PretendardJP-SemiBold.ttf",PRETENDARD_JP_FAMILY),
    ("PretendardJP-Bold.ttf",    PRETENDARD_JP_FAMILY),
]

FALLBACK_FAMILY_DEFAULT = "Segoe UI"
FALLBACK_FAMILY_JP      = "Yu Gothic UI"


class FontLoader:
    """Loads bundled TTFs into the process via AddFontResourceExW."""

    def __init__(self) -> None:
        self._loaded_paths:     list[str] = []
        self.has_pretendard:    bool      = False
        self.has_pretendard_jp: bool      = False

    def load(self) -> None:
        any_default = False
        any_jp      = False

        for filename, family in FONT_FILES:
            font_path = resource_path(os.path.join("assets", "fonts", filename))
            if not os.path.isfile(font_path):
                continue
            n = _gdi32.AddFontResourceExW(font_path, FR_PRIVATE, None)
            if n > 0:
                self._loaded_paths.append(font_path)
                if family == PRETENDARD_FAMILY:
                    any_default = True
                elif family == PRETENDARD_JP_FAMILY:
                    any_jp = True

        if self._loaded_paths:
            try:
                _user32.SendMessageW(HWND_BROADCAST, WM_FONTCHANGE, 0, 0)
            except Exception:
                pass

        self.has_pretendard    = any_default
        self.has_pretendard_jp = any_jp

    def family_for(self, lang_code: str) -> str:
        """Return the best available font family for a given UI language."""
        if lang_code == "ja":
            if self.has_pretendard_jp:
                return PRETENDARD_JP_FAMILY
            if self.has_pretendard:
                return PRETENDARD_FAMILY
            return FALLBACK_FAMILY_JP
        if self.has_pretendard:
            return PRETENDARD_FAMILY
        return FALLBACK_FAMILY_DEFAULT

    def multilingual_family(self) -> str:
        """Return a CJK-safe family for mixed Korean/English/Japanese UI areas."""
        if self.has_pretendard_jp:
            return PRETENDARD_JP_FAMILY
        if self.has_pretendard:
            return PRETENDARD_FAMILY
        return FALLBACK_FAMILY_JP

    def unload(self) -> None:
        for p in self._loaded_paths:
            try:
                _gdi32.RemoveFontResourceExW(p, FR_PRIVATE, None)
            except Exception:
                pass
        self._loaded_paths.clear()


FONT_LOADER = FontLoader()
FONT_LOADER.load()


# =====================================================================
# 4. Centralized font role table
# =====================================================================
FONT_ROLES = {
    "title":       (18, "bold"),     # was 22 — Apple-style smaller title
    "subtitle":    (11, "normal"),   # was 12
    "section":     (11, "bold"),
    "label":       (12, "normal"),
    "label_bold":  (11, "bold"),
    "button_main": (14, "bold"),     # was 15
    "button_sub":  (12, "normal"),
    "switch":      (12, "normal"),
    "menu":        (12, "normal"),
    "note":        (11, "normal"),
}

FONT_MONO_ROLES = {
    "mono":     ("Consolas",  11, "normal"),
    "mono_key": ("Consolas",  12, "normal"),
    "mono_log": ("CJK_SAFE",  10, "normal"),
}


# =====================================================================
# 5. Color tokens (light / dark)
# =====================================================================
# NOTE: ctk.set_default_color_theme is invoked from DecrypterApp.__init__
# rather than at module import time, so importing this module has no
# global side effects (helpful for tests and tooling).

COLORS = {
    "bg":             ("#F5F5F7", "#161618"),
    "surface":        ("#FFFFFF", "#1E1E20"),
    "surface_alt":    ("#F0F0F3", "#28282C"),
    "border":         ("#D1D1D6", "#3A3A3E"),
    "accent":         ("#007AFF", "#0A84FF"),
    "accent_hover":   ("#0066CC", "#0071E3"),
    "success":        ("#248A3D", "#30D158"),
    "warning":        ("#BF5B00", "#FF9F0A"),
    # Slightly desaturated reds — full systemRed feels jarring on a 54-px button.
    "danger":         ("#C73734", "#E55A4D"),
    "danger_hover":   ("#A12A28", "#C7423A"),
    "text_primary":   ("#1D1D1F", "#F5F5F7"),
    "text_secondary": ("#3A3A3C", "#98989F"),
    "text_tertiary":  ("#6E6E73", "#636366"),
}


# =====================================================================
# 6. Geometry tokens (100 % DPI baseline)
# =====================================================================
RADIUS_CARD    = 8
RADIUS_CONTROL = 4
RADIUS_BUTTON  = 4
RADIUS_ENTRY   = 4
RADIUS_MENU    = 4
RADIUS_DIVIDER = 0


# =====================================================================
# 7. App-level constants
# =====================================================================
PAD_X                  = 18                 # outer window padding (was 28)
WRAP_PADDING           = PAD_X * 2          # used to compute wraplength on resize
PROGRESS_BAR_HEIGHT    = 6                  # was 8 — thinner, Apple-style
STATUS_LABEL_HEIGHT    = 18
NOTIFY_DELAY_MS        = 0                  # delay before completion popup
CLOSE_POLL_INTERVAL_MS = 100                # interval for waiting on cancel-then-close
PROGRESS_LOG_BUCKET    = 5                  # log every N % progress
UI_THROTTLE_SEC        = 0.05               # min interval between UI progress updates
LOG_MAX_LINES          = 5000               # auto-trim threshold for the log textbox
LOG_TRIM_TARGET        = 2500               # how many lines to keep after a trim

# Fixed widths for buttons that hold translated text — locks the layout
# to the Korean baseline so EN/JA can't shift columns.  The three folder/
# show buttons share a common width for visual consistency.
BTN_W_FIND_FOLDER  = 130   # "게임 폴더 찾기" / "Find Game Folder" / "ゲームフォルダーを開く"
BTN_W_KEY_TOGGLE   = 130   # "표시" / "숨기기" — same as folder buttons for symmetry
BTN_W_LOG_CTRL     = 80    # "복사" / "지우기"
BTN_H_LOG_CTRL     = 24

# Severity prefixes used to color log lines.  Ordering matters only when a
# message could match multiple — first match wins.
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

# Subdirectories that strongly indicate an RPG Maker project root.
RPG_FOLDER_INDICATORS = ("data", "www", "img", "audio", "js")

# Skip-only failure codes that should NOT count as a real failure.
SKIP_REASONS = {
    "too_small",
    "already_png",
    "already_ogg",
    "already_m4a",
    "not_encrypted",
}


# =====================================================================
# 8. Main application
# =====================================================================
class DecrypterApp:
    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def __init__(self, root: ctk.CTk) -> None:
        # Per-instance side effect — keeps importing main.py free of
        # global CTk state changes.
        ctk.set_default_color_theme("blue")

        self.root = root
        self.root.title("RPG Decrypter")
        self.set_window_icon()

        # Apple-style fixed-size window — non-resizable so the carefully
        # tuned layout can't be deformed.  Controls : log = 2 : 1.
        self.root.geometry("880x800")
        self.root.resizable(False, False)

        # Runtime state
        self.current_lang        = "ko"
        self.current_appearance  = "dark"
        self.current_target_mode = "both"
        self.is_processing       = False
        self.processed_files     = 0
        self.total_files         = 0

        # Threading state
        self._cancel_event         = threading.Event()
        self._closing_after_cancel = False
        self._key_shown            = False  # key field hidden by default for security
        # UI-update throttling for the per-file progress callbacks.
        self._last_ui_update       = 0.0

        # Key entry alert state. Holds a translation key like
        # "encrypted_no_key" when the auto-detect found no key for an
        # encrypted game; None when the field is in its normal state.
        self._key_alert_key: str | None = None

        # Status-label state (so language changes can re-render the label).
        self._status_key:  str | None = None
        self._status_args: dict       = {}

        # Tk variables (key_var is in-memory only — never written to disk)
        self.key_var         = tk.StringVar()
        self.input_dir_var   = tk.StringVar()
        self.output_dir_var  = tk.StringVar()
        self.dark_mode_var   = tk.BooleanVar(value=True)
        self.language_var    = tk.StringVar(value=LANGUAGE_OPTIONS[self.current_lang])
        self.target_mode_var = tk.StringVar()
        self.auto_open_var   = tk.BooleanVar(value=False)
        self.overwrite_var   = tk.BooleanVar(value=False)

        # Widget bookkeeping
        self.widgets: dict[str, tk.Widget]                       = {}
        self.font_registry: list[tuple[tk.Widget, str]]          = []
        self.placeholder_widgets: list[tuple[ctk.CTkEntry, str]] = []

        # Load persisted (non-sensitive) settings BEFORE building UI.
        self.load_config(silent=True)
        ctk.set_appearance_mode("dark" if self.current_appearance == "dark" else "light")
        self.dark_mode_var.set(self.current_appearance == "dark")
        self.language_var.set(LANGUAGE_OPTIONS.get(self.current_lang, LANGUAGE_OPTIONS["ko"]))

        self.root.configure(fg_color=COLORS["bg"])
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # Reactive bindings (after _build_ui so widgets exist).
        self.root.bind("<Configure>", self._on_root_configure)
        if hasattr(self, "_controls_panel"):
            self._controls_panel.bind("<Configure>", self._on_controls_configure)
        self.key_var.trace_add("write", self._on_key_changed)

        self._setup_keyboard_shortcuts()
        self._setup_key_context_menu()

        # First language pass: no log entry, no config write.
        self.apply_language(log_change=False, save=False)

        # Warm up reactive widgets.
        self._render_key_state()
        self._configure_log_tags()

        if not (FONT_LOADER.has_pretendard or FONT_LOADER.has_pretendard_jp):
            self.log(self.t("fonts_missing_note"))

    def set_window_icon(self) -> None:
        """Apply the app icon. Failures are logged to stderr (dev visibility)."""
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
    # Translation helpers
    # ------------------------------------------------------------------
    def t(self, key: str, **kwargs) -> str:
        template = TEXT.get(self.current_lang, TEXT["ko"]).get(
            key, TEXT["ko"].get(key, key)
        )
        try:
            return template.format(**kwargs) if kwargs else template
        except (KeyError, IndexError):
            return template

    def _font(self, role: str) -> tuple:
        """Return a font tuple for *role* using the current language family."""
        if role == "mono_log":
            _, size, weight = FONT_MONO_ROLES[role]
            return (FONT_LOADER.multilingual_family(), size, weight)
        if role in FONT_MONO_ROLES:
            return FONT_MONO_ROLES[role]
        if role == "menu":
            family = FONT_LOADER.multilingual_family()
        else:
            family = FONT_LOADER.family_for(self.current_lang)
        size, weight = FONT_ROLES[role]
        return (family, size, weight)

    def _register_font(self, widget: tk.Widget, role: str) -> tk.Widget:
        """Apply font to *widget* and register it for language-change refresh."""
        try:
            widget.configure(font=self._font(role))
        except Exception:
            pass
        self.font_registry.append((widget, role))
        return widget

    def _refresh_fonts(self) -> None:
        for widget, role in self.font_registry:
            try:
                if role == "menu":
                    widget.configure(
                        font=self._font(role),
                        dropdown_font=self._font(role),
                    )
                else:
                    widget.configure(font=self._font(role))
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Config (no key persistence)
    # ------------------------------------------------------------------
    def load_config(self, silent: bool = False) -> None:
        data, error = load_config_data()
        if error is not None:
            if not silent:
                self.log(self.t("config_loaded_fail", error=error))
            return

        # input_dir is intentionally never saved — skip reading it.
        self.output_dir_var.set(data.get("output_dir", "") or "")

        lang = data.get("language", "ko")
        if lang in TEXT:
            self.current_lang = lang

        appearance = data.get("appearance", "dark")
        if appearance in ("dark", "light"):
            self.current_appearance = appearance

        target_mode = data.get("target_mode", "both")
        if target_mode in TARGET_MODE_TEXT_KEYS:
            self.current_target_mode = target_mode

        self.auto_open_var.set(bool(data.get("auto_open", False)))
        self.overwrite_var.set(bool(data.get("overwrite", False)))

    def save_config(self) -> bool:
        ok, error = save_config_data(
            output_dir=self.output_dir_var.get(),
            language=self.current_lang,
            appearance=self.current_appearance,
            target_mode=self.current_target_mode,
            auto_open=self.auto_open_var.get(),
            overwrite=self.overwrite_var.get(),
        )
        if not ok:
            self.log(self.t("config_saved_fail", error=error))
        return ok

    # ------------------------------------------------------------------
    # Language / appearance
    # ------------------------------------------------------------------
    def apply_language(self, log_change: bool = True, save: bool = True) -> None:
        self.root.title(self.t("window_title"))
        self._refresh_fonts()

        # Re-text every registered widget by translation key. The dark_mode
        # switch is intentionally skipped here — _update_switch_text renders
        # state-aware text ("Dark"/"Light") below.
        for key, widget in self.widgets.items():
            if key == "dark_mode":
                continue
            if key in TEXT[self.current_lang]:
                try:
                    widget.configure(text=self.t(key))
                except Exception:
                    pass

        # Entry placeholders.
        for entry, text_key in self.placeholder_widgets:
            try:
                entry.configure(placeholder_text=self.t(text_key))
            except Exception:
                pass

        if hasattr(self, "target_mode_menu"):
            self._refresh_target_mode_menu()

        # Dark-mode switch: show state-aware text ("Dark" / "Light").
        self._update_switch_text()

        # Key visibility toggle button.
        if hasattr(self, "btn_toggle_key"):
            self.btn_toggle_key.configure(
                text=self.t("key_hide" if self._key_shown else "key_show")
            )

        # Run / Cancel / Cancelling button text — refresh in every state so
        # mid-processing language changes update the visible label.
        if hasattr(self, "btn_run"):
            if not self.is_processing:
                self.btn_run.configure(text=self.t("run_button"))
            elif self._cancel_event.is_set():
                self.btn_run.configure(text=self.t("cancelling_button"))
            else:
                self.btn_run.configure(text=self.t("cancel_button"))

        # Re-render the status label so its text follows the new language.
        self._render_status()

        # Re-render key entry state — the generic widgets loop above set
        # the key_note label to its default text, but an active alert
        # (e.g. encrypted_no_key) needs to override that.
        self._render_key_state()

        if log_change:
            self.log(self.t("lang_changed"))
        if save:
            self.save_config()

    def on_language_changed(self, selected_label: str) -> None:
        lang_code = LANGUAGE_CODES_BY_LABEL.get(selected_label, "ko")
        self.current_lang = lang_code
        self.language_var.set(LANGUAGE_OPTIONS[lang_code])
        self.apply_language(log_change=True, save=True)

    def on_dark_mode_toggle(self) -> None:
        if self.dark_mode_var.get():
            self.current_appearance = "dark"
            ctk.set_appearance_mode("dark")
            self.log(self.t("mode_dark"))
        else:
            self.current_appearance = "light"
            ctk.set_appearance_mode("light")
            self.log(self.t("mode_light"))
        self._update_switch_text()
        # Tag colours are picked per-mode, so re-pick after the toggle.
        self._configure_log_tags()
        self.save_config()

    def _update_switch_text(self) -> None:
        """Set the dark-mode switch label to reflect the current state."""
        if "dark_mode" in self.widgets:
            text_key = "switch_dark" if self.current_appearance == "dark" else "switch_light"
            try:
                self.widgets["dark_mode"].configure(text=self.t(text_key))
            except Exception:
                pass

    def _target_mode_label(self, mode: str) -> str:
        return self.t(TARGET_MODE_TEXT_KEYS.get(mode, "target_both"))

    def _refresh_target_mode_menu(self) -> None:
        values = [self._target_mode_label(mode) for mode in TARGET_MODE_ORDER]
        try:
            self.target_mode_menu.configure(values=values)
        except Exception:
            pass
        self.target_mode_var.set(self._target_mode_label(self.current_target_mode))

    def on_target_mode_changed(self, selected_label: str) -> None:
        for mode in TARGET_MODE_ORDER:
            if selected_label == self._target_mode_label(mode):
                self.current_target_mode = mode
                break
        else:
            self.current_target_mode = "both"
        self.target_mode_var.set(self._target_mode_label(self.current_target_mode))
        self.save_config()

    # ------------------------------------------------------------------
    # Reactive UI helpers
    # ------------------------------------------------------------------
    def _on_root_configure(self, event) -> None:
        """Update wraplength for full-width labels (header subtitle/guide)."""
        if event.widget is not self.root:
            return
        new_wrap = max(200, event.width - WRAP_PADDING)
        for key in ("app_subtitle", "quick_guide"):
            if key in self.widgets:
                try:
                    self.widgets[key].configure(wraplength=new_wrap)
                except Exception:
                    pass

    def _on_controls_configure(self, event) -> None:
        """Update wraplength for labels inside the (narrower) controls panel."""
        if not hasattr(self, "_controls_panel"):
            return
        if event.widget is not self._controls_panel:
            return
        # Account for card border + inner padding (about 40 px total).
        new_wrap = max(180, event.width - 40)
        if "key_note" in self.widgets:
            try:
                self.widgets["key_note"].configure(wraplength=new_wrap)
            except Exception:
                pass

    def _on_key_changed(self, *_) -> None:
        """Trace handler for key_var. Clears alert state if the user starts
        typing, then re-renders the key entry's appearance."""
        if self._key_alert_key is not None and self.key_var.get().strip():
            self._key_alert_key = None
        self._render_key_state()

    def _set_key_alert(self, message_key: str | None) -> None:
        """Activate or clear the key entry's warning state.

        Pass a translation key (e.g. ``"encrypted_no_key"``) to display
        an inline warning under the key field, or ``None`` to clear.
        """
        self._key_alert_key = message_key
        self._render_key_state()

    def _render_key_state(self) -> None:
        """Re-render the key entry border + key_note label.

        Priority order for the border colour:
          1. Key visibility ON          -> warning  (visually mark exposure)
          2. Active alert (no_key etc.) -> warning
          3. Empty input                -> accent   (neutral)
          4. Valid 32-char hex          -> success
          5. Anything else              -> danger
        """
        if self._key_shown:
            color = COLORS["warning"]
        elif self._key_alert_key is not None:
            color = COLORS["warning"]
        else:
            key = self.key_var.get().strip()
            if not key:
                color = COLORS["accent"]
            else:
                ok, _ = validate_key(key)
                color = COLORS["success"] if ok else COLORS["danger"]

        if hasattr(self, "entry_key"):
            try:
                self.entry_key.configure(border_color=color)
            except Exception:
                pass

        # Re-render the note label below the key field.
        if "key_note" in self.widgets:
            note_key = self._key_alert_key if self._key_alert_key else "key_note"
            note_color = (
                COLORS["warning"] if self._key_alert_key else COLORS["text_tertiary"]
            )
            try:
                self.widgets["key_note"].configure(
                    text=self.t(note_key), text_color=note_color
                )
            except Exception:
                pass

    def _set_status(self, key: str | None = None, **kwargs) -> None:
        """Update the status label by translation key.

        Pass ``key=None`` to clear the label. Stored args are remembered so
        :py:meth:`_render_status` can re-render the label in a different
        language without losing context.
        """
        self._status_key  = key
        self._status_args = kwargs
        self._render_status()

    def _render_status(self) -> None:
        """Render the status label using the current status state.

        When idle (status_key is None), the label doubles as a keyboard-
        shortcut hint so the F5 / Esc / Ctrl+L bindings are discoverable.
        """
        if self._status_key is None:
            text = self.t("shortcuts_hint")
        else:
            text = (
                self.t(self._status_key, **self._status_args)
                if self._status_args
                else self.t(self._status_key)
            )
        if "status_label" in self.widgets:
            try:
                self.widgets["status_label"].configure(text=text)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Keyboard shortcuts
    # ------------------------------------------------------------------
    def _setup_keyboard_shortcuts(self) -> None:
        """Bind global keyboard shortcuts."""
        self.root.bind("<F5>",          self._handle_run_shortcut)
        self.root.bind("<Escape>",      self._handle_cancel_shortcut)
        self.root.bind("<Control-l>",   self._handle_clear_log_shortcut)
        self.root.bind("<Control-L>",   self._handle_clear_log_shortcut)

        # Enter on the key entry triggers Run for quick keyboard-only flow.
        if hasattr(self, "entry_key"):
            self.entry_key.bind("<Return>", self._handle_run_shortcut)

    def _handle_run_shortcut(self, event=None) -> str:
        if not self.is_processing:
            self.start_processing()
        return "break"

    def _handle_cancel_shortcut(self, event=None) -> str:
        # If the key entry has focus, treat Esc as "blur the field" rather
        # than "cancel the running job" — keystrokes meant to dismiss the
        # entry shouldn't kill an in-flight batch.
        if hasattr(self, "entry_key"):
            try:
                if self.root.focus_get() is self.entry_key:
                    self.root.focus_set()
                    return "break"
            except Exception:
                pass
        if self.is_processing:
            self.cancel_processing()
        return "break"

    def _handle_clear_log_shortcut(self, event=None) -> str:
        self.clear_log()
        return "break"

    # ------------------------------------------------------------------
    # Right-click context menu on key entry (Cut / Copy / Paste)
    # ------------------------------------------------------------------
    def _setup_key_context_menu(self) -> None:
        if not hasattr(self, "entry_key"):
            return
        # Use plain tk.Menu — CTk has no built-in context menu primitive.
        self._key_context_menu = tk.Menu(self.entry_key, tearoff=0)
        self._key_context_menu.add_command(label="", command=self._ctx_cut)
        self._key_context_menu.add_command(label="", command=self._ctx_copy)
        self._key_context_menu.add_command(label="", command=self._ctx_paste)
        self.entry_key.bind("<Button-3>", self._show_key_context_menu)

    def _show_key_context_menu(self, event) -> None:
        # Refresh labels so language changes are reflected immediately.
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
        """Open the output folder in Windows Explorer.

        If *subdir* is given (e.g. the game name) and that subdirectory
        exists under the output folder, open it directly so the user
        lands on the decrypted assets instead of the parent folder.
        Falls back to the bare output folder when the subdir is missing.
        """
        base = self.output_dir_var.get().strip()
        if not base:
            return
        target = os.path.join(base, subdir) if subdir else base
        if os.path.isdir(target):
            os.startfile(target)
        elif os.path.isdir(base):
            os.startfile(base)

    def select_game_folder(self) -> None:
        selected_dir = filedialog.askdirectory(
            parent=self.root, title=self.t("select_game_dialog")
        )
        if not selected_dir:
            return

        # Sanity check: warn before scanning a folder that is unlikely to be
        # an RPG Maker game (avoids accidentally crawling C:\ or a home dir).
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
            self._set_key_alert(None)
        elif scan.found_system_json:
            # System.json exists but no usable key.
            if not scan.has_encrypted_images and not scan.has_encrypted_audio:
                # Game is genuinely unencrypted — no decryption needed.
                self.log(self.t("unencrypted_game"))
                self._set_key_alert(None)
            else:
                # Game IS encrypted but the key is missing or malformed —
                # surface the warning prominently in the key area too.
                self.log(self.t("encrypted_no_key"))
                self._set_key_alert("encrypted_no_key")
        else:
            # No System.json found at all.
            self.log(self.t("key_search_failed"))
            self._set_key_alert(None)
        # NOTE: no save_config() here — input_dir and key are intentionally
        # not persisted, and no other persisted setting changed.

    @staticmethod
    def _looks_like_rpg_folder(path: str) -> bool:
        """Return True if *path* contains at least one RPG Maker indicator
        subfolder (data/www/img/audio/js)."""
        try:
            return any(
                os.path.isdir(os.path.join(path, ind))
                for ind in RPG_FOLDER_INDICATORS
            )
        except Exception:
            return False

    def _format_key_status(self, status: str, extra) -> str:
        if status == "not_found":
            return self.t("status_not_found")
        if status == "read_error":
            return self.t("status_read_error", error=extra)
        if status == "key_missing":
            return self.t("status_key_missing")
        if status == "key_empty":
            return self.t("status_key_empty")
        if status == "key_bad_length":
            return self.t("status_key_bad_length", length=extra)
        if status == "key_non_hex":
            return self.t("status_key_non_hex")
        if status == "ok":
            return self.t("status_ok")
        return status

    def _format_decrypt_error(self, reason) -> str:
        """Translate rpg_core failure codes into user-facing messages.

        Only failure codes that actually reach this method are matched.
        Skip codes (``too_small``, ``already_*``, ``not_encrypted``) are
        filtered upstream by ``SKIP_REASONS`` so they never arrive here.
        """
        if isinstance(reason, tuple):
            code   = reason[0]
            detail = reason[1] if len(reason) > 1 else ""
            if code == "io_error":
                return self.t("io_error", error=detail)
            if code == "raw_error":
                if detail in ("unknown_error", "key_too_short"):
                    return self.t(detail)
                return str(detail)
            return str(detail or code)
        if reason in ("bad_png", "bad_ogg", "bad_m4a", "unknown_error"):
            return self.t(reason)
        return str(reason)

    # ------------------------------------------------------------------
    # Key visibility toggle
    # ------------------------------------------------------------------
    def toggle_key_visibility(self) -> None:
        self._key_shown = not self._key_shown
        show_char = "" if self._key_shown else "*"
        try:
            self.entry_key.configure(show=show_char)
        except Exception:
            pass
        if hasattr(self, "btn_toggle_key"):
            self.btn_toggle_key.configure(
                text=self.t("key_hide" if self._key_shown else "key_show")
            )
        # Visibility toggle changes the border priority, so re-render.
        self._render_key_state()

    # ------------------------------------------------------------------
    # Log helpers
    # ------------------------------------------------------------------
    def copy_log(self) -> None:
        """Copy the entire log content to the clipboard."""
        try:
            self.log_area.configure(state="normal")
            content = self.log_area.get("1.0", tk.END)
            self.log_area.configure(state="disabled")
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
        except Exception:
            pass

    def clear_log(self) -> None:
        """Erase all text from the log area, with a confirm prompt.

        The prompt is skipped when the log is already empty so the
        keyboard shortcut (Ctrl+L) and button click feel snappy when
        there's nothing to lose.
        """
        try:
            self.log_area.configure(state="normal")
            content = self.log_area.get("1.0", "end-1c")
            self.log_area.configure(state="disabled")
        except Exception:
            return

        if not content:
            return

        if not messagebox.askyesno(
            self.t("log_clear_confirm_title"),
            self.t("log_clear_confirm_msg"),
            parent=self.root,
        ):
            return

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
        """Return one of {info, warning, error, success} or None.

        Driven by the leading bracket prefix in *message* — see
        ``SEVERITY_PREFIXES``.  Returns None for unprefixed lines so they
        render in the default colour.
        """
        msg = message.lstrip()
        for severity, prefixes in SEVERITY_PREFIXES.items():
            for prefix in prefixes:
                if msg.startswith(prefix):
                    return severity
        return None

    def _configure_log_tags(self) -> None:
        """(Re)configure log Text-widget tag colours for the current theme.

        Tag colours are picked from the COLORS table using the appropriate
        light/dark variant so the log lines remain readable on either bg.
        Called once after _build_ui and again on appearance toggles.
        """
        if not hasattr(self, "log_area"):
            return
        mode_idx = 0 if self.current_appearance == "light" else 1
        for severity, color_key in (
            ("info",    "accent"),
            ("warning", "warning"),
            ("error",   "danger"),
            ("success", "success"),
        ):
            try:
                self.log_area.tag_config(
                    severity, foreground=COLORS[color_key][mode_idx]
                )
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
            # Auto-trim so the log textbox does not grow unbounded on
            # huge batches (50k+ files would otherwise pin memory).
            try:
                line_count = int(self.log_area.index("end-1c").split(".")[0])
                if line_count > LOG_MAX_LINES:
                    delete_to = line_count - LOG_TRIM_TARGET
                    self.log_area.delete("1.0", f"{delete_to}.0")
            except Exception:
                pass
            self.log_area.see(tk.END)
            self.log_area.configure(state="disabled")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Run / cancel / worker thread
    # ------------------------------------------------------------------
    def start_processing(self) -> None:
        key        = self.key_var.get().strip()
        input_dir  = self.input_dir_var.get().strip()
        output_dir = self.output_dir_var.get().strip()

        if not key or not input_dir or not output_dir:
            messagebox.showwarning(
                self.t("warning_title"), self.t("missing_fields"), parent=self.root
            )
            return

        key_ok, key_msg = validate_key(key)
        if not key_ok:
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
        self.processed_files = 0
        self.total_files     = 0
        self._last_ui_update = 0.0
        self._cancel_event.clear()

        # Switch run button to cancel mode.
        self.btn_run.configure(
            text=self.t("cancel_button"),
            fg_color=COLORS["danger"],
            hover_color=COLORS["danger_hover"],
            command=self.cancel_processing,
        )

        # Switch progress bar to indeterminate (scanning phase).
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()
        self._set_status("scan_status")

        self.save_config()

        worker = threading.Thread(
            target=self.process_files,
            args=(
                key,
                input_dir,
                output_dir,
                self.current_target_mode,
                self.overwrite_var.get(),
            ),
            daemon=True,
        )
        worker.start()

    def cancel_processing(self) -> None:
        """Signal the worker thread to stop after the current file."""
        self._cancel_event.set()
        try:
            self.btn_run.configure(
                state="disabled",
                text=self.t("cancelling_button"),
            )
        except Exception:
            pass

    def process_files(
        self,
        key: str,
        input_dir: str,
        output_dir: str,
        target_mode: str,
        overwrite: bool,
    ) -> None:
        """Worker entry point: scan, decrypt, summarise."""
        self.log(self.t("start_log"))

        try:
            target_files, unsupported_count, plain_media_counts = self._scan_files(
                input_dir, target_mode
            )

            if any(plain_media_counts.values()):
                self.log(
                    self.t(
                        "plain_media_summary",
                        png=plain_media_counts[".png"],
                        ogg=plain_media_counts[".ogg"],
                        m4a=plain_media_counts[".m4a"],
                    )
                )

            self.total_files = len(target_files)

            # Switch progress bar to determinate now that we know the total.
            self.root.after(0, self._end_scan_phase)

            if self.total_files == 0:
                self.log(self.t("no_files"))
                return

            self.log(self.t("count_log", total=self.total_files))
            self.log(
                self.t("progress_log", percent=0, processed=0, total=self.total_files)
            )

            stats = self._run_decrypt_loop(
                target_files, key, input_dir, output_dir, overwrite
            )

            # Summary + notification only when not cancelled mid-loop.
            if not stats["cancelled_in_loop"]:
                self._log_summary(stats, unsupported_count)
                self.root.after(
                    NOTIFY_DELAY_MS,
                    lambda s=stats: self._show_completion_notification(s),
                )

        except Exception as e:
            err_msg = self.t("fatal_error", error=e)
            self.log(err_msg)
            # Surface fatal errors as a popup too — without this, the user
            # only sees a single log line and might not realise the run
            # blew up rather than completed normally.
            self.root.after(
                0,
                lambda m=err_msg: messagebox.showerror(
                    self.t("error_title"), m, parent=self.root
                ),
            )

        finally:
            self.finish_processing()

    def _scan_files(
        self, input_dir: str, target_mode: str
    ) -> tuple[list[tuple[str, str, str]], int, dict[str, int]]:
        """Walk *input_dir* and bucket files by category."""
        self.log(self.t("scan_log"))

        target_exts      = get_target_extensions(target_mode)
        plain_media_exts = PLAIN_MEDIA_EXTS_BY_TARGET.get(
            target_mode, PLAIN_MEDIA_EXTS_BY_TARGET["both"]
        )

        target_files: list[tuple[str, str, str]] = []
        unsupported_count                        = 0
        plain_media_counts                       = {".png": 0, ".ogg": 0, ".m4a": 0}

        for root_dir, _, files in os.walk(input_dir):
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

    def _run_decrypt_loop(
        self,
        target_files: list[tuple[str, str, str]],
        key: str,
        input_dir: str,
        output_dir: str,
        overwrite: bool = False,
    ) -> dict:
        """Decrypt each file in *target_files*. Returns aggregated stats."""
        success_count = 0
        fail_count    = 0
        skip_count    = 0
        failed_files: list[tuple[str, str]] = []
        last_logged_bucket = 0
        cancelled_in_loop  = False

        # Wall-clock anchor for ETA estimation. monotonic() never goes backwards.
        start_time = time.monotonic()

        # Parse the hex key once; pass raw bytes to avoid per-file conversion.
        key_bytes = bytes.fromhex(key)

        # Resolve the game name once — constant for the entire batch.
        # If the input folder is named "www", the real game name is one level up.
        _base_folder = os.path.basename(input_dir)
        game_name = (
            os.path.basename(os.path.dirname(input_dir))
            if _base_folder == "www"
            else _base_folder
        )
        # Guard against degenerate folder names (".", "..") that could escape output_dir.
        if game_name in ("", ".", ".."):
            game_name = ""

        total = len(target_files)

        for root_dir, filename, ext in target_files:
            # Cancellation check at the top of each iteration.
            if self._cancel_event.is_set():
                cancelled_in_loop = True
                self.log(self.t("cancel_log"))
                break

            input_path   = os.path.join(root_dir, filename)
            relative_dir = os.path.relpath(root_dir, input_dir)

            # Insert the game name as a *parent* folder before the first
            # "img" or "audio" component, producing  "gamename/img/face/A.png"
            # rather than the older "gamename-img/face/A.png" (which mashed
            # the names into a single segment).
            parts = pathlib.PurePath(relative_dir).parts
            new_parts = list(parts)
            if game_name:
                for i, p in enumerate(parts):
                    if p in ("img", "audio"):
                        new_parts.insert(i, game_name)
                        break
            new_relative_dir = os.path.join(*new_parts) if new_parts else relative_dir

            target_dir = os.path.join(output_dir, new_relative_dir)
            os.makedirs(target_dir, exist_ok=True)

            stem, _        = os.path.splitext(filename)
            desired_output = os.path.join(target_dir, stem + EXT_MAP[ext])
            # Overwrite mode skips the _N suffix dance — decrypt_asset
            # uses a tmp file + os.replace so this is atomic.
            output_path    = (
                desired_output if overwrite else unique_output_path(desired_output)
            )

            ok, reason = decrypt_asset(input_path, output_path, key_bytes)

            self.processed_files += 1

            if ok:
                success_count += 1
            elif reason in SKIP_REASONS:
                skip_count += 1
            else:
                fail_count += 1
                failed_files.append((input_path, self._format_decrypt_error(reason)))

            # Progress logging at PROGRESS_LOG_BUCKET % intervals.
            percent         = int((self.processed_files / total) * 100)
            progress_bucket = (percent // PROGRESS_LOG_BUCKET) * PROGRESS_LOG_BUCKET
            should_log      = (
                progress_bucket > last_logged_bucket
                or self.processed_files == total
            )
            if should_log:
                last_logged_bucket = progress_bucket
                self.log(
                    self.t(
                        "progress_log",
                        percent=percent,
                        processed=self.processed_files,
                        total=total,
                    )
                )

            # ETA — only meaningful after a few files complete.
            elapsed = time.monotonic() - start_time
            if self.processed_files >= 3 and elapsed > 0:
                avg = elapsed / self.processed_files
                eta_seconds = max(0, (total - self.processed_files) * avg)
            else:
                eta_seconds = None

            # Update progress bar + status label on the main thread.
            # Throttle to UI_THROTTLE_SEC so a 50k-file batch doesn't queue
            # 50k lambdas onto the Tk event loop. Always emit on the last
            # file so the bar lands exactly on 100%.
            now = time.monotonic()
            if (
                now - self._last_ui_update >= UI_THROTTLE_SEC
                or self.processed_files == total
            ):
                self._last_ui_update = now
                pct       = self.processed_files / total
                processed = self.processed_files
                self.root.after(
                    0,
                    lambda v=pct, p=processed, t=total, pc=percent, e=eta_seconds:
                        self._update_progress(v, p, t, pc, e),
                )

        return {
            "success_count":      success_count,
            "fail_count":         fail_count,
            "skip_count":         skip_count,
            "failed_files":       failed_files,
            "cancelled_in_loop":  cancelled_in_loop,
            "total":              total,
            "game_name":          game_name,
        }

    def _log_summary(self, stats: dict, unsupported_count: int) -> None:
        self.log(
            self.t(
                "done_log",
                success=stats["success_count"],
                failed=stats["fail_count"],
                skipped=stats["skip_count"] + unsupported_count,
                total=stats["total"],
            )
        )
        if stats["fail_count"] == 0:
            self.log(self.t("done_all_success"))
        else:
            self.log(self.t("done_some_failed"))
            self.log(self.t("failed_files_header"))
            for path, reason in stats["failed_files"]:
                self.log(self.t("file_failed", path=path, reason=reason))

    def _update_progress(
        self,
        value: float,
        processed: int,
        total: int,
        percent: int,
        eta_seconds: float | None,
    ) -> None:
        try:
            self.progress_bar.set(value)
        except Exception:
            pass
        self._set_status(
            "decrypt_status",
            processed=processed,
            total=total,
            percent=percent,
            eta=self._format_eta(eta_seconds),
        )

    def _format_eta(self, seconds: float | None) -> str:
        """Render an ETA in the user's language. Returns "-" when unknown."""
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
        """Switch the progress bar from indeterminate (scan) to determinate."""
        try:
            self.progress_bar.stop()
            self.progress_bar.configure(mode="determinate")
            self.progress_bar.set(0)
        except Exception:
            pass

    def _show_completion_notification(self, stats: dict) -> None:
        """Ring the bell, show a summary dialog, and auto-open if enabled.

        The messagebox is modal, so by the time it returns the user has
        dismissed it — we then optionally open the output folder.

        If the user is in the middle of closing the window (cancel-then-close
        flow), we suppress everything: no popup, no auto-open. Otherwise the
        user would see a "done" dialog and have a folder pop open after they
        explicitly asked the app to quit.
        """
        if self._closing_after_cancel:
            return

        # Subtle bell only — don't yank the window in front of whatever the
        # user is doing now (lift() was too intrusive when batches finish in
        # the background).
        self.root.bell()

        if stats["fail_count"] == 0:
            messagebox.showinfo(
                self.t("done_title"),
                self.t("done_success_msg", count=stats["success_count"]),
                parent=self.root,
            )
        else:
            # Partial failure is still "done" — the warning icon conveys
            # severity, the title shouldn't claim it was an outright failure.
            messagebox.showwarning(
                self.t("done_title"),
                self.t("done_failed_msg", failed=stats["fail_count"]),
                parent=self.root,
            )

        if self.auto_open_var.get():
            # Try to open the game-specific folder first (output_dir/GameName)
            # so the user lands on the actual decrypted assets.  The helper
            # falls back to the bare output folder if it's not there.
            self.open_output_folder(subdir=stats.get("game_name", ""))

    def finish_processing(self) -> None:
        def _reset() -> None:
            cancelled = self._cancel_event.is_set()
            self.is_processing = False

            try:
                self.progress_bar.stop()
                self.progress_bar.configure(mode="determinate")
                # Keep bar at 100% on success so the user sees completion feedback;
                # reset to 0 on cancel or when nothing was processed.
                self.progress_bar.set(0 if (cancelled or self.total_files == 0) else 1.0)
            except Exception:
                pass

            self.btn_run.configure(
                state="normal",
                text=self.t("run_button"),
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
                command=self.start_processing,
            )

            if cancelled:
                self._set_status("cancel_status")
            elif self.total_files > 0:
                self._set_status("complete_status")
            else:
                self._set_status(None)

            # If a close-after-cancel was requested, the polling loop will
            # detect that processing finished and destroy the window.

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
            # User confirmed: cancel and wait for the worker to stop.
            self.cancel_processing()
            self._closing_after_cancel = True
            self.root.after(CLOSE_POLL_INTERVAL_MS, self._poll_for_close)
            return

        self._destroy_window()

    def _poll_for_close(self) -> None:
        """Poll until the worker has finished, then destroy the window."""
        if self.is_processing:
            self.root.after(CLOSE_POLL_INTERVAL_MS, self._poll_for_close)
            return
        self._destroy_window()

    def _destroy_window(self) -> None:
        self.root.destroy()

    # ==================================================================
    # UI construction
    # ==================================================================
    def _build_ui(self) -> None:
        # ── Top-level grid: 2 columns (controls | log), 3 rows ───────
        # Fixed 2 : 1 ratio between the controls panel (wide) and the log
        # panel (narrow).  Window is non-resizable so the ratio sticks.
        self.root.grid_columnconfigure(0, weight=2)  # controls
        self.root.grid_columnconfigure(1, weight=1)  # log
        self.root.grid_rowconfigure(0, weight=0)  # header
        self.root.grid_rowconfigure(1, weight=0)  # divider
        self.root.grid_rowconfigure(2, weight=1)  # main row

        PAD_GAP = 10  # gap between controls panel and log panel

        # ── Header (spans both columns) ──────────────────────────────
        header = ctk.CTkFrame(self.root, fg_color="transparent", corner_radius=RADIUS_DIVIDER)
        header.grid(row=0, column=0, columnspan=2, sticky="ew",
                    padx=PAD_X, pady=(16, 2))
        header.grid_columnconfigure(0, weight=1)

        title_row = ctk.CTkFrame(header, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew")

        self.widgets["app_title"] = self._register_font(
            ctk.CTkLabel(title_row, text="", text_color=COLORS["text_primary"]),
            "title",
        )
        self.widgets["app_title"].pack(side="left")

        self.widgets["app_subtitle"] = self._register_font(
            ctk.CTkLabel(
                header, text="",
                text_color=COLORS["text_tertiary"],
                anchor="w", justify="left",
                wraplength=900,  # initial; updated dynamically on resize
            ),
            "subtitle",
        )
        self.widgets["app_subtitle"].grid(row=1, column=0, sticky="ew", pady=(2, 0))

        # Quick-start guide — visible right under the subtitle so first-time
        # users see the 3-step flow without reading anywhere else.
        self.widgets["quick_guide"] = self._register_font(
            ctk.CTkLabel(
                header, text="",
                text_color=COLORS["accent"],
                anchor="w", justify="left",
                wraplength=900,
            ),
            "note",
        )
        self.widgets["quick_guide"].grid(row=2, column=0, sticky="ew", pady=(4, 0))

        # Divider (spans both columns)
        ctk.CTkFrame(
            self.root, height=1, fg_color=COLORS["border"], corner_radius=RADIUS_DIVIDER
        ).grid(row=1, column=0, columnspan=2, sticky="ew",
               padx=PAD_X, pady=(6, 6))

        # ── Left column: controls panel ──────────────────────────────
        controls = ctk.CTkFrame(self.root, fg_color="transparent")
        controls.grid(row=2, column=0, sticky="nsew",
                      padx=(PAD_X, PAD_GAP), pady=(0, 14))
        controls.grid_columnconfigure(0, weight=1)
        for r in range(0, 9):
            controls.grid_rowconfigure(r, weight=0)
        self._controls_panel = controls

        # ── Section 0: Settings ──────────────────────────────────────
        self._section_label(parent=controls, row=0, translation_key="settings_section")

        settings_card = self._card(parent=controls, row=1)
        settings_row  = ctk.CTkFrame(settings_card, fg_color="transparent")
        settings_row.pack(fill="x", padx=12, pady=10)
        settings_row.grid_columnconfigure(0, weight=1)
        settings_row.grid_columnconfigure(1, weight=1)

        # Appearance (dark mode switch)
        mode_box = ctk.CTkFrame(settings_row, fg_color="transparent")
        mode_box.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.widgets["appearance_label"] = self._register_font(
            ctk.CTkLabel(mode_box, text="", text_color=COLORS["text_tertiary"], anchor="w"),
            "label_bold",
        )
        self.widgets["appearance_label"].pack(anchor="w", pady=(0, 6))
        self.widgets["dark_mode"] = self._register_font(
            ctk.CTkSwitch(
                mode_box, text="",
                variable=self.dark_mode_var,
                command=self.on_dark_mode_toggle,
                button_color=COLORS["accent"],
                button_hover_color=COLORS["accent_hover"],
                progress_color=COLORS["accent"],
                text_color=COLORS["text_secondary"],
            ),
            "switch",
        )
        self.widgets["dark_mode"].pack(anchor="w")

        # Language
        lang_box = ctk.CTkFrame(settings_row, fg_color="transparent")
        lang_box.grid(row=0, column=1, sticky="ew")
        self.widgets["language_label"] = self._register_font(
            ctk.CTkLabel(lang_box, text="", text_color=COLORS["text_tertiary"], anchor="w"),
            "label_bold",
        )
        self.widgets["language_label"].pack(anchor="w", pady=(0, 6))
        self.language_menu = ctk.CTkOptionMenu(
            lang_box,
            values=list(LANGUAGE_OPTIONS.values()),
            variable=self.language_var,
            command=self.on_language_changed,
            fg_color=COLORS["surface_alt"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            text_color=COLORS["text_primary"],
            dropdown_fg_color=COLORS["surface"],
            dropdown_hover_color=COLORS["surface_alt"],
            dropdown_text_color=COLORS["text_primary"],
            dropdown_font=self._font("menu"),
            corner_radius=RADIUS_MENU,
            height=36,
        )
        self._register_font(self.language_menu, "menu")
        self.language_menu.pack(fill="x")

        # Target mode
        target_box = ctk.CTkFrame(settings_card, fg_color="transparent")
        target_box.pack(fill="x", padx=12, pady=(0, 10))
        self.widgets["target_label"] = self._register_font(
            ctk.CTkLabel(target_box, text="", text_color=COLORS["text_tertiary"], anchor="w"),
            "label_bold",
        )
        self.widgets["target_label"].pack(anchor="w", pady=(0, 6))
        self.target_mode_menu = ctk.CTkOptionMenu(
            target_box,
            values=[self._target_mode_label(mode) for mode in TARGET_MODE_ORDER],
            variable=self.target_mode_var,
            command=self.on_target_mode_changed,
            fg_color=COLORS["surface_alt"],
            button_color=COLORS["accent"],
            button_hover_color=COLORS["accent_hover"],
            text_color=COLORS["text_primary"],
            dropdown_fg_color=COLORS["surface"],
            dropdown_hover_color=COLORS["surface_alt"],
            dropdown_text_color=COLORS["text_primary"],
            dropdown_font=self._font("menu"),
            corner_radius=RADIUS_MENU,
            height=36,
        )
        self._register_font(self.target_mode_menu, "menu")
        self.target_mode_menu.pack(fill="x")
        # NOTE: the auto_open checkbox lives in the Output card now —
        # users found it more discoverable next to the output folder.

        # ── Section 1: Source folder + key ───────────────────────────
        self._section_label(parent=controls, row=2, translation_key="section_game")

        card1      = self._card(parent=controls, row=3)
        row_folder = ctk.CTkFrame(card1, fg_color="transparent")
        row_folder.pack(fill="x", padx=12, pady=(10, 6))

        # Pack right-side button first so expand= fills the remainder.
        self.widgets["folder_button_game"] = ctk.CTkButton(
            row_folder, text="",
            fg_color=COLORS["surface_alt"],
            hover_color=COLORS["border"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"], border_width=1,
            corner_radius=RADIUS_CONTROL,
            height=32, width=BTN_W_FIND_FOLDER,
            command=self.select_game_folder,
        )
        self._register_font(self.widgets["folder_button_game"], "button_sub")
        self.widgets["folder_button_game"].pack(side="right")

        self.entry_input = ctk.CTkEntry(
            row_folder,
            textvariable=self.input_dir_var,
            state="readonly", placeholder_text="",
            fg_color=COLORS["surface_alt"],
            border_color=COLORS["border"],
            text_color=COLORS["text_secondary"],
            corner_radius=RADIUS_CONTROL, height=32,
        )
        self._register_font(self.entry_input, "label")
        self.entry_input.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.placeholder_widgets.append((self.entry_input, "input_placeholder"))

        ctk.CTkFrame(card1, height=1, fg_color=COLORS["border"]).pack(fill="x", padx=12, pady=0)

        # Key row
        row_key = ctk.CTkFrame(card1, fg_color="transparent")
        row_key.pack(fill="x", padx=12, pady=(8, 10))

        self.widgets["key_label"] = self._register_font(
            ctk.CTkLabel(row_key, text="", text_color=COLORS["text_tertiary"]),
            "label_bold",
        )
        self.widgets["key_label"].pack(anchor="w", pady=(0, 5))

        row_key_inner = ctk.CTkFrame(row_key, fg_color="transparent")
        row_key_inner.pack(fill="x")

        # Show / Hide toggle (right side, packed first).
        self.btn_toggle_key = ctk.CTkButton(
            row_key_inner, text="",
            fg_color=COLORS["surface_alt"],
            hover_color=COLORS["border"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"], border_width=1,
            corner_radius=RADIUS_CONTROL,
            height=32, width=BTN_W_KEY_TOGGLE,
            command=self.toggle_key_visibility,
        )
        self._register_font(self.btn_toggle_key, "button_sub")
        self.btn_toggle_key.pack(side="right")

        # Key entry (hidden by default — show="*").
        self.entry_key = ctk.CTkEntry(
            row_key_inner,
            textvariable=self.key_var,
            show="*", placeholder_text="",
            fg_color=COLORS["surface_alt"],
            border_color=COLORS["accent"],
            text_color=COLORS["text_primary"],
            corner_radius=RADIUS_CONTROL, height=32,
        )
        # Register so the font refresh path stays consistent with every
        # other widget (mono_key is language-independent today, but using
        # the same registration mechanism avoids future surprises).
        self._register_font(self.entry_key, "mono_key")
        self.entry_key.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.placeholder_widgets.append((self.entry_key, "key_placeholder"))

        self.widgets["key_note"] = self._register_font(
            ctk.CTkLabel(
                row_key, text="",
                text_color=COLORS["text_tertiary"],
                anchor="w", justify="left",
                wraplength=540,
            ),
            "note",
        )
        self.widgets["key_note"].pack(anchor="w", fill="x", pady=(8, 0))

        # ── Section 2: Output folder ─────────────────────────────────
        self._section_label(parent=controls, row=4, translation_key="section_output")

        card2   = self._card(parent=controls, row=5)
        row_out = ctk.CTkFrame(card2, fg_color="transparent")
        row_out.pack(fill="x", padx=12, pady=10)

        self.widgets["folder_button_output"] = ctk.CTkButton(
            row_out, text="",
            fg_color=COLORS["surface_alt"],
            hover_color=COLORS["border"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"], border_width=1,
            corner_radius=RADIUS_CONTROL,
            height=32, width=BTN_W_FIND_FOLDER,
            command=self.select_output_folder,
        )
        self._register_font(self.widgets["folder_button_output"], "button_sub")
        self.widgets["folder_button_output"].pack(side="right")

        self.entry_output = ctk.CTkEntry(
            row_out,
            textvariable=self.output_dir_var,
            state="readonly", placeholder_text="",
            fg_color=COLORS["surface_alt"],
            border_color=COLORS["border"],
            text_color=COLORS["text_secondary"],
            corner_radius=RADIUS_CONTROL, height=32,
        )
        self._register_font(self.entry_output, "label")
        self.entry_output.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.placeholder_widgets.append((self.entry_output, "output_placeholder"))

        # Auto-open option — lives next to the output folder so it sits
        # exactly where users are configuring "where the result goes".
        options_box = ctk.CTkFrame(card2, fg_color="transparent")
        options_box.pack(fill="x", padx=12, pady=(0, 10))

        self.widgets["auto_open_label"] = self._register_font(
            ctk.CTkCheckBox(
                options_box, text="",
                variable=self.auto_open_var,
                command=self.save_config,
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
                border_color=COLORS["border"],
                text_color=COLORS["text_secondary"],
                checkmark_color="#ffffff",
                corner_radius=RADIUS_CONTROL,
            ),
            "switch",
        )
        self.widgets["auto_open_label"].pack(anchor="w", pady=(0, 4))

        # Overwrite option — when enabled, decrypted files replace any
        # existing file with the same name (instead of generating _1, _2…).
        self.widgets["overwrite_label"] = self._register_font(
            ctk.CTkCheckBox(
                options_box, text="",
                variable=self.overwrite_var,
                command=self.save_config,
                fg_color=COLORS["accent"],
                hover_color=COLORS["accent_hover"],
                border_color=COLORS["border"],
                text_color=COLORS["text_secondary"],
                checkmark_color="#ffffff",
                corner_radius=RADIUS_CONTROL,
            ),
            "switch",
        )
        self.widgets["overwrite_label"].pack(anchor="w")

        # ── Run button (inside controls panel) ───────────────────────
        self.btn_run = ctk.CTkButton(
            controls, text="",
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#ffffff",
            corner_radius=RADIUS_BUTTON, height=44,
            command=self.start_processing,
        )
        self._register_font(self.btn_run, "button_main")
        self.btn_run.grid(row=6, column=0, sticky="ew", pady=(14, 0))

        # ── Progress bar ─────────────────────────────────────────────
        self.progress_bar = ctk.CTkProgressBar(
            controls, mode="determinate",
            fg_color=COLORS["surface_alt"],
            progress_color=COLORS["accent"],
            corner_radius=RADIUS_CONTROL,
            height=PROGRESS_BAR_HEIGHT,
        )
        self.progress_bar.set(0)
        self.progress_bar.grid(row=7, column=0, sticky="ew", pady=(8, 0))

        # ── Status label (below progress bar) ────────────────────────
        # Doubles as a keyboard-shortcut hint when idle.
        self.widgets["status_label"] = self._register_font(
            ctk.CTkLabel(
                controls, text="",
                text_color=COLORS["text_secondary"],
                anchor="w", height=STATUS_LABEL_HEIGHT,
            ),
            "note",
        )
        self.widgets["status_label"].grid(
            row=8, column=0, sticky="ew", padx=4, pady=(2, 0)
        )

        # ── Right column: log panel ──────────────────────────────────
        # The "LOG  /  Copy  Clear" header sits OUTSIDE the textbox card
        # so it lines up vertically with the section labels on the left
        # ("설정", "원본 게임 폴더", "결과물 저장 폴더").
        log_panel = ctk.CTkFrame(self.root, fg_color="transparent")
        log_panel.grid(row=2, column=1, sticky="nsew",
                       padx=(PAD_GAP, PAD_X), pady=(0, 14))
        log_panel.grid_columnconfigure(0, weight=1)
        log_panel.grid_rowconfigure(0, weight=0)  # header
        log_panel.grid_rowconfigure(1, weight=1)  # textbox card

        # Header row — same pady as section labels on the left so the
        # "LOG" baseline aligns with "설정".
        log_header = ctk.CTkFrame(log_panel, fg_color="transparent")
        log_header.grid(row=0, column=0, sticky="ew", padx=4, pady=(6, 0))
        log_header.grid_columnconfigure(0, weight=1)

        self.widgets["log_header"] = self._register_font(
            ctk.CTkLabel(
                log_header, text="",
                text_color=COLORS["text_tertiary"],
                anchor="w",
            ),
            "section",
        )
        self.widgets["log_header"].grid(row=0, column=0, sticky="w")

        self.widgets["log_copy"] = ctk.CTkButton(
            log_header, text="",
            width=BTN_W_LOG_CTRL, height=BTN_H_LOG_CTRL,
            fg_color=COLORS["surface_alt"],
            hover_color=COLORS["border"],
            text_color=COLORS["text_secondary"],
            corner_radius=RADIUS_CONTROL,
            command=self.copy_log,
        )
        self._register_font(self.widgets["log_copy"], "note")
        self.widgets["log_copy"].grid(row=0, column=1, padx=(0, 6))

        self.widgets["log_clear"] = ctk.CTkButton(
            log_header, text="",
            width=BTN_W_LOG_CTRL, height=BTN_H_LOG_CTRL,
            fg_color=COLORS["surface_alt"],
            hover_color=COLORS["border"],
            text_color=COLORS["text_secondary"],
            corner_radius=RADIUS_CONTROL,
            command=self.clear_log,
        )
        self._register_font(self.widgets["log_clear"], "note")
        self.widgets["log_clear"].grid(row=0, column=2)

        # Log textbox card — borderless, picks up the surface tone vs the
        # window bg so it visually separates without an explicit outline.
        log_card = ctk.CTkFrame(
            log_panel,
            fg_color=COLORS["surface"],
            corner_radius=RADIUS_CARD,
            border_width=0,
        )
        log_card.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(0, weight=1)

        self.log_area = ctk.CTkTextbox(
            log_card,
            fg_color="transparent",
            text_color=COLORS["text_secondary"],
            scrollbar_button_color=COLORS["border"],
            state="disabled",
            corner_radius=RADIUS_DIVIDER,
            wrap="word",
        )
        self._register_font(self.log_area, "mono_log")
        self.log_area.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------
    def _section_label(self, *, parent, row: int, translation_key: str) -> None:
        """Create a small section label inside *parent* on the given grid row."""
        label = ctk.CTkLabel(
            parent, text="",
            text_color=COLORS["text_tertiary"],
            anchor="w",
        )
        self._register_font(label, "section")
        label.grid(row=row, column=0, sticky="ew", padx=4, pady=(6, 0))
        self.widgets[translation_key] = label

    def _card(self, *, parent, row: int) -> ctk.CTkFrame:
        """Create a card frame inside *parent* on the given grid row.

        Apple-style: no outline border — the surface vs bg colour
        contrast does the visual separation.
        """
        card = ctk.CTkFrame(
            parent,
            fg_color=COLORS["surface"],
            corner_radius=RADIUS_CARD,
            border_width=0,
        )
        card.grid(row=row, column=0, sticky="ew", padx=0, pady=(6, 0))
        return card


# =====================================================================
# Entry point
# =====================================================================
if __name__ == "__main__":
    root = ctk.CTk()
    try:
        app = DecrypterApp(root)
        root.mainloop()
    finally:
        try:
            FONT_LOADER.unload()
        except Exception:
            pass
