#!/usr/bin/env python3
from __future__ import annotations

import io
import sys
import tarfile
from pathlib import Path


REQUIRED_ROOT = {"INFO", "package.tgz", "scripts", "PACKAGE_ICON.PNG", "PACKAGE_ICON_256.PNG", "conf"}
REQUIRED_INFO = ["package=", "version=", "arch=", "os_min_ver=", "dsmuidir=", "dsmappname=", "maintainer="]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_spk.py <file.spk>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    with tarfile.open(path, "r:*") as tf:
        names = set(m.name.split("/")[0] for m in tf.getmembers())
        missing = REQUIRED_ROOT - names
        if missing:
            print("missing root entries:", sorted(missing), file=sys.stderr)
            return 1
        info = tf.extractfile("INFO").read().decode("utf-8")
        for key in REQUIRED_INFO:
            if key not in info:
                print("INFO missing", key, file=sys.stderr)
                return 1
        pkg = tf.extractfile("package.tgz")
        with tarfile.open(fileobj=io.BytesIO(pkg.read()), mode="r:gz") as inner:
            inner_names = {m.name for m in inner.getmembers()}
            for required in (
                "ui/OTPManager.js",
                "ui/config",
                "bin/run-python",
                "backend/otpmanager/service.py",
                "ui/webapi/pin.cgi",
            ):
                if required not in inner_names and f"./{required}" not in inner_names:
                    # tar may store without prefix consistency
                    if not any(n.endswith(required) for n in inner_names):
                        print("package.tgz missing", required, file=sys.stderr)
                        return 1
    print("SPK validation OK:", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())