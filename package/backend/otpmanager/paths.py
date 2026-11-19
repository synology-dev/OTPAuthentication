"""Filesystem locations for OTP Manager."""

from __future__ import annotations

import os
from pathlib import Path

from . import constants as C


def package_root() -> Path:
    # .../target/backend/otpmanager/paths.py -> target
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    override = os.environ.get(C.ENV_DATA_DIR)
    if override:
        return Path(override)
    # Preferred Synology location
    syno = Path("/var/packages") / C.PACKAGE_NAME / "var"
    if syno.parent.exists() or os.environ.get("SYNOPKG_PKGNAME"):
        return syno
    # Local/dev fallback
    return package_root() / "var"


def db_path() -> Path:
    return data_dir() / "otp.db"


def dek_path() -> Path:
    return data_dir() / "dek"


def enabled_flag() -> Path:
    return data_dir() / "enabled"


def ensure_data_dir() -> Path:
    path = data_dir()
    # 0770: package user owns data; DSM synoscgi runs *.cgi as `http` (group access).
    path.mkdir(parents=True, mode=0o770, exist_ok=True)
    try:
        os.chmod(path, 0o770)
    except OSError:
        pass
    return path