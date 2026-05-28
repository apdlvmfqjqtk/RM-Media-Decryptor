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

VALID_LANGUAGES    = {"ko", "en", "ja", "zh"}
VALID_TARGET_MODES = {"both", "image", "audio"}

LEGACY_KEYS = (
    "decryption_key", "encryption_key", "key",
    "appearance", "overwrite",
    "workers", "priority",
)



# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_cached_config_dir: str | None = None

def _config_path() -> str:
    """Return the absolute path to the config file.

    The application directory is created on demand so that importing this
    module never triggers file-system side effects.
    """
    global _cached_config_dir
    if _cached_config_dir is None:
        base_dir = os.getenv("APPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Roaming"
        )
        _cached_config_dir = os.path.join(base_dir, "RPGDecrypter")
        os.makedirs(_cached_config_dir, exist_ok=True)
    return os.path.join(_cached_config_dir, "config.json")



def _sanitize(data: dict) -> dict:
    """Return a dict containing only the allowed, non-sensitive settings.

    input_dir is intentionally excluded — the source game folder is
    never written to disk.
    """
    language    = data.get("language", "ko")
    target_mode = data.get("target_mode", "both")

    return {
        "output_dir":   data.get("output_dir", "") or "",
        "language":     language    if language    in VALID_LANGUAGES    else "ko",
        "target_mode":  target_mode if target_mode in VALID_TARGET_MODES else "both",
        "auto_open":    bool(data.get("auto_open", False)),
        "no_key_png":   bool(data.get("no_key_png", False)),
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

    # Security hygiene + schema cleanup: purge any legacy fields we no
    # longer support so re-saving doesn't carry them forward.
    had_legacy = False
    for k in LEGACY_KEYS:
        if k in data:
            data.pop(k, None)
            had_legacy = True

    sanitized = _sanitize(data)

    # Re-save only when the file contained stale or invalid data so that
    # a normal startup does not incur a pointless write.
    # We only save if we had legacy keys, or if any of the active keys in data had a different value/was missing.
    is_dirty = had_legacy or any(data.get(k) != sanitized[k] for k in sanitized)
    if is_dirty:
        try:
            save_config_data(**sanitized)
        except Exception as e:
            import sys
            sys.stderr.write(f"[config] Failed to re-save config: {e}\n")

    return sanitized, None



def save_config_data(
    output_dir:   str  = "",
    language:     str  = "ko",
    target_mode:  str  = "both",
    auto_open:    bool = False,
    no_key_png:   bool = False,
) -> tuple[bool, Exception | None]:
    """Persist only non-sensitive UI settings.

    The decryption key and source game folder are intentionally excluded
    from the saved payload.
    """
    payload = _sanitize(
        {
            "output_dir":  output_dir,
            "language":    language,
            "target_mode": target_mode,
            "auto_open":   auto_open,
            "no_key_png":  no_key_png,
        }
    )

    try:
        with open(_config_path(), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=4)
        return True, None
    except Exception as e:
        return False, e
