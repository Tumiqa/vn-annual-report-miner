# -*- coding: utf-8 -*-
"""
scripts/audit_and_heal_reports.py
=================================
Công cụ tự động kiểm toán chất lượng kho BCTN và phục hồi các file bị cào nhầm (1-2 trang).

Sử dụng:
  # 1. Kiểm tra 1 mã cụ thể:
  python scripts/audit_and_heal_reports.py --ticker PNJ

  # 2. Kiểm toán nhanh toàn bộ kho (phát hiện các file <= 4 trang):
  python scripts/audit_and_heal_reports.py --audit

  # 3. Tự động cào bù và thay thế tất cả file lỗi phát hiện được:
  python scripts/audit_and_heal_reports.py --heal-all
"""

import argparse
import json
import os
from pathlib import Path
import sys
import time

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from loguru import logger
import pandas as pd
from arminer.data.report_healer import ReportHealer

def main():
    parser = argparse.ArgumentParser(description="Kiểm toán chất lượng BCTN và cào bù tự động")
    parser.add_argument("--ticker", type=str, help="Kiểm tra và phục hồi 1 mã cụ thể (VD: PNJ, AAA)")
    parser.add_argument("--year", type=int, help="Năm cụ thể (tùy chọn)")
    parser.add_argument("--audit", action="store_true", help="Quét toàn bộ kho để tìm file cào nhầm (<= 4 trang)")
    parser.add_argument("--heal-all", action="store_true", help="Tự động cào bù và thay thế tất cả file cào nhầm")
    parser.add_argument("--max-tickers", type=int, default=100, help="Số lượng mã tối đa quét audit (mặc định 100)")
    args = parser.parse_args()

    healer = ReportHealer()
    if not healer.gdrive_root or not healer.gdrive_root.exists():
        logger.error("Không tìm thấy thư mục kho dữ liệu Google Drive (H:\\My Drive\\arminer_bctn_gap)!")
        return

    logger.info(f"Kho dữ liệu mục tiêu: {healer.gdrive_root}")

    # Chế độ 1: Kiểm tra 1 mã cụ thể
    if args.ticker:
        t_dir = healer.gdrive_root / args.ticker.upper()
        if not t_dir.exists():
            logger.warning(f"Không tìm thấy thư mục {args.ticker.upper()} trong kho!")
            return

        pdf_files = list(t_dir.glob("*.pdf"))
        logger.info(f"--- KIỂM TOÁN MÃ {args.ticker.upper()} ({len(pdf_files)} file) ---")
        for f in sorted(pdf_files):
            # Parse year
            import re
            m = re.search(r'(20\d{2})', f.name)
            year = int(m.group(1)) if m else None
            if args.year and year != args.year:
                continue

            audit = healer.audit_pdf(f)
            status_tag = "[LỖI/CÀO NHẦM]" if audit["is_bogus"] else "[CHUẨN]"
            logger.info(f"  {status_tag} {f.name}: {audit['pages']} trang ({audit['file_size_kb']} KB) - {audit['reason']}")

            if audit["is_bogus"] and year:
                logger.info(f"  -> Kích hoạt cào bù phục hồi cho {args.ticker.upper()} ({year})...")
                res = healer.heal_report(args.ticker.upper(), year)
                logger.info(f"  -> Kết quả: {res['status']} ({res['message']})")

        return

    # Chế độ 2: Quét audit diện rộng
    logger.info("Bắt đầu kiểm toán chất lượng kho dữ liệu BCTN...")
    ticker_dirs = [d for d in healer.gdrive_root.iterdir() if d.is_dir() and len(d.name) in (3, 4)]
    logger.info(f"Tìm thấy tổng cộng {len(ticker_dirs)} thư mục mã chứng khoán.")

    limit_dirs = ticker_dirs[:args.max_tickers] if args.max_tickers else ticker_dirs
    suspicious_list = []
    total_scanned = 0

    for idx, d in enumerate(limit_dirs, 1):
        for f in d.glob("*.pdf"):
            total_scanned += 1
            audit = healer.audit_pdf(f)
            if audit["is_bogus"]:
                import re
                m = re.search(r'(20\d{2})', f.name)
                yr = int(m.group(1)) if m else None
                item = {
                    "ticker": d.name,
                    "year": yr,
                    "file_name": f.name,
                    "pages": audit["pages"],
                    "size_kb": audit["file_size_kb"],
                    "reason": audit["reason"],
                    "path": str(f),
                }
                suspicious_list.append(item)
                logger.warning(f"[{total_scanned}] PHÁT HIỆN FILE BẤT THƯỜNG: {d.name}/{f.name} ({audit['pages']} trang, {audit['size_kb']} KB)")

                if args.heal_all and yr:
                    res = healer.heal_report(d.name, yr)
                    logger.info(f"  -> Cào bù {d.name}/{yr}: {res['status']} ({res['message']})")

    # Xuất báo cáo
    out_dir = Path(__file__).resolve().parent.parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "audit_bogus_reports.csv"

    if suspicious_list:
        df = pd.DataFrame(suspicious_list)
        df.to_csv(out_csv, index=False, encoding="utf-8-sig")
        logger.info(f"\n==========================================")
        logger.info(f"KẾT QUẢ KIỂM TOÁN:")
        logger.info(f"- Tổng số file đã quét: {total_scanned}")
        logger.info(f"- Số file bị cào nhầm (<= 4 trang): {len(suspicious_list)} ({(len(suspicious_list)/total_scanned)*100:.2f}%)")
        logger.info(f"- Đã lưu chi tiết danh sách vào: {out_csv}")
        logger.info(f"==========================================")
    else:
        logger.info(f"Tất cả {total_scanned} file đã quét đều đạt chuẩn!")

if __name__ == "__main__":
    main()
