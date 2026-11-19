"""Application service layer."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple

from . import constants as C
from .auth import AuthError, DsmIdentity, authenticate_request, resolve_local_username, verify_dsm_password
from .crypto import (
    decrypt_backup_payload,
    decrypt_secret,
    encrypt_backup_payload,
    encrypt_secret,
    generate_dek,
    hash_pin,
    verify_pin,
)
from .db import Database, ensure_user, get_user_by_uid, get_user_by_username, now
from .otpauth import OtpAccount, decode_secret, parse_otpauth_lines, parse_otpauth_uri, serialize_otpauth
from .paths import db_path, dek_path, enabled_flag, ensure_data_dir
from .totp import generate_totp


class AppError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400, extra: Optional[dict] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.extra = extra or {}


class OTPService:
    def __init__(self, environ: Optional[dict] = None, dev_user: Optional[str] = None):
        self.environ = dict(environ or {})
        if dev_user:
            self.environ["HTTP_X_OTPM_DEV_USER"] = dev_user
            os.environ[C.ENV_DEV_USER] = dev_user
        ensure_data_dir()
        self.db = Database(str(db_path()))
        self.db.initialize()
        self._ensure_dek()

    def _ensure_dek(self) -> None:
        path = dek_path()
        db_exists = db_path().exists() and db_path().stat().st_size > 0
        if path.exists():
            try:
                os.chmod(path, 0o660)
            except OSError:
                pass
            return
        if db_exists:
            # Fail closed: DB without DEK
            with self.db.connect() as conn:
                count = conn.execute("SELECT COUNT(*) AS c FROM entries").fetchone()["c"]
            if count:
                raise AppError("missing_dek", "Encryption key missing for existing vault", 500)
        path.write_bytes(generate_dek())
        os.chmod(path, 0o660)

    def _dek(self) -> bytes:
        data = dek_path().read_bytes()
        if len(data) != C.DEK_BYTES:
            raise AppError("invalid_dek", "Encryption key is invalid", 500)
        return data

    def is_enabled(self) -> bool:
        return enabled_flag().exists()

    def set_enabled(self, enabled: bool) -> None:
        flag = enabled_flag()
        if enabled:
            flag.write_text("1\n", encoding="utf-8")
            os.chmod(flag, 0o660)
        elif flag.exists():
            flag.unlink()

    def identity(self) -> DsmIdentity:
        try:
            return authenticate_request(self.environ)
        except AuthError as exc:
            raise AppError("unauthorized", str(exc), 401) from exc

    def _require_enabled(self) -> None:
        if not self.is_enabled() and os.environ.get(C.ENV_SKIP_DSM_AUTH) != "1":
            raise AppError("package_stopped", "OTP Manager is stopped", 503)

    def _user_row(self, conn, identity: DsmIdentity):
        return ensure_user(conn, identity.dsm_uid, identity.username)

    def pin_status(self) -> dict:
        if not self.is_enabled():
            return {
                "enabled": False,
                "package_stopped": True,
                "pin_set": False,
                "pin_disabled": False,
                "cooldown_seconds": 0,
                "idle_timeout": C.UNLOCK_IDLE_SECONDS,
                "absolute_timeout": C.UNLOCK_ABSOLUTE_SECONDS,
                "app_version": C.APP_VERSION,
            }
        identity = self.identity()
        with self.db.connect() as conn:
            user = self._user_row(conn, identity)
            attempts = conn.execute(
                "SELECT failures, cooldown_until FROM pin_attempts WHERE user_id = ?",
                (user["id"],),
            ).fetchone()
            cooldown = 0
            if attempts and attempts["cooldown_until"] > now():
                cooldown = attempts["cooldown_until"] - now()
            return {
                "enabled": True,
                "package_stopped": False,
                "username": identity.username,
                "pin_set": bool(user["pin_hash"]),
                "pin_disabled": self._pin_disabled(conn, user["id"]),
                "cooldown_seconds": cooldown,
                "idle_timeout": C.UNLOCK_IDLE_SECONDS,
                "absolute_timeout": C.UNLOCK_ABSOLUTE_SECONDS,
                "app_version": C.APP_VERSION,
            }

    def setup_pin(self, pin: str, confirm: str) -> dict:
        self._require_enabled()
        pin = (pin or "").strip()
        confirm = (confirm or "").strip()
        identity = self.identity()
        # Empty PIN + confirm = disable PIN protection (keep OTP data).
        if not pin and not confirm:
            with self.db.txn() as conn:
                user = self._user_row(conn, identity)
                if user["pin_hash"]:
                    raise AppError("pin_exists", "PIN already configured")
                self._set_pin_disabled(conn, user["id"], True)
                return self._issue_session(conn, identity, user["id"])
        self._validate_pin(pin)
        if pin != confirm:
            raise AppError("pin_mismatch", "PIN confirmation does not match")
        with self.db.txn() as conn:
            user = self._user_row(conn, identity)
            if user["pin_hash"]:
                raise AppError("pin_exists", "PIN already configured")
            digest, salt, iters = hash_pin(pin)
            ts = now()
            conn.execute(
                "UPDATE users SET pin_hash=?, pin_salt=?, pin_iters=?, pin_set_at=?, updated_at=? WHERE id=?",
                (digest, salt, iters, ts, ts, user["id"]),
            )
            conn.execute(
                "INSERT OR REPLACE INTO pin_attempts(user_id, failures, cooldown_until, updated_at) VALUES (?,0,0,?)",
                (user["id"], ts),
            )
            self._set_pin_disabled(conn, user["id"], False)
        return {"ok": True}

    def unlock(self, pin: str, interactive: bool = True) -> dict:
        self._require_enabled()
        identity = self.identity()
        with self.db.connect() as conn:
            user = self._user_row(conn, identity)
            if not user["pin_hash"]:
                raise AppError("pin_required", "PIN is not configured")
            self._check_cooldown(conn, user["id"])
            if not verify_pin(pin, user["pin_hash"], user["pin_salt"], user["pin_iters"]):
                self._register_failure(conn, user["id"])
                raise AppError("invalid_pin", "Incorrect PIN")
        with self.db.txn() as conn:
            user = self._user_row(conn, identity)
            conn.execute(
                "INSERT OR REPLACE INTO pin_attempts(user_id, failures, cooldown_until, updated_at) VALUES (?,0,0,?)",
                (user["id"], now()),
            )
            return self._issue_session(conn, identity, user["id"])

    def lock(self, unlock_token: str) -> dict:
        identity = self.identity()
        with self.db.txn() as conn:
            user = self._user_row(conn, identity)
            th = self._token_hash(unlock_token)
            conn.execute(
                "UPDATE sessions SET revoked_at=? WHERE user_id=? AND token_hash=? AND revoked_at IS NULL",
                (now(), user["id"], th),
            )
            conn.execute(
                "DELETE FROM package_state WHERE key = ?",
                (f"csrf:{user['id']}:{th.hex()}",),
            )
            self._cleanup_previews(conn, user["id"])
        return {"ok": True}

    def change_pin(self, unlock_token: str, current_pin: str, new_pin: str, confirm: str) -> dict:
        self._require_enabled()
        new_pin = (new_pin or "").strip()
        confirm = (confirm or "").strip()
        identity = self.identity()
        # Empty new PIN + confirm = disable PIN (same as Remove PIN / pin_disabled).
        if not new_pin and not confirm:
            with self.db.txn() as conn:
                user = self._session_user(conn, identity, unlock_token, interactive=True)
                if not user["pin_hash"] or not verify_pin(
                    current_pin, user["pin_hash"], user["pin_salt"], user["pin_iters"]
                ):
                    raise AppError("invalid_pin", "Current PIN is incorrect")
                self._clear_user_pin(conn, user["id"])
                self._set_pin_disabled(conn, user["id"], True)
                return self._issue_session(conn, identity, user["id"])
        self._validate_pin(new_pin)
        if new_pin != confirm:
            raise AppError("pin_mismatch", "PIN confirmation does not match")
        with self.db.txn() as conn:
            user = self._session_user(conn, identity, unlock_token, interactive=True)
            if not verify_pin(current_pin, user["pin_hash"], user["pin_salt"], user["pin_iters"]):
                raise AppError("invalid_pin", "Current PIN is incorrect")
            digest, salt, iters = hash_pin(new_pin)
            ts = now()
            conn.execute(
                "UPDATE users SET pin_hash=?, pin_salt=?, pin_iters=?, pin_set_at=?, updated_at=? WHERE id=?",
                (digest, salt, iters, ts, ts, user["id"]),
            )
            conn.execute(
                "UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
                (ts, user["id"]),
            )
            self._set_pin_disabled(conn, user["id"], False)
        return {"ok": True}

    def recover_verify(self, password: str) -> dict:
        """Confirm DSM password and issue a short-lived recovery token."""
        self._require_enabled()
        identity = self.identity()
        with self.db.connect() as conn:
            user = self._user_row(conn, identity)
            if not user["pin_hash"]:
                raise AppError("pin_required", "PIN is not configured")
            self._check_cooldown(conn, user["id"])
        if not verify_dsm_password(self.environ, password):
            with self.db.connect() as conn:
                user = self._user_row(conn, identity)
                self._register_failure(conn, user["id"])
            raise AppError("invalid_password", "Incorrect DSM password")
        with self.db.txn() as conn:
            user = self._user_row(conn, identity)
            conn.execute(
                "INSERT OR REPLACE INTO pin_attempts(user_id, failures, cooldown_until, updated_at) VALUES (?,0,0,?)",
                (user["id"], now()),
            )
            token = secrets.token_urlsafe(C.RECOVERY_TOKEN_BYTES)
            token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
            ts = now()
            conn.execute(
                "INSERT OR REPLACE INTO package_state(key, value) VALUES (?, ?)",
                (
                    f"recover:{user['id']}",
                    json.dumps({"hash": token_hash, "expires_at": ts + C.RECOVERY_TOKEN_TTL_SECONDS}),
                ),
            )
        return {"ok": True, "recovery_token": token, "username": identity.username}

    def recover_pin(self, recovery_token: str, action: str) -> dict:
        """Clear PIN after DSM password confirmation; keep OTP entries/shares.

        PIN only gates UI/API unlock sessions. Secrets remain under package DEK.

        action:
          - remove: clear PIN, mark pin_disabled, return unlock session (no PIN)
          - reset: clear PIN, require Setup PIN next
        """
        self._require_enabled()
        action = (action or "").strip().lower()
        if action not in {"remove", "reset"}:
            raise AppError("invalid_action", "Unknown recovery action")
        if not recovery_token:
            raise AppError("invalid_token", "Recovery token required", 401)
        identity = self.identity()
        with self.db.txn() as conn:
            user = self._user_row(conn, identity)
            self._consume_recovery_token(conn, user["id"], recovery_token)
            self._clear_user_pin(conn, user["id"])
            if action == "remove":
                self._set_pin_disabled(conn, user["id"], True)
                return self._issue_session(conn, identity, user["id"])
            self._set_pin_disabled(conn, user["id"], False)
        return {"ok": True, "need_setup": True, "pin_set": False}

    def open_nopin(self) -> dict:
        """Open a vault session when PIN protection was explicitly removed."""
        self._require_enabled()
        identity = self.identity()
        with self.db.txn() as conn:
            user = self._user_row(conn, identity)
            if user["pin_hash"]:
                raise AppError("pin_exists", "PIN is configured — unlock with PIN")
            if not self._pin_disabled(conn, user["id"]):
                raise AppError("pin_required", "PIN setup required")
            return self._issue_session(conn, identity, user["id"])

    def list_entries(
        self,
        unlock_token: str,
        scope: str = "all",
        query: str = "",
        offset: int = 0,
        limit: int = 50,
    ) -> dict:
        identity = self.identity()
        limit = max(1, min(limit, C.LIST_PAGE_MAX))
        offset = max(0, offset)
        scope = (scope or "all").strip().lower()
        with self.db.connect() as conn:
            user = self._session_user(conn, identity, unlock_token, interactive=False)
            q = f"%{query.strip().lower()}%" if query.strip() else None
            if scope == "shared":
                sql = """
                  SELECT e.*, u.username AS owner_name, 1 AS is_shared, 0 AS share_count
                  FROM entries e
                  JOIN shares s ON s.entry_id = e.id
                  JOIN users u ON u.id = e.owner_id
                  WHERE s.grantee_id = ?
                """
                params: List[Any] = [user["id"]]
            elif scope == "owned":
                sql = """
                  SELECT e.*, ? AS owner_name, 0 AS is_shared,
                    (SELECT COUNT(*) FROM shares sh WHERE sh.entry_id = e.id) AS share_count
                  FROM entries e
                  WHERE e.owner_id = ?
                """
                params = [identity.username, user["id"]]
            else:
                # Combined owned + shared (default UI list).
                sql = """
                  SELECT e.*, ? AS owner_name, 0 AS is_shared,
                    (SELECT COUNT(*) FROM shares sh WHERE sh.entry_id = e.id) AS share_count
                  FROM entries e
                  WHERE e.owner_id = ?
                  UNION ALL
                  SELECT e.*, u.username AS owner_name, 1 AS is_shared, 0 AS share_count
                  FROM entries e
                  JOIN shares s ON s.entry_id = e.id
                  JOIN users u ON u.id = e.owner_id
                  WHERE s.grantee_id = ?
                """
                params = [identity.username, user["id"], user["id"]]
            if q:
                if scope in {"owned", "shared"}:
                    sql += " AND (lower(e.issuer) LIKE ? OR lower(e.account) LIKE ? OR lower(e.label) LIKE ?)"
                    params.extend([q, q, q])
                else:
                    sql = f"SELECT * FROM ({sql}) AS combined WHERE (lower(issuer) LIKE ? OR lower(account) LIKE ? OR lower(label) LIKE ?)"
                    params.extend([q, q, q])
            count_sql = f"SELECT COUNT(*) AS c FROM ({sql}) AS counted"
            total = int(conn.execute(count_sql, params).fetchone()["c"])
            if scope in {"owned", "shared"}:
                sql += " ORDER BY e.issuer COLLATE NOCASE, e.account COLLATE NOCASE LIMIT ? OFFSET ?"
            else:
                sql += " ORDER BY issuer COLLATE NOCASE, account COLLATE NOCASE LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            rows = conn.execute(sql, params).fetchall()
            items = [self._entry_public(row) for row in rows]
            return {"items": items, "offset": offset, "limit": limit, "total": total}

    def create_entry(self, unlock_token: str, payload: dict, request_id: str = "") -> dict:
        identity = self.identity()
        account = self._account_from_payload(payload)
        with self.db.txn() as conn:
            user = self._session_user(conn, identity, unlock_token, interactive=True)
            if request_id:
                key = f"idem:{user['id']}:{request_id}"
                existing = conn.execute("SELECT value FROM package_state WHERE key=?", (key,)).fetchone()
                if existing:
                    return json.loads(existing["value"])
            entry_id = self._insert_entry(conn, user["id"], account)
            result = {"id": entry_id}
            if request_id:
                conn.execute(
                    "INSERT OR REPLACE INTO package_state(key, value) VALUES (?, ?)",
                    (key, json.dumps(result)),
                )
            return result

    def update_entry(self, unlock_token: str, entry_id: int, payload: dict, pin: str = "") -> dict:
        identity = self.identity()
        with self.db.txn() as conn:
            user = self._session_user(conn, identity, unlock_token, interactive=True)
            row = conn.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
            if not row or row["owner_id"] != user["id"]:
                raise AppError("forbidden", "Not allowed", 403)
            if int(payload.get("revision", row["revision"])) != row["revision"]:
                raise AppError("conflict", "Entry was modified; reload and retry", 409)
            issuer = payload.get("issuer", row["issuer"]).strip()
            account = payload.get("account", row["account"]).strip()
            label = payload.get("label", row["label"])
            algorithm = payload.get("algorithm", row["algorithm"]).upper()
            digits = int(payload.get("digits", row["digits"]))
            period = int(payload.get("period", row["period"]))
            self._validate_params(algorithm, digits, period)
            secret_ct, secret_nonce, secret_tag = row["secret_ct"], row["secret_nonce"], row["secret_tag"]
            if payload.get("secret"):
                if not pin or not verify_pin(pin, user["pin_hash"], user["pin_salt"], user["pin_iters"]):
                    raise AppError("pin_required", "PIN required to change secret")
                secret = decode_secret(payload["secret"])
                aad = self._aad(entry_id, user["id"])
                secret_ct, secret_nonce, secret_tag = encrypt_secret(self._dek(), secret, aad)
            ts = now()
            conn.execute(
                """UPDATE entries SET issuer=?, account=?, label=?, algorithm=?, digits=?, period=?,
                   secret_ct=?, secret_nonce=?, secret_tag=?, revision=revision+1, updated_at=?
                   WHERE id=?""",
                (
                    issuer,
                    account,
                    label,
                    algorithm,
                    digits,
                    period,
                    secret_ct,
                    secret_nonce,
                    secret_tag,
                    ts,
                    entry_id,
                ),
            )
            return {"id": entry_id, "revision": row["revision"] + 1}

    def delete_entry(self, unlock_token: str, entry_id: int) -> dict:
        identity = self.identity()
        with self.db.txn() as conn:
            user = self._session_user(conn, identity, unlock_token, interactive=True)
            row = conn.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
            if not row or row["owner_id"] != user["id"]:
                raise AppError("forbidden", "Not allowed", 403)
            shares = conn.execute("SELECT COUNT(*) AS c FROM shares WHERE entry_id=?", (entry_id,)).fetchone()["c"]
            conn.execute("DELETE FROM entries WHERE id=?", (entry_id,))
            return {"deleted": True, "shares_removed": shares}

    def reveal_secret(self, unlock_token: str, entry_id: int, pin: str) -> dict:
        identity = self.identity()
        with self.db.connect() as conn:
            user = self._session_user(conn, identity, unlock_token, interactive=True)
            if not verify_pin(pin, user["pin_hash"], user["pin_salt"], user["pin_iters"]):
                raise AppError("invalid_pin", "Incorrect PIN")
            row = conn.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
            if not row or row["owner_id"] != user["id"]:
                raise AppError("forbidden", "Not allowed", 403)
            secret = decrypt_secret(
                self._dek(),
                row["secret_ct"],
                row["secret_nonce"],
                row["secret_tag"],
                self._aad(row["id"], row["owner_id"]),
            )
            import base64

            return {"secret": base64.b32encode(secret).decode("ascii").rstrip("=")}

    def codes(self, unlock_token: str, entry_ids: List[int]) -> dict:
        if len(entry_ids) > C.BATCH_CODES_MAX:
            raise AppError("too_many", "Too many entries")
        identity = self.identity()
        with self.db.connect() as conn:
            user = self._session_user(conn, identity, unlock_token, interactive=False)
            items = []
            for entry_id in entry_ids:
                row = conn.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
                if not row or not self._can_view(conn, user["id"], row):
                    continue
                secret = decrypt_secret(
                    self._dek(),
                    row["secret_ct"],
                    row["secret_nonce"],
                    row["secret_tag"],
                    self._aad(row["id"], row["owner_id"]),
                )
                code, remaining, expires_at = generate_totp(
                    secret, digits=row["digits"], period=row["period"], algorithm=row["algorithm"]
                )
                items.append(
                    {
                        "id": row["id"],
                        "code": code,
                        "remaining": remaining,
                        "expires_at": expires_at,
                        "period": row["period"],
                    }
                )
            return {"server_time": now(), "items": items}

    def share_list(self, unlock_token: str, entry_id: int) -> dict:
        identity = self.identity()
        with self.db.connect() as conn:
            user = self._session_user(conn, identity, unlock_token, interactive=False)
            row = conn.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
            if not row or row["owner_id"] != user["id"]:
                raise AppError("forbidden", "Not allowed", 403)
            rows = conn.execute(
                """SELECT s.id, u.username, s.shared_at
                   FROM shares s JOIN users u ON u.id = s.grantee_id
                   WHERE s.entry_id=? ORDER BY u.username COLLATE NOCASE""",
                (entry_id,),
            ).fetchall()
            return {
                "items": [
                    {"id": r["id"], "username": r["username"], "permission": "view", "shared_at": r["shared_at"]}
                    for r in rows
                ]
            }

    def share_add(self, unlock_token: str, entry_id: int, username: str) -> dict:
        identity = self.identity()
        username = username.strip()
        if not username or username.lower() == identity.username.lower():
            raise AppError("invalid_recipient", "Invalid recipient")
        with self.db.txn() as conn:
            user = self._session_user(conn, identity, unlock_token, interactive=True)
            row = conn.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
            if not row or row["owner_id"] != user["id"]:
                raise AppError("forbidden", "Not allowed", 403)
            grantee = get_user_by_username(conn, username)
            if grantee is None or not grantee["pin_hash"]:
                # Recipient must have initialized OTP Manager
                if not resolve_local_username(username):
                    raise AppError("invalid_recipient", "User not found")
                raise AppError("recipient_not_ready", "User has not set up OTP Manager yet")
            try:
                conn.execute(
                    "INSERT INTO shares(entry_id, grantee_id, shared_at) VALUES (?, ?, ?)",
                    (entry_id, grantee["id"], now()),
                )
            except Exception as exc:
                raise AppError("already_shared", "Already shared with this user") from exc
            return {"ok": True}

    def share_remove(self, unlock_token: str, entry_id: int, share_id: int) -> dict:
        identity = self.identity()
        with self.db.txn() as conn:
            user = self._session_user(conn, identity, unlock_token, interactive=True)
            row = conn.execute("SELECT * FROM entries WHERE id=?", (entry_id,)).fetchone()
            if not row or row["owner_id"] != user["id"]:
                raise AppError("forbidden", "Not allowed", 403)
            cur = conn.execute(
                "DELETE FROM shares WHERE id=? AND entry_id=?",
                (share_id, entry_id),
            )
            if cur.rowcount == 0:
                raise AppError("not_found", "Share not found", 404)
            return {"ok": True}

    def resolve_recipient(self, unlock_token: str, username: str) -> dict:
        identity = self.identity()
        username = username.strip()
        with self.db.connect() as conn:
            self._session_user(conn, identity, unlock_token, interactive=True)
            if not username or username.lower() == identity.username.lower():
                raise AppError("invalid_recipient", "Invalid recipient")
            if not resolve_local_username(username):
                raise AppError("invalid_recipient", "User not found")
            grantee = get_user_by_username(conn, username)
            return {
                "username": username,
                "ready": bool(grantee and grantee["pin_hash"]),
                "permission": "view",
            }

    def export_plain(self, unlock_token: str, dsm_password: str, entry_ids: Optional[List[int]] = None) -> dict:
        accounts = self._owned_accounts_for_export(unlock_token, dsm_password, entry_ids)
        text = "\n".join(serialize_otpauth(a) for a in accounts) + ("\n" if accounts else "")
        return {"content": text, "count": len(accounts)}

    def export_encrypted(
        self, unlock_token: str, dsm_password: str, password: str, entry_ids: Optional[List[int]] = None
    ) -> dict:
        if not password:
            raise AppError("password_required", "Encryption password is required")
        accounts = self._owned_accounts_for_export(unlock_token, dsm_password, entry_ids)
        payload = {
            "version": 1,
            "entries": [
                {
                    "issuer": a.issuer,
                    "account": a.account,
                    "label": a.label,
                    "secret": a.normalized_secret(),
                    "algorithm": a.algorithm,
                    "digits": a.digits,
                    "period": a.period,
                }
                for a in accounts
            ],
        }
        plaintext = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        aad = b"otp-backup-v1"
        blob = encrypt_backup_payload(password, plaintext, aad)
        blob["count"] = len(accounts)
        return blob

    def import_preview(self, unlock_token: str, content: str, password: str = "") -> dict:
        if len(content.encode("utf-8")) > C.BACKUP_MAX_BYTES:
            raise AppError("too_large", "Backup too large")
        accounts = self._parse_import_content(content, password)
        if len(accounts) > C.BACKUP_MAX_ENTRIES:
            raise AppError("too_many", "Too many entries")
        identity = self.identity()
        with self.db.txn() as conn:
            user = self._session_user(conn, identity, unlock_token, interactive=True)
            items = []
            for a in accounts:
                dup = self._is_duplicate(conn, user["id"], a)
                items.append(
                    {
                        "issuer": a.issuer,
                        "account": a.account,
                        "status": "duplicate" if dup else "new",
                    }
                )
            staging = json.dumps(
                [
                    {
                        "issuer": a.issuer,
                        "account": a.account,
                        "label": a.label,
                        "secret": a.normalized_secret(),
                        "algorithm": a.algorithm,
                        "digits": a.digits,
                        "period": a.period,
                    }
                    for a in accounts
                ],
                separators=(",", ":"),
            ).encode("utf-8")
            token = secrets.token_bytes(C.TOKEN_BYTES)
            token_hash = hashlib.sha256(token).digest()
            digest = hashlib.sha256(staging).hexdigest()
            aad = f"preview:{user['id']}".encode("utf-8")
            ct, nonce, tag = encrypt_secret(self._dek(), staging, aad)
            ts = now()
            conn.execute(
                """INSERT INTO import_previews(token_hash, user_id, payload_ct, payload_nonce, payload_tag, digest, created_at, expires_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (token_hash, user["id"], ct, nonce, tag, digest, ts, ts + C.PREVIEW_TTL_SECONDS),
            )
            return {"preview_token": token.hex(), "items": items, "count": len(items)}

    def import_confirm(
        self,
        unlock_token: str,
        preview_token: str,
        request_id: str = "",
        decisions: Optional[List[str]] = None,
    ) -> dict:
        identity = self.identity()
        with self.db.txn() as conn:
            user = self._session_user(conn, identity, unlock_token, interactive=True)
            if request_id:
                key = f"idem:{user['id']}:{request_id}"
                existing = conn.execute("SELECT value FROM package_state WHERE key=?", (key,)).fetchone()
                if existing:
                    return json.loads(existing["value"])
            th = self._token_hash(preview_token)
            row = conn.execute(
                "SELECT * FROM import_previews WHERE token_hash=? AND user_id=?",
                (th, user["id"]),
            ).fetchone()
            if not row or row["expires_at"] < now():
                raise AppError("preview_expired", "Import preview expired")
            aad = f"preview:{user['id']}".encode("utf-8")
            staging = decrypt_secret(self._dek(), row["payload_ct"], row["payload_nonce"], row["payload_tag"], aad)
            if hashlib.sha256(staging).hexdigest() != row["digest"]:
                raise AppError("preview_tampered", "Import preview invalid")
            payload = json.loads(staging.decode("utf-8"))
            if decisions is not None and len(decisions) != len(payload):
                raise AppError("invalid_decisions", "Import decisions length mismatch")
            added = skipped = overridden = 0
            for idx, item in enumerate(payload):
                account = OtpAccount(
                    issuer=item["issuer"],
                    account=item["account"],
                    label=item.get("label", ""),
                    secret=item["secret"],
                    algorithm=item["algorithm"],
                    digits=item["digits"],
                    period=item["period"],
                )
                existing_row = self._find_duplicate(conn, user["id"], account)
                decision = "skip" if decisions is None else str(decisions[idx] or "skip").lower()
                if existing_row is None:
                    if decision == "skip":
                        skipped += 1
                        continue
                    self._insert_entry(conn, user["id"], account)
                    added += 1
                    continue
                if decision == "override":
                    self._replace_entry(conn, user["id"], int(existing_row["id"]), account)
                    overridden += 1
                else:
                    skipped += 1
            conn.execute("DELETE FROM import_previews WHERE token_hash=?", (th,))
            result = {"added": added, "skipped": skipped, "overridden": overridden}
            if request_id:
                conn.execute(
                    "INSERT OR REPLACE INTO package_state(key, value) VALUES (?, ?)",
                    (key, json.dumps(result)),
                )
            return result

    # --- helpers ---

    def _validate_pin(self, pin: str) -> None:
        if not pin.isdigit() or not (C.PIN_MIN_LEN <= len(pin) <= C.PIN_MAX_LEN):
            raise AppError("invalid_pin_format", f"PIN must be {C.PIN_MIN_LEN}-{C.PIN_MAX_LEN} digits")

    def _token_hash(self, token_hex: str) -> bytes:
        try:
            raw = bytes.fromhex(token_hex)
        except ValueError as exc:
            raise AppError("invalid_token", "Invalid unlock token", 401) from exc
        if len(raw) != C.TOKEN_BYTES:
            raise AppError("invalid_token", "Invalid unlock token", 401)
        return hashlib.sha256(raw).digest()

    def _session_user(self, conn, identity: DsmIdentity, unlock_token: str, interactive: bool):
        self._require_enabled()
        user = self._user_row(conn, identity)
        th = self._token_hash(unlock_token)
        row = conn.execute(
            """SELECT * FROM sessions WHERE user_id=? AND token_hash=? AND revoked_at IS NULL""",
            (user["id"], th),
        ).fetchone()
        ts = now()
        if not row or row["absolute_expires_at"] < ts or row["idle_expires_at"] < ts:
            raise AppError("locked", "Vault is locked", 401)
        if identity.sid and row["dsm_sid"] and row["dsm_sid"] != identity.sid:
            raise AppError("locked", "DSM session changed", 401)
        if interactive:
            conn.execute(
                "UPDATE sessions SET last_seen_at=?, idle_expires_at=? WHERE id=?",
                (ts, ts + C.UNLOCK_IDLE_SECONDS, row["id"]),
            )
        return user

    def _issue_session(self, conn, identity: DsmIdentity, user_id: int) -> dict:
        token = secrets.token_bytes(C.TOKEN_BYTES)
        token_hash = hashlib.sha256(token).digest()
        ts = now()
        conn.execute(
            """INSERT INTO sessions(user_id, token_hash, dsm_sid, created_at, last_seen_at,
               absolute_expires_at, idle_expires_at, revoked_at)
               VALUES (?,?,?,?,?,?,?,NULL)""",
            (
                user_id,
                token_hash,
                identity.sid,
                ts,
                ts,
                ts + C.UNLOCK_ABSOLUTE_SECONDS,
                ts + C.UNLOCK_IDLE_SECONDS,
            ),
        )
        csrf = secrets.token_urlsafe(24)
        conn.execute(
            "INSERT OR REPLACE INTO package_state(key, value) VALUES (?, ?)",
            (f"csrf:{user_id}:{token_hash.hex()}", csrf),
        )
        return {
            "unlock_token": token.hex(),
            "csrf_token": csrf,
            "idle_timeout": C.UNLOCK_IDLE_SECONDS,
            "absolute_timeout": C.UNLOCK_ABSOLUTE_SECONDS,
        }

    def _pin_disabled_key(self, user_id: int) -> str:
        return f"pin_disabled:{user_id}"

    def _pin_disabled(self, conn, user_id: int) -> bool:
        row = conn.execute(
            "SELECT value FROM package_state WHERE key=?",
            (self._pin_disabled_key(user_id),),
        ).fetchone()
        return bool(row and row["value"] == "1")

    def _set_pin_disabled(self, conn, user_id: int, disabled: bool) -> None:
        key = self._pin_disabled_key(user_id)
        if disabled:
            conn.execute(
                "INSERT OR REPLACE INTO package_state(key, value) VALUES (?, ?)",
                (key, "1"),
            )
        else:
            conn.execute("DELETE FROM package_state WHERE key=?", (key,))

    def _consume_recovery_token(self, conn, user_id: int, recovery_token: str) -> None:
        key = f"recover:{user_id}"
        row = conn.execute("SELECT value FROM package_state WHERE key=?", (key,)).fetchone()
        conn.execute("DELETE FROM package_state WHERE key=?", (key,))
        if not row:
            raise AppError("invalid_token", "Recovery token invalid or expired", 401)
        try:
            meta = json.loads(row["value"])
        except (TypeError, ValueError) as exc:
            raise AppError("invalid_token", "Recovery token invalid or expired", 401) from exc
        if int(meta.get("expires_at") or 0) < now():
            raise AppError("invalid_token", "Recovery token invalid or expired", 401)
        expected = meta.get("hash") or ""
        got = hashlib.sha256(recovery_token.encode("utf-8")).hexdigest()
        if not expected or not secrets.compare_digest(expected, got):
            raise AppError("invalid_token", "Recovery token invalid or expired", 401)

    def _clear_user_pin(self, conn, user_id: int) -> None:
        """Clear PIN and revoke unlock sessions; keep entries/shares intact."""
        ts = now()
        conn.execute(
            "UPDATE sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
            (ts, user_id),
        )
        conn.execute("DELETE FROM import_previews WHERE user_id=?", (user_id,))
        conn.execute(
            "DELETE FROM package_state WHERE key LIKE ?",
            (f"csrf:{user_id}:%",),
        )
        conn.execute(
            "UPDATE users SET pin_hash=NULL, pin_salt=NULL, pin_iters=NULL, pin_set_at=NULL, updated_at=? WHERE id=?",
            (ts, user_id),
        )
        conn.execute(
            "INSERT OR REPLACE INTO pin_attempts(user_id, failures, cooldown_until, updated_at) VALUES (?,0,0,?)",
            (user_id, ts),
        )

    def _check_cooldown(self, conn, user_id: int) -> None:
        row = conn.execute("SELECT * FROM pin_attempts WHERE user_id=?", (user_id,)).fetchone()
        if row and row["cooldown_until"] > now():
            raise AppError(
                "cooldown",
                "Too many attempts; try later",
                429,
                {"cooldown_seconds": row["cooldown_until"] - now()},
            )

    def _register_failure(self, conn, user_id: int) -> None:
        ts = now()
        row = conn.execute("SELECT * FROM pin_attempts WHERE user_id=?", (user_id,)).fetchone()
        failures = (row["failures"] if row else 0) + 1
        cooldown = ts + C.PIN_COOLDOWN_SECONDS if failures >= C.PIN_MAX_FAILURES else 0
        if failures >= C.PIN_MAX_FAILURES:
            failures = 0
        # Persist immediately (caller may raise afterwards).
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT OR REPLACE INTO pin_attempts(user_id, failures, cooldown_until, updated_at) VALUES (?,?,?,?)",
            (user_id, failures, cooldown, ts),
        )
        conn.execute("COMMIT")

    def _aad(self, entry_id: int, owner_id: int) -> bytes:
        return f"v{C.SCHEMA_VERSION}:{owner_id}:{entry_id}".encode("utf-8")

    def _entry_public(self, row) -> dict:
        data = {
            "id": row["id"],
            "issuer": row["issuer"],
            "account": row["account"],
            "label": row["label"],
            "algorithm": row["algorithm"],
            "digits": row["digits"],
            "period": row["period"],
            "revision": row["revision"],
            "is_shared": bool(row["is_shared"]),
            "owner": row["owner_name"],
            "updated_at": row["updated_at"],
        }
        if "share_count" in row.keys():
            data["share_count"] = row["share_count"]
        return data

    def _can_view(self, conn, user_id: int, row) -> bool:
        if row["owner_id"] == user_id:
            return True
        share = conn.execute(
            "SELECT 1 FROM shares WHERE entry_id=? AND grantee_id=?",
            (row["id"], user_id),
        ).fetchone()
        return bool(share)

    def _validate_params(self, algorithm: str, digits: int, period: int) -> None:
        if algorithm not in C.ALLOWED_ALGOS:
            raise AppError("invalid_algorithm", "Unsupported algorithm")
        if digits not in C.ALLOWED_DIGITS:
            raise AppError("invalid_digits", "Unsupported digits")
        if period < C.PERIOD_MIN or period > C.PERIOD_MAX:
            raise AppError("invalid_period", "Unsupported period")

    def _account_from_payload(self, payload: dict) -> OtpAccount:
        if payload.get("uri"):
            return parse_otpauth_uri(payload["uri"])
        issuer = (payload.get("issuer") or "").strip()
        account = (payload.get("account") or "").strip()
        secret = payload.get("secret") or ""
        if not issuer or not account or not secret:
            raise AppError("invalid_entry", "issuer, account and secret are required")
        algorithm = (payload.get("algorithm") or C.DEFAULT_ALGO).upper()
        digits = int(payload.get("digits") or C.DEFAULT_DIGITS)
        period = int(payload.get("period") or C.DEFAULT_PERIOD)
        self._validate_params(algorithm, digits, period)
        decode_secret(secret)
        return OtpAccount(
            issuer=issuer,
            account=account,
            secret=secret,
            algorithm=algorithm,
            digits=digits,
            period=period,
            label=payload.get("label") or f"{issuer}:{account}",
        )

    def _insert_entry(self, conn, owner_id: int, account: OtpAccount) -> int:
        ts = now()
        cur = conn.execute(
            """INSERT INTO entries(owner_id, issuer, account, label, algorithm, digits, period,
               secret_ct, secret_nonce, secret_tag, revision, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,1,?,?)""",
            (
                owner_id,
                account.issuer,
                account.account,
                account.label or f"{account.issuer}:{account.account}",
                account.algorithm,
                account.digits,
                account.period,
                b"",
                b"",
                b"",
                ts,
                ts,
            ),
        )
        entry_id = cur.lastrowid
        secret = decode_secret(account.secret)
        ct, nonce, tag = encrypt_secret(self._dek(), secret, self._aad(entry_id, owner_id))
        conn.execute(
            "UPDATE entries SET secret_ct=?, secret_nonce=?, secret_tag=? WHERE id=?",
            (ct, nonce, tag, entry_id),
        )
        return int(entry_id)

    def _find_duplicate(self, conn, owner_id: int, account: OtpAccount):
        # Duplicate identity: same owner + issuer + account (exact match).
        return conn.execute(
            "SELECT * FROM entries WHERE owner_id=? AND issuer=? AND account=? ORDER BY id ASC LIMIT 1",
            (owner_id, account.issuer, account.account),
        ).fetchone()

    def _is_duplicate(self, conn, owner_id: int, account: OtpAccount) -> bool:
        return self._find_duplicate(conn, owner_id, account) is not None

    def _replace_entry(self, conn, owner_id: int, entry_id: int, account: OtpAccount) -> None:
        secret = decode_secret(account.secret)
        aad = self._aad(entry_id, owner_id)
        ct, nonce, tag = encrypt_secret(self._dek(), secret, aad)
        ts = now()
        conn.execute(
            """UPDATE entries SET issuer=?, account=?, label=?, algorithm=?, digits=?, period=?,
               secret_ct=?, secret_nonce=?, secret_tag=?, revision=revision+1, updated_at=?
               WHERE id=? AND owner_id=?""",
            (
                account.issuer,
                account.account,
                account.label or f"{account.issuer}:{account.account}",
                account.algorithm,
                account.digits,
                account.period,
                ct,
                nonce,
                tag,
                ts,
                entry_id,
                owner_id,
            ),
        )

    def _owned_accounts_for_export(
        self, unlock_token: str, dsm_password: str, entry_ids: Optional[List[int]]
    ) -> List[OtpAccount]:
        identity = self.identity()
        if not verify_dsm_password(self.environ, dsm_password or ""):
            raise AppError("invalid_password", "Incorrect DSM password")
        with self.db.connect() as conn:
            user = self._session_user(conn, identity, unlock_token, interactive=True)
            if entry_ids:
                rows = []
                for eid in entry_ids:
                    row = conn.execute("SELECT * FROM entries WHERE id=?", (eid,)).fetchone()
                    if not row or row["owner_id"] != user["id"]:
                        raise AppError("forbidden", "Not allowed to export selected entries", 403)
                    rows.append(row)
            else:
                rows = conn.execute("SELECT * FROM entries WHERE owner_id=?", (user["id"],)).fetchall()
            accounts = []
            import base64

            for row in rows:
                secret = decrypt_secret(
                    self._dek(),
                    row["secret_ct"],
                    row["secret_nonce"],
                    row["secret_tag"],
                    self._aad(row["id"], row["owner_id"]),
                )
                accounts.append(
                    OtpAccount(
                        issuer=row["issuer"],
                        account=row["account"],
                        label=row["label"],
                        secret=base64.b32encode(secret).decode("ascii").rstrip("="),
                        algorithm=row["algorithm"],
                        digits=row["digits"],
                        period=row["period"],
                    )
                )
            return accounts

    def _parse_import_content(self, content: str, password: str) -> List[OtpAccount]:
        content = content.strip()
        if content.startswith("{"):
            blob = json.loads(content)
            if blob.get("format") == C.BACKUP_FORMAT:
                if not password:
                    raise AppError("password_required", "Password required for encrypted backup")
                plaintext = decrypt_backup_payload(password, blob)
                data = json.loads(plaintext.decode("utf-8"))
                accounts = []
                for item in data.get("entries", []):
                    accounts.append(
                        OtpAccount(
                            issuer=item["issuer"],
                            account=item["account"],
                            label=item.get("label", ""),
                            secret=item["secret"],
                            algorithm=item.get("algorithm", C.DEFAULT_ALGO),
                            digits=int(item.get("digits", C.DEFAULT_DIGITS)),
                            period=int(item.get("period", C.DEFAULT_PERIOD)),
                        )
                    )
                return accounts
        return parse_otpauth_lines(content)

    def _cleanup_previews(self, conn, user_id: int) -> None:
        conn.execute("DELETE FROM import_previews WHERE user_id=? OR expires_at < ?", (user_id, now()))
