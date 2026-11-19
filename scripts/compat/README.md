# Compatibility probes

Lab notes for DSM auth/runtime checks stay out of git when they contain host details.

Expected helpers on DSM 7.x:

- `/usr/syno/synoman/webman/modules/authenticate.cgi`
- `/usr/syno/sbin/synouser`
- `/usr/bin/python3` (3.8+ observed)

Record model/DSM/Python/glibc results in `docs/compatibility.md` without credentials.
