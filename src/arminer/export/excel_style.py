# -*- coding: utf-8 -*-
"""
arminer.export.excel_style
===========================
Shared premium styling utility for ALL Excel exports.
Cung cấp bộ styling nhất quán cho mọi file .xlsx xuất ra từ arminer:
header gradient, zebra stripe, section headers, auto-filter, freeze panes, column auto-width.

Usage:
    from arminer.export.excel_style import style_workbook
    wb = style_workbook(path_or_writer, sheet_configs={...})
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side, numbers
from openpyxl.utils import get_column_letter
import pandas as pd
from loguru import logger


# =====================================================================
# PREMIUM COLOR PALETTE
# =====================================================================

NAVY = "1B3A5C"
TEAL = "0D7377"
GOLD = "D4A843"
PURPLE = "805AD5"
GREEN = "38A169"
DARK_BLUE = "205375"
WHITE = "FFFFFF"
LIGHT_GRAY = "F8FAFB"
BORDER_COLOR = "E2E8F0"

# Pre-built fills
FILL_NAVY = PatternFill(start_color=NAVY, end_color=NAVY, fill_type="solid")
FILL_TEAL = PatternFill(start_color=TEAL, end_color=TEAL, fill_type="solid")
FILL_PURPLE = PatternFill(start_color=PURPLE, end_color=PURPLE, fill_type="solid")
FILL_GREEN = PatternFill(start_color=GREEN, end_color=GREEN, fill_type="solid")
FILL_DARK_BLUE = PatternFill(start_color=DARK_BLUE, end_color=DARK_BLUE, fill_type="solid")
FILL_WHITE = PatternFill(start_color=WHITE, end_color=WHITE, fill_type="solid")
FILL_ZEBRA = PatternFill(start_color=LIGHT_GRAY, end_color=LIGHT_GRAY, fill_type="solid")

# Pre-built fonts
FONT_HEADER = Font(name="Segoe UI", size=11, bold=True, color=WHITE)
FONT_BODY = Font(name="Segoe UI", size=10, color="2D3748")
FONT_SMALL = Font(name="Segoe UI", size=9, color="718096")

# Pre-built borders
THIN_BORDER = Border(
    left=Side(style="thin", color=BORDER_COLOR),
    right=Side(style="thin", color=BORDER_COLOR),
    top=Side(style="thin", color=BORDER_COLOR),
    bottom=Side(style="thin", color=BORDER_COLOR),
)

CENTER = Alignment(horizontal="center", vertical="center")
LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
RIGHT = Alignment(horizontal="right", vertical="center")

# Color palette per sheet name for auto-selection
_SHEET_COLORS = {
    "Panel_Data": NAVY,
    "Merged_Panel": NAVY,
    "Raw_Keywords": TEAL,
    "Codebook": PURPLE,
    "Descriptive_Stats": GREEN,
    "Correlation": DARK_BLUE,
    "Financial_Data": NAVY,
}


def _pick_header_fill(sheet_name: str) -> PatternFill:
    """Auto-pick a header fill color based on sheet name."""
    color = _SHEET_COLORS.get(sheet_name, NAVY)
    return PatternFill(start_color=color, end_color=color, fill_type="solid")


def _auto_col_width(ws, min_width: int = 10, max_width: int = 55) -> None:
    """Auto-size column widths based on content (heuristic)."""
    for col_cells in ws.columns:
        col_letter = get_column_letter(col_cells[0].column)
        max_len = 0
        for cell in col_cells[:100]:  # sample first 100 rows for perf
            if cell.value is not None:
                cell_len = len(str(cell.value))
                if cell_len > max_len:
                    max_len = cell_len
        width = min(max(max_len + 3, min_width), max_width)
        ws.column_dimensions[col_letter].width = width


def _guess_number_format(col_name: str) -> Optional[str]:
    """Guess appropriate number format from column name."""
    cl = col_name.lower()
    if cl in ("year", "nam"):
        return "0"
    if any(k in cl for k in ("pct", "ratio", "rate", "roa", "roe", "ros", "margin", "ty_le", "bien")):
        return "0.00%"
    if any(k in cl for k in ("log", "ln_")):
        return "0.000"
    if any(k in cl for k in ("freq", "count", "n", "so_luong")):
        return "#,##0"
    return None


def style_worksheet(
    ws,
    header_fill: Optional[PatternFill] = None,
    freeze_at: Optional[str] = None,
    auto_filter: bool = True,
    auto_width: bool = True,
    tab_color: Optional[str] = None,
    number_formats: Optional[Dict[str, str]] = None,
) -> None:
    """
    Apply premium styling to a worksheet that already has data.

    Args:
        ws: openpyxl Worksheet with data written (row 1 = headers).
        header_fill: PatternFill for header row. Auto-picked if None.
        freeze_at: Cell ref for freeze panes (e.g. "C2"). Auto-set if None.
        auto_filter: Whether to add AutoFilter.
        auto_width: Whether to auto-size columns.
        tab_color: Sheet tab color hex. Auto-picked if None.
        number_formats: Dict of {column_name: format_string} overrides.
    """
    if ws.max_row is None or ws.max_row < 1:
        return

    max_col = ws.max_column or 1
    max_row = ws.max_row or 1

    # Tab color
    if tab_color:
        ws.sheet_properties.tabColor = tab_color
    else:
        color = _SHEET_COLORS.get(ws.title, NAVY)
        ws.sheet_properties.tabColor = color

    # Header fill
    if header_fill is None:
        header_fill = _pick_header_fill(ws.title)

    # --- Style header row (row 1) ---
    col_names = []
    for col_idx in range(1, max_col + 1):
        cell = ws.cell(row=1, column=col_idx)
        col_names.append(str(cell.value or ""))
        cell.font = FONT_HEADER
        cell.fill = header_fill
        cell.alignment = CENTER
        cell.border = THIN_BORDER

    # --- Build number_formats map (col_index -> fmt) ---
    nf_map: Dict[int, str] = {}
    user_nf = number_formats or {}
    for col_idx, cname in enumerate(col_names, 1):
        if cname in user_nf:
            nf_map[col_idx] = user_nf[cname]
        else:
            guessed = _guess_number_format(cname)
            if guessed:
                nf_map[col_idx] = guessed

    # --- Style data rows (row 2+) ---
    for row_idx in range(2, max_row + 1):
        # Zebra striping
        fill = FILL_WHITE if (row_idx - 2) % 2 == 0 else FILL_ZEBRA

        for col_idx in range(1, max_col + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = FONT_BODY
            cell.fill = fill
            cell.border = THIN_BORDER

            # Alignment: numbers right, text left
            if isinstance(cell.value, (int, float)):
                cell.alignment = RIGHT
            else:
                cell.alignment = LEFT

            # Number format
            if col_idx in nf_map and isinstance(cell.value, (int, float)):
                cell.number_format = nf_map[col_idx]
            elif isinstance(cell.value, (int, float)):
                v = abs(cell.value)
                if v == 0 or v >= 100:
                    cell.number_format = "#,##0"
                elif v >= 1:
                    cell.number_format = "#,##0.00"
                else:
                    cell.number_format = "0.0000"

    # --- Freeze panes ---
    if freeze_at:
        ws.freeze_panes = freeze_at
    elif max_col >= 3:
        ws.freeze_panes = "C2"
    else:
        ws.freeze_panes = "A2"

    # --- AutoFilter ---
    if auto_filter and max_row > 1:
        ws.auto_filter.ref = f"A1:{get_column_letter(max_col)}{max_row}"

    # --- Auto column width ---
    if auto_width:
        _auto_col_width(ws)


def style_workbook(wb: openpyxl.Workbook) -> openpyxl.Workbook:
    """Apply premium styling to ALL sheets in a workbook."""
    for ws in wb.worksheets:
        if ws.max_row and ws.max_row > 1:
            style_worksheet(ws)
    return wb


def style_excel_file(path: Union[str, Path]) -> Path:
    """
    Open an existing .xlsx file, apply premium styling, and save.
    Convenience function for post-processing after pd.ExcelWriter.

    Args:
        path: Path to the .xlsx file.

    Returns:
        The same Path after styling.
    """
    path = Path(path)
    if not path.exists():
        logger.warning(f"style_excel_file: file not found: {path}")
        return path

    try:
        wb = openpyxl.load_workbook(path)
        style_workbook(wb)
        wb.save(path)
        wb.close()
        logger.debug(f"Applied premium styling to {path.name}")
    except Exception as e:
        logger.warning(f"Could not apply styling to {path.name}: {e}")

    return path
