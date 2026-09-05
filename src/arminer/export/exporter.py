# -*- coding: utf-8 -*-
"""
arminer.export.exporter
========================
Xuất kết quả ra CSV / Parquet / Stata (.dta) / Excel.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import pandas as pd
from loguru import logger


class Exporter:
    """Xuất dữ liệu ra nhiều định dạng."""

    def __init__(self, project=None, output_dir: str | Path = None):
        if project:
            self.output_dir = project.output_dir
            self.formats = project.config.export.formats
        else:
            self.output_dir = Path(output_dir or "./output")
            self.formats = ["csv", "parquet"]

        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export(self, df: pd.DataFrame, name: str = "panel_data",
               formats: Optional[List[str]] = None) -> List[Path]:
        """
        Xuất DataFrame ra file.

        Args:
            df: DataFrame cần xuất
            name: Tên file (không có extension)
            formats: Danh sách format ["csv", "parquet", "stata", "excel"]

        Returns:
            List[Path] các file đã tạo
        """
        formats = formats or self.formats
        exported: List[Path] = []

        for fmt in formats:
            path = self._export_format(df, name, fmt)
            if path:
                exported.append(path)

        return exported

    def _export_format(self, df: pd.DataFrame, name: str,
                       fmt: str) -> Optional[Path]:
        """Export 1 format."""
        try:
            if fmt == "csv":
                path = self.output_dir / f"{name}.csv"
                df.to_csv(path, index=False, encoding="utf-8-sig")

            elif fmt == "parquet":
                path = self.output_dir / f"{name}.parquet"
                df.to_parquet(path, index=False, engine="pyarrow")

            elif fmt == "stata":
                path = self.output_dir / f"{name}.dta"
                self._export_stata(df, path)

            elif fmt == "excel":
                path = self.output_dir / f"{name}.xlsx"
                df.to_excel(path, index=False, engine="openpyxl")

            else:
                logger.warning(f"Unknown format: {fmt}")
                return None

            size = path.stat().st_size
            size_str = (
                f"{size / 1024 / 1024:.1f} MB"
                if size > 1024 * 1024
                else f"{size / 1024:.1f} KB"
            )
            logger.success(f"Exported: {path.name} ({size_str})")
            return path

        except Exception as e:
            logger.error(f"Export failed ({fmt}): {e}")
            return None

    def _export_stata(self, df: pd.DataFrame, path: Path) -> None:
        """Export sang Stata .dta với tên biến hợp lệ và nhãn mô tả."""
        from arminer.core.smart_mode import sanitize_stata_dataframe
        stata_df, labels = sanitize_stata_dataframe(df)

        try:
            import pyreadstat
            pyreadstat.write_dta(stata_df, str(path), column_labels=labels)
            return
        except ImportError:
            pass

        # Fallback: pandas to_stata
        try:
            stata_df.to_stata(path, write_index=False, version=118, variable_labels=labels)
        except Exception as e:
            logger.warning(f"to_stata with labels failed ({e}), retrying without labels")
            stata_df.to_stata(path, write_index=False, version=118)

    def export_all(self, dfs: dict = None) -> None:
        """Export tất cả dataframes."""
        if not dfs:
            logger.info("No data to export. Run mining stage first.")
            return

        for name, df in dfs.items():
            self.export(df, name=name)
