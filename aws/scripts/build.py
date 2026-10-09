"""Build the Lambda deployment package.

    python scripts/build.py            -> dist/budget-lambda.zip

One command, stdlib only, same result on Windows and on CI. The package is just
`src/` - the `budget` package plus `handler.py` - because the library has no
dependencies and boto3 already exists inside the Lambda runtime.

Only `.py` files and the rules file (`.toml`) are listed, which is what keeps
`__pycache__` out without relying on exclude globs, and the entries are written
in sorted order with a fixed timestamp so the same sources always produce a
byte-identical zip. That makes the archive comparable between a local build
and a CI one.

The `.toml` is not optional: every group, limit and pattern
the classifier uses lives in `src/budget/rules.toml`, and a zip without it is
a Lambda that fails at import. Terraform's `archive_file` lists the same two
kinds - keep them in step.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
OUT = ROOT / "dist" / "budget-lambda.zip"

# Fixed, so two builds of the same sources match to the byte. Zip's own epoch.
STAMP = (1980, 1, 1, 0, 0, 0)


SHIPPED = (".py", ".toml")


def files() -> list[Path]:
    return sorted(
        p for p in SRC.rglob("*")
        if p.is_file() and p.suffix in SHIPPED and "__pycache__" not in p.parts
    )


def build(out: Path = OUT) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in files():
            info = zipfile.ZipInfo(str(path.relative_to(SRC)).replace("\\", "/"), STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, path.read_bytes())
    return out


if __name__ == "__main__":
    written = build()
    size = written.stat().st_size
    print(f"{written}  ({len(files())} files, {size / 1024:.1f} KB)")
    if size > 50 * 1024 * 1024:
        sys.exit("too large for a direct Lambda upload - use S3")
