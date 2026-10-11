# -*- coding: utf-8 -*-
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import crawl_and_standardize_bctc as c

from arminer.data.catalog import UnifiedCatalog
cat = UnifiedCatalog()
cat.initialize()
bctn_records, total_bctn = cat.search(limit=100000, return_total=True)

bctn_targets = defaultdict(lambda: defaultdict(set))
for r in bctn_records:
    t = r.get("ticker")
    y = r.get("year")
    ex = r.get("exchange", "UNKNOWN")
    if t and y:
        bctn_targets[ex][t].add(int(y))

upcom_tickers = sorted(bctn_targets["UPCOM"].keys())
print(f"=== BẮT ĐẦU CÀO & CHUẨN HÓA {len(upcom_tickers)} MÃ UPCOM (10 WORKERS) ===", flush=True)

templates = c.load_templates()

import threading
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_local = threading.local()

def get_thread_session():
    if not hasattr(_local, "session"):
        s = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=15,
            pool_maxsize=15,
            max_retries=Retry(total=1, backoff_factor=0.2, status_forcelist=[500, 502, 503, 504])
        )
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        s.headers.update(c.HEADERS)
        _local.session = s
    return _local.session

def process_one_upcom(ticker):
    sess = get_thread_session()
    t_years = sorted(bctn_targets["UPCOM"].get(ticker, list(range(2018, 2026))))
    raw = c.crawl_ticker(ticker, sess, t_years)
    return c.standardize_ticker_data(ticker, "UPCOM", raw, templates, t_years)

upcom_rows = []
success_count = 0
t_start = time.time()

with ThreadPoolExecutor(max_workers=10) as executor:
    futures = {executor.submit(process_one_upcom, t): t for t in upcom_tickers}
    done = 0
    for fut in as_completed(futures):
        t = futures[fut]
        done += 1
        try:
            res = fut.result()
            if res:
                upcom_rows.extend(res)
                # Count success if has non-zero values
                if any(r["value"] != 0.0 for r in res):
                    success_count += 1
            if done % 50 == 0 or done == len(upcom_tickers):
                elapsed = time.time() - t_start
                pct = (done / len(upcom_tickers)) * 100
                rate = done / elapsed if elapsed > 0 else 0
                print(f"  [UPCoM] {done:3d}/{len(upcom_tickers)} ({pct:5.1f}%) | Thành công BCTC: {success_count:3d} mã | Tốc độ: {rate:4.1f} mã/s | Thời gian: {elapsed:5.1f}s", flush=True)
        except Exception as e:
            print(f"  [Lỗi {t}]: {e}", flush=True)

print(f"\nĐã xử lý xong toàn bộ {len(upcom_tickers)} mã UPCoM ({len(upcom_rows):,} rows dữ liệu)!", flush=True)
print("Đang ghi vào src/arminer/data/bctc_data/{statement}/UPCOM.parquet...", flush=True)
c.update_parquet_files(upcom_rows, "UPCOM")
print("=== HOÀN TẤT 100% GIAI ĐOẠN 2 CHO SÀN UPCOM ===", flush=True)
