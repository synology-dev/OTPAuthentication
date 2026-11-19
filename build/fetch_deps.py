#!/usr/bin/env python3
"""Download cryptography (+cffi when available) wheels into package/deps for a target arch.

Dual runtime path (matches run-python probe order cpXY then abi3):
- Python 3.8 → package/deps/<arch>/cp38 with cryptography 47 (Requires-Python >=3.8)
- Python ≥3.9 → package/deps/<arch>/abi3 and cp39 with cryptography 50
Dev/CI keep auditing cryptography 50 via requirements-dev.txt.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLATFORMS = json.loads((ROOT / "build" / "platforms.json").read_text(encoding="utf-8"))
CRYPTO_VERSION = PLATFORMS["crypto"]["version"]
CRYPTO_VERSION_PY38 = PLATFORMS["crypto"].get("version_py38", "47.0.0")
CFFI_VERSION = PLATFORMS["crypto"].get("cffi_version", "1.17.1")

PLATFORM_TAGS = {
    "x86_64": ["manylinux_2_17_x86_64", "manylinux2014_x86_64"],
    "aarch64": ["manylinux_2_17_aarch64", "manylinux2014_aarch64"],
    # PyPI ships armv7 cryptography as manylinux_2_28/2_31 only; cffi has no armv7l wheels.
    "armv7": ["manylinux_2_28_armv7l", "manylinux_2_31_armv7l"],
}


def _pip_download(
    dest: Path,
    packages: list,
    platforms: list,
    python_version: str,
    abis: list,
    *,
    no_deps: bool = False,
) -> None:
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "download",
        *packages,
        "--only-binary=:all:",
        "--dest",
        str(dest),
        "--python-version",
        python_version,
        "--implementation",
        "cp",
    ]
    if no_deps:
        cmd.append("--no-deps")
    for plat in platforms:
        cmd.extend(["--platform", plat])
    for abi in abis:
        cmd.extend(["--abi", abi])
    print("Running", " ".join(cmd))
    subprocess.check_call(cmd)


def _extract_wheels(tmp_path: Path, out: Path) -> None:
    wheels = list(tmp_path.glob("*.whl"))
    if not wheels:
        raise RuntimeError("no wheels downloaded")
    for wheel in wheels:
        shutil.copy2(wheel, out / wheel.name)
        subprocess.check_call([sys.executable, "-m", "zipfile", "-e", str(wheel), str(out)])


def _download_pycparser(tmp_path: Path) -> None:
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "pip",
            "download",
            "pycparser",
            "--no-deps",
            "--dest",
            str(tmp_path),
        ]
    )


def _fetch_bundle(
    *,
    out: Path,
    platforms: list,
    crypto_version: str,
    python_version: str,
    crypto_abis: list,
    cffi_abis: list,
    include_cffi: bool,
) -> None:
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        try:
            _pip_download(
                tmp_path,
                [f"cryptography=={crypto_version}"],
                platforms,
                python_version=python_version,
                abis=crypto_abis,
                no_deps=True,
            )
        except subprocess.CalledProcessError:
            _pip_download(
                tmp_path,
                [f"cryptography=={crypto_version}"],
                platforms,
                python_version=python_version,
                abis=["abi3"],
                no_deps=True,
            )

        if include_cffi:
            try:
                _pip_download(
                    tmp_path,
                    [f"cffi=={CFFI_VERSION}"],
                    platforms,
                    python_version=python_version,
                    abis=cffi_abis,
                    no_deps=True,
                )
            except subprocess.CalledProcessError as exc:
                print(f"cffi wheel missing for {out}: {exc}", file=sys.stderr)
                raise SystemExit(4) from exc
            _download_pycparser(tmp_path)
        else:
            print(
                "WARNING: armv7 SPK ships cryptography without cffi "
                "(no public manylinux armv7l cffi wheel). Verify import on device.",
                file=sys.stderr,
            )
            _download_pycparser(tmp_path)

        try:
            _extract_wheels(tmp_path, out)
        except RuntimeError as exc:
            print(exc, file=sys.stderr)
            raise SystemExit(3) from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default="x86_64")
    parser.add_argument("--dest", default=str(ROOT / "package" / "deps"))
    args = parser.parse_args()

    platforms = PLATFORM_TAGS.get(args.target)
    if not platforms:
        print(f"unknown target {args.target}", file=sys.stderr)
        return 2

    dest = Path(args.dest)
    include_cffi = args.target != "armv7"

    # Python ≥3.9 path (cryptography 50): abi3 + cp39 mirror
    # Use 3.9.2 (not "39"/3.9.0): cryptography Requires-Python excludes 3.9.0/3.9.1.
    abi3 = dest / args.target / "abi3"
    _fetch_bundle(
        out=abi3,
        platforms=platforms,
        crypto_version=CRYPTO_VERSION,
        python_version="3.9.2",
        crypto_abis=["abi3", "cp39"],
        cffi_abis=["cp39"],
        include_cffi=include_cffi,
    )
    cp39 = dest / args.target / "cp39"
    if cp39.exists():
        shutil.rmtree(cp39)
    shutil.copytree(abi3, cp39)

    # DSM Python 3.8 path (cryptography 47)
    cp38 = dest / args.target / "cp38"
    _fetch_bundle(
        out=cp38,
        platforms=platforms,
        crypto_version=CRYPTO_VERSION_PY38,
        python_version="3.8",
        crypto_abis=["abi3", "cp38"],
        cffi_abis=["cp38"],
        include_cffi=include_cffi,
    )

    manifest = {
        "crypto": CRYPTO_VERSION,
        "crypto_py38": CRYPTO_VERSION_PY38,
        "cffi": None if args.target == "armv7" else CFFI_VERSION,
        "target": args.target,
        "python_baseline": "3.8",
        "note": (
            "Dual path: cp38 uses cryptography "
            f"{CRYPTO_VERSION_PY38}; abi3/cp39 use {CRYPTO_VERSION}. "
            "Verify on DSM before release."
        ),
        "armv7_cffi": "missing_public_wheel" if args.target == "armv7" else "bundled",
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("deps ready at", abi3, "and", cp38)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
