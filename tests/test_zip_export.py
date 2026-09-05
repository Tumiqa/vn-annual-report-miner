# -*- coding: utf-8 -*-
"""
Test suit cho arminer.export.zip_export
Kiem tra tinh nang dong goi va nen bao cao thuong nien goc vao file ZIP.
"""

import csv
import io
import zipfile
from pathlib import Path
import pytest

from arminer.export.zip_export import create_reports_zip_archive, sanitize_folder_name


def test_sanitize_folder_name():
    assert sanitize_folder_name("Ngân hàng & Dịch vụ tài chính") == "Ngân_hàng_&_Dịch_vụ_tài_chính"
    assert sanitize_folder_name("Test/Slash\\Backslash:Colon*Star?Question\"Quote<Less>Greater|Pipe") == "Test_Slash_Backslash_Colon_Star_Question_Quote_Less_Greater_Pipe"
    assert sanitize_folder_name(None) == "Chua_Phan_Loai"
    assert sanitize_folder_name("") == "Chua_Phan_Loai"
    assert sanitize_folder_name("nan") == "Chua_Phan_Loai"


def test_create_reports_zip_archive_structures(tmp_path):
    # Tao cac file PDF gia lap
    doc1 = tmp_path / "SSI_2023_BCTN.pdf"
    doc2 = tmp_path / "VNM_2023_BCTN.pdf"
    doc3 = tmp_path / "FPT_2022_BCTN.pdf"

    dummy_content = b"%PDF-1.4 simulated pdf content with sufficient bytes to exceed minimum size check" * 5
    doc1.write_bytes(dummy_content)
    doc2.write_bytes(dummy_content)
    doc3.write_bytes(dummy_content)

    reports = [
        {
            "local_path": str(doc1),
            "ticker": "SSI",
            "year": 2023,
            "file_name": "SSI_2023_BCTN.pdf",
            "icb_l1": "Dịch vụ tài chính",
            "icb_l2": "Chứng khoán",
            "source": "Zenodo",
        },
        {
            "local_path": str(doc2),
            "ticker": "VNM",
            "year": 2023,
            "file_name": "VNM_2023_BCTN.pdf",
            "icb_l1": "Hàng tiêu dùng",
            "icb_l2": "Thực phẩm và đồ uống",
            "source": "Zenodo",
        },
        {
            "local_path": str(doc3),
            "ticker": "FPT",
            "year": 2022,
            "file_name": "FPT_2022_BCTN.pdf",
            "icb_l1": "Công nghệ thông tin",
            "icb_l2": "Phần mềm & Dịch vụ",
            "source": "Zenodo",
        },
    ]

    # 1. Kiem tra cau truc 'ticker' (mac dinh: {Mã CK}/{Tên file})
    zip_ticker = tmp_path / "export_ticker.zip"
    res_ticker = create_reports_zip_archive(reports, zip_ticker, structure="ticker")
    assert res_ticker["zipped_reports"] == 3
    assert zip_ticker.exists()

    with zipfile.ZipFile(zip_ticker, "r") as zf:
        namelist = zf.namelist()
        assert "SSI/SSI_2023_BCTN.pdf" in namelist
        assert "VNM/VNM_2023_BCTN.pdf" in namelist
        assert "FPT/FPT_2022_BCTN.pdf" in namelist
        assert "Danh_Muc_Bao_Cao.csv" in namelist

        # Kiem tra noi dung file PDF trong ZIP khop chinh xac byte-for-byte
        assert zf.read("SSI/SSI_2023_BCTN.pdf") == dummy_content

        # Kiem tra file index Danh_Muc_Bao_Cao.csv
        csv_bytes = zf.read("Danh_Muc_Bao_Cao.csv")
        assert csv_bytes.startswith(b"\xef\xbb\xbf")  # UTF-8 BOM
        csv_text = csv_bytes.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(csv_text))
        rows = list(reader)
        assert len(rows) == 3
        tickers = {r["Mã CK"] for r in rows}
        assert tickers == {"SSI", "VNM", "FPT"}
        assert rows[0]["Trạng thái"] == "Thành công"

    # 2. Kiem tra cau truc 'sector' ({Ngành}/{Mã CK}/{Tên file})
    zip_sector = tmp_path / "export_sector.zip"
    res_sector = create_reports_zip_archive(reports, zip_sector, structure="sector")
    assert res_sector["zipped_reports"] == 3

    with zipfile.ZipFile(zip_sector, "r") as zf:
        namelist = zf.namelist()
        assert any(name.startswith("Dịch_vụ_tài_chính/SSI/") for name in namelist)
        assert any(name.startswith("Hàng_tiêu_dùng/VNM/") for name in namelist)
        assert any(name.startswith("Công_nghệ_thông_tin/FPT/") for name in namelist)
        assert "Danh_Muc_Bao_Cao.csv" in namelist

    # 3. Kiem tra cau truc 'year' ({Năm}/{Mã CK}/{Tên file})
    zip_year = tmp_path / "export_year.zip"
    res_year = create_reports_zip_archive(reports, zip_year, structure="year")
    assert res_year["zipped_reports"] == 3

    with zipfile.ZipFile(zip_year, "r") as zf:
        namelist = zf.namelist()
        assert "2023/SSI/SSI_2023_BCTN.pdf" in namelist
        assert "2023/VNM/VNM_2023_BCTN.pdf" in namelist
        assert "2022/FPT/FPT_2022_BCTN.pdf" in namelist
        assert "Danh_Muc_Bao_Cao.csv" in namelist


def test_create_reports_zip_duplicate_handling(tmp_path):
    # Kiem tra xu ly khi 2 bao cao trung ten trong cung 1 thu muc
    doc = tmp_path / "Report.pdf"
    doc.write_bytes(b"%PDF-1.4 file content dummy test" * 5)

    reports = [
        {"local_path": str(doc), "ticker": "SSI", "year": 2023, "file_name": "Report.pdf"},
        {"local_path": str(doc), "ticker": "SSI", "year": 2023, "file_name": "Report.pdf"},
    ]

    zip_out = tmp_path / "export_dups.zip"
    res = create_reports_zip_archive(reports, zip_out, structure="ticker")
    assert res["zipped_reports"] == 2

    with zipfile.ZipFile(zip_out, "r") as zf:
        namelist = zf.namelist()
        assert "SSI/Report.pdf" in namelist
        assert "SSI/Report_1.pdf" in namelist
