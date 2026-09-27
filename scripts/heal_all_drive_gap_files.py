# -*- coding: utf-8 -*-
"""
scripts/heal_all_drive_gap_files.py
===================================
Kiểm toán và cào bù trực tiếp toàn bộ các file nghi vấn (<= 4 trang)
ngay trong ổ H:\\My Drive\\arminer_bctn_gap.
"""

import json
import os
from pathlib import Path
import sys
import time

import fitz
import pandas as pd
from loguru import logger

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from arminer.data.report_healer import ReportHealer

sys.stdout.reconfigure(encoding="utf-8")

def main():
    healer = ReportHealer()
    if not healer.gdrive_root or not healer.gdrive_root.exists():
        logger.error("Không tìm thấy ổ H:\\My Drive\\arminer_bctn_gap!")
        sys.exit(1)

    drive_index_file = Path(__file__).resolve().parent.parent / "data" / "gap_filler" / "drive_index.json"
    if not drive_index_file.exists():
        logger.error(f"Không tìm thấy {drive_index_file}!")
        sys.exit(1)

    drive_data = json.loads(drive_index_file.read_text(encoding="utf-8"))
    logger.info(f"Tổng số file trong drive_index.json: {len(drive_data)}")

    # Lọc các file có dung lượng < 450 KB (ứng viên tiềm năng của tệp 1-2 trang)
    candidates = {}
    for k, v in drive_data.items():
        sz = v.get("file_size", 0)
        if 0 < sz < 450 * 1024:
            candidates[k] = v

    logger.info(f"Tìm thấy {len(candidates)} file nghi vấn dung lượng < 450 KB.")

    bogus_records = []
    healed_records = []

    for idx, (k, item) in enumerate(candidates.items(), 1):
        parts = k.rsplit("_", 1)
        if len(parts) != 2 or not parts[1].isdigit():
            continue
        ticker, year = parts[0].upper(), int(parts[1])
        fname = item.get("file_name", f"{ticker}_{year}_BCTN.pdf")
        fpath = healer.gdrive_root / ticker / fname

        if not fpath.exists():
            continue

        try:
            doc = fitz.open(fpath)
            pages = len(doc)
            doc.close()
        except Exception as e:
            logger.warning(f"Lỗi đọc {fpath.name}: {e}")
            pages = 0

        # Nếu số trang <= 4: Xác định chắc chắn là file cào nhầm công văn
        if pages <= 4:
            bogus_records.append({
                "ticker": ticker,
                "year": year,
                "file_name": fname,
                "pages": pages,
                "size_kb": round(fpath.stat().st_size / 1024, 1),
                "path": str(fpath),
            })
            logger.warning(f"[{idx}/{len(candidates)}] PHÁT HIỆN FILE CÀO NHẦM: {ticker}/{year} ({pages} trang, {round(fpath.stat().st_size/1024, 1)} KB)")

            # Kích hoạt cào bù ngay lập tức
            res = healer.heal_report(ticker, year)
            if res.get("status") == "healed":
                logger.info(f"  -> PHỤC HỒI THÀNH CÔNG: {ticker} ({year}) -> {res['new_pages']} trang (Nguồn: {res['source']})")
                healed_records.append({
                    "ticker": ticker,
                    "year": year,
                    "old_pages": pages,
                    "new_pages": res["new_pages"],
                    "source": res["source"],
                })
            else:
                logger.info(f"  -> Chưa tìm thấy bản thay thế cho {ticker}/{year} qua CafeF/IR")

    logger.info("\n=======================================================")
    logger.info(f"KẾT QUẢ KIỂM TOÁN VÀ CÀO BÙ:")
    logger.info(f"- Tổng số file nghi vấn đã kiểm tra: {len(candidates)}")
    logger.info(f"- Số file xác nhận bị cào nhầm (<= 4 trang): {len(bogus_records)}")
    logger.info(f"- Số file đã được cào bù bản chuẩn thành công: {len(healed_records)}")
    logger.info("=======================================================")

    out_dir = Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)
    if bogus_records:
        pd.DataFrame(bogus_records).to_csv(out_dir / "all_bogus_files_confirmed.csv", index=False, encoding="utf-8-sig")
    if healed_records:
        pd.DataFrame(healed_records).to_csv(out_dir / "healed_reports_summary.csv", index=False, encoding="utf-8-sig")

if __name__ == "__main__":
    main()
