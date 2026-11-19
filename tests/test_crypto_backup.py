from __future__ import annotations

import json

import pytest
from cryptography.exceptions import InvalidTag

from otpmanager.crypto import (
    decrypt_backup_payload,
    decrypt_secret,
    encrypt_backup_payload,
    encrypt_secret,
    generate_dek,
    hash_pin,
    verify_pin,
)


def test_aes_gcm_roundtrip_and_aad():
    dek = generate_dek()
    ct, nonce, tag = encrypt_secret(dek, b"hello-secret", b"aad-1")
    assert decrypt_secret(dek, ct, nonce, tag, b"aad-1") == b"hello-secret"
    with pytest.raises(InvalidTag):
        decrypt_secret(dek, ct, nonce, tag, b"aad-2")


def test_pin_hash():
    digest, salt, iters = hash_pin("123456")
    assert verify_pin("123456", digest, salt, iters)
    assert not verify_pin("000000", digest, salt, iters)


def test_backup_encrypt_decrypt():
    payload = json.dumps({"version": 1, "entries": []}).encode("utf-8")
    blob = encrypt_backup_payload("password123", payload, b"otp-backup-v1")
    assert blob["format"] == "otp-backup-v1"
    out = decrypt_backup_payload("password123", blob)
    assert out == payload
    with pytest.raises(InvalidTag):
        decrypt_backup_payload("wrong-password", blob)