# -*- coding: utf-8 -*-
"""
tests.test_bctn_validator
=========================
Unit tests for strict BCTN (Annual Report) validation across the system.
Ensures that only authentic, multi-page annual reports (>= 8 pages)
are indexed, displayed, searched, downloaded, or mined.
"""

import sys
from pathlib import Path
import pytest
import fitz

from arminer.data.bctn_validator import (
    MIN_BCTN_PAGES,
    is_valid_bctn_file,
    audit_bctn_file,
)


def test_min_bctn_pages_constant():
    assert MIN_BCTN_PAGES == 8


def test_non_existent_file():
    fake_path = Path("data/non_existent_bctn_12345.pdf")
    assert not is_valid_bctn_file(fake_path)
    audit = audit_bctn_file(fake_path)
    assert not audit["valid"]
    assert "không tồn tại" in audit["reason"]


def test_short_file_rejection(tmp_path):
    # Create dummy 3-page PDF
    pdf_path = tmp_path / "TEST_2023_BCTN.pdf"
    doc = fitz.open()
    for i in range(3):
        p = doc.new_page()
        p.insert_text((50, 50), f"Trang {i+1}: Công văn giải trình công bố thông tin")
    doc.save(str(pdf_path))
    doc.close()

    assert not is_valid_bctn_file(pdf_path)
    audit = audit_bctn_file(pdf_path)
    assert not audit["valid"]
    assert audit["page_count"] == 3
    assert "3 trang" in audit["reason"]


def test_administrative_letter_rejection(tmp_path):
    # Create 9-page PDF that is just an administrative cover letter
    pdf_path = tmp_path / "TEST_2023_CBTT.pdf"
    doc = fitz.open()
    for i in range(9):
        p = doc.new_page()
        p.insert_text((50, 50), f"CONG HOA XA HOI CHU NGHIA VIET NAM\nBAN CONG BO THONG TIN DINH KY\nKinh gui: So Giao dich Chung khoan TP.HCM\nTrang {i+1}")
    doc.save(str(pdf_path))
    doc.close()

    assert not is_valid_bctn_file(pdf_path)
    audit = audit_bctn_file(pdf_path)
    assert not audit["valid"]
    assert "văn bản hành chính" in audit["reason"].lower()


def test_genuine_multi_page_bctn(tmp_path):
    # Create genuine 15-page BCTN with proper chapters
    pdf_path = tmp_path / "TEST_2023_GENUINE_BCTN.pdf"
    doc = fitz.open()
    for i in range(25):
        p = doc.new_page()
        if i == 0:
            p.insert_text((50, 50), "BÁO CÁO THƯỜNG NIÊN NĂM 2023\nCÔNG TY CỔ PHẦN TẬP ĐOÀN TEST")
        elif i == 1:
            p.insert_text((50, 50), "MỤC LỤC\nI. Thông điệp Chủ tịch HĐQT\nII. Báo cáo tình hình hoạt động\nIII. Báo cáo tài chính")
        else:
            p.insert_text((50, 50), f"Phần {i}: Báo cáo chi tiết hoạt động kinh doanh sản xuất, nguồn nhân lực, lao động tổng số 2500 người.")
    doc.save(str(pdf_path))
    doc.close()

    assert is_valid_bctn_file(pdf_path)
    audit = audit_bctn_file(pdf_path)
    assert audit["valid"]
    assert audit["page_count"] == 25
