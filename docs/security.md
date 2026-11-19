# Security model

## Threat model (MVP)

- Protects against other DSM users without share grants.
- Protects against casual access when the app is locked (PIN gates UI/API unlock session only).
- Does **not** protect secrets from NAS root / anyone with filesystem access to both `otp.db` and `dek`.
- Forgot PIN (DSM password) removes or resets PIN protection; it does **not** wipe OTP entries (secrets stay under package DEK).

## Controls

- AES-256-GCM at rest with package DEK (`/var/packages/OTPAuthentication/var/dek`).
- PIN: PBKDF2-HMAC-SHA256, 6–12 digits, lockout/cooldown; unlock session only (not a per-user DEK).
- Unlock tokens hashed at rest, idle + absolute timeouts; polling does not extend idle timeout.
- CSRF token bound to unlock session; state-changing requests require POST.
- Share ACL enforced server-side; grantees cannot reveal/export secrets.
- No secrets in logs.

## Dependency

`cryptography==50.0.2` is shipped under `package/deps/<arch>/` and selected by the Python probe (requires system Python ≥ 3.9). Run `pip-audit -r requirements-dev.txt` before each release.

DSM hosts still on Python 3.8 cannot use this package crypto stack; upgrade the system interpreter or stay on an older SPK that vendors cryptography 47.