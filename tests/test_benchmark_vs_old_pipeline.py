# -*- coding: utf-8 -*-
"""
tests/test_benchmark_vs_old_pipeline.py
========================================
So sánh trực tiếp độ chính xác và hiệu năng giữa:
1. Dự án cũ: blockchain_pipeline (FuzzyMatcher + blockchain_dictionary.py)
2. Dự án mới: vn-annual-report-miner (GenericFuzzyMatcher + FlexibleDictionary)

Dữ liệu kiểm thử: Các file OCR thật từ blockchain_pipeline/data/ocr_output/
"""

import sys
import time
from pathlib import Path
import pandas as pd
from loguru import logger

# Set logging level to WARNING to avoid verbose logs during test
logger.remove()
logger.add(sys.stderr, level="WARNING")

# Paths
ROOT_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_DIR = ROOT_DIR.parent
OLD_PIPELINE_DIR = WORKSPACE_DIR / "blockchain_pipeline"

import pytest
if not OLD_PIPELINE_DIR.exists():
    pytest.skip("Legacy benchmark directory not present on this machine", allow_module_level=True)

# Import old pipeline
sys.path.insert(0, str(OLD_PIPELINE_DIR))
from stage4_text_mining.fuzzy_matcher import FuzzyMatcher as OldFuzzyMatcher

# Import new pipeline
from arminer.mining.matcher import GenericFuzzyMatcher
from arminer.core.smart_mode import FlexibleDictionary, SmartVariableCalculator

def test_benchmark_against_old_pipeline():
    print("=" * 70)
    print("BENCHMARK & ACCURACY COMPARISON: arminer vs blockchain_pipeline")
    print("=" * 70)

    # 1. Setup dictionaries
    old_matcher = OldFuzzyMatcher(threshold=85, include_ambiguous=False)
    
    # Use the exact same dictionary in arminer
    dict_csv = OLD_PIPELINE_DIR / "data" / "exports" / "blockchain_keywords_db.csv"
    flex_dict = FlexibleDictionary.load(dict_csv)
    core_dict = flex_dict.to_core_dictionary()
    new_matcher = GenericFuzzyMatcher(dictionary=core_dict, threshold=85, include_ambiguous=False)

    print(f"Old matcher keywords: {len(old_matcher.keywords)}")
    print(f"New matcher keywords: {len(new_matcher.keywords)}")
    print()

    # Load baseline panel data from old pipeline
    panel_csv = OLD_PIPELINE_DIR / "data" / "parquet" / "blockchain_panel_data.csv"
    baseline_df = pd.read_csv(panel_csv) if panel_csv.exists() else None

    # Test cases with real OCR files
    test_cases = [
        ("FPT", 2021, OLD_PIPELINE_DIR / "data" / "ocr_output" / "MST_FPT" / "2021" / "text.txt"),
        ("FPT", 2020, OLD_PIPELINE_DIR / "data" / "ocr_output" / "MST_FPT" / "2020" / "text.txt"),
        ("SSI", 2024, OLD_PIPELINE_DIR / "data" / "ocr_output" / "MST_SSI" / "2024" / "text.txt"),
        ("HUT", 2022, OLD_PIPELINE_DIR / "data" / "ocr_output" / "MST_HUT" / "2022" / "text.txt"),
        ("MSR", 2023, OLD_PIPELINE_DIR / "data" / "ocr_output" / "MST_MSR" / "2023" / "text.txt"),
        ("VIC", 2021, OLD_PIPELINE_DIR / "data" / "ocr_output" / "MST_VIC" / "2021" / "text.txt"),
        ("VNM", 2021, OLD_PIPELINE_DIR / "data" / "ocr_output" / "MST_VNM" / "2021" / "text.txt"),
    ]

    total_old_time = 0.0
    total_new_time = 0.0
    all_matched_perfectly = True

    calc = SmartVariableCalculator()

    for ticker, year, file_path in test_cases:
        if not file_path.exists():
            print(f"[SKIP] {ticker} {year}: File not found ({file_path})")
            continue

        text = file_path.read_text(encoding="utf-8", errors="replace")
        words = text.split()
        word_count = len(words)

        # Old pipeline search (exact + fuzzy + deduplication)
        t0 = time.perf_counter()
        old_matches = old_matcher.search(text, use_fuzzy=True)
        old_time = time.perf_counter() - t0
        total_old_time += old_time

        # New arminer search
        t0 = time.perf_counter()
        new_matches = new_matcher.search(text, use_fuzzy=True)
        new_time = time.perf_counter() - t0
        total_new_time += new_time

        # Baseline stats from CSV
        csv_row = None
        if baseline_df is not None:
            matches_in_csv = baseline_df[(baseline_df["ticker"] == ticker) & (baseline_df["year"] == year)]
            if not matches_in_csv.empty:
                csv_row = matches_in_csv.iloc[0]

        # Extract canonicals
        old_canonicals = set(m.get("keyword_original") or m.get("keyword_found") for m in old_matches)
        new_canonicals = set(m.get("keyword_canonical", m.get("keyword_found")) for m in new_matches)

        # Variables from arminer
        vars_res = calc.calculate_all(new_matches, word_count, category_names=flex_dict.categories, topic_prefix="blockchain")

        freq_old = len(old_matches)
        freq_new = len(new_matches)
        csv_freq = int(csv_row["frequency"]) if csv_row is not None else "N/A"

        div_old = len(old_canonicals)
        div_new = len(new_canonicals)
        csv_div = int(csv_row["diversity"]) if csv_row is not None else "N/A"

        status = "OK" if freq_old == freq_new and div_old == div_new else "DIFF"
        if status != "OK":
            all_matched_perfectly = False

        print(f"Report: {ticker} ({year}) | Words: {word_count:,} | Status: [{status}]")
        print(f"  Old Pipeline: Freq={freq_old}, Div={div_old} ({old_time*1000:.1f} ms)")
        print(f"  arminer:      Freq={freq_new}, Div={div_new} ({new_time*1000:.1f} ms) [Speedup: {old_time/max(new_time, 1e-6):.2f}x]")
        if csv_row is not None:
            print(f"  Baseline CSV: Freq={csv_freq}, Div={csv_div}")
        print(f"  Keywords matched: {', '.join(sorted(new_canonicals)) or 'None'}")
        print()

    print("=" * 70)
    print("SUMMARY RESULTS")
    print("=" * 70)
    print(f"Total Old Execution Time: {total_old_time*1000:.2f} ms")
    print(f"Total arminer Time:        {total_new_time*1000:.2f} ms")
    if total_new_time > 0:
        print(f"Overall Speedup:           {total_old_time/total_new_time:.2f}x")
    print(f"Accuracy Consistency:      {'100% IDENTICAL' if all_matched_perfectly else 'DIFFERENCES FOUND'}")
    print("=" * 70)

if __name__ == "__main__":
    test_benchmark_against_old_pipeline()
