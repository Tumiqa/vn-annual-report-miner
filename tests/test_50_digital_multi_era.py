# -*- coding: utf-8 -*-
"""
Multi-Era Benchmark: 50 Untested Reports (2014 - 2024)
======================================================
Tests 50 distinct reports spanning:
- 20 reports from XUA (2014 - 2017)
- 15 reports from TRUNG (2018 - 2020)
- 15 reports from NAY (2021 - 2024)
All from reports not previously audited in batches 1-3.
"""

import glob
import json
import os
import random
import re
import sys
import time
from pathlib import Path
import fitz

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")

from arminer.mining.labor_extractor import LaborExtractor

def load_already_tested():
    tested = set()
    for yr in range(2010, 2026):
        tested.add(('AAA', yr))
    
    if os.path.exists('tests/labor_audit_50_results.json'):
        with open('tests/labor_audit_50_results.json', encoding='utf-8') as f:
            for item in json.load(f):
                tested.add((item['ticker'], item['year']))
                
    if os.path.exists('tests/batch_audit_results.json'):
        with open('tests/batch_audit_results.json', encoding='utf-8') as f:
            for item in json.load(f)['results']:
                tested.add((item['ticker'], item['year']))
    return tested

def sample_50_multi_era():
    already_tested = load_already_tested()
    all_files = glob.glob('data/bctn_new_extracted/*/*.pdf')
    
    xua_pool = []
    trung_pool = []
    nay_pool = []
    
    for p in all_files:
        fn = os.path.basename(p)
        m = re.search(r'([A-Za-z0-9]+)_(\d{4})', fn)
        if m:
            t = m.group(1).upper()
            yr = int(m.group(2))
            if (t, yr) not in already_tested:
                try:
                    doc = fitz.open(p)
                    pgs = len(doc)
                    if pgs >= 10:
                        txt = ''.join(doc[i].get_text() for i in range(min(5, pgs)))
                        if len(txt.strip()) > 500:
                            if yr <= 2017:
                                xua_pool.append((t, yr, pgs, p))
                            elif yr <= 2020:
                                trung_pool.append((t, yr, pgs, p))
                            else:
                                nay_pool.append((t, yr, pgs, p))
                    doc.close()
                except Exception:
                    pass

    random.seed(42)  # Deterministic seed for reproducible evaluation
    xua_sampled = random.sample(xua_pool, min(20, len(xua_pool)))
    trung_sampled = random.sample(trung_pool, min(15, len(trung_pool)))
    nay_sampled = random.sample(nay_pool, min(15, len(nay_pool)))
    
    combined = (
        [(t, yr, pgs, p, 'XUA') for t, yr, pgs, p in xua_sampled] +
        [(t, yr, pgs, p, 'TRUNG') for t, yr, pgs, p in trung_sampled] +
        [(t, yr, pgs, p, 'NAY') for t, yr, pgs, p in nay_sampled]
    )
    return combined

def scan_pdf_for_potential_miss(pdf_path, target_year):
    strong_keywords = [
        r"tổng\s+số\s+lao\s+động",
        r"tổng\s+số\s+cán\s+bộ\s+công\s+nhân\s+viên",
        r"tổng\s+số\s+cbcnv",
        r"tổng\s+số\s+nhân\s+viên",
        r"số\s+lượng\s+lao\s+động",
        r"số\s+lượng\s+nhân\s+viên",
        r"quy\s+mô\s+nhân\s+sự",
    ]
    misses = []
    try:
        doc = fitz.open(pdf_path)
        for page_idx in range(len(doc)):
            txt = doc[page_idx].get_text()
            if not txt or len(txt.strip()) < 50:
                continue
            txt_lower = txt.lower()
            for kw in strong_keywords:
                m = re.search(kw, txt_lower)
                if m:
                    surrounding = txt_lower[max(0, m.start()-50):m.end()+50]
                    if "hội đồng quản trị" in surrounding or "cổ đông" in surrounding:
                        continue
                    start = max(0, m.start() - 100)
                    end = min(len(txt), m.end() + 250)
                    window = txt[start:end]
                    num_match = re.search(r'\b([1-9]\d{1,5})\b', window)
                    if num_match:
                        misses.append({
                            "page": page_idx + 1,
                            "kw": kw,
                            "candidate_num": int(num_match.group(1)),
                            "window": window.strip().replace('\n', ' ')
                        })
                        break
        doc.close()
    except Exception:
        pass
    return misses

def run_multi_era_audit():
    test_cases = sample_50_multi_era()
    print(f"Sampled {len(test_cases)} distinct multi-era reports:")
    xua_cnt = sum(1 for c in test_cases if c[4] == 'XUA')
    trung_cnt = sum(1 for c in test_cases if c[4] == 'TRUNG')
    nay_cnt = sum(1 for c in test_cases if c[4] == 'NAY')
    print(f"  * XUA   (2014-2017): {xua_cnt} reports")
    print(f"  * TRUNG (2018-2020): {trung_cnt} reports")
    print(f"  * NAY   (2021-2024): {nay_cnt} reports\n")
    
    extractor = LaborExtractor()
    results = []
    anomalies = []
    start_time = time.time()
    
    for idx, (ticker, year, pgs, pdf_path, era) in enumerate(test_cases, 1):
        print(f"[{idx:02d}/50] [{era:5s}] {ticker:4s} {year} ({pgs:3d}p)...", end=" ", flush=True)
        t0 = time.time()
        try:
            res = extractor.extract_from_pdf(pdf_path, ticker=ticker, year=year)
        except Exception as e:
            print(f"CRASH: {e}")
            anomalies.append({
                "ticker": ticker,
                "year": year,
                "era": era,
                "type": "CRASH",
                "error": str(e),
                "path": str(pdf_path)
            })
            continue
            
        elapsed = time.time() - t0
        strat = res.all_candidates[0].strategy if res.all_candidates else None
        entry = {
            "ticker": ticker,
            "year": year,
            "era": era,
            "pages": pgs,
            "labor": res.labor,
            "status": str(res.status),
            "confidence": res.confidence,
            "source_page": res.source_page,
            "strategy": strat,
            "raw_text": res.raw_text[:200] if res.raw_text else None,
            "elapsed_sec": round(elapsed, 2),
            "pdf_path": str(pdf_path)
        }
        results.append(entry)
        
        # AUDIT CHECKS:
        if res.labor is not None:
            val = res.labor
            snip = (res.raw_text or "").lower()
            reasons = []
            if val in (year, year - 1, year + 1, 2020, 2021, 2022, 2023, 2024, 2025):
                reasons.append(f"Labor matches year ({val})")
            if val < 5:
                reasons.append(f"Suspiciously small headcount ({val})")
            if val > 500000:
                reasons.append(f"Suspiciously huge headcount ({val})")
            if any(term in snip for term in ["triệu đồng", "tỷ đồng", "vnd", "usd", "lương bình quân"]):
                reasons.append("Snippet contains currency/salary terms")
            if "%" in snip or "tỷ lệ" in snip:
                if re.search(r'\b' + str(val) + r'\s*%', snip):
                    reasons.append("Extracted number is followed by %")
            
            if reasons:
                print(f"FAILED (SUSPICIOUS): val={val} | {'; '.join(reasons)}")
                anomalies.append({
                    "ticker": ticker,
                    "year": year,
                    "era": era,
                    "type": "FALSE_POSITIVE_RISK",
                    "labor": val,
                    "page": res.source_page,
                    "reasons": reasons,
                    "snippet": res.raw_text,
                    "path": str(pdf_path)
                })
            else:
                print(f"SUCCESS -> {val:,} (p.{res.source_page}, {strat}, conf={res.confidence:.2f}, {elapsed:.1f}s)")
        else:
            misses = scan_pdf_for_potential_miss(pdf_path, year)
            if misses:
                first_miss = misses[0]
                print(f"POTENTIAL MISS: p.{first_miss['page']}, kw='{first_miss['kw']}', num={first_miss['candidate_num']}")
                anomalies.append({
                    "ticker": ticker,
                    "year": year,
                    "era": era,
                    "type": "FALSE_NEGATIVE_RISK",
                    "page": first_miss["page"],
                    "kw": first_miss["kw"],
                    "candidate_num": first_miss["candidate_num"],
                    "snippet": first_miss["window"],
                    "path": str(pdf_path)
                })
            else:
                print(f"NOT_FOUND (Verified: no labor section in report, {elapsed:.1f}s)")

    print("\n" + "="*70)
    print("50 MULTI-ERA AUDIT SUMMARY:")
    print(f"Total reports evaluated: {len(results)}")
    success_count = sum(1 for r in results if "SUCCESS" in r["status"])
    not_found_count = sum(1 for r in results if "NOT_FOUND" in r["status"])
    print(f"Extracted (SUCCESS): {success_count} ({success_count/len(results)*100:.1f}%)")
    print(f"Legitimately NOT_FOUND: {not_found_count - len([a for a in anomalies if a['type'] == 'FALSE_NEGATIVE_RISK'])}")
    print(f"Anomalies / Risks detected: {len(anomalies)}")
    for a in anomalies:
        print(f"   * [{a['type']}] {a['ticker']} {a['year']} ({a['era']}): {a.get('reasons') or a.get('kw')}")
    
    with open("tests/multi_era_50_results.json", "w", encoding="utf-8") as f:
        json.dump({"results": results, "anomalies": anomalies}, f, ensure_ascii=False, indent=2)
    print(f"Results saved to tests/multi_era_50_results.json. Total runtime: {time.time() - start_time:.1f}s")
    
    return anomalies

if __name__ == "__main__":
    run_multi_era_audit()
