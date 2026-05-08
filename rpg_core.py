# -*- coding: utf-8 -*-
"""Core RPG Maker MV/MZ key detection, validation, and decryption logic.

This module has no tkinter/customtkinter dependency by design.
All functions return plain status codes so the GUI layer can translate
and display messages in the appropriate language.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from typing import NamedTuple

# ---------------------------------------------------------------------------
# Extension maps
# ---------------------------------------------------------------------------

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
    """Return the set of encrypted extensions enabled by *target_mode*."""
    return set(TARGET_MODE_EXTS.get(target_mode, TARGET_MODE_EXTS["both"]))


# Extensions that are recognised but cannot be handled
# (RPG Maker VX / Ace archive formats, etc.).
KNOWN_UNSUPPORTED_EXT: set[str] = {".rgss3a", ".rgss2a", ".rgssad"}

# Normal, unencrypted media extensions that may appear alongside encrypted files.
PLAIN_MEDIA_EXT = {
    ".png": "PNG",
    ".ogg": "OGG",
    ".m4a": "M4A",
}

# ---------------------------------------------------------------------------
# Magic bytes
# ---------------------------------------------------------------------------
PNG_SIGNATURE      = b"\x89PNG\r\n\x1a\n"
OGG_SIGNATURE      = b"OggS"
RPGMV_HEADER_MAGIC = b"RPGMV"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def is_m4a_signature(data: bytes) -> bool:
    """Return True if *data* starts with an M4A/MP4 'ftyp' box."""
    return len(data) >= 12 and data[4:8] == b"ftyp"


def mask_key(key: str) -> str:
    """Return a partially masked representation of *key* for safe logging."""
    key = key.strip()
    if len(key) <= 10:
        return "*" * len(key)
    return f"{key[:6]}...{key[-4:]}"


def get_system_json_candidates(selected_dir: str) -> list[str]:
    """Return candidate System.json paths relative to *selected_dir*."""
    parent_dir = os.path.dirname(os.path.abspath(selected_dir))
    return [
        os.path.join(selected_dir, "System.json"),
        os.path.join(selected_dir, "data", "System.json"),
        os.path.join(selected_dir, "www", "data", "System.json"),
        os.path.join(parent_dir, "data", "System.json"),
        os.path.join(parent_dir, "www", "data", "System.json"),
    ]


class SystemJsonScan(NamedTuple):
    """Result of scanning System.json files for encryption metadata.

    Attributes:
        key:                  Extracted 32-char hex key, or None.
        attempts:             Per-path status log (path, status_code, extra).
        has_encrypted_images: True if any System.json has hasEncryptedImages=true.
        has_encrypted_audio:  True if any System.json has hasEncryptedAudio=true.
        found_system_json:    True if at least one System.json file existed.
    """
    key:                  str | None
    attempts:             list[tuple[str, str, object]]
    has_encrypted_images: bool
    has_encrypted_audio:  bool
    found_system_json:    bool


def extract_key_from_system_json(selected_dir: str) -> SystemJsonScan:
    """Walk every candidate System.json path and gather encryption metadata.

    The function reads `encryptionKey`, `hasEncryptedImages`, and
    `hasEncryptedAudio` so callers can distinguish between:
      * A correctly-detected key
      * An encrypted game whose key could not be parsed
      * A game that simply isn't encrypted at all
    """
    attempts: list[tuple[str, str, object]] = []
    has_img_enc      = False
    has_aud_enc      = False
    found_any        = False

    for path in get_system_json_candidates(selected_dir):
        if not os.path.exists(path):
            attempts.append((path, "not_found", None))
            continue

        # At least one System.json exists on disk.
        found_any = True

        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except Exception as e:
            attempts.append((path, "read_error", str(e)))
            continue

        if not isinstance(data, dict):
            attempts.append((path, "key_missing", None))
            continue

        # OR-accumulate encryption flags across all System.json files.
        if data.get("hasEncryptedImages"):
            has_img_enc = True
        if data.get("hasEncryptedAudio"):
            has_aud_enc = True

        if "encryptionKey" not in data:
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
        return SystemJsonScan(
            key=key,
            attempts=attempts,
            has_encrypted_images=has_img_enc,
            has_encrypted_audio=has_aud_enc,
            found_system_json=True,
        )

    return SystemJsonScan(
        key=None,
        attempts=attempts,
        has_encrypted_images=has_img_enc,
        has_encrypted_audio=has_aud_enc,
        found_system_json=found_any,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_key(key: str) -> tuple[bool, str]:
    """Return ``(True, "")`` when *key* is a valid 32-character hex string."""
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
    """Validate input/output directories and create *output_dir* if needed.

    Pre-flight relationship checks (same_dir, output_inside_input) run
    BEFORE makedirs so a rejected output_dir does not leave a stray empty
    folder polluting the user's filesystem (notably the input folder).
    """
    if not os.path.isdir(input_dir):
        return False, "invalid_input_dir"

    # realpath works on non-existent paths — it just normalises the segments
    # that do exist and returns the rest as-is. Safe to use for the
    # relationship comparison before the directory is actually created.
    input_abs  = os.path.normcase(os.path.realpath(input_dir))
    output_abs = os.path.normcase(os.path.realpath(output_dir))

    if input_abs == output_abs:
        return False, "same_dir"

    try:
        if os.path.commonpath([input_abs, output_abs]) == input_abs:
            return False, "output_inside_input"
    except ValueError:
        # Paths are on different drives — that is fine.
        pass

    # Relationship checks passed — now safe to create the output directory.
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception:
        return False, "invalid_output_dir"

    if not os.path.isdir(output_dir):
        return False, "invalid_output_dir"

    return True, ""


# ---------------------------------------------------------------------------
# Output path utilities
# ---------------------------------------------------------------------------

def unique_output_path(path: str) -> str:
    """Return *path* if it does not exist, otherwise append an incrementing
    numeric suffix until a free path is found.

    Tries up to 9 999 numeric suffixes; falls back to a Unix-timestamp suffix
    to guarantee uniqueness without an unbounded loop.
    """
    if not os.path.exists(path):
        return path

    base, ext = os.path.splitext(path)
    for idx in range(1, 10_000):
        candidate = f"{base}_{idx}{ext}"
        if not os.path.exists(candidate):
            return candidate

    # Extreme fallback: use the current timestamp (microsecond resolution).
    # time_ns gives full integer precision; floats from time.time() lose
    # sub-second precision past 2038-ish.
    return f"{base}_{time.time_ns() // 1000}{ext}"


# ---------------------------------------------------------------------------
# Decryption
# ---------------------------------------------------------------------------

# Copy buffer size for the unencrypted body of each file.
# Python's own shutil.copyfile uses a 1 MiB buffer on Windows (vs the 64 KiB
# default of shutil.copyfileobj) and benchmarks 20-40% faster on large media
# files. RPG Maker audio (.ogg/.m4a) routinely runs into multi-MB territory,
# so we adopt the same Windows-tuned size.
COPY_BUFSIZE = 1024 * 1024

def classify_input_header(header_data: bytes) -> str:
    """Classify the first 32 bytes of a file.

    Returns one of:
        ``"ok"``           – valid RPGMV header, ready to decrypt
        ``"too_small"``    – file is smaller than 32 bytes
        ``"already_png"``  – file is already a plain PNG
        ``"already_ogg"``  – file is already a plain OGG
        ``"already_m4a"``  – file is already a plain M4A
        ``"not_encrypted"``– no recognised header
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


def decrypt_asset(input_path: str, output_path: str, key_bytes: bytes):
    """Decrypt a single encrypted RPG Maker asset.

    Algorithm:
        1. Skip the 16-byte RPGMV header.
        2. XOR the next 16 bytes with the first 16 bytes of *key_bytes*.
        3. Append the remainder of the file unchanged.

    Args:
        input_path:  Path to the encrypted source file.
        output_path: Destination path for the decrypted file.
        key_bytes:   Pre-parsed key bytes. Accepting ``bytes`` instead of a
                     hex string avoids redundant conversion for every file in
                     a batch operation.

    Returns:
        ``(True, "")`` on success.
        ``(False, status_code_or_tuple)`` on skip or failure.
    """
    # Defensive check: callers always pass a 16-byte key from a validated
    # 32-char hex string, but guard against accidental misuse.
    if len(key_bytes) < 16:
        return False, ("raw_error", "key_too_short")

    tmp_path = output_path + ".tmp"

    try:
        with open(input_path, "rb") as fin:
            header_data    = fin.read(32)
            classification = classify_input_header(header_data)
            if classification != "ok":
                return False, classification

            # XOR the 16 encrypted bytes against the first 16 bytes of the key.
            header = bytes(a ^ b for a, b in zip(header_data[16:32], key_bytes[:16]))

            # Verify the decrypted header matches the expected file signature.
            sig_error = _verify_signature(output_path, header)
            if sig_error is not None:
                return False, sig_error

            # Write decrypted header + remaining file data to a temp file,
            # then atomically replace the destination.
            with open(tmp_path, "wb") as fout:
                fout.write(header)
                shutil.copyfileobj(fin, fout, length=COPY_BUFSIZE)

        os.replace(tmp_path, output_path)
        return True, ""

    except OSError as e:
        _cleanup_tmp(tmp_path)
        return False, ("io_error", str(e))
    except Exception as e:
        _cleanup_tmp(tmp_path)
        return False, ("raw_error", str(e) or "unknown_error")


# Output-extension -> (validator, error_code) for the post-XOR header check.
_SIGNATURE_CHECKS = {
    ".png": (lambda h: h.startswith(PNG_SIGNATURE), "bad_png"),
    ".ogg": (lambda h: h.startswith(OGG_SIGNATURE), "bad_ogg"),
    ".m4a": (is_m4a_signature, "bad_m4a"),
}


def _verify_signature(output_path: str, header: bytes) -> str | None:
    """Return an error code if *header* doesn't match the expected magic bytes
    for *output_path*'s extension, otherwise None."""
    ext = os.path.splitext(output_path)[1].lower()
    check = _SIGNATURE_CHECKS.get(ext)
    if check is None:
        return None
    validator, error_code = check
    return None if validator(header) else error_code


def _cleanup_tmp(tmp_path: str) -> None:
    """Remove *tmp_path* if it exists, ignoring any errors."""
    try:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    except Exception:
        pass
