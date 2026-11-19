"""TOTP implementation (RFC 6238)."""

from __future__ import annotations

import hashlib
import hmac
import struct
import time
from typing import Tuple


_HASHES = {
    "SHA1": hashlib.sha1,
    "SHA256": hashlib.sha256,
    "SHA512": hashlib.sha512,
}


def generate_totp(
    secret: bytes,
    digits: int = 6,
    period: int = 30,
    algorithm: str = "SHA1",
    for_time: float | None = None,
) -> Tuple[str, int, int]:
    if algorithm not in _HASHES:
        raise ValueError("unsupported algorithm")
    if digits not in (6, 8):
        raise ValueError("unsupported digits")
    if period < 15 or period > 300:
        raise ValueError("unsupported period")
    now = int(time.time() if for_time is None else for_time)
    counter = now // period
    remaining = period - (now % period)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(secret, msg, _HASHES[algorithm]).digest()
    offset = digest[-1] & 0x0F
    code_int = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    code = str(code_int % (10**digits)).zfill(digits)
    return code, remaining, now + remaining