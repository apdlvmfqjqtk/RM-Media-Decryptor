# -*- coding: utf-8 -*-
"""Core RPG Maker MV/MZ key detection, validation, and decryption logic.

This module intentionally has no tkinter/customtkinter dependency.
It returns status codes so the GUI can translate and display messages.
"""

from __future__ import annotations

import json
import os

# Encrypted-extension -> output-extension mapping.
EXT_MAP = {
    # MV
    ".rpgmvp": ".png",
    ".rpgmvo": ".ogg",
    ".rpgmvm": ".m4a",
    # MZ
    ".png_": ".png",
    ".ogg_": ".ogg",
    ".m4a_": ".m4a",
}

# Target filters used by the GUI.
IMAGE_EXTS = {".rpgmvp", ".png_"}
AUDIO_EXTS = {".rpgmvo", ".ogg_", ".rpgmvm", ".m4a_"}
TARGET_MODE_EXTS = {
    "both": set(EXT_MAP.keys()),
    "image": IMAGE_EXTS,
    "audio": AUDIO_EXTS,
}


def get_target_extensions(target_mode: str) -> set[str]:
    """Return encrypted extensions enabled by the selected target mode."""
    return set(TARGET_MODE_EXTS.get(target_mode, TARGET_MODE_EXTS["both"]))

# Extensions we recognise but cannot handle (RPG Maker VX/Ace archives etc.).
KNOWN_UNSUPPORTED_EXT = {
    ".rgss3a": "rgss3a",
    ".rgss2a": "rgss2a",
    ".rgssad": "rgssad",
}

# Normal, unencrypted media extensions.
PLAIN_MEDIA_EXT = {
    ".png": "PNG",
    ".ogg": "OGG",
    ".m4a": "M4A",
}

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
OGG_SIGNATURE = b"OggS"
RPGMV_HEADER_MAGIC = b"RPGMV"


def is_m4a_signature(data: bytes) -> bool:
    return len(data) >= 12 and data[4:8] == b"ftyp"


def mask_key(key: str) -> str:
    key = key.strip()
    if len(key) <= 10:
        return "*" * len(key)
    return f"{key[:6]}…{key[-4:]}"


def get_system_json_candidates(selected_dir: str) -> list[str]:
    parent_dir = os.path.dirname(os.path.abspath(selected_dir))
    return [
        os.path.join(selected_dir, "System.json"),
        os.path.join(selected_dir, "data", "System.json"),
        os.path.join(selected_dir, "www", "data", "System.json"),
        os.path.join(parent_dir, "data", "System.json"),
        os.path.join(parent_dir, "www", "data", "System.json"),
    ]


def extract_key_from_system_json(selected_dir: str):
    """
    Walk every candidate System.json path.

    Returns:
        (key_or_none, attempts)

    attempts is a list of:
        (path, status_code, extra_info)
    """
    attempts: list[tuple[str, str, object]] = []

    for path in get_system_json_candidates(selected_dir):
        if not os.path.exists(path):
            attempts.append((path, "not_found", None))
            continue

        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except Exception as e:
            attempts.append((path, "read_error", str(e)))
            continue

        if not isinstance(data, dict) or "encryptionKey" not in data:
            attempts.append((path, "key_missing", None))
            continue

        raw = data.get("encryptionKey")
        key = (raw or "").strip() if isinstance(raw, str) else ""
        if not key:
            attempts.append((path, "key_empty", None))
            continue

        if len(key) != 32:
            attempts.append((path, "key_bad_length", len(key)))
            continue

        try:
            bytes.fromhex(key)
        except ValueError:
            attempts.append((path, "key_non_hex", None))
            continue

        attempts.append((path, "ok", None))
        return key, attempts

    return None, attempts


def validate_key(key: str) -> tuple[bool, str]:
    key = key.strip()
    if not key:
        return False, "key_empty"
    if len(key) != 32:
        return False, "key_len"
    try:
        bytes.fromhex(key)
    except ValueError:
        return False, "key_hex"
    return True, ""


def validate_paths(input_dir: str, output_dir: str) -> tuple[bool, str]:
    if not os.path.isdir(input_dir):
        return False, "invalid_input_dir"

    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception:
        return False, "invalid_output_dir"

    if not os.path.isdir(output_dir):
        return False, "invalid_output_dir"

    input_abs = os.path.normcase(os.path.realpath(input_dir))
    output_abs = os.path.normcase(os.path.realpath(output_dir))

    if input_abs == output_abs:
        return False, "same_dir"

    try:
        common_path = os.path.commonpath([input_abs, output_abs])
        if common_path == input_abs:
            return False, "output_inside_input"
    except ValueError:
        # Different drives — that's fine.
        pass

    return True, ""


def unique_output_path(path: str) -> str:
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    idx = 1
    while True:
        candidate = f"{base}_{idx}{ext}"
        if not os.path.exists(candidate):
            return candidate
        idx += 1


def classify_input_header(header_data: bytes) -> str:
    """
    Return one of:
        ok, too_small, already_png, already_ogg, already_m4a, not_encrypted
    """
    if len(header_data) < 32:
        return "too_small"

    if header_data.startswith(RPGMV_HEADER_MAGIC):
        return "ok"

    if header_data.startswith(PNG_SIGNATURE):
        return "already_png"
    if header_data.startswith(OGG_SIGNATURE):
        return "already_ogg"
    if is_m4a_signature(header_data):
        return "already_m4a"
    return "not_encrypted"


def decrypt_asset(input_path: str, output_path: str, key_hex: str):
    """
    Decrypt a single encrypted RPG Maker asset.

    Algorithm:
        1. Skip the first 16-byte RPGMV header.
        2. XOR the next 16 bytes with the first 16 bytes of the key.
        3. Append the rest of the file unchanged.

    Returns:
        (True, "") on success
        (False, status_code_or_tuple) on skip/failure
    """
    tmp_path = output_path + ".tmp"

    try:
        key = bytearray.fromhex(key_hex)

        with open(input_path, "rb") as fin:
            header_data = fin.read(32)
            classification = classify_input_header(header_data)
            if classification != "ok":
                return False, classification

            header = bytearray(header_data[16:32])
            for idx in range(16):
                header[idx] ^= key[idx % 16]

            header_bytes = bytes(header)
            output_lower = output_path.lower()
            if output_lower.endswith(".png") and not header_bytes.startswith(PNG_SIGNATURE):
                return False, "bad_png"
            if output_lower.endswith(".ogg") and not header_bytes.startswith(OGG_SIGNATURE):
                return False, "bad_ogg"
            if output_lower.endswith(".m4a") and not is_m4a_signature(header_bytes):
                return False, "bad_m4a"

            with open(tmp_path, "wb") as fout:
                fout.write(header)
                while True:
                    chunk = fin.read(65536)
                    if not chunk:
                        break
                    fout.write(chunk)

        os.replace(tmp_path, output_path)
        return True, ""

    except OSError as e:
        cleanup_tmp(tmp_path)
        return False, ("io_error", str(e))
    except Exception as e:
        cleanup_tmp(tmp_path)
        return False, ("raw_error", str(e) or "unknown_error")


def cleanup_tmp(tmp_path: str) -> None:
    try:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    except Exception:
        pass
