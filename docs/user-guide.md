# OTP Authentication user guide

## First launch

1. Open **OTP Authentication** from the DSM main menu.
2. Create a PIN (6–12 digits). There is no automatic PIN reset.
3. Unlock with your PIN whenever you open the app.

## Add accounts

- **Add** → enter issuer/account/secret, or paste an `otpauth://totp/...` URI.
- Codes refresh automatically while the vault is unlocked.

## Share

Owners can share an entry with another DSM user who has already set up OTP Authentication.
Recipients can view/copy codes only.

## Backup

- Prefer **encrypted** export with a strong password.
- Plaintext export contains raw 2FA secrets — handle like passwords.
- Import preview shows new/duplicate rows without revealing secrets.

## Lock

Use **Lock** or close the window to clear codes from the UI. Server sessions expire after idle/absolute timeouts.