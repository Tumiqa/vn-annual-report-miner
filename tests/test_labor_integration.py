# -*- coding: utf-8 -*-
"""
tests.test_labor_integration
============================
End-to-End Integration Tests for Labor Extraction:
- Tests _process_one_bctn with extract_labor=True
- Tests ResearchOutputGenerator with labor_audit_df
- Tests Excel sheets creation (Panel_Data, Labor_Audit, Codebook)
"""

import glob
import os
import sys
import tempfile
from pathlib import Path
import pandas as pd
import pytest

sys.stdout.reconfigure(encoding="utf-8")

from arminer.core.smart_mode import FlexibleDictionary, SmartVariableCalculator, ResearchOutputGenerator
from arminer.mining.matcher import GenericFuzzyMatcher
from arminer.mining.labor_extractor import LaborExtractor
from arminer.ui.server import _process_one_bctn, ScanSelectedRequest, scan_selected_reports


def test_process_one_bctn_with_labor():
    # Find IMP 2021 or KSB 2022
    p_list = glob.glob("data/bctn_new_extracted/*/IMP_2021_BCTN.pdf")
    assert len(p_list) > 0, "IMP 2021 test report must exist"
    p = Path(p_list[0])

    item = {
        "path": p,
        "ticker": "IMP",
        "year": 2021,
        "icb_l1": "Y tế",
        "icb_l2": "Dược phẩm",
    }

    flex_dict = FlexibleDictionary.from_dict({"core": ["dược phẩm"]})
    core_dict = flex_dict.to_core_dictionary()
    matcher = GenericFuzzyMatcher(dictionary=core_dict)
    calc = SmartVariableCalculator()

    res = _process_one_bctn(
        item=item,
        matcher=matcher,
        calc=calc,
        flex_dict=flex_dict,
        topic_prefix="test",
        use_fuzzy=False,
        extract_labor=True,
    )

    assert res is not None
    assert "Labor" in res["row"]
    assert res["row"]["Labor"] == 1224
    assert res["row"]["Labor_Page"] == 51
    assert res["row"]["Labor_Confidence"] >= 0.95
    assert res["labor_audit"] is not None
    assert res["labor_audit"]["Ticker"] == "IMP"
    assert res["labor_audit"]["Labor"] == 1224
    assert "người" in res["labor_audit"]["Snippet"] or "nhân" in res["labor_audit"]["Snippet"]


def test_research_output_generator_with_labor_audit():
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_dir = Path(tmp_dir)
        generator = ResearchOutputGenerator(out_dir)

        panel_df = pd.DataFrame([
            {
                "ticker": "IMP",
                "year": 2021,
                "icb_level1": "Y tế",
                "icb_level2": "Dược phẩm",
                "file": "IMP_2021_BCTN.pdf",
                "pages": 81,
                "Labor": 1224,
                "Labor_Page": 51,
                "Labor_Confidence": 0.99,
                "Word_Count": 15000,
                "Frequency": 5,
                "Log_Frequency": 1.7918,
                "Mention": 1,
                "Density": 0.0333,
                "Unique_Keywords": 2,
            },
            {
                "ticker": "KSB",
                "year": 2022,
                "icb_level1": "Tài nguyên Cơ bản",
                "icb_level2": "Khai khoáng",
                "file": "KSB_2022_BCTN.pdf",
                "pages": 85,
                "Labor": 310,
                "Labor_Page": 39,
                "Labor_Confidence": 0.99,
                "Word_Count": 20000,
                "Frequency": 0,
                "Log_Frequency": 0.0,
                "Mention": 0,
                "Density": 0.0,
                "Unique_Keywords": 0,
            }
        ])

        labor_audit_df = pd.DataFrame([
            {
                "STT": 1,
                "Ticker": "IMP",
                "Year": 2021,
                "Labor": 1224,
                "Page": 51,
                "Confidence": 0.99,
                "Status": "SUCCESS",
                "Strategy": "narrative_direct_total",
                "Snippet": "Tổng số nhân viên tính đến 31/12/2021 là 1.224 người",
                "File": "IMP_2021_BCTN.pdf",
            },
            {
                "STT": 2,
                "Ticker": "KSB",
                "Year": 2022,
                "Labor": 310,
                "Page": 39,
                "Confidence": 0.99,
                "Status": "SUCCESS",
                "Strategy": "narrative_direct_total",
                "Snippet": "Tổng số lao động năm 2022 là 310 người",
                "File": "KSB_2022_BCTN.pdf",
            }
        ])

        outputs = generator.generate_all(panel_df, labor_audit_df=labor_audit_df)

        assert "panel_excel" in outputs
        excel_path = outputs["panel_excel"]
        assert excel_path.exists()

        # Check excel sheets
        xl = pd.ExcelFile(excel_path)
        sheet_names = xl.sheet_names
        print(f"Generated Excel Sheets: {sheet_names}")
        assert "Panel_Data" in sheet_names
        assert "Labor_Audit" in sheet_names
        assert "Codebook" in sheet_names

        # Verify Panel_Data content
        df_panel = pd.read_excel(excel_path, sheet_name="Panel_Data")
        assert "Labor" in df_panel.columns
        assert list(df_panel["Labor"]) == [1224, 310]

        # Verify Labor_Audit content
        df_audit = pd.read_excel(excel_path, sheet_name="Labor_Audit")
        assert len(df_audit) == 2
        assert list(df_audit["Ticker"]) == ["IMP", "KSB"]
        assert list(df_audit["Labor"]) == [1224, 310]

        xl.close()


if __name__ == "__main__":
    print("Running integration tests...")
    test_process_one_bctn_with_labor()
    print("✓ test_process_one_bctn_with_labor PASSED!")
    test_research_output_generator_with_labor_audit()
    print("✓ test_research_output_generator_with_labor_audit PASSED!")
    print("All integration tests PASSED successfully!")
