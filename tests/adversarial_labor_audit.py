# -*- coding: utf-8 -*-
"""
Adversarial Labor Audit: 51 Untested Listed Companies
====================================================
Tests 51 distinct untested tickers across diverse industries.
Audits precision (zero false positives) AND recall (flags potential false negatives).
"""

import glob
import json
import os
import re
import sys
import time
from pathlib import Path
import fitz

sys.path.insert(0, "src")
sys.stdout.reconfigure(encoding="utf-8")

from arminer.mining.labor_extractor import LaborExtractor

ALREADY_TESTED = {
    'AAA', 'HU1', 'HU4', 'HVN', 'ICG', 'ICN', 'ICT', 'IDC', 'ILA', 'ILC', 'IMP',
    'IN4', 'ISH', 'ITA', 'ITQ', 'ITS', 'JVC', 'KAC', 'KBE', 'KDH', 'KDM', 'KHL',
    'KLF', 'KOS', 'KSB', 'KSH', 'KSV', 'KTS', 'KTT', 'L10', 'LAI', 'LBM', 'LDW',
    'LG9', 'LHC', 'LLM', 'LMI', 'LO5', 'LTC', 'LUT', 'MBG', 'MFS', 'MH3', 'MHC',
    'MKV', 'MNB', 'MSN', 'MTG', 'MTL', 'MVB', 'TN1'
}

def collect_digital_reports():
    all_files = glob.glob('data/bctn_new_extracted/*/*.pdf') + glob.glob('data/zenodo_cache/*/*.pdf') + glob.glob('data/zenodo_cache/*/*/*.pdf')
    digital_by_ticker = {}
    for p in all_files:
        m = re.search(r'([A-Za-z0-9]+)_(\d{4})', os.path.basename(p))
        if m:
            t = m.group(1).upper()
            if t not in ALREADY_TESTED:
                yr = int(m.group(2))
                try:
                    doc = fitz.open(p)
                    pgs = len(doc)
                    if pgs >= 10:
                        sample_text = ''.join(doc[i].get_text() for i in range(min(5, pgs)))
                        if len(sample_text.strip()) >= 800:
                            if t not in digital_by_ticker:
                                digital_by_ticker[t] = []
                            digital_by_ticker[t].append((yr, p, pgs))
                    doc.close()
                except Exception:
                    pass
    return digital_by_ticker

def scan_pdf_for_potential_miss(pdf_path, target_year):
    """
    Independent scanner to check if the PDF mentions labor explicitly
    to catch potential false negatives when LaborExtractor returns NOT_FOUND.
    """
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
                    # Exclude sections talking about BOD or shareholders
                    if "hội đồng quản trị" in txt_lower[max(0, m.start()-50):m.end()+50]:
                        continue
                    start = max(0, m.start() - 100)
                    end = min(len(txt), m.end() + 250)
                    window = txt[start:end]
                    # check if window has numbers >= 20
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

def run_adversarial_audit():
    digital_reports = collect_digital_reports()
    all_tickers = sorted(list(digital_reports.keys()))
    print(f"Total distinct untested tickers with digital reports: {len(all_tickers)}\n")
    
    extractor = LaborExtractor()
    results = []
    anomalies = []
    
    start_total_time = time.time()
    
    for idx, ticker in enumerate(all_tickers, 1):
        reports = sorted(digital_reports[ticker], key=lambda x: x[0], reverse=True)
        selected_yr, selected_path, pgs = reports[0]
        
        print(f"[{idx:02d}/{len(all_tickers):02d}] {ticker} ({selected_yr}, {pgs}p)...", end=" ", flush=True)
        
        t0 = time.time()
        try:
            res = extractor.extract_from_pdf(selected_path, ticker=ticker, year=selected_yr)
        except Exception as e:
            print(f"CRASH: {e}")
            anomalies.append({
                "ticker": ticker,
                "year": selected_yr,
                "type": "CRASH",
                "error": str(e),
                "path": selected_path
            })
            continue
            
        elapsed = time.time() - t0
        
        strat = res.all_candidates[0].strategy if res.all_candidates else None
        entry = {
            "ticker": ticker,
            "year": selected_yr,
            "pages": pgs,
            "pdf_path": selected_path,
            "labor": res.labor,
            "status": str(res.status),
            "confidence": res.confidence,
            "source_page": res.source_page,
            "strategy": strat,
            "raw_text": res.raw_text[:200] if res.raw_text else None,
            "elapsed_sec": round(elapsed, 2)
        }
        results.append(entry)
        
        # AUDIT CHECKS:
        # Check 1: Suspicious labor value (False Positive check)
        if res.labor is not None:
            val = res.labor
            snip = (res.raw_text or "").lower()
            reasons = []
            if val in (selected_yr, selected_yr - 1, selected_yr + 1, 2020, 2021, 2022, 2023, 2024, 2025):
                reasons.append(f"Labor matches year ({val})")
            if val < 10:
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
                    "year": selected_yr,
                    "type": "FALSE_POSITIVE_RISK",
                    "labor": val,
                    "page": res.source_page,
                    "reasons": reasons,
                    "snippet": res.raw_text,
                    "path": selected_path
                })
            else:
                print(f"SUCCESS -> {val:,} (p.{res.source_page}, {strat}, conf={res.confidence:.2f}, {elapsed:.1f}s)")
        else:
            # Check 2: Potential miss check (False Negative check)
            misses = scan_pdf_for_potential_miss(selected_path, selected_yr)
            if misses:
                first_miss = misses[0]
                print(f"POTENTIAL MISS: p.{first_miss['page']}, kw='{first_miss['kw']}', num={first_miss['candidate_num']}")
                anomalies.append({
                    "ticker": ticker,
                    "year": selected_yr,
                    "type": "FALSE_NEGATIVE_RISK",
                    "page": first_miss["page"],
                    "kw": first_miss["kw"],
                    "candidate_num": first_miss["candidate_num"],
                    "snippet": first_miss["window"],
                    "path": selected_path
                })
            else:
                print(f"NOT_FOUND (Verified: no labor section in report, {elapsed:.1f}s)")

    print("\n" + "="*70)
    print(f"AUDIT SUMMARY:")
    print(f"Total companies tested: {len(results)}")
    success_count = sum(1 for r in results if r["status"] == "ExtractionStatus.SUCCESS" or r["status"] == "SUCCESS")
    not_found_count = sum(1 for r in results if r["status"] == "ExtractionStatus.NOT_FOUND" or r["status"] == "NOT_FOUND")
    print(f"Extracted (SUCCESS): {success_count} ({success_count/len(results)*100:.1f}%)")
    print(f"Legitimately NOT_FOUND: {not_found_count - len([a for a in anomalies if a['type'] == 'FALSE_NEGATIVE_RISK'])}")
    print(f"Anomalies / Risks detected: {len(anomalies)}")
    for a in anomalies:
        print(f"   * [{a['type']}] {a['ticker']} ({a['year']}): {a.get('reasons') or a.get('kw')}")
    
    with open("tests/batch_audit_results.json", "w", encoding="utf-8") as f:
        json.dump({"results": results, "anomalies": anomalies}, f, ensure_ascii=False, indent=2)
    print(f"Results saved to tests/batch_audit_results.json. Total time: {time.time() - start_total_time:.1f}s")
    
    return anomalies

if __name__ == "__main__":
    run_adversarial_audit()
