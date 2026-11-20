# AGENTS.md — OTP Authentication

Guide for agents working in this repo (Synology DSM 7 TOTP vault package).

## Product

- Display name: **OTP Authentication**; package id: **OTPAuthentication** — native DSM ExtJS app + Python CGI backend.
- GitHub: `synology-dev/OTPAuthentication` (`https://github.com/synology-dev/OTPAuthentication`).
- Vault per DSM user, PIN unlock, share view-only, import/export (`otpauth://` + encrypted backup).
- System Python 3.8+; ship `cryptography` wheels per arch (`x86_64`, `aarch64`, `armv7`).

## Language

- Code, identifiers, commit messages, current UI labels: **English**.

## Canonical docs (read before changing behavior)

| Doc | Role |
|-----|------|
| [docs/logic-spec.md](docs/logic-spec.md) | Living logic/UI spec — test/verify checklist |
| [.cursor/plans/synology_otp_package_3471a2a5.plan.md](.cursor/plans/synology_otp_package_3471a2a5.plan.md) | Architecture plan (edit only when the user asks) |
| [docs/security.md](docs/security.md) | Security model / DEK |
| [docs/verification.md](docs/verification.md) | DSM smoke / platform matrix |
| [.cursor/rules/logic-spec-sync.mdc](.cursor/rules/logic-spec-sync.mdc) | Rule: every new requirement → update `logic-spec.md` |

## Workspace layout

```
package/ui/          ExtJS app (OTPAuthentication.js, style.css, images)
package/backend/     Python service / CGI
package/bin/         run-python wrappers
spk/                 INFO, scripts, PACKAGE_ICON*.PNG
tests/               pytest
docs/                verification, security, logic-spec
.secrets/            local only — never commit or echo
dist/                built .spk
```

## Working rules

1. **Small diffs** — do not reformat whole files; do not delete unrelated code.
2. **≥2 files changed** — state a 3–5 bullet plan, wait for user confirmation (unless the user already said “go ahead” / named a clear deliverable).
3. **No new dependency** unless asked; prefer the existing lockfile.
4. **Do not invent** Synology APIs / parameters — read code or docs in the repo.
5. **Secrets**: read `.secrets/` only when needed for deploy/test; never print passwords/tokens to chat/log; never commit `.secrets/`.
6. **Plan file** (`.cursor/plans/*`): do not edit unless the user asks.
7. **Logic spec**: every requirement/bugfix that changes behavior → read + update `docs/logic-spec.md` (stable IDs `V*`, `I*`, …).
8. Commit / push / ClickUp: only when the user asks.

## Implementation notes

- DSM 7 AppWindow: needs `jsConfig` from `appInstance`; API needs `X-SYNO-TOKEN`.
- CGI runs as user `http`: data dir permissions compatible with `OTPAuthentication:http` (typically `770`/`660`).
- App CSS: inject `/webman/3rdparty/OTPAuthentication/style.css` (see `OTPAuthentication.js`).
- PIN only locks UI/API (unlock session); secrets are encrypted with the package DEK. Forgot PIN = verify DSM password then remove/reset PIN — **do not wipe OTP** (see logic-spec §2).

## Build / test

```bash
pip install -r requirements-dev.txt
pytest -q
VERSION=1.0.0-00N TARGET=x86_64 ./build.sh
```

UI verify on lab NAS: Playwright/DSM desktop; checklist in `docs/logic-spec.md`.
Typical hot-copy: `package/ui/*` and backend → `/var/packages/OTPAuthentication/target/` (then close/reopen app or hard refresh).

## Deploy icons

Package Center icons update only after rebuild/reinstall of the SPK (`spk/PACKAGE_ICON*.PNG` + `package/ui/images/icon_*.png`).
