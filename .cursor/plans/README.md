# Plans

Thư mục kế hoạch triển khai / kiến trúc cho package Synology **OTP Authentication** (`OTPAuthentication`).

## Bản chính

| File | Vai trò |
|------|---------|
| [synology_otp_package_3471a2a5.plan.md](synology_otp_package_3471a2a5.plan.md) | **Kế hoạch chính** (canonical) — kiến trúc, lifecycle SPK, CI, verification, publication |

## Liên quan

- Hành vi UI/API sống (checklist test): [`docs/logic-spec.md`](../../docs/logic-spec.md)
- Hướng dẫn agent: [`AGENTS.md`](../../AGENTS.md)
- Repo: [synology-dev/OTPAuthentication](https://github.com/synology-dev/OTPAuthentication)

## Quy ước

- Agent **không sửa** `.cursor/plans/*` trừ khi user yêu cầu rõ.
- Không tạo plan trùng; quyết định hành vi mới ghi vào `docs/logic-spec.md`.
- Thư mục này được track trong git (`!.cursor/plans/**` trong `.gitignore`).
