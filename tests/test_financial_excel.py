# -*- coding: utf-8 -*-
"""
Unit tests for financial Excel export with INDEX/MATCH dynamic formulas.
"""

from pathlib import Path
import openpyxl
import pandas as pd
import pytest

from arminer.export.financial_excel import export_financial_workbook, populate_financial_sheets


def _make_test_data():
    """Create minimal test data for 2 tickers × 2 years."""
    tickers = ["VCB", "HPG"]
    years = [2022, 2023]
    records = []
    for t in tickers:
        for y in years:
            records.append({
                "ticker": t, "year": y, "statement": "balance_sheet",
                "item_code": "bs_tong_tai_san", "item_name": "TỔNG CỘNG TÀI SẢN",
                "value": 1500000.0 if t == "VCB" else 900000.0,
            })
            records.append({
                "ticker": t, "year": y, "statement": "income_statement",
                "item_code": "is_doanh_thu_thuan", "item_name": "Doanh thu thuần",
                "value": 600000.0 if t == "VCB" else 400000.0,
            })

    all_data = pd.DataFrame(records)
    pivot = all_data.pivot_table(index=["ticker", "year"], columns="item_code", values="value").reset_index()
    ratio_cols = {}
    fin_codebook = [
        {
            "Biến": "bs_tong_tai_san",
            "Tên chỉ tiêu": "TỔNG CỘNG TÀI SẢN",
            "Phân loại / Nhóm": "Bảng cân đối kế toán",
            "Phân loại": "Chỉ tiêu kế toán",
            "Công thức / Nguồn": "vnfinancialdata",
        },
    ]
    return all_data, pivot, ratio_cols, fin_codebook


def test_export_financial_workbook_structure(tmp_path: Path):
    """Test that the exported xlsx has the correct sheet structure."""
    all_data, pivot, ratio_cols, fin_codebook = _make_test_data()
    export_xlsx = tmp_path / "financial_data.xlsx"

    result = export_financial_workbook(
        all_data=all_data, pivot=pivot,
        ratio_cols=ratio_cols, fin_codebook=fin_codebook,
        export_xlsx=export_xlsx,
    )

    assert export_xlsx.exists()
    wb = openpyxl.load_workbook(export_xlsx)

    # Check visible sheets
    expected_visible = ["Trang_Bia", "Bao_Cao_Tai_Chinh", "Ty_So_Tai_Chinh",
                        "Panel_Data_Goc", "Codebook", "Huong_Dan"]
    for s in expected_visible:
        assert s in wb.sheetnames, f"Missing sheet: {s}"

    # Check hidden data sheets
    assert "Data_BCTC" in wb.sheetnames
    assert "Data_TySo" in wb.sheetnames
    assert wb["Data_BCTC"].sheet_state == "hidden"
    assert wb["Data_TySo"].sheet_state == "hidden"

    # No xlsm should be generated
    assert not (tmp_path / "financial_data.xlsm").exists()

    wb.close()


def test_bctc_report_has_dynamic_formulas(tmp_path: Path):
    """Test that Bao_Cao_Tai_Chinh uses INDEX/MATCH formulas, not static values."""
    all_data, pivot, ratio_cols, fin_codebook = _make_test_data()
    export_xlsx = tmp_path / "financial_data.xlsx"

    export_financial_workbook(
        all_data=all_data, pivot=pivot,
        ratio_cols=ratio_cols, fin_codebook=fin_codebook,
        export_xlsx=export_xlsx,
    )

    wb = openpyxl.load_workbook(export_xlsx)
    ws_bc = wb["Bao_Cao_Tai_Chinh"]

    # Title
    assert ws_bc["A1"].value == "BÁO CÁO TÀI CHÍNH DOANH NGHIỆP"

    # B2 should have a ticker value (first ticker as default)
    assert ws_bc["B2"].value in ("HPG", "VCB")

    # Find the first data row (after header at row 4 and possible section header at row 5)
    first_formula_row = None
    for r in range(5, 20):
        cell = ws_bc.cell(row=r, column=4)  # First year column (D)
        if cell.value and str(cell.value).startswith("=IFERROR"):
            first_formula_row = r
            break

    assert first_formula_row is not None, "No INDEX/MATCH formula found in BCTC report"

    # Verify formula structure
    formula = str(ws_bc.cell(row=first_formula_row, column=4).value)
    assert "INDEX(Data_BCTC!" in formula
    assert "MATCH($B$2" in formula
    assert "IFERROR" in formula

    wb.close()


def test_tyso_report_has_dynamic_formulas(tmp_path: Path):
    """Test that Ty_So_Tai_Chinh uses INDEX/MATCH formulas."""
    all_data, pivot, ratio_cols, fin_codebook = _make_test_data()
    export_xlsx = tmp_path / "financial_data.xlsx"

    export_financial_workbook(
        all_data=all_data, pivot=pivot,
        ratio_cols=ratio_cols, fin_codebook=fin_codebook,
        export_xlsx=export_xlsx,
    )

    wb = openpyxl.load_workbook(export_xlsx)
    ws_ts = wb["Ty_So_Tai_Chinh"]

    assert "WIDATA" in ws_ts["A1"].value
    assert ws_ts["B2"].value in ("HPG", "VCB")

    # Find first formula row
    first_formula_row = None
    for r in range(5, 20):
        cell = ws_ts.cell(row=r, column=5)  # First year column (E)
        if cell.value and str(cell.value).startswith("=IFERROR"):
            first_formula_row = r
            break

    assert first_formula_row is not None, "No INDEX/MATCH formula found in TySo report"

    formula = str(ws_ts.cell(row=first_formula_row, column=5).value)
    assert "INDEX(Data_TySo!" in formula
    assert "MATCH($B$2" in formula

    wb.close()


def test_full_702_indicators_guarantee(tmp_path: Path):
    """Verify that ALL 702 accounting items are exported to the hidden data sheet."""
    import vnfinancialdata as vnf
    df_master = vnf.list_items(active_only=False)
    assert len(df_master) == 702

    all_data = pd.DataFrame([
        {"ticker": "VCB", "year": 2023, "item_code": "bs_tong_tai_san",
         "item_name": "TỔNG CỘNG TÀI SẢN", "value": 1500000.0, "statement": "balance_sheet"},
        {"ticker": "VCB", "year": 2023, "item_code": "is_doanh_thu_thuan",
         "item_name": "Doanh thu thuần", "value": 600000.0, "statement": "income_statement"},
    ])
    pivot = all_data.pivot_table(index=["ticker", "year"], columns="item_code", values="value").reset_index()

    export_xlsx = tmp_path / "vcb_702.xlsx"
    export_financial_workbook(
        all_data=all_data, pivot=pivot,
        ratio_cols={}, fin_codebook=[],
        export_xlsx=export_xlsx,
    )

    assert export_xlsx.exists()
    wb = openpyxl.load_workbook(export_xlsx, data_only=True)

    # Hidden Data_BCTC should have exactly 702 data rows (1 ticker × 702 items)
    ws_data = wb["Data_BCTC"]
    data_rows = ws_data.max_row - 1  # minus header row
    assert data_rows == 702, f"Expected 702 data rows, got {data_rows}"

    # Ty_So should have 75 ratios
    ws_tyso_data = wb["Data_TySo"]
    tyso_rows = ws_tyso_data.max_row - 1
    assert tyso_rows == 75, f"Expected 75 ratio rows, got {tyso_rows}"

    # BCTC report should have section headers + 702 item rows
    ws_bc = wb["Bao_Cao_Tai_Chinh"]
    # Count rows that have an item_code in column B (non-section-header rows)
    item_rows = 0
    for r in range(5, ws_bc.max_row + 1):
        val = ws_bc.cell(row=r, column=2).value
        if val and str(val).startswith(("bs_", "is_", "cf_", "thuyet_minh", "ngoai_bang")):
            item_rows += 1
    assert item_rows == 702, f"Expected 702 item rows in report, got {item_rows}"

    # Check 13 accounting categories exist in section headers
    all_text = set()
    for r in range(5, ws_bc.max_row + 1):
        v = ws_bc.cell(row=r, column=1).value
        if v:
            all_text.add(str(v).strip())
    assert any("TÀI SẢN NGẮN HẠN" in t for t in all_text)
    assert any("VỐN CHỦ SỞ HỮU" in t for t in all_text)
    assert any("DOANH THU" in t for t in all_text)
    assert any("DÒNG TIỀN" in t for t in all_text)

    wb.close()
