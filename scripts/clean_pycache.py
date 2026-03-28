#!/usr/bin/env python3
# scripts/clean_pycache.py
# Remove orphaned .pyc files whose source .py no longer exists, then prune empty __pycache__/ dirs.
# Design: docs/plans/2026-03-27-60-clean-stale-pycache-design.md

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
GITIGNORE_PATH = PROJECT_ROOT / ".gitignore"
PYCACHE_DIR_NAME = "__pycache__"
GITIGNORE_PYCACHE_ENTRY = "__pycache__/"
PYC_SUFFIX = ".pyc"
CPYTHON_MARKER = ".cpython-"


def verify_gitignore() -> bool:
    """Confirm .gitignore already excludes __pycache__/ and report the result."""
    if not GITIGNORE_PATH.exists():
        print(f"WARNING: {GITIGNORE_PATH} not found")
        return False
    content = GITIGNORE_PATH.read_text()
    found = GITIGNORE_PYCACHE_ENTRY in content
    status = "OK" if found else "MISSING"
    print(f".gitignore {GITIGNORE_PYCACHE_ENTRY!r}: {status}")
    return found


def source_path_for_pyc(pyc_path: Path) -> Path:
    """Derive the .py source path that corresponds to a .pyc file inside __pycache__/."""
    stem = pyc_path.stem
    # Stem looks like: module.cpython-311 — strip the cpython version tag.
    if CPYTHON_MARKER in stem:
        module_name = stem.split(CPYTHON_MARKER)[0]
    else:
        module_name = stem
    return pyc_path.parent.parent / (module_name + ".py")


def clean_pycache_dirs() -> tuple[int, int]:
    """
    Walk all __pycache__/ directories, delete orphaned .pyc files, and remove empty dirs.

    Returns (deleted_pyc_count, removed_dir_count).
    """
    deleted_pyc = 0
    removed_dirs = 0

    for pycache_dir in PROJECT_ROOT.rglob(PYCACHE_DIR_NAME):
        if not pycache_dir.is_dir():
            continue

        for pyc_file in list(pycache_dir.glob(f"*{PYC_SUFFIX}")):
            source = source_path_for_pyc(pyc_file)
            if not source.exists():
                print(f"  Deleting orphaned: {pyc_file.relative_to(PROJECT_ROOT)}")
                pyc_file.unlink()
                deleted_pyc += 1

        # Remove the directory if it is now empty.
        remaining = list(pycache_dir.iterdir())
        if not remaining:
            print(f"  Removing empty dir: {pycache_dir.relative_to(PROJECT_ROOT)}/")
            pycache_dir.rmdir()
            removed_dirs += 1

    return deleted_pyc, removed_dirs


def main() -> int:
    print(f"Project root: {PROJECT_ROOT}\n")
    verify_gitignore()
    print()

    print("Scanning for orphaned .pyc files...")
    deleted_pyc, removed_dirs = clean_pycache_dirs()

    print()
    print(f"Done. Deleted {deleted_pyc} orphaned .pyc file(s), removed {removed_dirs} empty __pycache__/ dir(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
