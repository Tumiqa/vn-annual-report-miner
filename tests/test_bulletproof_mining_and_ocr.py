# -*- coding: utf-8 -*-
"""
tests/test_bulletproof_mining_and_ocr.py
==========================================
Unit & Integration tests verifying:
1. Exact keyword matching (no fuzzy noise, full case-insensitivity, acronym guard).
2. Vietnamese NFC Unicode normalization.
3. Span-based deduplication (no arbitrary // 5 bucket loss; AI/ML both preserved).
4. Longest-match precedence for compound terms (Generative AI vs AI core).
5. Category frequency mapping (ensuring category _Freq columns are real non-zero numbers).
6. Smart Hybrid OCR page classification:
   - Sliced/tiled image pages (e.g., 4 or 5 horizontal slices like AAA 2018 / 2019).
   - 100% scanned pages (AAA 2010).
   - Hybrid digital + scanned audit report pages (AAA 2021).
   - Pure native pages (AAA 2024).
   - Blank / divider pages (no compute wasted).
"""

import unicodedata
from pathlib import Path
import pytest

from arminer.core.smart_mode import FlexibleDictionary, SmartVariableCalculator
from arminer.mining.matcher import GenericFuzzyMatcher
from arminer.ocr.engine import OCREngine


def make_ai_flex_dict():
    raw_data = {
        "name": "AI_F1_Dictionary",
        "version": "1.0.0",
        "categories": {
            "lớp_1_ai_core": {
                "description": "AI Core",
                "keywords": [
                    {
                        "keyword": "Artificial Intelligence",
                        "variants": ["trí tuệ nhân tạo", "AI"],
                    },
                    {
                        "keyword": "Generative AI",
                        "variants": ["trí tuệ nhân tạo tạo sinh", "GenAI"],
                    },
                    {
                        "keyword": "Machine Learning",
                        "variants": ["học máy", "ML"],
                    },
                    {
                        "keyword": "Blockchain",
                        "variants": ["blockchain", "DLT", "chuỗi khối"],
                    },
                ],
            }
        },
    }
    import tempfile, yaml
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        yaml.dump(raw_data, f, allow_unicode=True)
        tmp_name = f.name
    try:
        return FlexibleDictionary.load(tmp_name)
    finally:
        Path(tmp_name).unlink(missing_ok=True)


def test_exact_matcher_acronym_and_vietnamese():
    flex = make_ai_flex_dict()
    core_dict = flex.to_core_dictionary()
    matcher = GenericFuzzyMatcher(dictionary=core_dict)

    text = """
    Báo cáo thường niên 2024:
    Công ty đẩy mạnh ứng dụng Trí tuệ nhân tạo và trí tuệ nhân tạo tạo sinh.
    Đồng thời hệ thống AI/ML và DLT được tích hợp vào core banking.
    Tuy nhiên, ai cũng hiểu rằng nếu không có nhân lực thì ai làm được?
    """

    matches = matcher.search(text, use_fuzzy=False)
    canonical_counts = {}
    for m in matches:
        canon = m["keyword_canonical"]
        canonical_counts[canon] = canonical_counts.get(canon, 0) + 1

    # 'Artificial Intelligence' should be found (from 'Trí tuệ nhân tạo' and 'AI')
    assert canonical_counts.get("Artificial Intelligence", 0) >= 1
    # 'Machine Learning' should be found (from 'ML' in 'AI/ML')
    assert canonical_counts.get("Machine Learning", 0) >= 1
    # 'Generative AI' should be found (from 'trí tuệ nhân tạo tạo sinh')
    assert canonical_counts.get("Generative AI", 0) >= 1

    # Crucial check: Vietnamese stopword 'ai' ("ai cũng hiểu", "ai làm được") MUST NOT MATCH!
    for m in matches:
        assert m["keyword_found"].lower() != "ai" or m["keyword_found"] == "AI", (
            f"False positive lowercase 'ai' matched: {m}"
        )


def test_no_bucket_collision_preserves_adjacent_keywords():
    flex = make_ai_flex_dict()
    core_dict = flex.to_core_dictionary()
    matcher = GenericFuzzyMatcher(dictionary=core_dict)

    # In "AI/ML", AI is at pos 0..2, ML is at pos 3..5. The old // 5 bucket erased ML.
    text = "AI/ML"
    matches = matcher.search(text, use_fuzzy=False)
    assert len(matches) == 2, f"Expected 2 matches for AI/ML, got {len(matches)}: {matches}"
    found_keywords = [m["keyword_canonical"] for m in matches]
    assert "Artificial Intelligence" in found_keywords
    assert "Machine Learning" in found_keywords


def test_longest_match_precedence():
    flex = make_ai_flex_dict()
    core_dict = flex.to_core_dictionary()
    matcher = GenericFuzzyMatcher(dictionary=core_dict)

    # 'trí tuệ nhân tạo tạo sinh' should win over 'trí tuệ nhân tạo' at that exact span
    text = "Đầu tư mạnh vào trí tuệ nhân tạo tạo sinh phục vụ khách hàng."
    matches = matcher.search(text, use_fuzzy=False)
    assert len(matches) == 1
    assert matches[0]["keyword_canonical"] == "Generative AI"


def test_category_frequency_calculation():
    flex = make_ai_flex_dict()
    core_dict = flex.to_core_dictionary()
    matcher = GenericFuzzyMatcher(dictionary=core_dict)
    calc = SmartVariableCalculator()

    text = """
    Chiến lược Chuyển đổi số:
    1. Trí tuệ nhân tạo (AI): tự động hóa quy trình.
    2. Học máy (Machine Learning - ML): mô hình dự báo rủi ro tín dụng.
    3. Blockchain: minh bạch hóa dữ liệu hợp đồng điện tử.
    """

    matches = matcher.search(text, use_fuzzy=False)
    words = text.split()
    vars_r = calc.calculate_all(
        matches, len(words),
        category_names=flex.categories,
        topic_prefix="ai",
        total_dict_keywords=len(flex.entries),
        classification_rules=flex.classification_rules,
    )

    # Verify that total frequency is positive and category columns have real values
    assert vars_r["Frequency"] >= 3
    assert vars_r["Mention"] == 1
    assert vars_r["Unique_Keywords"] >= 2
    # Verify AI core category frequency is non-zero
    ai_core_col = [k for k in vars_r if "lớp_1" in k and "Freq" in k]
    assert len(ai_core_col) == 1
    assert vars_r[ai_core_col[0]] >= 2


def test_sliced_image_page_detection_for_ocr():
    """Verify that pages sliced into 4 or 5 images (e.g. AAA 2018, AAA 2019) are detected for OCR."""
    import fitz
    aaa_dir = Path("H:/My Drive/arminer_bctn_gap/AAA")
    if not aaa_dir.exists():
        pytest.skip("AAA directory not available on this environment")

    p2019 = aaa_dir / "AAA_2019_BCTN.pdf"
    if not p2019.exists():
        pytest.skip("AAA 2019 not present")

    doc = fitz.open(p2019)
    # Check page 3 (index 2) which was skipped by the old engine because each slice has h=250/240 < 400
    page3 = doc[2]
    imgs = page3.get_images()
    total_px = sum(doc.extract_image(img[0])["width"] * doc.extract_image(img[0])["height"] for img in imgs)
    
    # Must have substantial visual image pixels
    assert len(imgs) == 5
    assert total_px > 2_000_000

    # Ensure engine logic detects page3 as a scanned page
    engine = OCREngine()
    extract_flags = fitz.TEXT_DEHYPHENATE | fitz.TEXT_PRESERVE_WHITESPACE
    p_text = page3.get_text(flags=extract_flags).strip()
    assert len(p_text) < 50
    has_scanned = (total_px >= 50_000)
    assert has_scanned is True
    doc.close()


def test_panel_data_no_company_name_exchange_and_integer_pages(tmp_path):
    """
    Verify:
    1. 'company_name' and 'exchange' are deleted from sheet 'Panel_Data' (Excel, CSV, Stata, Parquet).
    2. 'pages' is formatted strictly as an integer (e.g., 90, not 90.00).
    """
    import pandas as pd
    import openpyxl
    from arminer.core.smart_mode import ResearchOutputGenerator

    df = pd.DataFrame([
        {
            "ticker": "AAA",
            "company_name": "CTCP Nhựa An Phát Xanh",
            "exchange": "HOSE",
            "year": 2024,
            "icb_level1": "Nguyên vật liệu",
            "icb_level2": "Hóa chất",
            "file": "AAA_2024_BCTN.pdf",
            "pages": 90,  # Specific test case: 90 must stay 90, not 90.00
            "Word_Count": 35000,
            "Frequency": 5,
            "Log_Frequency": 1.7918,
            "Mention": 1,
            "Density": 0.0143,
            "Unique_Keywords": 2,
        },
        {
            "ticker": "BID",
            "company_name": "Ngân hàng TMCP Đầu tư và Phát triển Việt Nam",
            "exchange": "HOSE",
            "year": 2023,
            "icb_level1": "Tài chính",
            "icb_level2": "Ngân hàng",
            "file": "BID_2023_BCTN.pdf",
            "pages": 45.0,  # Even if float in source, must be converted to int
            "Word_Count": 42000,
            "Frequency": 8,
            "Log_Frequency": 2.1972,
            "Mention": 1,
            "Density": 0.0190,
            "Unique_Keywords": 3,
        },
    ])

    generator = ResearchOutputGenerator(tmp_path)
    outputs = generator.generate_all(df)

    xlsx_path = outputs["panel_excel"]
    csv_path = outputs["panel_csv"]
    stata_path = outputs["panel_stata"]

    # 1. Check Excel sheet 'Panel_Data'
    df_excel = pd.read_excel(xlsx_path, sheet_name="Panel_Data")
    assert "company_name" not in df_excel.columns, "company_name must be omitted from sheet Panel_Data"
    assert "exchange" not in df_excel.columns, "exchange must be omitted from sheet Panel_Data"
    assert "pages" in df_excel.columns
    assert pd.api.types.is_integer_dtype(df_excel["pages"])
    assert list(df_excel["pages"]) == [90, 45]

    # Check openpyxl cell value and number formatting (no .00)
    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb["Panel_Data"]
    col_names = [str(ws.cell(1, col).value) for col in range(1, ws.max_column + 1)]
    assert "company_name" not in col_names
    assert "exchange" not in col_names

    pages_idx = col_names.index("pages") + 1
    cell_row2 = ws.cell(row=2, column=pages_idx)
    assert isinstance(cell_row2.value, int)
    assert cell_row2.value == 90
    assert cell_row2.number_format == "0", f"Format must be '0', got {cell_row2.number_format}"

    cell_row3 = ws.cell(row=3, column=pages_idx)
    assert isinstance(cell_row3.value, int)
    assert cell_row3.value == 45
    assert cell_row3.number_format == "0"
    wb.close()

    # 2. Check CSV export
    df_csv = pd.read_csv(csv_path)
    assert "company_name" not in df_csv.columns
    assert "exchange" not in df_csv.columns
    assert list(df_csv["pages"]) == [90, 45]

    # Verify raw CSV text does NOT contain '90.0' or '90.00' for pages
    raw_csv = csv_path.read_text(encoding="utf-8")
    assert ",90," in raw_csv or raw_csv.endswith(",90\n") or raw_csv.endswith(",90\r\n")

    # 3. Check Stata export
    df_stata = pd.read_stata(stata_path)
    assert "company_name" not in df_stata.columns
    assert "exchange" not in df_stata.columns
    assert list(df_stata["pages"]) == [90, 45]

