# -*- coding: utf-8 -*-
"""
tests/test_snippet_extractor.py
================================
Unit tests for SnippetExtractor and the "Context" sheet in ResearchOutputGenerator.
"""

from pathlib import Path
import tempfile
import pandas as pd
import openpyxl

from arminer.mining.snippet_extractor import SnippetExtractor
from arminer.core.smart_mode import ResearchOutputGenerator
from arminer.export.excel_style import style_excel_file


def test_split_sentences_basic():
    text = (
        "Báo cáo thường niên năm 2023 của ngân hàng. "
        "Chúng tôi đã triển khai công nghệ blockchain trong thanh toán quốc tế! "
        "Dự án mang lại hiệu quả cao? Đúng vậy, rất thành công."
    )
    sentences = SnippetExtractor._split_sentences(text)
    assert len(sentences) == 4
    # Check that sentences correctly capture the text
    s0 = text[sentences[0][0]:sentences[0][1]].strip()
    s1 = text[sentences[1][0]:sentences[1][1]].strip()
    assert "Báo cáo thường niên" in s0
    assert "blockchain" in s1


def test_split_sentences_vietnamese_abbreviations():
    text = (
        "Ông Nguyễn Văn A là PGS.TS tại trường ĐH Kinh Tế TP.HCM. "
        "Ngân hàng hợp tác với công ty FPT Corp. để phát triển giải pháp AI."
    )
    sentences = SnippetExtractor._split_sentences(text)
    # PGS.TS and TP.HCM and Corp. should NOT create extra sentence boundaries
    assert len(sentences) == 2
    assert "PGS.TS" in text[sentences[0][0]:sentences[0][1]]
    assert "TP.HCM" in text[sentences[0][0]:sentences[0][1]]


def test_split_sentences_decimals():
    text = (
        "Tăng trưởng GDP đạt mức 6.5% trong năm qua. "
        "Lợi nhuận sau thuế đạt 1.250 tỷ đồng, tương đương tăng 12.8% so với cùng kỳ."
    )
    sentences = SnippetExtractor._split_sentences(text)
    assert len(sentences) == 2


def test_extract_sentence_context_normal():
    extractor = SnippetExtractor()
    text = (
        "Đoạn văn mở đầu giới thiệu tình hình chung. "
        "Hội đồng quản trị đã thông qua chủ trương ứng dụng blockchain trong thanh toán. "
        "Công nghệ này giúp giảm thời gian và chi phí xử lý giao dịch. "
        "Một câu văn kết luận ở phía sau."
    )
    pos = text.find("blockchain")
    kw = "blockchain"
    ctx = extractor.extract_sentence_context(text, pos, len(kw))

    # Should include preceding sentence, current sentence, and next sentence
    assert "giới thiệu tình hình chung" in ctx
    assert "blockchain trong thanh toán" in ctx
    assert "giảm thời gian và chi phí" in ctx
    # Should end at a sentence boundary (or with ...)
    assert ctx.endswith("xử lý giao dịch.") or ctx.endswith("...")


def test_extract_sentence_context_table():
    extractor = SnippetExtractor()
    table_text = (
        "STT\tChi tiêu\tNăm 2022\tNăm 2023\n"
        "1\tDoanh thu blockchain\t100.5\t250.0\n"
        "2\tLợi nhuận ròng\t50.2\t120.3\n"
    )
    pos = table_text.find("blockchain")
    kw = "blockchain"
    ctx = extractor.extract_sentence_context(table_text, pos, len(kw))

    # Should extract tabular context (line containing keyword ± 1 line)
    assert "Doanh thu blockchain" in ctx
    assert "Năm 2022" in ctx or "Lợi nhuận ròng" in ctx


def test_extract_all_with_context():
    extractor = SnippetExtractor()
    text = "Ngân hàng mở rộng ứng dụng blockchain và trí tuệ nhân tạo trong năm 2023."
    matches = [
        {
            "keyword_found": "blockchain",
            "keyword_canonical": "blockchain",
            "category": "technology",
            "match_type": "exact",
            "similarity": 100.0,
            "position": text.find("blockchain"),
        }
    ]
    results = extractor.extract_all_with_context(text, matches, ticker="ACB", year=2023)
    assert len(results) == 1
    r = results[0]
    assert r["STT"] == 1
    assert r["Firm"] == "ACB"
    assert r["Year"] == 2023
    assert r["Keyword"] == "blockchain"
    assert "blockchain" in r["Sentence_Context"]


def test_research_output_generator_with_context_sheet():
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        gen = ResearchOutputGenerator(out_dir)

        panel_df = pd.DataFrame([
            {"ticker": "VCB", "year": 2023, "blockchain_frequency": 5, "blockchain_dummy": 1},
            {"ticker": "ACB", "year": 2023, "blockchain_frequency": 2, "blockchain_dummy": 1},
        ])
        raw_df = pd.DataFrame([
            {"Firm": "VCB", "Year": 2023, "Keyword": "blockchain", "Category": "tech", "Frequency": 5},
            {"Firm": "ACB", "Year": 2023, "Keyword": "blockchain", "Category": "tech", "Frequency": 2},
        ])
        context_df = pd.DataFrame([
            {
                "STT": 1,
                "Firm": "VCB",
                "Year": 2023,
                "Keyword": "blockchain",
                "Canonical": "blockchain",
                "Category": "tech",
                "Match_Type": "exact",
                "Similarity": 100.0,
                "Sentence_Context": "Ngân hàng VCB đã ứng dụng công nghệ blockchain trong thanh toán quốc tế.",
            },
            {
                "STT": 2,
                "Firm": "ACB",
                "Year": 2023,
                "Keyword": "blockchain",
                "Canonical": "blockchain",
                "Category": "tech",
                "Match_Type": "exact",
                "Similarity": 100.0,
                "Sentence_Context": "ACB thí điểm blockchain cho dịch vụ bảo lãnh phát hành trực tuyến.",
            },
        ])

        outputs = gen.generate_all(
            panel_df=panel_df,
            raw_keywords_df=raw_df,
            context_snippets_df=context_df,
        )

        excel_path = outputs.get("panel_excel")
        assert excel_path is not None
        assert excel_path.exists()

        # Check sheets in generated Excel file (clean 5-sheet structure)
        wb = openpyxl.load_workbook(excel_path)
        sheet_names = wb.sheetnames
        assert sheet_names == ["Trang_Bia", "Panel_Data", "Context", "Raw_Keywords", "Codebook", "Company_Info"]
        assert "Descriptive_Stats" not in sheet_names
        assert "Correlation" not in sheet_names

        # Verify Panel_Data is the first data sheet and Context is the second data sheet
        assert sheet_names.index("Panel_Data") < sheet_names.index("Context")
        assert sheet_names.index("Context") < sheet_names.index("Raw_Keywords")

        # Verify Context sheet content
        ws_ctx = wb["Context"]
        headers = [cell.value for cell in ws_ctx[1]]
        assert "Sentence_Context" in headers
        assert "Firm" in headers
        assert "Keyword" in headers

        # Row count: 1 header + 2 data rows = 3 rows
        assert ws_ctx.max_row == 3

        # Also verify context_snippets.csv was generated
        csv_path = outputs.get("context_snippets_csv")
        assert csv_path is not None
        assert csv_path.exists()

        # Verify styling runs smoothly without error
        style_excel_file(excel_path)


def test_smart_variable_calculator_core_metrics():
    from arminer.core.smart_mode import SmartVariableCalculator
    calc = SmartVariableCalculator()
    matches = [
        {"keyword_canonical": "blockchain", "keyword_found": "blockchain", "category": "tech"},
        {"keyword_canonical": "blockchain", "keyword_found": "blockchain", "category": "tech"},
        {"keyword_canonical": "smart contract", "keyword_found": "smart contract", "category": "legal"},
    ]
    res = calc.calculate_all(matches, total_words=1000, category_names=["tech", "legal"], topic_prefix="fintech", total_dict_keywords=10)
    assert res["Word_Count"] == 1000
    assert res["Frequency"] == 3
    assert res["Log_Frequency"] > 0
    assert res["Mention"] == 1
    assert res["Density"] == 0.3
    assert res["Unique_Keywords"] == 2
    assert res["fintech_tech_Freq"] == 2
    assert res["fintech_legal_Freq"] == 1
    # Check that duplicates and Substantive/Coverage were removed
    assert "Substantive" not in res
    assert "Coverage" not in res
    assert "fintech_Frequency" not in res
    assert "fintech_Mention" not in res
