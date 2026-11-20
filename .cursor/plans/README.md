# Plans

Deployment / architecture plan directory for the Synology **OTP Authentication** package (`OTPAuthentication`).

## Canonical plan

| File | Role |
|------|------|
| [synology_otp_package_3471a2a5.plan.md](synology_otp_package_3471a2a5.plan.md) | **Main plan** (canonical) — architecture, SPK lifecycle, CI, verification, publication |

## Related

- Living UI/API behavior (test checklist): [`docs/logic-spec.md`](../../docs/logic-spec.md)
- Agent guide: [`AGENTS.md`](../../AGENTS.md)
- Repo: [synology-dev/OTPAuthentication](https://github.com/synology-dev/OTPAuthentication)

## Conventions

- Agents **must not edit** `.cursor/plans/*` unless the user explicitly asks.
- Do not create duplicate plans; record new behavior decisions in `docs/logic-spec.md`.
- This directory is tracked in git (`!.cursor/plans/**` in `.gitignore`).
