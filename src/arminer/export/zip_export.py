# -*- coding: utf-8 -*-
"""
arminer.export.zip_export
=========================
Dong goi va nen file bao cao thuong nien goc (PDF) vao file ZIP
co cau truc phan cap thu muc chuyen nghiep va kem file danh muc index CSV.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from loguru import logger


def sanitize_folder_name(name: Any) -> str:
    """Loai bo cac ky tu khong hop le trong ten thu muc."""
    if not name or pd_is_na(name):
        return "Chua_Phan_Loai"
    s = str(name).strip()
    # Loai bo ky tu cam trong Windows/Linux path: \ / : * ? " < > |
    s = re.sub(r'[\\/*?:"<>|]', "_", s)
    s = re.sub(r'\s+', '_', s)
    return s.strip("._") or "Chua_Phan_Loai"


def pd_is_na(val: Any) -> bool:
    return val is None or val == "" or str(val).lower() == "nan"


def create_reports_zip_archive(
    reports: List[Dict[str, Any]],
    output_zip_path: Path,
    structure: str = "ticker",
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, Any]:
    """
    Nen danh sach file bao cao thuong nien goc vao file ZIP theo phan cap thu muc.

    Parameters
    ----------
    reports : List[Dict[str, Any]]
        Danh sach bao cao, moi phan tu chua:
        - local_path: duong dan file PDF goc tren o dia
        - ticker: ma chung khoan
        - year: nam bao cao
        - file_name: ten file goc
        - icb_l1: nganh cap 1
        - icb_l2: nganh cap 2
        - source: nguon (Zenodo / Local)
    output_zip_path : Path
        Duong dan luu file .zip
    structure : str
        Kieu phan cap thu muc:
        - 'ticker': {TICKER}/{file_name} (khuyen nghi)
        - 'sector': {ICB_L1}/{TICKER}/{file_name}
        - 'year': {YEAR}/{TICKER}/{file_name}
    progress_callback : Optional[Callable]
        Callback cap nhat tien do (current, total, message)

    Returns
    -------
    Dict[str, Any]
        Thong tin tong ket qua trinh nen zip.
    """
    output_zip_path.parent.mkdir(parents=True, exist_ok=True)
    total = len(reports)
    index_rows = []
    used_arcnames = set()
    total_uncompressed_bytes = 0
    zipped_count = 0

    with zipfile.ZipFile(output_zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for idx, r in enumerate(reports, 1):
            local_path_str = r.get("local_path")
            if not local_path_str:
                continue
            src_file = Path(local_path_str)
            if not src_file.exists() or src_file.stat().st_size < 100:
                logger.warning(f"File khong ton tai hoac rong: {src_file}")
                continue

            ticker = sanitize_folder_name(r.get("ticker") or "KHAC").upper()
            year = str(r.get("year") or "Chua_Xac_Dinh")
            sector_l1 = sanitize_folder_name(r.get("icb_l1") or "Chua_Phan_Loai")
            sector_l2 = sanitize_folder_name(r.get("icb_l2") or "Khac")
            original_filename = r.get("file_name") or src_file.name

            # Xay dung duong dan noi bo trong file ZIP theo phan cap
            if structure == "sector":
                folder_path = f"{sector_l1}/{ticker}"
            elif structure == "year":
                folder_path = f"{year}/{ticker}"
            else:  # mac dinh: ticker
                folder_path = ticker

            arcname = f"{folder_path}/{original_filename}"

            # Xu ly trung ten neu co
            if arcname in used_arcnames:
                stem = Path(original_filename).stem
                suffix = Path(original_filename).suffix
                dup_idx = 1
                while f"{folder_path}/{stem}_{dup_idx}{suffix}" in used_arcnames:
                    dup_idx += 1
                arcname = f"{folder_path}/{stem}_{dup_idx}{suffix}"

            used_arcnames.add(arcname)
            file_size = src_file.stat().st_size
            total_uncompressed_bytes += file_size

            # Ghi file PDF vao archive ZIP
            zf.write(src_file, arcname=arcname)
            zipped_count += 1

            # Luu metadata cho file index CSV
            index_rows.append({
                "Mã CK": ticker,
                "Năm": year,
                "Ngành cấp 1": r.get("icb_l1") or "",
                "Ngành cấp 2": r.get("icb_l2") or "",
                "Tên file gốc": original_filename,
                "Đường dẫn trong ZIP": arcname,
                "Dung lượng (KB)": f"{file_size / 1024:.1f}",
                "Nguồn lưu trữ": r.get("source") or "Zenodo",
                "Trạng thái": "Thành công",
            })

            if progress_callback:
                progress_callback(idx, total, f"Đang nén [{idx}/{total}]: {ticker} ({year})")

        # Tao file Danh_Muc_Bao_Cao.csv o thu muc goc cua file ZIP
        csv_buffer = io.StringIO()
        # Ghi UTF-8 BOM de Excel mo truc tiep khong bi loi font tieng Viet
        csv_buffer.write("\ufeff")
        if index_rows:
            fieldnames = list(index_rows[0].keys())
            writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(index_rows)
        else:
            csv_buffer.write("Thông báo\nKhông có báo cáo nào được nén.\n")

        zf.writestr("Danh_Muc_Bao_Cao.csv", csv_buffer.getvalue().encode("utf-8"))

    zip_size = output_zip_path.stat().st_size if output_zip_path.exists() else 0

    return {
        "zip_path": output_zip_path,
        "zip_filename": output_zip_path.name,
        "total_reports": total,
        "zipped_reports": zipped_count,
        "total_uncompressed_mb": round(total_uncompressed_bytes / (1024 * 1024), 2),
        "zip_size_mb": round(zip_size / (1024 * 1024), 2),
        "structure": structure,
    }
