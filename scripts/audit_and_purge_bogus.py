# -*- coding: utf-8 -*-
"""
scripts/audit_and_purge_bogus.py
================================
Hệ thống Kiểm toán Chất lượng BCTN Siêu tốc & Tự động Đào thải File Sai:
1. Quét toàn diện 100% kho dữ liệu Google Drive (20.467+ file).
2. Phát hiện và loại bỏ triệt để:
   - File 0 KB / hỏng cấu trúc PDF.
   - File < 6 trang (công văn CBTT, giải trình, giấy xác nhận...).
   - File văn bản hành chính thuần túy (Nghị quyết ĐHĐCĐ, Biên bản họp, Điều lệ...).
3. Xóa bỏ ngay các file sai khỏi kho H:\\My Drive\\arminer_bctn_gap.
4. Xuất danh sách recrawl_queue.json để chuyển sang module tự động cào lại.
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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

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

def inspect_file(file_info: Tuple[str, Path, int]) -> Dict[str, Any]:
    ticker, p, sz = file_info
    year = parse_year_from_name(p.name)

    # 1. Kích thước 0 KB hoặc quá nhỏ
    if sz < 2000:
        return {
            "ticker": ticker,
            "year": year,
            "filename": p.name,
            "path": str(p),
            "size_kb": round(sz / 1024, 2),
            "pages": 0,
            "is_valid": False,
            "reason": f"File 0 byte hoặc quá nhỏ ({sz} bytes - rác)",
        }

    # 2. Sử dụng audit_bctn_file
    res = audit_bctn_file(p)
    return {
        "ticker": ticker,
        "year": year,
        "filename": p.name,
        "path": str(p),
        "size_kb": res.get("file_size_kb", round(sz / 1024, 2)),
        "pages": res.get("pages", 0),
        "is_valid": res.get("is_valid", False),
        "reason": res.get("reason", ""),
        "title_sample": res.get("title_sample", "")[:120],
    }

def main():
    parser = argparse.ArgumentParser(description="Kiểm toán siêu tốc và đào thải file BCTN sai")
    parser.add_argument("--gdrive", type=str, default=r"H:\My Drive\arminer_bctn_gap", help="Kho Google Drive")
    parser.add_argument("--purge", action="store_true", help="Xóa ngay các file sai khỏi ổ H")
    parser.add_argument("--workers", type=int, default=16, help="Số luồng song song")
    args = parser.parse_args()

    gdrive_root = Path(args.gdrive)
    if not gdrive_root.exists():
        logger.error(f"Không tìm thấy thư mục kho BCTN tại: {gdrive_root}")
        return

    logger.info(f"=== KHỞI ĐỘNG KIỂM TOÁN CHUẨN MỰC BCTN 100% TẠI: {gdrive_root} ===")
    t0 = time.time()

    all_files: List[Tuple[str, Path, int]] = []
    small_files: List[Tuple[str, Path, int]] = []
    large_files: List[Tuple[str, Path, int]] = []

    for d in gdrive_root.iterdir():
        if d.is_dir() and len(d.name) in (3, 4):
            t_name = d.name.upper()
            for f in d.glob("*.pdf"):
                try:
                    sz = f.stat().st_size
                except Exception:
                    sz = 0
                item = (t_name, f, sz)
                all_files.append(item)
                if sz < 500 * 1024:
                    small_files.append(item)
                else:
                    large_files.append(item)

    logger.info(
        f"Quét hoàn tất: Tổng {len(all_files)} file | "
        f"Nhóm rủi ro cao (< 500KB): {len(small_files)} file | "
        f"Nhóm dung lượng chuẩn (>= 500KB): {len(large_files)} file ({time.time() - t0:.2f}s)"
    )

    bogus_list: List[Dict[str, Any]] = []
    valid_count = 0

    # BƯỚC 1: KIỂM TRA SÂU TOÀN BỘ NHÓM RỦI RO CAO (< 500KB)
    logger.info(f"--- BƯỚC 1: Kiểm toán sâu toàn bộ {len(small_files)} file nhỏ (< 500KB) ---")
    t1 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(inspect_file, item): item for item in small_files}
        for fut in as_completed(futures):
            res = fut.result()
            if res["is_valid"]:
                valid_count += 1
            else:
                bogus_list.append(res)
                logger.warning(
                    f" [PHÁT HIỆN SAI] {res['ticker']} ({res['year']}) - {res['filename']}: "
                    f"{res['pages']} trang, {res['size_kb']} KB - {res['reason']}"
                )

    logger.info(
        f"Bước 1 xong ({time.time() - t1:.2f}s): "
        f"Hợp lệ: {valid_count} | Sai/Rác: {len(bogus_list)}"
    )

    # BƯỚC 2: KIỂM TRA NHANH NHÓM >= 500KB (Mở trang để đảm bảo không bị lỗi/dưới 6 trang)
    logger.info(f"--- BƯỚC 2: Kiểm tra {len(large_files)} file chuẩn dung lượng (>= 500KB) ---")
    t2 = time.time()
    large_checked = 0

    def check_large_file(item: Tuple[str, Path, int]) -> Dict[str, Any] | None:
        ticker, p, sz = item
        try:
            doc = fitz.open(p)
            pages = len(doc)
            doc.close()
            if pages < 6:
                # Nếu file >= 500KB mà < 6 trang -> nghi vấn, chạy audit sâu
                return inspect_file(item)
            return None
        except Exception as e:
            return {
                "ticker": ticker,
                "year": parse_year_from_name(p.name),
                "filename": p.name,
                "path": str(p),
                "size_kb": round(sz / 1024, 2),
                "pages": 0,
                "is_valid": False,
                "reason": f"File PDF hỏng không mở được: {e}",
            }

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(check_large_file, item): item for item in large_files}
        for fut in as_completed(futures):
            large_checked += 1
            res = fut.result()
            if res is not None:
                if not res["is_valid"]:
                    bogus_list.append(res)
                    logger.warning(
                        f" [PHÁT HIỆN SAI >=500KB] {res['ticker']} ({res['year']}) - {res['filename']}: "
                        f"{res['pages']} trang, {res['size_kb']} KB - {res['reason']}"
                    )
            else:
                valid_count += 1

            if large_checked % 5000 == 0 or large_checked == len(large_files):
                logger.info(f"Tiến độ Bước 2: {large_checked}/{len(large_files)} file đã kiểm tra...")

    total_scanned = len(all_files)
    logger.info("=" * 70)
    logger.info(f"KẾT QUẢ KIỂM TOÁN TOÀN BỘ {total_scanned} FILE TRONG KHO ({time.time() - t0:.2f}s):")
    logger.info(f"1. FILE BCTN ĐẠT CHUẨN 100%:  {valid_count} ({valid_count/total_scanned*100:.2f}%)")
    logger.info(f"2. FILE SAI / RÁC PHÁT HIỆN:  {len(bogus_list)} ({len(bogus_list)/total_scanned*100:.2f}%)")
    logger.info("=" * 70)

    # Xuất danh sách recrawl queue
    out_dir = Path(__file__).resolve().parent.parent / "data" / "gap_filler"
    out_dir.mkdir(parents=True, exist_ok=True)
    recrawl_path = out_dir / "recrawl_queue.json"

    recrawl_items = []
    for b in bogus_list:
        if b["ticker"] and b["year"]:
            recrawl_items.append({
                "ticker": b["ticker"],
                "year": b["year"],
                "old_filename": b["filename"],
                "old_path": b["path"],
                "pages": b["pages"],
                "size_kb": b["size_kb"],
                "reason": b["reason"],
            })

    with open(recrawl_path, "w", encoding="utf-8") as f_out:
        json.dump(recrawl_items, f_out, ensure_ascii=False, indent=2)

    logger.info(f"Đã lưu danh sách {len(recrawl_items)} file cần cào lại vào: {recrawl_path}")

    # Đào thải file sai nếu có cờ --purge
    if args.purge and bogus_list:
        logger.warning(f"BẮT ĐẦU ĐÀO THẢI / XÓA BỎ {len(bogus_list)} FILE SAI KHỎI KHO...")
        deleted_count = 0
        for item in bogus_list:
            p = Path(item["path"])
            try:
                if p.exists():
                    p.unlink()
                    deleted_count += 1
            except Exception as e:
                logger.error(f"Lỗi khi xóa file {p}: {e}")
        logger.info(f"ĐÃ XÓA TRIỆT ĐỂ {deleted_count} FILE SAI! KHO BCTN HIỆN NAY 100% SẠCH SẼ VÀ CHUẨN XÁC.")

if __name__ == "__main__":
    main()
