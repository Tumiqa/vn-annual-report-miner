# -*- coding: utf-8 -*-
"""
scripts/crawl_ir_targets.py
===========================
Bộ cào chuyên sâu BCTN trực tiếp từ Cổng IR Doanh nghiệp và Vietstock
dành cho các mã UPCoM đặc thù.
Mục tiêu: Đạt 100% mã, 100% chuẩn BCTN (kiểm định nghiêm ngặt >= 6 trang).
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Dict, List, Optional
import urllib.parse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bs4 import BeautifulSoup
from loguru import logger
import requests

from arminer.data.bctn_validator import audit_bctn_file, is_valid_bctn_file
from arminer.data.news_scraper import DEFAULT_HEADERS, safe_requests_get, get_shared_session
from arminer.data.report_healer import ReportHealer

GDRIVE_DIR = Path(r"H:\My Drive\arminer_bctn_gap")
DRIVE_INDEX_PATH = Path(__file__).resolve().parent.parent / "data" / "gap_filler" / "drive_index.json"
MANIFEST_PATH = Path(__file__).resolve().parent.parent / "data" / "gap_manifest.csv"

TARGET_PROFILES = {
    "PCB": {
        "name": "Ngân hàng TMCP Đại chúng Việt Nam (PVcomBank)",
        "ir": "https://www.pvcombank.com.vn/quan-he-co-dong",
        "home": "https://www.pvcombank.com.vn",
    },
    "KAI": {
        "name": "CTCP Chứng khoán KAFI",
        "ir": "https://kafi.vn/quan-he-co-dong",
        "home": "https://kafi.vn",
    },
    "UPS": {
        "name": "CTCP Chứng khoán UP",
        "ir": "https://upstock.com.vn/quan-he-co-dong",
        "home": "https://upstock.com.vn",
    },
    "ULG": {
        "name": "CTCP Logistics U&I",
        "ir": "https://www.unilogistics.vn/quan-he-co-dong",
        "home": "https://www.unilogistics.vn",
    },
    "CBV": {
        "name": "CTCP CTCBIO Việt Nam",
        "ir": "https://ctcbio.com.vn/quan-he-co-dong",
        "home": "https://ctcbio.com.vn",
    },
    "GDH": {
        "name": "CTCP Tập đoàn GDC",
        "ir": "https://gdcgroup.vn/quan-he-co-dong",
        "home": "https://gdcgroup.vn",
    },
    "V45": {
        "name": "CTCP Đầu tư và Xây dựng số 45",
        "ir": "http://vinaconex45.vn/quan-he-co-dong",
        "home": "http://vinaconex45.vn",
    },
    "V68": {
        "name": "CTCP Đầu tư Sản xuất và Thương mại Tuấn Anh",
        "ir": "https://tuananh.vn/quan-he-co-dong",
        "home": "https://tuananh.vn",
    },
    "DMH": {
        "name": "CTCP Dược Minh Hải",
        "ir": "http://www.mipharmco.com.vn/quan-he-co-dong",
        "home": "http://www.mipharmco.com.vn",
    },
    "HNC": {
        "name": "CTCP Xi măng Hữu Nghị",
        "ir": "http://www.ximanghuunghi.vn/quan-he-co-dong",
        "home": "http://www.ximanghuunghi.vn",
    },
    "HTS": {
        "name": "CTCP Thép Hương Thịnh",
        "ir": "http://www.thephuongthinh.com.vn/quan-he-co-dong",
        "home": "http://www.thephuongthinh.com.vn",
    },
    "TAH": {
        "name": "CTCP Thương mại Dịch vụ Giấy Thuận An",
        "ir": "https://thuananpaper.com/quan-he-co-dong",
        "home": "https://thuananpaper.com",
    },
    "REN": {
        "name": "CTCP Xây dựng và Đầu tư Khu du lịch Sinh Thái",
        "ir": "http://www.e-zones.com.vn/quan-he-co-dong",
        "home": "http://www.e-zones.com.vn",
    },
}

def crawl_company_ir(ticker: str, profile: Dict[str, str], healer: ReportHealer) -> List[Dict[str, Any]]:
    results = []
    logger.info(f"=== BẮT ĐẦU DÒ BCTN CHO [{ticker}] {profile['name']} ===")

    # Bước 1: Thử Vietstock trước cho các năm 2016-2025
    for year in range(2025, 2015, -1):
        # Kiểm tra xem đã có trong drive chưa
        drive_path = GDRIVE_DIR / ticker / f"{ticker}_{year}_BCTN.pdf"
        if drive_path.exists() and is_valid_bctn_file(drive_path):
            continue

        pdf_bytes = healer.fetch_from_vietstock(ticker, year)
        if pdf_bytes and is_valid_bctn_file(pdf_bytes):
            res = save_bctn_report(ticker, year, pdf_bytes, source=f"Vietstock API")
            if res:
                results.append(res)

    # Bước 2: Dò trên Cổng IR chính thức của Doanh nghiệp
    ir_url = profile.get("ir")
    home_url = profile.get("home")
    if not ir_url and not home_url:
        return results

    pages_to_visit = [ir_url, home_url]
    subpaths = [
        "/bao-cao-thuong-nien", "/annual-report", "/tai-lieu-co-dong",
        "/bao-cao-thuong-nien.html", "/annual-reports", "/quan-he-nha-dau-tu",
        "/cong-bo-thong-tin", "/bao-cao-tai-chinh"
    ]
    for sp in subpaths:
        if ir_url:
            pages_to_visit.append(urllib.parse.urljoin(ir_url.rstrip("/") + "/", sp.lstrip("/")))
        if home_url:
            pages_to_visit.append(urllib.parse.urljoin(home_url.rstrip("/") + "/", sp.lstrip("/")))

    session = get_shared_session()
    pdf_candidates = []

    for page in pages_to_visit[:12]:
        try:
            r = safe_requests_get(page, timeout=8)
            if not r or r.status_code != 200:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                txt = a.get_text().strip()
                comb = (txt + " " + href).lower()
                
                # Điều kiện BCTN
                is_bctn_text = any(k in comb for k in ("báo cáo thường niên", "annual report", "bctn", "báo cáo tổng kết", "bctn-"))
                has_pdf = ".pdf" in href.lower() or "download" in href.lower()
                
                if (is_bctn_text or "bctn" in href.lower()) and has_pdf:
                    full_url = urllib.parse.urljoin(page, href)
                    if full_url not in pdf_candidates:
                        pdf_candidates.append((full_url, txt))
        except Exception:
            pass

    logger.info(f"[{ticker}] Tìm thấy {len(pdf_candidates)} link tài liệu tiềm năng từ cổng IR")
    for link, title in pdf_candidates:
        m = re.search(r'(20\d{2})', title + " " + link)
        year = int(m.group(1)) if m else None
        if not year or year < 2015 or year > 2026:
            continue

        drive_path = GDRIVE_DIR / ticker / f"{ticker}_{year}_BCTN.pdf"
        if drive_path.exists() and is_valid_bctn_file(drive_path):
            continue

        try:
            r_pdf = session.get(link, headers={"User-Agent": DEFAULT_HEADERS["User-Agent"]}, timeout=25)
            if r_pdf.status_code == 200 and len(r_pdf.content) > 50_000:
                audit = audit_bctn_file(r_pdf.content)
                if audit["is_valid"]:
                    res = save_bctn_report(ticker, year, r_pdf.content, source=f"IR Portal ({link})")
                    if res:
                        results.append(res)
                else:
                    logger.warning(f"[{ticker}/{year}] Bỏ qua file vi phạm từ IR: {audit['reason']}")
        except Exception as e:
            logger.debug(f"Lỗi tải {link}: {e}")

    return results

def save_bctn_report(ticker: str, year: int, content: bytes, source: str) -> Optional[Dict[str, Any]]:
    audit = audit_bctn_file(content)
    if not audit["is_valid"]:
        logger.error(f"[{ticker}/{year}] Từ chối lưu: Không đạt chuẩn BCTN ({audit['reason']})")
        return None

    ticker_u = ticker.upper()
    dest_dir = GDRIVE_DIR / ticker_u
    dest_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{ticker_u}_{year}_BCTN.pdf"
    dest_file = dest_dir / fname

    dest_file.write_bytes(content)
    logger.success(f" [THÀNH CÔNG] ĐÃ LƯU BCTN CHUẨN {ticker_u} ({year}): {audit['pages']} trang ({len(content)//1024} KB) từ {source}")

    # Cập nhật drive_index.json
    try:
        drive_map = {}
        if DRIVE_INDEX_PATH.exists():
            drive_map = json.loads(DRIVE_INDEX_PATH.read_text(encoding="utf-8"))
        key = f"{ticker_u}_{year}"
        drive_map[key] = {
            "file_name": fname,
            "file_size": len(content),
            "pages": audit["pages"],
            "source": source,
            "healthy": True
        }
        DRIVE_INDEX_PATH.write_text(json.dumps(drive_map, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Lỗi cập nhật drive_index: {e}")

    # Cập nhật manifest
    try:
        if MANIFEST_PATH.exists():
            with open(MANIFEST_PATH, "a", encoding="utf-8") as mf:
                mf.write(f"\n{ticker_u},{year},{fname},{len(content)},{source},True")
    except Exception:
        pass

    return {
        "ticker": ticker_u,
        "year": year,
        "pages": audit["pages"],
        "size_kb": len(content) // 1024,
        "source": source
    }

def main():
    healer = ReportHealer()
    logger.info("=== BẮT ĐẦU CÀO VÉT BCTN CHUYÊN SÂU CHO NHÓM DOANH NGHIỆP CÒN KHUYẾT ===")
    total_added = 0

    for ticker, profile in TARGET_PROFILES.items():
        res = crawl_company_ir(ticker, profile, healer)
        total_added += len(res)

    logger.info("=" * 60)
    logger.info(f"HOÀN TẤT ĐỢT CÀO VÉT: Bổ sung thành công {total_added} BCTN chuẩn 100%!")
    logger.info("=" * 60)

if __name__ == "__main__":
    main()
