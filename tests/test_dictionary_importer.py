# -*- coding: utf-8 -*-
"""
tests/test_dictionary_importer.py
=================================
Unit tests for multi-format dictionary import & fault-tolerance:
1. Excel (.xlsx) parsing & header recognition
2. Word (.docx) table & paragraph parsing
3. Text (.txt, .csv) delimited & plain list parsing
4. Fault tolerance: skipping invalid rows, handling malformed weights, deduplication
5. Template download endpoints and manager integration
"""

import io
from pathlib import Path
import pytest
import pandas as pd
from fastapi.testclient import TestClient

from arminer.core.dictionary_importer import DictionaryFileImporter, ImportResult
from arminer.core.dictionary_manager import DictionaryManager
from arminer.ui.server import app

client = TestClient(app)
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "src" / "arminer" / "templates" / "sample_templates"


def test_excel_template_parsing():
    """Kiểm tra đọc file Excel mẫu .xlsx chuẩn."""
    excel_path = TEMPLATES_DIR / "mau_tu_dien_arminer.xlsx"
    assert excel_path.exists()
    content = excel_path.read_bytes()

    res = DictionaryFileImporter.parse_file(content, "mau_tu_dien_arminer.xlsx")
    assert res.success is True
    assert res.total_parsed == 8
    assert "CongNghe" in res.categories
    assert "ESG" in res.categories
    # Kiểm tra biến thể
    ai_entry = next((e for e in res.entries if "nhân tạo" in e["keyword"]), None)
    assert ai_entry is not None
    assert len(ai_entry["variants"]) >= 2
    assert ai_entry["weight"] == 1.5


def test_word_template_parsing():
    """Kiểm tra đọc file Word mẫu .docx chuẩn."""
    docx_path = TEMPLATES_DIR / "mau_tu_dien_arminer.docx"
    assert docx_path.exists()
    content = docx_path.read_bytes()

    res = DictionaryFileImporter.parse_file(content, "mau_tu_dien_arminer.docx")
    assert res.success is True
    assert res.total_parsed == 8
    assert "TaiChinh" in res.categories
    assert res.skipped_count == 0


def test_text_template_parsing():
    """Kiểm tra đọc file Text mẫu .txt chuẩn."""
    txt_path = TEMPLATES_DIR / "mau_tu_dien_arminer.txt"
    assert txt_path.exists()
    content = txt_path.read_bytes()

    res = DictionaryFileImporter.parse_file(content, "mau_tu_dien_arminer.txt")
    assert res.success is True
    assert res.total_parsed >= 10
    # Chứa cả các từ khóa đơn giản không có nhóm -> được gán nhóm 'Chung'
    assert "Chung" in res.categories


def test_excel_fault_tolerance():
    """Kiểm tra khả năng dung sai và xử lý lỗi nhập liệu trên Excel."""
    # Tạo DataFrame với nhiều lỗi nhập liệu cố ý:
    # - Hàng 0: Header gõ lệch
    # - Hàng 1: Bình thường
    # - Hàng 2: Trọng số gõ chữ 'rất cao' -> fallback 1.0
    # - Hàng 3: Trọng số dùng dấu phẩy '1,8' -> parse thành 1.8
    # - Hàng 4: Thiếu từ khóa chính (trống) -> bị bỏ qua
    # - Hàng 5: Từ khóa trùng lặp với Hàng 1 -> tự động gộp biến thể
    data = [
        ["Thuật ngữ nghiên cứu", "Các từ đồng nghĩa", "Lĩnh vực", "Trọng số"],
        ["trách nhiệm xã hội", "csr, dao duc kinh doanh", "XaHoi", "1.0"],
        ["năng lượng mặt trời", "solar energy", "MoiTruong", "rất cao"],
        ["tài chính xanh", "green finance", "TaiChinh", "1,8"],
        ["", "bien the mo ho", "Chung", "1.0"],
        ["trách nhiệm xã hội", "corporate social responsibility", "XaHoi", "1.5"],
    ]
    df = pd.DataFrame(data)
    buf = io.BytesIO()
    df.to_excel(buf, index=False, header=False)
    buf.seek(0)

    res = DictionaryFileImporter.parse_file(buf.read(), "test_dirty.xlsx")
    assert res.success is True
    assert res.total_parsed == 3  # 3 unique keywords: trách nhiệm xã hội, năng lượng mặt trời, tài chính xanh
    assert res.skipped_count == 1  # 1 hàng rỗng bị bỏ qua
    assert len(res.warnings) >= 3

    # Kiểm tra trọng số '1,8' được chuyển thành 1.8
    tcx = next(e for e in res.entries if e["keyword"] == "tài chính xanh")
    assert tcx["weight"] == 1.8

    # Kiểm tra trọng số 'rất cao' fallback về 1.0
    nlmt = next(e for e in res.entries if e["keyword"] == "năng lượng mặt trời")
    assert nlmt["weight"] == 1.0

    # Kiểm tra từ khóa trùng được gộp biến thể và lấy max weight 1.5
    tnxh = next(e for e in res.entries if e["keyword"] == "trách nhiệm xã hội")
    assert tnxh["weight"] == 1.5
    assert any("corporate social responsibility" in v.lower() for v in tnxh["variants"])


def test_text_plain_and_bullets():
    """Kiểm tra đọc file text thuần và danh sách gạch đầu dòng bullet points."""
    raw_txt = """
# Danh sách từ khóa nghiên cứu
- FinTech
* Ngân hàng số
1. Thanh toán không tiền mặt
• Ví điện tử
Ví điện tử | e-wallet | CongNghe | 2.0
"""
    res = DictionaryFileImporter.parse_file(raw_txt.encode("utf-8"), "keywords.txt")
    assert res.success is True
    assert res.total_parsed == 4
    # "Ví điện tử" được gộp với dòng có biến thể
    vdt = next(e for e in res.entries if "ví điện tử" in e["keyword"].lower())
    assert vdt["weight"] == 2.0
    assert "e-wallet" in vdt["variants"]


def test_dictionary_manager_import(tmp_path):
    """Kiểm tra hàm import_entries của DictionaryManager."""
    mgr = DictionaryManager(workspace_root=tmp_path)
    entries = [
        {"keyword": "robotics", "variants": ["tu dong hoa"], "category": "CongNghe", "weight": 1.2},
        {"keyword": "iot", "variants": ["internet of things"], "category": "CongNghe", "weight": 1.0},
    ]

    # Import mode 'new'
    d1 = mgr.import_entries("test_tech", "Tech Topic", entries, mode="new")
    assert len(d1["keywords"]) == 2

    # Import mode 'append'
    more_entries = [
        {"keyword": "ai", "variants": ["tri tue nhan tao"], "category": "CongNghe", "weight": 1.5},
        {"keyword": "iot", "variants": ["van vat ket noi"], "category": "CongNghe", "weight": 1.1},
    ]
    d2 = mgr.import_entries("test_tech", "Tech Topic", more_entries, mode="append")
    assert len(d2["keywords"]) == 3  # 2 ban đầu + 1 mới (iot đã merge)


def test_api_template_download():
    """Kiểm tra API tải template .xlsx, .docx, .txt."""
    r_xlsx = client.get("/api/dictionaries/templates/xlsx")
    assert r_xlsx.status_code == 200
    assert len(r_xlsx.content) > 1000

    r_docx = client.get("/api/dictionaries/templates/docx")
    assert r_docx.status_code == 200
    assert len(r_docx.content) > 1000

    r_txt = client.get("/api/dictionaries/templates/txt")
    assert r_txt.status_code == 200
    assert b"arminer" in r_txt.content


def test_api_upload_endpoint():
    """Kiểm tra API upload file từ điển."""
    txt_content = b"blockchain | chuoi khoi | Tech | 1.0\nsmart contract | hop dong thong minh | Tech | 1.2\n"
    files = {"file": ("test_upload.txt", txt_content, "text/plain")}
    data = {"mode": "new", "topic_name": "Test Upload Topic"}

    res = client.post("/api/dictionaries/upload", files=files, data=data)
    assert res.status_code == 200
    json_data = res.json()
    assert json_data["success"] is True
    assert "tech" in [c.lower() for c in json_data["categories"]]

