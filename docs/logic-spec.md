# OTP Authentication — đặc tả logic (UI / hành vi)

Tài liệu sống để test/verify. Cập nhật khi có yêu cầu hoặc thay đổi hành vi.
Nhãn UI hiện tại chủ yếu tiếng Anh (khớp app).

## 1. Vault & PIN

Mô hình: **PIN = khóa UI/API** (cấp unlock session). OTP ciphertext dùng package DEK — quên PIN không mất dữ liệu.

| ID | Hành vi | Ghi chú test |
|----|---------|--------------|
| V1 | Vault có PIN: mở app → hiện popup **Unlock OTP Authentication** ngay (không cần bấm Import/Add trước) | Mở app lần đầu trong session |
| V2 | Đóng app (X): **không** hiện lại Unlock | Sau khi unlock hoặc đang hiện Unlock rồi X |
| V3 | Unlock có nút **Cancel** và **Unlock** | Cancel đóng dialog, vault vẫn khóa |
| V4 | Setup PIN (lần đầu) có Cancel + hành động chính | |
| V5 | Toolbar: vault **khóa** → nhãn **Unlock**; vault **mở** → nhãn **Lock** | Cancel Unlock → phải là Unlock |
| V5b | **Không có PIN** (chưa setup / đã disable) → **ẩn** nút Lock/Unlock | Hiện lại khi bật/setup PIN |
| V11 | Sau **Setup PIN** / bật PIN lại → **hiện** nút; sau New PIN trống (disable) hoặc **Remove PIN protection** → **ẩn** | |
| V6 | Bấm **Unlock** (toolbar) → mở dialog Unlock; bấm **Lock** → khóa vault | |
| V7 | **Forgot PIN** trên dialog Unlock | Xem §2 |
| V8 | Đóng Unlock bằng Cancel: cửa sổ chính vẫn mở, không auto-reopen Unlock | |
| V9 | **New PIN để trống** (Change PIN / chỗ đặt PIN mới) = **vô hiệu hóa PIN**; giữ nguyên OTP | Không bắt buộc luôn có PIN |
| V10 | PIN không trống thì vẫn 6–12 digits; empty chỉ hợp lệ khi nghĩa là disable | |

## 2. Forgot PIN (đã chốt)

| ID | Hành vi |
|----|---------|
| F1 | Unlock có nút **Forgot PIN** |
| F2 | Bấm Forgot PIN → yêu cầu nhập **mật khẩu DSM** của user hiện tại |
| F3 | Sai mật khẩu → báo lỗi, không reset; có rate-limit (`pin_attempts`) |
| F4 | Đúng mật khẩu → hai lựa chọn: **Remove PIN protection** / **Set a new PIN** |
| F5 | PIN chỉ bảo vệ thao tác UI/API (session unlock). **Không wipe** OTP entries/shares khi Forgot PIN |
| F6 | Remove PIN protection → clear PIN, `pin_disabled`, cho dùng app không PIN; **giữ nguyên** OTP |
| F7 | Set a new PIN → bỏ PIN cũ / Setup PIN mới; **giữ nguyên** OTP |
| F8 | Xác thực DSM qua `SYNO.Core.User.PasswordConfirm` (auth v2), forward session Cookie/`_sid` |

## 3. Import

| ID | Hành vi |
|----|---------|
| I1 | Import khi vault khóa: **không** chỉ hiện lỗi trần "Vault is locked" — mở Unlock (hoặc tương đương) |
| I2 | **Confirm import** chạy được **không bắt buộc Preview** trước |
| I3 | Trùng entry theo **issuer + account** (cùng owner) |
| I4 | Conflict UI: **Override** / **Skip** / **Override All** / **Skip All** (+ Cancel) |
| I5 | Override cập nhật entry cũ; Skip bỏ qua; *All áp dụng cho phần còn lại trong batch |

## 4. Dialog / form chung

| ID | Hành vi |
|----|---------|
| D0 | Lỗi API: hiện `error.message` (fallback `error.code`), **không** nuốt thành “Network error” khi body có JSON lỗi |
| D0b | Lỗi thao tác form: hiện **trên dialog/form** đang mở; status cửa sổ chính chỉ cho thao tác grid/app-level |
| D0c | Chữ lỗi validate/dialog (`_dialogError`, API `error.message`, invalid): **đỏ** `#d94841` (`--otp-warn`) dưới `.otpauthentication-dialog` |
| D1 | Mọi popup của app có **Close** hoặc **Cancel** (không chỉ một nút primary) |
| D2 | Skin DSM 7 light: toolbar, grid, dialog (accent `#2481eb`) |
| D3 | Không viền đen thô; viền mềm `#d0d4d9` / soft shadow |
| D4 | Textarea (URI…) cùng chiều rộng input text sibling |
| D5 | Combo (Algorithm/Digits…): một khối, trigger không lệch/ô xám nổi |
| D6 | Input/combo đủ cao (~32px), không sát chữ |
| D7 | Title dialog không sát đường kẻ header (padding ~16px tới border) |
| D8 | Màn hình chính: grid/toolbar/paging/status inset trái–phải ~14px (border `margins`), không sát mép cửa sổ | |
| D9 | Settings: hàng Info Center — cột label trái + value/control phải, gutter thẳng hàng; separator ngang nhẹ giữa hàng (không zebra). **Copy to Clipboard only**: label trái, checkbox cột value | |

## 5. Grid / codes

| ID | Hành vi |
|----|---------|
| G1 | Cột Code: monospace, nổi bật; có mã live khi đã unlock |
| G2 | Cột Time: đổi màu cảnh báo khi remaining thấp (≤ 5s) |
| G3 | **Không** có nút/toggle “My OTPs” / “Shared with me” — một danh sách chung (owned + shared) |
| G4 | Click ô **Code** → copy TOTP vào clipboard; feedback ngắn “Copied” (status) | OM-18 |
| G5 | Settings checkbox **Copy to Clipboard only** (mặc định **tắt**, lưu per-user localStorage). Bật → mask CODE (`••••••`); click cell vẫn copy mã thật + “Copied” | |
| G6 | Phân trang kiểu DSM Log Center: first/prev/page/next/last, Items per page (25/50/100/200, mặc định 50), “N items”, refresh | API list offset/limit + total |

## 6. Export

| ID | Hành vi |
|----|---------|
| E1 | Dialog Export **không** có trường vault PIN |
| E2 | Mọi export (plain/enc) đều yêu cầu **mật khẩu DSM** (re-auth `SYNO.Core.User.PasswordConfirm`) |
| E3 | Format **Encrypted**: hiện **Encryption password** + Confirm; trống → “Encryption password is required”; không khớp → message riêng; **không** min length/complexity. Plaintext: **ẩn** hai field |
| E4 | Plaintext: hiện checkbox rủi ro 2FA; Encrypted: ẩn checkbox |
| E5 | Cần unlock session + CSRF; sai DSM password → lỗi trên dialog, không export |
| E6 | Checkbox plaintext: checkbox thẳng hàng dọc với dòng chữ đầu của label |

## 7. Package icon

| ID | Hành vi |
|----|---------|
| P1 | Icon không phải ô màu trơn; motif OTP/vault (shield + ticks + lock) |
| P2 | Bo góc kiểu app DSM (Control Panel…), ngoài góc trong suốt |
| P3 | `spk/PACKAGE_ICON.PNG` (72), `PACKAGE_ICON_256.PNG` (256) + `package/ui/images/icon_*.png` |

## 8. Ngoài phạm vi / chưa chốt trong đặc tả này

- Recovery key / câu hỏi bảo mật (đã gợi ý; **không** chọn — đã chọn Forgot PIN + DSM password).
- Share / backup UI polish chi tiết ngoài skin chung.
- User DSM không có quyền app → denied (smoke verification riêng).

## Lịch sử quyết định ngắn

- 2026-11-19: Unlock on open; Cancel trên auth dialogs; không Unlock khi close.
- 2026-11-19: Import Confirm không cần Preview; conflict Override/Skip/*All; trùng issuer+account.
- 2026-11-19: Toolbar Lock/Unlock theo trạng thái vault.
- 2026-11-19: Forgot PIN → DSM password → xóa PIN hoặc đặt PIN mới (**không wipe OTP**; PIN chỉ khóa UI/API).
- 2026-11-19: Icon bo góc DSM.
- 2026-11-19: Lỗi validate hiện message thật trên form; New PIN trống = disable PIN.
- 2026-11-19: Bỏ filter My OTPs / Shared with me — list chung.
- 2026-11-19: OM-18 — click cột Code copy clipboard + “Copied”.
- 2026-11-19: Click Code → copy clipboard.
- 2026-11-19: Không PIN → ẩn nút Lock/Unlock.
- 2026-11-19: Settings “Copy to Clipboard only” — mask CODE khi bật.
- 2026-11-19: Phân trang grid kiểu Log Center.
- 2026-11-19: Export bỏ PIN; re-auth bằng mật khẩu DSM; sửa căn checkbox plaintext.
- 2026-11-19: Export plaintext ẩn password/confirm; encrypted hiện; DSM password luôn bắt buộc.
- 2026-11-19: Chữ lỗi validate/dialog màu đỏ toàn bộ form.
- 2026-11-19: D8 — grid/toolbar màn chính padding trái–phải ~14px.
- 2026-11-19: Export encryption password tự do (không min length); label Encryption password; lỗi required rõ.
- 2026-11-19: Đổi tên package/id/path/Ext → **OTPAuthentication**; display **OTP Authentication**; GitHub `synology-dev/OTPAuthentication`. Migrating vault từ package cũ: copy `@appdata/OTPManager` → `OTPAuthentication` (postinst tự copy nếu data mới trống).
- 2026-11-19: Settings restyle kiểu DSM Info Center (D9) — hàng label|value + checkbox căn cột value.
