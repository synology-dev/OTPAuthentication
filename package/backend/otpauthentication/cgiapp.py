"""CGI JSON dispatcher."""

from __future__ import annotations

import cgi
import json
import os
import sys
from typing import Any, Callable, Dict
from urllib.parse import parse_qs

from .service import AppError, OTPService


def _read_json() -> dict:
    length = int(os.environ.get("CONTENT_LENGTH") or 0)
    raw = sys.stdin.buffer.read(length) if length > 0 else b""
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise AppError("invalid_json", "Invalid JSON body") from exc


def _query() -> dict:
    return {k: v[0] for k, v in parse_qs(os.environ.get("QUERY_STRING", ""), keep_blank_values=False).items()}


def _origin_ok(environ: dict) -> bool:
    origin = environ.get("HTTP_ORIGIN") or ""
    if not origin:
        # Same-origin XHR from DSM UI often omits Origin on GET; state-changing methods must send it.
        return True
    host = environ.get("HTTP_HOST") or environ.get("SERVER_NAME") or ""
    if not host:
        return False
    # Allow same host over http/https
    return origin.rstrip("/") in {f"http://{host}", f"https://{host}"}


def handle(handler_name: str) -> None:
    environ = dict(os.environ)
    method = (environ.get("REQUEST_METHOD") or "GET").upper()
    try:
        if method == "OPTIONS":
            _respond(204, {"success": True})
            return
        if method not in {"GET", "POST"}:
            raise AppError("method_not_allowed", "Method not allowed", 405)
        if method == "POST" and not _origin_ok(environ):
            raise AppError("csrf", "Origin not allowed", 403)

        body = _read_json() if method == "POST" else {}
        query = _query()
        payload = {**query, **body}
        svc = OTPService(environ)
        result = dispatch(svc, handler_name, payload, method, environ)
        _respond(200, {"success": True, "data": result})
    except AppError as exc:
        # DSM web server replaces CGI HTTP 500 bodies with an HTML error page, so never emit 500.
        status = 400 if exc.http_status == 500 else exc.http_status
        _respond(status, {"success": False, "error": {"code": exc.code, "message": exc.message, **exc.extra}})
    except Exception:
        # Prefer JSON 400 over 500: UI can show error.message; 500 becomes opaque HTML in DSM.
        _respond(400, {"success": False, "error": {"code": "internal", "message": "Internal error"}})


def dispatch(svc: OTPService, name: str, payload: dict, method: str, environ: dict) -> Any:
    action = payload.get("method") or payload.get("action") or "status"
    unlock = (
        payload.get("unlock_token")
        or environ.get("HTTP_X_OTP_UNLOCK")
        or ""
    )
    csrf = payload.get("csrf_token") or environ.get("HTTP_X_OTP_CSRF") or ""

    if name == "pin":
        if action == "status":
            return svc.pin_status()
        _require_post(method)
        if action == "setup":
            return svc.setup_pin(payload.get("pin", ""), payload.get("confirm", ""))
        if action == "unlock":
            return svc.unlock(payload.get("pin", ""))
        if action == "lock":
            return svc.lock(unlock)
        if action == "change":
            _require_csrf(svc, unlock, csrf)
            return svc.change_pin(unlock, payload.get("current_pin", ""), payload.get("pin", ""), payload.get("confirm", ""))
        if action == "recover_verify":
            return svc.recover_verify(payload.get("password", ""))
        if action == "recover":
            return svc.recover_pin(payload.get("recovery_token", ""), payload.get("action", ""))
        if action == "open_nopin":
            return svc.open_nopin()
        raise AppError("unknown_method", "Unknown method")

    if name == "entries":
        if action == "list":
            return svc.list_entries(
                unlock,
                scope=payload.get("scope", "all"),
                query=payload.get("q", ""),
                offset=int(payload.get("offset", 0)),
                limit=int(payload.get("limit", 50)),
            )
        _require_post(method)
        _require_csrf(svc, unlock, csrf)
        if action == "create":
            return svc.create_entry(unlock, payload, request_id=payload.get("request_id", ""))
        if action == "update":
            return svc.update_entry(unlock, int(payload["id"]), payload, pin=payload.get("pin", ""))
        if action == "delete":
            ids = payload.get("ids")
            if ids is not None and ids != "":
                if isinstance(ids, str):
                    ids = [int(x) for x in ids.split(",") if x]
                else:
                    ids = [int(x) for x in ids]
                return svc.delete_entries(unlock, ids)
            return svc.delete_entry(unlock, int(payload["id"]))
        if action == "reveal":
            return svc.reveal_secret(unlock, int(payload["id"]), payload.get("pin", ""))
        raise AppError("unknown_method", "Unknown method")

    if name == "codes":
        ids = payload.get("ids") or []
        if isinstance(ids, str):
            ids = [int(x) for x in ids.split(",") if x]
        else:
            ids = [int(x) for x in ids]
        return svc.codes(unlock, ids)

    if name == "share":
        if action == "list":
            return svc.share_list(unlock, int(payload["entry_id"]))
        _require_post(method)
        _require_csrf(svc, unlock, csrf)
        if action == "add":
            return svc.share_add(unlock, int(payload["entry_id"]), payload.get("username", ""))
        if action == "remove":
            return svc.share_remove(unlock, int(payload["entry_id"]), int(payload["share_id"]))
        if action == "resolve-recipient":
            return svc.resolve_recipient(unlock, payload.get("username", ""))
        raise AppError("unknown_method", "Unknown method")

    if name == "backup":
        _require_post(method)
        _require_csrf(svc, unlock, csrf)
        if action == "export_plain":
            ids = payload.get("ids")
            return svc.export_plain(unlock, payload.get("dsm_password", ""), ids)
        if action == "export_enc":
            return svc.export_encrypted(
                unlock,
                payload.get("dsm_password", ""),
                payload.get("password", ""),
                payload.get("ids"),
            )
        if action == "preview":
            return svc.import_preview(unlock, payload.get("content", ""), payload.get("password", ""))
        if action == "confirm":
            return svc.import_confirm(
                unlock,
                payload.get("preview_token", ""),
                request_id=payload.get("request_id", ""),
                decisions=payload.get("decisions"),
            )
        raise AppError("unknown_method", "Unknown method")

    raise AppError("unknown_handler", "Unknown handler")


def _require_post(method: str) -> None:
    if method != "POST":
        raise AppError("method_not_allowed", "POST required", 405)


def _require_csrf(svc: OTPService, unlock: str, csrf: str) -> None:
    if not unlock or not csrf:
        raise AppError("csrf", "CSRF token required", 403)
    # Validate CSRF bound to unlock token via package_state
    import hashlib

    from .db import now

    identity = svc.identity()
    with svc.db.connect() as conn:
        user = svc._user_row(conn, identity)
        th = svc._token_hash(unlock)
        key = f"csrf:{user['id']}:{th.hex()}"
        row = conn.execute("SELECT value FROM package_state WHERE key=?", (key,)).fetchone()
        if not row or row["value"] != csrf:
            raise AppError("csrf", "CSRF token invalid", 403)


def _respond(status: int, payload: dict) -> None:
    reasons = {
        200: "OK",
        204: "No Content",
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        405: "Method Not Allowed",
        409: "Conflict",
        429: "Too Many Requests",
        500: "Internal Server Error",
        503: "Service Unavailable",
    }
    reason = reasons.get(status, "OK")
    body = b"" if status == 204 else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sys.stdout.write(f"Status: {status} {reason}\r\n")
    sys.stdout.write("Content-Type: application/json; charset=utf-8\r\n")
    sys.stdout.write("Cache-Control: no-store\r\n")
    sys.stdout.write("X-Content-Type-Options: nosniff\r\n")
    if status != 204:
        sys.stdout.write(f"Content-Length: {len(body)}\r\n")
    sys.stdout.write("\r\n")
    sys.stdout.flush()
    if body:
        sys.stdout.buffer.write(body)
        sys.stdout.buffer.flush()