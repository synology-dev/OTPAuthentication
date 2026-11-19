# Privacy statement

OTP Manager is a self-hosted Synology DSM package.

- Vault data (encrypted secrets, PIN hashes, share metadata, sessions) stays on the NAS under the package data directory.
- The package does not sync accounts to a cloud service and does not phone home.
- Backups are created only when a user exports them; encrypted exports are protected by a password chosen by the user.
- DSM authentication uses the signed-in DSM session; the app does not collect DSM passwords.
- Maintainers may receive support requests through GitHub Issues; do not attach real 2FA secrets or backup files containing live credentials.
