# -*- coding: utf-8 -*-
"""
arminer.export.financial_excel
==============================
Tao file Excel bao cao tai chinh chuyen nghiep:
- Tab Bao_Cao_Tai_Chinh: Trinh bay day du toan bo 700+ chi tieu, phan chia ro rang theo 13 nhom chuan muc:
    1. CĐKT. TÀI SẢN NGẮN HẠN
    2. CĐKT. TÀI SẢN DÀI HẠN
    3. CĐKT. NỢ PHẢI TRẢ NGẮN HẠN
    4. CĐKT. NỢ PHẢI TRẢ DÀI HẠN
    5. CĐKT. VỐN CHỦ SỞ HỮU
    6. KQKD. DOANH THU, CHI PHÍ, LỢI NHUẬN
    7. LCTT. DÒNG TIỀN TỪ HOẠT ĐỘNG KINH DOANH
    8. LCTT. DÒNG TIỀN TỪ HOẠT ĐỘNG ĐẦU TƯ
    9. LCTT. DÒNG TIỀN TỪ HOẠT ĐỘNG TÀI CHÍNH
    10. LCTT. DÒNG TIỀN THUẦN, TIỀN CUỐI KÌ
    11. NGOẠI BẢNG. A TÀI SẢN CỦA CTCK VÀ TÀI SẢN QUẢN LÝ THEO CAM KẾT
    12. NGOẠI BẢNG. B TÀI SẢN VÀ CÁC KHOẢN PHẢI TRẢ VỀ TÀI SẢN QUẢN LÝ CAM KẾT VỚI KHÁCH HÀNG
    13. THUYẾT MINH. CÁC LOẠI TÀI SẢN TÀI CHÍNH
- Tab Ty_So_Tai_Chinh: He thong chi so tai chinh toan dien chuan WiData (Kha nang sinh loi, Don bay & Thanh toan,
  Dac thu CTCK / Margin / Dau tu, Toc do tang truong YoY %, Quy mo & Dinh gia).
- Tab Panel_Data_Goc: Bang du lieu bang phang (Panel Data) chuan nghien cuu kinh te luong.
- Tab Codebook: Tu dien bien chi tiet.
- Tab Huong_Dan_VBA: Huong dan su dung bo loc va ma nguon VBA.
Xuat ca file .xlsx (chuan) va file .xlsm (tich hop Macro VBA va cac nut bam loc nhanh).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
import pandas as pd
from loguru import logger

# 13 Nhom chuan hoa bao cao tai chinh theo dung yeu cau
CATEGORY_ORDER = [
    "CĐKT. TÀI SẢN NGẮN HẠN",
    "CĐKT. TÀI SẢN DÀI HẠN",
    "CĐKT. NỢ PHẢI TRẢ NGẮN HẠN",
    "CĐKT. NỢ PHẢI TRẢ DÀI HẠN",
    "CĐKT. VỐN CHỦ SỞ HỮU",
    "KQKD. DOANH THU, CHI PHÍ, LỢI NHUẬN",
    "LCTT. DÒNG TIỀN TỪ HOẠT ĐỘNG KINH DOANH",
    "LCTT. DÒNG TIỀN TỪ HOẠT ĐỘNG ĐẦU TƯ",
    "LCTT. DÒNG TIỀN TỪ HOẠT ĐỘNG TÀI CHÍNH",
    "LCTT. DÒNG TIỀN THUẦN, TIỀN CUỐI KÌ",
    "NGOẠI BẢNG. A TÀI SẢN CỦA CTCK VÀ TÀI SẢN QUẢN LÝ THEO CAM KẾT",
    "NGOẠI BẢNG. B TÀI SẢN VÀ CÁC KHOẢN PHẢI TRẢ VỀ TÀI SẢN QUẢN LÝ CAM KẾT VỚI KHÁCH HÀNG",
    "THUYẾT MINH. CÁC LOẠI TÀI SẢN TÀI CHÍNH",
]
CATEGORIES = CATEGORY_ORDER

def classify_financial_item(code: str, name: str, stmt: str, order: int = 0) -> str:
    """Phan loai chi tieu vao dung 1 trong 13 nhom theo quy chuan ke toan Viet Nam."""
    c = str(code).lower()
    n = str(name).lower()

    # 1. Thuyet minh
    if "thuyet_minh" in c or "thuyết minh" in n:
        return "THUYẾT MINH. CÁC LOẠI TÀI SẢN TÀI CHÍNH"

    # 2. Ngoai bang
    if "ngoai_bang" in c or "ngoại bảng" in n:
        if any(k in c or k in n for k in ["khach_hang", "nha_dau_tu", "khách hàng", "nhà đầu tư", "phải trả", "phai_tra"]):
            return "NGOẠI BẢNG. B TÀI SẢN VÀ CÁC KHOẢN PHẢI TRẢ VỀ TÀI SẢN QUẢN LÝ CAM KẾT VỚI KHÁCH HÀNG"
        return "NGOẠI BẢNG. A TÀI SẢN CỦA CTCK VÀ TÀI SẢN QUẢN LÝ THEO CAM KẾT"

    # 3. Ket qua kinh doanh
    if stmt == "income_statement":
        return "KQKD. DOANH THU, CHI PHÍ, LỢI NHUẬN"

    # 4. Luu chuyen tien te
    if stmt == "cash_flow":
        if any(k in c or k in n for k in ["đầu tư", "dau_tu", "mua_sam", "thanh_ly", "cho_vay", "tien_gui", "thu_lai"]):
            return "LCTT. DÒNG TIỀN TỪ HOẠT ĐỘNG ĐẦU TƯ"
        elif any(k in c or k in n for k in ["tài chính", "tai_chinh", "co_tuc", "cổ tức", "von_gop", "vốn góp", "vay", "tra_no", "cổ phiếu quỹ"]):
            return "LCTT. DÒNG TIỀN TỪ HOẠT ĐỘNG TÀI CHÍNH"
        elif any(k in c or k in n for k in ["thuần trong kỳ", "thuan_trong_ky", "đầu kỳ", "dau_ky", "cuối kỳ", "cuoi_ky", "tỷ giá", "ty_gia", "tiền cuối kỳ"]):
            return "LCTT. DÒNG TIỀN THUẦN, TIỀN CUỐI KÌ"
        else:
            return "LCTT. DÒNG TIỀN TỪ HOẠT ĐỘNG KINH DOANH"

    # 5. Bang can doi ke toan
    if stmt == "balance_sheet":
        if any(k in c or k in n for k in ["vốn chủ sở hữu", "von_chu_so_huu", "vốn đầu tư của chủ sở hữu", "thặng dư", "cổ phiếu quỹ", "nguồn kinh phí", "lợi nhuận sau thuế chưa phân phối"]):
            return "CĐKT. VỐN CHỦ SỞ HỮU"

        if any(k in c or k in n for k in ["nợ dài hạn", "no_dai_han", "vay và nợ thuê tài chính dài hạn", "trái phiếu phát hành dài hạn"]):
            return "CĐKT. NỢ PHẢI TRẢ DÀI HẠN"

        if any(k in c or k in n for k in ["nợ ngắn hạn", "no_ngan_han", "vay và nợ thuê tài chính ngắn hạn", "trái phiếu phát hành ngắn hạn", "chi phí phải trả ngắn hạn", "phải trả người bán ngắn hạn", "người mua trả tiền trước ngắn hạn"]):
            return "CĐKT. NỢ PHẢI TRẢ NGẮN HẠN"

        if any(k in c or k in n for k in ["tài sản dài hạn", "tai_san_dai_han", "tài sản cố định", "bất động sản đầu tư", "xây dựng cơ bản"]):
            return "CĐKT. TÀI SẢN DÀI HẠN"

        if any(k in c or k in n for k in ["tài sản ngắn hạn", "tai_san_ngan_han", "tiền và tương đương", "tiền và các khoản", "đầu tư ngắn hạn", "chứng khoán kinh doanh", "phải thu ngắn hạn", "hàng tồn kho"]):
            return "CĐKT. TÀI SẢN NGẮN HẠN"

        if "nợ" in n or "phải trả" in n or "no_" in c:
            if "dài hạn" in n or "dai_han" in c:
                return "CĐKT. NỢ PHẢI TRẢ DÀI HẠN"
            return "CĐKT. NỢ PHẢI TRẢ NGẮN HẠN"

        if "dài hạn" in n or "dai_han" in c or order > 120:
            return "CĐKT. TÀI SẢN DÀI HẠN"

        return "CĐKT. TÀI SẢN NGẮN HẠN"

    return "CĐKT. TÀI SẢN NGẮN HẠN"


# He thong dinh nghia toan bo cac chi so WiData
WIDATA_RATIOS = {
    # 1. Kha nang sinh loi & Hieu qua
    "roa": {
        "name": "ROA (%) (Y)",
        "group": "Khả năng sinh lời",
        "formula": "Lợi nhuận sau thuế / Tổng tài sản",
        "fmt": "0.00%",
    },
    "roe": {
        "name": "ROE (%) (Y)",
        "group": "Khả năng sinh lời",
        "formula": "Lợi nhuận sau thuế / Vốn chủ sở hữu",
        "fmt": "0.00%",
    },
    "gross_margin": {
        "name": "Biên lợi nhuận gộp (%) (Y)",
        "group": "Khả năng sinh lời",
        "formula": "Lợi nhuận gộp / Doanh thu thuần",
        "fmt": "0.00%",
    },
    "net_margin": {
        "name": "Biên lợi nhuận ròng (%) (Y)",
        "group": "Khả năng sinh lời",
        "formula": "Lợi nhuận sau thuế / Doanh thu thuần",
        "fmt": "0.00%",
    },
    "ebit_margin": {
        "name": "Biên EBIT (%) (Y)",
        "group": "Khả năng sinh lời",
        "formula": "EBIT / Doanh thu thuần",
        "fmt": "0.00%",
    },
    "effective_tax_rate": {
        "name": "Tỷ lệ thuế suất hiệu dụng (%) (Y)",
        "group": "Khả năng sinh lời",
        "formula": "Chi phí thuế TNDN / Lợi nhuận trước thuế",
        "fmt": "0.00%",
    },
    "asset_turnover": {
        "name": "Vòng quay tổng tài sản (Lần) (Y)",
        "group": "Hiệu quả hoạt động",
        "formula": "Doanh thu thuần / Tổng tài sản",
        "fmt": "0.00",
    },
    "cfo_to_net_income": {
        "name": "Dòng tiền HĐKD/Lợi nhuận thuần (%) (Y)",
        "group": "Hiệu quả dòng tiền",
        "formula": "Dòng tiền thuần HĐKD / Lợi nhuận sau thuế",
        "fmt": "0.00%",
    },
    "cfo_to_avg_assets": {
        "name": "Dòng tiền HĐKD/Trung bình tổng tài sản (%) (Y)",
        "group": "Hiệu quả dòng tiền",
        "formula": "Dòng tiền thuần HĐKD / Tổng tài sản",
        "fmt": "0.00%",
    },
    "cfo_to_avg_equity": {
        "name": "Dòng tiền HĐKD/Trung bình vốn chủ sỡ hữu (%) (Y)",
        "group": "Hiệu quả dòng tiền",
        "formula": "Dòng tiền thuần HĐKD / Vốn chủ sở hữu",
        "fmt": "0.00%",
    },

    # 2. Co cau von & Kha nang thanh toan
    "debt_to_assets": {
        "name": "Hệ số nợ trên tổng tài sản (%) (Y)",
        "group": "Cơ cấu vốn và Đòn bẩy",
        "formula": "Nợ phải trả / Tổng tài sản",
        "fmt": "0.00%",
    },
    "debt_to_equity": {
        "name": "Hệ số nợ trên vốn chủ sở hữu (%) (Y)",
        "group": "Cơ cấu vốn và Đòn bẩy",
        "formula": "Nợ phải trả / Vốn chủ sở hữu",
        "fmt": "0.00%",
    },
    "equity_to_assets": {
        "name": "Hệ số vốn chủ sở hữu (%) (Y)",
        "group": "Cơ cấu vốn và Đòn bẩy",
        "formula": "Vốn chủ sở hữu / Tổng tài sản",
        "fmt": "0.00%",
    },
    "equity_multiplier": {
        "name": "Tổng tài sản/Vốn chủ sở hữu (Lần) (Y)",
        "group": "Cơ cấu vốn và Đòn bẩy",
        "formula": "Tổng tài sản / Vốn chủ sở hữu",
        "fmt": "0.00",
    },
    "current_ratio": {
        "name": "Tỷ số thanh toán hiện hành (Lần) (Y)",
        "group": "Khả năng thanh toán",
        "formula": "Tài sản ngắn hạn / Nợ ngắn hạn",
        "fmt": "0.00",
    },
    "quick_ratio": {
        "name": "Tỷ số thanh toán nhanh (Lần) (Y)",
        "group": "Khả năng thanh toán",
        "formula": "(Tài sản ngắn hạn - Hàng tồn kho) / Nợ ngắn hạn",
        "fmt": "0.00",
    },

    # 3. Dac thu CTCK & Tai san tai chinh
    "margin_to_equity": {
        "name": "Tỷ lệ cho vay ký quỹ trên VCSH (%) (Y)",
        "group": "Đặc thù CTCK & Margin",
        "formula": "Cho vay ký quỹ (margin) / Vốn chủ sở hữu",
        "fmt": "0.00%",
    },
    "pct_margin_loans": {
        "name": "% Cho vay nghiệp vụ ký quỹ (margin) (%) (Y)",
        "group": "Đặc thù CTCK & Margin",
        "formula": "Cho vay margin / Tổng tài sản",
        "fmt": "0.00%",
    },
    "pct_advances": {
        "name": "% Cho vay ứng trước tiền bán chứng khoán của khách hàng (%) (Y)",
        "group": "Đặc thù CTCK & Margin",
        "formula": "Cho vay ứng trước tiền bán CK / Tổng tài sản",
        "fmt": "0.00%",
    },
    "pct_fvtpl": {
        "name": "% Tài sản tài chính ghi nhận thông qua lãi lỗ (FVTPL) (%) (Y)",
        "group": "Cơ cấu tài sản tài chính",
        "formula": "Tài sản FVTPL / Tổng tài sản",
        "fmt": "0.00%",
    },
    "pct_afs": {
        "name": "% Tài sản tài chính sẵn sàng để bán (AFS) (%) (Y)",
        "group": "Cơ cấu tài sản tài chính",
        "formula": "Tài sản AFS / Tổng tài sản",
        "fmt": "0.00%",
    },
    "pct_htm": {
        "name": "% Tài sản tài chính giữ đến ngày đáo hạn (HTM) (%) (Y)",
        "group": "Cơ cấu tài sản tài chính",
        "formula": "Tài sản HTM / Tổng tài sản",
        "fmt": "0.00%",
    },
    "pct_cash": {
        "name": "% Tiền và các khoản tương đương tiền (%) (Y)",
        "group": "Cơ cấu tài sản tài chính",
        "formula": "Tiền và tương đương tiền / Tổng tài sản",
        "fmt": "0.00%",
    },
    "pct_loans": {
        "name": "% Các khoản cho vay (%) (Y)",
        "group": "Cơ cấu tài sản tài chính",
        "formula": "Tổng các khoản cho vay / Tổng tài sản",
        "fmt": "0.00%",
    },
    "pct_brokerage_rev": {
        "name": "% Doanh thu hoạt động môi giới chứng khoán (%) (Y)",
        "group": "Cơ cấu doanh thu",
        "formula": "Doanh thu môi giới CK / Tổng doanh thu hoạt động",
        "fmt": "0.00%",
    },
    "pct_proprietary_rev": {
        "name": "% Doanh thu mảng tự doanh và kinh doanh nguồn vốn (%) (Y)",
        "group": "Cơ cấu doanh thu",
        "formula": "Doanh thu tự doanh / Tổng doanh thu hoạt động",
        "fmt": "0.00%",
    },
    "pct_margin_profit": {
        "name": "% Lợi nhuận cho vay ký quỹ (%) (Y)",
        "group": "Cơ cấu lợi nhuận",
        "formula": "Lợi nhuận cho vay margin / Lợi nhuận hoạt động",
        "fmt": "0.00%",
    },
    "pct_ib_rev": {
        "name": "% Doanh thu mảng ngân hàng đầu tư (%) (Y)",
        "group": "Cơ cấu doanh thu",
        "formula": "Doanh thu tư vấn tài chính, IB / Tổng doanh thu",
        "fmt": "0.00%",
    },
    "pct_brokerage_cost": {
        "name": "% Chi phí hoạt động môi giới chứng khoán (%) (Y)",
        "group": "Cơ cấu chi phí",
        "formula": "Chi phí môi giới / Tổng chi phí hoạt động",
        "fmt": "0.00%",
    },
    "pct_proprietary_cost": {
        "name": "% Chi phí hoạt động tự doanh (%) (Y)",
        "group": "Cơ cấu chi phí",
        "formula": "Chi phí tự doanh / Tổng chi phí hoạt động",
        "fmt": "0.00%",
    },
    "pct_advisory_cost": {
        "name": "% Chi phí hoạt động tư vấn tài chính (%) (Y)",
        "group": "Cơ cấu chi phí",
        "formula": "Chi phí tư vấn tài chính / Tổng chi phí hoạt động",
        "fmt": "0.00%",
    },
    "pct_provision_cost": {
        "name": "% Chi phí dự phòng/Hoàn nhập TSTC (%) (Y)",
        "group": "Cơ cấu chi phí",
        "formula": "Chi phí dự phòng TSTC / Tổng chi phí hoạt động",
        "fmt": "0.00%",
    },

    # 4. Tang truong cung ky YoY (%)
    "rev_growth_yoy": {
        "name": "Doanh thu (*) (YoY) (%) (Y)",
        "group": "Tăng trưởng cùng kỳ (YoY)",
        "formula": "(Doanh thu T - Doanh thu T-1) / |Doanh thu T-1|",
        "fmt": "0.00%",
    },
    "ebt_growth_yoy": {
        "name": "Lợi nhuận trước thuế (YoY) (%) (Y)",
        "group": "Tăng trưởng cùng kỳ (YoY)",
        "formula": "(LNTT T - LNTT T-1) / |LNTT T-1|",
        "fmt": "0.00%",
    },
    "eat_growth_yoy": {
        "name": "Lợi nhuận sau thuế (YoY) (%) (Y)",
        "group": "Tăng trưởng cùng kỳ (YoY)",
        "formula": "(LNST T - LNST T-1) / |LNST T-1|",
        "fmt": "0.00%",
    },
    "eat_parent_growth_yoy": {
        "name": "Lợi nhuận sau thuế CĐCTM (YoY) (%) (Y)",
        "group": "Tăng trưởng cùng kỳ (YoY)",
        "formula": "(LNST Cty mẹ T - LNST Cty mẹ T-1) / |LNST Cty mẹ T-1|",
        "fmt": "0.00%",
    },
    "assets_growth_yoy": {
        "name": "Tổng tài sản (YoY) (%) (Y)",
        "group": "Tăng trưởng cùng kỳ (YoY)",
        "formula": "(Tổng tài sản T - Tổng tài sản T-1) / Tổng tài sản T-1",
        "fmt": "0.00%",
    },
    "equity_growth_yoy": {
        "name": "Vốn chủ sở hữu (YoY) (%) (Y)",
        "group": "Tăng trưởng cùng kỳ (YoY)",
        "formula": "(Vốn CSH T - Vốn CSH T-1) / Vốn CSH T-1",
        "fmt": "0.00%",
    },
    "debt_growth_yoy": {
        "name": "Nợ phải trả (YoY) (%) (Y)",
        "group": "Tăng trưởng cùng kỳ (YoY)",
        "formula": "(Nợ phải trả T - Nợ phải trả T-1) / Nợ phải trả T-1",
        "fmt": "0.00%",
    },
    "margin_loans_growth_yoy": {
        "name": "Cho vay nghiệp vụ ký quỹ (margin) (YoY) (%) (Y)",
        "group": "Tăng trưởng cùng kỳ (YoY)",
        "formula": "(Dư nợ margin T - Dư nợ margin T-1) / Dư nợ margin T-1",
        "fmt": "0.00%",
    },
    "advances_growth_yoy": {
        "name": "Cho vay ứng trước tiền bán chứng khoán của khách hàng (YoY) (%) (Y)",
        "group": "Tăng trưởng cùng kỳ (YoY)",
        "formula": "(Ứng trước T - Ứng trước T-1) / Ứng trước T-1",
        "fmt": "0.00%",
    },
    "brokerage_rev_growth_yoy": {
        "name": "Doanh thu hoạt động môi giới chứng khoán (YoY) (%) (Y)",
        "group": "Tăng trưởng cùng kỳ (YoY)",
        "formula": "(DT môi giới T - DT môi giới T-1) / DT môi giới T-1",
        "fmt": "0.00%",
    },
    "proprietary_rev_growth_yoy": {
        "name": "Doanh thu mảng tự doanh và kinh doanh nguồn vốn (YoY) (%) (Y)",
        "group": "Tăng trưởng cùng kỳ (YoY)",
        "formula": "(DT tự doanh T - DT tự doanh T-1) / DT tự doanh T-1",
        "fmt": "0.00%",
    },
    "cash_growth_yoy": {
        "name": "Tiền và các khoản tương đương tiền (YoY) (%) (Y)",
        "group": "Tăng trưởng cùng kỳ (YoY)",
        "formula": "(Tiền T - Tiền T-1) / Tiền T-1",
        "fmt": "0.00%",
    },
    "fvtpl_growth_yoy": {
        "name": "Tài sản tài chính ghi nhận thông qua lãi lỗ (FVTPL) (YoY) (%) (Y)",
        "group": "Tăng trưởng cùng kỳ (YoY)",
        "formula": "(FVTPL T - FVTPL T-1) / FVTPL T-1",
        "fmt": "0.00%",
    },
    "htm_growth_yoy": {
        "name": "Tài sản tài chính giữ đến ngày đáo hạn (HTM) (YoY) (%) (Y)",
        "group": "Tăng trưởng cùng kỳ (YoY)",
        "formula": "(HTM T - HTM T-1) / HTM T-1",
        "fmt": "0.00%",
    },
    "afs_growth_yoy": {
        "name": "Tài sản tài chính sẵn sàng để bán (AFS) (YoY) (%) (Y)",
        "group": "Tăng trưởng cùng kỳ (YoY)",
        "formula": "(AFS T - AFS T-1) / AFS T-1",
        "fmt": "0.00%",
    },

    # 5. Quy mo & Dinh gia co ban (VND & ln)
    "total_assets": {
        "name": "Tổng tài sản (VND) (Y)",
        "group": "Quy mô tài chính",
        "formula": "BCTC - Tổng tài sản",
        "fmt": "#,##0",
    },
    "total_debt": {
        "name": "Nợ phải trả (VND) (Y)",
        "group": "Quy mô tài chính",
        "formula": "BCTC - Nợ phải trả",
        "fmt": "#,##0",
    },
    "equity": {
        "name": "Vốn chủ sở hữu (VND) (Y)",
        "group": "Quy mô tài chính",
        "formula": "BCTC - Vốn chủ sở hữu",
        "fmt": "#,##0",
    },
    "net_revenue": {
        "name": "Doanh thu (*) (VND) (Y)",
        "group": "Quy mô tài chính",
        "formula": "BCTC - Doanh thu thuần / Doanh thu hoạt động",
        "fmt": "#,##0",
    },
    "profit_before_tax": {
        "name": "Lợi nhuận trước thuế (VND) (Y)",
        "group": "Quy mô tài chính",
        "formula": "BCTC - Lợi nhuận trước thuế",
        "fmt": "#,##0",
    },
    "profit_after_tax": {
        "name": "Lợi nhuận sau thuế (VND) (Y)",
        "group": "Quy mô tài chính",
        "formula": "BCTC - Lợi nhuận sau thuế",
        "fmt": "#,##0",
    },
    "operating_cash_flow": {
        "name": "Dòng tiền từ hoạt động kinh doanh (VND) (Y)",
        "group": "Quy mô tài chính",
        "formula": "LCTT - Dòng tiền thuần từ HĐKD",
        "fmt": "#,##0",
    },
    "investing_cash_flow": {
        "name": "Dòng tiền từ hoạt động đầu tư (VND) (Y)",
        "group": "Quy mô tài chính",
        "formula": "LCTT - Dòng tiền thuần từ HĐĐT",
        "fmt": "#,##0",
    },
    "financing_cash_flow": {
        "name": "Dòng tiền từ hoạt động tài chính (VND) (Y)",
        "group": "Quy mô tài chính",
        "formula": "LCTT - Dòng tiền thuần từ HĐTC",
        "fmt": "#,##0",
    },
    "eat_parent": {
        "name": "Lợi nhuận sau thuế công ty mẹ (VND) (Y)",
        "group": "Quy mô tài chính",
        "formula": "BCTC - LNST Cổ đông công ty mẹ",
        "fmt": "#,##0",
    },
    "curr_debt": {
        "name": "Nợ phải trả ngắn hạn (VND) (Y)",
        "group": "Quy mô tài chính",
        "formula": "BCTC - Nợ ngắn hạn",
        "fmt": "#,##0",
    },
    "long_term_debt": {
        "name": "Nợ phải trả dài hạn (VND) (Y)",
        "group": "Quy mô tài chính",
        "formula": "BCTC - Nợ dài hạn",
        "fmt": "#,##0",
    },
    "curr_assets": {
        "name": "Tài sản ngắn hạn (VND) (Y)",
        "group": "Quy mô tài chính",
        "formula": "BCTC - Tài sản ngắn hạn",
        "fmt": "#,##0",
    },
    "non_curr_assets": {
        "name": "Tài sản dài hạn (VND) (Y)",
        "group": "Quy mô tài chính",
        "formula": "BCTC - Tài sản dài hạn",
        "fmt": "#,##0",
    },
    "brokerage_profit": {
        "name": "Lợi nhuận từ nghiệp vụ môi giới (VND) (Y)",
        "group": "Đặc thù CTCK & Margin",
        "formula": "Doanh thu môi giới - Chi phí môi giới",
        "fmt": "#,##0",
    },
    "advisory_profit": {
        "name": "Lợi nhuận từ nghiệp vụ tư vấn tài chính (VND) (Y)",
        "group": "Đặc thù CTCK & Margin",
        "formula": "Doanh thu tư vấn - Chi phí tư vấn",
        "fmt": "#,##0",
    },
    "margin_profit": {
        "name": "Lợi nhuận từ cho vay ký quỹ (VND) (Y)",
        "group": "Đặc thù CTCK & Margin",
        "formula": "Lãi từ các khoản cho vay và phải thu",
        "fmt": "#,##0",
    },
    "operating_profit": {
        "name": "Lợi nhuận hoạt động (VND) (Y)",
        "group": "Quy mô tài chính",
        "formula": "Doanh thu hoạt động - Chi phí hoạt động",
        "fmt": "#,##0",
    },
    "operating_cost": {
        "name": "Chi phí hoạt động (*) (VND) (Y)",
        "group": "Quy mô tài chính",
        "formula": "Tổng chi phí hoạt động CTCK",
        "fmt": "#,##0",
    },
    "curr_debt_growth_yoy": {
        "name": "Nợ phải trả ngắn hạn (YoY) (%) (Y)",
        "group": "Tăng trưởng cùng kỳ (YoY)",
        "formula": "(Nợ NH T - Nợ NH T-1) / Nợ NH T-1",
        "fmt": "0.00%",
    },
    "long_debt_growth_yoy": {
        "name": "Nợ phải trả dài hạn (YoY) (%) (Y)",
        "group": "Tăng trưởng cùng kỳ (YoY)",
        "formula": "(Nợ DH T - Nợ DH T-1) / Nợ DH T-1",
        "fmt": "0.00%",
    },
    "curr_assets_growth_yoy": {
        "name": "Tài sản ngắn hạn (YoY) (%) (Y)",
        "group": "Tăng trưởng cùng kỳ (YoY)",
        "formula": "(TSNH T - TSNH T-1) / TSNH T-1",
        "fmt": "0.00%",
    },
    "non_curr_assets_growth_yoy": {
        "name": "Tài sản dài hạn (YoY) (%) (Y)",
        "group": "Tăng trưởng cùng kỳ (YoY)",
        "formula": "(TSDH T - TSDH T-1) / TSDH T-1",
        "fmt": "0.00%",
    },
    "oper_cost_growth_yoy": {
        "name": "Chi phí hoạt động (*) (YoY) (%) (Y)",
        "group": "Tăng trưởng cùng kỳ (YoY)",
        "formula": "(Chi phí HĐ T - Chi phí HĐ T-1) / Chi phí HĐ T-1",
        "fmt": "0.00%",
    },
    "oper_profit_growth_yoy": {
        "name": "Lợi nhuận hoạt động (YoY) (%) (Y)",
        "group": "Tăng trưởng cùng kỳ (YoY)",
        "formula": "(Lợi nhuận HĐ T - Lợi nhuận HĐ T-1) / Lợi nhuận HĐ T-1",
        "fmt": "0.00%",
    },
    "pct_other_receivables": {
        "name": "% Phải thu khác (%) (Y)",
        "group": "Cơ cấu tài sản tài chính",
        "formula": "Phải thu khác / Tổng tài sản",
        "fmt": "0.00%",
    },
    "pct_broker_services": {
        "name": "% Phải thu các dịch vụ CTCK cung cấp (%) (Y)",
        "group": "Cơ cấu tài sản tài chính",
        "formula": "Phải thu dịch vụ CTCK / Tổng tài sản",
        "fmt": "0.00%",
    },
    "size_ln": {
        "name": "Quy mô doanh nghiệp Size ln(Tổng tài sản)",
        "group": "Quy mô tài chính",
        "formula": "ln(Tổng tài sản)",
        "fmt": "0.000",
    },
}


def compute_widata_metrics(pivot: pd.DataFrame) -> pd.DataFrame:
    """Tinh toan toan bo he thong chi so WiData tu bang pivot panel."""
    df = pivot.copy()
    if "ticker" not in df.columns or "year" not in df.columns:
        return df

    df = df.sort_values(["ticker", "year"]).reset_index(drop=True)

    def coalesce_cols(patterns):
        res = pd.Series(np.nan, index=df.index, dtype=float)
        matched_cols = []
        # Priority 1: Exact case-insensitive match
        for p in patterns:
            for c in df.columns:
                if c.lower() == p.lower() and c not in matched_cols:
                    matched_cols.append(c)
        # Priority 2: Substring match
        for p in patterns:
            for c in df.columns:
                if p.lower() in c.lower() and c not in matched_cols:
                    matched_cols.append(c)
        # Coalesce: first non-null across matched candidate columns per row
        for c in matched_cols:
            col_s = pd.to_numeric(df[c], errors="coerce")
            res = res.combine_first(col_s)
        return res

    # Core base items (Multi-sector: Commercial/Manufacturing, Banking, Securities, Insurance)
    total_assets = coalesce_cols(["bs_tong_tai_san", "bs_tong_cong_tai_san"])
    equity = coalesce_cols([
        "bs_von_chu_so_huu_4d280b22",
        "bs_von_chu_so_huu_6cda78ae",
        "bs_von_chu_so_huu",
        "bs_tong_von_chu_so_huu",
        "bs_von_va_cac_quy",
    ])
    debt = coalesce_cols(["bs_no_phai_tra", "bs_tong_no_phai_tra"])
    curr_assets = coalesce_cols(["bs_tai_san_ngan_han", "bs_tong_tai_san_ngan_han"])
    curr_liab = coalesce_cols(["bs_no_ngan_han", "bs_tong_no_ngan_han"])
    inventory = coalesce_cols(["bs_hang_ton_kho", "bs_hang_ton_kho_rong"])
    cash = coalesce_cols(["bs_tien_va_tuong_duong_tien", "bs_tien_mat_vang_bac_da_quy", "bs_tien"])
    revenue = coalesce_cols([
        "is_doanh_thu_thuan",
        "is_doanh_so_thuan",
        "is_tong_thu_nhap_hoat_dong",
        "is_doanh_thu_hoat_dong",
        "is_thu_nhap_lai_thuan",
    ])
    gross_profit = coalesce_cols(["is_loi_nhuan_gop", "is_lai_gop", "is_thu_nhap_lai_thuan"])
    ebt = coalesce_cols([
        "is_tong_loi_nhuan_ke_toan_truoc_thue",
        "is_tong_loi_nhuan_truoc_thue",
        "is_loi_nhuan_truoc_thue",
        "is_lai_truoc_thue",
    ])
    eat = coalesce_cols([
        "is_lai_lo_thuan_sau_thue",
        "is_loi_nhuan_sau_thue",
        "is_loi_nhuan_ke_toan_sau_thue",
        "is_loi_nhuan_sau_thue_thu_nhap_doanh_nghiep",
        "is_loi_nhuan_sau_thue_phan_bo_cho_chu_so_huu",
        "is_loi_nhuan_sau_thue_cua_chu_so_huu_tap_doan",
        "is_tong_loi_nhuan_ke_toan_sau_thue",
        "is_lai_sau_thue",
    ])
    eat_parent = coalesce_cols([
        "is_loi_nhuan_sau_thue_cua_co_dong_cong_ty_me",
        "is_loi_nhuan_cua_co_dong_cua_cong_ty_me",
        "is_loi_nhuan_sau_thue_phan_bo_cho_chu_so_huu",
        "is_loi_nhuan_sau_thue_cua_chu_so_huu_tap_doan",
        "is_loi_nhuan_sau_thue_cty_me",
        "is_lai_sau_thue_cua_co_dong_cong_ty_me",
    ])
    eat_parent = eat_parent.combine_first(eat)
    interest_expense = coalesce_cols([
        "is_chi_phi_lai_vay",
        "is_trong_do_chi_phi_lai_vay",
        "is_chi_phi_lai_va_cac_khoan_chi_phi_tuong_tu",
    ])
    operating_profit_base = coalesce_cols([
        "is_ebit",
        "is_lai_lo_tu_hoat_dong_kinh_doanh",
        "is_ln_thuan_tu_hoat_dong_kinh_doanh_truoc_cf_du_phong_rui_ro_tin_dung",
        "is_ket_qua_hoat_dong",
    ])
    ebit = coalesce_cols(["is_ebit"]).combine_first(ebt + interest_expense.fillna(0)).combine_first(operating_profit_base)
    tax = coalesce_cols([
        "is_chi_phi_thue_tndn",
        "is_chi_phi_thue_thu_nhap_doanh_nghiep_hien_hanh",
        "is_chi_phi_thue_thu_nhap_doanh_nghiep",
    ])
    cfo = coalesce_cols([
        "cf_luu_chuyen_tien_thuan_tu_cac_hoat_dong_san_xuat_kinh_doanh",
        "cf_luu_chuyen_thuan_tu_hoat_dong_kinh_doanh_chung_khoan",
        "cf_luu_chuyen_tien_thuan_tu_hoat_dong_kinh_doanh",
        "cf_luu_chuyen_tien_thuan_tu_hoat_dong_kinh_doanh_truoc_thue_thu_nhap_dn",
    ])
    cfi = coalesce_cols([
        "cf_luu_chuyen_tien_te_rong_tu_hoat_dong_dau_tu",
        "cf_luu_chuyen_tien_thuan_tu_hoat_dong_dau_tu",
        "cf_luu_chuyen_tu_hoat_dong_dau_tu",
    ])
    cff = coalesce_cols([
        "cf_luu_chuyen_tien_te_tu_hoat_dong_tai_chinh",
        "cf_luu_chuyen_tien_tu_hoat_dong_tai_chinh",
        "cf_luu_chuyen_thuan_tu_hoat_dong_tai_chinh",
        "cf_luu_chuyen_tien_thuan_tu_hoat_dong_tai_chinh",
    ])

    # CTCK & Non-financial specific items
    margin_loans = coalesce_cols(["bs_cac_khoan_cho_vay", "bs_phai_thu_ve_cho_vay_ky_quy", "bs_cho_vay_margin"])
    advances = coalesce_cols([
        "bs_phai_thu_ung_truoc_tien_ban_chung_khoan_cua_khach_hang",
        "bs_ung_truoc_tien_ban",
        "bs_phai_thu_ve_hoat_dong_giao_dich_chung_khoan",
    ])
    fvtpl = coalesce_cols(["bs_cac_tai_san_tai_chinh_ghi_nhan_thong_qua_lai_lo_fvtpl", "bs_tai_san_tai_chinh_fvtpl"])
    htm = coalesce_cols(["bs_cac_khoan_dau_tu_nam_giu_den_ngay_dao_han_htm", "bs_dau_tu_nam_giu_den_ngay_dao_han_htm"])
    afs = coalesce_cols(["bs_cac_khoan_tai_chinh_san_sang_de_ban_afs", "bs_tai_san_tai_chinh_san_sang_de_ban_afs"])
    brokerage_rev = coalesce_cols(["is_doanh_thu_hoat_dong_moi_gioi_chung_khoan", "is_doanh_thu_moi_gioi"])
    proprietary_rev = coalesce_cols(["is_doanh_thu_mang_tu_doanh_va_kinh_doanh_nguon_von", "is_lai_tu_cac_tai_san_tai_chinh_ghi_nhan_thong_qua_lai_lo_fvtpl"])
    margin_profit = coalesce_cols(["is_lai_tu_cac_khoan_cho_vay_va_phai_thu"])
    ib_rev = coalesce_cols(["is_doanh_thu_hoat_dong_tu_van_tai_chinh", "is_doanh_thu_mang_ngan_hang_dau_tu"])
    brokerage_cost = coalesce_cols([
        "is_chi_phi_moi_gioi_chung_khoan",
        "is_chi_phi_hoat_dong_moi_gioi_chung_khoan",
    ])
    proprietary_cost = coalesce_cols(["is_chi_phi_hoat_dong_tu_doanh"])
    advisory_cost = coalesce_cols(["is_chi_phi_hoat_dong_tu_van_tai_chinh"])
    provision_cost = coalesce_cols(["is_chi_phi_du_phong_tstc", "is_chi_phi_du_phong"])
    long_term_debt = coalesce_cols(["bs_no_dai_han", "bs_tong_no_dai_han"])
    non_curr_assets = coalesce_cols(["bs_tai_san_dai_han"])
    operating_cost = coalesce_cols(["is_chi_phi_hoat_dong", "is_tong_chi_phi_hoat_dong"])
    other_receivables = coalesce_cols(["bs_phai_thu_khac", "bs_cac_khoan_phai_thu_khac"])
    broker_services = coalesce_cols(["bs_phai_thu_cac_dich_vu_ctck_cung_cap"])

    def sdiv(a, b):
        return a.astype(float) / b.replace(0, np.nan).astype(float)

    # 1. Sinh loi
    df["roa"] = sdiv(eat, total_assets)
    df["roe"] = sdiv(eat, equity)
    df["gross_margin"] = sdiv(gross_profit, revenue)
    df["net_margin"] = sdiv(eat, revenue)
    df["ebit_margin"] = sdiv(ebit, revenue)
    df["effective_tax_rate"] = sdiv(tax, ebt)
    df["asset_turnover"] = sdiv(revenue, total_assets)
    df["cfo_to_net_income"] = sdiv(cfo, eat)
    df["cfo_to_avg_assets"] = sdiv(cfo, total_assets)
    df["cfo_to_avg_equity"] = sdiv(cfo, equity)

    # 2. Don bay & Thanh toan
    df["debt_to_assets"] = sdiv(debt, total_assets)
    df["debt_to_equity"] = sdiv(debt, equity)
    df["equity_to_assets"] = sdiv(equity, total_assets)
    df["equity_multiplier"] = sdiv(total_assets, equity)
    df["current_ratio"] = sdiv(curr_assets, curr_liab)
    df["quick_ratio"] = sdiv(curr_assets - inventory.fillna(0), curr_liab)

    # 3. CTCK & Co cau
    df["margin_to_equity"] = sdiv(margin_loans, equity)
    df["pct_margin_loans"] = sdiv(margin_loans, total_assets)
    df["pct_advances"] = sdiv(advances, total_assets)
    df["pct_fvtpl"] = sdiv(fvtpl, total_assets)
    df["pct_afs"] = sdiv(afs, total_assets)
    df["pct_htm"] = sdiv(htm, total_assets)
    df["pct_cash"] = sdiv(cash, total_assets)
    df["pct_loans"] = sdiv(margin_loans, total_assets)
    df["pct_brokerage_rev"] = sdiv(brokerage_rev, revenue)
    df["pct_proprietary_rev"] = sdiv(proprietary_rev, revenue)
    df["pct_margin_profit"] = sdiv(margin_profit, ebt)
    df["pct_ib_rev"] = sdiv(ib_rev, revenue)
    df["pct_brokerage_cost"] = sdiv(brokerage_cost, revenue)
    df["pct_proprietary_cost"] = sdiv(proprietary_cost, revenue)
    df["pct_advisory_cost"] = sdiv(advisory_cost, revenue)
    df["pct_provision_cost"] = sdiv(provision_cost, revenue)
    df["pct_other_receivables"] = sdiv(other_receivables, total_assets)
    df["pct_broker_services"] = sdiv(broker_services, total_assets)

    # 4. Quy mo
    df["total_assets"] = total_assets
    df["total_debt"] = debt
    df["equity"] = equity
    df["curr_assets"] = curr_assets
    df["non_curr_assets"] = non_curr_assets
    df["curr_debt"] = curr_liab
    df["long_term_debt"] = long_term_debt
    df["net_revenue"] = revenue
    df["profit_before_tax"] = ebt
    df["profit_after_tax"] = eat
    df["eat_parent"] = eat_parent
    df["brokerage_profit"] = brokerage_rev.fillna(0) - brokerage_cost.fillna(0)
    df["advisory_profit"] = ib_rev.fillna(0) - advisory_cost.fillna(0)
    df["margin_profit"] = margin_profit
    df["operating_cost"] = operating_cost
    df["operating_profit"] = revenue.fillna(0) - operating_cost.fillna(0)
    df["operating_cash_flow"] = cfo
    df["investing_cash_flow"] = cfi
    df["financing_cash_flow"] = cff
    df["size_ln"] = total_assets.apply(lambda x: math.log(x) if pd.notna(x) and x > 0 else np.nan)

    # 5. YoY Growth %
    for col, yoy_col in [
        ("net_revenue", "rev_growth_yoy"),
        ("profit_before_tax", "ebt_growth_yoy"),
        ("profit_after_tax", "eat_growth_yoy"),
        ("eat_parent", "eat_parent_growth_yoy"),
        ("total_assets", "assets_growth_yoy"),
        ("equity", "equity_growth_yoy"),
        ("total_debt", "debt_growth_yoy"),
        ("curr_debt", "curr_debt_growth_yoy"),
        ("long_term_debt", "long_debt_growth_yoy"),
        ("curr_assets", "curr_assets_growth_yoy"),
        ("non_curr_assets", "non_curr_assets_growth_yoy"),
        ("operating_cost", "oper_cost_growth_yoy"),
        ("operating_profit", "oper_profit_growth_yoy"),
    ]:
        try:
            df[yoy_col] = df.groupby("ticker")[col].pct_change(fill_method=None)
        except TypeError:
            df[yoy_col] = df.groupby("ticker")[col].pct_change()

    # CTCK & Financial asset specific YoY
    extra_yoy_items = {
        "margin_loans": margin_loans,
        "advances": advances,
        "brokerage_rev": brokerage_rev,
        "proprietary_rev": proprietary_rev,
        "cash": cash,
        "fvtpl": fvtpl,
        "htm": htm,
        "afs": afs,
    }
    for base_key, s_val in extra_yoy_items.items():
        yoy_col = f"{base_key}_growth_yoy"
        tmp_col = f"_tmp_{base_key}"
        df[tmp_col] = s_val
        try:
            df[yoy_col] = df.groupby("ticker")[tmp_col].pct_change(fill_method=None)
        except TypeError:
            df[yoy_col] = df.groupby("ticker")[tmp_col].pct_change()
        df.drop(columns=[tmp_col], inplace=True)

    return df


# =====================================================================
# PREMIUM STYLING CONSTANTS
# =====================================================================

_NAVY = "1B3A5C"
_DARK_NAVY = "0F2440"
_TEAL = "0D7377"
_GOLD = "D4A843"
_WHITE = "FFFFFF"
_LIGHT_GRAY = "F8FAFB"
_SECTION_BG = "E1EDF5"
_DROPDOWN_BG = "FFF8E7"
_BORDER_COLOR = "E2E8F0"

_NAVY_FILL = PatternFill(start_color=_NAVY, end_color=_NAVY, fill_type="solid")
_TEAL_FILL = PatternFill(start_color=_TEAL, end_color=_TEAL, fill_type="solid")
_SECTION_FILL = PatternFill(start_color=_SECTION_BG, end_color=_SECTION_BG, fill_type="solid")
_DROPDOWN_FILL = PatternFill(start_color=_DROPDOWN_BG, end_color=_DROPDOWN_BG, fill_type="solid")
_ZEBRA_EVEN = PatternFill(start_color=_WHITE, end_color=_WHITE, fill_type="solid")
_ZEBRA_ODD = PatternFill(start_color=_LIGHT_GRAY, end_color=_LIGHT_GRAY, fill_type="solid")

_TITLE_FONT = Font(name="Segoe UI", size=16, bold=True, color=_NAVY)
_HEADER_FONT = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
_SECTION_FONT = Font(name="Segoe UI", size=11, bold=True, color=_NAVY)
_BODY_FONT = Font(name="Segoe UI", size=10, color="2D3748")
_BODY_BOLD = Font(name="Segoe UI", size=10, bold=True, color="2D3748")
_LABEL_FONT = Font(name="Segoe UI", size=10, bold=True, color="4A5568")
_SMALL_FONT = Font(name="Segoe UI", size=9, color="718096")
_COVER_TITLE = Font(name="Segoe UI", size=22, bold=True, color=_NAVY)
_COVER_LABEL = Font(name="Segoe UI", size=11, bold=True, color=_TEAL)
_COVER_INFO = Font(name="Segoe UI", size=11, color="2D3748")

_THIN_BORDER = Border(
    left=Side(style="thin", color=_BORDER_COLOR),
    right=Side(style="thin", color=_BORDER_COLOR),
    top=Side(style="thin", color=_BORDER_COLOR),
    bottom=Side(style="thin", color=_BORDER_COLOR),
)
_GOLD_BORDER = Border(
    left=Side(style="medium", color=_GOLD),
    right=Side(style="medium", color=_GOLD),
    top=Side(style="medium", color=_GOLD),
    bottom=Side(style="medium", color=_GOLD),
)
_SECTION_BORDER = Border(bottom=Side(style="medium", color=_NAVY))

_CENTER = Alignment(horizontal="center", vertical="center")
_LEFT = Alignment(horizontal="left", vertical="center")
_RIGHT = Alignment(horizontal="right", vertical="center")


# =====================================================================
# HELPER: Get master item list
# =====================================================================

def _get_master_items(all_data, fin_codebook):
    """Get the full 702-item master list, classified into 13 categories."""
    try:
        import vnfinancialdata as vnf
        df_master = vnf.list_items(active_only=False).copy()
    except Exception:
        df_master = pd.DataFrame()

    if df_master.empty:
        if not all_data.empty:
            df_master = all_data[["item_code", "item_name", "statement"]].drop_duplicates().copy()
            df_master["item_order"] = 0
        else:
            df_master = pd.DataFrame(columns=["item_code", "item_name", "statement", "item_order"])

    if "statement" not in df_master.columns:
        df_master["statement"] = df_master["item_code"].apply(
            lambda c: "balance_sheet" if str(c).startswith("bs_") else "income_statement" if str(c).startswith("is_") else "cash_flow"
        )
    if "item_order" not in df_master.columns:
        df_master["item_order"] = 0

    df_master["category"] = df_master.apply(
        lambda r: classify_financial_item(r["item_code"], r["item_name"], r["statement"], r.get("item_order", 0)),
        axis=1
    )

    cat_order_map = {cat: idx for idx, cat in enumerate(CATEGORY_ORDER)}
    df_master["cat_order"] = df_master["category"].map(lambda c: cat_order_map.get(c, 99))
    df_master = df_master.sort_values(["cat_order", "item_order", "item_code"]).reset_index(drop=True)

    if fin_codebook:
        selected_items = {item.get("Biến") for item in fin_codebook if item.get("Phân loại") == "Chỉ tiêu kế toán"}
        if selected_items and len(selected_items) < len(df_master):
            df_master = df_master[df_master["item_code"].isin(selected_items)].copy()

    return df_master


def _build_data_lookup(all_data):
    """Build dict of (ticker, item_code, year) -> value."""
    data_lookup = {}
    if not all_data.empty:
        for _, r in all_data.iterrows():
            t_key = str(r["ticker"]).strip().upper()
            icode_key = str(r["item_code"]).strip()
            try:
                y_key = int(r["year"])
            except (ValueError, TypeError):
                continue
            v_val = r.get("value")
            if pd.notna(v_val) and v_val is not None:
                data_lookup[(t_key, icode_key, y_key)] = v_val
    return data_lookup


# =====================================================================
# SHEET: Cover (Trang_Bia)
# =====================================================================

def _create_cover_sheet(ws, tickers, years, missing_tickers: Optional[List[str]] = None):
    """Create a premium cover sheet."""
    from datetime import datetime

    ws.sheet_properties.tabColor = _NAVY
    ws.column_dimensions["A"].width = 4
    ws.column_dimensions["B"].width = 24
    ws.column_dimensions["C"].width = 65

    # Try embedding arminer PNG logo image
    logo_path = Path(__file__).resolve().parent.parent / "ui" / "static" / "arminer_logo.png"
    if logo_path.exists():
        try:
            img = openpyxl.drawing.image.Image(str(logo_path))
            img.width = 62
            img.height = 62
            ws.add_image(img, "B2")
        except Exception:
            pass

    row = 3
    ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=3)
    ws.cell(row=row, column=2, value="BÁO CÁO TÀI CHÍNH").font = _COVER_TITLE
    row += 1

    ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=3)
    ws.cell(row=row, column=2, value="DOANH NGHIỆP NIÊM YẾT VIỆT NAM").font = Font(
        name="Segoe UI", size=18, bold=True, color=_TEAL
    )
    row += 1

    ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=3)
    ws.cell(row=row, column=2, value="arminer Studio — Trương Minh Quân").font = Font(
        name="Segoe UI", size=12, italic=True, bold=True, color="1B3A5C"
    )
    row += 2

    # Gold divider
    for col in range(2, 4):
        ws.cell(row=row, column=col).border = Border(bottom=Side(style="medium", color=_GOLD))
    row += 2

    # Info section
    info_items = [
        ("Tác giả phát triển:", "Trương Minh Quân"),
        ("Công cụ trích xuất:", "arminer Web Studio v2.5 (Corporate Text Mining & Financial Intelligence)"),
        ("Mã chứng khoán:", ", ".join(tickers)),
        ("Giai đoạn:", f"{min(years)} — {max(years)}"),
        ("Ngày xuất báo cáo:", datetime.now().strftime("%d/%m/%Y %H:%M")),
        ("Số chỉ tiêu BCTC:", "702 chỉ tiêu (13 nhóm kế toán chuẩn mực)"),
        ("Số tỷ số tài chính:", f"{len(WIDATA_RATIOS)} chỉ số (chuẩn WiData / WiGroup)"),
    ]
    if missing_tickers:
        info_items.append(("⚠️ Mã không có dữ liệu:", f"{', '.join(missing_tickers)} (Đã tự động loại bỏ)"))

    for label, value in info_items:
        ws.cell(row=row, column=2, value=label).font = _COVER_LABEL
        cell_val = ws.cell(row=row, column=3, value=value)
        if "⚠️" in label:
            cell_val.font = Font(name="Segoe UI", size=10, bold=True, color="C53030")
        else:
            cell_val.font = _COVER_INFO
        row += 1

    row += 1

    # Navigation guide
    ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=3)
    ws.cell(row=row, column=2, value="Nội dung bảng tính:").font = _COVER_LABEL
    row += 1

    nav_items = [
        ("→ Bao_Cao_Tai_Chinh", "702 chỉ tiêu kế toán — Chọn mã CK ở ô B2, dữ liệu tự động cập nhật"),
        ("→ Ty_So_Tai_Chinh", "75 tỷ số WiData — Chọn mã CK ở ô B2, dữ liệu tự động cập nhật"),
        ("→ Panel_Data_Goc", "Bảng phẳng Panel Data (tất cả mã) — sẵn sàng cho Stata / R / Python"),
        ("→ Codebook", "Từ điển biến, công thức tính toán và nguồn dữ liệu"),
        ("→ Huong_Dan", "Hướng dẫn sử dụng bộ chọn mã chứng khoán"),
    ]
    for sheet_name, desc in nav_items:
        ws.cell(row=row, column=2, value=sheet_name).font = Font(name="Segoe UI", size=10, bold=True, color=_NAVY)
        ws.cell(row=row, column=3, value=desc).font = _BODY_FONT
        row += 1

    row += 1

    # Data sources
    ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=3)
    ws.cell(row=row, column=2, value="Nguồn dữ liệu:").font = _COVER_LABEL
    row += 1
    for src in [
        "vnfinancialdata — Ngo Phu Thanh (UEL, ĐHQG TP.HCM)",
        "Hệ thống tỷ số tài chính WiData — WiGroup",
        "vn-annual-report-miner — github.com/Tumiqa/vn-annual-report-miner",
    ]:
        ws.cell(row=row, column=2, value="→").font = Font(name="Segoe UI", size=10, color=_TEAL)
        ws.cell(row=row, column=3, value=src).font = _SMALL_FONT
        row += 1


# =====================================================================
# SHEET: Hidden Data_BCTC
# =====================================================================

def _create_hidden_bctc_sheet(ws, df_master, tickers, years, data_lookup):
    """Create hidden data sheet for INDEX/MATCH lookup (BCTC)."""
    ws.sheet_state = "hidden"

    headers = ["key", "ticker", "item_code", "item_name", "category"] + [str(y) for y in years]
    for col_idx, h in enumerate(headers, 1):
        ws.cell(row=1, column=col_idx, value=h)

    row = 2
    for t in tickers:
        for _, mrow in df_master.iterrows():
            icode = str(mrow["item_code"])
            ws.cell(row=row, column=1, value=f"{t}_{icode}")
            ws.cell(row=row, column=2, value=t)
            ws.cell(row=row, column=3, value=icode)
            ws.cell(row=row, column=4, value=str(mrow["item_name"]))
            ws.cell(row=row, column=5, value=str(mrow["category"]))
            for y_idx, y in enumerate(years):
                val = data_lookup.get((t, icode, y))
                if pd.notna(val) and val is not None:
                    try:
                        ws.cell(row=row, column=6 + y_idx, value=float(val))
                    except (ValueError, TypeError):
                        ws.cell(row=row, column=6 + y_idx, value=str(val))
            row += 1

    return row - 1  # last data row


# =====================================================================
# SHEET: Hidden Data_TySo
# =====================================================================

def _create_hidden_tyso_sheet(ws, pivot, tickers, years, active_ratios):
    """Create hidden data sheet for INDEX/MATCH lookup (ratios)."""
    ws.sheet_state = "hidden"

    headers = ["key", "ticker", "ratio_code", "group", "name", "formula"] + [str(y) for y in years]
    for col_idx, h in enumerate(headers, 1):
        ws.cell(row=1, column=col_idx, value=h)

    row = 2
    for t in tickers:
        df_t = pivot[pivot["ticker"] == t]
        for rcode in active_ratios:
            meta = WIDATA_RATIOS.get(rcode, {"name": rcode, "group": "Tỷ số tài chính", "formula": "", "fmt": "0.00%"})
            ws.cell(row=row, column=1, value=f"{t}_{rcode}")
            ws.cell(row=row, column=2, value=t)
            ws.cell(row=row, column=3, value=rcode)
            ws.cell(row=row, column=4, value=meta["group"])
            ws.cell(row=row, column=5, value=meta["name"])
            ws.cell(row=row, column=6, value=meta["formula"])
            for y_idx, y in enumerate(years):
                row_match = df_t[df_t["year"] == y]
                val = row_match[rcode].values[0] if len(row_match) > 0 and rcode in row_match.columns else None
                if pd.notna(val) and val is not None:
                    try:
                        ws.cell(row=row, column=7 + y_idx, value=float(val))
                    except (ValueError, TypeError):
                        pass
            row += 1

    return row - 1  # last data row


# =====================================================================
# SHEET: Bao_Cao_Tai_Chinh (Report with INDEX/MATCH formulas)
# =====================================================================

def _create_bctc_report_sheet(ws, df_master, tickers, years, bctc_last_row):
    """Create visible BCTC report with dynamic INDEX/MATCH formulas."""
    ws.sheet_properties.tabColor = _NAVY
    max_col = 3 + len(years)

    # Row 1: Title
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max_col)
    ws.cell(row=1, column=1, value="BÁO CÁO TÀI CHÍNH DOANH NGHIỆP").font = _TITLE_FONT

    # Row 2: Ticker selector
    ws.cell(row=2, column=1, value="Chọn Mã CK →").font = _LABEL_FONT
    ws.cell(row=2, column=1).alignment = Alignment(horizontal="right", vertical="center")

    cell_b2 = ws.cell(row=2, column=2, value=tickers[0])
    cell_b2.font = Font(name="Segoe UI", size=12, bold=True, color=_NAVY)
    cell_b2.fill = _DROPDOWN_FILL
    cell_b2.alignment = _CENTER
    cell_b2.border = _GOLD_BORDER

    dv = DataValidation(type="list", formula1='"' + ",".join(tickers) + '"', allow_blank=False)
    dv.prompt = "Chọn mã chứng khoán để xem BCTC"
    dv.promptTitle = "Mã CK"
    ws.add_data_validation(dv)
    dv.add(ws["B2"])

    ws.cell(row=2, column=3, value="← Chọn mã CK, dữ liệu bên dưới tự động cập nhật").font = _SMALL_FONT

    # Row 4: Column headers
    headers = ["Phân nhóm báo cáo", "Mã chỉ tiêu", "Tên chỉ tiêu"] + [str(y) for y in years]
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col_idx, value=h)
        cell.font = _HEADER_FONT
        cell.fill = _NAVY_FILL
        cell.alignment = _CENTER
        cell.border = _THIN_BORDER

    # Data rows: section headers + formula rows
    row = 5
    current_category = None
    item_count = 0

    for _, mrow in df_master.iterrows():
        cat = str(mrow["category"])

        # Section header row when category changes
        if cat != current_category:
            current_category = cat
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=max_col)
            sc = ws.cell(row=row, column=1, value=f"  {cat}")
            sc.font = _SECTION_FONT
            sc.fill = _SECTION_FILL
            sc.alignment = _LEFT
            sc.border = _SECTION_BORDER
            row += 1

        # Data row with static labels + INDEX/MATCH formula cells
        icode = str(mrow["item_code"])
        iname = str(mrow["item_name"])

        ws.cell(row=row, column=1, value=cat).font = _SMALL_FONT
        ws.cell(row=row, column=1).alignment = _LEFT
        ws.cell(row=row, column=2, value=icode).font = _BODY_FONT
        ws.cell(row=row, column=2).alignment = _LEFT
        ws.cell(row=row, column=3, value=iname).font = _BODY_FONT
        ws.cell(row=row, column=3).alignment = _LEFT

        # Formula cells for each year column
        for y_idx in range(len(years)):
            dcol = get_column_letter(6 + y_idx)  # Data_BCTC year cols start at F (col 6)
            formula = (
                f'=IFERROR(INDEX(Data_BCTC!${dcol}$2:${dcol}${bctc_last_row},'
                f'MATCH($B$2&"_"&$B{row},Data_BCTC!$A$2:$A${bctc_last_row},0)),"")'
            )
            cell = ws.cell(row=row, column=4 + y_idx, value=formula)
            cell.number_format = "#,##0"
            cell.font = _BODY_FONT
            cell.alignment = _RIGHT

        # Zebra striping
        fill = _ZEBRA_EVEN if item_count % 2 == 0 else _ZEBRA_ODD
        for col_idx in range(1, max_col + 1):
            ws.cell(row=row, column=col_idx).fill = fill
            ws.cell(row=row, column=col_idx).border = _THIN_BORDER

        item_count += 1
        row += 1

    # Column widths
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 28
    ws.column_dimensions["C"].width = 52
    for y_idx in range(len(years)):
        ws.column_dimensions[get_column_letter(4 + y_idx)].width = 20

    ws.freeze_panes = "D5"
    ws.auto_filter.ref = f"A4:{get_column_letter(max_col)}{row - 1}"

    return row - 1  # last row


# =====================================================================
# SHEET: Ty_So_Tai_Chinh (Report with INDEX/MATCH formulas)
# =====================================================================

def _create_tyso_report_sheet(ws, tickers, years, active_ratios, tyso_last_row):
    """Create visible Ty So report with dynamic INDEX/MATCH formulas."""
    ws.sheet_properties.tabColor = _TEAL
    max_col = 4 + len(years)

    # Row 1: Title
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max_col)
    ws.cell(row=1, column=1, value="CÁC TỶ SỐ TÀI CHÍNH PHÂN TÍCH (CHUẨN WIDATA)").font = _TITLE_FONT

    # Row 2: Ticker selector
    ws.cell(row=2, column=1, value="Chọn Mã CK →").font = _LABEL_FONT
    ws.cell(row=2, column=1).alignment = Alignment(horizontal="right", vertical="center")

    cell_b2 = ws.cell(row=2, column=2, value=tickers[0])
    cell_b2.font = Font(name="Segoe UI", size=12, bold=True, color=_TEAL)
    cell_b2.fill = _DROPDOWN_FILL
    cell_b2.alignment = _CENTER
    cell_b2.border = _GOLD_BORDER

    dv = DataValidation(type="list", formula1='"' + ",".join(tickers) + '"', allow_blank=False)
    dv.prompt = "Chọn mã chứng khoán để xem tỷ số"
    dv.promptTitle = "Mã CK"
    ws.add_data_validation(dv)
    dv.add(ws["B2"])

    ws.cell(row=2, column=3, value="← Chọn mã CK, dữ liệu bên dưới tự động cập nhật").font = _SMALL_FONT

    # Row 4: Headers
    headers = ["Phân nhóm tỷ số", "Mã chỉ số", "Tên chỉ số tài chính", "Công thức tính toán"] + [str(y) for y in years]
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col_idx, value=h)
        cell.font = _HEADER_FONT
        cell.fill = _TEAL_FILL
        cell.alignment = _CENTER
        cell.border = _THIN_BORDER

    # Data rows
    row = 5
    current_group = None
    item_count = 0

    for rcode in active_ratios:
        meta = WIDATA_RATIOS.get(rcode, {"name": rcode, "group": "Tỷ số tài chính", "formula": "", "fmt": "0.00%"})
        group = meta["group"]

        # Section header
        if group != current_group:
            current_group = group
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=max_col)
            sc = ws.cell(row=row, column=1, value=f"  {group}")
            sc.font = _SECTION_FONT
            sc.fill = _SECTION_FILL
            sc.alignment = _LEFT
            sc.border = Border(bottom=Side(style="medium", color=_TEAL))
            row += 1

        # Data row
        ws.cell(row=row, column=1, value=group).font = _SMALL_FONT
        ws.cell(row=row, column=1).alignment = _LEFT
        ws.cell(row=row, column=2, value=rcode).font = _BODY_FONT
        ws.cell(row=row, column=2).alignment = _LEFT
        ws.cell(row=row, column=3, value=meta["name"]).font = _BODY_FONT
        ws.cell(row=row, column=3).alignment = _LEFT
        ws.cell(row=row, column=4, value=meta["formula"]).font = _SMALL_FONT
        ws.cell(row=row, column=4).alignment = _LEFT

        # Formula cells
        num_fmt = meta.get("fmt", "0.00%")
        for y_idx in range(len(years)):
            dcol = get_column_letter(7 + y_idx)  # Data_TySo year cols start at G (col 7)
            formula = (
                f'=IFERROR(INDEX(Data_TySo!${dcol}$2:${dcol}${tyso_last_row},'
                f'MATCH($B$2&"_"&$B{row},Data_TySo!$A$2:$A${tyso_last_row},0)),"")'
            )
            cell = ws.cell(row=row, column=5 + y_idx, value=formula)
            cell.number_format = num_fmt
            cell.font = _BODY_FONT
            cell.alignment = _RIGHT

        # Zebra striping
        fill = _ZEBRA_EVEN if item_count % 2 == 0 else _ZEBRA_ODD
        for col_idx in range(1, max_col + 1):
            ws.cell(row=row, column=col_idx).fill = fill
            ws.cell(row=row, column=col_idx).border = _THIN_BORDER

        item_count += 1
        row += 1

    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 28
    ws.column_dimensions["C"].width = 52
    ws.column_dimensions["D"].width = 44
    for y_idx in range(len(years)):
        ws.column_dimensions[get_column_letter(5 + y_idx)].width = 18

    ws.freeze_panes = "E5"
    ws.auto_filter.ref = f"A4:{get_column_letter(max_col)}{row - 1}"

    return row - 1


# =====================================================================
# SHEET: Panel_Data_Goc (flat panel with actual values)
# =====================================================================

def _create_panel_sheet(ws, pivot):
    """Create Panel Data sheet with actual values for Stata/R/Python."""
    ws.sheet_properties.tabColor = "38A169"

    pnl_cols = list(pivot.columns)
    for c_idx, col_name in enumerate(pnl_cols, 1):
        cell = ws.cell(row=1, column=c_idx, value=col_name)
        cell.font = _HEADER_FONT
        cell.fill = PatternFill(start_color="205375", end_color="205375", fill_type="solid")
        cell.alignment = _CENTER
        cell.border = _THIN_BORDER

    for r_idx, (_, r) in enumerate(pivot.iterrows(), 2):
        for c_idx, col_name in enumerate(pnl_cols, 1):
            val = r[col_name]
            cell = ws.cell(row=r_idx, column=c_idx)
            if pd.notna(val) and val is not None:
                if isinstance(val, (int, float)):
                    cell.value = float(val)
                    if col_name == "year":
                        cell.number_format = "0"
                    elif col_name != "ticker":
                        cell.number_format = "#,##0.00" if abs(float(val)) < 100 else "#,##0"
                else:
                    cell.value = str(val)
            cell.font = _BODY_FONT
            cell.border = _THIN_BORDER

        # Zebra
        fill = _ZEBRA_EVEN if (r_idx - 2) % 2 == 0 else _ZEBRA_ODD
        for c_idx in range(1, len(pnl_cols) + 1):
            ws.cell(row=r_idx, column=c_idx).fill = fill

    ws.auto_filter.ref = f"A1:{get_column_letter(len(pnl_cols))}{len(pivot) + 1}"
    ws.freeze_panes = "C2"
    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 12
    for c_idx in range(3, min(len(pnl_cols) + 1, 60)):
        ws.column_dimensions[get_column_letter(c_idx)].width = 18


# =====================================================================
# SHEET: Codebook
# =====================================================================

def _create_codebook_sheet(ws, fin_codebook):
    """Create Codebook sheet with variable definitions."""
    ws.sheet_properties.tabColor = "805AD5"

    cb_headers = ["Biến", "Tên chỉ tiêu", "Phân loại / Nhóm", "Phân loại", "Công thức / Nguồn"]
    for c_idx, h in enumerate(cb_headers, 1):
        cell = ws.cell(row=1, column=c_idx, value=h)
        cell.font = _HEADER_FONT
        cell.fill = PatternFill(start_color="805AD5", end_color="805AD5", fill_type="solid")
        cell.alignment = _CENTER
        cell.border = _THIN_BORDER

    # Codebook strictly mirrors exported variables in fin_codebook
    cb_full = list(fin_codebook)

    for r_idx, item in enumerate(cb_full, 2):
        for c_idx, h in enumerate(cb_headers, 1):
            val = item.get(h, "")
            cell = ws.cell(row=r_idx, column=c_idx, value=val)
            cell.font = _BODY_FONT
            cell.border = _THIN_BORDER
            cell.alignment = _CENTER if c_idx in (1, 3, 4) else _LEFT

        fill = _ZEBRA_EVEN if (r_idx - 2) % 2 == 0 else _ZEBRA_ODD
        for c_idx in range(1, 6):
            ws.cell(row=r_idx, column=c_idx).fill = fill

    ws.column_dimensions["D"].width = 26
    ws.column_dimensions["E"].width = 48


# =====================================================================
# SHEET: Huong_Dan (Guide — no VBA)
# =====================================================================

def _create_guide_sheet(ws):
    """Create guide sheet explaining how to use the ticker selector."""
    ws.sheet_properties.tabColor = _GOLD

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=2)
    ws.cell(row=1, column=1, value="HƯỚNG DẪN SỬ DỤNG BÁO CÁO TÀI CHÍNH").font = _TITLE_FONT

    instructions = [
        ("1. Cách chọn mã chứng khoán (Tự động — không cần Macro):", [
            "Tại sheet 'Bao_Cao_Tai_Chinh' hoặc 'Ty_So_Tai_Chinh', nhấp vào ô B2 (ô viền vàng).",
            "Một mũi tên nhỏ ▼ sẽ xuất hiện bên phải ô. Nhấp vào mũi tên đó để mở danh sách thả xuống.",
            "Chọn mã chứng khoán bạn muốn xem (ví dụ: VCB, HPG, VNM...).",
            "TOÀN BỘ dữ liệu trên sheet sẽ TỰ ĐỘNG cập nhật sang công ty bạn vừa chọn.",
            "Bạn cũng có thể gõ trực tiếp mã CK vào ô B2 rồi nhấn Enter.",
        ]),
        ("2. Tổng quan các Tab trong bảng tính:", [
            "Bao_Cao_Tai_Chinh: Toàn bộ chỉ tiêu kế toán phân chia theo 13 nhóm chuẩn mực.",
            "Ty_So_Tai_Chinh: Hệ thống tỷ số tài chính được trích chọn theo chuẩn WiData.",
            "Panel_Data_Goc: Bảng dữ liệu phẳng Panel Data (tất cả mã CK) để chạy hồi quy trên Stata/R/Python.",
            "Codebook: Từ điển định nghĩa chi tiết từng biến thực tế xuất hiện trong tập dữ liệu.",
        ]),
        ("3. Sử dụng bộ lọc AutoFilter bổ sung:", [
            "Tại dòng tiêu đề (dòng 4), mỗi cột đều có mũi tên lọc ▼.",
            "Bấm vào mũi tên trên cột 'Phân nhóm báo cáo' để lọc theo nhóm kế toán cụ thể.",
            "Ví dụ: chỉ hiện nhóm 'CĐKT. TÀI SẢN NGẮN HẠN' hoặc 'KQKD. DOANH THU, CHI PHÍ, LỢI NHUẬN'.",
        ]),
        ("4. Lưu ý quan trọng:", [
            "File này KHÔNG sử dụng Macro (VBA). Mọi tính năng đều hoạt động trên mọi phiên bản Excel.",
            "Tương thích: Windows Excel, macOS Excel, Excel Online, Google Sheets, LibreOffice Calc.",
            "Khi mở file lần đầu, Excel có thể hỏi 'Enable Editing' — hãy bấm chấp nhận.",
            "Sheet 'Panel_Data_Goc' chứa dữ liệu gốc của TẤT CẢ mã CK — dùng để import vào Stata (.dta) hoặc R.",
        ]),
    ]

    r_idx = 3
    for title, lines in instructions:
        ws.cell(row=r_idx, column=1, value=title).font = _SECTION_FONT
        r_idx += 1
        for line in lines:
            ws.cell(row=r_idx, column=1, value=f"   • {line}").font = _BODY_FONT
            r_idx += 1
        r_idx += 1

    ws.column_dimensions["A"].width = 105


# =====================================================================
# MAIN: Populate all sheets
# =====================================================================

def populate_financial_sheets(
    wb: openpyxl.Workbook,
    all_data: pd.DataFrame,
    pivot: pd.DataFrame,
    ratio_cols: Dict[str, str],
    fin_codebook: List[Dict[str, Any]],
    missing_tickers: Optional[List[str]] = None,
) -> openpyxl.Workbook:
    """
    Populate an openpyxl Workbook with financial sheets:
    - Trang_Bia (Cover)
    - Bao_Cao_Tai_Chinh (Dropdown B2 + INDEX/MATCH)
    - Ty_So_Tai_Chinh (Ratios + Dropdown B2 + INDEX/MATCH - if ratios selected)
    - Panel_Data_Goc (Flat panel data for all tickers)
    - Codebook
    - Huong_Dan
    - Data_BCTC (Hidden raw data sheet for formulas)
    - Data_TySo (Hidden ratio data sheet for formulas - if ratios selected)
    """
    # Compute WiData metrics
    pivot = compute_widata_metrics(pivot)

    tickers = sorted([str(t) for t in pivot["ticker"].dropna().unique().tolist()])
    years = sorted([int(y) for y in pivot["year"].dropna().unique().tolist()])

    # Master item list
    df_master = _get_master_items(all_data, fin_codebook)

    # Data lookup
    data_lookup = _build_data_lookup(all_data)

    # Active ratios (Strictly respect caller's ratio_cols)
    if ratio_cols is not None:
        active_ratios = [r for r in ratio_cols.keys() if r in WIDATA_RATIOS]
    elif fin_codebook:
        selected_ratios = [item.get("Biến") for item in fin_codebook if item.get("Phân loại") == "Tỷ số tài chính WiData"]
        active_ratios = [r for r in WIDATA_RATIOS if r in selected_ratios]
    else:
        active_ratios = [r for r in WIDATA_RATIOS.keys() if r in pivot.columns]

    # 1. Hidden Data sheets (must be created FIRST for formula references)
    ws_data_bctc = wb.create_sheet("Data_BCTC")
    bctc_last_row = _create_hidden_bctc_sheet(ws_data_bctc, df_master, tickers, years, data_lookup)

    if active_ratios:
        ws_data_tyso = wb.create_sheet("Data_TySo")
        tyso_last_row = _create_hidden_tyso_sheet(ws_data_tyso, pivot, tickers, years, active_ratios)

    # 2. Cover sheet
    ws_cover = wb.create_sheet("Trang_Bia", 0)  # Insert at position 0 (first)
    _create_cover_sheet(ws_cover, tickers, years, missing_tickers=missing_tickers)

    # 3. BCTC report (with formulas)
    ws_bctc = wb.create_sheet("Bao_Cao_Tai_Chinh")
    _create_bctc_report_sheet(ws_bctc, df_master, tickers, years, bctc_last_row)

    # 4. TySo report (with formulas) - only if active_ratios
    if active_ratios:
        ws_tyso = wb.create_sheet("Ty_So_Tai_Chinh")
        _create_tyso_report_sheet(ws_tyso, tickers, years, active_ratios, tyso_last_row)

    # 5. Panel Data (actual values for Stata/R/Python)
    ws_panel = wb.create_sheet("Panel_Data_Goc")
    _create_panel_sheet(ws_panel, pivot)

    # 6. Codebook
    ws_codebook = wb.create_sheet("Codebook")
    _create_codebook_sheet(ws_codebook, fin_codebook)

    # 7. Guide
    ws_guide = wb.create_sheet("Huong_Dan")
    _create_guide_sheet(ws_guide)

    return wb


def export_financial_workbook(
    all_data: pd.DataFrame,
    pivot: pd.DataFrame,
    ratio_cols: Dict[str, str],
    fin_codebook: List[Dict[str, Any]],
    export_xlsx: Path,
    missing_tickers: Optional[List[str]] = None,
) -> Path:
    """Export a single professional .xlsx file (no VBA/Macro needed)."""
    wb = openpyxl.Workbook()
    populate_financial_sheets(wb, all_data, pivot, ratio_cols, fin_codebook, missing_tickers=missing_tickers)

    # Remove the default "Sheet" created by openpyxl
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    # Set Trang_Bia as active sheet
    if "Trang_Bia" in wb.sheetnames:
        wb.active = wb.sheetnames.index("Trang_Bia")

    wb.save(export_xlsx)
    wb.close()
    logger.success(f"Đã xuất file Excel chuyên nghiệp: {export_xlsx.name}")
    return export_xlsx


# Backward-compatible wrapper (server.py may call this with old signature)
def export_financial_workbooks(
    all_data: pd.DataFrame,
    pivot: pd.DataFrame,
    ratio_cols: Dict[str, str],
    fin_codebook: List[Dict[str, Any]],
    export_xlsx: Path,
    export_xlsm: Optional[Path] = None,
    template_xlsm: Optional[Path] = None,
    missing_tickers: Optional[List[str]] = None,
) -> Dict[str, Path]:
    """Export .xlsx file. The xlsm parameters are accepted but ignored (deprecated)."""
    result_path = export_financial_workbook(all_data, pivot, ratio_cols, fin_codebook, export_xlsx, missing_tickers=missing_tickers)
    return {"xlsx": result_path}
