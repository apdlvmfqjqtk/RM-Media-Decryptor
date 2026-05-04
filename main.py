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

Designed for PyInstaller --onedir --windowed packaging.
"""

import os
import sys
import threading
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
    get_target_extensions,
    PLAIN_MEDIA_EXT,
    decrypt_asset,
    extract_key_from_system_json,
    mask_key,
    unique_output_path,
    validate_key,
    validate_paths,
)

# =====================================================================
# 0. Windows 10/11 only guard
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
    """
    Resolve the absolute path for a bundled resource.

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
FR_PRIVATE = 0x10
WM_FONTCHANGE = 0x001D
HWND_BROADCAST = 0xFFFF

_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
_gdi32.AddFontResourceExW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
_gdi32.AddFontResourceExW.restype = ctypes.c_int
_gdi32.RemoveFontResourceExW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_void_p,
]
_gdi32.RemoveFontResourceExW.restype = wintypes.BOOL

_user32 = ctypes.WinDLL("user32", use_last_error=True)

# Files we expect to live under assets/fonts.
# Family names are what tkinter font tuples reference.
PRETENDARD_FAMILY = "Pretendard"
PRETENDARD_JP_FAMILY = "Pretendard JP"

FONT_FILES = [
    ("Pretendard-Regular.ttf", PRETENDARD_FAMILY),
    ("Pretendard-Medium.ttf", PRETENDARD_FAMILY),
    ("Pretendard-SemiBold.ttf", PRETENDARD_FAMILY),
    ("Pretendard-Bold.ttf", PRETENDARD_FAMILY),
    ("PretendardJP-Regular.ttf", PRETENDARD_JP_FAMILY),
    ("PretendardJP-Medium.ttf", PRETENDARD_JP_FAMILY),
    ("PretendardJP-SemiBold.ttf", PRETENDARD_JP_FAMILY),
    ("PretendardJP-Bold.ttf", PRETENDARD_JP_FAMILY),
]

# Conservative fallback families (Windows 10/11 ship these).
FALLBACK_FAMILY_DEFAULT = "Segoe UI"
FALLBACK_FAMILY_JP = "Yu Gothic UI"


class FontLoader:
    """Loads bundled TTFs into the process via AddFontResourceExW."""

    def __init__(self):
        self._loaded_paths: list[str] = []
        self.has_pretendard: bool = False
        self.has_pretendard_jp: bool = False

    def load(self) -> None:
        any_default = False
        any_jp = False

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
            # Tell other windows that font resources changed (harmless if it fails).
            try:
                _user32.SendMessageW(HWND_BROADCAST, WM_FONTCHANGE, 0, 0)
            except Exception:
                pass

        self.has_pretendard = any_default
        self.has_pretendard_jp = any_jp

    def family_for(self, lang_code: str) -> str:
        """Return the best available family for a given UI language."""
        if lang_code == "ja":
            if self.has_pretendard_jp:
                return PRETENDARD_JP_FAMILY
            # Some Pretendard builds cover JP glyphs; fall back to default Pretendard
            # before reaching for the OS font.
            if self.has_pretendard:
                return PRETENDARD_FAMILY
            return FALLBACK_FAMILY_JP
        # ko / en
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
#
#    Each role maps to (size, weight). The family is resolved at runtime
#    based on the UI language so KO/EN use Pretendard and JA uses
#    Pretendard JP. Monospace roles use Consolas (HEX key, log).
# =====================================================================
FONT_ROLES = {
    "title": (22, "bold"),
    "subtitle": (12, "normal"),
    "section": (11, "bold"),
    "label": (12, "normal"),
    "label_bold": (11, "bold"),
    "button_main": (15, "bold"),
    "button_sub": (12, "normal"),
    "switch": (12, "normal"),
    "menu": (12, "normal"),
    "note": (11, "normal"),
}

# Key/HEX fields keep monospace. Log roles use a CJK-safe UI font so
# Korean/Japanese text does not break in the log area.
FONT_MONO_ROLES = {
    "mono": ("Consolas", 11, "normal"),
    "mono_key": ("Consolas", 12, "normal"),
    "mono_log": ("CJK_SAFE", 10, "normal"),
    "mono_log_header": ("CJK_SAFE", 9, "bold"),
}


# =====================================================================
# 7. Color tokens (light, dark)
# =====================================================================
ctk.set_default_color_theme("blue")

COLORS = {
    "bg": ("#F5F5F7", "#161618"),
    "surface": ("#FFFFFF", "#1E1E20"),
    "surface_alt": ("#F0F0F3", "#28282C"),
    "border": ("#D1D1D6", "#3A3A3E"),
    "accent": ("#007AFF", "#0A84FF"),
    "accent_hover": ("#0066CC", "#0071E3"),
    "success": ("#248A3D", "#30D158"),
    "warning": ("#BF5B00", "#FF9F0A"),
    "danger": ("#D70015", "#FF453A"),
    "text_primary": ("#1D1D1F", "#F5F5F7"),
    "text_secondary": ("#3A3A3C", "#98989F"),
    "text_tertiary": ("#6E6E73", "#636366"),
}


# =====================================================================
# 7-1. Windows 11-style geometry tokens (100% DPI baseline)
# =====================================================================
# Microsoft-style rounded corners:
#   - Large containers/cards: 8 px
#   - Buttons, entries, menus: 4 px
#   - Dividers / flush edges: 0 px
RADIUS_CARD = 8
RADIUS_CONTROL = 4
RADIUS_BUTTON = 4
RADIUS_ENTRY = 4
RADIUS_MENU = 4
RADIUS_DIVIDER = 0


TARGET_MODE_ORDER = ("both", "image", "audio")
TARGET_MODE_TEXT_KEYS = {
    "both": "target_both",
    "image": "target_image",
    "audio": "target_audio",
}
PLAIN_MEDIA_EXTS_BY_TARGET = {
    "both": {".png", ".ogg", ".m4a"},
    "image": {".png"},
    "audio": {".ogg", ".m4a"},
}


# =====================================================================
# 10. Main app
# =====================================================================
class DecrypterApp:
    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def __init__(self, root: ctk.CTk):
        self.root = root
        self.root.title("RPG Decrypter")
        self.set_window_icon()

        # Windows 11-style compact default size.
        # Smaller minimum allows the UI to shrink with the window more naturally.
        self.root.geometry("600x900")
        self.root.minsize(400, 520)
        self.root.resizable(True, True)

        # State
        self.current_lang = "ko"
        self.current_appearance = "dark"
        self.current_target_mode = "both"
        self.is_processing = False
        self.processed_files = 0
        self.total_files = 0

        # Tk vars (key var is in-memory only; never written to disk)
        self.key_var = tk.StringVar()
        self.input_dir_var = tk.StringVar()
        self.output_dir_var = tk.StringVar()
        self.dark_mode_var = tk.BooleanVar(value=True)
        self.language_var = tk.StringVar(value=LANGUAGE_OPTIONS[self.current_lang])
        self.target_mode_var = tk.StringVar()

        # Widget bookkeeping
        # widgets[text_key]   -> widget that displays t(text_key)
        # widgets_alias       -> widget bookkeeping name -> text_key
        # font_registry       -> [(widget, role)]   for re-applying fonts on lang change
        # placeholder_widgets -> [(entry_widget, text_key)]
        self.widgets: dict[str, tk.Widget] = {}
        self.widgets_alias: dict[str, str] = {}
        self.font_registry: list[tuple[tk.Widget, str]] = []
        self.placeholder_widgets: list[tuple[ctk.CTkEntry, str]] = []

        # Load persisted (non-sensitive) settings BEFORE building UI
        self.load_config(silent=True)
        ctk.set_appearance_mode(
            "dark" if self.current_appearance == "dark" else "light"
        )
        self.dark_mode_var.set(self.current_appearance == "dark")
        self.language_var.set(
            LANGUAGE_OPTIONS.get(self.current_lang, LANGUAGE_OPTIONS["ko"])
        )

        self.root.configure(fg_color=COLORS["bg"])
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # First language application: don't log "language changed" or write config.
        self.apply_language(log_change=False, save=False)

        # Note in the log if the bundled fonts are missing.
        if not (FONT_LOADER.has_pretendard or FONT_LOADER.has_pretendard_jp):
            self.log(self.t("fonts_missing_note"))

    def set_window_icon(self) -> None:
        """Apply the app window icon in both source-run and PyInstaller modes."""
        for rel in (
            os.path.join("assets", "myicon.ico"),
            os.path.join("assets", "icon", "myicon.ico"),
            "myicon.ico",
        ):
            icon_path = resource_path(rel)
            if os.path.isfile(icon_path):
                try:
                    self.root.iconbitmap(icon_path)
                except Exception:
                    pass
                return

    # ------------------------------------------------------------------
    # Translation / fonts
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
        """Return a font tuple for a UI role using the current language family."""
        if role in ("mono_log", "mono_log_header"):
            _, size, weight = FONT_MONO_ROLES[role]
            return (FONT_LOADER.multilingual_family(), size, weight)
        if role in FONT_MONO_ROLES:
            return FONT_MONO_ROLES[role]
        if role == "menu":
            # The language menu contains 한국어 / English / 日本語 at the same time,
            # so use a CJK-safe font regardless of the currently selected language.
            family = FONT_LOADER.multilingual_family()
        else:
            family = FONT_LOADER.family_for(self.current_lang)
        size, weight = FONT_ROLES[role]
        return (family, size, weight)

    def _register_font(self, widget: tk.Widget, role: str) -> tk.Widget:
        """Apply font + remember the (widget, role) pair so language change can refresh it."""
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
                        font=self._font(role), dropdown_font=self._font(role)
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

        self.input_dir_var.set(data.get("input_dir", "") or "")
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

    def save_config(self) -> bool:
        ok, error = save_config_data(
            input_dir=self.input_dir_var.get(),
            output_dir=self.output_dir_var.get(),
            language=self.current_lang,
            appearance=self.current_appearance,
            target_mode=self.current_target_mode,
        )
        if not ok:
            self.log(self.t("config_saved_fail", error=error))
        return ok

    def save_settings_action(self):
        if self.save_config():
            messagebox.showinfo(self.t("save_title"), self.t("save_done"))

    # ------------------------------------------------------------------
    # Language / appearance
    # ------------------------------------------------------------------
    def apply_language(self, log_change: bool = True, save: bool = True) -> None:
        # Window title
        self.root.title(self.t("window_title"))

        # Refresh fonts (family may switch when toggling KO/EN <-> JA)
        self._refresh_fonts()

        # Re-text every registered widget by translation key
        for key, widget in self.widgets.items():
            if key in TEXT[self.current_lang]:
                try:
                    widget.configure(text=self.t(key))
                except Exception:
                    pass

        # Aliases (multiple widgets sharing the same translation key)
        for widget_key, text_key in self.widgets_alias.items():
            if widget_key in self.widgets:
                try:
                    self.widgets[widget_key].configure(text=self.t(text_key))
                except Exception:
                    pass

        # Entry placeholders
        for entry, text_key in self.placeholder_widgets:
            try:
                entry.configure(placeholder_text=self.t(text_key))
            except Exception:
                pass

        if hasattr(self, "target_mode_menu"):
            self._refresh_target_mode_menu()

        # Run button (depends on processing state)
        if not self.is_processing:
            self.btn_run.configure(text=self.t("run_button"))
        else:
            self._update_progress_button_text()

        if log_change:
            self.log(self.t("lang_changed"))

        if save:
            self.save_config()

    def on_language_changed(self, selected_label: str):
        lang_code = LANGUAGE_CODES_BY_LABEL.get(selected_label, "ko")
        self.current_lang = lang_code
        self.language_var.set(LANGUAGE_OPTIONS[lang_code])
        self.apply_language(log_change=True, save=True)

    def on_dark_mode_toggle(self):
        if self.dark_mode_var.get():
            self.current_appearance = "dark"
            ctk.set_appearance_mode("dark")
            self.log(self.t("mode_dark"))
        else:
            self.current_appearance = "light"
            ctk.set_appearance_mode("light")
            self.log(self.t("mode_light"))
        self.save_config()

    def _target_mode_label(self, mode: str) -> str:
        return self.t(TARGET_MODE_TEXT_KEYS.get(mode, "target_both"))

    def _refresh_target_mode_menu(self) -> None:
        values = [self._target_mode_label(mode) for mode in TARGET_MODE_ORDER]
        try:
            self.target_mode_menu.configure(values=values)
        except Exception:
            pass
        self.target_mode_var.set(self._target_mode_label(self.current_target_mode))

    def on_target_mode_changed(self, selected_label: str):
        for mode in TARGET_MODE_ORDER:
            if selected_label == self._target_mode_label(mode):
                self.current_target_mode = mode
                break
        else:
            self.current_target_mode = "both"
        self.target_mode_var.set(self._target_mode_label(self.current_target_mode))
        self.save_config()

    # ------------------------------------------------------------------
    # Folder selection / key auto-detect
    # ------------------------------------------------------------------
    def select_output_folder(self):
        folder = filedialog.askdirectory(title=self.t("select_output_dialog"))
        if folder:
            self.output_dir_var.set(folder)
            self.save_config()

    def select_game_folder(self):
        selected_dir = filedialog.askdirectory(title=self.t("select_game_dialog"))
        if not selected_dir:
            return

        # Autocorrect: if "<root>/www/img" exists this is an MV layout — record www as input.
        input_dir = (
            os.path.join(selected_dir, "www")
            if os.path.exists(os.path.join(selected_dir, "www", "img"))
            else selected_dir
        )
        self.input_dir_var.set(input_dir)

        # Try to auto-extract the encryption key, and log every path we tried.
        key, attempts = extract_key_from_system_json(selected_dir)

        self.log(self.t("key_search_header"))
        for path, status_key, extra in attempts:
            status_text = self._format_key_status(status_key, extra)
            self.log(self.t("key_search_path_check", path=path, status=status_text))

        if key:
            self.key_var.set(key)
            self.log(self.t("key_found", key=mask_key(key)))
        else:
            self.log(self.t("key_search_failed"))

        self.save_config()

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
        """Translate rpg_core failure codes into a user-facing message."""
        if isinstance(reason, tuple):
            code = reason[0]
            detail = reason[1] if len(reason) > 1 else ""
            if code == "io_error":
                return self.t("io_error", error=detail)
            if code == "raw_error":
                if detail == "unknown_error":
                    return self.t("unknown_error")
                return str(detail)
            return str(detail or code)

        if reason in (
            "bad_png",
            "bad_ogg",
            "bad_m4a",
            "unknown_error",
            "file_too_small",
        ):
            return self.t(reason)
        return str(reason)

    # ------------------------------------------------------------------
    # Run / worker thread
    # ------------------------------------------------------------------
    def start_processing(self):
        key = self.key_var.get().strip()
        input_dir = self.input_dir_var.get().strip()
        output_dir = self.output_dir_var.get().strip()

        if not key or not input_dir or not output_dir:
            messagebox.showwarning(self.t("warning_title"), self.t("missing_fields"))
            return

        key_ok, key_msg = validate_key(key)
        if not key_ok:
            messagebox.showwarning(self.t("warning_title"), self.t(key_msg))
            return

        path_ok, path_msg = validate_paths(input_dir, output_dir)
        if not path_ok:
            messagebox.showwarning(self.t("warning_title"), self.t(path_msg))
            return

        self.is_processing = True
        self.processed_files = 0
        self.total_files = 0
        self.btn_run.configure(state="disabled", text=self.t("searching_button"))
        self.save_config()

        worker = threading.Thread(
            target=self.process_files,
            args=(key, input_dir, output_dir, self.current_target_mode),
            daemon=True,
        )
        worker.start()

    def process_files(self, key: str, input_dir: str, output_dir: str, target_mode: str):
        self.log(self.t("start_log"))
        self.log(self.t("scan_log"))

        try:
            target_exts = get_target_extensions(target_mode)
            plain_media_exts = PLAIN_MEDIA_EXTS_BY_TARGET.get(
                target_mode,
                PLAIN_MEDIA_EXTS_BY_TARGET["both"],
            )
            target_files = []
            unsupported_count = 0
            plain_media_counts = {".png": 0, ".ogg": 0, ".m4a": 0}

            for root_dir, _, files in os.walk(input_dir):
                for filename in files:
                    ext = os.path.splitext(filename)[1].lower()
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

            if self.total_files == 0:
                self.log(self.t("no_files"))
                return

            self.log(self.t("count_log", total=self.total_files))
            self.log(self.t("progress_log", percent=0, processed=0, total=self.total_files))

            success_count = 0
            fail_count = 0
            skip_count = unsupported_count
            failed_files: list[tuple[str, str]] = []
            last_logged_bucket = 0

            for root_dir, filename, ext in target_files:
                input_path = os.path.join(root_dir, filename)
                relative_dir = os.path.relpath(root_dir, input_dir)
                target_dir = os.path.join(output_dir, relative_dir)
                os.makedirs(target_dir, exist_ok=True)

                stem, _ = os.path.splitext(filename)
                desired_output = os.path.join(target_dir, stem + EXT_MAP[ext])
                output_path = unique_output_path(desired_output)

                ok, reason = decrypt_asset(input_path, output_path, key)

                self.processed_files += 1

                if ok:
                    success_count += 1
                else:
                    if reason in (
                        "too_small",
                        "already_png",
                        "already_ogg",
                        "already_m4a",
                        "not_encrypted",
                    ):
                        skip_count += 1
                    else:
                        fail_count += 1
                        failed_files.append((input_path, self._format_decrypt_error(reason)))

                percent = int((self.processed_files / self.total_files) * 100)
                progress_bucket = (percent // 5) * 5
                should_log_progress = (
                    progress_bucket > last_logged_bucket
                    or self.processed_files == self.total_files
                )

                if should_log_progress:
                    last_logged_bucket = progress_bucket
                    self.log(
                        self.t(
                            "progress_log",
                            percent=percent,
                            processed=self.processed_files,
                            total=self.total_files,
                        )
                    )
                    self._update_progress_button_text()

            self.log(
                self.t(
                    "done_log",
                    success=success_count,
                    failed=fail_count,
                    skipped=skip_count,
                    total=self.total_files,
                )
            )
            if fail_count == 0:
                self.log(self.t("done_all_success"))
            else:
                self.log(self.t("done_some_failed"))
                self.log(self.t("failed_files_header"))
                for path, reason in failed_files:
                    self.log(self.t("file_failed", path=path, reason=reason))

        except Exception as e:
            self.log(self.t("fatal_error", error=e))

        finally:
            self.finish_processing()

    def _update_progress_button_text(self):
        if self.total_files <= 0:
            text = self.t("searching_button")
        else:
            percent = int((self.processed_files / self.total_files) * 100)
            text = self.t(
                "progress_button",
                processed=self.processed_files,
                total=self.total_files,
                percent=percent,
            )
        self.root.after(0, lambda t=text: self.btn_run.configure(text=t))

    def finish_processing(self):
        def reset_button():
            self.is_processing = False
            self.btn_run.configure(state="normal", text=self.t("run_button"))

        self.root.after(0, reset_button)

    # ------------------------------------------------------------------
    # Logging (always marshalled to the main thread)
    # ------------------------------------------------------------------
    def log(self, message: str):
        self.root.after(0, lambda: self._append_log(message))

    def _append_log(self, message: str):
        try:
            self.log_area.configure(state="normal")
            self.log_area.insert(tk.END, message + "\n")
            self.log_area.see(tk.END)
            self.log_area.configure(state="disabled")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Window close
    # ------------------------------------------------------------------
    def on_close(self):
        if self.is_processing:
            messagebox.showwarning(
                self.t("warning_title"), self.t("close_while_processing")
            )
            return
        try:
            FONT_LOADER.unload()
        except Exception:
            pass
        self.root.destroy()

    # ==================================================================
    # UI construction (uses grid on the root for proper resize behaviour)
    # ==================================================================
    def _build_ui(self):
        self.root.grid_columnconfigure(0, weight=1)
        # Fixed-height rows are weight=0; the log frame at the bottom takes
        # the remaining vertical space.
        for r in range(0, 9):
            self.root.grid_rowconfigure(r, weight=0)
        self.root.grid_rowconfigure(9, weight=1)

        PAD_X = 28

        # ── Header (title + subtitle) ────────────────────────────────
        header = ctk.CTkFrame(
            self.root, fg_color="transparent", corner_radius=RADIUS_DIVIDER
        )
        header.grid(row=0, column=0, sticky="ew", padx=PAD_X, pady=(22, 4))
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
                header,
                text="",
                text_color=COLORS["text_tertiary"],
                anchor="w",
                justify="left",
                wraplength=900,
            ),
            "subtitle",
        )
        self.widgets["app_subtitle"].grid(row=1, column=0, sticky="ew", pady=(4, 0))

        # Divider
        ctk.CTkFrame(
            self.root, height=1, fg_color=COLORS["border"], corner_radius=RADIUS_DIVIDER
        ).grid(row=1, column=0, sticky="ew", padx=PAD_X, pady=(10, 14))

        # ── Section 0: Settings ──────────────────────────────────────
        self._section_label(row=2, translation_key="settings_section", padx=PAD_X)

        settings_card = self._card(row=3, padx=PAD_X)
        settings_row = ctk.CTkFrame(settings_card, fg_color="transparent")
        settings_row.pack(fill="x", padx=16, pady=14)
        settings_row.grid_columnconfigure(0, weight=1)
        settings_row.grid_columnconfigure(1, weight=1)

        # Appearance
        mode_box = ctk.CTkFrame(settings_row, fg_color="transparent")
        mode_box.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.widgets["appearance_label"] = self._register_font(
            ctk.CTkLabel(
                mode_box, text="", text_color=COLORS["text_tertiary"], anchor="w"
            ),
            "label_bold",
        )
        self.widgets["appearance_label"].pack(anchor="w", pady=(0, 6))
        self.widgets["dark_mode"] = self._register_font(
            ctk.CTkSwitch(
                mode_box,
                text="",
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
            ctk.CTkLabel(
                lang_box, text="", text_color=COLORS["text_tertiary"], anchor="w"
            ),
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
            font=self._font("menu"),
            dropdown_font=self._font("menu"),
            corner_radius=RADIUS_MENU,
            height=36,
        )
        self._register_font(self.language_menu, "menu")
        self.language_menu.pack(fill="x")

        # Target mode
        target_box = ctk.CTkFrame(settings_card, fg_color="transparent")
        target_box.pack(fill="x", padx=16, pady=(0, 14))

        self.widgets["target_label"] = self._register_font(
            ctk.CTkLabel(
                target_box,
                text="",
                text_color=COLORS["text_tertiary"],
                anchor="w",
            ),
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
            font=self._font("menu"),
            dropdown_font=self._font("menu"),
            corner_radius=RADIUS_MENU,
            height=36,
        )
        self._register_font(self.target_mode_menu, "menu")
        self.target_mode_menu.pack(fill="x")

        # ── Section 1: Source folder + key ───────────────────────────
        self._section_label(row=4, translation_key="section_game", padx=PAD_X)

        card1 = self._card(row=5, padx=PAD_X)

        row_folder = ctk.CTkFrame(card1, fg_color="transparent")
        row_folder.pack(fill="x", padx=16, pady=(14, 8))

        self.entry_input = ctk.CTkEntry(
            row_folder,
            textvariable=self.input_dir_var,
            state="readonly",
            placeholder_text="",
            fg_color=COLORS["surface_alt"],
            border_color=COLORS["border"],
            text_color=COLORS["text_secondary"],
            corner_radius=RADIUS_CONTROL,
            height=36,
        )
        self._register_font(self.entry_input, "label")
        self.entry_input.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.placeholder_widgets.append((self.entry_input, "input_placeholder"))

        self.widgets["folder_button_game"] = ctk.CTkButton(
            row_folder,
            text="",
            fg_color=COLORS["surface_alt"],
            hover_color=COLORS["border"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=RADIUS_CONTROL,
            height=36,
            width=110,
            command=self.select_game_folder,
        )
        self._register_font(self.widgets["folder_button_game"], "button_sub")
        self.widgets["folder_button_game"].pack(side="right")

        ctk.CTkFrame(card1, height=1, fg_color=COLORS["border"]).pack(
            fill="x", padx=16, pady=0
        )

        # Key row
        row_key = ctk.CTkFrame(card1, fg_color="transparent")
        row_key.pack(fill="x", padx=16, pady=(10, 14))

        self.widgets["key_label"] = self._register_font(
            ctk.CTkLabel(row_key, text="", text_color=COLORS["text_tertiary"]),
            "label_bold",
        )
        self.widgets["key_label"].pack(anchor="w", pady=(0, 5))

        row_key_inner = ctk.CTkFrame(row_key, fg_color="transparent")
        row_key_inner.pack(fill="x")

        self.entry_key = ctk.CTkEntry(
            row_key_inner,
            textvariable=self.key_var,
            placeholder_text="",
            fg_color=COLORS["surface_alt"],
            border_color=COLORS["accent"],
            text_color=COLORS["success"],
            corner_radius=RADIUS_CONTROL,
            height=36,
        )
        # The key field uses a monospace font — leave it unchanged across languages.
        self.entry_key.configure(font=self._font("mono_key"))
        self.entry_key.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.placeholder_widgets.append((self.entry_key, "key_placeholder"))

        self.widgets["save_button"] = ctk.CTkButton(
            row_key_inner,
            text="",
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#ffffff",
            corner_radius=RADIUS_CONTROL,
            height=36,
            width=120,
            command=self.save_settings_action,
        )
        self._register_font(self.widgets["save_button"], "button_sub")
        self.widgets["save_button"].pack(side="right")

        self.widgets["key_note"] = self._register_font(
            ctk.CTkLabel(
                row_key,
                text="",
                text_color=COLORS["text_tertiary"],
                anchor="w",
                justify="left",
                wraplength=860,
            ),
            "note",
        )
        self.widgets["key_note"].pack(anchor="w", fill="x", pady=(8, 0))

        # ── Section 2: Output folder ─────────────────────────────────
        self._section_label(row=6, translation_key="section_output", padx=PAD_X)

        card2 = self._card(row=7, padx=PAD_X)

        row_out = ctk.CTkFrame(card2, fg_color="transparent")
        row_out.pack(fill="x", padx=16, pady=14)

        self.entry_output = ctk.CTkEntry(
            row_out,
            textvariable=self.output_dir_var,
            state="readonly",
            placeholder_text="",
            fg_color=COLORS["surface_alt"],
            border_color=COLORS["border"],
            text_color=COLORS["text_secondary"],
            corner_radius=RADIUS_CONTROL,
            height=36,
        )
        self._register_font(self.entry_output, "label")
        self.entry_output.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.placeholder_widgets.append((self.entry_output, "output_placeholder"))

        self.widgets["folder_button_output"] = ctk.CTkButton(
            row_out,
            text="",
            fg_color=COLORS["surface_alt"],
            hover_color=COLORS["border"],
            text_color=COLORS["text_primary"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=RADIUS_CONTROL,
            height=36,
            width=110,
            command=self.select_output_folder,
        )
        self._register_font(self.widgets["folder_button_output"], "button_sub")
        self.widgets["folder_button_output"].pack(side="right")

        # ── Run button ───────────────────────────────────────────────
        self.btn_run = ctk.CTkButton(
            self.root,
            text="",
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            text_color="#ffffff",
            corner_radius=RADIUS_BUTTON,
            height=54,
            command=self.start_processing,
        )
        self._register_font(self.btn_run, "button_main")
        self.btn_run.grid(row=8, column=0, sticky="ew", padx=PAD_X, pady=(18, 0))

        # ── Log frame (expanding) ────────────────────────────────────
        log_frame = ctk.CTkFrame(
            self.root,
            fg_color=COLORS["surface"],
            corner_radius=RADIUS_CARD,
            border_width=1,
            border_color=COLORS["border"],
        )
        log_frame.grid(row=9, column=0, sticky="nsew", padx=PAD_X, pady=(14, 20))
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)

        log_header = ctk.CTkFrame(log_frame, fg_color="transparent")
        log_header.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 4))

        self.widgets["log_header"] = ctk.CTkLabel(
            log_header,
            text="",
            text_color=COLORS["success"],
        )
        # Log header uses a CJK-safe font so Japanese/Korean text stays intact.
        self._register_font(self.widgets["log_header"], "mono_log_header")
        self.widgets["log_header"].pack(side="left")

        self.log_area = ctk.CTkTextbox(
            log_frame,
            fg_color="transparent",
            text_color=COLORS["text_secondary"],
            scrollbar_button_color=COLORS["border"],
            state="disabled",
            corner_radius=RADIUS_DIVIDER,
            wrap="word",
        )
        self._register_font(self.log_area, "mono_log")
        self.log_area.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 8))

        # Multiple widgets show the same translation ("folder_button" label).
        self.widgets_alias = {
            "folder_button_game": "folder_button",
            "folder_button_output": "folder_button",
        }

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------
    def _section_label(self, *, row: int, translation_key: str, padx: int):
        label = ctk.CTkLabel(
            self.root,
            text="",
            text_color=COLORS["text_tertiary"],
            anchor="w",
        )
        self._register_font(label, "section")
        label.grid(row=row, column=0, sticky="ew", padx=padx + 4, pady=(14, 0))
        self.widgets[translation_key] = label

    def _card(self, *, row: int, padx: int) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            self.root,
            fg_color=COLORS["surface"],
            corner_radius=RADIUS_CARD,
            border_width=1,
            border_color=COLORS["border"],
        )
        card.grid(row=row, column=0, sticky="ew", padx=padx, pady=(6, 0))
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