# -*- coding: utf-8 -*-
"""
arminer.data.report_healer
==========================
Module tự động kiểm toán chất lượng (Audit) và phục hồi/cào lại (Self-Healing)
các file Báo cáo Thường niên bị cào nhầm (như các file công văn, giải trình 1-2 trang).

Các nguồn cào bù chuẩn:
1. Chuyên trang Quan hệ Cổ đông (IR Portal) chính thức của 1.581 doanh nghiệp niêm yết
2. CafeF Media CDN (30+ URL patterns chuyên sâu từ blockchain_pipeline)
3. Vietstock Corporate Documents
"""

from __future__ import annotations

import io
try:
    import pymupdf as fitz
except ImportError:
    import fitz
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple
import zipfile

from loguru import logger
import requests

from arminer.data.news_scraper import DEFAULT_HEADERS, safe_requests_get, get_shared_session

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
WEBSITES_DB_PATH = FIXTURES_DIR / "company_websites.json"
DRIVE_INDEX_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "gap_filler" / "drive_index.json"

CAFEF_CDN_BASE = "https://cafef1.mediacdn.vn/Images/Uploaded/DuLieuDownload"
CAFEF_CDN_FALLBACKS = [
    "https://cafefnew.mediacdn.vn/Images/Uploaded/DuLieuDownload",
    "https://cafef.mediacdn.vn/Images/Uploaded/DuLieuDownload",
]


class ReportHealer:
    """
    Hệ thống kiểm toán chất lượng và cào bù BCTN chuẩn xác.
    """

    def __init__(self, gdrive_root: Optional[Path] = None):
        self.session = get_shared_session()
        self.gdrive_root = gdrive_root or self._detect_gdrive_root()
        self._websites_db: Dict[str, Any] = {}
        self._load_websites_db()
        self._vietstock_token: Optional[str] = None
        self._vietstock_token_time: float = 0.0

    def _detect_gdrive_root(self) -> Optional[Path]:
        avail = {d[0].upper() for d in os.listdrives()} if hasattr(os, "listdrives") else {"C", "D", "E", "F", "G", "H"}
        for drive_letter in ("H", "I", "G", "D"):
            if drive_letter not in avail:
                continue
            p = Path(f"{drive_letter}:\\My Drive\\arminer_bctn_gap")
            if p.exists() and p.is_dir():
                return p
        colab_p = Path("/content/drive/MyDrive/arminer_bctn_gap")
        if colab_p.exists():
            return colab_p
        return None

    def _load_websites_db(self):
        if WEBSITES_DB_PATH.exists():
            try:
                self._websites_db = json.loads(WEBSITES_DB_PATH.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Could not load websites DB: {e}")

    # =========================================================================
    # 0. NGUỒN VIETSTOCK: KHO LƯU TRỮ VĂN BẢN NIÊM YẾT CHÍNH THỐNG (HOSE & HNX)
    # =========================================================================

    _token_lock = threading.Lock()

    def _ensure_vietstock_token(self) -> str:
        with self._token_lock:
            now = time.time()
            if self._vietstock_token and (now - self._vietstock_token_time < 300):
                return self._vietstock_token
            try:
                from bs4 import BeautifulSoup
                headers = {
                    "User-Agent": DEFAULT_HEADERS["User-Agent"],
                    "Referer": "https://finance.vietstock.vn/STB/tai-lieu/bao-cao-thuong-nien.htm",
                }
                r0 = self.session.get("https://finance.vietstock.vn/STB/tai-lieu/bao-cao-thuong-nien.htm", headers=headers, timeout=12)
                soup = BeautifulSoup(r0.text, "html.parser")
                t_tag = soup.find("input", {"name": "__RequestVerificationToken"})
                if t_tag and t_tag.get("value"):
                    self._vietstock_token = t_tag["value"]
                    self._vietstock_token_time = now
                    logger.info(f"ReportHealer: Đã cấp mới verification token Vietstock ({self._vietstock_token[:15]}...)")
                    return self._vietstock_token
            except Exception as e:
                logger.debug(f"ReportHealer: Không thể lấy token Vietstock: {e}")
            return self._vietstock_token or ""

    def fetch_from_vietstock(self, ticker: str, year: int) -> Optional[bytes]:
        """
        Tìm và tải bản BCTN gốc từ kho dữ liệu niêm yết chính thống Vietstock (HOSE & HNX).
        Tự động bóc tách các file nén (.zip, .rar, .7z) và trích xuất PDF báo cáo thường niên đầy đủ nhất.
        """
        from arminer.data.bctn_validator import is_valid_bctn_file

        ticker_u = ticker.upper()
        year_str = str(year)
        token = self._ensure_vietstock_token()

        payload = {
            "code": ticker_u,
            "type": "2",  # 2 = Báo cáo thường niên (BCTN)
            "page": 1,
            "pageSize": 50,
        }
        if token:
            payload["__RequestVerificationToken"] = token

        headers = {
            "User-Agent": DEFAULT_HEADERS["User-Agent"],
            "Referer": f"https://finance.vietstock.vn/{ticker_u}/tai-lieu/bao-cao-thuong-nien.htm",
            "X-Requested-With": "XMLHttpRequest",
        }

        try:
            r = self.session.post("https://finance.vietstock.vn/data/getdocument", data=payload, headers=headers, timeout=12)
            if r.status_code != 200:
                return None
            raw_text = r.content.decode("utf-8-sig", errors="replace").strip()
            items = json.loads(raw_text)
            if not isinstance(items, list):
                return None
        except Exception as e:
            logger.debug(f"ReportHealer: Lỗi truy vấn Vietstock cho {ticker_u}: {e}")
            return None

        candidates = []
        for it in items:
            title = it.get("Title", "") or ""
            url = it.get("Url", "") or it.get("FileUrl", "") or ""
            comb = (title + " " + url).lower()

            matched_year = False
            if f"năm {year_str}" in comb or f" {year_str}" in comb or f"_{year_str}" in comb or f"/{year_str}/" in comb or f"-{year_str}" in comb:
                matched_year = True

            if matched_year:
                candidates.append((title, url))

        logger.info(f"ReportHealer: Tìm thấy {len(candidates)} ứng viên Vietstock cho {ticker_u}/{year}")

        for title, url in candidates:
            if not url or not url.startswith("http"):
                continue
            try:
                resp = self.session.get(url, headers={"User-Agent": DEFAULT_HEADERS["User-Agent"]}, stream=True, timeout=30)
                if resp.status_code != 200:
                    continue
                content = resp.content
                if len(content) < 100_000:
                    continue

                url_low = url.lower()
                # 1. Trực tiếp PDF
                if url_low.endswith(".pdf") or b"%PDF" in content[:1024]:
                    if is_valid_bctn_file(content):
                        logger.info(f"ReportHealer: Tải thành công BCTN trực tiếp Vietstock: {ticker_u}/{year} ({len(content)//1024} KB)")
                        return content

                # 2. File nén ZIP
                elif url_low.endswith(".zip") or content[:4] == b"PK\x03\x04":
                    try:
                        zf = zipfile.ZipFile(io.BytesIO(content))
                        pdf_entries = [f for f in zf.infolist() if f.filename.lower().endswith(".pdf")]
                        pdf_entries.sort(key=lambda x: x.file_size, reverse=True)
                        for entry in pdf_entries:
                            pdf_bytes = zf.read(entry)
                            if is_valid_bctn_file(pdf_bytes):
                                logger.info(f"ReportHealer: Bóc tách thành công BCTN từ ZIP Vietstock: {ticker_u}/{year} - {entry.filename} ({len(pdf_bytes)//1024} KB)")
                                return pdf_bytes
                    except Exception as ze:
                        logger.debug(f"ReportHealer zip extract error: {ze}")

                # 3. File nén RAR / 7Z
                elif url_low.endswith((".rar", ".7z")):
                    with tempfile.TemporaryDirectory() as tmp_dir:
                        tmp_archive = Path(tmp_dir) / f"archive_{ticker_u}_{year}"
                        tmp_archive.write_bytes(content)
                        extract_dir = Path(tmp_dir) / "extracted"
                        extract_dir.mkdir(exist_ok=True)

                        proc = subprocess.run(["tar", "-xf", str(tmp_archive), "-C", str(extract_dir)], capture_output=True, text=True)
                        if proc.returncode == 0:
                            extracted_pdfs = list(extract_dir.rglob("*.pdf"))
                            extracted_pdfs.sort(key=lambda p: p.stat().st_size, reverse=True)
                            for ep in extracted_pdfs:
                                if is_valid_bctn_file(ep):
                                    logger.info(f"ReportHealer: Bóc tách thành công BCTN từ RAR/7Z Vietstock: {ticker_u}/{year} - {ep.name} ({ep.stat().st_size//1024} KB)")
                                    return ep.read_bytes()
            except Exception as e:
                logger.debug(f"ReportHealer: Lỗi tải ứng viên Vietstock {url}: {e}")

        return None

    # =========================================================================
    # 1. BỘ LỌC KIỂM TOÁN CHẤT LƯỢNG (AUDIT / BOGUS DETECTION)
    # =========================================================================

    @staticmethod
    def audit_pdf(pdf_path: Path) -> Dict[str, Any]:
        """
        Kiểm tra toàn diện xem file PDF có phải là BCTN thật hay bị cào nhầm văn bản hành chính.
        """
        from arminer.data.bctn_validator import audit_bctn_file
        res = audit_bctn_file(pdf_path)
        return {
            "is_bogus": not res["is_valid"],
            "pages": res["pages"],
            "file_size_kb": res["file_size_kb"],
            "reason": res["reason"],
            "header_sample": res["title_sample"],
        }

    # =========================================================================
    # 2. CÀO BÙ NGUỒN 1: QUAN HỆ CỔ ĐÔNG (IR PORTAL) CHÍNH HÃNG DOANH NGHIỆP
    # =========================================================================

    def fetch_from_ir_portal(self, ticker: str, year: int) -> Optional[bytes]:
        """
        Tìm và tải bản PDF gốc chất lượng cao từ chuyên trang IR của doanh nghiệp.
        """
        from arminer.data.bctn_validator import is_valid_bctn_file

        info = self._websites_db.get(ticker.upper(), {})
        ir_portal = info.get("ir_portal") or info.get("website")
        if not ir_portal:
            return None

        # Clean/quote unicode URLs
        def _normalize_url(u: str) -> str:
            p_parts = urllib.parse.urlsplit(u)
            quoted_path = urllib.parse.quote(p_parts.path)
            return urllib.parse.urlunsplit((p_parts.scheme, p_parts.netloc, quoted_path, p_parts.query, p_parts.fragment))

        ir_portal_norm = _normalize_url(ir_portal)
        logger.info(f"ReportHealer: Đang dò BCTN {ticker}/{year} trên IR Portal: {ir_portal_norm}")

        try:
            resp = safe_requests_get(ir_portal_norm, timeout=12)
            html = resp.text if (resp and resp.status_code == 200) else ""

            bctn_page_urls = [ir_portal_norm]
            website = info.get("website") or ""

            proactive_subpaths = [
                "/quan-he-nha-dau-tu/bao-cao-thuong-nien.html",
                "/quan-he-nha-dau-tu/bao-cao-thuong-nien",
                "/bao-cao-thuong-nien.htm",
                "/bao-cao-thuong-nien.html",
                "/bao-cao-thuong-nien",
                "/annual-report",
                "/annual-reports",
                "/shareholder/annual-report",
                "/shareholder/annual-reports",
                "/shareholder/bao-cao-thuong-nien",
                "/vi/quan-he-co-dong/bao-cao-thuong-nien.html",
                "/vi/quan-he-co-dong/bao-cao-thuong-nien",
                "/vi/quan-he-nha-dau-tu/bao-cao-thuong-nien",
                "/vi/quan-he-co-dong/tai-lieu-co-dong",
                "/vi/bao-cao-thuong-nien.html",
                "/nha-dau-tu/bao-cao-thuong-nien.html",
                "/nha-dau-tu/bao-cao-thuong-nien",
                "/bctn",
                "/quan-he-co-dong/bao-cao-thuong-nien",
                "/tai-lieu-co-dong",
                "/quan-he-co-%C4%91ong/tai-lieu-co-%C4%91ong",
            ]
            for sub in proactive_subpaths:
                cand = urllib.parse.urljoin(ir_portal_norm.rstrip("/") + "/", sub.lstrip("/"))
                if cand not in bctn_page_urls:
                    bctn_page_urls.append(cand)
                if website:
                    w_norm = _normalize_url(website)
                    w_cand = urllib.parse.urljoin(w_norm.rstrip("/") + "/", sub.lstrip("/"))
                    if w_cand not in bctn_page_urls:
                        bctn_page_urls.append(w_cand)

            # Proactively thêm link lọc theo năm nếu portal hỗ trợ
            bctn_page_urls.append(f"{ir_portal_norm}?year={year}")
            bctn_page_urls.append(f"{ir_portal_norm}/{year}")

            # Khám phá thêm link từ thẻ <a>
            if html:
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(html, "html.parser")
                    for a in soup.find_all("a", href=True):
                        href = a["href"].strip()
                        txt = a.get_text().strip().lower()
                        if any(k in txt for k in ("báo cáo thường niên", "annual report", "bctn")) or \
                           any(k in href.lower() for k in ("bao-cao-thuong-nien", "annual-report", "bctn")):
                            full_u = urllib.parse.urljoin(ir_portal_norm, href)
                            if full_u not in bctn_page_urls:
                                bctn_page_urls.append(_normalize_url(full_u))
                except Exception:
                    pass

            year_str = str(year)
            yy_str = year_str[2:]

            for page_url in bctn_page_urls[:8]:
                try:
                    p_resp = safe_requests_get(page_url, timeout=12)
                    if not p_resp or p_resp.status_code != 200:
                        continue
                    p_html = p_resp.text

                    # 1. Tìm các thẻ <a> trực tiếp bằng BeautifulSoup
                    from bs4 import BeautifulSoup
                    p_soup = BeautifulSoup(p_html, "html.parser")
                    candidate_links = []
                    detail_links = []

                    for a in p_soup.find_all("a", href=True):
                        href = a["href"].strip()
                        txt = a.get_text().strip()
                        comb = (txt + " " + href).lower()

                        has_yr = (year_str in comb) or (f"_{yy_str}_" in comb) or (f"-{yy_str}-" in comb) or (f"_{yy_str}cn" in comb)
                        is_bctn = any(k in comb for k in ("báo cáo thường niên", "bctn", "annual report", "ar", "annual_report"))

                        if has_yr and not any(bad in comb for bad in ("ptbv", "sustainability", "bctc", "kiemtoan", "dieule", "chữ ký số")):
                            full_cand = urllib.parse.urljoin(page_url, href)
                            if ".pdf" in href.lower() or "documentdownload" in href.lower() or "download" in href.lower():
                                candidate_links.append(full_cand)
                            elif is_bctn or ("year=" in href.lower() or "?year" in href.lower() or ".htm" in href.lower() or "article" in href.lower() or "detail" in href.lower()):
                                detail_links.append(full_cand)

                    # Duyệt các link chi tiết để tìm file PDF nhúng bên trong
                    for d_url in detail_links[:2]:
                        try:
                            d_resp = safe_requests_get(d_url, timeout=10)
                            if d_resp and d_resp.status_code == 200:
                                d_soup = BeautifulSoup(d_resp.text, "html.parser")
                                for da in d_soup.find_all("a", href=True):
                                    dh = da["href"].strip()
                                    if ".pdf" in dh.lower() or "documentdownload" in dh.lower():
                                        candidate_links.append(urllib.parse.urljoin(d_url, dh))
                        except Exception:
                            pass

                    # 2. Quét regex bổ sung cho link PDF
                    pdf_candidates = re.findall(r'href=[\'"]([^\'"]+?\.pdf[^\'"]*)[\'"]', p_html, re.IGNORECASE)
                    for c_url in pdf_candidates:
                        c_lower = c_url.lower()
                        has_year = (year_str in c_lower) or (f"_{yy_str}_" in c_lower) or (f"_{yy_str}cn" in c_lower)
                        if has_year and not any(bad in c_lower for bad in ("ptbv", "sustainability", "bctc", "kiemtoan", "dieule")):
                            candidate_links.append(urllib.parse.urljoin(page_url, c_url))

                    # Thử tải và kiểm định từng ứng viên
                    seen_urls = set()
                    for full_pdf_url in candidate_links:
                        norm_pdf_url = _normalize_url(full_pdf_url)
                        if norm_pdf_url in seen_urls:
                            continue
                        seen_urls.add(norm_pdf_url)

                        logger.info(f"ReportHealer: Thử tải ứng viên IR: {norm_pdf_url}")
                        pdf_resp = safe_requests_get(norm_pdf_url, timeout=30)
                        if pdf_resp and pdf_resp.status_code == 200 and len(pdf_resp.content) > 300_000:
                            if is_valid_bctn_file(pdf_resp.content):
                                t_doc = fitz.open(stream=pdf_resp.content, filetype="pdf")
                                t_pages = len(t_doc)
                                t_doc.close()
                                logger.info(f"ReportHealer: BCTN {ticker}/{year} TẢI THÀNH CÔNG TỪ IR! ({t_pages} trang, {len(pdf_resp.content)//1024} KB)")
                                return pdf_resp.content

                except Exception as e:
                    logger.debug(f"ReportHealer IR page error: {e}")

        except Exception as e:
            logger.debug(f"ReportHealer IR failed for {ticker}: {e}")

        return None

    # =========================================================================
    # 3. CÀO BÙ NGUỒN 2: CAFEF CDN 30+ PATTERNS (BLOCKCHAIN_PIPELINE)
    # =========================================================================

    def _generate_cafef_patterns(self, ticker: str, year: int) -> List[str]:
        """Sinh 30+ URL patterns từ cấu trúc lưu trữ CafeF CDN."""
        yy = str(year)[2:]
        yyyy = str(year)
        t = ticker.upper()
        t_low = ticker.lower()

        urls = []
        cn_vars = ["CN", "Cn", "cn", "NC", "Nc", "nc"]

        for cn in cn_vars:
            urls.extend([
                f"{CAFEF_CDN_BASE}/BCTC/{t}_{yy}{cn}_BCTN.pdf",
                f"{CAFEF_CDN_BASE}/BCTC/{t}_{yy}_{cn}_BCTN.pdf",
                f"{CAFEF_CDN_BASE}/{yyyy}/{t}_{yy}{cn}_BCTN.pdf",
                f"{CAFEF_CDN_BASE}/BCTC/{t}_{yy}{cn}_BaoCaoThuongNien.pdf",
                f"{CAFEF_CDN_BASE}/BaoCaoThuongNien/{t}_{yy}{cn}_BCTN.pdf",
            ])
            for fb in CAFEF_CDN_FALLBACKS:
                urls.extend([
                    f"{fb}/BCTC/{t}_{yy}{cn}_BCTN.pdf",
                    f"{fb}/{yyyy}/{t}_{yy}{cn}_BCTN.pdf",
                ])

        urls.extend([
            f"{CAFEF_CDN_BASE}/BCTC/{t}_BCTN_{yyyy}.pdf",
            f"{CAFEF_CDN_BASE}/BCTC/{t}_BCTN{yyyy}.pdf",
            f"{CAFEF_CDN_BASE}/BCTC/{t}_BaoCaoThuongNien_{yyyy}.pdf",
            f"{CAFEF_CDN_BASE}/BCTC/{t}_{yyyy}_BCTN.pdf",
            f"{CAFEF_CDN_BASE}/BCTC/{t}_{yyyy}.pdf",
            f"{CAFEF_CDN_BASE}/BCTC/BCTN_{t}_{yyyy}.pdf",
            f"{CAFEF_CDN_BASE}/BCTC/{t}_Annual_Report_{yyyy}.pdf",
            f"{CAFEF_CDN_BASE}/{yyyy}/{t}_BCTN_{yyyy}.pdf",
            f"{CAFEF_CDN_BASE}/{yyyy}/{t}_{yyyy}_BCTN.pdf",
            f"{CAFEF_CDN_BASE}/BaoCaoThuongNien/{t}_BCTN_{yyyy}.pdf",
            f"{CAFEF_CDN_BASE}/BaoCaoThuongNien/{t}_{yyyy}.pdf",
            f"{CAFEF_CDN_BASE}/BCTC/{t_low}_{yy}cn_bctn.pdf",
            f"{CAFEF_CDN_BASE}/BCTC/{t_low}_bctn_{yyyy}.pdf",
        ])

        return urls

    def fetch_from_cafef_cdn(self, ticker: str, year: int) -> Optional[bytes]:
        """Thử tải từ CafeF CDN theo 30+ URL patterns với kiểm tra số trang > 5."""
        urls = self._generate_cafef_patterns(ticker, year)
        for u in urls:
            try:
                resp = safe_requests_get(u, timeout=8)
                if resp.status_code == 200 and len(resp.content) > 300_000:
                    try:
                        doc = fitz.open(stream=resp.content, filetype="pdf")
                        pages = len(doc)
                        doc.close()
                        if pages >= 10:
                            logger.info(f"ReportHealer: CafeF CDN hit: {u} ({pages} trang, {len(resp.content)//1024} KB)")
                            return resp.content
                    except Exception:
                        pass
            except Exception:
                continue
        return None

    # =========================================================================
    # 4. HÀM TỔNG HỢP: TỰ ĐỘNG PHỤC HỒI & THAY THẾ (HEAL AND REPLACE)
    # =========================================================================

    def heal_report(self, ticker: str, year: int, force: bool = False) -> Dict[str, Any]:
        """
        Kiểm tra và tự động phục hồi báo cáo thường niên cho một mã và năm cụ thể.
        Nếu file hiện tại bị cào sai (<= 4 trang), tìm file chuẩn từ IR / CafeF và ghi đè.
        """
        ticker_u = ticker.upper()
        res = {
            "ticker": ticker_u,
            "year": year,
            "status": "unchanged",
            "old_pages": 0,
            "new_pages": 0,
            "source": "",
            "message": "",
        }

        # 1. Xác định file hiện tại trong kho Google Drive gap-filler & local cache
        ws_root = Path(__file__).resolve().parent.parent.parent.parent
        local_target = ws_root / "data" / "zenodo_cache" / "gap_filler" / ticker_u / f"{ticker_u}_{year}_BCTN.pdf"
        target_file: Optional[Path] = None
        if self.gdrive_root:
            target_file = self.gdrive_root / ticker_u / f"{ticker_u}_{year}_BCTN.pdf"

        # Kiểm tra file hiện tại: nếu 1 trong các file đã chuẩn BCTN (>= 8 trang) thì already_healthy
        for probe_p in (local_target, target_file):
            if probe_p and probe_p.exists() and not force:
                audit = self.audit_pdf(probe_p)
                res["old_pages"] = max(res["old_pages"], audit["pages"])
                if not audit["is_bogus"] and audit["pages"] >= 8:
                    res["status"] = "already_healthy"
                    res["message"] = f"Báo cáo {ticker_u}/{year} đã chuẩn ({audit['pages']} trang)."
                    return res

        if target_file and target_file.exists():
            logger.warning(f"ReportHealer: Phát hiện file cào lỗi trên Google Drive: {target_file.name} (chỉ có {res['old_pages']} trang)")
        if local_target.exists():
            logger.warning(f"ReportHealer: Phát hiện file cào lỗi trong local cache: {local_target.name}")

        # 2. Bắt đầu cào bù từ các nguồn dữ liệu chất lượng cao
        pdf_bytes = None
        healed_source = ""

        # Ưu tiên 1: Kho văn bản niêm yết chính thống Vietstock (HOSE & HNX)
        try:
            pdf_bytes = self.fetch_from_vietstock(ticker_u, year)
            if pdf_bytes:
                healed_source = "vietstock_corporate_depository"
        except Exception as e_vs:
            logger.debug(f"ReportHealer: Lỗi Vietstock cho {ticker_u}/{year}: {e_vs}")

        # Ưu tiên 2: IR Portal chính thức của doanh nghiệp
        if not pdf_bytes:
            try:
                pdf_bytes = self.fetch_from_ir_portal(ticker_u, year)
                if pdf_bytes:
                    healed_source = "official_ir_portal"
            except Exception as e_ir:
                logger.debug(f"ReportHealer: Lỗi IR Portal cho {ticker_u}/{year}: {e_ir}")

        # Ưu tiên 3: CafeF CDN 30+ patterns
        if not pdf_bytes:
            try:
                pdf_bytes = self.fetch_from_cafef_cdn(ticker_u, year)
                if pdf_bytes:
                    healed_source = "cafef_cdn_patterns"
            except Exception as e_cf:
                logger.debug(f"ReportHealer: Lỗi CafeF cho {ticker_u}/{year}: {e_cf}")

        # 3. Ghi đè file chuẩn nếu tìm thấy
        if pdf_bytes and len(pdf_bytes) > 200_000:
            try:
                from arminer.data.bctn_validator import is_valid_bctn_file
                if is_valid_bctn_file(pdf_bytes):
                    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                    new_pages = len(doc)
                    doc.close()

                    # Ghi vào local cache trước
                    local_target.parent.mkdir(parents=True, exist_ok=True)
                    local_target.write_bytes(pdf_bytes)
                    logger.info(f"ReportHealer: ĐÃ LƯU BCTN CHUẨN VÀO LOCAL CACHE: {local_target} ({new_pages} trang)")

                    # Ghi vào Google Drive nếu có
                    if target_file:
                        try:
                            target_file.parent.mkdir(parents=True, exist_ok=True)
                            target_file.write_bytes(pdf_bytes)
                            logger.info(f"ReportHealer: ĐÃ LƯU BCTN CHUẨN VÀO GOOGLE DRIVE: {target_file} ({new_pages} trang)")
                        except Exception as e_drv:
                            logger.warning(f"Could not write to Google Drive: {e_drv}")

                    # Cập nhật drive_index.json nếu có
                    self._update_drive_index(ticker_u, year, len(pdf_bytes), new_pages)

                    # Dọn dẹp file rác bogus trong .trash_bogus_notices nếu có
                    if self.gdrive_root:
                        trash_dir = self.gdrive_root / ".trash_bogus_notices"
                        if trash_dir.exists():
                            for trash_f in trash_dir.glob(f"{ticker_u}_{year}_BCTN*.pdf"):
                                try:
                                    trash_f.unlink()
                                    logger.info(f"ReportHealer: Đã dọn file bogus cũ khỏi trash: {trash_f.name}")
                                except Exception:
                                    pass

                    res["status"] = "healed"
                    res["new_pages"] = new_pages
                    res["source"] = healed_source
                    res["message"] = f"Đã phục hồi thành công từ {healed_source}: {new_pages} trang (trước đó: {res['old_pages']} trang)."
                    return res
            except Exception as e:
                logger.error(f"ReportHealer: Lỗi ghi đè file: {e}")

        res["status"] = "failed"
        res["message"] = f"Không tìm thấy bản thay thế đầy đủ cho {ticker_u}/{year} trên các nguồn dự phòng."
        return res

    def _update_drive_index(self, ticker: str, year: int, file_size: int, pages: int = 0):
        """Cập nhật dung lượng và trạng thái vào data/gap_filler/drive_index.json."""
        if not DRIVE_INDEX_PATH.exists():
            return
        try:
            d = json.loads(DRIVE_INDEX_PATH.read_text(encoding="utf-8"))
            k = f"{ticker}_{year}"
            if k in d:
                d[k]["file_size"] = file_size
                if pages > 0:
                    d[k]["pages"] = pages
                    d[k]["healthy"] = True
            else:
                d[k] = {
                    "file_id": "",
                    "file_name": f"{ticker}_{year}_BCTN.pdf",
                    "file_size": file_size,
                    "pages": pages,
                    "healthy": True,
                    "direct_url": "",
                }
            DRIVE_INDEX_PATH.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.debug(f"Could not update drive_index.json: {e}")
