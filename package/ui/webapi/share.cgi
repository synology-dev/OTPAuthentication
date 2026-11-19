#!/bin/sh
SCRIPT="$0"
if command -v readlink >/dev/null 2>&1; then
  RESOLVED="$(readlink -f "$0" 2>/dev/null || true)"
  [ -n "$RESOLVED" ] && SCRIPT="$RESOLVED"
fi
ROOT="$(CDPATH= cd -- "$(dirname "$SCRIPT")/../.." && pwd)"
export OTPMANAGER_HANDLER=share
export OTPMANAGER_DATA_DIR="${OTPMANAGER_DATA_DIR:-/var/packages/OTPManager/var}"
exec "$ROOT/bin/run-python" -m otpmanager.cgi_main
