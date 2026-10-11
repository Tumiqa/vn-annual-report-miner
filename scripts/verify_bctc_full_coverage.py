# -*- coding: utf-8 -*-
"""
Kịch bản kiểm toán toàn diện dữ liệu BCTC sau khi cào và chuẩn hóa bổ sung:
1. Độ bao phủ BCTN - BCTC theo từng sàn (HSX, HNX, UPCOM) giai đoạn 2018-2025 & toàn bộ lịch sử.
2. Kiểm tra tính toàn vẹn và tính cân đối kế toán (Tổng tài sản = Nợ phải trả + Vốn chủ sở hữu).
3. Kiểm tra tính tương thích với FinancialDataProvider (build_panel & get_item_value).
"""

import sys
import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from arminer.data.catalog import UnifiedCatalog
from arminer.data.financial import FinancialDataProvider

def run_comprehensive_audit():
    print("=" * 70)
    print("           KIỂM TOÁN ĐỐI SOÁT TOÀN DIỆN BCTC - BCTN (3 SÀN)")
    print("=" * 70)

    # 1. Tải catalog BCTN
    cat = UnifiedCatalog()
    cat.initialize()
    records, total = cat.search(limit=100000, return_total=True)
    print(f"Tổng số báo cáo thường niên (BCTN) trong catalog: {len(records):,} bản ghi")

    bctn_targets = defaultdict(lambda: defaultdict(set))
    for r in records:
        ex = r.get("exchange", "UNKNOWN")
        t = r.get("ticker")
        y = r.get("year")
        if t and y:
            bctn_targets[ex][t].add(int(y))

    # 2. Tải dữ liệu BCTC từ parquet
    bctc_dir = ROOT / "src" / "arminer" / "data" / "bctc_data"
    exchanges = ["HSX", "HNX", "UPCOM"]
    
    bctc_firm_years = defaultdict(set)
    summary_stats = {}

    for ex in exchanges:
        bs_path = bctc_dir / "balance_sheet" / f"{ex}.parquet"
        is_path = bctc_dir / "income_statement" / f"{ex}.parquet"
        cf_path = bctc_dir / "cash_flow" / f"{ex}.parquet"

        if not bs_path.exists():
            print(f"[-] Cảnh báo: Chưa tìm thấy file {bs_path}")
            continue

        df_bs = pd.read_parquet(bs_path)
        df_is = pd.read_parquet(is_path) if is_path.exists() else pd.DataFrame()
        df_cf = pd.read_parquet(cf_path) if cf_path.exists() else pd.DataFrame()

        summary_stats[ex] = {
            "bs_rows": len(df_bs),
            "bs_tickers": df_bs["ticker"].nunique(),
            "is_rows": len(df_is),
            "is_tickers": df_is["ticker"].nunique() if not df_is.empty else 0,
            "cf_rows": len(df_cf),
            "cf_tickers": df_cf["ticker"].nunique() if not df_cf.empty else 0,
        }

        # Lưu các cặp (ticker, year) có trong BCTC
        pairs = set(zip(df_bs["ticker"], df_bs["year"]))
        bctc_firm_years[ex] = pairs

    print("\n1. THỐNG KÊ QUY MÔ DỮ LIỆU BCTC NỘI BỘ (PARQUET OFFLINE):")
    print(f"{'Sàn':<8} | {'Bảng CĐKT (BS)':<20} | {'Kết Quả KD (IS)':<20} | {'Lưu Chuyển TT (CF)':<20}")
    print("-" * 75)
    for ex in exchanges:
        if ex in summary_stats:
            s = summary_stats[ex]
            print(f"{ex:<8} | {s['bs_rows']:>7,} rows ({s['bs_tickers']:>3} mã) | {s['is_rows']:>7,} rows ({s['is_tickers']:>3} mã) | {s['cf_rows']:>7,} rows ({s['cf_tickers']:>3} mã)")

    # 3. Đối soát tỷ lệ match BCTN vs BCTC
    print("\n2. TỶ LỆ KHỚP NỐI BCTN - BCTC (GIAI ĐOẠN TRỌNG TÂM 2018 - 2025):")
    print(f"{'Sàn':<8} | {'Số mã':<8} | {'Firm-Years BCTN':<16} | {'Firm-Years BCTC':<16} | {'Khớp (%)':<10} | {'Khuyết':<8}")
    print("-" * 75)
    
    total_bctn_fy_focus = 0
    total_matched_fy_focus = 0

    for ex in ["HSX", "HNX", "UPCOM"]:
        tickers = bctn_targets[ex]
        bctn_fy_focus = 0
        matched_fy_focus = 0
        missing_focus = []

        for t, years in tickers.items():
            focus_years = [y for y in years if 2018 <= y <= 2025]
            for y in focus_years:
                bctn_fy_focus += 1
                if (t, y) in bctc_firm_years[ex]:
                    matched_fy_focus += 1
                else:
                    missing_focus.append((t, y))

        total_bctn_fy_focus += bctn_fy_focus
        total_matched_fy_focus += matched_fy_focus
        rate = (matched_fy_focus / bctn_fy_focus * 100) if bctn_fy_focus > 0 else 0
        print(f"{ex:<8} | {len(tickers):<8} | {bctn_fy_focus:<16} | {matched_fy_focus:<16} | {rate:>7.2f}%  | {len(missing_focus):<8}")
        if missing_focus and len(missing_focus) <= 10:
            print(f"   -> Danh sách khuyết {ex}: {missing_focus}")
        elif missing_focus:
            print(f"   -> Danh sách khuyết {ex} ({len(missing_focus)} cặp): {missing_focus[:10]}...")

    tot_rate = (total_matched_fy_focus / total_bctn_fy_focus * 100) if total_bctn_fy_focus > 0 else 0
    print("-" * 75)
    print(f"{'TỔNG':<8} | {'—':<8} | {total_bctn_fy_focus:<16} | {total_matched_fy_focus:<16} | {tot_rate:>7.2f}%  | {total_bctn_fy_focus - total_matched_fy_focus:<8}")

    # 4. Kiểm tra tính cân đối kế toán (Tổng Tài sản = Nợ phải trả + Vốn CSH)
    print("\n3. KIỂM TOÁN TÍNH CÂN ĐỐI KẾ TOÁN (Assets == Liabilities + Equity):")
    for ex in ["HSX", "HNX", "UPCOM"]:
        bs_path = bctc_dir / "balance_sheet" / f"{ex}.parquet"
        if not bs_path.exists(): continue
        df = pd.read_parquet(bs_path)
        
        piv = df.pivot_table(index=["ticker", "year"], columns="item_code", values="value", aggfunc="first")
        
        balanced_count = 0
        tested_count = 0
        
        for target_pair in piv.index:
            row = piv.loc[target_pair]
            tot_assets = row.get("bs_tong_cong_tai_san", np.nan)
            if np.isnan(tot_assets):
                tot_assets = row.get("bs_tong_tai_san", np.nan)

            tot_resources = row.get("bs_tong_cong_nguon_von", np.nan)
            liabilities = row.get("bs_tong_no_phai_tra", np.nan)
            if np.isnan(liabilities):
                liabilities = row.get("bs_no_phai_tra", np.nan)

            equity = row.get("bs_tong_von_chu_so_huu", np.nan)
            if np.isnan(equity):
                equity = row.get("bs_von_chu_so_huu", np.nan)
            
            if not np.isnan(tot_assets) and not np.isnan(tot_resources) and tot_assets > 0:
                tested_count += 1
                diff = abs(tot_assets - tot_resources)
                if diff < 1.0 or (diff / tot_assets) < 0.001:
                    balanced_count += 1
            elif not np.isnan(liabilities) and not np.isnan(equity) and not np.isnan(tot_assets) and tot_assets > 0:
                tested_count += 1
                diff = abs(tot_assets - (liabilities + equity))
                if diff < 1.0 or (diff / tot_assets) < 0.001:
                    balanced_count += 1
                    
        pct_balanced = (balanced_count / tested_count * 100) if tested_count > 0 else 0
        print(f"  [{ex}] Kiểm tra {tested_count:,} báo cáo có số liệu -> Cân đối chính xác: {balanced_count:,} ({pct_balanced:.2f}%)")

    # 5. Thử nghiệm FinancialDataProvider
    print("\n4. THỬ NGHIỆM TRUY VẤN QUA FINANCIAL DATA PROVIDER:")
    provider = FinancialDataProvider()
    test_tickers = ["SSI", "VNM", "BSR", "ACV", "VEA"]
    for t in test_tickers:
        val_2024 = provider.get_item_value(t, 2024, "total_assets")
        rev_2024 = provider.get_item_value(t, 2024, "revenue")
        net_2024 = provider.get_item_value(t, 2024, "net_income")
        val_str = f"{val_2024:,.0f} đ" if val_2024 is not None else "N/A"
        rev_str = f"{rev_2024:,.0f} đ" if rev_2024 is not None else "N/A"
        net_str = f"{net_2024:,.0f} đ" if net_2024 is not None else "N/A"
        print(f"  - Mã {t} (2024): Tổng Tài Sản = {val_str} | Doanh Thu = {rev_str} | Lợi Nhuận ST = {net_str}")

    print("\n5. THỬ NGHIỆM TẠO PANEL DATA TỰ ĐỘNG (build_panel):")
    panel_df = provider.build_panel(
        tickers=["SSI", "VNM", "BSR", "ACV", "VEA"],
        years=[2022, 2023, 2024],
        variables=["total_assets", "total_equity", "revenue", "net_income"],
        auto_ratios=["roa", "roe", "leverage"]
    )
    print(panel_df.to_string(index=False))

    print("\n=== HOÀN TẤT KIỂM TOÁN ===")

if __name__ == "__main__":
    run_comprehensive_audit()
