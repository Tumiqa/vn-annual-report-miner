# -*- coding: utf-8 -*-
"""
scripts/build_drive_index.py
=============================
Trích xuất toàn bộ Google Drive File ID của 5.928+ file BCTN đã đồng bộ trên Google Drive Cloud
từ cơ sở dữ liệu nội bộ của Google Drive for Desktop (mirror_metadata_sqlite.db).

Tạo ra file: data/gap_filler/drive_index.json
Giúp bất kỳ ai, ở bất kỳ đâu (Google Colab, máy tính khác, server) tự động tải trực tiếp BCTN
từ Google Drive Cloud qua HTTP trong 0.2s - y hệt cơ chế tải của Zenodo!
"""
import glob
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

# UTF-8 fix for Windows console
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_FILE = WORKSPACE_ROOT / "data" / "gap_filler" / "drive_index.json"


def build_drive_index():
    print("=" * 65)
    print("  TRÍCH XUẤT GOOGLE DRIVE CLOUD FILE ID TỪ DRIVEFS DATABASE  ")
    print("=" * 65)

    db_paths = glob.glob(os.path.expandvars(r"%LOCALAPPDATA%\Google\DriveFS\*\mirror_metadata_sqlite.db"))
    if not db_paths:
        print("❌ Không tìm thấy database của Google Drive for Desktop!")
        return

    # Sử dụng database có kích thước lớn nhất
    db_paths.sort(key=lambda p: os.path.getsize(p), reverse=True)
    target_db = db_paths[0]
    print(f"  Thư viện DriveFS DB: {target_db}")

    conn = sqlite3.connect(f"file:{target_db}?mode=ro", uri=True)
    cur = conn.cursor()

    cur.execute("""
        SELECT id, local_title, file_size
        FROM items
        WHERE local_title LIKE '%_BCTN.pdf'
          AND trashed = 0
          AND is_tombstone = 0
    """)
    rows = cur.fetchall()
    conn.close()

    print(f"  Tổng số file BCTN tìm thấy trong DriveFS: {len(rows):,} file")

    mapping = {}
    pattern = re.compile(r"^([A-Z0-9]+)_(\d{4})_BCTN\.pdf$", re.IGNORECASE)

    for file_id, filename, file_size in rows:
        m = pattern.match(filename)
        if m:
            ticker = m.group(1).upper()
            year = int(m.group(2))
            key = f"{ticker}_{year}"
            mapping[key] = {
                "file_id": file_id,
                "file_name": filename,
                "file_size": file_size,
                "direct_url": f"https://drive.google.com/uc?export=download&id={file_id}",
            }

    # Check physical folder for newly added files that are still syncing
    for dl in ("H", "I", "G"):
        g_dir = Path(f"{dl}:\\My Drive\\arminer_bctn_gap")
        if g_dir.exists():
            for p in g_dir.glob("*/*_BCTN.pdf"):
                m = pattern.match(p.name)
                if m:
                    t = m.group(1).upper()
                    y = int(m.group(2))
                    k = f"{t}_{y}"
                    if k not in mapping:
                        mapping[k] = {
                            "file_id": "",
                            "file_name": p.name,
                            "file_size": p.stat().st_size,
                            "direct_url": "",
                        }
            break

    print(f"  Tổng số bản ghi chuẩn hóa theo (MÃ_NĂM): {len(mapping):,} bản ghi")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✅ Đã lưu danh mục Google Drive Cloud vào: {OUTPUT_FILE}")
    print(f"     Dung lượng file index: {OUTPUT_FILE.stat().st_size / 1024:.1f} KB")
    print("=" * 65)


if __name__ == "__main__":
    build_drive_index()
