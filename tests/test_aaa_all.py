import sys
from pathlib import Path

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")

from arminer.mining.labor_extractor import LaborExtractor

EXPECTED = {
    2011: 1097,
    2012: 1072,
    2013: 1247,
    2014: 1121,
    2015: 1405,
    2016: 1737,
    2017: 1834,
    2020: 1950,
    2021: 1750,
    2022: 1689,
    2023: 1684,
    2024: 4765,
    2025: 4493,
}

extractor = LaborExtractor()
pdf_dir = Path("data/zenodo_cache/gap_filler/AAA")

all_passed = True
for yr, expected_val in EXPECTED.items():
    pdf_path = pdf_dir / f"AAA_{yr}_BCTN.pdf"
    if not pdf_path.exists():
        print(f"FAILED: {pdf_path} not found")
        all_passed = False
        continue

    res = extractor.extract_from_pdf(pdf_path, ticker="AAA", year=yr)
    passed = res.labor == expected_val
    if not passed:
        all_passed = False
    strat = res.all_candidates[0].strategy if res.all_candidates else "none"
    status_sym = "PASS" if passed else "FAIL"
    print(f"[{status_sym}] AAA {yr}: Extracted={res.labor} | Expected={expected_val} | Page={res.source_page} | Strategy={strat}")

print(f"\nOVERALL RESULT: {'ALL PASS' if all_passed else 'SOME FAILED'}")
assert all_passed, "Some AAA tests failed!"
