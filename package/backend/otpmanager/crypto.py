"""AES-256-GCM and KDF helpers using the cryptography package."""

from __future__ import annotations

import os
from typing import Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from . import constants as C


def generate_dek() -> bytes:
    return os.urandom(C.DEK_BYTES)


def encrypt_secret(dek: bytes, plaintext: bytes, aad: bytes) -> Tuple[bytes, bytes, bytes]:
    nonce = os.urandom(C.GCM_NONCE_BYTES)
    aesgcm = AESGCM(dek)
    raw = aesgcm.encrypt(nonce, plaintext, aad)
    ciphertext, tag = raw[: -C.GCM_TAG_BYTES], raw[-C.GCM_TAG_BYTES :]
    return ciphertext, nonce, tag


def decrypt_secret(dek: bytes, ciphertext: bytes, nonce: bytes, tag: bytes, aad: bytes) -> bytes:
    aesgcm = AESGCM(dek)
    return aesgcm.decrypt(nonce, ciphertext + tag, aad)


def pbkdf2(password: bytes, salt: bytes, iterations: int, length: int = 32) -> bytes:
    kdf = PBKDF2HMAC(algorithm=SHA256(), length=length, salt=salt, iterations=iterations)
    return kdf.derive(password)


def hash_pin(pin: str, salt: bytes | None = None, iterations: int = C.PIN_PBKDF2_ITERS) -> Tuple[bytes, bytes, int]:
    if salt is None:
        salt = os.urandom(C.PIN_SALT_BYTES)
    digest = pbkdf2(pin.encode("utf-8"), salt, iterations)
    return digest, salt, iterations


def verify_pin(pin: str, digest: bytes, salt: bytes, iterations: int) -> bool:
    candidate = pbkdf2(pin.encode("utf-8"), salt, iterations)
    if len(candidate) != len(digest):
        return False
    result = 0
    for a, b in zip(candidate, digest):
        result |= a ^ b
    return result == 0


def encrypt_backup_payload(password: str, plaintext: bytes, aad: bytes) -> dict:
    salt = os.urandom(C.BACKUP_SALT_BYTES)
    nonce = os.urandom(C.BACKUP_NONCE_BYTES)
    key = pbkdf2(password.encode("utf-8"), salt, C.BACKUP_KDF_ITERS)
    aesgcm = AESGCM(key)
    raw = aesgcm.encrypt(nonce, plaintext, aad)
    ciphertext, tag = raw[: -C.BACKUP_TAG_BYTES], raw[-C.BACKUP_TAG_BYTES :]
    return {
        "format": C.BACKUP_FORMAT,
        "kdf": "pbkdf2-sha256",
        "iter": C.BACKUP_KDF_ITERS,
        "salt": _b64(salt),
        "nonce": _b64(nonce),
        "ciphertext": _b64(ciphertext),
        "tag": _b64(tag),
        "aad": _b64(aad),
    }


def decrypt_backup_payload(password: str, blob: dict) -> bytes:
    if blob.get("format") != C.BACKUP_FORMAT:
        raise ValueError("unsupported backup format")
    if blob.get("kdf") != "pbkdf2-sha256":
        raise ValueError("unsupported kdf")
    iterations = int(blob.get("iter", 0))
    if iterations < 100_000 or iterations > 2_000_000:
        raise ValueError("invalid kdf iterations")
    salt = _ub64(blob["salt"])
    nonce = _ub64(blob["nonce"])
    ciphertext = _ub64(blob["ciphertext"])
    tag = _ub64(blob["tag"])
    aad = _ub64(blob.get("aad", "")) if blob.get("aad") else b"otp-backup-v1"
    if len(salt) < C.BACKUP_SALT_BYTES or len(nonce) != C.BACKUP_NONCE_BYTES:
        raise ValueError("invalid backup parameters")
    key = pbkdf2(password.encode("utf-8"), salt, iterations)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext + tag, aad)


def _b64(data: bytes) -> str:
    import base64

    return base64.b64encode(data).decode("ascii")


def _ub64(data: str) -> bytes:
    import base64

    return base64.b64decode(data.encode("ascii"))