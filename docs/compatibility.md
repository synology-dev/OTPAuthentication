# Compatibility findings

Verified against a DSM test host (details kept out of this document).

## Confirmed environment

| Item | Result |
|------|--------|
| DSM | 7.4.1 (build 90080) |
| Kernel / arch | Linux x86_64 (`synology_geminilake_*`) |
| Platform group | `x86_64` |
| System Python | `/usr/bin/python3` → **3.8.15** |
| SQLite | 3.40.0 |
| OpenSSL | 3.0.19 |
| glibc | 2.36 |
| `cryptography` in system Python | not installed |
| Auth helper | `/usr/syno/synoman/webman/modules/authenticate.cgi` present |
| User enum helper | `/usr/syno/sbin/synouser` present (admin path) |

## Implications

- Application code targets **Python 3.8+** syntax and stdlib.
- Crypto dependency (`cryptography`) must be shipped under `package/deps/` and selected by CPU + Python ABI probe.
- CI matrix includes Python 3.8–3.14 for unit tests; DSM publish matrix lists only platforms/versions actually verified on hardware.
- ARMv8/aarch64 SPK builds in CI; mark **unverified** until NAS hardware is available.
- ARMv7 SPK builds using `manylinux_2_28` cryptography wheels; **no public cffi armv7l wheel** — treat as experimental until on-device import + glibc checks pass.

## Auth / privilege probe checklist

Scripts under `scripts/compat/` document expected CGI auth flow. Full AppWindow privilege validation requires installing a test SPK on DSM with a non-admin user.