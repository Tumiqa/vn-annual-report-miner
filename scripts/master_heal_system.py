# -*- coding: utf-8 -*-
"""
scripts/master_heal_system.py
=============================
Hệ thống kiểm toán toàn diện & tự động bổ sung toàn bộ:
1. Những file BCTN sai (công văn, CBTT, <= 7 trang) -> Cào lại bản chuẩn BCTN (>= 8 trang).
2. Những file BCTN còn thiếu của các mã niêm yết trong giai đoạn nghiên cứu (2015-2024) -> Bổ sung vào hệ thống.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import io
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
from typing import Any, Dict, List, Set, Tuple

# Set utf-8 stdout for Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from loguru import logger
from arminer.data.report_healer import ReportHealer
from arminer.data.bctn_validator import is_valid_bctn_file, audit_bctn_file

DRIVE_INDEX_PATH = Path(__file__).resolve().parent.parent / "data" / "gap_filler" / "drive_index.json"
WEBSITES_DB_PATH = Path(__file__).resolve().parent.parent / "src" / "arminer" / "data" / "fixtures" / "company_websites.json"

_LOCK = threading.Lock()


def load_drive_index() -> Dict[str, Any]:
    if DRIVE_INDEX_PATH.exists():
        try:
            return json.loads(DRIVE_INDEX_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_drive_index(d: Dict[str, Any]):
    with _LOCK:
        DRIVE_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        DRIVE_INDEX_PATH.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def get_trashed_bogus_targets(healer: ReportHealer) -> List[Tuple[str, int]]:
    """Lấy danh sách các file cào sai đã bị cách ly vào .trash_bogus_notices."""
    targets = []
    if healer.gdrive_root:
        trash_dir = healer.gdrive_root / ".trash_bogus_notices"
        if trash_dir.exists():
            for f in trash_dir.glob("*_bogus*.pdf"):
                m = re.match(r"^([A-Z0-9]+)_(\d{4})_BCTN", f.name)
                if m:
                    t, y = m.group(1), int(m.group(2))
                    # Chỉ cào bù nếu trong thư mục chính chưa có file chuẩn
                    main_p = healer.gdrive_root / t / f"{t}_{y}_BCTN.pdf"
                    if not main_p.exists() or not is_valid_bctn_file(main_p):
                        targets.append((t, y))
    return sorted(list(set(targets)))


def get_missing_targets(healer: ReportHealer, target_years: List[int]) -> List[Tuple[str, int]]:
    """Xác định các năm còn thiếu BCTN của các mã niêm yết."""
    if not WEBSITES_DB_PATH.exists():
        return []

    websites_data = json.loads(WEBSITES_DB_PATH.read_text(encoding="utf-8"))
    all_tickers = sorted(list(websites_data.keys()))
    drive_data = load_drive_index()

    existing_keys = set()
    for k in drive_data.keys():
        parts = k.rsplit("_", 1)
        if len(parts) == 2 and parts[1].isdigit():
            existing_keys.add((parts[0].upper(), int(parts[1])))

    missing_pairs = []
    for t in all_tickers:
        for y in target_years:
            if (t, y) not in existing_keys:
                missing_pairs.append((t, y))

    return missing_pairs


def run_healing_worker(healer: ReportHealer, ticker: str, year: int, force: bool = False) -> Dict[str, Any]:
    try:
        res = healer.heal_report(ticker, year, force=force)
        return res
    except Exception as e:
        return {
            "ticker": ticker,
            "year": year,
            "status": "error",
            "message": str(e),
        }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Master BCTN Healing & Gap-Filling Pipeline")
    parser.add_argument("--heal-bogus-only", action="store_true", help="Chỉ phục hồi các file bị cào sai (<= 7 trang)")
    parser.add_argument("--missing-only", action="store_true", help="Chỉ bổ sung các file còn thiếu")
    parser.add_argument("--max-missing", type=int, default=500, help="Số lượng file thiếu tối đa cần bổ sung trong 1 đợt")
    parser.add_argument("--workers", type=int, default=4, help="Số luồng song song (mặc định 4)")
    args = parser.parse_args()

    healer = ReportHealer()
    logger.info(f"=== BẮT ĐẦU CHƯƠNG TRÌNH MASTER BỔ SUNG & PHỤC HỒI BCTN TOÀN HỆ THỐNG ===")
    logger.info(f"Google Drive Path: {healer.gdrive_root}")

    # =========================================================================
    # PHẦN 1: PHỤC HỒI TẤT CẢ FILE BCTN SAI / BOGUS (< 8 TRANG)
    # =========================================================================
    healed_bogus_count = 0
    if not args.missing_only:
        bogus_targets = get_trashed_bogus_targets(healer)
        logger.info(f"\n[PHẦN 1] Phát hiện {len(bogus_targets)} file BCTN cào sai/công văn cần thay thế bằng BCTN chuẩn:")
        for t, y in bogus_targets[:10]:
            logger.info(f"  - Cần cào chuẩn: {t} ({y})")
        if len(bogus_targets) > 10:
            logger.info(f"  ... và {len(bogus_targets) - 10} file khác.")

        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            future_to_item = {
                executor.submit(run_healing_worker, healer, t, y, True): (t, y)
                for t, y in bogus_targets
            }
            for fut in as_completed(future_to_item):
                t, y = future_to_item[fut]
                res = fut.result()
                if res.get("status") == "healed":
                    healed_bogus_count += 1
                    logger.success(f"[BOGUS HEALED] {t}/{y}: {res.get('new_pages')} trang ({res.get('source')})")
                elif res.get("status") == "already_healthy":
                    logger.info(f"[HEALTHY] {t}/{y}: Đã có bản chuẩn ({res.get('old_pages')} trang)")
                else:
                    logger.warning(f"[UNRESOLVED] {t}/{y}: {res.get('message')}")

        logger.info(f"[PHẦN 1 HOÀN TẤT] Đã phục hồi và thay thế thành công: {healed_bogus_count}/{len(bogus_targets)} file cào sai.\n")

    if args.heal_bogus_only:
        logger.info("Chế độ --heal-bogus-only hoàn tất.")
        return

    # =========================================================================
    # PHẦN 2: BỔ SUNG CÁC FILE BCTN CÒN THIẾU CỦA CÁC MÃ (2015 - 2024)
    # =========================================================================
    target_years = list(range(2015, 2025))
    missing_targets = get_missing_targets(healer, target_years)
    logger.info(f"[PHẦN 2] Tổng số báo cáo còn thiếu trên hệ thống (2015-2024): {len(missing_targets)}")

    limit_missing = missing_targets[:args.max_missing]
    logger.info(f"Tiến hành bổ sung đợt này ({len(limit_missing)} báo cáo) với {args.workers} luồng song song...")

    added_missing_count = 0
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_item = {
            executor.submit(run_healing_worker, healer, t, y, False): (t, y)
            for t, y in limit_missing
        }
        for fut in as_completed(future_to_item):
            t, y = future_to_item[fut]
            res = fut.result()
            if res.get("status") == "healed":
                added_missing_count += 1
                logger.success(f"[BCTN ADDED] {t}/{y}: {res.get('new_pages')} trang ({res.get('source')})")

    logger.info(f"\n=======================================================")
    logger.info(f"TỔNG KẾT KẾT QUẢ BỔ SUNG & PHỤC HỒI BCTN:")
    logger.info(f"- Số file BCTN cào sai đã thay thế chuẩn: {healed_bogus_count}")
    logger.info(f"- Số file BCTN còn thiếu mới được bổ sung: {added_missing_count}")
    curr_d = load_drive_index()
    logger.info(f"- Tổng số BCTN chuẩn hiện có trong drive_index: {len(curr_d)}")
    logger.info(f"=======================================================\n")


if __name__ == "__main__":
    main()
