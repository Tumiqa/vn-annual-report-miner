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
- Tab Ty_So_Tai_Chinh: He thong 116 chi so tai chinh toan dien chuan hoc thuat (CFA, VAS/IFRS, Basel III, CAMELS).
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


# He thong 116 chi so tai chinh chuan hoc thuat (CFA, VAS/IFRS, Basel III, CAMELS)
FINANCIAL_RATIOS = {
    # -------------------------------------------------------------
    # Trụ cột 1: Khả năng sinh lời & Hiệu quả vốn (15 chỉ số)
    # -------------------------------------------------------------
    "roa": {
        "name": "Tỷ suất sinh lời trên tổng tài sản (ROA) (%) (Y)",
        "group": "1. Khả năng sinh lời & Hiệu quả vốn",
        "formula": "Lợi nhuận sau thuế / Tổng tài sản",
        "fmt": "0.00%",
    },
    "roe": {
        "name": "Tỷ suất sinh lời trên vốn chủ sở hữu (ROE) (%) (Y)",
        "group": "1. Khả năng sinh lời & Hiệu quả vốn",
        "formula": "Lợi nhuận sau thuế / Vốn chủ sở hữu",
        "fmt": "0.00%",
    },
    "roce": {
        "name": "Tỷ suất sinh lời trên vốn sử dụng (ROCE) (%) (Y)",
        "group": "1. Khả năng sinh lời & Hiệu quả vốn",
        "formula": "EBIT / (Tổng tài sản - Nợ ngắn hạn)",
        "fmt": "0.00%",
    },
    "roic": {
        "name": "Tỷ suất sinh lời trên vốn đầu tư (ROIC) (%) (Y)",
        "group": "1. Khả năng sinh lời & Hiệu quả vốn",
        "formula": "EBIT*(1 - Thuế suất) / (Vốn CSH + Nợ vay tài chính - Tiền mặt)",
        "fmt": "0.00%",
    },
    "gross_margin": {
        "name": "Biên lợi nhuận gộp (Gross Margin) (%) (Y)",
        "group": "1. Khả năng sinh lời & Hiệu quả vốn",
        "formula": "Lợi nhuận gộp / Doanh thu thuần",
        "fmt": "0.00%",
    },
    "operating_margin": {
        "name": "Biên lợi nhuận hoạt động (Operating Margin) (%) (Y)",
        "group": "1. Khả năng sinh lời & Hiệu quả vốn",
        "formula": "EBIT / Doanh thu thuần",
        "fmt": "0.00%",
    },
    "ebitda_margin": {
        "name": "Biên EBITDA (EBITDA Margin) (%) (Y)",
        "group": "1. Khả năng sinh lời & Hiệu quả vốn",
        "formula": "EBITDA / Doanh thu thuần",
        "fmt": "0.00%",
    },
    "net_margin": {
        "name": "Biên lợi nhuận ròng (Net Profit Margin) (%) (Y)",
        "group": "1. Khả năng sinh lời & Hiệu quả vốn",
        "formula": "Lợi nhuận sau thuế / Doanh thu thuần",
        "fmt": "0.00%",
    },
    "ebt_margin": {
        "name": "Biên lợi nhuận trước thuế (EBT Margin) (%) (Y)",
        "group": "1. Khả năng sinh lời & Hiệu quả vốn",
        "formula": "Lợi nhuận trước thuế / Doanh thu thuần",
        "fmt": "0.00%",
    },
    "effective_tax_rate": {
        "name": "Thuế suất thực tế (Effective Tax Rate) (%) (Y)",
        "group": "1. Khả năng sinh lời & Hiệu quả vốn",
        "formula": "Chi phí thuế TNDN / Lợi nhuận trước thuế",
        "fmt": "0.00%",
    },
    "dupont_tax_burden": {
        "name": "DuPont - Gánh nặng thuế (Tax Burden) (Lần) (Y)",
        "group": "1. Khả năng sinh lời & Hiệu quả vốn",
        "formula": "LNST / Lợi nhuận trước thuế (EAT / EBT)",
        "fmt": "0.000",
    },
    "dupont_interest_burden": {
        "name": "DuPont - Gánh nặng lãi vay (Interest Burden) (Lần) (Y)",
        "group": "1. Khả năng sinh lời & Hiệu quả vốn",
        "formula": "Lợi nhuận trước thuế / EBIT (EBT / EBIT)",
        "fmt": "0.000",
    },
    "dupont_operating_margin": {
        "name": "DuPont - Biên hoạt động (Operating Margin) (%) (Y)",
        "group": "1. Khả năng sinh lời & Hiệu quả vốn",
        "formula": "EBIT / Doanh thu thuần",
        "fmt": "0.00%",
    },
    "dupont_asset_turnover": {
        "name": "DuPont - Vòng quay tổng tài sản (Asset Turnover) (Lần) (Y)",
        "group": "1. Khả năng sinh lời & Hiệu quả vốn",
        "formula": "Doanh thu thuần / Tổng tài sản",
        "fmt": "0.00",
    },
    "dupont_equity_multiplier": {
        "name": "DuPont - Đòn bẩy tài chính (Equity Multiplier) (Lần) (Y)",
        "group": "1. Khả năng sinh lời & Hiệu quả vốn",
        "formula": "Tổng tài sản / Vốn chủ sở hữu",
        "fmt": "0.00",
    },

    # -------------------------------------------------------------
    # Trụ cột 2: Cấu trúc vốn & Đòn bẩy tài chính (13 chỉ số)
    # -------------------------------------------------------------
    "debt_to_assets": {
        "name": "Hệ số nợ trên tổng tài sản (D/A) (%) (Y)",
        "group": "2. Cấu trúc vốn & Đòn bẩy tài chính",
        "formula": "Nợ phải trả / Tổng tài sản",
        "fmt": "0.00%",
    },
    "debt_to_equity": {
        "name": "Hệ số nợ trên vốn chủ sở hữu (D/E) (Lần) (Y)",
        "group": "2. Cấu trúc vốn & Đòn bẩy tài chính",
        "formula": "Nợ phải trả / Vốn chủ sở hữu",
        "fmt": "0.00",
    },
    "fin_debt_to_assets": {
        "name": "Hệ số nợ vay tài chính trên tổng tài sản (%) (Y)",
        "group": "2. Cấu trúc vốn & Đòn bẩy tài chính",
        "formula": "(Vay ngắn hạn + Vay dài hạn) / Tổng tài sản",
        "fmt": "0.00%",
    },
    "fin_debt_to_equity": {
        "name": "Hệ số nợ vay tài chính trên vốn CSH (Lần) (Y)",
        "group": "2. Cấu trúc vốn & Đòn bẩy tài chính",
        "formula": "(Vay ngắn hạn + Vay dài hạn) / Vốn chủ sở hữu",
        "fmt": "0.00",
    },
    "equity_to_assets": {
        "name": "Hệ số tự tài trợ (Equity / Assets) (%) (Y)",
        "group": "2. Cấu trúc vốn & Đòn bẩy tài chính",
        "formula": "Vốn chủ sở hữu / Tổng tài sản",
        "fmt": "0.00%",
    },
    "equity_multiplier": {
        "name": "Đòn bẩy tài chính (Equity Multiplier) (Lần) (Y)",
        "group": "2. Cấu trúc vốn & Đòn bẩy tài chính",
        "formula": "Tổng tài sản / Vốn chủ sở hữu",
        "fmt": "0.00",
    },
    "st_debt_to_total_debt": {
        "name": "Tỷ trọng nợ vay ngắn hạn / Tổng nợ vay (%) (Y)",
        "group": "2. Cấu trúc vốn & Đòn bẩy tài chính",
        "formula": "Vay ngắn hạn / Tổng nợ vay tài chính",
        "fmt": "0.00%",
    },
    "lt_debt_to_total_debt": {
        "name": "Tỷ trọng nợ vay dài hạn / Tổng nợ vay (%) (Y)",
        "group": "2. Cấu trúc vốn & Đòn bẩy tài chính",
        "formula": "Vay dài hạn / Tổng nợ vay tài chính",
        "fmt": "0.00%",
    },
    "interest_coverage": {
        "name": "Hệ số chi trả lãi vay (TIE - Interest Coverage) (Lần) (Y)",
        "group": "2. Cấu trúc vốn & Đòn bẩy tài chính",
        "formula": "EBIT / Chi phí lãi vay",
        "fmt": "0.00",
    },
    "debt_to_ebitda": {
        "name": "Tỷ lệ nợ vay tài chính trên EBITDA (Lần) (Y)",
        "group": "2. Cấu trúc vốn & Đòn bẩy tài chính",
        "formula": "Nợ vay tài chính / EBITDA",
        "fmt": "0.00",
    },
    "cfo_to_debt": {
        "name": "Khả năng trả nợ vay từ dòng tiền HĐKD (%) (Y)",
        "group": "2. Cấu trúc vốn & Đòn bẩy tài chính",
        "formula": "Dòng tiền thuần HĐKD (CFO) / Nợ vay tài chính",
        "fmt": "0.00%",
    },
    "cfo_to_liabilities": {
        "name": "Khả năng trang trải tổng nợ từ dòng tiền HĐKD (%) (Y)",
        "group": "2. Cấu trúc vốn & Đòn bẩy tài chính",
        "formula": "Dòng tiền thuần HĐKD (CFO) / Tổng nợ phải trả",
        "fmt": "0.00%",
    },
    "fin_leverage_ratio": {
        "name": "Hệ số đòn bẩy tài sản trên vốn (Assets / Equity) (Lần) (Y)",
        "group": "2. Cấu trúc vốn & Đòn bẩy tài chính",
        "formula": "Tổng tài sản / Vốn chủ sở hữu",
        "fmt": "0.00",
    },

    # -------------------------------------------------------------
    # Trụ cột 3: Thanh khoản & Vốn lưu động (8 chỉ số)
    # -------------------------------------------------------------
    "current_ratio": {
        "name": "Hệ số khả năng thanh toán hiện hành (Current Ratio) (Lần) (Y)",
        "group": "3. Thanh khoản & Vốn lưu động",
        "formula": "Tài sản ngắn hạn / Nợ ngắn hạn",
        "fmt": "0.00",
    },
    "quick_ratio": {
        "name": "Hệ số khả năng thanh toán nhanh (Quick Ratio) (Lần) (Y)",
        "group": "3. Thanh khoản & Vốn lưu động",
        "formula": "(Tài sản ngắn hạn - Hàng tồn kho) / Nợ ngắn hạn",
        "fmt": "0.00",
    },
    "cash_ratio": {
        "name": "Hệ số thanh toán tiền mặt (Cash Ratio) (Lần) (Y)",
        "group": "3. Thanh khoản & Vốn lưu động",
        "formula": "(Tiền và tương đương tiền + Đầu tư tài chính ngắn hạn) / Nợ ngắn hạn",
        "fmt": "0.00",
    },
    "cash_to_assets": {
        "name": "Tỷ trọng tiền mặt trên tổng tài sản (%) (Y)",
        "group": "3. Thanh khoản & Vốn lưu động",
        "formula": "Tiền và tương đương tiền / Tổng tài sản",
        "fmt": "0.00%",
    },
    "working_capital": {
        "name": "Vốn lưu động ròng (Net Working Capital) (VND) (Y)",
        "group": "3. Thanh khoản & Vốn lưu động",
        "formula": "Tài sản ngắn hạn - Nợ ngắn hạn",
        "fmt": "#,##0",
    },
    "nwc_to_assets": {
        "name": "Tỷ lệ vốn lưu động ròng trên tổng tài sản (%) (Y)",
        "group": "3. Thanh khoản & Vốn lưu động",
        "formula": "Vốn lưu động ròng / Tổng tài sản",
        "fmt": "0.00%",
    },
    "nwc_to_revenue": {
        "name": "Tỷ lệ vốn lưu động ròng trên doanh thu (%) (Y)",
        "group": "3. Thanh khoản & Vốn lưu động",
        "formula": "Vốn lưu động ròng / Doanh thu thuần",
        "fmt": "0.00%",
    },
    "defensive_interval": {
        "name": "Số ngày phòng thủ thanh khoản (Defensive Interval) (Ngày) (Y)",
        "group": "3. Thanh khoản & Vốn lưu động",
        "formula": "(Tiền + Phải thu khách hàng) / (Tổng chi phí hoạt động / 365)",
        "fmt": "0.0",
    },

    # -------------------------------------------------------------
    # Trụ cột 4: Hiệu quả hoạt động & Vòng quay tài sản (13 chỉ số)
    # -------------------------------------------------------------
    "asset_turnover": {
        "name": "Vòng quay tổng tài sản (Asset Turnover) (Lần) (Y)",
        "group": "4. Hiệu quả hoạt động & Vòng quay tài sản",
        "formula": "Doanh thu thuần / Tổng tài sản",
        "fmt": "0.00",
    },
    "fixed_asset_turnover": {
        "name": "Vòng quay tài sản cố định (Fixed Asset Turnover) (Lần) (Y)",
        "group": "4. Hiệu quả hoạt động & Vòng quay tài sản",
        "formula": "Doanh thu thuần / Tài sản cố định",
        "fmt": "0.00",
    },
    "inventory_turnover": {
        "name": "Vòng quay hàng tồn kho (Inventory Turnover) (Lần) (Y)",
        "group": "4. Hiệu quả hoạt động & Vòng quay tài sản",
        "formula": "Giá vốn hàng bán / Hàng tồn kho bình quân",
        "fmt": "0.00",
    },
    "dio": {
        "name": "Số ngày lưu kho bình quân (DIO) (Ngày) (Y)",
        "group": "4. Hiệu quả hoạt động & Vòng quay tài sản",
        "formula": "(Hàng tồn kho / Giá vốn hàng bán) * 365",
        "fmt": "0.0",
    },
    "ar_turnover": {
        "name": "Vòng quay các khoản phải thu (Receivables Turnover) (Lần) (Y)",
        "group": "4. Hiệu quả hoạt động & Vòng quay tài sản",
        "formula": "Doanh thu thuần / Phải thu khách hàng",
        "fmt": "0.00",
    },
    "dso": {
        "name": "Số ngày thu tiền bình quân (DSO) (Ngày) (Y)",
        "group": "4. Hiệu quả hoạt động & Vòng quay tài sản",
        "formula": "(Phải thu khách hàng / Doanh thu thuần) * 365",
        "fmt": "0.0",
    },
    "ap_turnover": {
        "name": "Vòng quay các khoản phải trả (Payables Turnover) (Lần) (Y)",
        "group": "4. Hiệu quả hoạt động & Vòng quay tài sản",
        "formula": "Giá vốn hàng bán / Phải trả người bán",
        "fmt": "0.00",
    },
    "dpo": {
        "name": "Số ngày trả tiền bình quân (DPO) (Ngày) (Y)",
        "group": "4. Hiệu quả hoạt động & Vòng quay tài sản",
        "formula": "(Phải trả người bán / Giá vốn hàng bán) * 365",
        "fmt": "0.0",
    },
    "ccc": {
        "name": "Chu kỳ chuyển hóa tiền mặt (Cash Conversion Cycle - CCC) (Ngày) (Y)",
        "group": "4. Hiệu quả hoạt động & Vòng quay tài sản",
        "formula": "DIO + DSO - DPO",
        "fmt": "0.0",
    },
    "working_capital_turnover": {
        "name": "Vòng quay vốn lưu động (Working Capital Turnover) (Lần) (Y)",
        "group": "4. Hiệu quả hoạt động & Vòng quay tài sản",
        "formula": "Doanh thu thuần / Vốn lưu động ròng (NWC)",
        "fmt": "0.00",
    },
    "sga_to_revenue": {
        "name": "Tỷ lệ chi phí bán hàng và QLDN / Doanh thu (%) (Y)",
        "group": "4. Hiệu quả hoạt động & Vòng quay tài sản",
        "formula": "(Chi phí bán hàng + Chi phí QLDN) / Doanh thu thuần",
        "fmt": "0.00%",
    },
    "selling_cost_ratio": {
        "name": "Tỷ lệ chi phí bán hàng trên doanh thu (%) (Y)",
        "group": "4. Hiệu quả hoạt động & Vòng quay tài sản",
        "formula": "Chi phí bán hàng / Doanh thu thuần",
        "fmt": "0.00%",
    },
    "admin_cost_ratio": {
        "name": "Tỷ lệ chi phí QLDN trên doanh thu (%) (Y)",
        "group": "4. Hiệu quả hoạt động & Vòng quay tài sản",
        "formula": "Chi phí quản lý doanh nghiệp / Doanh thu thuần",
        "fmt": "0.00%",
    },

    # -------------------------------------------------------------
    # Trụ cột 5: Chất lượng dòng tiền & Lợi nhuận (11 chỉ số)
    # -------------------------------------------------------------
    "cfo_to_net_income": {
        "name": "Tỷ lệ dòng tiền HĐKD trên LNST (Earnings Quality) (%) (Y)",
        "group": "5. Chất lượng dòng tiền & Lợi nhuận",
        "formula": "Dòng tiền thuần HĐKD (CFO) / Lợi nhuận sau thuế",
        "fmt": "0.00%",
    },
    "cfo_to_revenue": {
        "name": "Tỷ suất sinh dòng tiền trên doanh thu (CFO Margin) (%) (Y)",
        "group": "5. Chất lượng dòng tiền & Lợi nhuận",
        "formula": "Dòng tiền thuần HĐKD (CFO) / Doanh thu thuần",
        "fmt": "0.00%",
    },
    "cfo_to_assets": {
        "name": "Tỷ suất sinh dòng tiền trên tổng tài sản (%) (Y)",
        "group": "5. Chất lượng dòng tiền & Lợi nhuận",
        "formula": "Dòng tiền thuần HĐKD (CFO) / Tổng tài sản",
        "fmt": "0.00%",
    },
    "cfo_to_equity": {
        "name": "Tỷ suất sinh dòng tiền trên vốn chủ sở hữu (%) (Y)",
        "group": "5. Chất lượng dòng tiền & Lợi nhuận",
        "formula": "Dòng tiền thuần HĐKD (CFO) / Vốn chủ sở hữu",
        "fmt": "0.00%",
    },
    "fcf": {
        "name": "Dòng tiền tự do (Free Cash Flow - FCF) (VND) (Y)",
        "group": "5. Chất lượng dòng tiền & Lợi nhuận",
        "formula": "CFO - Tiền chi mua sắm, xây dựng TSCĐ (CAPEX)",
        "fmt": "#,##0",
    },
    "fcf_to_net_income": {
        "name": "Tỷ lệ dòng tiền tự do trên LNST (%) (Y)",
        "group": "5. Chất lượng dòng tiền & Lợi nhuận",
        "formula": "Dòng tiền tự do (FCF) / Lợi nhuận sau thuế",
        "fmt": "0.00%",
    },
    "fcf_to_revenue": {
        "name": "Tỷ lệ dòng tiền tự do trên doanh thu (%) (Y)",
        "group": "5. Chất lượng dòng tiền & Lợi nhuận",
        "formula": "Dòng tiền tự do (FCF) / Doanh thu thuần",
        "fmt": "0.00%",
    },
    "capex_to_revenue": {
        "name": "Tỷ lệ đầu tư vốn CAPEX trên doanh thu (%) (Y)",
        "group": "5. Chất lượng dòng tiền & Lợi nhuận",
        "formula": "Tiền chi mua sắm TSCĐ (CAPEX) / Doanh thu thuần",
        "fmt": "0.00%",
    },
    "capex_to_assets": {
        "name": "Tỷ lệ đầu tư vốn CAPEX trên tổng tài sản (%) (Y)",
        "group": "5. Chất lượng dòng tiền & Lợi nhuận",
        "formula": "Tiền chi mua sắm TSCĐ (CAPEX) / Tổng tài sản",
        "fmt": "0.00%",
    },
    "cfo_to_capex": {
        "name": "Hệ số tự tài trợ đầu tư CAPEX từ dòng tiền HĐKD (Lần) (Y)",
        "group": "5. Chất lượng dòng tiền & Lợi nhuận",
        "formula": "Dòng tiền thuần HĐKD (CFO) / CAPEX",
        "fmt": "0.00",
    },
    "accruals_to_assets": {
        "name": "Mức độ dồn tích kế toán trên tài sản (Accruals / Assets) (%) (Y)",
        "group": "5. Chất lượng dòng tiền & Lợi nhuận",
        "formula": "(Lợi nhuận sau thuế - CFO) / Tổng tài sản",
        "fmt": "0.00%",
    },

    # -------------------------------------------------------------
    # Trụ cột 6: Đặc thù Ngân hàng (CAMELS) (10 chỉ số)
    # -------------------------------------------------------------
    "bank_nim": {
        "name": "Tỷ lệ thu nhập lãi thuần (NIM - Net Interest Margin) (%) (Y)",
        "group": "6. Đặc thù Ngân hàng (CAMELS)",
        "formula": "Thu nhập lãi thuần / Tổng tài sản sinh lời (hoặc Tổng tài sản)",
        "fmt": "0.00%",
    },
    "bank_cir": {
        "name": "Tỷ lệ chi phí trên thu nhập (CIR - Cost to Income Ratio) (%) (Y)",
        "group": "6. Đặc thù Ngân hàng (CAMELS)",
        "formula": "Tổng chi phí hoạt động / Tổng thu nhập hoạt động (TOI)",
        "fmt": "0.00%",
    },
    "bank_ldr": {
        "name": "Tỷ lệ dư nợ cho vay trên tiền gửi (LDR) (%) (Y)",
        "group": "6. Đặc thù Ngân hàng (CAMELS)",
        "formula": "Cho vay khách hàng / Tiền gửi của khách hàng",
        "fmt": "0.00%",
    },
    "bank_provision_coverage": {
        "name": "Tỷ lệ dự phòng rủi ro trên dư nợ cho vay (%) (Y)",
        "group": "6. Đặc thù Ngân hàng (CAMELS)",
        "formula": "Dự phòng rủi ro cho vay / Dư nợ cho vay khách hàng",
        "fmt": "0.00%",
    },
    "bank_credit_cost": {
        "name": "Tỷ lệ chi phí trích lập dự phòng tín dụng (Credit Cost) (%) (Y)",
        "group": "6. Đặc thù Ngân hàng (CAMELS)",
        "formula": "Chi phí dự phòng rủi ro tín dụng / Cho vay khách hàng",
        "fmt": "0.00%",
    },
    "bank_loans_to_assets": {
        "name": "Tỷ trọng dư nợ cho vay trên tổng tài sản (%) (Y)",
        "group": "6. Đặc thù Ngân hàng (CAMELS)",
        "formula": "Cho vay khách hàng / Tổng tài sản",
        "fmt": "0.00%",
    },
    "bank_deposits_to_assets": {
        "name": "Tỷ trọng tiền gửi khách hàng trên tổng tài sản (%) (Y)",
        "group": "6. Đặc thù Ngân hàng (CAMELS)",
        "formula": "Tiền gửi của khách hàng / Tổng tài sản",
        "fmt": "0.00%",
    },
    "bank_equity_to_assets": {
        "name": "Tỷ lệ an toàn vốn chủ trên tổng tài sản (Equity / Assets) (%) (Y)",
        "group": "6. Đặc thù Ngân hàng (CAMELS)",
        "formula": "Vốn chủ sở hữu / Tổng tài sản",
        "fmt": "0.00%",
    },
    "bank_nii_to_toi": {
        "name": "Tỷ trọng thu nhập lãi thuần trong tổng thu nhập HĐ (%) (Y)",
        "group": "6. Đặc thù Ngân hàng (CAMELS)",
        "formula": "Thu nhập lãi thuần / Tổng thu nhập hoạt động (TOI)",
        "fmt": "0.00%",
    },
    "bank_non_interest_income_ratio": {
        "name": "Tỷ trọng thu nhập ngoài lãi trong tổng thu nhập HĐ (%) (Y)",
        "group": "6. Đặc thù Ngân hàng (CAMELS)",
        "formula": "(Tổng thu nhập HĐ - Thu nhập lãi thuần) / Tổng thu nhập HĐ",
        "fmt": "0.00%",
    },

    # -------------------------------------------------------------
    # Trụ cột 7: Đặc thù Công ty Chứng khoán (14 chỉ số)
    # -------------------------------------------------------------
    "margin_to_equity": {
        "name": "Tỷ lệ dư nợ cho vay ký quỹ (Margin) / Vốn CSH (%) (Y)",
        "group": "7. Đặc thù Công ty Chứng khoán",
        "formula": "Dư nợ cho vay ký quỹ (margin) / Vốn chủ sở hữu",
        "fmt": "0.00%",
    },
    "pct_margin_loans": {
        "name": "Tỷ trọng dư nợ Margin trên tổng tài sản (%) (Y)",
        "group": "7. Đặc thù Công ty Chứng khoán",
        "formula": "Dư nợ cho vay margin / Tổng tài sản",
        "fmt": "0.00%",
    },
    "pct_advances": {
        "name": "Tỷ trọng ứng trước tiền bán chứng khoán trên tổng tài sản (%) (Y)",
        "group": "7. Đặc thù Công ty Chứng khoán",
        "formula": "Ứng trước tiền bán chứng khoán của KH / Tổng tài sản",
        "fmt": "0.00%",
    },
    "pct_fvtpl": {
        "name": "Tỷ trọng tài sản tài chính FVTPL trên tổng tài sản (%) (Y)",
        "group": "7. Đặc thù Công ty Chứng khoán",
        "formula": "Tài sản tài chính FVTPL / Tổng tài sản",
        "fmt": "0.00%",
    },
    "pct_afs": {
        "name": "Tỷ trọng tài sản tài chính sẵn sàng để bán (AFS) trên tổng tài sản (%) (Y)",
        "group": "7. Đặc thù Công ty Chứng khoán",
        "formula": "Tài sản tài chính AFS / Tổng tài sản",
        "fmt": "0.00%",
    },
    "pct_htm": {
        "name": "Tỷ trọng đầu tư nắm giữ đến ngày đáo hạn (HTM) trên tổng tài sản (%) (Y)",
        "group": "7. Đặc thù Công ty Chứng khoán",
        "formula": "Tài sản tài chính HTM / Tổng tài sản",
        "fmt": "0.00%",
    },
    "pct_cash": {
        "name": "Tỷ trọng tiền và tương đương tiền trên tổng tài sản (%) (Y)",
        "group": "7. Đặc thù Công ty Chứng khoán",
        "formula": "Tiền và các khoản tương đương tiền / Tổng tài sản",
        "fmt": "0.00%",
    },
    "pct_brokerage_rev": {
        "name": "Tỷ trọng doanh thu hoạt động môi giới chứng khoán (%) (Y)",
        "group": "7. Đặc thù Công ty Chứng khoán",
        "formula": "Doanh thu môi giới chứng khoán / Doanh thu hoạt động",
        "fmt": "0.00%",
    },
    "pct_proprietary_rev": {
        "name": "Tỷ trọng doanh thu tự doanh và kinh doanh nguồn vốn (%) (Y)",
        "group": "7. Đặc thù Công ty Chứng khoán",
        "formula": "Lãi FVTPL, HTM, AFS / Doanh thu hoạt động",
        "fmt": "0.00%",
    },
    "pct_margin_profit": {
        "name": "Tỷ trọng lãi từ các khoản cho vay và phải thu (%) (Y)",
        "group": "7. Đặc thù Công ty Chứng khoán",
        "formula": "Lãi từ các khoản cho vay và phải thu / Doanh thu hoạt động",
        "fmt": "0.00%",
    },
    "pct_ib_rev": {
        "name": "Tỷ trọng doanh thu tư vấn tài chính & ngân hàng đầu tư (%) (Y)",
        "group": "7. Đặc thù Công ty Chứng khoán",
        "formula": "Doanh thu tư vấn tài chính / Doanh thu hoạt động",
        "fmt": "0.00%",
    },
    "pct_brokerage_cost": {
        "name": "Tỷ trọng chi phí môi giới trên tổng chi phí hoạt động (%) (Y)",
        "group": "7. Đặc thù Công ty Chứng khoán",
        "formula": "Chi phí môi giới chứng khoán / Tổng chi phí hoạt động",
        "fmt": "0.00%",
    },
    "pct_proprietary_cost": {
        "name": "Tỷ trọng chi phí tự doanh trên tổng chi phí hoạt động (%) (Y)",
        "group": "7. Đặc thù Công ty Chứng khoán",
        "formula": "Chi phí tự doanh / Tổng chi phí hoạt động",
        "fmt": "0.00%",
    },
    "pct_provision_cost": {
        "name": "Tỷ trọng chi phí dự phòng TSTC trên tổng chi phí hoạt động (%) (Y)",
        "group": "7. Đặc thù Công ty Chứng khoán",
        "formula": "Chi phí dự phòng TSTC / Tổng chi phí hoạt động",
        "fmt": "0.00%",
    },

    # -------------------------------------------------------------
    # Trụ cột 8: Đặc thù Bất động sản & Xây dựng (6 chỉ số)
    # -------------------------------------------------------------
    "re_prepayments_to_inventory": {
        "name": "Tỷ lệ người mua trả tiền trước / Hàng tồn kho dự án (%) (Y)",
        "group": "8. Đặc thù Bất động sản & Xây dựng",
        "formula": "Người mua trả tiền trước / Hàng tồn kho BĐS",
        "fmt": "0.00%",
    },
    "re_prepayments_to_assets": {
        "name": "Tỷ lệ người mua trả tiền trước / Tổng tài sản (%) (Y)",
        "group": "8. Đặc thù Bất động sản & Xây dựng",
        "formula": "Người mua trả tiền trước / Tổng tài sản",
        "fmt": "0.00%",
    },
    "re_inventory_to_assets": {
        "name": "Tỷ trọng hàng tồn kho BĐS trên tổng tài sản (%) (Y)",
        "group": "8. Đặc thù Bất động sản & Xây dựng",
        "formula": "Hàng tồn kho / Tổng tài sản",
        "fmt": "0.00%",
    },
    "re_wip_to_assets": {
        "name": "Tỷ trọng tài sản dở dang dài hạn / Tổng tài sản (%) (Y)",
        "group": "8. Đặc thù Bất động sản & Xây dựng",
        "formula": "Chi phí XDCB dở dang / Tổng tài sản",
        "fmt": "0.00%",
    },
    "re_debt_to_inventory": {
        "name": "Hệ số nợ vay tài chính trên hàng tồn kho (Lần) (Y)",
        "group": "8. Đặc thù Bất động sản & Xây dựng",
        "formula": "Nợ vay tài chính / Hàng tồn kho BĐS",
        "fmt": "0.00",
    },
    "re_invest_prop_to_assets": {
        "name": "Tỷ trọng bất động sản đầu tư trên tổng tài sản (%) (Y)",
        "group": "8. Đặc thù Bất động sản & Xây dựng",
        "formula": "Bất động sản đầu tư / Tổng tài sản",
        "fmt": "0.00%",
    },

    # -------------------------------------------------------------
    # Trụ cột 9: Tốc độ tăng trưởng cùng kỳ (YoY) (14 chỉ số)
    # -------------------------------------------------------------
    "rev_growth_yoy": {
        "name": "Doanh thu thuần (YoY) (%) (Y)",
        "group": "9. Tốc độ tăng trưởng cùng kỳ (YoY)",
        "formula": "(Doanh thu T - Doanh thu T-1) / |Doanh thu T-1|",
        "fmt": "0.00%",
    },
    "gross_profit_growth_yoy": {
        "name": "Lợi nhuận gộp (YoY) (%) (Y)",
        "group": "9. Tốc độ tăng trưởng cùng kỳ (YoY)",
        "formula": "(Lợi nhuận gộp T - Lợi nhuận gộp T-1) / |Lợi nhuận gộp T-1|",
        "fmt": "0.00%",
    },
    "ebit_growth_yoy": {
        "name": "Lợi nhuận trước lãi vay và thuế (EBIT) (YoY) (%) (Y)",
        "group": "9. Tốc độ tăng trưởng cùng kỳ (YoY)",
        "formula": "(EBIT T - EBIT T-1) / |EBIT T-1|",
        "fmt": "0.00%",
    },
    "ebt_growth_yoy": {
        "name": "Lợi nhuận trước thuế (EBT) (YoY) (%) (Y)",
        "group": "9. Tốc độ tăng trưởng cùng kỳ (YoY)",
        "formula": "(LNTT T - LNTT T-1) / |LNTT T-1|",
        "fmt": "0.00%",
    },
    "eat_growth_yoy": {
        "name": "Lợi nhuận sau thuế (EAT) (YoY) (%) (Y)",
        "group": "9. Tốc độ tăng trưởng cùng kỳ (YoY)",
        "formula": "(LNST T - LNST T-1) / |LNST T-1|",
        "fmt": "0.00%",
    },
    "eat_parent_growth_yoy": {
        "name": "Lợi nhuận sau thuế CĐCT mẹ (YoY) (%) (Y)",
        "group": "9. Tốc độ tăng trưởng cùng kỳ (YoY)",
        "formula": "(LNST mẹ T - LNST mẹ T-1) / |LNST mẹ T-1|",
        "fmt": "0.00%",
    },
    "assets_growth_yoy": {
        "name": "Tổng tài sản (YoY) (%) (Y)",
        "group": "9. Tốc độ tăng trưởng cùng kỳ (YoY)",
        "formula": "(Tổng tài sản T - Tổng tài sản T-1) / Tổng tài sản T-1",
        "fmt": "0.00%",
    },
    "equity_growth_yoy": {
        "name": "Vốn chủ sở hữu (YoY) (%) (Y)",
        "group": "9. Tốc độ tăng trưởng cùng kỳ (YoY)",
        "formula": "(Vốn CSH T - Vốn CSH T-1) / Vốn CSH T-1",
        "fmt": "0.00%",
    },
    "debt_growth_yoy": {
        "name": "Tổng nợ phải trả (YoY) (%) (Y)",
        "group": "9. Tốc độ tăng trưởng cùng kỳ (YoY)",
        "formula": "(Nợ phải trả T - Nợ phải trả T-1) / Nợ phải trả T-1",
        "fmt": "0.00%",
    },
    "fin_debt_growth_yoy": {
        "name": "Nợ vay tài chính (YoY) (%) (Y)",
        "group": "9. Tốc độ tăng trưởng cùng kỳ (YoY)",
        "formula": "(Nợ vay T - Nợ vay T-1) / Nợ vay T-1",
        "fmt": "0.00%",
    },
    "cfo_growth_yoy": {
        "name": "Dòng tiền thuần từ HĐKD (CFO) (YoY) (%) (Y)",
        "group": "9. Tốc độ tăng trưởng cùng kỳ (YoY)",
        "formula": "(CFO T - CFO T-1) / |CFO T-1|",
        "fmt": "0.00%",
    },
    "bank_loans_growth_yoy": {
        "name": "Dư nợ cho vay khách hàng ngân hàng (YoY) (%) (Y)",
        "group": "9. Tốc độ tăng trưởng cùng kỳ (YoY)",
        "formula": "(Cho vay T - Cho vay T-1) / Cho vay T-1",
        "fmt": "0.00%",
    },
    "bank_deposits_growth_yoy": {
        "name": "Tiền gửi khách hàng ngân hàng (YoY) (%) (Y)",
        "group": "9. Tốc độ tăng trưởng cùng kỳ (YoY)",
        "formula": "(Tiền gửi T - Tiền gửi T-1) / Tiền gửi T-1",
        "fmt": "0.00%",
    },
    "margin_loans_growth_yoy": {
        "name": "Dư nợ cho vay ký quỹ margin CTCK (YoY) (%) (Y)",
        "group": "9. Tốc độ tăng trưởng cùng kỳ (YoY)",
        "formula": "(Dư nợ margin T - Dư nợ margin T-1) / Dư nợ margin T-1",
        "fmt": "0.00%",
    },

    # -------------------------------------------------------------
    # Trụ cột 10: Biến kiểm soát kinh tế lượng & Altman Z-Score (12 chỉ số)
    # -------------------------------------------------------------
    "size_ln": {
        "name": "Quy mô doanh nghiệp Size ln(Tổng tài sản)",
        "group": "10. Biến kiểm soát kinh tế lượng & Altman Z-Score",
        "formula": "ln(Tổng tài sản)",
        "fmt": "0.000",
    },
    "size_log10": {
        "name": "Quy mô doanh nghiệp log10(Tổng tài sản)",
        "group": "10. Biến kiểm soát kinh tế lượng & Altman Z-Score",
        "formula": "log10(Tổng tài sản)",
        "fmt": "0.000",
    },
    "tangibility": {
        "name": "Tỷ lệ tài sản hữu hình (Asset Tangibility) (%) (Y)",
        "group": "10. Biến kiểm soát kinh tế lượng & Altman Z-Score",
        "formula": "Tài sản cố định hữu hình / Tổng tài sản",
        "fmt": "0.00%",
    },
    "firm_age_proxy": {
        "name": "Tỷ lệ thặng dư lợi nhuận tích lũy (Capital Accumulation) (%) (Y)",
        "group": "10. Biến kiểm soát kinh tế lượng & Altman Z-Score",
        "formula": "LNST chưa phân phối / Tổng tài sản",
        "fmt": "0.00%",
    },
    "altman_x1": {
        "name": "Hệ số Altman X1: Vốn lưu động ròng / Tổng tài sản (Y)",
        "group": "10. Biến kiểm soát kinh tế lượng & Altman Z-Score",
        "formula": "Vốn lưu động ròng / Tổng tài sản",
        "fmt": "0.000",
    },
    "altman_x2": {
        "name": "Hệ số Altman X2: Lợi nhuận giữ lại / Tổng tài sản (Y)",
        "group": "10. Biến kiểm soát kinh tế lượng & Altman Z-Score",
        "formula": "LNST chưa phân phối / Tổng tài sản",
        "fmt": "0.000",
    },
    "altman_x3": {
        "name": "Hệ số Altman X3: EBIT / Tổng tài sản (Y)",
        "group": "10. Biến kiểm soát kinh tế lượng & Altman Z-Score",
        "formula": "EBIT / Tổng tài sản",
        "fmt": "0.000",
    },
    "altman_x4": {
        "name": "Hệ số Altman X4: Vốn chủ sở hữu / Tổng nợ phải trả (Y)",
        "group": "10. Biến kiểm soát kinh tế lượng & Altman Z-Score",
        "formula": "Vốn chủ sở hữu / Tổng nợ phải trả",
        "fmt": "0.000",
    },
    "altman_x5": {
        "name": "Hệ số Altman X5: Vòng quay tài sản (Doanh thu / Tài sản) (Y)",
        "group": "10. Biến kiểm soát kinh tế lượng & Altman Z-Score",
        "formula": "Doanh thu thuần / Tổng tài sản",
        "fmt": "0.000",
    },
    "altman_z_prime": {
        "name": "Điểm nguy cơ kiệt quệ tài chính Altman Z'-Score (Thị trường mới nổi)",
        "group": "10. Biến kiểm soát kinh tế lượng & Altman Z-Score",
        "formula": "0.717*X1 + 0.847*X2 + 3.107*X3 + 0.420*X4 + 0.998*X5",
        "fmt": "0.00",
    },
    "charter_capital_to_equity": {
        "name": "Tỷ lệ vốn điều lệ trên vốn chủ sở hữu (%) (Y)",
        "group": "10. Biến kiểm soát kinh tế lượng & Altman Z-Score",
        "formula": "Vốn điều lệ / Vốn chủ sở hữu",
        "fmt": "0.00%",
    },
    "retained_earnings_to_equity": {
        "name": "Tỷ lệ LNST chưa phân phối trên vốn CSH (%) (Y)",
        "group": "10. Biến kiểm soát kinh tế lượng & Altman Z-Score",
        "formula": "LNST chưa phân phối / Vốn chủ sở hữu",
        "fmt": "0.00%",
    },
}


def compute_financial_ratios(pivot: pd.DataFrame) -> pd.DataFrame:
    """
    Tinh toan toan bo he thong 116 chi so tai chinh chuan hoc thuat tu bang pivot panel:
    1. Kha nang sinh loi & Hieu qua von (15 chi so)
    2. Cau truc von, Don bay & Kha nang thanh toan (13 chi so)
    3. Thanh khoan & Von luu dong (8 chi so)
    4. Hieu qua hoat dong & Vong quay tai san (13 chi so)
    5. Chat luong dong tien & Loi nhuan (11 chi so)
    6. Dac thu Ngan hang - CAMELS (10 chi so)
    7. Dac thu Cong ty Chung khoan (14 chi so)
    8. Dac thu Bat dong san & Xay dung (6 chi so)
    9. Toc do tang truong cung ky YoY (14 chi so)
    10. Bien kiem soat kinh te luong & Altman Z-Score (12 chi so)
    """
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
        # Coalesce
        for c in matched_cols:
            col_s = pd.to_numeric(df[c], errors="coerce")
            res = res.combine_first(col_s)
        return res

    def safe_div(a, b):
        a = pd.to_numeric(a, errors="coerce")
        b = pd.to_numeric(b, errors="coerce")
        res = a / b.replace(0, np.nan)
        res = res.replace([np.inf, -np.inf], np.nan)
        return res

    # 1. Base balance sheet items
    total_assets = coalesce_cols(["bs_tong_tai_san", "bs_tong_cong_tai_san"])
    curr_assets = coalesce_cols(["bs_tai_san_ngan_han", "bs_tong_tai_san_ngan_han"])
    non_curr_assets = coalesce_cols(["bs_tai_san_dai_han", "bs_tong_tai_san_dai_han"])
    cash = coalesce_cols(["bs_tien_va_tuong_duong_tien", "bs_tien_mat_vang_bac_da_quy", "bs_tien"])
    st_invest = coalesce_cols(["bs_gia_tri_thuan_dau_tu_ngan_han", "bs_dau_tu_ngan_han", "bs_chung_khoan_kinh_doanh", "bs_cac_tai_san_tai_chinh_ghi_nhan_thong_qua_lai_lo_fvtpl"])
    receivables = coalesce_cols(["bs_cac_khoan_phai_thu", "bs_phai_thu_khach_hang", "bs_tong_cac_khoan_phai_thu", "bs_phai_thu_cua_khach_hang"])
    ar_cust = coalesce_cols(["bs_phai_thu_khach_hang", "bs_phai_thu_cua_khach_hang"]).combine_first(receivables)
    inventory = coalesce_cols(["bs_hang_ton_kho_rong_746c904f", "bs_hang_ton_kho", "bs_hang_ton_kho_rong_fd969671", "bs_hang_ton_kho_2"])
    fixed_assets = coalesce_cols(["bs_tai_san_co_dinh", "bs_gtcl_tscd_huu_hinh", "bs_tai_san_co_dinh_huu_hinh"])
    tangible_assets = coalesce_cols(["bs_tai_san_co_dinh_huu_hinh", "bs_gtcl_tscd_huu_hinh", "bs_nguyen_gia_tscd_huu_hinh"])
    invest_prop = coalesce_cols(["bs_bat_dong_san_dau_tu"])
    re_wip = coalesce_cols(["bs_chi_phi_san_xuat_kinh_doanh_do_dang_dai_han", "bs_xay_dung_co_ban_do_dang", "bs_tai_san_do_dang_dai_han"])

    total_debt = coalesce_cols(["bs_no_phai_tra", "bs_tong_no_phai_tra"])
    curr_liab = coalesce_cols(["bs_no_ngan_han", "bs_tong_no_ngan_han"])
    long_liab = coalesce_cols(["bs_no_dai_han", "bs_tong_no_dai_han"])
    st_debt = coalesce_cols(["bs_vay_va_no_thue_tai_chinh_ngan_han", "bs_vay_ngan_han", "bs_vay_no_ngan_han", "bs_vay_tai_san_tai_chinh_ngan_han"])
    lt_debt = coalesce_cols(["bs_vay_va_no_thue_tai_san_tai_chinh_dai_han", "bs_vay_dai_han", "bs_vay_va_no_dai_han", "bs_trai_phieu_phat_hanh_dai_han"])
    fin_debt = st_debt.fillna(0) + lt_debt.fillna(0)
    fin_debt = fin_debt.where(st_debt.notna() | lt_debt.notna(), np.nan)
    payables = coalesce_cols(["bs_phai_tra_nguoi_ban_ngan_han", "bs_phai_tra_nguoi_ban"])
    prepayments = coalesce_cols(["bs_nguoi_mua_tra_tien_truoc_ngan_han", "bs_nguoi_mua_tra_tien_truoc", "bs_tra_truoc_ngan_han"])

    equity = coalesce_cols(["bs_von_chu_so_huu_4d280b22", "bs_von_chu_so_huu_6cda78ae", "bs_von_chu_so_huu", "bs_tong_von_chu_so_huu", "bs_von_va_cac_quy"])
    charter_capital = coalesce_cols(["bs_von_dieu_le", "bs_von_gop", "bs_von_dau_tu_cua_chu_so_huu"])
    retained_earnings = coalesce_cols(["bs_loi_nhuan_sau_thue_chua_phan_phoi", "bs_loi_nhuan_chua_phan_phoi", "bs_lai_chua_phan_phoi"])

    # 2. Base income statement items
    revenue = coalesce_cols([
        "is_doanh_so_thuan",
        "is_doanh_thu_thuan_ve_hoat_dong_kinh_doanh",
        "is_tong_thu_nhap_hoat_dong",
        "is_doanh_thu_hoat_dong",
        "is_doanh_thu_phi_bao_hiem_thuan",
        "is_thu_nhap_lai_thuan",
        "is_doanh_thu_thuan",
    ])
    cogs_raw = coalesce_cols(["is_gia_von_hang_ban", "is_gia_von"])
    cogs = cogs_raw.abs() if cogs_raw is not None else None
    gross_profit = coalesce_cols(["is_lai_gop", "is_loi_nhuan_gop", "is_loi_nhuan_gop_hoat_dong_kinh_doanh_bao_hiem"]).combine_first(revenue - cogs if cogs is not None else None)

    selling_exp = coalesce_cols(["is_chi_phi_ban_hang", "is_chi_phi_ban_hang_truoc_2014"]).abs()
    admin_exp = coalesce_cols(["is_chi_phi_quan_ly_doanh_nghiep", "is_chi_phi_quan_ly_doanh_nghiep_lien_quan_truc_tiep_den_hoat_dong_bao_hiem", "is_chi_phi_quan_ly_cong_ty_chung_khoan"]).abs()
    sga = selling_exp.fillna(0) + admin_exp.fillna(0)
    sga = sga.where(selling_exp.notna() | admin_exp.notna(), np.nan)

    interest_exp = coalesce_cols(["is_chi_phi_lai_vay", "is_trong_do_chi_phi_lai_vay", "is_chi_phi_lai_va_cac_khoan_chi_phi_tuong_tu", "is_chi_phi_lai_va_cac_chi_phi_tuong_tu", "cf_chi_phi_lai_vay"]).abs()
    ebt = coalesce_cols(["is_tong_loi_nhuan_ke_toan_truoc_thue", "is_tong_loi_nhuan_truoc_thue", "is_lai_lo_rong_truoc_thue", "is_loi_nhuan_truoc_thue", "is_lai_truoc_thue"])
    eat = coalesce_cols(["is_loi_nhuan_sau_thue_thu_nhap_doanh_nghiep", "is_lai_lo_thuan_sau_thue", "is_loi_nhuan_ke_toan_sau_thue", "is_loi_nhuan_sau_thue"])
    eat_parent = coalesce_cols(["is_loi_nhuan_cua_co_dong_cua_cong_ty_me", "is_loi_nhuan_sau_thue_cua_co_dong_cong_ty_me", "is_co_dong_cua_cong_ty_me", "is_loi_nhuan_sau_thue_cua_chu_so_huu_tap_doan"]).combine_first(eat)
    tax = coalesce_cols(["is_chi_phi_thue_thu_nhap_doanh_nghiep", "is_chi_phi_thue_tndn_hien_hanh", "is_chi_phi_thue_thu_nhap_hien_hanh", "is_thue_thu_nhap_doanh_nghiep_hien_thoi"]).abs()
    operating_profit = coalesce_cols(["is_ebit", "is_lai_lo_tu_hoat_dong_kinh_doanh", "is_ln_thuan_tu_hoat_dong_kinh_doanh_truoc_cf_du_phong_rui_ro_tin_dung", "is_ket_qua_hoat_dong"])
    ebit = coalesce_cols(["is_ebit"]).combine_first(ebt + interest_exp.fillna(0)).combine_first(operating_profit).combine_first(gross_profit - sga if gross_profit is not None else None)
    ebitda = coalesce_cols(["is_ebitda"]).combine_first(ebit)

    # 3. Base cash flow items
    cfo = coalesce_cols([
        "cf_luu_chuyen_tien_thuan_tu_cac_hoat_dong_san_xuat_kinh_doanh",
        "cf_luu_chuyen_thuan_tu_hoat_dong_kinh_doanh_chung_khoan",
        "cf_luu_chuyen_tien_thuan_tu_hoat_dong_kinh_doanh",
        "cf_luu_chuyen_tien_thuan_tu_hoat_dong_kinh_doanh_truoc_thue_thu_nhap_dn",
    ])
    cfi = coalesce_cols(["cf_luu_chuyen_tien_te_rong_tu_hoat_dong_dau_tu", "cf_luu_chuyen_tien_thuan_tu_hoat_dong_dau_tu", "cf_luu_chuyen_tu_hoat_dong_dau_tu"])
    cff = coalesce_cols(["cf_luu_chuyen_tien_te_tu_hoat_dong_tai_chinh", "cf_luu_chuyen_tien_tu_hoat_dong_tai_chinh", "cf_luu_chuyen_thuan_tu_hoat_dong_tai_chinh", "cf_luu_chuyen_tien_thuan_tu_hoat_dong_tai_chinh"])
    capex = coalesce_cols(["cf_tien_chi_de_mua_sam_xay_dung_tscd_va_cac_tai_san_dai_han_khac", "cf_tien_chi_mua_sam_xay_dung_tscd_va_cac_tai_san_dai_han_khac", "cf_tien_mua_tai_san_co_dinh_va_cac_tai_san_dai_han_khac"]).abs()
    fcf = cfo - capex.fillna(0)

    # 4. Bank specific base items
    bank_loans = coalesce_cols(["bs_cho_vay_khach_hang", "bs_cho_vay_khach_hang_2"])
    bank_deposits = coalesce_cols(["bs_tien_gui_cua_khach_hang", "bs_tien_gui_cua_khach_hang_va_cac_to_chuc_tin_dung_khac"])
    bank_nii = coalesce_cols(["is_thu_nhap_lai_thuan"])
    bank_toi = coalesce_cols(["is_tong_thu_nhap_hoat_dong"])
    bank_provisions = coalesce_cols(["bs_du_phong_rui_ro_cho_vay_khach_hang", "bs_du_phong_rui_ro_tin_dung"]).abs()
    bank_credit_cost = coalesce_cols(["is_chi_phi_du_phong_rui_ro_tin_dung"]).abs()
    bank_opex = coalesce_cols(["is_chi_phi_hoat_dong", "is_chi_phi_quan_ly_doanh_nghiep"]).abs()

    # 5. Securities specific base items
    sec_margin = coalesce_cols(["bs_cho_vay_va_ung_truoc_cho_khach_hang", "bs_cho_vay_va_ung_truoc_cho_vay", "bs_cac_khoan_cho_vay"])
    sec_advances = coalesce_cols(["bs_phai_thu_ung_truoc_tien_ban_chung_khoan_cua_khach_hang", "bs_ung_truoc_tien_ban"])
    sec_fvtpl = coalesce_cols(["bs_cac_tai_san_tai_chinh_ghi_nhan_thong_qua_lai_lo_fvtpl"])
    sec_afs = coalesce_cols(["bs_cac_khoan_tai_chinh_san_sang_de_ban_afs"])
    sec_htm = coalesce_cols(["bs_cac_khoan_dau_tu_nam_giu_den_ngay_dao_han_htm"])
    sec_broker_rev = coalesce_cols(["is_doanh_thu_hoat_dong_moi_gioi_chung_khoan"])
    sec_broker_cost = coalesce_cols(["is_chi_phi_moi_gioi_chung_khoan"]).abs()
    sec_prop_rev = coalesce_cols(["is_lai_tu_cac_tai_san_tai_chinh_ghi_nhan_thong_qua_lai_lo_fvtpl"])
    sec_margin_profit = coalesce_cols(["is_lai_tu_cac_khoan_cho_vay_va_phai_thu"])
    sec_ib_rev = coalesce_cols(["is_doanh_thu_hoat_dong_tu_van_tai_chinh", "is_doanh_thu_bao_lanh_phat_hanh_chung_khoan"])
    sec_oper_cost = coalesce_cols(["is_chi_phi_hoat_dong_kinh_doanh", "is_chi_phi_hoat_dong"]).abs()

    # Build calculation dictionary to avoid DataFrame fragmentation
    new_metrics = {}

    # Pillar 1: Sinh loi
    new_metrics["roa"] = safe_div(eat, total_assets)
    new_metrics["roe"] = safe_div(eat, equity)
    new_metrics["roce"] = safe_div(ebit, total_assets - curr_liab)
    new_metrics["roic"] = safe_div(ebit * (1 - safe_div(tax, ebt).fillna(0.2)), equity + fin_debt.fillna(0) - cash.fillna(0))
    new_metrics["gross_margin"] = safe_div(gross_profit, revenue)
    new_metrics["operating_margin"] = safe_div(ebit, revenue)
    new_metrics["ebitda_margin"] = safe_div(ebitda, revenue)
    new_metrics["net_margin"] = safe_div(eat, revenue)
    new_metrics["ebt_margin"] = safe_div(ebt, revenue)
    new_metrics["effective_tax_rate"] = safe_div(tax, ebt)
    new_metrics["dupont_tax_burden"] = safe_div(eat, ebt)
    new_metrics["dupont_interest_burden"] = safe_div(ebt, ebit)
    new_metrics["dupont_operating_margin"] = safe_div(ebit, revenue)
    new_metrics["dupont_asset_turnover"] = safe_div(revenue, total_assets)
    new_metrics["dupont_equity_multiplier"] = safe_div(total_assets, equity)

    # Pillar 2: Cau truc von & Don bay
    new_metrics["debt_to_assets"] = safe_div(total_debt, total_assets)
    new_metrics["debt_to_equity"] = safe_div(total_debt, equity)
    new_metrics["fin_debt_to_assets"] = safe_div(fin_debt, total_assets)
    new_metrics["fin_debt_to_equity"] = safe_div(fin_debt, equity)
    new_metrics["equity_to_assets"] = safe_div(equity, total_assets)
    new_metrics["equity_multiplier"] = safe_div(total_assets, equity)
    new_metrics["st_debt_to_total_debt"] = safe_div(st_debt, fin_debt)
    new_metrics["lt_debt_to_total_debt"] = safe_div(lt_debt, fin_debt)
    new_metrics["interest_coverage"] = safe_div(ebit, interest_exp)
    new_metrics["debt_to_ebitda"] = safe_div(fin_debt, ebitda)
    new_metrics["cfo_to_debt"] = safe_div(cfo, fin_debt)
    new_metrics["cfo_to_liabilities"] = safe_div(cfo, total_debt)
    new_metrics["fin_leverage_ratio"] = safe_div(total_assets, equity)

    # Pillar 3: Thanh khoan & Von luu dong
    new_metrics["current_ratio"] = safe_div(curr_assets, curr_liab)
    new_metrics["quick_ratio"] = safe_div(curr_assets - inventory.fillna(0), curr_liab)
    new_metrics["cash_ratio"] = safe_div(cash.fillna(0) + st_invest.fillna(0), curr_liab)
    new_metrics["cash_to_assets"] = safe_div(cash, total_assets)
    nwc = curr_assets - curr_liab
    new_metrics["working_capital"] = nwc
    new_metrics["nwc_to_assets"] = safe_div(nwc, total_assets)
    new_metrics["nwc_to_revenue"] = safe_div(nwc, revenue)
    new_metrics["defensive_interval"] = safe_div((cash.fillna(0) + ar_cust.fillna(0)) * 365, sga.fillna(cogs.fillna(0)))

    # Pillar 4: Hieu qua hoat dong
    new_metrics["asset_turnover"] = safe_div(revenue, total_assets)
    new_metrics["fixed_asset_turnover"] = safe_div(revenue, fixed_assets)
    new_metrics["inventory_turnover"] = safe_div(cogs, inventory)
    dio = safe_div(inventory * 365, cogs)
    new_metrics["dio"] = dio
    new_metrics["ar_turnover"] = safe_div(revenue, ar_cust)
    dso = safe_div(ar_cust * 365, revenue)
    new_metrics["dso"] = dso
    new_metrics["ap_turnover"] = safe_div(cogs, payables)
    dpo = safe_div(payables * 365, cogs)
    new_metrics["dpo"] = dpo
    new_metrics["ccc"] = dio + dso - dpo
    new_metrics["working_capital_turnover"] = safe_div(revenue, nwc)
    new_metrics["sga_to_revenue"] = safe_div(sga, revenue)
    new_metrics["selling_cost_ratio"] = safe_div(selling_exp, revenue)
    new_metrics["admin_cost_ratio"] = safe_div(admin_exp, revenue)

    # Pillar 5: Chat luong dong tien
    new_metrics["cfo_to_net_income"] = safe_div(cfo, eat)
    new_metrics["cfo_to_revenue"] = safe_div(cfo, revenue)
    new_metrics["cfo_to_assets"] = safe_div(cfo, total_assets)
    new_metrics["cfo_to_equity"] = safe_div(cfo, equity)
    new_metrics["fcf"] = fcf
    new_metrics["fcf_to_net_income"] = safe_div(fcf, eat)
    new_metrics["fcf_to_revenue"] = safe_div(fcf, revenue)
    new_metrics["capex_to_revenue"] = safe_div(capex, revenue)
    new_metrics["capex_to_assets"] = safe_div(capex, total_assets)
    new_metrics["cfo_to_capex"] = safe_div(cfo, capex)
    new_metrics["accruals_to_assets"] = safe_div(eat - cfo, total_assets)

    # Pillar 6: Ngan hang (CAMELS)
    new_metrics["bank_nim"] = safe_div(bank_nii, total_assets)
    new_metrics["bank_cir"] = safe_div(bank_opex, bank_toi)
    new_metrics["bank_ldr"] = safe_div(bank_loans, bank_deposits)
    new_metrics["bank_provision_coverage"] = safe_div(bank_provisions, bank_loans)
    new_metrics["bank_credit_cost"] = safe_div(bank_credit_cost, bank_loans)
    new_metrics["bank_loans_to_assets"] = safe_div(bank_loans, total_assets)
    new_metrics["bank_deposits_to_assets"] = safe_div(bank_deposits, total_assets)
    new_metrics["bank_equity_to_assets"] = safe_div(equity, total_assets)
    new_metrics["bank_nii_to_toi"] = safe_div(bank_nii, bank_toi)
    new_metrics["bank_non_interest_income_ratio"] = safe_div(bank_toi - bank_nii, bank_toi)

    # Pillar 7: Chung khoan
    new_metrics["margin_to_equity"] = safe_div(sec_margin, equity)
    new_metrics["pct_margin_loans"] = safe_div(sec_margin, total_assets)
    new_metrics["pct_advances"] = safe_div(sec_advances, total_assets)
    new_metrics["pct_fvtpl"] = safe_div(sec_fvtpl, total_assets)
    new_metrics["pct_afs"] = safe_div(sec_afs, total_assets)
    new_metrics["pct_htm"] = safe_div(sec_htm, total_assets)
    new_metrics["pct_cash"] = safe_div(cash, total_assets)
    new_metrics["pct_brokerage_rev"] = safe_div(sec_broker_rev, revenue)
    new_metrics["pct_proprietary_rev"] = safe_div(sec_prop_rev, revenue)
    new_metrics["pct_margin_profit"] = safe_div(sec_margin_profit, revenue)
    new_metrics["pct_ib_rev"] = safe_div(sec_ib_rev, revenue)
    new_metrics["pct_brokerage_cost"] = safe_div(sec_broker_cost, sec_oper_cost)
    new_metrics["pct_proprietary_cost"] = safe_div(coalesce_cols(["is_chi_phi_hoat_dong_tu_doanh"]).abs(), sec_oper_cost)
    new_metrics["pct_provision_cost"] = safe_div(coalesce_cols(["is_chi_phi_du_phong_tstc", "is_chi_phi_du_phong"]).abs(), sec_oper_cost)

    # Pillar 8: Bat dong san & Xay dung
    new_metrics["re_prepayments_to_inventory"] = safe_div(prepayments, inventory)
    new_metrics["re_prepayments_to_assets"] = safe_div(prepayments, total_assets)
    new_metrics["re_inventory_to_assets"] = safe_div(inventory, total_assets)
    new_metrics["re_wip_to_assets"] = safe_div(re_wip, total_assets)
    new_metrics["re_debt_to_inventory"] = safe_div(fin_debt, inventory)
    new_metrics["re_invest_prop_to_assets"] = safe_div(invest_prop, total_assets)

    # Pillar 9: YoY Growth Dynamics
    yoy_specs = [
        ("rev_growth_yoy", revenue),
        ("gross_profit_growth_yoy", gross_profit),
        ("ebit_growth_yoy", ebit),
        ("ebt_growth_yoy", ebt),
        ("eat_growth_yoy", eat),
        ("eat_parent_growth_yoy", eat_parent),
        ("assets_growth_yoy", total_assets),
        ("equity_growth_yoy", equity),
        ("debt_growth_yoy", total_debt),
        ("fin_debt_growth_yoy", fin_debt),
        ("cfo_growth_yoy", cfo),
        ("bank_loans_growth_yoy", bank_loans),
        ("bank_deposits_growth_yoy", bank_deposits),
        ("margin_loans_growth_yoy", sec_margin),
    ]
    for yoy_col, src in yoy_specs:
        s_prev = df.groupby("ticker")["ticker"].apply(lambda g: pd.Series(src.iloc[g.index]).shift(1)).reset_index(level=0, drop=True)
        denom = s_prev.abs().replace(0, np.nan)
        new_metrics[yoy_col] = (src - s_prev) / denom

    # Pillar 10: Econometrics & Altman Z-Score
    new_metrics["size_ln"] = np.log(total_assets.where(total_assets > 0, np.nan))
    new_metrics["size_log10"] = np.log10(total_assets.where(total_assets > 0, np.nan))
    new_metrics["tangibility"] = safe_div(tangible_assets, total_assets)
    new_metrics["firm_age_proxy"] = safe_div(retained_earnings, total_assets)
    x1 = safe_div(nwc, total_assets)
    x2 = safe_div(retained_earnings, total_assets)
    x3 = safe_div(ebit, total_assets)
    x4 = safe_div(equity, total_debt)
    x5 = safe_div(revenue, total_assets)
    new_metrics["altman_x1"] = x1
    new_metrics["altman_x2"] = x2
    new_metrics["altman_x3"] = x3
    new_metrics["altman_x4"] = x4
    new_metrics["altman_x5"] = x5
    new_metrics["altman_z_prime"] = 0.717 * x1 + 0.847 * x2 + 3.107 * x3 + 0.420 * x4 + 0.998 * x5
    new_metrics["charter_capital_to_equity"] = safe_div(charter_capital, equity)
    new_metrics["retained_earnings_to_equity"] = safe_div(retained_earnings, equity)

    # Concat all new metrics at once to prevent fragmentation
    df_metrics = pd.DataFrame(new_metrics, index=df.index)
    
    # Also attach base items if not already present
    base_items = {
        "total_assets": total_assets,
        "total_debt": total_debt,
        "equity": equity,
        "curr_assets": curr_assets,
        "non_curr_assets": non_curr_assets,
        "curr_debt": curr_liab,
        "long_term_debt": long_liab,
        "net_revenue": revenue,
        "profit_before_tax": ebt,
        "profit_after_tax": eat,
        "eat_parent": eat_parent,
        "operating_cash_flow": cfo,
        "investing_cash_flow": cfi,
        "financing_cash_flow": cff,
    }
    for k, v in base_items.items():
        if k not in df.columns:
            df_metrics[k] = v

    overlap = [c for c in df_metrics.columns if c in df.columns]
    if overlap:
        df = df.drop(columns=overlap)

    return pd.concat([df, df_metrics], axis=1)




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
        ("Số tỷ số tài chính:", f"{len(FINANCIAL_RATIOS)} chỉ số (Chuẩn học thuật: CFA, IFRS/VAS, Basel III, CAMELS)"),
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
        ("→ Ty_So_Tai_Chinh", "116 chỉ số tài chính — Chọn mã CK ở ô B2, dữ liệu tự động cập nhật"),
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
        "Hệ thống chỉ số tài chính phân tích & nghiên cứu chuyên sâu",
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
            meta = FINANCIAL_RATIOS.get(rcode, {"name": rcode, "group": "Chỉ số tài chính", "formula": "", "fmt": "0.00%"})
            ws.cell(row=row, column=1, value=f"{t}_{rcode}")
            ws.cell(row=row, column=2, value=t)
            ws.cell(row=row, column=3, value=rcode)
            ws.cell(row=row, column=4, value=meta["group"])
            ws.cell(row=row, column=5, value=meta["name"])
            ws.cell(row=row, column=6, value=meta["formula"])
            for y_idx, y in enumerate(years):
                row_match = df_t[df_t["year"] == y]
                val = None
                if len(row_match) > 0 and rcode in row_match.columns:
                    col_data = row_match[rcode]
                    if isinstance(col_data, pd.DataFrame):
                        col_data = col_data.iloc[:, 0]
                    val = col_data.values[0] if len(col_data) > 0 else None
                if val is not None and pd.notna(val):
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
    ws.cell(row=1, column=1, value="HỆ THỐNG CHỈ SỐ TÀI CHÍNH DOANH NGHIỆP").font = _TITLE_FONT

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
        meta = FINANCIAL_RATIOS.get(rcode, {"name": rcode, "group": "Chỉ số tài chính", "formula": "", "fmt": "0.00%"})
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
            "Ty_So_Tai_Chinh: Hệ thống chỉ số tài chính phân tích & nghiên cứu chuyên sâu (10 trụ cột học thuật).",
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
    # Compute academic financial ratios
    pivot = compute_financial_ratios(pivot)

    tickers = sorted([str(t) for t in pivot["ticker"].dropna().unique().tolist()])
    years = sorted([int(y) for y in pivot["year"].dropna().unique().tolist()])

    # Master item list
    df_master = _get_master_items(all_data, fin_codebook)

    # Data lookup
    data_lookup = _build_data_lookup(all_data)

    # Active ratios (Strictly respect caller's ratio_cols)
    if ratio_cols is not None:
        active_ratios = [r for r in ratio_cols.keys() if r in FINANCIAL_RATIOS]
    elif fin_codebook:
        selected_ratios = [item.get("Biến") for item in fin_codebook if item.get("Phân loại") == "Chỉ số tài chính phân tích"]
        active_ratios = [r for r in FINANCIAL_RATIOS if r in selected_ratios]
    else:
        active_ratios = [r for r in FINANCIAL_RATIOS.keys() if r in pivot.columns]

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
