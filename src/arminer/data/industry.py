# -*- coding: utf-8 -*-
"""
arminer.data.industry
======================
Hệ thống phân loại ngành chuẩn ICB (Industry Classification Benchmark)
cho các doanh nghiệp niêm yết trên thị trường chứng khoán Việt Nam (HOSE, HNX, UPCoM).

Bao gồm:
- ICB Level 1 (10 ngành cấp 1 tiêu chuẩn)
- ICB Level 2 (25+ ngành cấp 2 chuyên sâu)
- Ticker Mapping toàn diện các cổ phiếu phổ biến và phân tích từ danh sách HNX
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import pandas as pd
from loguru import logger


# 10 Ngành Cấp 1 Tiêu Chuẩn ICB
ICB_LEVEL1 = [
    {"code": "8000", "name_vi": "Tài chính", "name_en": "Financials"},
    {"code": "8600", "name_vi": "Bất động sản", "name_en": "Real Estate"},
    {"code": "9000", "name_vi": "Công nghệ Thông tin", "name_en": "Technology"},
    {"code": "3000", "name_vi": "Hàng tiêu dùng", "name_en": "Consumer Goods"},
    {"code": "2000", "name_vi": "Công nghiệp", "name_en": "Industrials"},
    {"code": "1000", "name_vi": "Nguyên vật liệu", "name_en": "Basic Materials"},
    {"code": "0001", "name_vi": "Dầu khí & Năng lượng", "name_en": "Energy"},
    {"code": "7000", "name_vi": "Tiện ích cộng đồng", "name_en": "Utilities"},
    {"code": "4000", "name_vi": "Y tế & Chăm sóc sức khỏe", "name_en": "Health Care"},
    {"code": "5000", "name_vi": "Dịch vụ tiêu dùng & Bán lẻ", "name_en": "Consumer Services"},
]

# Các Ngành Cấp 2 Chuyên Sâu
ICB_LEVEL2 = {
    "Tài chính": [
        "Ngân hàng",
        "Dịch vụ Tài chính / Chứng khoán",
        "Bảo hiểm",
    ],
    "Bất động sản": [
        "Bất động sản dân dụng",
        "Bất động sản khu công nghiệp",
    ],
    "Công nghệ Thông tin": [
        "Phần mềm & Dịch vụ CNTT",
        "Phần cứng & Thiết bị",
    ],
    "Hàng tiêu dùng": [
        "Thực phẩm & Đồ uống",
        "Hàng cá nhân & May mặc",
        "Ô tô & Phụ tùng",
    ],
    "Công nghiệp": [
        "Xây dựng & Vật liệu",
        "Vận tải & Logistics",
        "Hàng không",
        "Cơ khí & Chế tạo",
    ],
    "Nguyên vật liệu": [
        "Thép & Kim loại",
        "Hóa chất & Phân bón",
        "Khai khoáng & Than đá",
    ],
    "Dầu khí & Năng lượng": [
        "Thăm dò & Khai thác Dầu khí",
        "Lọc hóa dầu & Phân phối",
    ],
    "Tiện ích cộng đồng": [
        "Sản xuất & Phân phối Điện",
        "Nước & Xử lý chất thải",
    ],
    "Y tế & Chăm sóc sức khỏe": [
        "Dược phẩm",
        "Thiết bị y tế & Bệnh viện",
    ],
    "Dịch vụ tiêu dùng & Bán lẻ": [
        "Bán lẻ tổng hợp",
        "Du lịch & Giải trí",
        "Truyền thông & Xuất bản",
    ],
}


class IndustryClassifier:
    """Bộ phân loại ngành ICB L1 và L2 cho cổ phiếu Việt Nam."""

    def __init__(self, workspace_root: Optional[Path] = None):
        if workspace_root is None:
            workspace_root = Path(__file__).resolve().parent.parent.parent.parent
        self.workspace_root = workspace_root
        self._ticker_map: Dict[str, Tuple[str, str]] = {}
        self._initialized = False

    def initialize(self):
        """Khởi tạo danh bạ phân ngành."""
        if self._initialized:
            return

        self._populate_core_mappings()
        self._parse_hnx_companies()
        self._initialized = True
        logger.info(f"IndustryClassifier: Indexed {len(self._ticker_map)} ticker-industry mappings")

    def _add_batch(self, tickers: List[str], l1: str, l2: str):
        for t in tickers:
            self._ticker_map[t.upper().strip()] = (l1, l2)

    def _populate_core_mappings(self):
        """Ánh xạ các mã lớn tiêu biểu trên HOSE, HNX và UPCoM."""
        # 1. Ngân hàng
        banks = [
            "VCB", "BID", "CTG", "TCB", "MBB", "VPB", "ACB", "STB", "HDB", "VIB",
            "SHB", "LPB", "MSB", "TPB", "OCB", "SSB", "EIB", "BAB", "ABB", "BVB",
            "KLB", "NVB", "PGB", "SGB", "VAB", "VBB"
        ]
        self._add_batch(banks, "Tài chính", "Ngân hàng")

        # 2. Dịch vụ Tài chính / Chứng khoán
        securities = [
            "SSI", "VND", "VCI", "HCM", "SHS", "MBS", "FTS", "CTS", "BSI", "AGR",
            "VDS", "ORS", "TVS", "EVS", "APS", "AAS", "ABW", "ART", "WSS", "VIG",
            "BVS", "PSI", "APG", "HBS", "IVS", "PHS", "SBS"
        ]
        self._add_batch(securities, "Tài chính", "Dịch vụ Tài chính / Chứng khoán")

        # 3. Bảo hiểm
        insurance = ["BVH", "PVI", "BMI", "MIG", "BIC", "PRE", "ABI", "BLI", "VNR"]
        self._add_batch(insurance, "Tài chính", "Bảo hiểm")

        # 4. Bất động sản dân dụng
        re_res = [
            "VHM", "NVL", "KDH", "DIG", "PDR", "DXG", "NLG", "CEO", "SCR", "HDC",
            "AGG", "NRC", "QCG", "VPH", "NTL", "HQC", "ITA", "AAV", "API", "DXS",
            "KHG", "CRE", "TCH", "HHS", "LDG", "IDJ", "D2D"
        ]
        self._add_batch(re_res, "Bất động sản", "Bất động sản dân dụng")

        # 5. Bất động sản KCN
        re_ind = ["BCM", "KBC", "IDC", "VGC", "SZC", "LHG", "NTC", "TIP", "MH3", "ITA", "SIP"]
        self._add_batch(re_ind, "Bất động sản", "Bất động sản khu công nghiệp")

        # 6. Công nghệ thông tin
        tech = ["FPT", "CMG", "ELC", "ICT", "ITD", "SGT", "SAM", "FOX", "CTR", "VGI"]
        self._add_batch(tech, "Công nghệ Thông tin", "Phần mềm & Dịch vụ CNTT")

        # 7. Thép & Kim loại
        steel = ["HPG", "HSG", "NKG", "TLH", "POM", "VGS", "TVN", "SMC", "TIS"]
        self._add_batch(steel, "Nguyên vật liệu", "Thép & Kim loại")

        # 8. Hóa chất & Phân bón
        chemicals = ["DGC", "DPM", "DCM", "BFC", "CSV", "LAS", "PHR", "DPR", "DRI", "GVR", "PAC"]
        self._add_batch(chemicals, "Nguyên vật liệu", "Hóa chất & Phân bón")

        # 9. Thực phẩm & Đồ uống
        food = [
            "VNM", "MSN", "SAB", "KDC", "VHC", "ANV", "FMC", "QNS", "SBT", "MCH",
            "BHN", "DBC", "BAF", "HAG", "HNG", "PAN", "MML", "IDI", "ACL", "CMX"
        ]
        self._add_batch(food, "Hàng tiêu dùng", "Thực phẩm & Đồ uống")

        # 10. Dệt may & Hàng cá nhân
        apparel = ["PNJ", "TCM", "MSH", "TNG", "GIL", "STK", "VGT", "ADS", "A32", "EVE"]
        self._add_batch(apparel, "Hàng tiêu dùng", "Hàng cá nhân & May mặc")

        # 11. Bán lẻ
        retail = ["MWG", "FRT", "DGW", "PET", "HAX", "SVC", "CTC"]
        self._add_batch(retail, "Dịch vụ tiêu dùng & Bán lẻ", "Bán lẻ tổng hợp")

        # 12. Dược phẩm & Y tế
        pharma = ["DHG", "IMP", "TRA", "DVN", "DBD", "DMC", "OPC", "DCL", "AMV", "JVC", "TNH"]
        self._add_batch(pharma, "Y tế & Chăm sóc sức khỏe", "Dược phẩm")

        # 13. Vận tải & Logistics
        logistics = [
            "GMD", "HAH", "VSC", "PVT", "VOS", "VTO", "VIP", "TMS", "VTP", "MVN",
            "SGP", "PHP", "DVP", "TCL", "VJC", "HVN", "ACV", "AST", "NCT", "SAS"
        ]
        self._add_batch(logistics, "Công nghiệp", "Vận tải & Logistics")

        # 14. Xây dựng & Vật liệu
        construction = [
            "VCG", "CTD", "HBC", "CII", "FCN", "PC1", "LCG", "HHV", "C4G", "HT1",
            "BCC", "VCS", "ACE", "AME", "VE3", "VC9"
        ]
        self._add_batch(construction, "Công nghiệp", "Xây dựng & Vật liệu")

        # 15. Dầu khí
        oil_gas = ["GAS", "PLX", "PVD", "PVS", "PVC", "PVB", "PSH", "OIL", "BSR"]
        self._add_batch(oil_gas, "Dầu khí & Năng lượng", "Thăm dò & Khai thác Dầu khí")

        # 16. Tiện ích Điện, Nước
        utilities = [
            "POW", "PGV", "GEG", "NT2", "PPC", "HND", "VSH", "SBA", "TTA", "SJD",
            "BWE", "TDM", "TDW", "DNW"
        ]
        self._add_batch(utilities, "Tiện ích cộng đồng", "Sản xuất & Phân phối Điện")

    def _parse_hnx_companies(self):
        """Phân tích các mã HNX từ file fixture đi kèm package."""
        fixture_path = Path(__file__).resolve().parent / "fixtures" / "hnx_companies.csv"
        csv_path = fixture_path if fixture_path.exists() else None

        if not csv_path:
            local_path = self.workspace_root / "data" / "hnx_companies.csv"
            if local_path.exists():
                csv_path = local_path

        if not csv_path:
            return


        try:
            df = pd.read_csv(csv_path)
            for _, row in df.iterrows():
                ticker = str(row["ticker"]).upper().strip()
                if ticker in self._ticker_map:
                    continue  # Đã có ánh xạ chi tiết

                text = str(row["company_name_and_sector"]).lower()

                # Rule-based inference
                if any(w in text for w in ["ngân hàng", "tài chính"]):
                    self._ticker_map[ticker] = ("Tài chính", "Ngân hàng")
                elif any(w in text for w in ["chứng khoán"]):
                    self._ticker_map[ticker] = ("Tài chính", "Dịch vụ Tài chính / Chứng khoán")
                elif any(w in text for w in ["bảo hiểm"]):
                    self._ticker_map[ticker] = ("Tài chính", "Bảo hiểm")
                elif any(w in text for w in ["bất động sản", "địa ốc"]):
                    self._ticker_map[ticker] = ("Bất động sản", "Bất động sản dân dụng")
                elif any(w in text for w in ["phần mềm", "công nghệ", "viễn thông", "tin học"]):
                    self._ticker_map[ticker] = ("Công nghệ Thông tin", "Phần mềm & Dịch vụ CNTT")
                elif any(w in text for w in ["thép", "kim loại"]):
                    self._ticker_map[ticker] = ("Nguyên vật liệu", "Thép & Kim loại")
                elif any(w in text for w in ["hóa chất", "phân bón", "nhựa", "cao su"]):
                    self._ticker_map[ticker] = ("Nguyên vật liệu", "Hóa chất & Phân bón")
                elif any(w in text for w in ["khoáng sản", "than"]):
                    self._ticker_map[ticker] = ("Nguyên vật liệu", "Khai khoáng & Than đá")
                elif any(w in text for w in ["thực phẩm", "đồ uống", "bánh kẹo", "thủy sản", "chăn nuôi", "nông nghiệp"]):
                    self._ticker_map[ticker] = ("Hàng tiêu dùng", "Thực phẩm & Đồ uống")
                elif any(w in text for w in ["dệt may", "may", "da giày", "may mặc"]):
                    self._ticker_map[ticker] = ("Hàng tiêu dùng", "Hàng cá nhân & May mặc")
                elif any(w in text for w in ["dược", "y tế", "bệnh viện"]):
                    self._ticker_map[ticker] = ("Y tế & Chăm sóc sức khỏe", "Dược phẩm")
                elif any(w in text for w in ["xây dựng", "xây lắp", "bê tông", "vật liệu"]):
                    self._ticker_map[ticker] = ("Công nghiệp", "Xây dựng & Vật liệu")
                elif any(w in text for w in ["vận tải", "kho bãi", "cảng", "logistics"]):
                    self._ticker_map[ticker] = ("Công nghiệp", "Vận tải & Logistics")
                elif any(w in text for w in ["điện", "năng lượng", "thủy điện", "nhiệt điện"]):
                    self._ticker_map[ticker] = ("Tiện ích cộng đồng", "Sản xuất & Phân phối Điện")
                elif any(w in text for w in ["nước", "môi trường"]):
                    self._ticker_map[ticker] = ("Tiện ích cộng đồng", "Nước & Xử lý chất thải")
                elif any(w in text for w in ["dầu khí", "xăng dầu"]):
                    self._ticker_map[ticker] = ("Dầu khí & Năng lượng", "Thăm dò & Khai thác Dầu khí")
                elif any(w in text for w in ["bán lẻ", "thương mại"]):
                    self._ticker_map[ticker] = ("Dịch vụ tiêu dùng & Bán lẻ", "Bán lẻ tổng hợp")
                elif any(w in text for w in ["truyền thông", "in ấn", "xuất bản"]):
                    self._ticker_map[ticker] = ("Dịch vụ tiêu dùng & Bán lẻ", "Truyền thông & Xuất bản")
                else:
                    self._ticker_map[ticker] = ("Công nghiệp", "Cơ khí & Chế tạo")
        except Exception as e:
            logger.warning(f"Could not parse HNX companies: {e}")

    def get_industry(self, ticker: str) -> Tuple[str, str]:
        """Lấy (ICB L1, ICB L2) cho một mã cổ phiếu."""
        self.initialize()
        t = ticker.upper().strip()
        if t in self._ticker_map:
            return self._ticker_map[t]
        return ("Khác / Chưa phân loại", "Chưa phân loại")

    def get_taxonomy_tree(self) -> Dict[str, Any]:
        """Trả về cấu trúc cây L1 -> L2 kèm danh sách mã cổ phiếu."""
        self.initialize()
        tree: Dict[str, Dict[str, List[str]]] = {}

        # Initialize structure
        for l1, l2_list in ICB_LEVEL2.items():
            tree[l1] = {l2: [] for l2 in l2_list}

        # Populate with tickers
        for ticker, (l1, l2) in self._ticker_map.items():
            if l1 not in tree:
                tree[l1] = {}
            if l2 not in tree[l1]:
                tree[l1][l2] = []
            tree[l1][l2].append(ticker)

        # Sort tickers
        result = []
        for l1, sub in tree.items():
            total_tickers = sum(len(tickers) for tickers in sub.values())
            sub_list = []
            for l2, tickers in sub.items():
                sub_list.append({
                    "name": l2,
                    "ticker_count": len(tickers),
                    "tickers": sorted(tickers),
                })
            result.append({
                "name": l1,
                "total_tickers": total_tickers,
                "subsectors": sub_list,
            })

        return {"sectors": result}
