#!/usr/bin/env python3
"""Package the contents, with exactly one sulkan.json at the ZIP root."""
from pathlib import Path
import argparse
import zipfile

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("UN_Aurora_Lite-0.1.3-Sulkan-0.4.2.zip"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.resolve() != output
                   and not any(part.startswith(".") or part in {"__pycache__", "build", "dist"} for part in p.relative_to(root).parts)
                   and p.suffix not in {".zip", ".class", ".spv", ".pyc"})
    assert (root / "sulkan.json") in files
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            info = zipfile.ZipInfo(path.relative_to(root).as_posix(), (2026, 9, 16, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert archive.namelist().count("sulkan.json") == 1
    print(output)

if __name__ == "__main__":
    main()
