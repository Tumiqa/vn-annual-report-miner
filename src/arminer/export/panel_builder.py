# -*- coding: utf-8 -*-
"""
arminer.export.panel_builder
===============================
⭐ Merge text mining results + financial data → research-ready panel.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd
from loguru import logger


class PanelBuilder:
    """
    Xây dựng Panel Data kết hợp Text Mining + Financial Variables.

    Merge by (ticker, year) → output DataFrame ready for Stata/R regression.
    """

    def __init__(self, panel_id: str = "ticker", time_var: str = "year"):
        self.panel_id = panel_id
        self.time_var = time_var

    def build(
        self,
        text_mining_df: Optional[pd.DataFrame] = None,
        financial_df: Optional[pd.DataFrame] = None,
        custom_variables_df: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """
        Merge tất cả sources thành 1 panel data.

        Args:
            text_mining_df: DataFrame (ticker, year, freq, div, score, ...)
            financial_df: DataFrame (ticker, year, roa, roe, size, ...)
            custom_variables_df: DataFrame (ticker, year, var1, var2, ...)

        Returns:
            Merged panel DataFrame
        """
        merge_keys = [self.panel_id, self.time_var]
        dfs: List[pd.DataFrame] = []

        if text_mining_df is not None and not text_mining_df.empty:
            dfs.append(text_mining_df)

        if financial_df is not None and not financial_df.empty:
            dfs.append(financial_df)

        if custom_variables_df is not None and not custom_variables_df.empty:
            dfs.append(custom_variables_df)

        if not dfs:
            logger.warning("No data to merge")
            return pd.DataFrame()

        # Start with first DF
        panel = dfs[0]

        # Merge remaining
        for df in dfs[1:]:
            # Find common columns to avoid duplicates
            common_cols = [
                c for c in df.columns
                if c in panel.columns and c not in merge_keys
            ]
            if common_cols:
                df = df.drop(columns=common_cols)

            panel = pd.merge(
                panel, df,
                on=merge_keys,
                how="outer",
            )

        # Sort
        panel = panel.sort_values(merge_keys).reset_index(drop=True)

        logger.info(
            f"Panel built: {len(panel)} observations, "
            f"{len(panel.columns)} variables"
        )
        return panel

    def add_controls(self, panel: pd.DataFrame) -> pd.DataFrame:
        """Thêm biến control chuẩn cho mô hình hồi quy."""
        df = panel.copy()

        # Year dummies
        if self.time_var in df.columns:
            year_dummies = pd.get_dummies(
                df[self.time_var], prefix="year", dtype=int
            )
            df = pd.concat([df, year_dummies], axis=1)

        # Industry dummies (nếu có)
        if "industry" in df.columns:
            industry_dummies = pd.get_dummies(
                df["industry"], prefix="ind", dtype=int
            )
            df = pd.concat([df, industry_dummies], axis=1)

        return df

    def describe(self, panel: pd.DataFrame) -> pd.DataFrame:
        """Descriptive statistics chuẩn cho bài báo."""
        numeric_cols = panel.select_dtypes(include=["number"]).columns
        desc = panel[numeric_cols].describe().T
        desc["missing"] = panel[numeric_cols].isna().sum()
        desc["missing_pct"] = (desc["missing"] / len(panel) * 100).round(2)
        return desc.round(4)
