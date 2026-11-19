# Security model

## Threat model (MVP)

- Protects against other DSM users without share grants.
- Protects against casual access when the app is locked (PIN gates UI/API unlock session only).
- Does **not** protect secrets from NAS root / anyone with filesystem access to both `otp.db` and `dek`.
- Forgot PIN (DSM password) removes or resets PIN protection; it does **not** wipe OTP entries (secrets stay under package DEK).

## Controls

- AES-256-GCM at rest with package DEK (`/var/packages/OTPManager/var/dek`).
- PIN: PBKDF2-HMAC-SHA256, 6–12 digits, lockout/cooldown; unlock session only (not a per-user DEK).
- Unlock tokens hashed at rest, idle + absolute timeouts; polling does not extend idle timeout.
- CSRF token bound to unlock session; state-changing requests require POST.
- Share ACL enforced server-side; grantees cannot reveal/export secrets.
- No secrets in logs.

## Dependency

`cryptography==47.0.0` is shipped under `package/deps/<arch>/` and selected by the Python probe (newest release that still installs on Python 3.8). Run `pip-audit -r requirements-dev.txt` before each release.

Known residual advisories as of the 1.0.0-005 build (fixes need cryptography 48–50, which require Python ≥ 3.9): PYSEC-2026-3552, PYSEC-2026-3553, PYSEC-2026-3554, GHSA-537c-gmf6-5ccf. Track DSM system Python upgrades; when NAS interpreters are ≥ 3.9, bump cryptography past 48 and re-verify wheels on hardware.

`cryptography` 47 emits a Python 3.8 deprecation warning on import; treat that as a forward-looking publish constraint, not a runtime failure on current DSM 7.4.1.