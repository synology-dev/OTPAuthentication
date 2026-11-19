# Package Center publication checklist (Free)

- [ ] Owner accepts Synology Developer Distribution Agreement
- [ ] Apply via Synology developer form
- [ ] Confirm package id `OTPManager` with Synology (not reserved)
- [ ] Choose project license text for public distribution (see `LICENSE`)
- [ ] Build all required CPU SPKs; attach SHA256 sums
- [ ] GitHub Release download URL ready (`synology-dev/OTPManager`)
- [ ] Description/changelog/screenshots (synthetic data only) — see `docs/screenshots/`
- [ ] Operation manual + test scenarios for Synology QA (`docs/user-guide.md`, `docs/verification.md`)
- [ ] Compatibility matrix limited to verified DSM/model/Python (`docs/compatibility.md`)
- [x] Privacy statement: data stays on device; no cloud sync (`docs/privacy.md`)
- [ ] Appendix C lifecycle/security checks completed on hardware
- [x] Support email / website / issue tracker URLs in INFO

Free packages cannot later become paid under current Synology guidelines.

## Suggested Package Center blurb

OTP Manager is a self-hosted TOTP authenticator vault for DSM users. Store 2FA accounts on your NAS with PIN unlock, view-only sharing between local users, and encrypted backup. It does not enable DSM login 2FA and does not sync to the cloud.
