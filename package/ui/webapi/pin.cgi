#!/bin/sh
SCRIPT="$0"
if command -v readlink >/dev/null 2>&1; then
  RESOLVED="$(readlink -f "$0" 2>/dev/null || true)"
  [ -n "$RESOLVED" ] && SCRIPT="$RESOLVED"
fi
ROOT="$(CDPATH= cd -- "$(dirname "$SCRIPT")/../.." && pwd)"
export OTPAUTHENTICATION_HANDLER=pin
export OTPAUTHENTICATION_DATA_DIR="${OTPAUTHENTICATION_DATA_DIR:-/var/packages/OTPAuthentication/var}"
exec "$ROOT/bin/run-python" -m otpauthentication.cgi_main
