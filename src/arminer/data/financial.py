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

    # Mapping item_name phổ biến
    ITEM_MAPPING = {
        "total_assets": "TỔNG TÀI SẢN",
        "total_equity": "VỐN CHỦ SỞ HỮU",
        "total_debt": "NỢ PHẢI TRẢ",
        "revenue": "Doanh số thuần",
        "net_income": "Lãi/(lỗ) thuần sau thuế",
        "cash": "Tiền và tương đương tiền",
        "ebit": "EBIT",
        "ebitda": "EBITDA",
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
                       item_name: str, statement: str = "balance_sheet",
                       exchange: str = None) -> Optional[float]:
        """Lấy 1 giá trị cụ thể cho (ticker, year, item)."""
        exchanges = [exchange] if exchange else ["HSX", "HNX"]

        for ex in exchanges:
            try:
                df = self.load_raw(ex, statement)
                mask = (
                    (df["ticker"] == ticker) &
                    (df["year"] == year) &
                    (df["item_name"] == item_name)
                )
                result = df.loc[mask, "value"]
                if not result.empty:
                    val = result.iloc[0]
                    return float(val) if pd.notna(val) else None
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
