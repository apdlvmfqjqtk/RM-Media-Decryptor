# -*- coding: utf-8 -*-
"""Config loading/saving for RPG Decrypter.

Security note:
    The decryption key is never saved here.
    The source game folder is also not saved.
    Only non-sensitive UI preferences are saved.
    Legacy keys found in older config files are removed automatically.
"""

from __future__ import annotations

import json
import os

VALID_LANGUAGES = {"ko", "en", "ja"}
VALID_APPEARANCES = {"dark", "light"}
VALID_TARGET_MODES = {"both", "image", "audio"}


def get_config_file() -> str:
    base_dir = os.getenv("APPDATA") or os.path.join(
        os.path.expanduser("~"), "AppData", "Roaming"
    )
    app_dir = os.path.join(base_dir, "RPGDecrypter")
    os.makedirs(app_dir, exist_ok=True)
    return os.path.join(app_dir, "config.json")


CONFIG_FILE = get_config_file()


def sanitize_config(data: dict) -> dict:
    """Keep only non-sensitive settings."""
    language = data.get("language", "ko")
    appearance = data.get("appearance", "dark")
    target_mode = data.get("target_mode", "both")

    return {
        # 원본 게임 폴더는 저장하지 않음
        "input_dir": "",
        # 결과물 저장 폴더만 저장
        "output_dir": data.get("output_dir", "") or "",
        "language": language if language in VALID_LANGUAGES else "ko",
        "appearance": appearance if appearance in VALID_APPEARANCES else "dark",
        "target_mode": target_mode if target_mode in VALID_TARGET_MODES else "both",
    }


def load_config_data() -> tuple[dict, Exception | None]:
    """Return (config_data, error). Missing config is not an error."""
    if not os.path.exists(CONFIG_FILE):
        return sanitize_config({}), None

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return sanitize_config({}), e

    # Security hygiene: purge any legacy stored key.
    if "decryption_key" in data or "encryption_key" in data or "key" in data:
        data.pop("decryption_key", None)
        data.pop("encryption_key", None)
        data.pop("key", None)
        try:
            save_config_data(**sanitize_config(data))
        except Exception:
            pass

    # input_dir가 예전 config에 남아 있어도 여기서 무조건 빈 값으로 정리됨
    sanitized = sanitize_config(data)

    # 기존 config.json에 남아 있던 input_dir도 파일에서 제거되도록 한 번 다시 저장
    try:
        save_config_data(**sanitized)
    except Exception:
        pass

    return sanitized, None


def save_config_data(
    input_dir: str = "",
    output_dir: str = "",
    language: str = "ko",
    appearance: str = "dark",
    target_mode: str = "both",
) -> tuple[bool, Exception | None]:
    """Save only non-sensitive UI settings.

    The decryption key is intentionally excluded.
    The source game folder(input_dir) is intentionally not saved.
    """
    payload = sanitize_config(
        {
            # input_dir는 넘겨받아도 sanitize_config에서 빈 값으로 처리됨
            "input_dir": input_dir,
            "output_dir": output_dir,
            "language": language,
            "appearance": appearance,
            "target_mode": target_mode,
        }
    )

    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=4)
        return True, None
    except Exception as e:
        return False, e