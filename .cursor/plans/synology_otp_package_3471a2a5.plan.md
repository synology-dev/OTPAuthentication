---
name: Synology OTPManager Package
overview: "OTP Manager: ExtJS native, Python hệ thống DSM tự phát hiện, dependencies riêng theo CPU/ABI, vault per-user, PIN, share, backup; GitHub Actions build và chuẩn bị publish Free."
isProject: true
todos:
  - id: compatibility
    content: "Kiểm chứng DSM integration, Python hệ thống DSM/crypto/toolchain và ma trận platform trước khi triển khai vault"
    status: pending
  - id: repository
    content: "Khởi tạo repo, giữ plan chính, cấu hình build reproducible và khóa dependencies"
    status: pending
  - id: backend
    content: "Backend: identity DSM, SQLite, encryption, PIN/session, ACL, TOTP và tests"
    status: pending
  - id: ui
    content: "ExtJS native: unlock, CRUD, search, codes, share và backup/restore"
    status: pending
  - id: lifecycle
    content: "SPK lifecycle, migration, backup nhất quán, stop enforcement và uninstall an toàn"
    status: pending
  - id: ci
    content: "GitHub Actions: lint/tests, cross-build matrix, validation, checksums và release"
    status: pending
  - id: verification
    content: "Kiểm thử DSM theo platform, hai user thường và user không được cấp quyền"
    status: pending
  - id: publication
    content: "Hoàn thiện tài liệu, license, privacy, screenshots và hồ sơ publish Free"
    status: pending
---

# OTP Manager — kế hoạch triển khai và phát hành

## 1. Quyết định đã chốt

- Bản chính duy nhất: [.cursor/plans/synology_otp_package_3471a2a5.plan.md](synology_otp_package_3471a2a5.plan.md). Commit file này.
- Repository: [synology-dev/OTPManager](https://github.com/synology-dev/OTPManager), SSH remote `git@github.com:synology-dev/OTPManager.git`.
- Package ID `OTPManager`; tên hiển thị `OTP Manager`; namespace `SYNO.SDS.OTPManager.Application`.
- UI desktop native ExtJS, không chuyển sang WebStation portal hoặc iframe SPA.
- Backend dùng **Python 3 hệ thống DSM**, không hardcode minor version, không đóng gói interpreter và không yêu cầu cài package Python riêng. Không sửa site-packages hệ thống. Hỗ trợ rộng các phiên bản đã được kiểm chứng bằng capability probe và CI, không tuyên bố mọi Python đều tương thích.
- Bỏ `noarch`. CI build cho nhóm x86_64, ARMv8/aarch64 và ARMv7; đóng gói theo platform/ABI tương thích.
- Mục tiêu DSM 7.0/7.1 trở lên. Chỉ công bố các tổ hợp DSM/model/platform đã kiểm chứng; không khẳng định mọi NAS DSM 7.x đều hỗ trợ.
- Vault riêng mỗi user DSM; chia sẻ từng entry với quyền xem mã. Publish **Free** trên Package Center sau khi đạt kiểm thử và được Synology chấp thuận.

## 2. Ràng buộc Python hệ thống DSM và điều kiện phát hành

Không coi phiên bản Python là cố định theo DSM. Synology quản lý interpreter; dự án quản lý dependencies riêng và kiểm thử lại sau DSM update. Phiên bản upstream EOL cần đánh giá bản vá/advisory của vendor, không tự suy ra an toàn hoặc không an toàn chỉ từ version.

- Baseline mã nguồn là Python 3.8-compatible; CI mục tiêu Python 3.8–3.14. Đây là phạm vi test dự kiến, không khẳng định DSM cung cấp mọi phiên bản này. Không hỗ trợ Python 2. Runtime ngoài phạm vi đã kiểm chứng bị từ chối kèm thông báo rõ, không thử chạy mù.
- Launcher dò interpreter tại các đường dẫn hệ thống tin cậy được xác minh trên DSM, không dùng PATH tùy ý. Probe version, architecture, sqlite3, ssl, hashlib, hmac, entropy và crypto backend. Ghi lại đường dẫn đã xác thực trong cấu hình riêng, revalidate mỗi start và sau DSM upgrade; không cố định tên `python3.9`.
- Dependencies nằm trong thư mục riêng của package, không pip install trên NAS, không sửa Python hệ thống hoặc dùng site-packages từ user. Probe chạy cùng identity/environment thực tế của backend.
- Native crypto phải khớp CPU, libc, Python ABI và OpenSSL linkage. Build dependency bundles theo nhóm Python ABI đã kiểm chứng; chỉ dùng abi3 khi thư viện thực sự hỗ trợ. Khóa manifest chọn bundle theo runtime và fail closed nếu không có bundle phù hợp. Không coi SPK theo CPU là đủ tương thích mọi minor Python.
- Python 3.8-compatible syntax không đảm bảo thư viện crypto còn hỗ trợ 3.8. Không ép dùng dependency EOL chỉ để mở rộng matrix; target không đạt security gate là blocker phải báo người dùng.
- Chọn Python `cryptography` cho AES-256-GCM. Đây là dependency mới phải được người dùng duyệt trước implementation/cài đặt; không tự cài trong giai đoạn plan.
- Kiểm tra phiên bản `cryptography`, Rust build toolchain và OpenSSL tương thích Python hệ thống DSM, libc và CPU mục tiêu. Không pin tùy tiện bản cũ chỉ để build pass; cần rà advisory và nguồn hỗ trợ.
- CI có bước rà vulnerability và license cho runtime cùng native dependencies. Không phát hành khi còn lỗ hổng nghiêm trọng áp dụng mà chưa xử lý hoặc chưa có kế hoạch hỗ trợ bản vá được chấp nhận.
- Nếu không tìm được bộ runtime/crypto an toàn và build được, dừng trước implementation để báo blocker; không âm thầm đổi Python, giảm DSM support hoặc thay bằng crypto tự viết.
- Không dùng `openssl enc` làm fallback AES-GCM, không viết AES, không copy implementation crypto không rõ nguồn.

## 3. Giai đoạn đầu: compatibility và DSM integration

Thực hiện trước khi xây dựng vault thật, chỉ dùng dữ liệu tổng hợp:

1. Xác nhận version DSM, model, CPU/ABI và môi trường thử nghiệm qua quyền truy cập được cấp riêng; không đưa host/user/port/password NAS vào repo.
2. Tạo SPK thử nghiệm tối thiểu có icon và AppWindow; kiểm tra mở app bằng user thường. Xác minh ExtJS/API thực tế trên từng DSM, không coi ví dụ cộng đồng là cam kết tương thích.
3. Xác thực session DSM từ custom CGI bằng cơ chế được Synology tài liệu hóa; xác nhận helper, CGI environment, logout, account disabled và application privilege.
4. Đo UID/GID thực tế của CGI và quyền đọc/ghi dữ liệu. `conf/privilege` không tự chứng minh CGI chạy dưới package user. Không giải quyết bằng root, setuid hoặc chmod world-readable; thiếu cơ chế quyền an toàn là blocker.
5. Xác minh API/nguồn danh tính user và vòng đời xóa/tạo lại tài khoản. MVP hỗ trợ local DSM users; không tự mở rộng LDAP/domain.
6. Probe Python có sẵn; cross-build dependency crypto cho CPU/Python ABI tương ứng, kiểm tra SQLite, SSL, entropy, AES-GCM round-trip và tamper rejection trên NAS. Không build hoặc cài interpreter.
7. Ánh xạ nhóm CPU sang platform/toolchain chính thức, chốt minimum DSM và metadata `arch` theo kết quả.

Tiêu chí qua bước này: UI/CGI hoạt động đúng quyền, identity tin cậy, runtime/crypto chạy offline và ít nhất một target có kết quả tích hợp thật. Các target khác phải qua cùng kiểm chứng trước khi release đầy đủ.

## 4. Kiến trúc và cấu trúc repo

Frontend ExtJS gọi JSON CGI cùng origin tại `/webman/3rdparty/OTPManager/webapi/`. CGI xác thực DSM, kiểm tra app privilege, trạng thái package, unlock session và ACL trước khi truy cập dữ liệu.

Các đường dẫn dự kiến:

- `package/ui/OTPManager.js`: AppInstance/AppWindow, dialogs, countdown và client API.
- `package/ui/config`: đăng ký app và privilege theo cơ chế xác minh ở compatibility spike.
- `package/ui/webapi/`: entry points CGI mỏng; không chứa key/DB hoặc mã nguồn nhạy cảm có thể tải qua HTTP.
- `package/backend/`: auth, sessions, storage, crypto, TOTP, URI parser, share và backup.
- `package/deps/`: dependency bundles riêng theo CPU/Python ABI; manifest và launcher chọn bundle đã kiểm chứng. Không chứa Python interpreter.
- `spk/INFO.in`, `spk/conf/privilege`, `spk/conf/resource`, `spk/scripts/`: metadata và lifecycle.
- `build.sh`, `build/`: cross-build, dependency lock/checksum, platform mapping và SPK validator.
- `tests/`: unit, authorization/integration và fixture tổng hợp.
- `.github/workflows/ci.yml`, `.github/workflows/release.yml`: kiểm thử và build/release.
- `docs/`: hướng dẫn người dùng, build, security model, compatibility và submission checklist.

Dữ liệu nằm ngoài web root, trong persistent package data directory do DSM quản lý, truy cập qua `/var/packages/OTPManager/var` sau khi xác minh lifecycle. Directory mode 0700, DB/key mode 0600; chỉ identity backend được cấp quyền.

## 5. Mô hình bảo mật

### At-rest encryption

- Một package DEK 256-bit sinh bằng CSPRNG; mỗi entry mã hóa AES-256-GCM với nonce 96-bit mới khi ghi và tag 128-bit.
- AAD gắn schema version, entry ID và owner ID; không cho phép tráo ciphertext giữa entry/owner.
- PIN là khóa truy cập app, **không phải khóa giải mã DEK**. Per-user là phân quyền ứng dụng, không phải cách ly mật mã khỏi root.
- Bên có cả DB và DEK có thể giải mã. Không quảng bá zero-knowledge hoặc bảo vệ khỏi admin NAS.
- Không gửi secret cho người nhận share; owner chỉ nhận secret qua thao tác reveal/export có xác nhận PIN lại.
- Mất key khi DB đã tồn tại: fail closed, tuyệt đối không sinh key mới rồi ghi đè dữ liệu.

### PIN và phiên

- PIN số tối thiểu 6, tối đa 12 chữ số; UI khuyến nghị PIN dài. Lưu salted PBKDF2-HMAC-SHA256 với tham số versioned; benchmark trên NAS yếu nhất và rà hướng dẫn hiện hành trước khóa tham số.
- Hạn chế thử sai bền vững theo user, backoff tăng dần và cooldown sau 5 lần sai; thao tác cập nhật bộ đếm phải atomic.
- Token random 32 bytes, chỉ lưu hash trong DB; gắn user, instance app và session DSM. Không lưu token vào localStorage hoặc URL.
- Idle timeout 15 phút, thời gian sống tối đa 8 giờ. Chỉ tương tác người dùng mới gia hạn; polling không gia hạn.
- Lock, đổi PIN, stop package thu hồi phiên. Đóng cửa sổ thu hồi best-effort; thời hạn server vẫn bắt buộc. Session DSM hết hạn/logout/disable phải bị từ chối ở request kế tiếp.
- Đổi PIN cần PIN hiện tại. MVP không có bypass/reset PIN tự động; tài liệu phải nói rõ trước setup. Backup đã export có thể nhập vào vault mới hợp lệ bằng mật khẩu backup.

### API hardening

- Mọi API, kể cả list/search/metadata, cần unlock trừ status/setup/unlock đã xác thực DSM.
- Kiểm tra quyền ở backend cho từng entry, không tin username/owner do client gửi.
- Thay đổi trạng thái chỉ qua POST, CSRF token gắn session, kiểm tra Origin với cấu hình origin tin cậy; không coi custom header đơn lẻ là đủ.
- HTTPS là điều kiện vận hành; responses nhạy cảm dùng `Cache-Control: no-store`; escape metadata trong UI, SQL parameterized.
- Giới hạn request/upload/batch, kiểm tra schema/type; không log secret, OTP, PIN, password backup, token, cookie hoặc DEK.

## 6. Dữ liệu, TOTP và share

SQLite có schema version, foreign keys, transaction và busy timeout. Các bảng:

- `users`: internal ID, DSM identity binding, username hiển thị, PIN hash/salt/parameters, trạng thái.
- `entries`: ID, owner ID, issuer, account, label, algorithm, digits, period, ciphertext/nonce/tag và timestamps.
- `shares`: entry ID, grantee ID, timestamps; unique entry/grantee. MVP chỉ có quyền view.
- `sessions`: token hash, owner/session binding, idle/absolute expiry và revocation.
- `pin_attempts`: counter/cooldown bền vững theo user.
- `schema_migrations`, package enabled state và security event metadata không chứa secrets.

Identity DSM phải có cơ chế phát hiện account bị xóa/tạo lại; username hoặc UID có thể tái sử dụng không đủ để tự trao lại vault. Tình huống không chứng minh được continuity phải fail closed và yêu cầu xử lý rõ ràng, không tự remap.

TOTP hỗ trợ SHA1/SHA256/SHA512, 6 hoặc 8 digits, period nguyên từ 15 đến 300 giây; mặc định SHA1/6/30. URI ngoài phạm vi bị báo lỗi, không âm thầm sửa tham số. HOTP ngoài MVP.

- Owner: CRUD, xem mã, share/revoke, reveal/export sau PIN lại.
- Người nhận: xem metadata và mã hiện tại; không sửa/xóa/share/reveal/export secret.
- Thu hồi ACL kiểm tra mỗi request. Mã đã hiển thị không thể thu hồi ngược và còn giá trị tới hết chu kỳ.
- Chỉ share với local DSM user đã khởi tạo OTP Manager; nhập username chính xác và kiểm tra server, không lộ danh sách toàn bộ tài khoản.
- Search không phân biệt hoa/thường trên issuer/account/label, chỉ trong tập entry được phép; phân trang và giới hạn batch.

## 7. Backup / restore

### Plaintext

Mỗi dòng một `otpauth://totp/` URI; percent-encode issuer/account đúng quy tắc, xuất `secret`, `issuer` và algorithm/digits/period không mặc định. Không ghi secrets thật trong test hoặc tài liệu.

Chỉ export entries sở hữu. Cảnh báo rõ file chứa khóa 2FA; yêu cầu nhập lại PIN, tải trực tiếp, không lưu plaintext tạm trên NAS.

### Encrypted

- File JSON có format version, cipher, KDF identifier/parameters, salt, nonce và ciphertext/tag base64.
- AES-256-GCM; key dẫn xuất từ password backup độc lập PIN bằng PBKDF2-HMAC-SHA256; tham số được khóa sau benchmark/security review ở compatibility gate.
- Salt tối thiểu 16 bytes, nonce 12 bytes, tag 16 bytes; authenticate header bằng canonical AAD.
- Payload JSON versioned chứa metadata và TOTP parameters; không gồm PIN, sessions, DEK hay ACL share.
- V1 giới hạn file 10 MiB, 10.000 entries; KDF parameters phải nằm trong profile cho phép để chống DoS. Sai password, tag lỗi hoặc format không hỗ trợ: từ chối toàn bộ.

### Import

Preview và validate toàn bộ trước commit transaction. Mặc định merge, bỏ duplicate chính xác sau chuẩn hóa; cùng issuer/account nhưng khác secret giữ thành entry riêng có cảnh báo. Không replace trong MVP. Lỗi bất kỳ không để lại import một phần; thông báo chỉ số dòng/entry, không echo secret.

Backup cá nhân phục hồi vào owner đang đăng nhập, không tự khôi phục share. Backup phục hồi toàn package là quy trình quản trị riêng gồm DB và DEK nhất quán.

## 8. UI và API

UI native gồm UnlockDialog, danh sách Owned/Shared, search, CRUD, share/revoke, backup/restore và Lock. Không dùng `Ext.create` của ExtJS mới trong code target ExtJS 3.

API nhóm chức năng:

- `pin`: status/setup/unlock/change/lock.
- `entries`: list/create/update/delete/reveal.
- `codes`: batch mã, server time và thời điểm hết hạn.
- `shares`: list/add/remove/resolve-recipient.
- `backup`: export/import plain và encrypted, preview/confirm.

Countdown chạy client dựa trên giờ server. Fetch theo ranh giới chu kỳ, không gọi CGI mỗi giây. Dừng polling khi ẩn/khóa; khi quay lại kiểm tra phiên trước hiển thị. Dọn mã/token khỏi UI khi khóa; copy clipboard cần thao tác người dùng và không hứa xóa clipboard tự động.

### 8.1. Điều hướng và danh sách

- **My OTPs**: mặc định sau unlock, chỉ entries sở hữu. Grid: issuer, account, label, code, countdown, trạng thái share và actions.
- **Shared with me**: entries được chia sẻ, thêm cột owner; chỉ xem/copy mã.
- **Settings**: Change PIN, idle timeout 15 phút và absolute timeout 8 giờ ở dạng chỉ đọc trong MVP; About hiển thị version app, DSM/Python đã phát hiện, không hiển thị đường dẫn/key nhạy cảm.
- **Lock** luôn có trên toolbar khi mở khóa. Không hiển thị entry, metadata hoặc search results phía sau màn hình PIN.
- Search trong tab hiện tại trên issuer/account/label, debounce 300 ms, reset pagination khi đổi query; bỏ response cũ về trễ. Có Clear search và pagination.
- Chọn nhiều dòng chỉ dùng cho export trên My OTPs; MVP không bulk delete/share.

### 8.2. Toolbar và action contract

Các tên action dưới đây là contract nội bộ dự kiến, không phải API có sẵn của DSM. Mọi thao tác đều kiểm tra session/ACL phía server tại thời điểm thực hiện.

- **Add OTP** — My OTPs; mở form, chọn Manual hoặc Paste URI. Preview URI không lưu dữ liệu; Save gọi `entries.create`, thành công thêm entry và đóng dialog, lỗi giữ form không chứa lỗi echo secret.
- **Import** — My OTPs; file plaintext/encrypted, password cho encrypted. Preview gọi `backup.preview`; Confirm Import chỉ bật khi toàn bộ input hợp lệ, gọi `backup.confirm`, trả số added/skipped và refresh danh sách.
- **Export** — My OTPs; phạm vi Selected hoặc All owned, mặc định Selected khi có lựa chọn, ngược lại All owned. Không hiểu All là trang hiện tại hoặc kết quả search. Mặc định encrypted, yêu cầu password và confirm password. Plaintext có cảnh báo riêng và checkbox xác nhận. Cả hai yêu cầu PIN lại; server reauthorize toàn bộ tập entry trước export, không xuất một phần âm thầm khi quyền/dữ liệu đã thay đổi.
- **Lock** — gọi `pin.lock`, đồng thời dọn UI ngay. Nếu mất mạng vẫn khóa local, không báo đã revoke server thành công; token server hết hạn theo policy. Không chờ network mới che secrets.
- **Refresh** — tải lại danh sách/quyền và mã của tab hiện tại, không tự unlock hoặc kéo dài phiên chỉ vì refresh nền.

### 8.3. Actions từng entry

- **Copy code** — owner hoặc grantee view; chỉ copy mã còn hiệu lực, phát sinh từ thao tác người dùng. Nếu mã sắp hết hạn cần lấy mã mới trước copy. Clipboard bị trình duyệt từ chối thì thông báo và cho chọn mã thủ công; không báo thành công giả.
- **Edit** — owner; sửa issuer/account/label và TOTP parameters. Secret hiện hữu không preload về form; để trống trường replacement nghĩa là giữ nguyên. Thay secret cần PIN lại và cảnh báo thay đổi tác động tới người đang được share. Save gọi `entries.update`; chỉ cập nhật grid sau server xác nhận.
- **Share** — owner; nhập đúng username, `shares.resolve-recipient` chỉ trả thông tin tối thiểu của local user đã khởi tạo app. Hiển thị người nhận và quyền View codes để xác nhận rồi `shares.add`. Không autocomplete danh sách mọi DSM user; không share bản thân hoặc tạo share trùng.
- **Revoke** — owner trong Share dialog; hiển thị người nhận, xác nhận rồi `shares.remove`. Cảnh báo mã đã cấp còn hiệu lực tới hết chu kỳ. Chỉ bỏ share khỏi danh sách sau response thành công.
- **Reveal secret** — owner; PIN lại qua server rồi `entries.reveal`. Hiển thị có chủ đích, tự che sau 30 giây và khi dialog đóng/app khóa. Không preload, không cho grantee dùng endpoint này.
- **Delete** — owner; dialog nêu issuer/account và số người nhận share bị ảnh hưởng. Confirm gọi `entries.delete`, cascade shares trong transaction; không xóa optimistic trước server xác nhận. MVP không có undo/trash.
- Grantee không thấy Edit/Share/Revoke/Reveal/Delete/Export entry; gọi API trực tiếp vẫn phải bị từ chối.

### 8.4. Dialog và dữ liệu nhập

- **Setup PIN**: PIN/confirm PIN, policy và cảnh báo không có reset tự động; chỉ tạo sau server xác minh chưa có PIN. Không cho setup ghi đè PIN hiện tại.
- **Unlock**: PIN, Unlock; Enter submit, hiển thị cooldown từ server, disable submit trong request/cooldown. Không lưu PIN ở browser storage.
- **Change PIN**: current/new/confirm; thành công revoke các unlock sessions và đưa app về Unlock.
- **Entry form**: issuer, account, label, secret Base32; Advanced gồm SHA1/SHA256/SHA512, digits 6/8, period 15–300 giây. Mặc định SHA1/6/30. Validate client để hỗ trợ UX, server là nguồn quyết định cuối cùng.
- **Import preview**: hiển thị issuer/account và trạng thái new/duplicate/error, không hiển thị secret. Token preview ngắn hạn gắn session/user/digest input; dữ liệu nhạy cảm chỉ giữ trong memory giới hạn hoặc encrypted staging riêng, không plaintext file. Confirm chỉ dùng đúng input đã preview, validate lại trong transaction; Cancel/lock/expiry dọn staging. Giới hạn upload/KDF/count áp dụng cả preview.
- **Export**: nút Export chỉ bật khi phạm vi hợp lệ, PIN và password xác nhận hợp lệ. Password/PIN không đưa vào query string/log hoặc lưu browser storage. Dọn input nhạy cảm và thu hồi Blob URL sau download; không cam kết xóa bản tải về hay clipboard.
- Các dialog có Cancel; đóng form đang sửa yêu cầu xác nhận bỏ thay đổi. Lock/session expiry luôn ưu tiên dọn dữ liệu, không bị chặn bởi dialog unsaved changes.

### 8.5. Trạng thái, lỗi và accessibility

- Empty My OTPs có Add/Import; empty Shared with me giải thích chưa có entry được share; no search results có Clear search.
- Loading/saving hiển thị tiến trình và disable nút gửi lặp. Mutation không tự retry mù khi timeout; reconcile trạng thái server trước khi cho gửi lại, dùng request ID/idempotency cho create/import.
- Session hết hạn: dọn grid/dialog nhạy cảm và về Unlock; session DSM hết hạn yêu cầu đăng nhập lại DSM, không thu password DSM trong app.
- Mất kết nối: báo trạng thái offline, dừng coi mã cũ là hợp lệ khi hết hạn, disable Copy khi không xác nhận được mã còn hiệu lực. Không cache để dùng offline ở browser.
- Share bị thu hồi/entry bị xóa: dọn mã/entry ở lần xác minh kế tiếp; lỗi stale update không ghi đè âm thầm. Dùng revision/updated version để phát hiện concurrent edits và yêu cầu reload.
- Error message thân thiện, không raw stack trace/secret; thông báo kết quả bằng text, không chỉ màu. Label rõ cho input/nút icon, keyboard navigation, focus đầu dialog và trả focus khi đóng.

### 8.6. Acceptance criteria UI

QA phải đi hết mỗi action ở trạng thái owner/grantee/locked/expired, kiểm tra nút ẩn/disable và API denial tương ứng. Bắt buộc test double-submit, response đảo thứ tự khi search, clipboard failure, network timeout, close/reopen, import preview khác confirm, khóa khi reveal/export và quyền bị thu hồi giữa thao tác.

## 9. Packaging và lifecycle

- Package chạy non-root; tài nguyên đặc quyền qua resource worker được hỗ trợ. Không sửa cấu hình DSM toàn cục để ép CGI chạy root.
- INFO generated từ template: package/displayname/version/arch/os_min_ver/maintainer/support_url nhất quán; không dùng metadata deprecated.
- Dependencies đóng gói offline; không đóng gói interpreter, không pip install/download/compiler trên NAS. RPATH/shared libraries riêng được cô lập khỏi hệ thống.
- Install tạo data/key/schema với quyền tối thiểu; setup vault yêu cầu DSM identity hợp lệ.
- Start chạy self-test runtime/key/schema rồi enable API; stop disable API và revoke sessions. Không báo running chỉ vì directory tồn tại.
- Upgrade quiesce writes, dùng SQLite backup API hoặc shutdown nhất quán; DB/DEK backup cùng bộ, migrations transaction và có rollback được test.
- Persistent data dùng cơ chế DSM đã xác minh; không copy raw DB đang ghi hoặc giả định var luôn sống qua uninstall.
- Uninstall cảnh báo export trước, xác nhận xóa dữ liệu rõ ràng và cleanup package files/processes; không tự thực hiện thử nghiệm phá dữ liệu trên NAS thật.

## 10. CI và phát hành

Matrix mục tiêu: x86_64, ARMv8/aarch64, ARMv7. Mapping build target chính thức được khóa ở compatibility gate; ARMv7 phải tách platform khi loader/libc/ABI khác. Không bao gồm x86 32-bit, ARMv5, PowerPC trong đợt đầu.

- Pin source revisions/checksums/toolchain và actions theo SHA; không dùng binary Ubuntu host làm runtime NAS.
- `ci.yml`: PR/push main và manual dispatch; lint Python/JS/shell, unit/integration tests, matrix test Python 3.8–3.14 và cross-build dependency theo CPU/Python ABI, ELF/loader/library checks, SPK metadata/permission/layout checks.
- Cache theo target/toolchain/dependency hashes; build release phải có thể tái tạo từ commit và lock manifest.
- Artifact: `OTPManager-<version>-<target>.spk`, SHA256SUMS, compatibility manifest và license/dependency inventory.
- `release.yml`: tag dạng `v1.0.0-001`, phải khớp INFO và build number tăng dần. Chạy lại toàn bộ gate; chỉ tạo draft GitHub Release khi tất cả target bắt buộc pass.
- Mặc định `contents: read`; write chỉ ở job tạo release. Không dùng `pull_request_target` để chạy code PR, không đưa NAS credentials vào CI, không auto-deploy.
- Draft chỉ được publish sau QA DSM đủ matrix. QEMU bổ sung smoke test CPU, không thay thế NAS/DSM tests.
- Init repo kiểm tra remote trước khi tạo branch, không force-push. Track plan chính, ignore artifacts/runtime data/secrets; không ignore toàn bộ `.cursor/` làm mất plan.

## 11. Kiểm thử bắt buộc

- RFC 6238 vectors cho cả ba algorithms; boundary time, period, digits, parser/serializer Unicode và URI round-trip.
- AES-GCM tamper/wrong-key/AAD rejection, nonce handling, KDF limits và backup round-trip.
- Hai user thường và một user không được cấp quyền: isolation, IDOR, share/revoke, secret/export denial, account recreation và disabled account.
- CSRF, XSS metadata, expired DSM session, PIN lockout/restart, polling không gia hạn idle, close/reopen và stop enforcement.
- Import duplicate/error rollback, concurrent writes, SQLite busy, disk full, migration failure, missing DEK và restore sau upgrade.
- Lifecycle install/start/stop/restart/upgrade/uninstall/offline install, file permissions, AppArmor/system logs và Security Advisor/Antivirus.
- Ma trận test DSM 7.0/7.1 và DSM mới hơn trên mỗi platform công bố. Thiếu thiết bị test phải ghi chưa verify và chặn release target đó, không suy từ một NAS sang toàn matrix.

## 12. Publish Package Center

Tên OTPManager là tên đã chọn, chưa được Synology xác nhận/reserve. Free không đồng nghĩa open-source; license dự án cần chủ sở hữu chọn trước public release. Không tự chấp nhận thỏa thuận pháp lý hoặc submit thay người dùng.

Chuẩn bị SPK/checksums, description/changelog, screenshots dùng dữ liệu giả, manual/test scenarios, compatibility matrix, website/support email, privacy statement, dependency licenses và security maintenance policy. Mô tả rõ đây là TOTP vault, không phải tính năng bật 2FA đăng nhập DSM.

Theo guideline hiện tại: apply developer, chấp nhận Distribution Agreement/Guideline, submit package, Synology review scripts và chức năng trên DSM/model, sửa theo feedback, sau đó mới publish. Không cam kết được duyệt hoặc thời hạn. Free không chuyển sang Paid theo guideline đã tra.

Nguồn:

- [DSM Developer Guide](https://help.synology.com/developer-guide/)
- [Application authentication](https://help.synology.com/developer-guide/integrate_dsm/web_authentication.html)
- [Package INFO](https://help.synology.com/developer-guide/synology_package/INFO_necessary_fields.html)
- [Submission](https://help.synology.com/developer-guide/publish_package/summit_package_for_approval.html)
- [Publication checklist](https://help.synology.com/developer-guide/appendix/publication_review.html)
- [Developer application](https://www.synology.com/en-global/support/developer#apply)
- [Distribution agreement](https://www.synology.com/en-us/company/legal/Pkg_Center_Dev_Distri_Agreement)
- [Python version lifecycle](https://devguide.python.org/versions/)
- [DSM release notes — runtime hệ thống](https://www.synology.com/en-global/releaseNote/DSM)

## 13. Phạm vi và trạng thái

MVP gồm native UI, TOTP CRUD/search, PIN, share view, plain/encrypted backup, multi-platform SPK và CI. Không gồm HOTP, QR camera, cloud sync, share manage, public sharing, LDAP/domain, tự động reset PIN hoặc deploy NAS từ CI.

Đây là kế hoạch đã hợp nhất, không còn bản nháp cũ hoặc quyết định noarch. Chưa implement, cài dependency, kết nối NAS, commit/push hay submit marketplace. Bước thực thi đầu tiên là compatibility gate; bản patch/runtime dependency chính xác chỉ được khóa từ bằng chứng build và security review, không bịa phiên bản để điền kế hoạch.
