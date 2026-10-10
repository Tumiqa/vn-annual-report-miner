# -*- coding: utf-8 -*-
"""
scripts/audit_and_clean_all_reports.py
======================================
Hệ thống Kiểm toán Toàn diện Chất lượng Kho BCTN (20.500+ file)
Tiêu chí: 100% Chuẩn BCTN, không cho phép bất kỳ file sai/rác nào tồn tại.

Chức năng:
1. Quét song song đa luồng toàn bộ file PDF trong H:\\My Drive\\arminer_bctn_gap.
2. Kiểm tra tính toàn vẹn và chuẩn mực BCTN:
   - Số trang >= 6 trang (loại bỏ dứt điểm công văn CBTT, giải trình 1-5 trang).
   - Nội dung không phải văn bản hành chính (Nghị quyết ĐHĐCĐ, Biên bản họp, Điều lệ thuần túy).
   - File không bị lỗi cấu trúc PDF/0 byte/placeholder.
3. Tùy chọn tự động xóa bỏ (--purge) các file sai và tạo danh sách Recrawl Queue.
"""

from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Tuple

# Thiết lập UTF-8 toàn diện cho console Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

try:
    import fitz
    if hasattr(fitz, "TOOLS") and hasattr(fitz.TOOLS, "mupdf_display_errors"):
        fitz.TOOLS.mupdf_display_errors(False)
except ImportError:
    import fitz

from loguru import logger
from arminer.data.bctn_validator import audit_bctn_file, is_valid_bctn_file

def parse_year_from_name(name: str) -> int | None:
    m = re.search(r'(20\d{2})', name)
    return int(m.group(1)) if m else None

def inspect_single_pdf(file_path: Path) -> Dict[str, Any]:
    ticker = file_path.parent.name.upper()
    year = parse_year_from_name(file_path.name)
    
    try:
        sz = file_path.stat().st_size
    except Exception as e:
        return {
            "path": str(file_path),
            "ticker": ticker,
            "year": year,
            "filename": file_path.name,
            "is_valid": False,
            "pages": 0,
            "size_kb": 0.0,
            "reason": f"Không thể đọc file: {e}"
        }

    # 1. File rác / 0 byte / quá nhỏ (< 2KB)
    if sz < 2000:
        return {
            "path": str(file_path),
            "ticker": ticker,
            "year": year,
            "filename": file_path.name,
            "is_valid": False,
            "pages": 0,
            "size_kb": round(sz / 1024, 2),
            "reason": f"File quá nhỏ ({sz} bytes - rác/placeholder)"
        }

    # 2. Sử dụng audit_bctn_file để kiểm định sâu
    audit = audit_bctn_file(file_path)
    return {
        "path": str(file_path),
        "ticker": ticker,
        "year": year,
        "filename": file_path.name,
        "is_valid": audit.get("is_valid", False),
        "pages": audit.get("pages", 0),
        "size_kb": audit.get("file_size_kb", round(sz / 1024, 2)),
        "reason": audit.get("reason", "")
    }

def main():
    parser = argparse.ArgumentParser(description="Kiểm toán toàn diện chất lượng kho BCTN")
    parser.add_argument("--gdrive", type=str, default=r"H:\My Drive\arminer_bctn_gap", help="Đường dẫn kho Google Drive")
    parser.add_argument("--purge", action="store_true", help="Tự động xóa bỏ các file sai/rác")
    parser.add_argument("--workers", type=int, default=12, help="Số luồng kiểm tra song song (khuyến nghị 8-12 cho Drive)")
    parser.add_argument("--limit", type=int, default=0, help="Giới hạn số file kiểm tra (0 = toàn bộ)")
    args = parser.parse_args()

    gdrive_root = Path(args.gdrive)
    if not gdrive_root.exists():
        logger.error(f"Không tìm thấy thư mục kho BCTN tại: {gdrive_root}")
        return

    logger.info(f"Bắt đầu quét danh mục file từ: {gdrive_root}")
    t0 = time.time()
    all_pdf_files: List[Path] = []
    
    for dir_entry in gdrive_root.iterdir():
        if dir_entry.is_dir() and len(dir_entry.name) in (3, 4):
            for f in dir_entry.glob("*.pdf"):
                all_pdf_files.append(f)

    if args.limit > 0:
        all_pdf_files = all_pdf_files[:args.limit]

    total_files = len(all_pdf_files)
    logger.info(f"Đã phát hiện tổng cộng {total_files} file PDF ({time.time() - t0:.2f}s).")
    logger.info(f"Khởi động kiểm định chất lượng song song ({args.workers} workers)...")

    valid_files: List[Dict[str, Any]] = []
    bogus_files: List[Dict[str, Any]] = []
    checked_count = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_map = {executor.submit(inspect_single_pdf, p): p for p in all_pdf_files}
        for fut in as_completed(future_map):
            checked_count += 1
            try:
                res = fut.result()
            except Exception as e:
                orig_p = future_map[fut]
                res = {
                    "path": str(orig_p),
                    "ticker": orig_p.parent.name.upper(),
                    "year": parse_year_from_name(orig_p.name),
                    "filename": orig_p.name,
                    "is_valid": False,
                    "pages": 0,
                    "size_kb": 0.0,
                    "reason": f"Lỗi exception: {e}"
                }

            if res["is_valid"]:
                valid_files.append(res)
            else:
                bogus_files.append(res)

            if checked_count % 1000 == 0 or checked_count == total_files:
                pct = (checked_count / total_files) * 100
                logger.info(
                    f"Tiến độ: {checked_count}/{total_files} ({pct:.1f}%) | "
                    f"Chuẩn 100%: {len(valid_files)} | "
                    f"Sai/Rác: {len(bogus_files)}"
                )

    logger.info("=" * 70)
    logger.info(f"KẾT QUẢ KIỂM TOÁN TOÀN DIỆN ({time.time() - t0:.2f}s):")
    logger.info(f"- Tổng số file đã kiểm toán: {total_files}")
    logger.info(f"- File BCTN ĐẠT CHUẨN 100%:  {len(valid_files)} ({len(valid_files)/total_files*100:.2f}%)")
    logger.info(f"- File SAI/RÁC vi phạm:       {len(bogus_files)} ({len(bogus_files)/total_files*100:.2f}%)")
    logger.info("=" * 70)

    # Phân loại lý do sai của bogus_files
    reasons_count: Dict[str, int] = {}
    for b in bogus_files:
        r_short = b["reason"][:60]
        reasons_count[r_short] = reasons_count.get(r_short, 0) + 1

    logger.info("PHÂN BỐ NGUYÊN NHÂN FILE SAI:")
    for r_k, cnt in sorted(reasons_count.items(), key=lambda x: x[1], reverse=True)[:10]:
        logger.info(f"  * {cnt} file: {r_k}")

    # Lưu log danh sách file sai cần cào lại
    out_dir = Path(__file__).resolve().parent.parent / "data" / "gap_filler"
    out_dir.mkdir(parents=True, exist_ok=True)
    bogus_log_path = out_dir / "bogus_files_to_recrawl.json"
    
    with open(bogus_log_path, "w", encoding="utf-8") as f_out:
        json.dump(bogus_files, f_out, ensure_ascii=False, indent=2)
    logger.info(f"Đã lưu chi tiết {len(bogus_files)} file sai/rác vào: {bogus_log_path}")

    # Xử lý tự động xóa nếu có cờ --purge
    if args.purge and bogus_files:
        logger.warning(f"BẮT ĐẦU XÓA BỎ {len(bogus_files)} FILE SAI KHỎI KHO THEO YÊU CẦU...")
        deleted_count = 0
        for item in bogus_files:
            p = Path(item["path"])
            try:
                if p.exists():
                    p.unlink()
                    deleted_count += 1
            except Exception as e:
                logger.error(f"Không thể xóa {p}: {e}")
        logger.info(f"ĐÃ XÓA THÀNH CÔNG {deleted_count} FILE SAI! KHO BCTN HIỆN NAY 100% LÀ FILE CHUẨN.")

if __name__ == "__main__":
    main()
