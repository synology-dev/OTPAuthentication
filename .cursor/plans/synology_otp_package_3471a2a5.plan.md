---
name: Synology OTPManager Package
overview: "OTP Manager: native ExtJS, auto-detected DSM system Python, per-CPU/ABI dependencies, per-user vault, PIN, share, backup; GitHub Actions build and Free publish prep."
isProject: true
todos:
  - id: compatibility
    content: "Verify DSM integration, DSM system Python/crypto/toolchain, and platform matrix before implementing the vault"
    status: pending
  - id: repository
    content: "Initialize repo, keep the main plan, configure reproducible build and lock dependencies"
    status: pending
  - id: backend
    content: "Backend: DSM identity, SQLite, encryption, PIN/session, ACL, TOTP, and tests"
    status: pending
  - id: ui
    content: "Native ExtJS: unlock, CRUD, search, codes, share, and backup/restore"
    status: pending
  - id: lifecycle
    content: "SPK lifecycle, migration, consistent backup, stop enforcement, and safe uninstall"
    status: pending
  - id: ci
    content: "GitHub Actions: lint/tests, cross-build matrix, validation, checksums, and release"
    status: pending
  - id: verification
    content: "DSM testing per platform, two regular users, and one user without app privilege"
    status: pending
  - id: publication
    content: "Finish docs, license, privacy, screenshots, and Free publish package"
    status: pending
---

# OTP Manager — implementation and release plan

## 1. Decisions locked in

- Single canonical copy: [.cursor/plans/synology_otp_package_3471a2a5.plan.md](synology_otp_package_3471a2a5.plan.md). Commit this file.
- Repository: [synology-dev/OTPManager](https://github.com/synology-dev/OTPManager), SSH remote `git@github.com:synology-dev/OTPManager.git`.
- Package ID `OTPManager`; display name `OTP Manager`; namespace `SYNO.SDS.OTPManager.Application`.
- Native desktop ExtJS UI; do not switch to WebStation portal or iframe SPA.
- Backend uses **DSM system Python 3**, no hard-coded minor version, no bundled interpreter, and no requirement to install a separate Python package. Do not modify system site-packages. Broad support for versions verified by capability probe and CI; do not claim every Python is compatible.
- Drop `noarch`. CI builds for x86_64, ARMv8/aarch64, and ARMv7 groups; package by compatible platform/ABI.
- Target DSM 7.0/7.1 and above. Only publish DSM/model/platform combinations that have been verified; do not claim every DSM 7.x NAS is supported.
- Separate vault per DSM user; share individual entries with view-code permission. Publish **Free** on Package Center after tests pass and Synology approves.

## 2. DSM system Python constraints and release conditions

Do not treat the Python version as fixed per DSM. Synology manages the interpreter; the project manages its own dependencies and re-tests after DSM updates. Upstream EOL versions need vendor patch/advisory review; do not infer safe or unsafe from version alone.

- Source baseline is Python 3.8-compatible; CI targets Python 3.8–3.14. This is the intended test range, not a claim that DSM ships every version. No Python 2 support. Runtimes outside the verified range are rejected with a clear message; do not blind-run.
- Launcher probes interpreters at trusted system paths verified on DSM; do not use an arbitrary PATH. Probe version, architecture, sqlite3, ssl, hashlib, hmac, entropy, and crypto backend. Record the authenticated path in private config; revalidate on every start and after DSM upgrade; do not hard-code `python3.9`.
- Dependencies live in a package-private directory; no pip install on the NAS, no system Python edits, no user site-packages. Probe runs under the backend's real identity/environment.
- Native crypto must match CPU, libc, Python ABI, and OpenSSL linkage. Build dependency bundles per verified Python ABI group; use abi3 only when the library truly supports it. Lock the manifest to choose a bundle by runtime and fail closed if none matches. A CPU-based SPK is not enough for every Python minor.
- Python 3.8-compatible syntax does not guarantee crypto libraries still support 3.8. Do not force EOL dependencies only to widen the matrix; a target that fails the security gate is a blocker that must be reported.
- Choose Python `cryptography` for AES-256-GCM. This is a new dependency that must be approved by the user before implementation/install; do not auto-install during the plan phase.
- Check `cryptography` version, Rust build toolchain, and OpenSSL compatibility with DSM system Python, libc, and target CPU. Do not pin an arbitrary old version just to make the build pass; review advisories and support sources.
- CI includes vulnerability and license scans for runtime and native dependencies. Do not release while applicable critical vulnerabilities remain unaddressed or without an accepted patch-support plan.
- If no safe, buildable runtime/crypto set is found, stop before implementation and report the blocker; do not silently change Python, shrink DSM support, or substitute hand-rolled crypto.
- Do not use `openssl enc` as an AES-GCM fallback, do not write AES yourself, and do not copy crypto implementations of unclear provenance.

## 3. Early phase: compatibility and DSM integration

Do this before building the real vault; use synthetic data only:

1. Confirm DSM version, model, CPU/ABI, and test environment via separately granted access; do not put NAS host/user/port/password in the repo.
2. Build a minimal test SPK with icon and AppWindow; verify opening the app as a regular user. Verify real ExtJS/API on each DSM; do not treat community examples as a compatibility commitment.
3. Authenticate the DSM session from custom CGI via Synology-documented mechanisms; confirm helper, CGI environment, logout, disabled account, and application privilege.
4. Measure real CGI UID/GID and data read/write permissions. `conf/privilege` alone does not prove CGI runs as the package user. Do not “fix” with root, setuid, or world-readable chmod; missing a safe permission model is a blocker.
5. Verify user identity API/source and delete/recreate account lifecycle. MVP supports local DSM users; do not unilaterally expand to LDAP/domain.
6. Probe available Python; cross-build crypto dependencies for the matching CPU/Python ABI; verify SQLite, SSL, entropy, AES-GCM round-trip, and tamper rejection on the NAS. Do not build or install an interpreter.
7. Map CPU groups to official platform/toolchain; lock minimum DSM and `arch` metadata from results.

Pass criteria: UI/CGI works with correct privileges, trusted identity, offline runtime/crypto, and at least one target with real integration evidence. Other targets must pass the same verification before a full release.

## 4. Architecture and repo layout

ExtJS frontend calls same-origin JSON CGI at `/webman/3rdparty/OTPManager/webapi/`. CGI authenticates DSM, checks app privilege, package state, unlock session, and ACL before data access.

Expected paths:

- `package/ui/OTPManager.js`: AppInstance/AppWindow, dialogs, countdown, and client API.
- `package/ui/config`: app registration and privilege per the compatibility-spike verified mechanism.
- `package/ui/webapi/`: thin CGI entry points; no keys/DB or sensitive source downloadable over HTTP.
- `package/backend/`: auth, sessions, storage, crypto, TOTP, URI parser, share, and backup.
- `package/deps/`: per-CPU/Python ABI dependency bundles; manifest and launcher select a verified bundle. No Python interpreter.
- `spk/INFO.in`, `spk/conf/privilege`, `spk/conf/resource`, `spk/scripts/`: metadata and lifecycle.
- `build.sh`, `build/`: cross-build, dependency lock/checksum, platform mapping, and SPK validator.
- `tests/`: unit, authorization/integration, and synthetic fixtures.
- `.github/workflows/ci.yml`, `.github/workflows/release.yml`: test and build/release.
- `docs/`: user guide, build, security model, compatibility, and submission checklist.

Data lives outside the web root in the DSM-managed persistent package data directory, accessed via `/var/packages/OTPManager/var` after lifecycle verification. Directory mode 0700, DB/key mode 0600; only the backend identity may access.

## 5. Security model

### At-rest encryption

- One 256-bit package DEK from a CSPRNG; each entry encrypted with AES-256-GCM using a fresh 96-bit nonce on write and a 128-bit tag.
- AAD binds schema version, entry ID, and owner ID; do not allow ciphertext swaps across entry/owner.
- PIN is an app access lock, **not the DEK decryption key**. Per-user is application authorization, not cryptographic isolation from root.
- Anyone with both DB and DEK can decrypt. Do not advertise zero-knowledge or protection from the NAS admin.
- Do not send secrets to share recipients; the owner only receives a secret via reveal/export with PIN re-confirm.
- Missing key while DB already exists: fail closed; never mint a new key and overwrite data.

### PIN and sessions

- Numeric PIN minimum 6, maximum 12 digits; UI recommends a longer PIN. Store salted PBKDF2-HMAC-SHA256 with versioned parameters; benchmark on the weakest NAS and review current guidance before locking parameters.
- Persist failed-attempt limits per user with escalating backoff and cooldown after 5 failures; counter updates must be atomic.
- 32-byte random token; store only the hash in the DB; bind user, app instance, and DSM session. Do not put the token in localStorage or the URL.
- Idle timeout 15 minutes, absolute lifetime 8 hours. Only user interaction extends the session; polling does not.
- Lock, change PIN, and package stop revoke sessions. Window close revokes best-effort; server expiry remains mandatory. Expired/logged-out/disabled DSM sessions must be rejected on the next request.
- Changing PIN requires the current PIN. MVP has no automatic PIN bypass/reset; docs must say so before setup. An exported backup can be imported into a new valid vault with the backup password.

### API hardening

- Every API, including list/search/metadata, requires unlock except status/setup/unlock after DSM authentication.
- Enforce permissions on the backend per entry; do not trust client-supplied username/owner.
- State changes only via POST; CSRF token bound to session; Origin checked against a trusted-origin config; a custom header alone is not enough.
- HTTPS is an operational requirement; sensitive responses use `Cache-Control: no-store`; escape metadata in the UI; parameterized SQL.
- Limit request/upload/batch size; validate schema/type; never log secrets, OTP, PIN, backup password, token, cookie, or DEK.

## 6. Data, TOTP, and share

SQLite with schema version, foreign keys, transactions, and busy timeout. Tables:

- `users`: internal ID, DSM identity binding, display username, PIN hash/salt/parameters, status.
- `entries`: ID, owner ID, issuer, account, label, algorithm, digits, period, ciphertext/nonce/tag, and timestamps.
- `shares`: entry ID, grantee ID, timestamps; unique entry/grantee. MVP is view-only.
- `sessions`: token hash, owner/session binding, idle/absolute expiry, and revocation.
- `pin_attempts`: durable per-user counter/cooldown.
- `schema_migrations`, package enabled state, and security event metadata contain no secrets.

DSM identity must detect deleted/recreated accounts; username or UID reuse alone must not reattach a vault. Cases without proven continuity fail closed and need explicit handling, not auto-remap.

TOTP supports SHA1/SHA256/SHA512, 6 or 8 digits, integer period 15–300 seconds; defaults SHA1/6/30. Out-of-range URIs error; do not silently rewrite parameters. HOTP is out of MVP.

- Owner: CRUD, view codes, share/revoke, reveal/export after PIN re-confirm.
- Recipient: view metadata and current code; no edit/delete/share/reveal/export secret.
- ACL revoke is checked every request. Codes already shown cannot be revoked retroactively and remain valid until the period ends.
- Share only with a local DSM user who has initialized OTP Manager; exact username entry and server check; do not expose the full account list.
- Case-insensitive search on issuer/account/label within the allowed entry set only; pagination and batch limits.

## 7. Backup / restore

### Plaintext

One `otpauth://totp/` URI per line; percent-encode issuer/account correctly; export `secret`, `issuer`, and non-default algorithm/digits/period. Do not put real secrets in tests or docs.

Export owned entries only. Clearly warn that the file contains 2FA keys; require PIN re-entry; download directly; do not store temporary plaintext on the NAS.

### Encrypted

- JSON file with format version, cipher, KDF identifier/parameters, salt, nonce, and base64 ciphertext/tag.
- AES-256-GCM; key derived from a backup password independent of the PIN via PBKDF2-HMAC-SHA256; parameters locked after benchmark/security review at the compatibility gate.
- Salt at least 16 bytes, nonce 12 bytes, tag 16 bytes; authenticate the header with canonical AAD.
- Versioned JSON payload holds metadata and TOTP parameters; no PIN, sessions, DEK, or share ACLs.
- V1 limits: 10 MiB file, 10,000 entries; KDF parameters must stay within allowed profiles to resist DoS. Wrong password, bad tag, or unsupported format: reject entirely.

### Import

Preview and validate everything before committing the transaction. Default merge; skip exact duplicates after normalization; same issuer/account with different secret becomes a separate entry with a warning. No replace in MVP. Any error must not leave a partial import; messages cite line/entry numbers, never echo secrets.

Personal backup restores into the logged-in owner; do not auto-restore shares. Full-package restore is a separate admin process with a consistent DB+DEK set.

## 8. UI and API

Native UI includes UnlockDialog, Owned/Shared lists, search, CRUD, share/revoke, backup/restore, and Lock. Do not use newer ExtJS `Ext.create` in ExtJS 3 target code.

API groups:

- `pin`: status/setup/unlock/change/lock.
- `entries`: list/create/update/delete/reveal.
- `codes`: batch codes, server time, and expiry.
- `shares`: list/add/remove/resolve-recipient.
- `backup`: export/import plain and encrypted, preview/confirm.

Client countdown uses server time. Fetch on period boundaries; do not call CGI every second. Stop polling when hidden/locked; on return, check session before display. Clear codes/tokens from the UI on lock; clipboard copy requires a user gesture and does not promise automatic clipboard clear.

### 8.1. Navigation and lists

- **My OTPs**: default after unlock; owned entries only. Grid: issuer, account, label, code, countdown, share status, and actions.
- **Shared with me**: shared entries, plus owner column; view/copy code only.
- **Settings**: Change PIN; idle timeout 15 minutes and absolute timeout 8 hours read-only in MVP; About shows app version and detected DSM/Python, not sensitive paths/keys.
- **Lock** always on the toolbar when unlocked. Do not show entries, metadata, or search results behind the PIN screen.
- Search within the current tab on issuer/account/label, 300 ms debounce, reset pagination on query change; drop stale late responses. Clear search and pagination available.
- Multi-row select is for export on My OTPs only; MVP has no bulk delete/share.

### 8.2. Toolbar and action contract

Action names below are the expected internal contract, not a built-in DSM API. Every action checks session/ACL on the server at execution time.

- **Add OTP** — My OTPs; open form, Manual or Paste URI. URI preview does not persist; Save calls `entries.create`; success adds the entry and closes the dialog; errors keep the form without echoing secrets.
- **Import** — My OTPs; plaintext/encrypted file, password for encrypted. Preview calls `backup.preview`; Confirm Import enables only when all input is valid, calls `backup.confirm`, returns added/skipped counts, and refreshes the list.
- **Export** — My OTPs; scope Selected or All owned; default Selected when a selection exists, otherwise All owned. All does not mean current page or search results. Default encrypted; require password and confirm password. Plaintext has a separate warning and confirm checkbox. Both require PIN re-entry; server reauthorizes the full entry set before export and must not silently export a partial set when rights/data changed.
- **Lock** — call `pin.lock` and clear the UI immediately. If the network is down, still lock locally; do not claim server revoke succeeded; server token expires per policy. Do not wait on the network before hiding secrets.
- **Refresh** — reload the current tab’s list/permissions and codes; do not auto-unlock or extend the session merely because of background refresh.

### 8.3. Per-entry actions

- **Copy code** — owner or view grantee; copy only a still-valid code from a user gesture. If the code is about to expire, fetch a new one before copy. If the browser denies clipboard, notify and allow manual selection; never fake success.
- **Edit** — owner; edit issuer/account/label and TOTP parameters. Existing secret is not preloaded; leaving the replacement field empty keeps it. Changing the secret requires PIN re-entry and a warning that current share recipients are affected. Save calls `entries.update`; update the grid only after server confirmation.
- **Share** — owner; exact username; `shares.resolve-recipient` returns minimal info for a local user who has initialized the app. Show recipient and View codes permission for confirm, then `shares.add`. No autocomplete of every DSM user; no self-share or duplicate share.
- **Revoke** — owner in Share dialog; show recipient, confirm, then `shares.remove`. Warn that already-issued codes remain valid until the period ends. Remove from the list only after a successful response.
- **Reveal secret** — owner; PIN re-entry via server then `entries.reveal`. Intentional display; auto-hide after 30 seconds and on dialog close/app lock. No preload; grantees cannot use this endpoint.
- **Delete** — owner; dialog states issuer/account and how many share recipients are affected. Confirm calls `entries.delete`, cascades shares in a transaction; no optimistic delete before server confirmation. MVP has no undo/trash.
- Grantees do not see Edit/Share/Revoke/Reveal/Delete/Export entry; direct API calls must still be denied.

### 8.4. Dialogs and input

- **Setup PIN**: PIN/confirm PIN, policy, and warning that there is no automatic reset; create only after the server verifies no PIN exists. Setup must not overwrite an existing PIN.
- **Unlock**: PIN, Unlock; Enter submits; show server cooldown; disable submit during request/cooldown. Do not store PIN in browser storage.
- **Change PIN**: current/new/confirm; on success revoke unlock sessions and return the app to Unlock.
- **Entry form**: issuer, account, label, Base32 secret; Advanced includes SHA1/SHA256/SHA512, digits 6/8, period 15–300 seconds. Defaults SHA1/6/30. Client validation for UX; server is the final authority.
- **Import preview**: show issuer/account and new/duplicate/error status, never the secret. Short-lived preview token bound to session/user/input digest; sensitive data only in limited memory or separate encrypted staging, not a plaintext file. Confirm must use exactly the previewed input and re-validate in a transaction; Cancel/lock/expiry clears staging. Upload/KDF/count limits apply to preview too.
- **Export**: Export button enables only when scope, PIN, and password confirmation are valid. Do not put password/PIN in query string/logs or browser storage. Clear sensitive inputs and revoke Blob URLs after download; do not promise to erase the downloaded file or clipboard.
- Dialogs have Cancel; closing a dirty form asks to discard changes. Lock/session expiry always clears data first and is not blocked by unsaved-change dialogs.

### 8.5. State, errors, and accessibility

- Empty My OTPs offers Add/Import; empty Shared with me explains no shared entries yet; no search results offers Clear search.
- Loading/saving shows progress and disables repeat submit. Mutations do not blind-retry on timeout; reconcile server state before resubmit; use request ID/idempotency for create/import.
- Session expired: clear sensitive grid/dialogs and return to Unlock; expired DSM session requires DSM login again; do not collect the DSM password in-app.
- Offline: show offline status; stop treating old codes as valid past expiry; disable Copy when validity cannot be confirmed. No offline browser cache.
- Share revoked/entry deleted: clear code/entry on the next verification; stale update errors must not silently overwrite. Use revision/updated version to detect concurrent edits and require reload.
- Friendly error messages, no raw stack traces/secrets; result feedback is textual, not color-only. Clear labels for inputs/icon buttons, keyboard navigation, initial dialog focus, and restore focus on close.

### 8.6. UI acceptance criteria

QA must walk every action as owner/grantee/locked/expired, checking hidden/disabled buttons and matching API denial. Required tests: double-submit, out-of-order search responses, clipboard failure, network timeout, close/reopen, import preview differing from confirm, lock during reveal/export, and rights revoked mid-action.

## 9. Packaging and lifecycle

- Package runs non-root; privileged resources via supported resource workers. Do not rewrite global DSM config to force CGI as root.
- INFO generated from a template: package/displayname/version/arch/os_min_ver/maintainer/support_url consistent; no deprecated metadata.
- Dependencies packaged offline; no interpreter packaging, no pip install/download/compiler on the NAS. Private RPATH/shared libraries isolated from the system.
- Install creates data/key/schema with least privilege; vault setup requires a valid DSM identity.
- Start runs runtime/key/schema self-test then enables the API; stop disables the API and revokes sessions. Do not report running merely because a directory exists.
- Upgrade quiesces writes; use SQLite backup API or consistent shutdown; DB/DEK backed up together; migrations are transactional with tested rollback.
- Persistent data uses the verified DSM mechanism; do not copy a live DB mid-write or assume var always survives uninstall.
- Uninstall warns to export first, confirms data deletion clearly, and cleans package files/processes; do not run destructive data experiments on a real NAS unprompted.

## 10. CI and release

Target matrix: x86_64, ARMv8/aarch64, ARMv7. Official build-target mapping is locked at the compatibility gate; ARMv7 must split platforms when loader/libc/ABI differ. First wave excludes 32-bit x86, ARMv5, and PowerPC.

- Pin source revisions/checksums/toolchain and actions by SHA; do not use Ubuntu host binaries as NAS runtime.
- `ci.yml`: PR/push main and manual dispatch; lint Python/JS/shell, unit/integration tests, Python 3.8–3.14 matrix and cross-build dependencies per CPU/Python ABI, ELF/loader/library checks, SPK metadata/permission/layout checks.
- Cache by target/toolchain/dependency hashes; release builds must be reproducible from commit and lock manifest.
- Artifacts: `OTPManager-<version>-<target>.spk`, SHA256SUMS, compatibility manifest, and license/dependency inventory.
- `release.yml`: tags like `v1.0.0-001`, must match INFO and increasing build numbers. Re-run the full gate; create a draft GitHub Release only when all required targets pass.
- Default `contents: read`; write only on the release-creating job. Do not use `pull_request_target` to run PR code; do not put NAS credentials in CI; no auto-deploy.
- Draft is published only after DSM QA across the matrix. QEMU adds CPU smoke tests; it does not replace NAS/DSM tests.
- Repo init checks the remote before creating branches; no force-push. Track the main plan; ignore artifacts/runtime data/secrets; do not ignore all of `.cursor/` and lose the plan.

## 11. Mandatory testing

- RFC 6238 vectors for all three algorithms; boundary time, period, digits, Unicode parser/serializer, and URI round-trip.
- AES-GCM tamper/wrong-key/AAD rejection, nonce handling, KDF limits, and backup round-trip.
- Two regular users and one user without app privilege: isolation, IDOR, share/revoke, secret/export denial, account recreation, and disabled account.
- CSRF, metadata XSS, expired DSM session, PIN lockout/restart, polling does not extend idle, close/reopen, and stop enforcement.
- Import duplicate/error rollback, concurrent writes, SQLite busy, disk full, migration failure, missing DEK, and restore after upgrade.
- Lifecycle install/start/stop/restart/upgrade/uninstall/offline install, file permissions, AppArmor/system logs, and Security Advisor/Antivirus.
- DSM 7.0/7.1 and newer DSM test matrix on every published platform. Missing test hardware must be marked unverified and block that target’s release; do not extrapolate from one NAS to the whole matrix.

## 12. Package Center publish

The OTPManager name is chosen but not Synology-confirmed/reserved. Free does not mean open-source; the project license must be chosen by the owner before public release. Do not unilaterally accept legal agreements or submit on the user’s behalf.

Prepare SPK/checksums, description/changelog, screenshots with fake data, manual/test scenarios, compatibility matrix, website/support email, privacy statement, dependency licenses, and security maintenance policy. Clearly describe this as a TOTP vault, not DSM login 2FA enablement.

Per current guidelines: apply as developer, accept Distribution Agreement/Guideline, submit package, Synology reviews scripts and function on DSM/model, fix per feedback, then publish. Do not promise approval or timeline. Free does not convert to Paid under the reviewed guideline.

Sources:

- [DSM Developer Guide](https://help.synology.com/developer-guide/)
- [Application authentication](https://help.synology.com/developer-guide/integrate_dsm/web_authentication.html)
- [Package INFO](https://help.synology.com/developer-guide/synology_package/INFO_necessary_fields.html)
- [Submission](https://help.synology.com/developer-guide/publish_package/summit_package_for_approval.html)
- [Publication checklist](https://help.synology.com/developer-guide/appendix/publication_review.html)
- [Developer application](https://www.synology.com/en-global/support/developer#apply)
- [Distribution agreement](https://www.synology.com/en-us/company/legal/Pkg_Center_Dev_Distri_Agreement)
- [Python version lifecycle](https://devguide.python.org/versions/)
- [DSM release notes — system runtime](https://www.synology.com/en-global/releaseNote/DSM)

## 13. Scope and status

MVP includes native UI, TOTP CRUD/search, PIN, view share, plain/encrypted backup, multi-platform SPK, and CI. Out of scope: HOTP, QR camera, cloud sync, share manage, public sharing, LDAP/domain, automatic PIN reset, or deploying to NAS from CI.

This is the consolidated plan; no older drafts or noarch decisions remain. Not yet implemented, dependencies not installed, NAS not connected, no commit/push or marketplace submit. First execution step is the compatibility gate; exact patch/runtime dependency versions are locked only from build evidence and security review, not invented to fill the plan.
