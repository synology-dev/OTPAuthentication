"""DSM authentication helpers."""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

from . import constants as C


@dataclass
class DsmIdentity:
    username: str
    dsm_uid: str
    sid: str = ""


class AuthError(Exception):
    pass


def authenticate_request(environ: dict) -> DsmIdentity:
    if os.environ.get(C.ENV_SKIP_DSM_AUTH) == "1":
        user = environ.get("HTTP_X_OTPM_DEV_USER") or os.environ.get(C.ENV_DEV_USER) or "dev"
        return DsmIdentity(username=user, dsm_uid=f"dev:{user}", sid=f"dev:{user}")

    cgi = "/usr/syno/synoman/webman/modules/authenticate.cgi"
    if not os.path.exists(cgi):
        raise AuthError("DSM authenticate helper missing")

    env = os.environ.copy()
    for key in (
        "HTTP_COOKIE",
        "HTTP_X_SYNO_TOKEN",
        "REMOTE_ADDR",
        "SERVER_ADDR",
        "SERVER_NAME",
        "SERVER_PORT",
        "REQUEST_METHOD",
        "QUERY_STRING",
        "HTTPS",
    ):
        if key in environ and environ[key] is not None:
            env[key] = str(environ[key])
    # Common CGI mapping
    if "HTTP_COOKIE" not in env and "COOKIE" in environ:
        env["HTTP_COOKIE"] = str(environ["COOKIE"])

    try:
        proc = subprocess.run(
            [cgi],
            env=env,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AuthError("authentication unavailable") from exc

    username = (proc.stdout or "").strip()
    if proc.returncode != 0 or not username or username.lower() in {"error", "permission denied"}:
        raise AuthError("not authenticated")

    # Prefer numeric uid if available for continuity detection.
    dsm_uid = _lookup_uid(username) or f"name:{username}"
    sid = _cookie_value(env.get("HTTP_COOKIE", ""), "id") or ""
    return DsmIdentity(username=username, dsm_uid=dsm_uid, sid=sid)


def _lookup_uid(username: str) -> Optional[str]:
    try:
        import pwd

        return str(pwd.getpwnam(username).pw_uid)
    except Exception:
        pass
    synouser = "/usr/syno/sbin/synouser"
    if os.path.exists(synouser):
        try:
            proc = subprocess.run(
                [synouser, "--get", username],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            for line in (proc.stdout or "").splitlines():
                if line.lower().startswith("uid"):
                    parts = line.split(":", 1)
                    if len(parts) == 2 and parts[1].strip().isdigit():
                        return parts[1].strip()
        except (OSError, subprocess.TimeoutExpired):
            return None
    return None


def _cookie_value(cookie_header: str, name: str) -> Optional[str]:
    for part in cookie_header.split(";"):
        part = part.strip()
        if part.startswith(name + "="):
            return part.split("=", 1)[1]
    return None


def resolve_local_username(username: str) -> bool:
    """Return True if username exists as a local account."""
    username = username.strip()
    if not username:
        return False
    # Lab/tests: synthetic DSM users (dev:name) are always resolvable by name.
    if os.environ.get(C.ENV_SKIP_DSM_AUTH) == "1":
        return True
    try:
        import pwd

        pwd.getpwnam(username)
        return True
    except Exception:
        pass
    synouser = "/usr/syno/sbin/synouser"
    if os.path.exists(synouser):
        try:
            proc = subprocess.run(
                [synouser, "--get", username],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            return proc.returncode == 0 and bool((proc.stdout or "").strip())
        except (OSError, subprocess.TimeoutExpired):
            return False
    return False


def lookup_dsm_uid(username: str) -> str:
    """Stable vault key for a local DSM username."""
    username = username.strip()
    if os.environ.get(C.ENV_SKIP_DSM_AUTH) == "1":
        return f"dev:{username}"
    return _lookup_uid(username) or f"name:{username}"


def list_local_usernames(query: str = "", limit: int = 30) -> list:
    """Local DSM usernames for share type-ahead (best-effort)."""
    query = (query or "").strip().lower()
    limit = max(1, min(int(limit or 30), 100))
    names: list = []

    if os.environ.get(C.ENV_SKIP_DSM_AUTH) == "1":
        return []

    synouser = "/usr/syno/sbin/synouser"
    if os.path.exists(synouser):
        try:
            proc = subprocess.run(
                [synouser, "--enum", "local"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            raw = (proc.stdout or "").strip()
            if proc.returncode == 0 and raw:
                # Output is typically space-separated usernames on one line.
                for part in raw.replace(",", " ").split():
                    name = part.strip()
                    if name and name not in names:
                        names.append(name)
        except (OSError, subprocess.TimeoutExpired):
            pass

    if not names:
        try:
            import pwd

            for ent in pwd.getpwall():
                if ent.pw_uid < 1000 or ent.pw_name in {"nobody", "nfsnobody"}:
                    continue
                if ent.pw_name not in names:
                    names.append(ent.pw_name)
        except Exception:
            pass

    if query:
        names = [n for n in names if query in n.lower()]
    names.sort(key=lambda n: n.lower())
    return names[:limit]


def verify_dsm_password(environ: dict, password: str) -> bool:
    """Confirm password for the currently authenticated DSM session.

    Uses SYNO.Core.User.PasswordConfirm against the local DSM webAPI, forwarding
    the caller's Cookie / SynoToken. In skip-auth (dev/test) mode, accepts any
    non-empty password unless OTPAUTHENTICATION_DEV_PASSWORD is set.
    """
    if not isinstance(password, str) or not password:
        return False

    if os.environ.get(C.ENV_SKIP_DSM_AUTH) == "1":
        expected = os.environ.get(C.ENV_DEV_PASSWORD)
        if expected is not None:
            return password == expected
        return True

    cookie = environ.get("HTTP_COOKIE") or environ.get("COOKIE") or ""
    syno_token = environ.get("HTTP_X_SYNO_TOKEN") or ""
    sid = _cookie_value(cookie, "id") or ""

    body = urllib.parse.urlencode(
        {
            "api": "SYNO.Core.User.PasswordConfirm",
            "version": "2",
            "method": "auth",
            "password": password,
            **({"_sid": sid} if sid else {}),
        }
    ).encode("utf-8")

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Content-Length": str(len(body)),
    }
    if cookie:
        headers["Cookie"] = cookie
    if syno_token:
        headers["X-SYNO-TOKEN"] = syno_token

    for url in (
        "http://127.0.0.1:5000/webapi/entry.cgi",
        "https://127.0.0.1:5001/webapi/entry.cgi",
    ):
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            # Local DSM may use a self-signed cert on 5001.
            open_kwargs = {"timeout": 8}
            if url.startswith("https://"):
                import ssl

                open_kwargs["context"] = ssl._create_unverified_context()
            with urllib.request.urlopen(req, **open_kwargs) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if payload.get("success") is True:
                return True
            # Explicit auth failure — do not fall through to the next URL.
            if isinstance(payload.get("error"), dict):
                return False
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
            continue
    return False