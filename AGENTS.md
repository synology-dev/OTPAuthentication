# AGENTS.md — OTP Authentication

Hướng dẫn cho agent làm việc trong repo này (Synology DSM 7 TOTP vault package).

## Product

- Display name: **OTP Authentication**; package id: **OTPAuthentication** — native DSM ExtJS app + Python CGI backend.
- GitHub: `synology-dev/OTPAuthentication` (`https://github.com/synology-dev/OTPAuthentication`).
- Vault per DSM user, PIN unlock, share view-only, import/export (`otpauth://` + encrypted backup).
- System Python 3.8+; ship `cryptography` wheels per arch (`x86_64`, `aarch64`, `armv7`).

## Language

- Chat với user: **tiếng Việt**.
- Code, identifiers, commit messages, nhãn UI hiện tại: **English**.

## Canonical docs (read before changing behavior)

| Doc | Role |
|-----|------|
| [docs/logic-spec.md](docs/logic-spec.md) | Đặc tả logic/UI sống — checklist test/verify |
| [.cursor/plans/synology_otp_package_3471a2a5.plan.md](.cursor/plans/synology_otp_package_3471a2a5.plan.md) | Plan kiến trúc (chỉ sửa khi user yêu cầu) |
| [docs/security.md](docs/security.md) | Mô hình bảo mật / DEK |
| [docs/verification.md](docs/verification.md) | Smoke DSM / ma trận platform |
| [.cursor/rules/logic-spec-sync.mdc](.cursor/rules/logic-spec-sync.mdc) | Rule: mọi yêu cầu mới → cập nhật `logic-spec.md` |

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

1. **Diff nhỏ** — không format lại cả file; không xóa code không liên quan.
2. **≥2 file thay đổi** — nêu kế hoạch 3–5 gạch đầu dòng, chờ user xác nhận (trừ khi user đã bảo “làm đi” / chỉ định rõ deliverable).
3. **Không dependency mới** nếu chưa hỏi; ưu tiên lockfile hiện có.
4. **Không bịa** API Synology / tham số — đọc code hoặc docs trong repo.
5. **Secrets**: chỉ đọc `.secrets/` khi cần deploy/test; không in password/token ra chat/log; không commit `.secrets/`.
6. **Plan file** (`.cursor/plans/*`): không sửa trừ khi user yêu cầu.
7. **Logic spec**: mọi yêu cầu/bugfix đổi hành vi → đọc + cập nhật `docs/logic-spec.md` (ID ổn định `V*`, `I*`, …).
8. Commit / push / ClickUp: chỉ khi user yêu cầu.

## Implementation notes

- DSM 7 AppWindow: cần `jsConfig` từ `appInstance`; API cần `X-SYNO-TOKEN`.
- CGI chạy user `http`: data dir quyền tương thích `OTPAuthentication:http` (thường `770`/`660`).
- CSS app: inject `/webman/3rdparty/OTPAuthentication/style.css` (xem `OTPAuthentication.js`).
- PIN chỉ khóa UI/API (unlock session); secrets mã hóa bằng package DEK. Forgot PIN = xác thực mật khẩu DSM rồi gỡ/đặt lại PIN — **không wipe OTP** (xem logic-spec §2).

## Build / test

```bash
pip install -r requirements-dev.txt
pytest -q
VERSION=1.0.0-00N TARGET=x86_64 ./build.sh
```

UI verify trên lab NAS: Playwright/DSM desktop; checklist theo `docs/logic-spec.md`.
Hot-copy thường: `package/ui/*` và backend → `/var/packages/OTPAuthentication/target/` (rồi đóng/mở app hoặc hard refresh).

## Deploy icons

Icon Package Center chỉ cập nhật sau build/cài lại SPK (`spk/PACKAGE_ICON*.PNG` + `package/ui/images/icon_*.png`).
