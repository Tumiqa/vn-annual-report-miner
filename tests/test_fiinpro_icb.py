# -*- coding: utf-8 -*-
"""
tests.test_fiinpro_icb
=======================
Unit tests for the 4-level FiinPro ICB classification system,
master company datasets, and taxonomy tree integrity.
"""

from pathlib import Path
import pandas as pd
import pytest
from arminer.data.industry import IndustryClassifier, ICB_LEVEL1, ICB_LEVEL2


def test_master_csv_exists_and_complete():
    """Verify master CSV exists and contains 1,562 stocks across HOSE, HNX, UPCOM."""
    root = Path(__file__).resolve().parent.parent
    csv_path = root / "danh_sach_doanh_nghiep_niem_yet.csv"
    assert csv_path.exists(), "Master CSV file must exist in project root"

    df = pd.read_csv(csv_path)
    assert len(df) == 1562, f"Expected 1,562 stocks, found {len(df)}"

    # Required columns
    expected_cols = [
        "Mã CK",
        "Tên Doanh Nghiệp",
        "Tên thương hiệu / Viết tắt",
        "Sàn giao dịch",
        "Ngành ICB Cấp 1 (Industry)",
        "Ngành ICB Cấp 2 (Supersector)",
        "Ngành ICB Cấp 3 (Sector)",
        "Ngành ICB Cấp 4 (Subsector)",
        "Mã Phân Ngành (ICB Code L4)",
        "Nguồn tham khảo (Source)",
        "Trang chủ (Website)",
        "Cổng thông tin IR (Quan hệ CĐ)",
    ]
    for col in expected_cols:
        assert col in df.columns, f"Missing required column: {col}"

    # Zero nulls in critical classification fields
    assert df["Mã CK"].isna().sum() == 0, "No null tickers allowed"
    assert df["Sàn giao dịch"].isna().sum() == 0, "No null exchange allowed"
    assert df["Ngành ICB Cấp 1 (Industry)"].isna().sum() == 0, "No null ICB L1 allowed"
    assert df["Ngành ICB Cấp 2 (Supersector)"].isna().sum() == 0, "No null ICB L2 allowed"
    assert df["Ngành ICB Cấp 3 (Sector)"].isna().sum() == 0, "No null ICB L3 allowed"
    assert df["Ngành ICB Cấp 4 (Subsector)"].isna().sum() == 0, "No null ICB L4 allowed"
    assert df["Nguồn tham khảo (Source)"].isna().sum() == 0, "No null Source allowed"

    # Exchange counts
    hose_cnt = (df["Sàn giao dịch"] == "HOSE").sum()
    hnx_cnt = (df["Sàn giao dịch"] == "HNX").sum()
    upcom_cnt = (df["Sàn giao dịch"] == "UPCOM").sum()
    assert hose_cnt == 406
    assert hnx_cnt == 301
    assert upcom_cnt == 855


def test_industry_classifier_tree_integrity():
    """Verify that summing tickers across all sectors equals the exact total."""
    ic = IndustryClassifier()
    ic.initialize()

    # 1. HOSE + HNX default
    tree_sys = ic.get_taxonomy_tree()
    sum_sys = sum(s["total_tickers"] for s in tree_sys["sectors"])
    assert tree_sys["total_tickers"] == 707
    assert sum_sys == 707, f"Expected 707 tickers, got sum {sum_sys}"

    # 2. All exchanges including UPCoM
    tree_all = ic.get_taxonomy_tree(include_upcom=True)
    sum_all = sum(s["total_tickers"] for s in tree_all["sectors"])
    assert tree_all["total_tickers"] == 1562
    assert sum_all == 1562, f"Expected 1,562 tickers, got sum {sum_all}"


def test_standard_ticker_lookups():
    """Verify FiinPro ICB classification for representative bellwether tickers."""
    ic = IndustryClassifier()
    ic.initialize()

    # Banking
    assert ic.get_industry("VCB")[0] == "Ngân hàng"
    assert ic.get_industry("MBB")[0] == "Ngân hàng"

    # Steel / Basic Materials
    l1, l2 = ic.get_industry("HPG")
    assert l1 == "Nguyên vật liệu"
    assert l2 == "Tài nguyên Cơ bản"

    # Food / Consumer Goods
    assert ic.get_industry("VNM")[0] == "Hàng Tiêu dùng"

    # Technology
    assert ic.get_industry("FPT")[0] == "Công nghệ Thông tin"

    # Oil & Gas (UPCoM)
    full_bsr = ic.get_industry_full("BSR")
    assert full_bsr["icb_l1"] == "Dầu khí"
    assert full_bsr["website"] != ""
    assert full_bsr["ir_portal"] != ""
