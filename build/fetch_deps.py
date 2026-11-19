#!/usr/bin/env python3
"""Download cryptography (+cffi when available) wheels into package/deps for a target arch."""

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
    out = dest / args.target / "abi3"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        # Resolve cryptography with --no-deps so pip markers for newer CPython
        # do not block the DSM Python 3.8 wheel selection.
        try:
            _pip_download(
                tmp_path,
                [f"cryptography=={CRYPTO_VERSION}"],
                platforms,
                python_version="38",
                abis=["abi3", "cp38"],
                no_deps=True,
            )
        except subprocess.CalledProcessError:
            _pip_download(
                tmp_path,
                [f"cryptography=={CRYPTO_VERSION}"],
                platforms,
                python_version="38",
                abis=["abi3"],
                no_deps=True,
            )

        if args.target != "armv7":
            try:
                _pip_download(
                    tmp_path,
                    [f"cffi=={CFFI_VERSION}"],
                    platforms,
                    python_version="38",
                    abis=["cp38"],
                    no_deps=True,
                )
            except subprocess.CalledProcessError as exc:
                print(f"cffi wheel missing for {args.target}: {exc}", file=sys.stderr)
                return 4
        else:
            print(
                "WARNING: armv7 SPK ships cryptography without cffi "
                "(no public manylinux armv7l cffi wheel). Verify import on device.",
                file=sys.stderr,
            )

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
        try:
            _extract_wheels(tmp_path, out)
        except RuntimeError as exc:
            print(exc, file=sys.stderr)
            return 3

    cp38 = dest / args.target / "cp38"
    if cp38.exists():
        shutil.rmtree(cp38)
    shutil.copytree(out, cp38)

    manifest = {
        "crypto": CRYPTO_VERSION,
        "cffi": None if args.target == "armv7" else CFFI_VERSION,
        "target": args.target,
        "python_baseline": "3.8",
        "note": "Wheels extracted for PYTHONPATH; verify on DSM before release.",
        "armv7_cffi": "missing_public_wheel" if args.target == "armv7" else "bundled",
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("deps ready at", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
