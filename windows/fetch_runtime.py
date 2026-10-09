"""Downloads the embeddable Python and Tesseract the packaged app ships with."""

from __future__ import annotations

import hashlib
import io
import os
import shutil
import ssl
import struct
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENDOR = HERE / "vendor"

PYTHON_VERSION = "3.13.1"
PYTHON_ZIP = (
    f"https://www.python.org/ftp/python/{PYTHON_VERSION}/"
    f"python-{PYTHON_VERSION}-embed-amd64.zip"
)
PYTHON_SHA256 = "7b7923ff0183a8b8fca90f6047184b419b108cb437f75fc1c002f9d2f8bcec16"

TESSERACT_VERSION = "5.4.0.20240606"
TESSERACT_EXE = (
    "https://github.com/UB-Mannheim/tesseract/releases/download/"
    f"v{TESSERACT_VERSION}/tesseract-ocr-w64-setup-{TESSERACT_VERSION}.exe"
)
TESSERACT_SHA256 = "c885fff6998e0608ba4bb8ab51436e1c6775c2bafc2559a19b423e18678b60c9"

RUSSIAN_VERSION = "4.1.0"
RUSSIAN_DATA = (
    "https://github.com/tesseract-ocr/tessdata_fast/raw/"
    f"{RUSSIAN_VERSION}/rus.traineddata"
)
RUSSIAN_SHA256 = "e16e5e036cce1d9ec2b00063cf8b54472625b9e14d893a169e2b0dedeb4df225"


def _download(url: str, timeout: int = 900) -> bytes:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as reply:
            return reply.read()
    except urllib.error.URLError as first:
        reason = getattr(first, "reason", first)
        if not isinstance(reason, ssl.SSLError) or "not marked critical" not in str(reason):
            raise
        print("    HTTPS on this machine is being intercepted and re-signed;")
        print("    retrying without OpenSSL's strict CA check. What makes the")
        print("    result trustworthy is the pinned SHA-256, not the chain.")
        relaxed = ssl.create_default_context()
        relaxed.verify_flags &= ~ssl.VERIFY_X509_STRICT
        with urllib.request.urlopen(url, timeout=timeout, context=relaxed) as reply:
            return reply.read()


def _verified(url: str, expected: str, what: str) -> bytes | None:
    blob = _download(url)
    got = hashlib.sha256(blob).hexdigest()
    if got != expected:
        print(f"! {what}: that download is not the file this expects.", file=sys.stderr)
        print(f"    expected sha256 {expected}", file=sys.stderr)
        print(f"    got      sha256 {got}", file=sys.stderr)
        print("  Nothing was written. Try again; if it repeats, fetch it by hand",
              file=sys.stderr)
        print(f"  from {url} and check it yourself.", file=sys.stderr)
        return None
    print(f"  {what}: {len(blob) / 1e6:.1f} MB, sha256 verified")
    return blob


def _pe_headers(blob: bytes):
    pe = struct.unpack_from("<I", blob, 0x3C)[0]
    if blob[pe:pe + 4] != b"PE\0\0":
        raise ValueError("not a PE file")
    coff = pe + 4
    nsections = struct.unpack_from("<H", blob, coff + 2)[0]
    sym_ptr, nsyms = struct.unpack_from("<II", blob, coff + 8)
    opt_size = struct.unpack_from("<H", blob, coff + 16)[0]
    opt = coff + 20
    magic = struct.unpack_from("<H", blob, opt)[0]
    directories = opt + (112 if magic == 0x20B else 96)
    table = opt + opt_size
    return {
        "coff": coff, "opt": opt, "table": table, "n": nsections,
        "dirs": directories, "sym_ptr": sym_ptr, "nsyms": nsyms,
    }


def _sections(blob: bytes, h) -> list[tuple[str, int, int, int, int]]:
    strtab = h["sym_ptr"] + h["nsyms"] * 18 if h["sym_ptr"] else 0
    out = []
    for i in range(h["n"]):
        off = h["table"] + i * 40
        raw = blob[off:off + 8].rstrip(b"\0").decode("latin-1")
        name = raw
        if raw.startswith("/") and strtab and raw[1:].isdigit():
            at = strtab + int(raw[1:])
            if 0 < at < len(blob):
                name = blob[at:blob.index(b"\0", at)].decode("latin-1")
        vsize, vaddr, rawsize, rawptr = struct.unpack_from("<IIII", blob, off + 8)
        out.append((name, vsize, vaddr, rawsize, rawptr))
    return out


def _imports(path: Path) -> list[str]:
    blob = path.read_bytes()
    try:
        h = _pe_headers(blob)
    except (ValueError, struct.error):
        return []
    rva = struct.unpack_from("<I", blob, h["dirs"] + 8)[0]
    if not rva:
        return []
    sections = _sections(blob, h)

    def offset_of(address: int) -> int | None:
        for _, vsize, vaddr, rawsize, rawptr in sections:
            if rawptr and vaddr <= address < vaddr + max(vsize, rawsize):
                return rawptr + (address - vaddr)
        return None

    at = offset_of(rva)
    names = []
    while at is not None:
        entry = blob[at:at + 20]
        if len(entry) < 20 or entry == b"\0" * 20:
            break
        name_rva = struct.unpack_from("<I", entry, 12)[0]
        if not name_rva:
            break
        where = offset_of(name_rva)
        if where is not None:
            names.append(blob[where:blob.index(b"\0", where)].decode("latin-1"))
        at += 20
    return names


def _needed_dlls(root: Path, folder: Path) -> set[str]:
    have = {f.name.lower(): f for f in folder.glob("*.dll")}
    seen: set[str] = set()
    queue = [root]
    while queue:
        for name in _imports(queue.pop()):
            key = name.lower()
            if key in have and key not in seen:
                seen.add(key)
                queue.append(have[key])
    return seen


def _strip_debug(path: Path) -> int:
    blob = bytearray(path.read_bytes())
    before = len(blob)
    try:
        h = _pe_headers(blob)
    except (ValueError, struct.error):
        return 0
    sections = _sections(blob, h)

    keep = [i for i, s in enumerate(sections) if not s[0].startswith(".debug")]
    drop = [i for i, s in enumerate(sections) if s[0].startswith(".debug")]
    if not drop:
        return 0

    cut = min(sections[i][4] for i in drop)
    if any(sections[i][4] + sections[i][3] > cut for i in keep if sections[i][4]):
        return 0
    if h["sym_ptr"] and h["sym_ptr"] < cut:
        return 0

    table = h["table"]
    kept = b"".join(bytes(blob[table + i * 40: table + i * 40 + 40]) for i in keep)
    blob[table:table + h["n"] * 40] = kept + b"\0" * (40 * (h["n"] - len(keep)))
    struct.pack_into("<H", blob, h["coff"] + 2, len(keep))
    struct.pack_into("<II", blob, h["coff"] + 8, 0, 0)

    align = struct.unpack_from("<I", blob, h["opt"] + 32)[0] or 0x1000
    top = max(sections[i][2] + sections[i][1] for i in keep)
    struct.pack_into("<I", blob, h["opt"] + 56, (top + align - 1) // align * align)
    struct.pack_into("<I", blob, h["opt"] + 64, 0)

    del blob[cut:]
    path.write_bytes(bytes(blob))
    return before - len(blob)


def fetch_python() -> int:
    dest = VENDOR / "python"
    if (dest / "python.exe").exists():
        print(f"  python: already in {dest.relative_to(HERE)}")
        return 0
    print(f"  python: downloading {PYTHON_VERSION} embeddable ...")
    blob = _verified(PYTHON_ZIP, PYTHON_SHA256, "python")
    if blob is None:
        return 1

    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        archive.extractall(dest)

    pth = next(dest.glob("python*._pth"), None)
    if pth is not None:
        lines = pth.read_text(encoding="utf-8").splitlines()
        for wanted in ("..\\..", "..\\..\\app"):
            if wanted not in lines:
                lines.insert(0, wanted)
        pth.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"  python: taught {pth.name} where the app lives")
    print(f"  python: ready in {dest.relative_to(HERE)}")
    return 0


def _seven_zip() -> Path | None:
    found = shutil.which("7z")
    if found:
        return Path(found)
    for base in (r"C:\Program Files\7-Zip", r"C:\Program Files (x86)\7-Zip"):
        candidate = Path(base) / "7z.exe"
        if candidate.is_file():
            return candidate
    return None


def _unpack_installer(installer: Path, into: Path) -> bool:
    seven = _seven_zip()
    if seven is not None:
        print(f"  ocr: unpacking with {seven.name} (nothing is installed)")
        done = subprocess.run([str(seven), "x", "-y", f"-o{into}", str(installer)],
                              capture_output=True, text=True)
        if done.returncode == 0 and (into / "tesseract.exe").is_file():
            return True
        print(f"  ocr: 7-Zip could not read it ({done.returncode}), trying the installer")

    print("  ocr: no 7-Zip here - running the installer in silent mode")
    if " " in str(into):
        print(f"! ocr: refusing to pass a path with spaces to /D= ({into})", file=sys.stderr)
        return False
    done = subprocess.run(f'"{installer}" /S /D={into}', capture_output=True, text=True)
    if (into / "tesseract.exe").is_file():
        print("  ocr: installed silently - remove it later from Add/Remove Programs")
        return True
    print(f"! ocr: the installer left nothing in {into} (exit {done.returncode})",
          file=sys.stderr)
    return False


def _minimal_tesseract(unpacked: Path, dest: Path) -> int:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "tessdata").mkdir(exist_ok=True)

    engine = unpacked / "tesseract.exe"
    if not engine.is_file():
        print(f"! ocr: no tesseract.exe in {unpacked}", file=sys.stderr)
        return 1
    language = unpacked / "tessdata" / "eng.traineddata"
    if not language.is_file():
        print("! ocr: no English language data in the installer", file=sys.stderr)
        return 1

    shutil.copy2(engine, dest / "tesseract.exe")
    needed = _needed_dlls(engine, unpacked)
    for name in sorted(needed):
        shutil.copy2(unpacked / name, dest / name)
    shutil.copy2(language, dest / "tessdata" / "eng.traineddata")

    for candidate in (unpacked / "doc" / "LICENSE", unpacked / "LICENSE"):
        if candidate.is_file():
            shutil.copy2(candidate, dest / "LICENSE")
            break

    saved = sum(_strip_debug(f) for f in list(dest.glob("*.dll")) + [dest / "tesseract.exe"])
    total = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
    print(f"  ocr: kept tesseract.exe + {len(needed)} of "
          f"{len(list(unpacked.glob('*.dll')))} DLLs + English")
    if saved:
        print(f"  ocr: removed {saved / 1e6:.0f} MB of debug symbols")
    print(f"  ocr: ready in {dest.relative_to(HERE)}, {total / 1e6:.1f} MB")
    return 0


def fetch_russian(dest: Path) -> int:
    target = dest / "tessdata" / "rus.traineddata"
    try:
        where = target.parent.relative_to(HERE)
    except ValueError:
        where = target.parent
    if target.is_file():
        if hashlib.sha256(target.read_bytes()).hexdigest() == RUSSIAN_SHA256:
            print(f"  ocr: Russian already in {where}")
            return 0
        print(f"  ocr: {target.name} in {where} is not the pinned file - fetching it again")
    print(f"  ocr: downloading the Russian model, tessdata_fast {RUSSIAN_VERSION} (4 MB) ...")
    blob = _verified(RUSSIAN_DATA, RUSSIAN_SHA256, "ocr, Russian")
    if blob is None:
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    part.write_bytes(blob)
    part.replace(target)
    print(f"  ocr: Russian ready in {where}")
    return 0


def fetch_ocr() -> int:
    dest = VENDOR / "tesseract"
    if (dest / "tesseract.exe").exists():
        print(f"  ocr: already in {dest.relative_to(HERE)}")
        return fetch_russian(dest)

    print(f"  ocr: downloading Tesseract {TESSERACT_VERSION} (50 MB) ...")
    blob = _verified(TESSERACT_EXE, TESSERACT_SHA256, "ocr")
    if blob is None:
        return 1

    VENDOR.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="tess-", dir=VENDOR))
    try:
        installer = work / "setup.exe"
        installer.write_bytes(blob)
        unpacked = work / "unpacked"
        unpacked.mkdir()
        if not _unpack_installer(installer, unpacked):
            return 1
        if _minimal_tesseract(unpacked, dest):
            return 1
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return fetch_russian(dest)


def main(argv: list[str]) -> int:
    VENDOR.mkdir(parents=True, exist_ok=True)
    want_python = "--ocr" not in argv
    want_ocr = "--python" not in argv
    code = 0
    for wanted, job, what in ((want_python, fetch_python, "python"),
                              (want_ocr, fetch_ocr, "ocr")):
        if not wanted:
            continue
        try:
            code |= job()
        except Exception as why:
            print(f"! {what}: {why}", file=sys.stderr)
            code = 1
    if code == 0:
        print("\n  Done. Double-click budget.exe.\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
