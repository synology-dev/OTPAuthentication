"""otpauth URI parse/serialize."""

from __future__ import annotations

import base64
import re
import urllib.parse
from dataclasses import dataclass
from typing import List, Optional

from . import constants as C


_BASE32_RE = re.compile(r"^[A-Z2-7]+=*$")


@dataclass
class OtpAccount:
    issuer: str
    account: str
    secret: str
    algorithm: str = C.DEFAULT_ALGO
    digits: int = C.DEFAULT_DIGITS
    period: int = C.DEFAULT_PERIOD
    label: str = ""

    def normalized_secret(self) -> str:
        return re.sub(r"\s+", "", self.secret).upper()


def decode_secret(secret: str) -> bytes:
    cleaned = re.sub(r"\s+", "", secret).upper()
    if not cleaned or not _BASE32_RE.match(cleaned):
        raise ValueError("invalid base32 secret")
    pad = (-len(cleaned)) % 8
    cleaned += "=" * pad
    return base64.b32decode(cleaned, casefold=True)


def parse_otpauth_uri(uri: str) -> OtpAccount:
    uri = uri.strip()
    if not uri.lower().startswith("otpauth://totp/"):
        raise ValueError("only otpauth://totp/ URIs are supported")
    parsed = urllib.parse.urlparse(uri)
    label = urllib.parse.unquote(parsed.path.lstrip("/"))
    qs = urllib.parse.parse_qs(parsed.query, keep_blank_values=False)
    if "secret" not in qs or not qs["secret"][0]:
        raise ValueError("missing secret")
    secret = qs["secret"][0]
    decode_secret(secret)
    issuer_q = qs.get("issuer", [""])[0]
    algorithm = qs.get("algorithm", [C.DEFAULT_ALGO])[0].upper().replace("SHA-", "SHA")
    if algorithm not in C.ALLOWED_ALGOS:
        raise ValueError("unsupported algorithm")
    digits = int(qs.get("digits", [str(C.DEFAULT_DIGITS)])[0])
    if digits not in C.ALLOWED_DIGITS:
        raise ValueError("unsupported digits")
    period = int(qs.get("period", [str(C.DEFAULT_PERIOD)])[0])
    if period < C.PERIOD_MIN or period > C.PERIOD_MAX:
        raise ValueError("unsupported period")
    issuer, account = _split_label(label, issuer_q)
    return OtpAccount(
        issuer=issuer,
        account=account,
        secret=re.sub(r"\s+", "", secret).upper(),
        algorithm=algorithm,
        digits=digits,
        period=period,
        label=label,
    )


def serialize_otpauth(account: OtpAccount) -> str:
    label = account.label or (
        f"{account.issuer}:{account.account}" if account.issuer else account.account
    )
    params = {
        "secret": account.normalized_secret(),
        "issuer": account.issuer,
    }
    if account.algorithm != C.DEFAULT_ALGO:
        params["algorithm"] = account.algorithm
    if account.digits != C.DEFAULT_DIGITS:
        params["digits"] = str(account.digits)
    if account.period != C.DEFAULT_PERIOD:
        params["period"] = str(account.period)
    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return f"otpauth://totp/{urllib.parse.quote(label, safe='')}?{query}"


def parse_otpauth_lines(text: str) -> List[OtpAccount]:
    accounts: List[OtpAccount] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            accounts.append(parse_otpauth_uri(line))
        except ValueError as exc:
            raise ValueError(f"line {idx}: {exc}") from exc
    return accounts


def _split_label(label: str, issuer_q: str) -> tuple:
    issuer = issuer_q
    account = label
    if ":" in label:
        left, right = label.split(":", 1)
        if not issuer:
            issuer = left
        account = right
    if not account:
        raise ValueError("missing account")
    if not issuer:
        issuer = account
    return issuer, account