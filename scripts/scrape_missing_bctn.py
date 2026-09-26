# -*- coding: utf-8 -*-
"""
scripts/scrape_missing_bctn.py
===============================
Hệ thống cào và đồng bộ BCTN tự động tối ưu hóa tối đa tỷ lệ tìm thấy (Hit Rate),
kế thừa kiến trúc đa tầng từ blockchain_pipeline/stage2_pdf_scraper.

Các tầng tìm kiếm & thu thập:
  - Tầng 0: Local Sync - Kiểm tra kho lưu trữ blockchain_pipeline/data/raw_pdfs (sao chép tức thì 1ms)
  - Tầng 1: Multi-Pattern CDN Scanner (50+ URL patterns bao gồm bí danh DN, lệch năm công bố Y+1, đa luồng)
  - Tầng 2: HTTP HTML Parser cho các cổng công bố thông tin CafeF (s.cafef.vn & cafef.vn/du-lieu)
  - Tầng 3: Vietstock Finance Document Parser (finance.vietstock.vn)
  - Quản lý trạng thái: Tự động cập nhật data/gap_manifest.csv & data/gap_filler/drive_index.json
  - Lưu trữ: Tự động lưu chuẩn H:\\My Drive\\arminer_bctn_gap\\{TICKER}\\{TICKER}_{YEAR}_BCTN.pdf
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import io
import json
import os
import random
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Đảm bảo console Windows UTF-8 không bị lỗi charmap
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ===========================================================================
# Configuration & Auto-Detection
# ===========================================================================

def detect_gdrive_folder() -> Path:
    """Tự động phát hiện mount point Google Drive for Desktop."""
    env_path = os.environ.get("ARMINER_GDRIVE_PATH")
    if env_path:
        p = Path(env_path)
        p.mkdir(parents=True, exist_ok=True)
        return p

    for letter in ("H", "I", "G", "D", "E"):
        candidate = Path(f"{letter}:\\My Drive\\arminer_bctn_gap")
        if candidate.parent.exists():
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate

    fallback = Path(__file__).resolve().parent.parent / "data" / "gap_filler" / "drive_storage"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


PROJECT_ROOT = Path(__file__).resolve().parent.parent
GAP_MANIFEST = PROJECT_ROOT / "data" / "gap_manifest.csv"
DRIVE_INDEX_FILE = PROJECT_ROOT / "data" / "gap_filler" / "drive_index.json"

# Kho dữ liệu raw_pdfs từ blockchain_pipeline (nếu có trên máy)
BP_RAW_PDFS = PROJECT_ROOT.parent / "blockchain_pipeline" / "data" / "raw_pdfs"

CAFEF_CDN_BASES = [
    "https://cafef1.mediacdn.vn/Images/Uploaded/DuLieuDownload",
    "https://cafefnew.mediacdn.vn/Images/Uploaded/DuLieuDownload",
    "https://cafef.mediacdn.vn/Images/Uploaded/DuLieuDownload",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
]

MIN_PDF_SIZE = 50_000  # 50KB

# Bí danh tên công ty thường gặp trên hệ thống CafeF MediaCDN
COMPANY_ALIASES: Dict[str, List[str]] = {
    "CMG": ["CMC", "CMG"],
    "IDC": ["IDICO", "IDC"],
    "BVB": ["BVBank", "BVB", "VietCapitalBank", "BanVietBank"],
    "VCB": ["Vietcombank", "VCB"],
    "BID": ["BIDV", "BID"],
    "CTG": ["VietinBank", "Vietinbank", "CTG"],
    "MBB": ["MBBank", "MB", "MBB"],
    "TCB": ["Techcombank", "TCB"],
    "VPB": ["VPBank", "VPB"],
    "TPB": ["TPBank", "TienPhongBank", "TPB"],
    "STB": ["Sacombank", "STB"],
    "HDB": ["HDBank", "HDB"],
    "SHB": ["SHB", "SHBank"],
    "LPB": ["LienVietPostBank", "LPBank", "LPB"],
    "SSB": ["SeABank", "SSB"],
    "MSB": ["MSB", "MaritimeBank"],
    "OCB": ["OCB", "PhuongDongBank"],
    "EIB": ["Eximbank", "EIB"],
    "VIB": ["VIB", "QuocTeBank"],
    "ABB": ["AnBinhBank", "ABB"],
    "BAB": ["BacABank", "BAB"],
    "KLB": ["KienLongBank", "KLB"],
    "NAB": ["NamABank", "NAB"],
    "PGB": ["PGBank", "ThinhVuongBank", "PGB"],
    "SGB": ["SaigonBank", "SGB"],
    "VBB": ["VietBank", "VBB"],
    "GAS": ["PVGAS", "GAS"],
    "PLX": ["Petrolimex", "PLX"],
    "POW": ["PVPower", "POW"],
    "PVD": ["PVD", "PVDRILLING", "PVDrilling"],
    "PVS": ["PTSC", "PVS"],
    "GVR": ["VRG", "GVR"],
    "BSR": ["LocHoaDauBinhSon", "BSR"],
    "VND": ["VNDIRECT", "VND"],
    "SSI": ["SSI"],
    "HCM": ["HSC", "HCM"],
    "VCI": ["Vietcap", "VCSC", "VCI"],
}


# ===========================================================================
# Session & Validation Helpers
# ===========================================================================

def create_session() -> requests.Session:
    """Tạo session có retry, connection pool và anti-bot headers."""
    session = requests.Session()
    retry = Retry(
        total=2,
        backoff_factor=0.3,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=25, pool_maxsize=25)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive",
    })
    return session


def is_valid_pdf(filepath: Path) -> bool:
    """Kiểm tra file PDF hợp lệ (dung lượng > 50KB & magic header %PDF-)."""
    if not filepath.exists():
        return False
    if filepath.stat().st_size < MIN_PDF_SIZE:
        return False
    try:
        with open(filepath, "rb") as f:
            header = f.read(5)
            return header == b"%PDF-"
    except Exception:
        return False


def download_pdf(session: requests.Session, url: str, dest_path: Path) -> bool:
    """Tải PDF trực tiếp với streaming chunk và kiểm tra toàn vẹn."""
    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Referer": "https://cafef.vn/",
        }
        with session.get(url, headers=headers, stream=True, timeout=45) as r:
            if r.status_code != 200:
                return False
            ct = r.headers.get("Content-Type", "").lower()
            if "html" in ct and "pdf" not in ct:
                return False

            temp_dest = dest_path.with_suffix(".tmp")
            with open(temp_dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=16384):
                    if chunk:
                        f.write(chunk)

            if is_valid_pdf(temp_dest):
                if dest_path.exists():
                    dest_path.unlink()
                temp_dest.rename(dest_path)
                return True
            else:
                temp_dest.unlink(missing_ok=True)
                return False
    except Exception:
        if dest_path.exists():
            dest_path.unlink(missing_ok=True)
        return False


# ===========================================================================
# CDN Pattern Generator (Mở Rộng Tối Đa Tỷ Lệ Hit)
# ===========================================================================

def generate_cdn_urls(ticker: str, year: int) -> List[str]:
    """Sinh tập hợp đầy đủ URL CDN ứng viên với tất cả biến thể đặt tên CafeF."""
    yy = str(year)[2:]
    yyyy = str(year)
    t_upper = ticker.upper()

    # Danh sách tên cần thử (bao gồm mã CK và các bí danh tên thương hiệu)
    names_to_try = [t_upper]
    if t_upper in COMPANY_ALIASES:
        for alias in COMPANY_ALIASES[t_upper]:
            if alias not in names_to_try:
                names_to_try.append(alias)

    cn_vars = ["CN", "Cn", "cn", "NC", "Nc", "nc", ""]

    urls: List[str] = []

    for name in names_to_try:
        n_up = name.upper()
        n_low = name.lower()

        # Thử cả 3 domain CDN của CafeF
        for b in CAFEF_CDN_BASES:
            # 1. Năm xuất bản đúng = Y
            for cn in cn_vars:
                urls.append(f"{b}/BCTC/{n_up}_{yy}{cn}_BCTN.pdf")
                urls.append(f"{b}/BCTC/{n_up}_{yy}_{cn}_BCTN.pdf")
                urls.append(f"{b}/{yyyy}/{n_up}_{yy}{cn}_BCTN.pdf")
                urls.append(f"{b}/{yyyy}/{n_up}_{yy}_{cn}_BCTN.pdf")
                urls.append(f"{b}/BaoCaoThuongNien/{n_up}_{yy}{cn}_BCTN.pdf")

            # 2. Năm xuất bản trễ 1 năm = Y + 1 (Rất phổ biến vì BCTN năm trước được duyệt vào ĐHCĐ năm sau)
            try:
                next_yy = f"{int(yy) + 1:02d}"
                next_yyyy = str(int(yyyy) + 1)
                for cn in cn_vars:
                    urls.append(f"{b}/BCTC/{n_up}_{next_yy}{cn}_BCTN.pdf")
                    urls.append(f"{b}/BCTC/{n_up}_{next_yy}_{cn}_BCTN.pdf")
                    urls.append(f"{b}/{next_yyyy}/{n_up}_{next_yy}{cn}_BCTN.pdf")
                    urls.append(f"{b}/{next_yyyy}/{n_up}_{next_yy}_{cn}_BCTN.pdf")
                    urls.append(f"{b}/BaoCaoThuongNien/{n_up}_{next_yy}{cn}_BCTN.pdf")
                urls.append(f"{b}/BCTC/{n_up}_{next_yy}_BCTN_{yyyy}.pdf")
                urls.append(f"{b}/BCTC/{n_up}_{next_yy}BCTN_{yyyy}.pdf")
                urls.append(f"{b}/{next_yyyy}/{n_up}_{next_yy}_BCTN_{yyyy}.pdf")
            except Exception:
                pass

            # 3. Các dạng đặt tên theo năm 4 chữ số
            urls.extend([
                f"{b}/BCTC/{n_up}_BCTN_{yyyy}.pdf",
                f"{b}/BCTC/{n_up}_BCTN{yyyy}.pdf",
                f"{b}/BCTC/{n_up}_{yyyy}_BCTN.pdf",
                f"{b}/BCTC/{n_up}_{yyyy}_BaoCaoThuongNien.pdf",
                f"{b}/BCTC/{n_up}_BaoCaoThuongNien_{yyyy}.pdf",
                f"{b}/BCTC/{n_up}_BaoCaoThuongNien{yyyy}.pdf",
                f"{b}/BCTC/BCTN_{n_up}_{yyyy}.pdf",
                f"{b}/BCTC/{n_up}_AnnualReport_{yyyy}.pdf",
                f"{b}/BCTC/{n_up}_Annual_Report_{yyyy}.pdf",
                f"{b}/{yyyy}/{n_up}_BCTN_{yyyy}.pdf",
                f"{b}/{yyyy}/{n_up}_BCTN{yyyy}.pdf",
                f"{b}/{yyyy}/{n_up}_{yyyy}_BCTN.pdf",
                f"{b}/{yyyy}/{n_up}_BaoCaoThuongNien_{yyyy}.pdf",
                f"{b}/{yyyy}/BaoCaoThuongNien_{n_up}.pdf",
                f"{b}/BaoCaoThuongNien/{n_up}_BCTN_{yyyy}.pdf",
                f"{b}/BaoCaoThuongNien/{n_up}_{yyyy}.pdf",
                f"{b}/BaoCaoThuongNien/{n_up}_BaoCaoThuongNien_{yyyy}.pdf",
                # Ký tự gạch nối và chữ thường
                f"{b}/BCTC/{n_low}_{yy}cn_bctn.pdf",
                f"{b}/BCTC/{n_low}_bctn_{yyyy}.pdf",
                f"{b}/BCTC/{n_up}-{yy}CN-BCTN.pdf",
                f"{b}/BCTC/{n_up}-{yyyy}-BCTN.pdf",
                f"{b}/BCTC/{n_up}_BCTN.pdf",
            ])

    # Deduplicate nhưng giữ nguyên thứ tự ưu tiên
    seen = set()
    unique_urls = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)

    return unique_urls


# ===========================================================================
# Supercharged Multi-Layer Scraper Engine
# ===========================================================================

class SuperchargedBCTNScraper:
    """Bộ thu thập BCTN siêu năng suất, tận dụng cả kho offline và online đa tầng."""

    def __init__(self, drive_root: Path):
        self.drive_root = drive_root
        self.session = create_session()

    def check_and_copy_from_blockchain_pipeline(self, ticker: str, year: int, dest_path: Path) -> bool:
        """Tầng 0: Kiểm tra trong kho raw_pdfs của blockchain_pipeline đã cào trước đó."""
        if not BP_RAW_PDFS.exists():
            return False

        # Thử cấu trúc MST_{TICKER}/{YEAR}/annual_report.pdf
        candidate_paths = [
            BP_RAW_PDFS / f"MST_{ticker.upper()}" / str(year) / "annual_report.pdf",
            BP_RAW_PDFS / f"MST_{ticker.upper()}" / str(year) / f"{ticker.upper()}_{year}_BCTN.pdf",
            BP_RAW_PDFS / ticker.upper() / str(year) / "annual_report.pdf",
            BP_RAW_PDFS / ticker.upper() / f"{ticker.upper()}_{year}_BCTN.pdf",
        ]

        for cp in candidate_paths:
            if cp.exists() and is_valid_pdf(cp):
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(cp, dest_path)
                return True
        return False

    def _probe_cdn_url(self, url: str) -> Optional[str]:
        """Kiểm tra nhanh HEAD một URL CDN."""
        try:
            r = self.session.head(url, timeout=3, allow_redirects=True)
            if r.status_code == 200:
                ct = r.headers.get("Content-Type", "").lower()
                cl = int(r.headers.get("Content-Length", 0) or 0)
                if ("pdf" in ct or "octet-stream" in ct or url.endswith(".pdf")) and (cl == 0 or cl > MIN_PDF_SIZE):
                    return url
        except Exception:
            pass
        return None

    def search_and_download_cdn(self, ticker: str, year: int, dest_path: Path) -> bool:
        """Tầng 1: Quét song song MediaCDN 12 luồng (~300ms)."""
        candidate_urls = generate_cdn_urls(ticker, year)

        with ThreadPoolExecutor(max_workers=12) as executor:
            future_to_url = {executor.submit(self._probe_cdn_url, url): url for url in candidate_urls}
            for future in as_completed(future_to_url):
                matched_url = future.result()
                if matched_url:
                    executor.shutdown(wait=False, cancel_futures=True)
                    if download_pdf(self.session, matched_url, dest_path):
                        return True
        return False

    def search_and_download_cafef_docs(self, ticker: str, year: int, dest_path: Path) -> bool:
        """Tầng 2: Quét trang tài liệu và công bố thông tin CafeF."""
        t_up = ticker.upper()
        t_low = ticker.lower()

        doc_urls = [
            f"https://s.cafef.vn/bao-cao-tai-chinh/{t_up}/BaoCaoThuongNien/{year}.chn",
            f"https://s.cafef.vn/tai-lieu/{t_up}/BaoCaoThuongNien.chn",
            f"https://cafef.vn/du-lieu/hose/{t_low}-tai-lieu.chn",
            f"https://cafef.vn/du-lieu/hnx/{t_low}-tai-lieu.chn",
            f"https://cafef.vn/du-lieu/upcom/{t_low}-tai-lieu.chn",
            f"https://cafef.vn/du-lieu/{t_low}-tai-lieu.chn",
        ]

        for page_url in doc_urls:
            try:
                r = self.session.get(page_url, timeout=8, headers={"Referer": "https://cafef.vn/"})
                if r.status_code != 200:
                    continue

                links = re.findall(r'href=["\']([^"\']*\.pdf[^"\']*)["\']', r.text, re.I)
                for href in links:
                    href_l = href.lower()
                    is_bctn = any(kw in href_l for kw in ["bctn", "annual", "thuongnien", "baocaothuongnien"])
                    is_excluded = any(kw in href_l for kw in ["bctc", "soat_xet", "kiem_toan", "bcb", "bdl", "dieuchinh"])
                    if is_bctn and not is_excluded:
                        m = re.search(r'(20\d{2})', href)
                        if not m:
                            m_yy = re.search(r'_(\d{2})(?:CN|NC)_', href, re.I)
                            y_val = 2000 + int(m_yy.group(1)) if m_yy else None
                        else:
                            y_val = int(m.group(1))

                        if y_val == year:
                            full_url = href
                            if full_url.startswith("//"):
                                full_url = "https:" + full_url
                            elif full_url.startswith("/"):
                                full_url = "https://s.cafef.vn" + full_url

                            if download_pdf(self.session, full_url, dest_path):
                                return True
            except Exception:
                continue
        return False

    def search_and_download_vietstock(self, ticker: str, year: int, dest_path: Path) -> bool:
        """Tầng 3: Vietstock Finance fallback."""
        vs_urls = [
            f"https://finance.vietstock.vn/tai-lieu-co-dong/{ticker.upper()}.htm",
            f"https://finance.vietstock.vn/{ticker.upper()}/tai-lieu.htm",
        ]
        for vs_url in vs_urls:
            try:
                r = self.session.get(vs_url, timeout=10, headers={"Referer": "https://finance.vietstock.vn/"})
                if r.status_code == 200:
                    links = re.findall(r'href=["\']([^"\']*\.pdf[^"\']*)["\']', r.text, re.I)
                    for href in links:
                        href_l = href.lower()
                        if any(kw in href_l for kw in ["bctn", "annual", "thuongnien"]):
                            if str(year) in href:
                                full_url = href if href.startswith("http") else f"https://finance.vietstock.vn{href}"
                                if download_pdf(self.session, full_url, dest_path):
                                    return True
            except Exception:
                pass
        return False

    def acquire_report(self, ticker: str, year: int) -> Tuple[bool, str, Optional[Path]]:
        """Điều phối tải BCTN qua 4 tầng, tối đa hóa tỷ lệ tìm thấy."""
        ticker_u = ticker.upper()
        dest_pdf = self.drive_root / ticker_u / f"{ticker_u}_{year}_BCTN.pdf"

        # Nếu đã có trên Google Drive PC
        if is_valid_pdf(dest_pdf):
            return True, "already_exists", dest_pdf

        # Tầng 0: Kiểm tra kho blockchain_pipeline offline
        if self.check_and_copy_from_blockchain_pipeline(ticker_u, year, dest_pdf):
            return True, "blockchain_pipeline", dest_pdf

        # Tầng 1: Multi-pattern MediaCDN
        if self.search_and_download_cdn(ticker_u, year, dest_pdf):
            return True, "cafef_cdn", dest_pdf

        # Tầng 2: HTML Scraping CafeF
        if self.search_and_download_cafef_docs(ticker_u, year, dest_pdf):
            return True, "cafef_doc", dest_pdf

        # Tầng 3: Vietstock fallback
        if self.search_and_download_vietstock(ticker_u, year, dest_pdf):
            return True, "vietstock", dest_pdf

        return False, "not_found", None


# ===========================================================================
# Target Loader & Manifest Update
# ===========================================================================

def load_pending_targets(
    priority: Optional[str] = None,
    tickers: Optional[List[str]] = None,
    years: Optional[List[int]] = None,
    limit: Optional[int] = None,
    include_not_found: bool = True,
) -> pd.DataFrame:
    """Đọc danh sách báo cáo cần tải từ gap_manifest.csv."""
    if not GAP_MANIFEST.exists():
        print(f"❌ Không tìm thấy file {GAP_MANIFEST}")
        sys.exit(1)

    df = pd.read_csv(GAP_MANIFEST, encoding="utf-8-sig")

    # Cho phép retry lại các mục 'not_found' để tăng tỷ lệ tìm kiếm với thuật toán mới
    valid_statuses = ["pending"]
    if include_not_found:
        valid_statuses.append("not_found")

    df = df[df["search_status"].isin(valid_statuses)]

    if priority:
        df = df[df["priority"] == priority]
    if tickers:
        tu = [t.upper() for t in tickers]
        df = df[df["ticker"].str.upper().isin(tu)]
    if years:
        df = df[df["year"].isin(years)]

    priority_map = {"P1": 0, "P2": 1, "P3": 2}
    df["_sort"] = df["priority"].map(priority_map).fillna(9)
    df = df.sort_values(["_sort", "year"], ascending=[True, False]).drop(columns=["_sort"])

    if limit and limit > 0:
        df = df.head(limit)

    return df


def update_target_status(ticker: str, year: int, status: str, source: str = ""):
    """Cập nhật kết quả vào gap_manifest.csv & drive_index.json."""
    try:
        df = pd.read_csv(GAP_MANIFEST, encoding="utf-8-sig")
        df["source"] = df["source"].fillna("").astype(str)
        mask = (df["ticker"].str.upper() == ticker.upper()) & (df["year"] == year)
        if mask.any():
            df.loc[mask, "search_status"] = status
            if source:
                df.loc[mask, "source"] = source
            df.to_csv(GAP_MANIFEST, index=False, encoding="utf-8-sig")
    except Exception as e:
        print(f"  ⚠️  Lỗi cập nhật manifest: {e}")

    if status == "uploaded" and DRIVE_INDEX_FILE.exists():
        try:
            with open(DRIVE_INDEX_FILE, "r", encoding="utf-8") as f:
                idx = json.load(f)
            key = f"{ticker.upper()}_{year}"
            idx[key] = {
                "ticker": ticker.upper(),
                "year": year,
                "status": "ready",
                "source": source,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            with open(DRIVE_INDEX_FILE, "w", encoding="utf-8") as f:
                json.dump(idx, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


# ===========================================================================
# Main Execution CLI
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description="Hệ thống cào & đồng bộ BCTN siêu năng suất lưu Google Drive")
    parser.add_argument("--priority", choices=["P1", "P2", "P3"], default="P1", help="Mức ưu tiên (mặc định: P1)")
    parser.add_argument("--all-priorities", action="store_true", help="Chạy tất cả (P1, P2, P3)")
    parser.add_argument("--ticker", nargs="+", help="Chỉ tải các mã cụ thể (VD: AAA BVB CTD)")
    parser.add_argument("--year", nargs="+", type=int, help="Chỉ tải các năm cụ thể (VD: 2022 2023)")
    parser.add_argument("--limit", type=int, default=150, help="Số lượng tải tối đa trong 1 lượt (mặc định: 150)")
    parser.add_argument("--drive-path", help="Đường dẫn Google Drive chỉ định")
    parser.add_argument("--no-retry-not-found", action="store_true", help="Không thử lại các mục đã đánh dấu not_found")
    args = parser.parse_args()

    drive_path = Path(args.drive_path) if args.drive_path else detect_gdrive_folder()
    drive_path.mkdir(parents=True, exist_ok=True)

    p_filter = None if (args.all_priorities or args.ticker) else args.priority
    targets = load_pending_targets(
        priority=p_filter,
        tickers=args.ticker,
        years=args.year,
        limit=args.limit,
        include_not_found=not args.no_retry_not_found,
    )

    if targets.empty:
        print("=" * 65)
        print("  🎉 Tất cả báo cáo trong danh mục đã được thu thập đầy đủ!")
        print("=" * 65)
        return

    print("=" * 65)
    print("  🚀 ARMINER SUPERCHARGED BCTN SCRAPER — TỐI ƯU HÓA TỶ LỆ TÌM THẤY")
    print("=" * 65)
    print(f"  📊 Tổng số cần xử lý:   {len(targets)} báo cáo")
    print(f"  📁 Thư mục Google Drive: {drive_path}")
    print(f"  🔄 Tích hợp tầng kho:    blockchain_pipeline + CafeF CDN + HTML + Vietstock")
    print(f"  🔍 Thứ tự ưu tiên:      {dict(targets['priority'].value_counts())}")
    print("=" * 65)
    print()

    scraper = SuperchargedBCTNScraper(drive_root=drive_path)
    success_cnt = 0
    not_found_cnt = 0
    already_cnt = 0

    for idx, (_, row) in enumerate(targets.iterrows(), 1):
        ticker = str(row["ticker"]).upper()
        year = int(row["year"])
        company = str(row.get("company_name", ""))[:28]

        print(f"  [{idx:03d}/{len(targets):03d}] {ticker:<5} ({year}) | {company:<30} ...", end=" ", flush=True)

        try:
            ok, source, pdf_path = scraper.acquire_report(ticker, year)

            if ok and pdf_path and is_valid_pdf(pdf_path):
                size_mb = pdf_path.stat().st_size / (1024 * 1024)
                if source == "already_exists":
                    print(f"⚡ Đã có sẵn ({size_mb:.2f} MB)")
                    already_cnt += 1
                elif source == "blockchain_pipeline":
                    print(f"📦 Lấy từ blockchain_pipeline ({size_mb:.2f} MB)")
                    success_cnt += 1
                else:
                    print(f"✅ Tải thành công [{source}] ({size_mb:.2f} MB)")
                    success_cnt += 1
                update_target_status(ticker, year, "uploaded", source)
            else:
                print("❌ Không tìm thấy")
                update_target_status(ticker, year, "not_found")
                not_found_cnt += 1

        except KeyboardInterrupt:
            print("\n\n⚠️  Dừng tiến trình bởi người dùng (Ctrl+C). Tiến độ đã được lưu lại an toàn.")
            break
        except Exception as e:
            print(f"⚠️  Lỗi: {e}")
            update_target_status(ticker, year, "error", str(e)[:40])

        time.sleep(random.uniform(0.2, 0.5))

    print()
    print("=" * 65)
    print(f"  ✅ Tải/đồng bộ thành công: {success_cnt}")
    print(f"  ⚡ Đã có sẵn trên Drive:   {already_cnt}")
    print(f"  ❌ Không tìm thấy:         {not_found_cnt}")
    print(f"  📁 Thư mục lưu trữ:        {drive_path}")
    print("=" * 65)


if __name__ == "__main__":
    main()
