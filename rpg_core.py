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
import struct
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

    Tries up to 9 999 numeric suffixes; falls back to a UUID suffix
    to guarantee uniqueness without an unbounded loop or timing race conditions.
    """
    if not os.path.exists(path):
        return path

    base, ext = os.path.splitext(path)
    for idx in range(1, 10_000):
        candidate = f"{base}_{idx}{ext}"
        if not os.path.exists(candidate):
            return candidate

    # Extreme fallback: use a short UUID to guarantee uniqueness.
    import uuid
    return f"{base}_{uuid.uuid4().hex[:8]}{ext}"



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


def decrypt_asset(input_path: str, output_path: str, key_bytes: bytes) -> tuple[bool, tuple[str, str]]:
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
        ``(True, ("", ""))`` on success.
        ``(False, (status_code, detail))`` on skip or failure.
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
                return False, (classification, "")

            # XOR the 16 encrypted bytes against the first 16 bytes of the key.
            header = bytes(a ^ b for a, b in zip(header_data[16:32], key_bytes[:16]))

            # Verify the decrypted header matches the expected file signature.
            sig_error = _verify_signature(output_path, header)
            if sig_error is not None:
                return False, (sig_error, "")

            # Write decrypted header + remaining file data to a temp file,
            # then atomically replace the destination.
            with open(tmp_path, "wb") as fout:
                fout.write(header)
                shutil.copyfileobj(fin, fout, length=COPY_BUFSIZE)

        os.replace(tmp_path, output_path)
        return True, ("", "")

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


def recover_key_from_png(filepath: str) -> str | None:
    """Recover the 32-character hex encryption key from an encrypted PNG file.

    The first 16 bytes of a decrypted PNG are always:
    \\x89PNG\\r\\n\\x1a\\n\\x00\\x00\\x00\\rIHDR
    We read bytes 16 to 32 from the encrypted file and XOR with this header.
    """
    try:
        if not os.path.isfile(filepath):
            return None
        with open(filepath, "rb") as f:
            header = f.read(32)
        if len(header) < 32 or not header.startswith(RPGMV_HEADER_MAGIC):
            return None
        png_header = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        key_bytes = bytes(a ^ b for a, b in zip(header[16:32], png_header))
        return key_bytes.hex()
    except Exception:
        return None


def restore_png_no_key(input_path: str, output_path: str) -> tuple[bool, tuple[str, str]]:
    """Restore an encrypted RPG Maker PNG file without knowing the encryption key.

    It simply replaces the 16 encrypted bytes with the standard PNG/IHDR header.
    """
    tmp_path = output_path + ".tmp"
    try:
        with open(input_path, "rb") as fin:
            header = fin.read(32)
            if len(header) < 32 or not header.startswith(RPGMV_HEADER_MAGIC):
                return False, ("not_encrypted", "")
            png_header = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
            with open(tmp_path, "wb") as fout:
                fout.write(png_header)
                shutil.copyfileobj(fin, fout, length=COPY_BUFSIZE)
        os.replace(tmp_path, output_path)
        return True, ("", "")
    except OSError as e:
        _cleanup_tmp(tmp_path)
        return False, ("io_error", str(e))
    except Exception as e:
        _cleanup_tmp(tmp_path)
        return False, ("raw_error", str(e) or "unknown_error")


def encrypt_asset(input_path: str, output_path: str, key_bytes: bytes) -> tuple[bool, tuple[str, str]]:
    """Encrypt a plain media file (PNG, OGG, M4A) to an RPG Maker encrypted asset.

    Algorithm:
        1. Prepend the 16-byte RPGMV header magic.
        2. XOR the first 16 bytes of the input file with key_bytes.
        3. Append the remaining file content unchanged.
    """
    if len(key_bytes) < 16:
        return False, ("raw_error", "key_too_short")
    tmp_path = output_path + ".tmp"
    try:
        with open(input_path, "rb") as fin:
            header_data = fin.read(16)
            if len(header_data) < 16:
                return False, ("too_small", "")
            
            # The standard RPG Maker MV/MZ 16-byte header
            rpgmv_header = b"RPGMV\x00\x00\x00\x00\x03\x00\x00\x00\x00\x00\x00\x00"
            encrypted_header = bytes(a ^ b for a, b in zip(header_data, key_bytes[:16]))
            with open(tmp_path, "wb") as fout:
                fout.write(rpgmv_header)
                fout.write(encrypted_header)
                shutil.copyfileobj(fin, fout, length=COPY_BUFSIZE)
        os.replace(tmp_path, output_path)
        return True, ("", "")
    except OSError as e:
        _cleanup_tmp(tmp_path)
        return False, ("io_error", str(e))
    except Exception as e:
        _cleanup_tmp(tmp_path)
        return False, ("raw_error", str(e) or "unknown_error")


# ---------------------------------------------------------------------------
# RGSS Archive Extraction (XP/VX/VX Ace)
# ---------------------------------------------------------------------------

def _advance_magic(magic: int) -> tuple[int, int]:
    old = magic
    magic = (magic * 7 + 3) & 0xFFFFFFFF
    return old, magic

def _ru32(stream) -> int | None:
    data = stream.read(4)
    if len(data) < 4:
        return None
    return struct.unpack('<I', data)[0]

def _read_until_full(stream, size) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = stream.read(size - len(data))
        if not chunk:
            break
        data.extend(chunk)
    return bytes(data)

class RGSSEntryData:
    def __init__(self, offset=0, magic=0, size=0):
        self.offset = offset
        self.magic = magic
        self.size = size

class RGSSCoder:
    def __init__(self):
        self.buf = bytearray(COPY_BUFSIZE)

    def copy(self, stream_in, stream_out, data, cancel_event=None):
        stream_in.seek(data.offset)
        magic = data.magic
        remaining = data.size

        while remaining > 0:
            if cancel_event and cancel_event.is_set():
                break
            chunk_size = min(len(self.buf), remaining)
            chunk = bytearray(_read_until_full(stream_in, chunk_size))
            if not chunk:
                break

            # Process aligned u32 chunks
            aligned_size = (len(chunk) // 4) * 4
            for i in range(0, aligned_size, 4):
                old_magic, magic = _advance_magic(magic)
                val = struct.unpack('<I', chunk[i:i+4])[0]
                val ^= old_magic
                chunk[i:i+4] = struct.pack('<I', val)

            # Process remaining bytes
            for i in range(aligned_size, len(chunk)):
                chunk[i] ^= (magic >> ((i % 4) * 8)) & 0xFF

            stream_out.write(chunk)
            remaining -= len(chunk)

class RGSSEntry:
    def __init__(self, name: str, data: RGSSEntryData):
        self.name = name
        self.data = data

class RGSSArchive:
    def __init__(self, magic: int, version: int, entries: list[RGSSEntry], stream):
        self.magic = magic
        self.version = version
        self.entries = entries
        self.stream = stream

    def close(self):
        if self.stream and not self.stream.closed:
            self.stream.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @classmethod
    def open(cls, location: str):
        stream = open(location, 'rb')
        try:
            header = stream.read(8)
            if header[:6] != b'RGSSAD':
                raise ValueError("Input file header mismatch.")
            version = header[7]
            if version in (1, 2):
                return cls.open_rgssad(stream, version)
            elif version == 3:
                return cls.open_rgss3a(stream, version)
            else:
                raise ValueError("Not supported version (must be 1-3).")
        except Exception:
            stream.close()
            raise

    @classmethod
    def open_rgssad(cls, stream, version):
        magic = 0xDEADCAFE
        entries = []
        stream.seek(8)

        while True:
            name_len = _ru32(stream)
            if name_len is None:
                break
            name_len ^= _advance_magic(magic)[0]

            name = bytearray()
            for _ in range(name_len):
                b_data = stream.read(1)
                if not b_data:
                    break
                name_byte = b_data[0]
                name_byte ^= _advance_magic(magic)[0] & 0xFF
                name.append(name_byte)
            
            if len(name) < name_len:
                break
                
            name = name.replace(b'\\\\', b'/').replace(b'\\', b'/').decode('utf-8', 'ignore')
            size = _ru32(stream)
            if size is None:
                break
            size ^= _advance_magic(magic)[0]

            offset = stream.tell()
            stream.seek(size, 1)
            entries.append(RGSSEntry(name, RGSSEntryData(offset, magic, size)))

        stream.seek(0)
        return cls(magic, version, entries, stream)

    @classmethod
    def open_rgss3a(cls, stream, version):
        stream.seek(8)
        magic = _ru32(stream)
        if magic is None:
            raise ValueError("Magic number read failed.")
        magic = (magic * 9 + 3) & 0xFFFFFFFF
        entries = []

        while True:
            offset = _ru32(stream)
            if offset is None:
                break
            offset ^= magic
            
            if offset == 0:
                break

            size = _ru32(stream)
            if size is None:
                break
            size ^= magic
            
            start_magic = _ru32(stream)
            if start_magic is None:
                break
            start_magic ^= magic
            
            name_len = _ru32(stream)
            if name_len is None:
                break
            name_len ^= magic

            name = bytearray()
            for i in range(name_len):
                b_data = stream.read(1)
                if not b_data:
                    break
                name_byte = b_data[0]
                name_byte ^= (magic >> ((i % 4) * 8)) & 0xFF
                name.append(name_byte)
            
            if len(name) < name_len:
                break
                
            name = name.replace(b'\\\\', b'/').replace(b'\\', b'/').decode('utf-8', 'ignore')
            entries.append(RGSSEntry(name, RGSSEntryData(offset, start_magic, size)))

        stream.seek(0)
        return cls(magic, version, entries, stream)

