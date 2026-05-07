# -*- coding: utf-8 -*-
"""Config loading and saving for RPG Decrypter.

Security policy:
    The decryption key is never persisted here.
    The source game folder (input_dir) is never saved to disk.
    Only non-sensitive UI preferences are written to the config file.
    Legacy keys found in older config files are removed automatically.
"""

from __future__ import annotations

import json
import os

VALID_LANGUAGES    = {"ko", "en", "ja"}
VALID_APPEARANCES  = {"dark", "light"}
VALID_TARGET_MODES = {"both", "image", "audio"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _config_path() -> str:
    """Return the absolute path to the config file.

    The application directory is created on demand so that importing this
    module never triggers file-system side effects.
    """
    base_dir = os.getenv("APPDATA") or os.path.join(
        os.path.expanduser("~"), "AppData", "Roaming"
    )
    app_dir = os.path.join(base_dir, "RPGDecrypter")
    os.makedirs(app_dir, exist_ok=True)
    return os.path.join(app_dir, "config.json")


def _sanitize(data: dict) -> dict:
    """Return a dict containing only the allowed, non-sensitive settings.

    input_dir is intentionally excluded — the source game folder is
    never written to disk.
    """
    language    = data.get("language", "ko")
    appearance  = data.get("appearance", "dark")
    target_mode = data.get("target_mode", "both")

    return {
        "output_dir":   data.get("output_dir", "") or "",
        "language":     language    if language    in VALID_LANGUAGES    else "ko",
        "appearance":   appearance  if appearance  in VALID_APPEARANCES  else "dark",
        "target_mode":  target_mode if target_mode in VALID_TARGET_MODES else "both",
        "auto_open":    bool(data.get("auto_open", False)),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_config_data() -> tuple[dict, Exception | None]:
    """Load the config file and return ``(config_data, error)``.

    A missing config file is not treated as an error — a default dict is
    returned instead.
    """
    config_file = _config_path()

    if not os.path.exists(config_file):
        return _sanitize({}), None

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return _sanitize({}), e

    # The file was valid JSON but not necessarily a dict (e.g. someone
    # hand-edited it to "[]" or "null"). _sanitize calls data.get(...) so
    # treat any non-dict payload as a fresh start.
    if not isinstance(data, dict):
        return _sanitize({}), None

    # Security hygiene: purge any legacy stored key fields.
    legacy_keys = ("decryption_key", "encryption_key", "key")
    if any(k in data for k in legacy_keys):
        for k in legacy_keys:
            data.pop(k, None)
        try:
            save_config_data(**_sanitize(data))
        except Exception:
            pass

    sanitized = _sanitize(data)

    # Re-save to remove stale fields (e.g. a previously stored input_dir).
    try:
        save_config_data(**sanitized)
    except Exception:
        pass

    return sanitized, None


def save_config_data(
    output_dir:   str  = "",
    language:     str  = "ko",
    appearance:   str  = "dark",
    target_mode:  str  = "both",
    auto_open:    bool = False,
) -> tuple[bool, Exception | None]:
    """Persist only non-sensitive UI settings.

    The decryption key and source game folder are intentionally excluded
    from the saved payload.
    """
    payload = _sanitize(
        {
            "output_dir":  output_dir,
            "language":    language,
            "appearance":  appearance,
            "target_mode": target_mode,
            "auto_open":   auto_open,
        }
    )

    try:
        with open(_config_path(), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=4)
        return True, None
    except Exception as e:
        return False, e
