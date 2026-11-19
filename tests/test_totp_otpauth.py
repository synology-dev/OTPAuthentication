from __future__ import annotations

import base64

import pytest

from otpmanager.otpauth import parse_otpauth_uri, serialize_otpauth, parse_otpauth_lines
from otpmanager.totp import generate_totp


# RFC 6238 appendix B test vectors use a fixed seed; SHA1 secret is ASCII "12345678901234567890"
RFC_SECRET_SHA1 = b"12345678901234567890"


def test_rfc6238_sha1():
    # At 59 the code is 94287082 for 8 digits
    code, _, _ = generate_totp(RFC_SECRET_SHA1, digits=8, period=30, algorithm="SHA1", for_time=59)
    assert code == "94287082"


def test_parse_and_serialize_roundtrip():
    uri = "otpauth://totp/Example:user%40example.com?secret=JBSWY3DPEHPK3PXP&issuer=Example"
    acct = parse_otpauth_uri(uri)
    assert acct.issuer == "Example"
    assert acct.account == "user@example.com"
    out = serialize_otpauth(acct)
    again = parse_otpauth_uri(out)
    assert again.secret == acct.secret
    assert again.issuer == acct.issuer


def test_parse_lines_sample_format():
    text = """
otpauth://totp/EcoStruxure%20IT:demo%40example.com?secret=KNTGKT3HM42T4O2FIEVD4VJQH52D4ODG&issuer=EcoStruxure%20IT
otpauth://totp/megavn.net:admin?secret=SD2OT6MEZGEWJZEX&issuer=megavn.net
""".strip()
    accounts = parse_otpauth_lines(text)
    assert len(accounts) == 2
    assert accounts[0].issuer == "EcoStruxure IT"
    assert accounts[1].account == "admin"


def test_reject_hotp():
    with pytest.raises(ValueError):
        parse_otpauth_uri("otpauth://hotp/Example:user?secret=JBSWY3DPEHPK3PXP&counter=1")