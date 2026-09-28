# -*- coding: utf-8 -*-
"""
Benchmark & Audit Script: 50 Random Companies (2018-2025)
=========================================================
Runs LaborExtractor on 50 distinct listed companies across 2018-2025.
Collects Labor, Page, Confidence, Status, and Proving Snippet for verification.
"""

import glob
import json
import os
import random
import re
import sys
import time
from pathlib import Path

# Force UTF-8 stdout
sys.stdout.reconfigure(encoding="utf-8")

import fitz
from arminer.mining.labor_extractor import LaborExtractor


def collect_native_reports():
    reports_by_ticker = {}
    for p in glob.glob("data/bctn_new_extracted/*/*.pdf"):
        fn = os.path.basename(p)
        m = re.search(r"([A-Za-z0-9]+)_(\d{4})", fn)
        if m:
            ticker = m.group(1).upper()
            year = int(m.group(2))
            if 2018 <= year <= 2025:
                try:
                    doc = fitz.open(p)
                    pages = len(doc)
                    if pages >= 15:
                        t = "".join(doc[i].get_text() for i in range(min(5, pages)))
                        if len(t.strip()) > 500:
                            if ticker not in reports_by_ticker:
                                reports_by_ticker[ticker] = []
                            reports_by_ticker[ticker].append((year, p, pages))
                    doc.close()
                except Exception:
                    pass
    return reports_by_ticker


def run_benchmark():
    reports_by_ticker = collect_native_reports()
    print(f"Total available tickers with digital reports: {len(reports_by_ticker)}")

    random.seed(2026)  # Deterministic seed
    all_tickers = sorted(list(reports_by_ticker.keys()))
    sampled_tickers = random.sample(all_tickers, min(50, len(all_tickers)))

    test_cases = []
    for t in sorted(sampled_tickers):
        opts = reports_by_ticker[t]
        yr, path, pgs = random.choice(opts)
        test_cases.append((t, yr, path, pgs))

    print(f"Starting Labor Extraction on {len(test_cases)} companies...")
    print("=" * 110)
    print(f"{'#':2} | {'Ticker':6} | {'Year':4} | {'Pages':5} | {'Labor':8} | {'P.':4} | {'Conf':5} | {'Status':8} | {'Strategy':20}")
    print("=" * 110)

    extractor = LaborExtractor()
    results = []

    t0 = time.time()
    for idx, (t, yr, path, pgs) in enumerate(test_cases, 1):
        res = extractor.extract_from_pdf(path, t, yr)
        strat = res.metadata.get("strategy", "N/A")[:20]
        lab_str = str(res.labor) if res.labor is not None else "None"
        pg_str = str(res.source_page) if res.source_page is not None else "-"
        
        print(f"{idx:2} | {t:6} | {yr:4} | {pgs:5} | {lab_str:8} | {pg_str:4} | {res.confidence:5.2f} | {res.status:8} | {strat:20}")

        results.append({
            "index": idx,
            "ticker": t,
            "year": yr,
            "pages": pgs,
            "labor": res.labor,
            "source_page": res.source_page,
            "confidence": res.confidence,
            "status": res.status,
            "strategy": res.metadata.get("strategy", ""),
            "snippet": res.raw_text,
            "file": os.path.basename(path),
        })

    elapsed = time.time() - t0
    print("=" * 110)
    print(f"Completed {len(results)} reports in {elapsed:.2f}s ({elapsed/len(results):.2f}s/report).")

    # Save detailed audit log
    out_path = Path("tests/labor_audit_50_results.json")
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Detailed audit log saved to {out_path}")

    # Summary
    success_count = sum(1 for r in results if r["status"] == "SUCCESS")
    print(f"\nSUCCESS rate: {success_count}/{len(results)} ({success_count/len(results)*100:.1f}%)")


if __name__ == "__main__":
    run_benchmark()
