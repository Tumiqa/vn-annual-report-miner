r"""Clean up temporary/junk files across the workspace and Google Drive gap folder.

Removes:
1. Orphaned `.tmp` files in Google Drive folder (`H:\My Drive\arminer_bctn_gap`).
2. Scratch test scripts and temporary debug artifacts in `scratch/`.
3. Python `__pycache__` and `.pytest_cache` directories.
4. Any leftover `.tmp` or `.zip` test artifacts in the repository root.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
DRIVE_GAP_DIR = Path("H:/My Drive/arminer_bctn_gap")


def clean_drive_tmp_files() -> int:
    """Find and remove any orphaned .tmp files in the Google Drive storage directory."""
    cleaned = 0
    if not DRIVE_GAP_DIR.exists():
        print(f"[CLEANUP] Drive gap directory not found: {DRIVE_GAP_DIR}")
        return 0

    print(f"[CLEANUP] Scanning for .tmp files in {DRIVE_GAP_DIR}...")
    try:
        for tmp_file in DRIVE_GAP_DIR.rglob("*.tmp"):
            try:
                tmp_file.unlink()
                cleaned += 1
                print(f"  Removed orphaned tmp: {tmp_file.name}")
            except Exception as e:
                print(f"  Failed to remove {tmp_file}: {e}")
    except Exception as e:
        print(f"  Error scanning Drive: {e}")

    print(f"[CLEANUP] Cleaned {cleaned} orphaned .tmp files from Google Drive.")
    return cleaned


def clean_scratch_files() -> int:
    """Clean temporary test scripts and artifacts in scratch/ while preserving production assets."""
    scratch_dir = WORKSPACE_ROOT / "scratch"
    if not scratch_dir.exists():
        return 0

    # Temporary test files to remove
    junk_patterns = [
        "test_*.py",
        "verify_*.py",
        "fix_*.py",
        "*.tmp",
        "*.log",
        "gap_detail.csv",
        "gap_matrix.csv",
        "bctn_new_vs_zenodo.csv",
    ]

    cleaned = 0
    for pattern in junk_patterns:
        for f in scratch_dir.glob(pattern):
            try:
                f.unlink()
                cleaned += 1
                print(f"  Removed scratch junk: {f.name}")
            except Exception as e:
                print(f"  Failed to remove {f}: {e}")

    # Remove ocr_test_report if present
    ocr_dir = scratch_dir / "ocr_test_report"
    if ocr_dir.exists() and ocr_dir.is_dir():
        try:
            shutil.rmtree(ocr_dir)
            cleaned += 1
            print(f"  Removed temporary directory: {ocr_dir.name}")
        except Exception as e:
            print(f"  Failed to remove {ocr_dir}: {e}")

    print(f"[CLEANUP] Cleaned {cleaned} junk items from scratch/.")
    return cleaned


def clean_pycache_and_test_artifacts() -> int:
    """Recursively remove __pycache__, .pytest_cache, and test temp files."""
    cleaned = 0

    # Clean __pycache__
    for pycache in WORKSPACE_ROOT.rglob("__pycache__"):
        if ".git" in pycache.parts:
            continue
        try:
            shutil.rmtree(pycache)
            cleaned += 1
        except Exception:
            pass

    # Clean .pytest_cache
    for pytest_cache in WORKSPACE_ROOT.rglob(".pytest_cache"):
        try:
            shutil.rmtree(pytest_cache)
            cleaned += 1
        except Exception:
            pass

    # Clean test zip files in workspace root
    for zip_file in WORKSPACE_ROOT.glob("test_*.zip"):
        try:
            zip_file.unlink()
            cleaned += 1
            print(f"  Removed test zip: {zip_file.name}")
        except Exception:
            pass

    for tmp_file in WORKSPACE_ROOT.glob("*.tmp"):
        try:
            tmp_file.unlink()
            cleaned += 1
            print(f"  Removed root tmp: {tmp_file.name}")
        except Exception:
            pass

    print(f"[CLEANUP] Cleaned {cleaned} cache and temp artifacts.")
    return cleaned


def main():
    print("=" * 60)
    print("      ARMINER WORKSPACE & DRIVE CLEANUP UTILITY       ")
    print("=" * 60)

    total_cleaned = 0
    total_cleaned += clean_drive_tmp_files()
    total_cleaned += clean_scratch_files()
    total_cleaned += clean_pycache_and_test_artifacts()

    print("=" * 60)
    print(f"Cleanup finished! Total junk items removed: {total_cleaned}")
    print("=" * 60)


if __name__ == "__main__":
    main()
