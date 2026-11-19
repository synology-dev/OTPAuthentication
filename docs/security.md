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

Runtime wheels under `package/deps/<arch>/` are dual-path (selected by `run-python`):

| System Python | Bundle | `cryptography` |
|---------------|--------|----------------|
| 3.8 | `cp38/` | **47.0.0** (last line supporting 3.8) |
| ≥ 3.9 | `abi3/` or `cp39/` | **50.0.2** |

Dev/CI keep `cryptography==50.0.2` in `requirements-dev.txt` for tests and `pip-audit`. Run `pip-audit -r requirements-dev.txt` before each release.