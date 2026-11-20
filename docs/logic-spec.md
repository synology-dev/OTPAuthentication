# OTP Authentication — logic specification (UI / behavior)

Living document for test/verify. Update when requirements or behavior change.
Current UI labels are mostly English (matching the app).

## 1. Vault & PIN

Model: **PIN = UI/API lock** (grants unlock session). OTP ciphertext uses package DEK — forgetting the PIN does not lose data.

| ID | Behavior | Test notes |
|----|----------|------------|
| V1 | Vault has PIN: open app → show **Unlock OTP Authentication** popup immediately (no need to click Import/Add first) | First open in session |
| V2 | Close app (X): **do not** show Unlock again | After unlock, or while Unlock is showing then X |
| V3 | Unlock has **Cancel** and **Unlock** buttons | Cancel closes dialog; vault stays locked |
| V4 | Setup PIN (first time) has Cancel + primary action (**Create PIN**) | PIN is **optional** |
| V4b | **Cancel** (or close X) on Set up PIN when no PIN yet → treat as **no PIN** (`pin_disabled` + unlock session): dismiss “Checking vault status…”, **enable** Add / Import / Export; later opens must not stick on Checking | Creating a PIN is not required |
| V5 | Toolbar: vault **locked** → label **Unlock**; vault **open** → label **Lock** | Cancel Unlock → must stay Unlock |
| V5b | **No PIN** (never set up / disabled) → **hide** Lock/Unlock button | Show again when PIN is enabled/set up |
| V11 | After **Setup PIN** / re-enable PIN → **show** button; after empty New PIN (disable) or **Remove PIN protection** → **hide** | |
| V6 | Click **Unlock** (toolbar) → open Unlock dialog; click **Lock** → lock vault | |
| V7 | **Forgot PIN** on Unlock dialog | See §2 |
| V8 | Close Unlock via Cancel: main window stays open; do not auto-reopen Unlock | |
| V9 | **Empty New PIN** (Change PIN / new PIN field) = **disable PIN**; keep OTP entries | PIN need not always be set |
| V10 | Non-empty PIN still 6–12 digits; empty is valid only when it means disable | |
| V12 | **No PIN**: vault unlock API errors (`locked` / `invalid_token`) or HTTP 401 on poll/refresh → **do not** open Unlock PIN popup; retry `open_nopin`. Dead DSM session (`unauthorized` / bare 401) → status “DSM session expired — reload…”, **no** Unlock | Idle tab / `codes.cgi` 401; distinguish vault-locked vs DSM session vs package stop |
| V12b | Before showing **Unlock OTP Authentication**, re-check `pin.status` on the server. If `pin_set` is false, never show Unlock — use `open_nopin` (when `pin_disabled`) or Set up PIN. Client `pinConfigured` alone must not open Unlock (stale after idle / PIN removed) | OM-52; both NAS |

## 2. Forgot PIN (decided)

| ID | Behavior |
|----|----------|
| F1 | Unlock has a **Forgot PIN** button |
| F2 | Click Forgot PIN → require current user's **DSM password** |
| F3 | Wrong password → show error, no reset; rate-limit (`pin_attempts`) |
| F4 | Correct password → two choices: **Remove PIN protection** / **Set a new PIN** |
| F5 | PIN only protects UI/API actions (session unlock). **Do not wipe** OTP entries/shares on Forgot PIN |
| F6 | Remove PIN protection → clear PIN, `pin_disabled`, allow app use without PIN; **keep** OTP |
| F7 | Set a new PIN → drop old PIN / Setup new PIN; **keep** OTP |
| F8 | DSM auth via `SYNO.Core.User.PasswordConfirm` (auth v2), forward session Cookie/`_sid` |

## 3. Import

| ID | Behavior |
|----|----------|
| I1 | Import while vault locked: **do not** only show bare "Vault is locked" — open Unlock (or equivalent) |
| I2 | **Confirm import** works **without requiring Preview** first |
| I3 | Duplicate entry by **issuer + account** (same owner) |
| I4 | Conflict UI: **Override** / **Skip** / **Override All** / **Skip All** (+ Cancel) |
| I5 | Override updates existing entry; Skip skips; *All applies to the rest of the batch |
| I6 | Corrupt backup JSON / wrong encryption password / invalid otpauth → API `error.message` clear on dialog (not HTTP 500 / “Request failed (500)”) | DSM replaces CGI 500 body with HTML |
| I7 | otpauth path `Issuer:` (empty account after `:`) is valid if issuer (path and/or `issuer=`) is non-empty; store `account=""`. Still reject when both issuer and account are missing, or secret is missing |
| I8 | Import Content dialog: comfortable default width/height (dialog ~640, textarea ~220); vertical resize on real `<textarea>` actually changes height (not a decorative grip) | OM-35 |
| I9 | Import accepts **paste** into Content **and** choosing a `.txt` / `.json` file (client-side read → fill Content); same Preview / Confirm / conflict | OM-36; max ~2 MB |
| I10 | Auto-detect Content: plaintext/otpauth → **hide** Encryption password; encrypted backup (`format: otp-backup-v1`) → **show** + required on Preview/Confirm. Re-detect when Content changes (light debounce) and after file load | OM-37; mirror Export show/hide password |

## 4. Shared dialog / form

| ID | Behavior |
|----|----------|
| D0 | API errors: show `error.message` (fallback `error.code`); **do not** swallow as “Network error” when body has error JSON |
| D0b | Form action errors: show **on the open dialog/form**; main window status only for grid/app-level actions |
| D0c | Validation/dialog error text (`_dialogError`, API `error.message`, invalid): **red** `#d94841` (`--otp-warn`) under `.otpauthentication-dialog` |
| D1 | Every app popup has **Close** or **Cancel** (not only a primary button) |
| D2 | DSM 7 light skin: toolbar, grid, dialog (accent `#2481eb`) |
| D3 | No harsh black border; soft border `#d0d4d9` / soft shadow |
| D4 | Textarea (URI…) same width as sibling text input |
| D5 | Combo (Algorithm/Digits…): one block; trigger not misaligned / raised gray box |
| D6 | Input/combo tall enough (~32px), text not cramped |
| D7 | Dialog title not flush against header rule (padding ~16px to border) |
| D8 | Main screen: grid/toolbar/paging/status left–right inset ~14px (border `margins`), not flush to window edge | |
| D9 | Settings: Info Center rows — left label column + right value/control, aligned gutters; light horizontal separator between rows (no zebra). **Copy to Clipboard only**: label left, checkbox in value column | |

## 5. Grid / codes

| ID | Behavior |
|----|----------|
| G1 | Code column: monospace, prominent; live codes when unlocked |
| G2 | Time column: warning color when remaining is low (≤ 5s) |
| G3 | **No** “My OTPs” / “Shared with me” button/toggle — one combined list (owned + shared) |
| G4 | Click **Code** cell → copy TOTP to clipboard; short “Copied” feedback (status) | OM-18 |
| G5 | Settings checkbox **Copy to Clipboard only** (default **off**, per-user localStorage). On → mask CODE (`••••••`); cell click still copies real code + “Copied” | |
| G6 | Pagination like DSM Log Center: first/prev/page/next/last, Items per page (25/50/100/200, default 50), “N items”, refresh | API list offset/limit + total |
| G7 | Right-click grid: if row already in selection → **keep** multi-select; if not → select **only** that row | OM-49 |
| G8 | Context menu **Delete**: delete **all** selected owned entries (one confirm, **one** `ids` request); shared-with-me cannot be deleted; short status Deleted N / failed | OM-49; batch `entries.delete` + `ids` (keep single `id`) |
| G9 | Context menu multi-select (>1): hide Edit/Share/Reveal; still show Copy / Export / Delete (when any owned) | OM-49 |

## 6. Export

| ID | Behavior |
|----|----------|
| E1 | Export dialog **has no** vault PIN field |
| E2 | Every export (plain/enc) requires **DSM password** (re-auth `SYNO.Core.User.PasswordConfirm`) |
| E3 | Format **Encrypted**: show **Encryption password** + Confirm; empty → “Encryption password is required”; mismatch → separate message; **no** min length/complexity. Plaintext: **hide** both fields |
| E4 | Plaintext: show 2FA risk checkbox; Encrypted: hide checkbox |
| E5 | Needs unlock session + CSRF; wrong DSM password → error on dialog, no export |
| E6 | Plaintext checkbox: checkbox vertically aligned with first line of label text |
| E7 | Scope **Selected**: export selected **owned** entries (`ids`); ≥1 owned selected → dialog defaults to Selected; **0** selected (or only shared) → default **All owned**. Toolbar Export and context menu Export use the same dialog | OM-49 |

## 7. Package icon

| ID | Behavior |
|----|----------|
| P1 | Icon is not a flat color square; OTP/vault motif (shield + ticks + lock) |
| P2 | Rounded corners like DSM apps (Control Panel…), transparent outside corners |
| P3 | `spk/PACKAGE_ICON.PNG` (72), `PACKAGE_ICON_256.PNG` (256) + `package/ui/images/icon_*.png` |

## 8. Out of scope / not decided in this spec

- Recovery key / security questions (suggested; **not** chosen — chose Forgot PIN + DSM password).
- Share / backup UI polish beyond the shared skin.
- DSM user without app privilege → denied (separate smoke verification).

## Short decision history

- 2026-11-19: Unlock on open; Cancel on auth dialogs; no Unlock on close.
- 2026-11-19: Import Confirm without Preview; conflict Override/Skip/*All; duplicate issuer+account.
- 2026-11-19: Import otpauth `Issuer:` (empty account) accepted when issuer present; account stored as `""` (I7).
- 2026-11-19: OM-35/36/37 — Import textarea wide + real resize (I8); load `.txt`/`.json` (I9); auto show/hide Encryption password (I10).
- 2026-11-19: Toolbar Lock/Unlock follows vault state.
- 2026-11-19: Forgot PIN → DSM password → remove PIN or set new PIN (**no OTP wipe**; PIN only locks UI/API).
- 2026-11-19: DSM-style rounded icon corners.
- 2026-11-19: Validation errors show real messages on form; empty New PIN = disable PIN.
- 2026-11-19: Drop My OTPs / Shared with me filter — combined list.
- 2026-11-19: OM-18 — click Code column copies clipboard + “Copied”.
- 2026-11-19: Click Code → copy clipboard.
- 2026-11-19: No PIN → hide Lock/Unlock button.
- 2026-11-19: PIN optional — Cancel/X Set up PIN first time = no PIN + vault usable (V4b); no stuck “Checking vault status…”.
- 2026-11-19: Settings “Copy to Clipboard only” — mask CODE when on.
- 2026-11-19: Grid pagination like Log Center.
- 2026-11-19: Export drops PIN; re-auth with DSM password; fix plaintext checkbox alignment.
- 2026-11-19: Export plaintext hides password/confirm; encrypted shows them; DSM password always required.
- 2026-11-19: Validation/dialog error text red across forms.
- 2026-11-19: D8 — main grid/toolbar left–right padding ~14px.
- 2026-11-19: Export encryption password free-form (no min length); Encryption password label; clear required error.
- 2026-11-19: Rename package/id/path/Ext → **OTPAuthentication**; display **OTP Authentication**; GitHub `synology-dev/OTPAuthentication`. Migrating vault from old package: copy `@appdata/OTPManager` → `OTPAuthentication` (postinst auto-copies if new data empty).
- 2026-11-19: Settings restyle like DSM Info Center (D9) — label|value rows + checkbox aligned to value column.
- 2026-11-19: OM-49 — right-click keeps multi-select (G7); Delete bulk owned (G8); Export Selected via dialog/ids (E7).
- 2026-11-19: Import parse/decrypt errors → AppError 400 + message (I6); avoid CGI HTTP 500 because DSM returns HTML.
- 2026-11-19: G8 — bulk delete one `ids[]` request + txn (do not delete ids sequentially).
- 2026-11-20: V12 — no PIN: idle/401 does not open Unlock PIN; `unauthorized` → DSM session expired message.
- 2026-11-20: V12b — Unlock dialog always re-checks `pin.status`; stale client `pinConfigured` must not show Unlock (OM-52).
- 2026-11-20: OM-52 follow-up — auth recovery always uses `pin.status` (ignore stale client `pinConfigured`).
