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

import fitz  # PyMuPDF
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.request
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

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

    def _detect_gdrive_root(self) -> Optional[Path]:
        for drive_letter in ("H", "I", "G", "D"):
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
    # 1. BỘ LỌC KIỂM TOÁN CHẤT LƯỢNG (AUDIT / BOGUS DETECTION)
    # =========================================================================

    @staticmethod
    def audit_pdf(pdf_path: Path) -> Dict[str, Any]:
        """
        Kiểm tra toàn diện xem file PDF có phải là BCTN thật hay bị cào nhầm văn bản hành chính.
        
        Returns:
            Dict: {
                "is_bogus": bool,
                "pages": int,
                "file_size_kb": float,
                "reason": str,
                "header_sample": str
            }
        """
        if not pdf_path.exists() or pdf_path.stat().st_size < 100:
            return {
                "is_bogus": True,
                "pages": 0,
                "file_size_kb": 0.0,
                "reason": "file_not_found_or_empty",
                "header_sample": "",
            }

        size_kb = round(pdf_path.stat().st_size / 1024, 1)

        try:
            doc = fitz.open(pdf_path)
            pages = len(doc)
            header_sample = ""
            if pages > 0:
                header_sample = doc[0].get_text()[:400].strip()
            doc.close()
        except Exception as e:
            return {
                "is_bogus": True,
                "pages": 0,
                "file_size_kb": size_kb,
                "reason": f"corrupted_pdf: {e}",
                "header_sample": "",
            }

        # Tiêu chí 1: Số trang <= 4 (BCTN thật luôn dài từ 15 đến 200+ trang)
        if pages <= 4:
            return {
                "is_bogus": True,
                "pages": pages,
                "file_size_kb": size_kb,
                "reason": f"too_few_pages (chỉ có {pages} trang, thường là công văn/thông báo)",
                "header_sample": header_sample,
            }

        # Tiêu chí 2: Dung lượng quá nhỏ < 300KB và trang <= 6
        if size_kb < 300 and pages <= 6:
            return {
                "is_bogus": True,
                "pages": pages,
                "file_size_kb": size_kb,
                "reason": f"suspicious_small_file ({size_kb} KB, {pages} trang)",
                "header_sample": header_sample,
            }

        # Tiêu chí 3: Dấu hiệu công văn hành chính ở trang đầu kết thúc sớm
        header_lower = header_sample.lower()
        bogus_keywords = ["công văn", "giải trình", "thông báo v/v", "kính gửi: ủy ban chứng khoán", "nghị quyết hđqt"]
        if pages <= 8 and any(k in header_lower for k in bogus_keywords):
            return {
                "is_bogus": True,
                "pages": pages,
                "file_size_kb": size_kb,
                "reason": "administrative_notice_header",
                "header_sample": header_sample,
            }

        return {
            "is_bogus": False,
            "pages": pages,
            "file_size_kb": size_kb,
            "reason": "valid_annual_report",
            "header_sample": header_sample,
        }

    # =========================================================================
    # 2. CÀO BÙ NGUỒN 1: QUAN HỆ CỔ ĐÔNG (IR PORTAL) CHÍNH HÃNG DOANH NGHIỆP
    # =========================================================================

    def fetch_from_ir_portal(self, ticker: str, year: int) -> Optional[bytes]:
        """
        Tìm và tải bản PDF gốc chất lượng cao từ chuyên trang IR của doanh nghiệp.
        """
        info = self._websites_db.get(ticker.upper(), {})
        ir_portal = info.get("ir_portal") or info.get("website")
        if not ir_portal:
            return None

        logger.info(f"ReportHealer: Đang dò BCTN {ticker}/{year} trên IR Portal: {ir_portal}")
        try:
            resp = safe_requests_get(ir_portal, timeout=12)
            if resp.status_code != 200:
                return None

            html = resp.text
            bctn_page_urls = [ir_portal]
            # Proactively thêm các đường dẫn phổ biến của mục Báo cáo thường niên
            website = info.get("website") or ""
            proactive_subpaths = [
                "/bao-cao-thuong-nien", "/annual-report", "/annual-reports", "/bctn",
                "/quan-he-co-dong/bao-cao-thuong-nien", "/quan-he-nha-dau-tu/bao-cao-thuong-nien",
                "/ir/annual-reports", "/ir/annual-report", "/tai-lieu-co-dong",
            ]
            for sub in proactive_subpaths:
                cand = urllib.parse.urljoin(ir_portal.rstrip("/") + "/", sub.lstrip("/"))
                if cand not in bctn_page_urls:
                    bctn_page_urls.append(cand)
                if website:
                    w_cand = urllib.parse.urljoin(website.rstrip("/") + "/", sub.lstrip("/"))
                    if w_cand not in bctn_page_urls:
                        bctn_page_urls.append(w_cand)

            # Tìm thêm link qua thẻ <a> trên trang chủ IR
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"].strip()
                    txt = a.get_text().strip().lower()
                    if any(k in txt for k in ("báo cáo thường niên", "annual report", "bctn")) or \
                       any(k in href.lower() for k in ("bao-cao-thuong-nien", "annual-report", "bctn")):
                        full_u = urllib.parse.urljoin(ir_portal, href)
                        if full_u not in bctn_page_urls:
                            bctn_page_urls.append(full_u)
            except Exception:
                pass

            # Quét các trang để tìm file PDF của năm đó
            for page_url in bctn_page_urls[:4]:
                try:
                    p_resp = safe_requests_get(page_url, timeout=12)
                    if p_resp.status_code != 200:
                        continue
                    p_html = p_resp.text
                    pdf_candidates = re.findall(r'href=[\'"]([^\'"]+?\.pdf[^\'"]*)[\'"]', p_html, re.IGNORECASE)
                    
                    year_str = str(year)
                    yy_str = year_str[2:]
                    for c_url in pdf_candidates:
                        c_lower = c_url.lower()
                        # Kiểm tra có chứa năm và từ khóa báo cáo thường niên
                        has_year = (year_str in c_lower) or (f"_{yy_str}_" in c_lower) or (f"_{yy_str}cn" in c_lower)
                        if has_year and not any(bad in c_lower for bad in ("ptbv", "sustainability", "bctc", "kiemtoan", "dieule")):
                            full_pdf_url = urllib.parse.urljoin(page_url, c_url)
                            logger.info(f"ReportHealer: Tìm thấy ứng viên IR: {full_pdf_url}")
                            pdf_resp = safe_requests_get(full_pdf_url, timeout=25)
                            if pdf_resp.status_code == 200 and len(pdf_resp.content) > 500_000:
                                # Kiểm tra số trang thực tế
                                try:
                                    t_doc = fitz.open(stream=pdf_resp.content, filetype="pdf")
                                    t_pages = len(t_doc)
                                    t_doc.close()
                                    if t_pages >= 10:
                                        logger.info(f"ReportHealer: BCTN {ticker}/{year} tải thành công từ IR! ({t_pages} trang, {len(pdf_resp.content)//1024} KB)")
                                        return pdf_resp.content
                                except Exception:
                                    pass
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

        # 1. Xác định file hiện tại trong kho Google Drive gap-filler
        target_file: Optional[Path] = None
        if self.gdrive_root:
            target_file = self.gdrive_root / ticker_u / f"{ticker_u}_{year}_BCTN.pdf"

        # Kiểm tra file hiện tại
        if target_file and target_file.exists() and not force:
            audit = self.audit_pdf(target_file)
            res["old_pages"] = audit["pages"]
            if not audit["is_bogus"]:
                res["status"] = "already_healthy"
                res["message"] = f"Báo cáo {ticker_u}/{year} đã chuẩn ({audit['pages']} trang)."
                return res
            logger.warning(f"ReportHealer: Phát hiện file cào lỗi: {target_file.name} - {audit['reason']}")

        # 2. Bắt đầu cào bù từ các nguồn
        pdf_bytes = None
        healed_source = ""

        # Ưu tiên 1: IR Portal chính thức của doanh nghiệp
        pdf_bytes = self.fetch_from_ir_portal(ticker_u, year)
        if pdf_bytes:
            healed_source = "official_ir_portal"

        # Ưu tiên 2: CafeF CDN 30+ patterns
        if not pdf_bytes:
            pdf_bytes = self.fetch_from_cafef_cdn(ticker_u, year)
            if pdf_bytes:
                healed_source = "cafef_cdn_patterns"

        # 3. Ghi đè file chuẩn nếu tìm thấy
        if pdf_bytes and len(pdf_bytes) > 200_000:
            try:
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                new_pages = len(doc)
                doc.close()

                if new_pages > res["old_pages"] and new_pages >= 8:
                    if target_file:
                        target_file.parent.mkdir(parents=True, exist_ok=True)
                        target_file.write_bytes(pdf_bytes)
                        logger.info(f"ReportHealer: ĐÃ THAY THẾ FILE THÀNH CÔNG: {target_file} ({new_pages} trang)")

                    # Cập nhật drive_index.json nếu có
                    self._update_drive_index(ticker_u, year, len(pdf_bytes))

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

    def _update_drive_index(self, ticker: str, year: int, file_size: int):
        """Cập nhật dung lượng mới vào data/gap_filler/drive_index.json."""
        if not DRIVE_INDEX_PATH.exists():
            return
        try:
            d = json.loads(DRIVE_INDEX_PATH.read_text(encoding="utf-8"))
            k = f"{ticker}_{year}"
            if k in d:
                d[k]["file_size"] = file_size
                DRIVE_INDEX_PATH.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.debug(f"Could not update drive_index.json: {e}")
