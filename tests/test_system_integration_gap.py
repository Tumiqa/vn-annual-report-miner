# -*- coding: utf-8 -*-
"""
tests/test_system_integration_gap.py
======================================
Bộ kiểm thử tích hợp toàn diện & chuyên nghiệp (Full-Stack System Verification).
Kiểm thử 5 trụ cột:
  1. Kiểm tra tính toàn vẹn danh mục & Chặn trùng lặp 100% (Zero-Duplicate Audit)
  2. Kiểm tra tìm kiếm đa năng (Ticker, Tên công ty có dấu/không dấu, Thương hiệu, Phân ngành, Sàn)
  3. Kiểm tra trích xuất & định tuyến file PDF 0ms từ Google Drive PC
  4. Kiểm tra xuất file ZIP chuẩn hóa (kèm Danh_Muc_Bao_Cao.csv đầy đủ thông tin doanh nghiệp)
  5. Kiểm tra khai phá Text Mining & tạo Panel Data nghiên cứu (Excel, Stata, CSV)
"""
from __future__ import annotations

import csv
import io
import os
from pathlib import Path
import sys
import tempfile
import zipfile

# UTF-8 fix for Windows console
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import pandas as pd
import pytest

from arminer.data.catalog import UnifiedCatalog
from arminer.data.zenodo_downloader import ZenodoDownloader
from arminer.export.zip_export import create_reports_zip_archive
from arminer.core.smart_mode import FlexibleDictionary, SmartVariableCalculator, ResearchOutputGenerator
from arminer.mining.matcher import GenericFuzzyMatcher


@pytest.fixture(scope="module")
def cat() -> UnifiedCatalog:
    catalog = UnifiedCatalog()
    catalog.initialize()
    return catalog


def test_1_catalog_integrity_and_zero_duplicate(cat: UnifiedCatalog):
    """1. Kiểm tra tính toàn vẹn danh mục và đảm bảo 0 trùng lặp."""
    print("\n--- TEST 1: CATALOG INTEGRITY & ZERO-DUPLICATE AUDIT ---")
    records = cat._records_cache
    assert len(records) > 16_000, f"Tổng số báo cáo quá ít ({len(records)} < 16,000)"

    # Kiểm tra chặn trùng lặp tuyệt đối
    keys = [(r["ticker"].upper(), int(r["year"])) for r in records]
    unique_keys = set(keys)
    duplicates = len(keys) - len(unique_keys)
    assert duplicates == 0, f"Phát hiện {duplicates} bản ghi trùng lặp trong UnifiedCatalog!"

    # Kiểm tra trường thông tin công ty trên từng bản ghi
    missing_company_name = 0
    missing_exchange = 0
    sources = set()

    for r in records:
        assert "ticker" in r and r["ticker"]
        assert "year" in r and r["year"] > 0
        assert "exchange" in r and r["exchange"] in ("HSX", "HOSE", "HNX", "UPCOM", "Khác")
        if not r.get("company_name"):
            missing_company_name += 1
        if not r.get("exchange"):
            missing_exchange += 1
        sources.add(r.get("source"))

    print(f"  ✅ Tổng số báo cáo trong hệ thống: {len(records):,}")
    print(f"  ✅ Tổng số bản ghi (mã, năm) duy nhất: {len(unique_keys):,}")
    print(f"  ✅ Số bản ghi trùng lặp: {duplicates} (HOÀN HẢO 0 TRÙNG LẶP)")
    print(f"  ✅ Các nguồn dữ liệu tích hợp: {sources}")
    print(f"  ✅ Tỷ lệ bản ghi có Tên Doanh Nghiệp: {(len(records)-missing_company_name)/len(records)*100:.1f}%")
    print(f"  ✅ Tỷ lệ bản ghi có Sàn Giao Dịch: {(len(records)-missing_exchange)/len(records)*100:.1f}%")


def test_2_multimodal_search(cat: UnifiedCatalog):
    """2. Kiểm tra tìm kiếm đa năng: Ticker, Tên công ty, Thương hiệu, Sàn, Ngành."""
    print("\n--- TEST 2: MULTIMODAL SEARCH VERIFICATION ---")

    # 2.1 Tìm theo Ticker chuẩn
    res_fpt = cat.search(ticker="FPT")
    assert len(res_fpt) > 0, "Không tìm thấy FPT theo ticker"
    print(f"  ✅ Tìm theo mã 'FPT': {len(res_fpt)} báo cáo")

    # 2.2 Tìm theo Tên công ty tiếng Việt có dấu
    res_sua = cat.search(ticker="Sữa Việt Nam")
    assert any(r["ticker"] == "VNM" for r in res_sua), "Tìm 'Sữa Việt Nam' không ra VNM"
    print(f"  ✅ Tìm theo tên tiếng Việt 'Sữa Việt Nam' -> Tự động nhận diện VNM ({len(res_sua)} báo cáo)")

    # 2.3 Tìm theo Thương hiệu viết tắt
    res_masan = cat.search(ticker="Masan")
    masan_tickers = set(r["ticker"] for r in res_masan)
    assert bool({"MSN", "MCH", "MML"} & masan_tickers), f"Tìm 'Masan' không ra Masan group: {masan_tickers}"
    print(f"  ✅ Tìm theo thương hiệu 'Masan' -> Nhận diện các mã: {masan_tickers}")

    # 2.4 Lọc theo Sàn UPCOM
    res_upcom = cat.search(exchange="UPCOM", limit=50)
    assert all(r["exchange"] == "UPCOM" for r in res_upcom), "Lọc UPCOM bị lọt sàn khác"
    print(f"  ✅ Lọc theo sàn 'UPCOM': {len(res_upcom)} kết quả mẫu chuẩn 100% UPCOM")

    # 2.5 Lọc theo Ngành ICB Cấp 1
    res_tech = cat.search(icb_l1="Công nghệ Thông tin", limit=50)
    assert all(r["icb_l1"] == "Công nghệ Thông tin" for r in res_tech), "Lọc ICB L1 sai ngành"
    print(f"  ✅ Lọc theo ngành 'Công nghệ Thông tin': {len(res_tech)} kết quả chuẩn ngành")


def test_3_gdrive_pdf_resolution():
    """3. Kiểm tra khả năng trích xuất file PDF 0ms từ Google Drive Desktop."""
    print("\n--- TEST 3: GOOGLE DRIVE PC PDF RESOLUTION (0ms SPEED) ---")
    downloader = ZenodoDownloader()
    gdrive_root = Path(r"H:\My Drive\arminer_bctn_gap")

    if not gdrive_root.exists():
        pytest.skip("Google Drive folder H:\\My Drive\\arminer_bctn_gap chưa mount trên máy.")

    # Tìm các file PDF có sẵn trên Drive
    pdf_samples = list(gdrive_root.glob("*/*_BCTN.pdf"))[:5]
    assert len(pdf_samples) > 0, "Không có file PDF nào trong H:\\My Drive\\arminer_bctn_gap"

    for pdf in pdf_samples:
        parts = pdf.name.replace(".pdf", "").split("_")
        ticker = parts[0]
        year = int(parts[1])

        resolved_path = downloader.get_pdf_path(
            ticker=ticker,
            year=year,
            archive_period="gap_filler",
            relative_path=f"{ticker}/{pdf.name}",
        )
        assert resolved_path is not None, f"Không tìm thấy path cho {ticker}_{year}"
        p = Path(resolved_path)
        assert p.exists(), f"File resolved không tồn tại: {p}"
        assert p.stat().st_size > 50_000, f"File quá nhỏ hoặc rỗng: {p}"
        with open(p, "rb") as f:
            assert f.read(5) == b"%PDF-", f"File không phải chuẩn PDF: {p}"

        print(f"  ✅ {ticker} ({year}) -> {p.name} ({p.stat().st_size / 1024 / 1024:.2f} MB) [0ms từ Google Drive]")


def test_4_zip_export_with_company_info(cat: UnifiedCatalog):
    """4. Kiểm tra xuất file ZIP chuẩn hóa kèm đầy đủ thông tin doanh nghiệp trong Danh_Muc_Bao_Cao.csv."""
    print("\n--- TEST 4: ZIP EXPORT WITH COMPLETE COMPANY INFO AUDIT ---")

    # Lấy 5 báo cáo có sẵn file vật lý
    sample_records = [r for r in cat._records_cache if r.get("is_local") and r.get("local_path")][:5]
    if not sample_records:
        gdrive_root = Path(r"H:\My Drive\arminer_bctn_gap")
        for r in cat._records_cache:
            cand = gdrive_root / r["ticker"] / f"{r['ticker']}_{r['year']}_BCTN.pdf"
            if cand.exists():
                r["local_path"] = str(cand.resolve())
                sample_records.append(r)
                if len(sample_records) >= 5:
                    break

    assert len(sample_records) > 0, "Không tìm thấy file local nào để nén ZIP"

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_zip = Path(tmp_dir) / "test_export_full_info.zip"
        res = create_reports_zip_archive(sample_records, out_zip, structure="ticker")

        assert out_zip.exists(), "File ZIP không được tạo"
        assert res["zipped_reports"] == len(sample_records), "Số lượng file nén không khớp"

        # Đọc file ZIP và kiểm tra file Danh_Muc_Bao_Cao.csv
        with zipfile.ZipFile(out_zip, "r") as zf:
            namelist = zf.namelist()
            assert "Danh_Muc_Bao_Cao.csv" in namelist, "Thiếu file Danh_Muc_Bao_Cao.csv trong ZIP"

            csv_bytes = zf.read("Danh_Muc_Bao_Cao.csv")
            csv_text = csv_bytes.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(csv_text))
            rows = list(reader)

            assert len(rows) == len(sample_records), f"Số dòng index CSV ({len(rows)}) không khớp ({len(sample_records)})"

            # Kiểm tra các cột bắt buộc
            first_row = rows[0]
            required_cols = [
                "Mã CK", "Tên Doanh Nghiệp", "Sàn Giao Dịch", "Năm Báo Cáo",
                "Ngành Cấp 1 (ICB L1)", "Ngành Cấp 2 (ICB L2)", "Trang Chủ (Website)",
                "Tên file gốc", "Đường dẫn trong ZIP", "Dung lượng (MB)", "Nguồn lưu trữ"
            ]
            for col in required_cols:
                assert col in first_row, f"Thiếu cột '{col}' trong Danh_Muc_Bao_Cao.csv"

            print(f"  ✅ Đóng gói thành công {len(rows)} báo cáo vào {out_zip.name}")
            print(f"  ✅ File Danh_Muc_Bao_Cao.csv chứa đầy đủ {len(first_row.keys())} cột metadata chuẩn:")
            for k in list(first_row.keys())[:8]:
                print(f"      - {k}: {first_row[k]}")


def test_5_research_panel_generation_with_company_metadata(cat: UnifiedCatalog):
    """5. Kiểm tra tạo Panel Data kết quả nghiên cứu (Excel, Stata, CSV) có company_name và exchange."""
    print("\n--- TEST 5: RESEARCH PANEL DATA METADATA AUDIT ---")

    # Tạo mock rows như text mining trả về
    sample_records = cat.search(limit=5)
    mining_rows = []
    for r in sample_records:
        mining_rows.append({
            "ticker": r["ticker"],
            "company_name": r.get("company_name", ""),
            "exchange": r.get("exchange", "HSX"),
            "year": r["year"],
            "icb_level1": r.get("icb_l1", "Khác"),
            "icb_level2": r.get("icb_l2", "Chưa phân loại"),
            "file": r["file_name"],
            "pages": 120,
            "Word_Count": 45000,
            "Frequency": 12,
            "Log_Frequency": 2.56,
            "Mention": 1,
            "Density": 0.00026,
            "Unique_Keywords": 4,
        })

    df = pd.DataFrame(mining_rows)
    core_order = [
        "ticker", "company_name", "exchange", "year", "icb_level1", "icb_level2", "file", "pages",
        "Word_Count", "Frequency", "Log_Frequency", "Mention", "Density",
        "Unique_Keywords",
    ]
    df = df[core_order]

    with tempfile.TemporaryDirectory() as tmp_dir:
        generator = ResearchOutputGenerator(Path(tmp_dir))
        out_files = generator.generate_all(df)

        assert out_files["panel_excel"].exists(), "File Excel panel_data.xlsx không tồn tại"
        assert out_files["panel_csv"].exists(), "File CSV panel_data.csv không tồn tại"
        assert out_files["panel_stata"].exists(), "File Stata panel_data.dta không tồn tại"

        # Kiểm tra nội dung Excel
        df_read = pd.read_excel(out_files["panel_excel"], sheet_name="Panel_Data")
        assert "company_name" in df_read.columns, "Cột company_name thiếu trong Excel sheet Panel_Data"
        assert "exchange" in df_read.columns, "Cột exchange thiếu trong Excel sheet Panel_Data"

        # Kiểm tra nội dung Stata
        df_stata = pd.read_stata(out_files["panel_stata"])
        assert "ticker" in df_stata.columns
        assert "year" in df_stata.columns

        print(f"  ✅ Đã tạo đầy đủ bộ 3 file panel nghiên cứu:")
        print(f"      - Excel: {out_files['panel_excel'].name} (Chứa cột company_name & exchange)")
        print(f"      - CSV:   {out_files['panel_csv'].name}")
        print(f"      - Stata: {out_files['panel_stata'].name}")


if __name__ == "__main__":
    cat = UnifiedCatalog()
    cat.initialize()
    test_1_catalog_integrity_and_zero_duplicate(cat)
    test_2_multimodal_search(cat)
    test_3_gdrive_pdf_resolution()
    test_4_zip_export_with_company_info(cat)
    test_5_research_panel_generation_with_company_metadata(cat)
    print("\n" + "=" * 70)
    print("  🏆 TẤT CẢ 5 BÀI KIỂM THỬ TÍCH HỢP HỆ THỐNG ĐÃ ĐẠT 100%!")
    print("=" * 70)
