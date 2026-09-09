# -*- coding: utf-8 -*-
"""
arminer.data.financial
=======================
Wrapper cho vnfinancialdata — tự động tính các biến tài chính phổ biến.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional
import warnings

import pandas as pd
from loguru import logger

# Suppress harmless Hugging Face Hub unauthenticated warning for public datasets
warnings.filterwarnings("ignore", message=".*unauthenticated requests to the HF Hub.*")



class FinancialDataProvider:
    """
    Tích hợp vnfinancialdata → panel data tài chính.

    Tự động tính: ROA, ROE, Size (ln Total Assets),
    Leverage (Total Debt / Total Assets).
    """

    # Mapping item_name phổ biến (Đa ngành: Sản xuất/Thương mại, Ngân hàng, Chứng khoán, Bảo hiểm)
    ITEM_MAPPING = {
        "total_assets": ["TỔNG TÀI SẢN", "TỔNG CỘNG TÀI SẢN", "Tổng tài sản"],
        "total_equity": ["VỐN CHỦ SỞ HỮU", "Vốn chủ sở hữu", "TỔNG VỐN CHỦ SỞ HỮU", "Vốn và các quỹ"],
        "total_debt": ["NỢ PHẢI TRẢ", "Tổng nợ phải trả", "Nợ phải trả"],
        "revenue": ["Doanh số thuần", "Doanh thu thuần", "Tổng thu nhập hoạt động", "Doanh thu hoạt động", "Thu nhập lãi thuần"],
        "net_income": [
            "Lãi/(lỗ) thuần sau thuế",
            "Lợi nhuận sau thuế",
            "Lợi nhuận kế toán sau thuế",
            "Lợi nhuận sau thuế thu nhập doanh nghiệp",
            "Tổng lợi nhuận kế toán sau thuế",
            "Lợi nhuận sau thuế của cổ đông công ty mẹ",
        ],
        "cash": ["Tiền và tương đương tiền", "Tiền mặt, vàng bạc, đá quý", "Tiền"],
        "ebit": ["EBIT", "Lợi nhuận trước thuế và lãi vay"],
        "ebitda": ["EBITDA"],
    }

    RATIO_FORMULAS = {
        "roa": lambda d: d.get("net_income", 0) / d["total_assets"]
            if d.get("total_assets") else None,
        "roe": lambda d: d.get("net_income", 0) / d["total_equity"]
            if d.get("total_equity") else None,
        "size": lambda d: math.log(d["total_assets"])
            if d.get("total_assets") and d["total_assets"] > 0 else None,
        "leverage": lambda d: d.get("total_debt", 0) / d["total_assets"]
            if d.get("total_assets") else None,
        "current_ratio": lambda d: (
            d.get("total_assets", 0) / d.get("total_debt", 1)
        ) if d.get("total_debt") else None,
    }

    def __init__(self):
        self._vnf = None
        self._cache: Dict[str, pd.DataFrame] = {}

    def _get_vnf(self):
        """Lazy import vnfinancialdata."""
        if self._vnf is None:
            try:
                import vnfinancialdata as vnf
                self._vnf = vnf
                logger.info("vnfinancialdata loaded successfully")
            except ImportError:
                raise ImportError(
                    "vnfinancialdata is not installed. "
                    "Run: pip install vnfinancialdata"
                )
        return self._vnf

    def load_raw(self, exchange: str, statement: str) -> pd.DataFrame:
        """Load raw data từ vnfinancialdata (với cache)."""
        cache_key = f"{exchange}_{statement}"
        if cache_key not in self._cache:
            vnf = self._get_vnf()
            self._cache[cache_key] = vnf.load(
                exchange=exchange, statement=statement
            )
            logger.info(
                f"Loaded {exchange}/{statement}: "
                f"{len(self._cache[cache_key])} rows"
            )
        return self._cache[cache_key]

    def get_item_value(self, ticker: str, year: int,
                       item_name: Any, statement: str = "balance_sheet",
                       exchange: str = None) -> Optional[float]:
        """Lấy 1 giá trị cụ thể cho (ticker, year, item) với hỗ trợ danh sách tên dự phòng đa ngành."""
        exchanges = [exchange] if exchange else ["HSX", "HNX"]
        names = [item_name] if isinstance(item_name, str) else list(item_name)

        for ex in exchanges:
            try:
                df = self.load_raw(ex, statement)
                for name in names:
                    mask = (
                        (df["ticker"] == ticker) &
                        (df["year"] == year) &
                        (df["item_name"].str.strip() == str(name).strip())
                    )
                    result = df.loc[mask, "value"]
                    if not result.empty:
                        val = result.iloc[0]
                        if pd.notna(val):
                            return float(val)
            except Exception:
                continue

        return None

    def build_panel(
        self,
        tickers: List[str],
        years: List[int],
        variables: Optional[List[str]] = None,
        auto_ratios: Optional[List[str]] = None,
        progress_callback=None,
    ) -> pd.DataFrame:
        """
        Xây dựng panel data tài chính.

        Args:
            tickers: Danh sách mã CK
            years: Danh sách năm
            variables: Raw variables cần lấy (keys từ ITEM_MAPPING)
            auto_ratios: Ratios tự tính (keys từ RATIO_FORMULAS)
            progress_callback: Callable(ticker, year) — gọi sau mỗi observation

        Returns:
            pd.DataFrame: (ticker, year, var1, var2, ...)
        """
        if variables is None:
            variables = ["total_assets", "total_equity", "total_debt",
                         "revenue", "net_income"]
        if auto_ratios is None:
            auto_ratios = ["roa", "roe", "size", "leverage"]

        rows: List[Dict[str, Any]] = []

        for ticker in tickers:
            for year in years:
                row: Dict[str, Any] = {"ticker": ticker, "year": year}

                # Get raw variables
                for var_name in variables:
                    item_name = self.ITEM_MAPPING.get(var_name)
                    if item_name:
                        statement = (
                            "income_statement"
                            if var_name in ("revenue", "net_income", "ebit", "ebitda")
                            else "balance_sheet"
                        )
                        row[var_name] = self.get_item_value(
                            ticker, year, item_name, statement
                        )

                # Compute ratios
                for ratio_name in auto_ratios:
                    formula = self.RATIO_FORMULAS.get(ratio_name)
                    if formula:
                        try:
                            val = formula(row)
                            row[ratio_name] = round(val, 6) if val is not None else None
                        except (ZeroDivisionError, TypeError, ValueError):
                            row[ratio_name] = None

                rows.append(row)

                if progress_callback:
                    progress_callback(ticker, year)

        df = pd.DataFrame(rows)
        logger.info(
            f"Financial panel built: {len(df)} observations "
            f"({len(tickers)} tickers × {len(years)} years)"
        )
        return df
