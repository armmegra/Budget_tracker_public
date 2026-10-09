"""Compiles the small launcher (budget.exe) that starts the server and opens the
browser.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SOURCE = HERE / "budget.cs"
ICON = HERE / "budget.ico"
TARGET = ROOT / "budget.exe"


def find_csc() -> Path | None:
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    for arch in ("Framework64", "Framework"):
        found = windir / "Microsoft.NET" / arch / "v4.0.30319" / "csc.exe"
        if found.is_file():
            return found
    return None


def main() -> int:
    csc = find_csc()
    if csc is None:
        print("! csc.exe not found under %WINDIR%\\Microsoft.NET - is this Windows?",
              file=sys.stderr)
        return 1

    if not ICON.is_file():
        sys.path.insert(0, str(HERE))
        import make_icon
        make_icon.main()

    try:
        SOURCE.read_bytes().decode("utf-8")
    except UnicodeDecodeError as bad:
        print(f"! {SOURCE.name} is not UTF-8 (byte {bad.start}) - save it as UTF-8 "
              "and build again", file=sys.stderr)
        return 1

    command = [
        str(csc),
        "/nologo",
        "/target:exe",
        "/platform:anycpu",
        "/optimize+",
        "/warnaserror+",
        "/codepage:65001",
        f"/win32icon:{ICON}",
        f"/out:{TARGET}",
        str(SOURCE),
    ]
    done = subprocess.run(command, capture_output=True, text=True)
    if done.stdout.strip():
        print(done.stdout.rstrip())
    if done.returncode != 0:
        print(done.stderr.rstrip(), file=sys.stderr)
        print(f"! csc exited {done.returncode}", file=sys.stderr)
        return done.returncode

    unstamp(TARGET)
    print(f"  built: {TARGET.relative_to(ROOT)}  ({TARGET.stat().st_size} bytes, no build time)")
    return 0


def unstamp(exe: Path) -> None:
    blob = bytearray(exe.read_bytes())
    pe = int.from_bytes(blob[0x3C:0x40], "little")
    if blob[:2] != b"MZ" or blob[pe:pe + 4] != b"PE\0\0":
        raise SystemExit(f"! {exe.name} is not a PE file")
    coff, opt = pe + 4, pe + 24
    magic = int.from_bytes(blob[opt:opt + 2], "little")
    directories = opt + (96 if magic == 0x10B else 112)
    checksum = int.from_bytes(blob[opt + 64:opt + 68], "little")
    debug = blob[directories + 6 * 8:directories + 7 * 8]
    if checksum or any(debug):
        raise SystemExit(f"! {exe.name} has a checksum or a debug directory - "
                         "its build time cannot simply be cleared; see unstamp()")
    blob[coff + 4:coff + 8] = bytes(4)
    exe.write_bytes(bytes(blob))


if __name__ == "__main__":
    raise SystemExit(main())
