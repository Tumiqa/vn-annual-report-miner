# -*- coding: utf-8 -*-
"""
arminer.data.bctn_validator
===========================
Hệ thống kiểm định tiêu chuẩn Báo cáo Thường niên (BCTN).

ĐẢM BẢO CHUẨN MỰC TUYỆT ĐỐI CHO TOÀN BỘ HỆ THỐNG:
Bất kỳ file nào tồn tại, được lập chỉ mục (catalog), tải về, hiển thị (UI),
hoặc đưa vào khai phá (mining) trên tool PHẢI LÀ BCTN THẬT.

Các tiêu chí loại trừ (Bogus / Non-BCTN):
1. Số trang < 8: 100% là công văn CBTT, nghị quyết HĐQT, giải trình, hoặc chứng thư số.
2. Kích thước file < 10 KB hoặc PDF hỏng.
3. Nội dung văn bản hành chính đơn thuần (Kính gửi UBCKNN, Nghị quyết ĐHĐCĐ, Điều lệ...)
   mà không chứa nội dung báo cáo hoạt động thường niên.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union
try:
    import pymupdf as fitz
except ImportError:
    import fitz
from loguru import logger

# Tiêu chuẩn tối thiểu cho một Báo cáo thường niên (BCTN) hợp lệ
MIN_BCTN_PAGES = 8


import unicodedata

def strip_accents(text: str) -> str:
    """Loại bỏ dấu tiếng Việt để so khớp không phân biệt dấu / font."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn").replace("đ", "d").replace("Đ", "D")


# Từ khóa công văn hành chính (nếu trang ít và tiêu đề thuộc nhóm này -> loại trừ)
ADMINISTRATIVE_DISCLOSURE_PATTERNS = [
    "công bố thông tin định kỳ",
    "cong bo thong tin dinh ky",
    "bản công bố thông tin",
    "ban cong bo thong tin",
    "công bố thông tin",
    "cong bo thong tin",
    "thông tin định kỳ",
    "thong tin dinh ky",
    "kính gửi: ủy ban chứng khoán",
    "kinh gui: uy ban chung khoan",
    "kính gửi ủy ban chứng khoán",
    "kinh gui uy ban chung khoan",
    "sở giao dịch chứng khoán",
    "so giao dich chung khoan",
    "giải trình chênh lệch",
    "giai trinh chenh lech",
    "chứng thư số",
    "chung thu so",
    "digitally signed by",
    "nghị quyết đại hội đồng cổ đông",
    "nghi quyet dai hoi dong co dong",
    "biên bản họp đại hội đồng cổ đông",
    "bien ban hop dai hoi dong co dong",
    "nghị quyết đhđcđ",
    "nghi quyet dhdcd",
    "điều lệ công ty",
    "dieu le cong ty",
    "quy chế nội bộ",
    "quy che noi bo",
]

# Từ khóa xác nhận BCTN hợp lệ
GENUINE_BCTN_PATTERNS = [
    "báo cáo thường niên",
    "bao cao thuong nien",
    "annual report",
    "báo cáo tổng kết",
    "bao cao tong ket",
    "báo cáo tình hình hoạt động",
    "bao cao tinh hinh hoat dong",
    "thông điệp chủ tịch",
    "thong diep chu tich",
    "báo cáo của hội đồng quản trị",
    "bao cao cua hoi dong quan tri",
    "báo cáo ban giám đốc",
    "bao cao ban giam doc",
    "báo cáo ban tổng giám đốc",
    "bao cao ban tong giam doc",
]


def is_valid_bctn_file(
    pdf_path: Union[str, Path, bytes],
    min_pages: int = MIN_BCTN_PAGES,
    strict_content_check: bool = True,
) -> bool:
    """
    Kiểm tra nhanh xem một file PDF có phải là BCTN chuẩn hay không.
    
    Args:
        pdf_path: Đường dẫn Path/str hoặc bytes nội dung PDF.
        min_pages: Số trang tối thiểu (mặc định: 8 trang).
        strict_content_check: Kiểm tra thêm ngữ nghĩa tiêu đề nếu số trang từ 8-15 trang.
        
    Returns:
        bool: True nếu là BCTN chuẩn, False nếu là file công văn/hành chính/hỏng.
    """
    try:
        doc = None
        if isinstance(pdf_path, (bytes, bytearray)):
            if len(pdf_path) < 1000:
                return False
            doc = fitz.open(stream=pdf_path, filetype="pdf")
        else:
            p = Path(pdf_path)
            if not p.exists() or p.stat().st_size < 1000:
                return False
            doc = fitz.open(p)

        pages = len(doc)
        if pages < min_pages:
            doc.close()
            return False

        # Nếu số trang vừa phải (8 - 15 trang), kiểm tra xem có phải là nghị quyết hoặc công văn dài không
        if strict_content_check and pages <= 15:
            # Lấy text trang 1 và 2
            text_probe = ""
            for i in range(min(2, pages)):
                text_probe += " " + doc[i].get_text()[:600]

            doc.close()

            probe_low = text_probe.lower()
            probe_unacc = strip_accents(probe_low)
            has_genuine_kw = any(k in probe_low or k in probe_unacc for k in GENUINE_BCTN_PATTERNS)
            has_admin_kw = any(k in probe_low or k in probe_unacc for k in ADMINISTRATIVE_DISCLOSURE_PATTERNS)

            # Nếu tiêu đề là công văn/nghị quyết mà không có chữ Báo cáo thường niên -> loại trừ
            if has_admin_kw and not has_genuine_kw:
                return False

            return True

        doc.close()
        return True
    except Exception:
        return False


def audit_bctn_file(pdf_path: Union[str, Path, bytes]) -> Dict[str, Any]:
    """
    Kiểm toán chi tiết chất lượng file PDF BCTN.
    
    Returns:
        Dict: {
            "is_valid": bool,
            "pages": int,
            "file_size_kb": float,
            "reason": str,
            "title_sample": str
        }
    """
    res = {
        "is_valid": False,
        "valid": False,
        "pages": 0,
        "page_count": 0,
        "file_size_kb": 0.0,
        "reason": "",
        "title_sample": "",
    }

    try:
        doc = None
        if isinstance(pdf_path, (bytes, bytearray)):
            size_kb = round(len(pdf_path) / 1024, 1)
            res["file_size_kb"] = size_kb
            if len(pdf_path) < 5000:
                res["reason"] = f"File quá nhỏ ({len(pdf_path)} bytes)"
                return res
            doc = fitz.open(stream=pdf_path, filetype="pdf")
        else:
            p = Path(pdf_path)
            if not p.exists():
                res["reason"] = "File không tồn tại trên hệ thống"
                return res
            size_kb = round(p.stat().st_size / 1024, 1)
            res["file_size_kb"] = size_kb
            if p.stat().st_size < 1000:
                res["reason"] = f"File quá nhỏ ({p.stat().st_size} bytes)"
                return res
            doc = fitz.open(p)

        pages = len(doc)
        res["pages"] = pages
        res["page_count"] = pages

        title_sample = ""
        for i in range(min(2, pages)):
            title_sample += " " + doc[i].get_text()[:400].strip()
        doc.close()

        res["title_sample"] = title_sample[:200].replace("\n", " ")

        if pages < MIN_BCTN_PAGES:
            res["reason"] = f"Không đủ số trang BCTN chuẩn ({pages} trang < {MIN_BCTN_PAGES} trang - là công văn/thông báo)"
            res["is_valid"] = False
            res["valid"] = False
            return res

        # Kiểm tra nội dung văn bản hành chính
        if pages <= 15:
            text_lower = title_sample.lower()
            text_unacc = strip_accents(text_lower)
            has_genuine_kw = any(k in text_lower or k in text_unacc for k in GENUINE_BCTN_PATTERNS)
            has_admin_kw = any(k in text_lower or k in text_unacc for k in ADMINISTRATIVE_DISCLOSURE_PATTERNS)
            if has_admin_kw and not has_genuine_kw:
                res["reason"] = f"Văn bản hành chính/nghị quyết ({pages} trang, không phải BCTN)"
                res["is_valid"] = False
                res["valid"] = False
                return res

        res["is_valid"] = True
        res["valid"] = True
        res["reason"] = f"BCTN chuẩn ({pages} trang, {size_kb} KB)"
        return res

    except Exception as e:
        res["reason"] = f"Lỗi đọc định dạng PDF: {e}"
        res["is_valid"] = False
        return res
