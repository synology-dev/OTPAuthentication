# Verification

## Local

```bash
pip install -r requirements-dev.txt
pytest -q
./build.sh
```

## DSM smoke (x86_64 — DS220+ / DSM 7.4.1 / Python 3.8.15)

Verified 2026-11-19 on lab NAS (`OTPManager-1.0.0-004` … `1.0.0-006` hot-patched UI/CGI):

1. Fresh install + start OK (package-user ownership of `@appdata`; vault dirs `770` / files `660`, group `http` for CGI).
2. Start/stop/status lifecycle OK (`run-python` BusyBox/stdin-safe; scripts avoid fragile heredocs).
3. System Python 3.8.15 + shipped `cryptography` manylinux abi3 (+ cffi cp38 on x86_64/aarch64) import OK.
4. Two-user ACL: alice owns entry; bob shared view/codes OK; delete/reveal/export denied.
5. Cross-user unlock token rejected.
6. Encrypted export + import preview OK.
7. `pin_status` reports `package_stopped` when disabled.
8. Data dir usable by package user + `http` CGI; secrets not world-readable.

### ExtJS UI (Playwright, DSM desktop)

Pass on DS220+ / DSM 7.4.1 as user `nas` (synthetic vault PIN + TOTP secret `JBSWY3DPEHPK3PXP`):

1. Launch OTP Manager AppWindow OK (`jsConfig` handoff + SynoToken headers).
2. Unlock vault OK.
3. Add OTP (issuer `Example`, account `nas@example.com`) OK.
4. Live 6-digit code + remaining seconds refresh in grid (`status: 1 entries`).

Still required before Package Center publish:

- Share / backup-restore dialogs in UI (API already smoke-tested).
- DSM user **without** app privilege denied.
- Upgrade path on a build that already has the fixed BusyBox `preupgrade`.
- aarch64 / armv7 hardware installs (CI builds only until then; armv7 lacks public cffi wheel).
- Optional: auto-open Setup/Unlock on first launch (manual toolbar path works).

## Platform matrix status

| Target | Status |
|--------|--------|
| x86_64 | Verified install/start/stop + vault ACL on DSM 7.4.1 / Python 3.8.15 |
| aarch64 | Built in CI; DSM hardware verification pending |
| armv7 | Built in CI; DSM hardware verification pending |

Do not publish unverified targets as fully supported.
