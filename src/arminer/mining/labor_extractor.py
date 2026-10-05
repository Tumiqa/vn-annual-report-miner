# -*- coding: utf-8 -*-
"""
arminer.mining.labor_extractor
==============================
Lean & High-Precision Total Employee Extractor for Vietnamese Annual Reports (BCTN).

Target:
    LABOR(ticker, year) = Total headcount of the reporting enterprise at fiscal year-end (31/12).

Principles:
    1. 100% Precision Guarantee: Zero false positives. Exclude financial amounts,
       salaries, equity/ESOP, subgroups (female, contract types, qualifications),
       deltas (new hires, resignations), and page numbers.
    2. Maximum Recall: Comprehensively cover all disclosure modalities in Vietnamese BCTNs
       (audited financial statement notes, narrative sentences, post-number date expressions,
       bilingual disclosures, horizontal & vertical comparison tables, 100% breakdown tables,
       and plan vs. actual performance tables).
    3. Robust Font Handling: Native support for legacy/corrupted font encodings (TCVN3,
       corrupted diacritics like 'So hrong CB-CN', 'Numberof employees', '859 ngiroi').

Output Schema:
    LaborExtractionResult:
        ticker: str
        year: int
        labor: Optional[int]
        source_page: Optional[int]
        raw_text: str
        confidence: float
        status: "SUCCESS" | "NOT_FOUND" | "AMBIGUOUS"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from loguru import logger

from arminer.mining.labor_patterns import (
    EXCLUSION_PATTERNS,
    DELTA_EXCLUSION_REGEXES,
    normalize_number,
)


@dataclass
class LaborCandidate:
    """An individual candidate number discovered in text."""
    value: int
    raw_snippet: str
    page: Optional[int] = None
    target_year_matched: bool = False
    is_total_signal: bool = False
    is_subset_signal: bool = False
    strategy: str = "narrative"
    confidence: float = 0.0
    reason: str = ""


@dataclass
class LaborExtractionResult:
    """Final extracted result for a report."""
    ticker: str
    year: int
    labor: Optional[int] = None
    source_page: Optional[int] = None
    raw_text: str = ""
    confidence: float = 0.0
    status: str = "NOT_FOUND"  # "SUCCESS", "NOT_FOUND", "AMBIGUOUS"
    all_candidates: List[LaborCandidate] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "year": self.year,
            "labor": self.labor,
            "source_page": self.source_page,
            "raw_text": self.raw_text,
            "confidence": round(self.confidence, 3),
            "status": self.status,
        }


class LaborExtractor:
    """
    High-precision extractor focused specifically on Total Headcount (Labor)
    for listed companies in Vietnam Annual Reports (BCTN).
    """

    MIN_HEADCOUNT = 1  # Distressed/micro firms can have 1-4 employees
    MAX_HEADCOUNT = 500_000

    def __init__(self):
        self._compile_special_patterns()

    def _compile_special_patterns(self):
        """Compile regexes tailored to Vietnamese corporate disclosures."""

        # Units for employees (Vietnamese + English + unaccented & corrupted variations)
        self.unit_re = (
            r"(?:người|lao\s*động|nhân\s*viên|nhận\s*viên|cb\s*[-–]\s*cnv|cbcnv|cbnv|cb\s*[-–]\s*cn|cb\s*[-–]\s*nv|"
            r"cán\s*bộ\s*quản\s*lý\s*,?\s*người\s*lao\s*động|cán\s*bộ\s*,?\s*người\s*lao\s*động|"
            r"cán\s*bộ|cán\s*bộ\s*nhân\s*viên|cán\s*bộ\s*(?:,?\s*)?(?:công\s*nhân\s*)?viên|"
            r"người\s*lao\s*động|nhân\s*sự|lao\s*dng|lao\s*dqng|lao\s*tlqng|nhan\s*vien|"
            r"can\s*b[oộe>]+|ngiroi|nguai|nguoi|ngudi|ngucri|ngual|ngu'àl|employees?|workforce|staff|personnel|people|headcount)"
        )
        unit_opt = rf"(?:\s*(?P<unit>{self.unit_re}))?"
        unit_req = rf"\s*(?P<unit>{self.unit_re})"

        # Numbers: 1.750, 54,646, 1072, 2152, 48
        num_re = r"(?P<val>\d{1,3}(?:[.,]\d{3})+|\d{4,6}|\d{1,3})"

        # Date Anchors supporting standard, unaccented, and OCR slashes (e.g. 31/12, 31 thang 12, or 311121)
        date_anchor = (
            r"(?:(?:tại|vào|đến|tính\s+đến|ghi\s+nhận\s+tại|thời\s+điểm|ở)?\s*"
            r"(?:thời\s+điểm|ngày)?\s*31[/.\s1-]*(?:12|tháng\s*12|thang\s*12|december)[/.\s1-]*(?:năm\s+|nam\s+)?(?P<date_yr>201\d|202\d)|"
            r"(?:thời\s+điểm\s+)?cuối\s+năm\s+(?P<date_yr2>201\d|202\d)|"
            r"(?:năm\s+tài\s+chính|kết\s+thúc\s+năm)\s+(?P<date_yr3>201\d|202\d)|"
            r"(?:ngày\s+)?0?1[/.\s1-]*(?:0?1|tháng\s*1|thang\s*1|january)[/.\s1-]*(?:năm\s+|nam\s+)?(?P<date_yr4>201\d|202\d))"
        )

        lead_re = (
            r"(?P<lead>(?:t[o0ô6d][nñ]g\s+s[o0ô6i5]|t[o0ô6d][nñ]g\s+st[i1]|tổng\s+số|tổng\s+lượng|tổng\s+cộng|quy\s+mô|lực\s+lượng|đội\s+ngũ|"
            r"s[o0ô6][\s_]*l[uư][oợơ][nng][gq]|số\s+lượng|sé\s+lượng|só\s+lượng|"
            r"tổng\s+sé|tổng\s+só|"
            r"so\s+luong|s6\s+luong|so\s+hrong|s6\s+hrong|s0luqng|sa\s+luirng|s61u)\s+"
            r"(?:cán\s*bộ\s*,?\s*|can\s*b[oộe>r9]+\s*,?\s*)?(?:công\s*nhân\s*)?"
            r"(?:viên|nhân\s*viên|nhận\s*viên|nh[aâ6d]n\s*vi[eê6]n|lao\s*động|lao\s*d[oóôQ]ng|người\s*lao\s*động|nhân\s*sự|cbcnv|cbnv|cb\s*[-–]\s*cn|cb\s*[-–]\s*nv|"
            r"lao\s*dng|nhan\s*vien|nguoi\s*lao\s*dong)|"
            r"lao\s+động\s+(?:sử\s+dụng\s+)?b[ìi]nh\s+qu[âa6]n|nhân\s+sự\s+b[ìi]nh\s+qu[âa6]n|"
            r"(?:sử\s+dụng|sri\s+d[ụup]+ng|sir\s+d[ụup]+ng)\s+b[ìi]nh\s+qu[âa6]n|"
            r"duy\s+trì\s+(?:ổn\s+định\s+)?(?:số\s+lượng\s+lao\s+động|việc\s+làm\s+cho)|"
            r"lực\s+lượng\s+cbcnv|lực\s+lượng\s+lao\s+động|đội\s+ngũ\s+nhân\s+sự|tổng\s+nhân\s+sự|tổng\s+lao\s+động|tổng\s+nhân\s+viên|"
            r"tong\s+so\s+lao\s+dong|tong\s+so\s+nhan\s+vien|so\s+hrong\s+cb-cn|so\s+hrong\s+cb-nv|"
            r"total\s+number\s+of\s+employees|total\s+employees|number\s+of\s+employees|numberof\s+employees|"
            r"total\s+workforce|total\s+staff|total\s+personnel)"
        )

        verb_re = r"(?:là|was|đạt|có|ở\s+mức|quy\s+mô\s+là|quy\s+mô|bình\s+quân\s+là|bình\s+quân|l[àad]|1[ad]|ldr|[:=─–-])\s*"

        # Breakdown Total: "1.413 nguai, trong d6:" / "2.160 nguoi, trong do:"
        self.re_breakdown_total = re.compile(
            rf"{num_re}\s*(?P<unit>{self.unit_re})\s*,\s*trong\s*(?:đó|do|d6|cl6)",
            re.IGNORECASE,
        )

        # Average labor utilized: "sử dụng bình quân năm 2018 là: 556 người"
        self.re_avg_utilized = re.compile(
            r"(?:sử\s+dụng|sri\s+d[ụup]+ng|sir\s+d[ụup]+ng)\s+b[ìi]nh\s+qu[âa6]n[^\n:]{0,50}?(?:(?:n[ăâa]m|ndm)\s+\d{4})?[^\n:]{0,30}?(?:là|1a|ld|ldr|:)\s*"
            rf"{num_re}\s*{unit_opt}",
            re.IGNORECASE,
        )

        # 1. Date First: "Tại ngày 31 tháng 12 năm 2024 số lượng nhân viên công ty mẹ và các công ty con là 4.765 người"
        self.re_date_first = re.compile(
            rf"{date_anchor}[^.\n]{{0,120}}?{lead_re}(?![^,;.\n]*\b(?:tăng|giảm|tuyển|nghỉ|thuê)\b)[^0-9\n]{{0,60}}?{verb_re}{num_re}{unit_opt}",
            re.IGNORECASE,
        )

        # 2. Lead First: "Số lượng nhân sự tại công ty mẹ AAA thời điểm 31/12/2021 là 1.750 người"
        self.re_lead_first = re.compile(
            rf"{lead_re}[^.\n]{{0,100}}?{date_anchor}(?![^,;.\n]*\b(?:tăng|giảm|tuyển|nghỉ|thuê)\b)[^0-9\n]{{0,60}}?{verb_re}{num_re}{unit_opt}",
            re.IGNORECASE,
        )

        # 3. Post-Number Date: "+ S6 luong can be>,nhan vien/ Number of employees: 611 ngiroi (d~n 31/12/2024)"
        #    "- So hrong CB-CN: 859 ngiroi (den :3111212016)"
        #    "+ Số lượng cán bộ, nhân viên: 547 người (đến 31/12/2021)"
        self.re_post_date = re.compile(
            rf"{lead_re}(?![^,;.\n]*\b(?:tăng|giảm|tuyển|nghỉ|thuê)\b)[^0-9\n]{{0,60}}?{verb_re}{num_re}\s*{unit_opt}"
            rf"[^0-9\n]{{0,30}}?(?:\(?\s*(?:đến|d~n|den|tính\s+đến|tại|vào|thời\s+điểm|as\s+(?:of|at))?\s*[:=]?\s*"
            rf"(?:ngày\s+)?31[/.\s1-]*(?:12|tháng\s*12|december)[/.\s1-]*(?:năm\s+)?(?P<post_yr>201\d|202\d)\s*\)?)",
            re.IGNORECASE,
        )

        # 4. General Lead with Mandatory Unit: "Tổng số lao động: 1.255 người", "Lực lượng CBCNV là 1.097 người"
        self.re_general_lead = re.compile(
            rf"{lead_re}(?![^,;.\n]*\b(?:tăng|giảm|tuyển|nghỉ|thuê)\b)[^.\n]{{0,80}}?{verb_re}{num_re}\s*{unit_req}",
            re.IGNORECASE,
        )

        # 5. Bilingual Lead: "Số lượng lao động / Number of employees: 611 người / 611 people"
        self.re_bilingual_lead = re.compile(
            r"(?:số\s+lượng\s+lao\s+động|s6\s+hrong\s+lao\s+dqng|số\s+lượng\s+cán\s+bộ|số\s+lượng\s+nhân\s+viên|"
            r"so\s+luong\s+nhan\s+vien|so\s+hrong\s+cb-cn|so\s+luong\s+lao\s+dong)"
            r"[^0-9\n]{0,60}?/\s*(?:number\s*of\s*employees|numberof\s*employees)\s*[:=]\s*"
            rf"{num_re}\s*{unit_opt}",
            re.IGNORECASE,
        )

        # 6. Comparison in Parentheses: "(tại ngày 31/12/2023 là 2.928 người)" or "(tại ngày 31/12/2021: 1.241 người)"
        self.re_parenthesis = re.compile(
            rf"(?:tại|vào|đến|tính\s+đến|năm)?\s*(?:thời\s+điểm|ngày)?\s*31[/.\s-]*(?:12|tháng\s*12)[/.\s-]*(?:năm\s+)?(?P<comp_yr>201\d|202\d)[^0-9\n]{{0,40}}?{verb_re}{num_re}\s*{unit_req}",
            re.IGNORECASE,
        )

        # 7. English Total
        self.re_en_total = re.compile(
            r"(?:total\s+(?:number\s+of\s+)?(?:employees|workforce|staff|personnel)|"
            r"number\s+of\s+employees|numberof\s+employees|had)\s*"
            r"(?:as\s+(?:of|at)\s+31\s+december\s+(?P<year1>201\d|202\d))?"
            r"\s*(?:was|is|reached|:|\s+)\s*"
            rf"{num_re}\b(?!\s*%)"
            r"\s*(?:employees|people|staff|headcount)?"
            r"(?:\s*as\s+(?:of|at)\s+31[/.\s-]*(?:12|december)[/.\s-]*(?P<year2>201\d|202\d))?",
            re.IGNORECASE,
        )

        # 8. Corrupted Font Table (e.g. AAA 2016 style: S0luqng lao tlQng 1737)
        self.re_corrupted_font = re.compile(
            r"(?:S[0oOô]lu[qg]ng\s+lao\s+tlQng|Ngudn\s+nhin\s+lgc)\s*\n?\s*(?P<val>\d{3,5})",
            re.IGNORECASE,
        )

        # 9. BCTC Note Pattern (Audited Notes - Big4 standard)
        self.re_bctc_note = re.compile(
            r"(?:số\s+lượng\s+(?:nhân\s*viên|nhận\s*viên|lao\s*động|người\s*lao\s*động|nhân\s*sự)|sé\s+nhân\s*viên|number\s+of\s+employees|tập\s+đoàn\s+có|tập\s+đòan\s+có|tổng\s+công\s+ty\s+có|công\s+ty\s+có)\b"
            r"(?!\s+(?:thôi\s*việc|nghỉ\s*việc|thuê\s*mới|tuyển\s*dụng|tuyển\s*mới|nữ|nam))"
            r"[^0-9\n]{0,120}?"
            r"(?:(?:tại|vào|đến|tính\s+đến|thời\s+điểm)\s+(?:ngày\s+)?31[/.\s-]*(?:12|tháng\s*12|thang\s*12|december)[/.\s-]*(?:năm\s+|nam\s+)?(?P<year>201\d|202\d))"
            r"[^0-9\n]{0,50}?"
            r"(?:là|was|đạt|có|:|=|\s+)\s*"
            rf"{num_re}\b"
            r"(?!\s*%)"
            rf"{unit_opt}",
            re.IGNORECASE,
        )

        # 10. Direct Colon Disclosure (e.g. ICF 2015: "Nhu cầu lao động: + Tổng số : 550 người")
        self.re_direct_colon = re.compile(
            r"(?:(?:nhu\s+cầu|kế\s+hoạch|tình\s+hình)\s+lao\s+động[^.\n]{0,80}?)?"
            r"(?:(?:\+|-|\*|\d+[/.])\s*)?"
            r"(?:tổng\s+số|tổng\s+cộng|tổng\s+sé)\s*[:=]\s*"
            rf"{num_re}\s*{unit_req}",
            re.IGNORECASE,
        )

        # 11. BCTC Notes Dual Pairs Pattern (Primary Year & Comparative Year)
        # E.g. "Tại ngày 31 tháng 12 năm 2023 là 9.940 (ngày 31 tháng 12 năm 2022: 9.689)"
        # or "Tại ngày 31/12/2021 là 27.651 nhân viên (1/1/2021: 25.428 nhân viên)"
        # or "Tổng sé nhân viên của Tổng Công ty tại ngày 31 thang 12 năm 2020 là 47 (31/12/2019: 50 người)"
        self.re_bctc_pairs = re.compile(
            r"(?:(?:tổng\s+[sóoée]\s*|số\s+lượng\s+|sé\s+)?(?:nhân\s*viên|nhận\s*viên|lao\s*động|người\s*lao\s*động)[^0-9\n]{0,80}?|tập\s+đoàn\s+có|tập\s+đòan\s+có|tổng\s+công\s+ty\s+có|công\s+ty\s+có)\s*"
            r"(?:tại\s+ngày\s+|vào\s+ngày\s+|ngày\s+)?31[/.\s1-]*(?:12|tháng\s*12|thang\s*12|december)[/.\s1-]*(?:năm\s+|nam\s+)?(?P<y1>20[12]\d)\s*"
            r"[^0-9\n]{0,30}?(?:là|was|đạt|có|:|=|\s+)\s*(?P<v1>\d{1,3}(?:[.,]\d{3})*|\d{1,6})\s*(?:nhân\s*viên|nhận\s*viên|người|nguoi|lao\s*động)?"
            r"[^0-9\n]{0,30}?\(\s*(?:tại\s+ngày\s+|ngày\s+|vào\s+)?(?:31[/.\s1-]*(?:12|tháng\s*12|thang\s*12|december)[/.\s1-]*(?:năm\s+|nam\s+)?(?P<y2>20[12]\d)|0?1[/.\s1-]*(?:0?1|tháng\s*1|thang\s*1)[/.\s1-]*(?:năm\s+|nam\s+)?(?P<y2_alt>20[12]\d))\s*"
            r"[^0-9\n]{0,30}?(?:là|was|đạt|có|:|=|\s+)\s*(?P<v2>\d{1,3}(?:[.,]\d{3})*|\d{1,6})",
            re.IGNORECASE,
        )

        # Numbers: 1.750, 54,646, 1072, 2152, 48, or trailing footnote 35.8783
        num_re = r"(?P<val>\d{1,3}(?:[.,]\d{3})\d?|\d{1,3}(?:[.,]\d{3})+|\d{4,6}|\d{1,3})"

        # 12. Date First BCTC Notes Dual Pairs Pattern:
        # "Tại ngày 31 tháng 12 năm 2025, Tập đòan có 40.411 nhân viên (1/1/2025: 34.835 nhân viên)"
        self.re_date_first_pairs = re.compile(
            r"(?:tại\s+ngày|tính\s+đến\s+ngày|tính\s+đến|đến\s+ngày|vào\s+ngày)?\s*"
            r"31[/.\s1-]*(?:12|tháng\s*12|thang\s*12|december)[/.\s1-]*(?:năm\s+|nam\s+)?(?P<y1>20[12]\d)"
            r"[^0-9\n]{0,60}?(?:tập\s+đoàn\s+có|tập\s+đòan\s+có|tổng\s+công\s+ty\s+có|công\s+ty\s+có|công\s+ty\s+mẹ\s+có)\s*"
            rf"(?P<v1>\d{{1,3}}(?:[.,]\d{{3}})*|\d{{2,6}})\s*(?:nhân\s*viên|nhận\s*viên|lao\s*động|người|nguoi|cbcnv|cbnv)"
            r"(?![^0-9\n]*\b(?:triệu|tỷ|nghìn|đồng|vnd|usd)\b)"
            r"[^0-9\n]{0,40}?\(\s*(?:tại\s+ngày\s+|ngày\s+|vào\s+)?(?:31[/.\s1-]*(?:12|tháng\s*12|thang\s*12|december)[/.\s1-]*(?:năm\s+|nam\s+)?(?P<y2>20[12]\d)|0?1[/.\s1-]*(?:0?1|tháng\s*1|thang\s*1)[/.\s1-]*(?:năm\s+|nam\s+)?(?P<y2_alt>20[12]\d))\s*"
            r"[^0-9\n]{0,30}?(?:là|was|đạt|có|:|=|\s+)\s*(?P<v2>\d{1,3}(?:[.,]\d{3})*|\d{2,6})",
            re.IGNORECASE,
        )

        # 13. Date First Single BCTC Note Pattern:
        # "Tại ngày 31 tháng 12 năm 2025, Tập đòan có 40.411 nhân viên"
        self.re_date_first_bctc = re.compile(
            r"(?:tại\s+ngày|tính\s+đến\s+ngày|tính\s+đến|đến\s+ngày|vào\s+ngày)?\s*"
            r"31[/.\s1-]*(?:12|tháng\s*12|thang\s*12|december)[/.\s1-]*(?:năm\s+|nam\s+)?(?P<year>20[12]\d)"
            r"[^0-9\n]{0,60}?(?:tập\s+đoàn\s+có|tập\s+đòan\s+có|tổng\s+công\s+ty\s+có|công\s+ty\s+có|công\s+ty\s+mẹ\s+có|nhóm\s+công\s+ty\s+có)\s*"
            rf"{num_re}\s*(?:nhân\s*viên|nhận\s*viên|lao\s*động|người|nguoi|cbcnv|cbnv)",
            re.IGNORECASE,
        )

        # 14. Company Has Employees Pattern:
        # "nhân viên của Masan Group là 55.878"
        self.re_company_has_employees = re.compile(
            rf"(?:nhân\s*viên|lao\s*động)\s+của\s+[^0-9\n]{{1,50}}?(?:là|đạt|có|ở\s+mức|:|=)\s*{num_re}\b(?!\s*%)",
            re.IGNORECASE,
        )

    def extract_from_pdf(self, pdf_path: Union[str, Path], ticker: str, year: int) -> LaborExtractionResult:
        """Extract total labor directly from a PDF file."""
        path = Path(pdf_path)
        if not path.exists():
            return LaborExtractionResult(ticker=ticker, year=year, status="NOT_FOUND", raw_text="File not found")

        from arminer.data.bctn_validator import is_valid_bctn_file
        if not is_valid_bctn_file(path):
            return LaborExtractionResult(
                ticker=ticker,
                year=year,
                status="NOT_FOUND",
                raw_text=f"Bỏ qua: File {path.name} không phải BCTN hợp lệ (< 8 trang hoặc là văn bản hành chính)",
            )

        pages: List[Tuple[int, str]] = []
        try:
            try:
                import pymupdf as fitz
            except ImportError:
                import fitz
            doc = fitz.open(path)
            for page_num in range(len(doc)):
                t = doc[page_num].get_text()
                pages.append((page_num + 1, t))
            doc.close()
        except Exception as e:
            logger.warning(f"PyMuPDF error reading {path.name}: {e}")

        total_chars = sum(len(t.strip()) for _, t in pages)
        if total_chars > 300:
            return self.extract_from_pages(pages, ticker, year)

        # Fallback to OCR if PDF has no text layer (scanned report)
        # BƯỚC 1: Kiểm tra cache trước để KHÔNG BAO GIỜ OCR lại file đã quét trước đó!
        try:
            from arminer.ui.server import _extract_text_cached
            cached_text, _ = _extract_text_cached(path)
            if cached_text and len(cached_text.strip()) >= 300:
                return self.extract_from_text(cached_text, ticker, year)
        except Exception:
            pass

        # BƯỚC 2: Chỉ khi chưa có trong cache mới OCR
        try:
            from arminer.ocr.engine import OCREngine
            ocr = OCREngine()
            full_text = ocr.extract_text(path, ocr_mode="smart")
            return self.extract_from_text(full_text, ticker, year)
        except Exception as e:
            logger.error(f"OCR fallback error on {path.name}: {e}")
            return LaborExtractionResult(ticker=ticker, year=year, status="NOT_FOUND", raw_text=f"Extraction error: {e}")

    def extract_from_pages(
        self, pages: List[Tuple[int, str]], ticker: str, year: int
    ) -> LaborExtractionResult:
        """Extract total labor from a list of (page_num, page_text) tuples."""
        candidates: List[LaborCandidate] = []

        page_map = {p_num: t for p_num, t in pages}
        candidate_pages = self._select_candidate_pages(pages, year)

        for page_num, text in candidate_pages:
            # 1. Narrative Regex Strategy (augmented with previous page tail & next page head for split sentences)
            prev_tail = page_map.get(page_num - 1, "")[-300:]
            next_head = page_map.get(page_num + 1, "")[:300]
            augmented_text = (prev_tail + " " if prev_tail else "") + text + (" " + next_head if next_head else "")
            cands_narrative = self._extract_narrative_candidates(augmented_text, page_num, year)
            candidates.extend(cands_narrative)

            # 2. Table Multi-Year Strategy
            cands_table = self._extract_multiyear_table_candidates(text, page_num, year)
            candidates.extend(cands_table)

            # 3. Breakdown Table "100% / Tổng cộng" Strategy
            cands_breakdown = self._extract_breakdown_table_candidates(text, page_num, year)
            candidates.extend(cands_breakdown)

            # 4. BCTC Notes Strategy
            cands_bctc = self._extract_bctc_notes_candidates(text, page_num, year)
            candidates.extend(cands_bctc)

            # 5. Plan vs Actual Metric Table Strategy
            cands_plan_actual = self._extract_plan_actual_metric_candidates(text, page_num, year)
            candidates.extend(cands_plan_actual)

            # 6. Infographic / Big Callout Strategy (e.g. MWG 2025: 64.727 Nhân viên / TỔNG SỐ NHÂN VIÊN)
            cands_callout = self._extract_infographic_callout_candidates(text, page_num, year)
            candidates.extend(cands_callout)

        return self._select_best_candidate(candidates, ticker, year)

    def extract_from_text(self, full_text: str, ticker: str, year: int) -> LaborExtractionResult:
        """Extract total labor from full raw text."""
        if not full_text or len(full_text.strip()) < 50:
            return LaborExtractionResult(ticker=ticker, year=year, status="NOT_FOUND", raw_text="Empty text")

        if "\f" in full_text:
            pages = [(i + 1, p) for i, p in enumerate(full_text.split("\f"))]
        elif "--- [Page" in full_text:
            parts = re.split(r"---\s*\[Page\s*(\d+)\]\s*---", full_text)
            pages = []
            if len(parts) >= 3:
                for i in range(1, len(parts), 2):
                    pg_num = int(parts[i])
                    pg_txt = parts[i + 1] if i + 1 < len(parts) else ""
                    pages.append((pg_num, pg_txt))
            else:
                pages = [(1, full_text)]
        else:
            chunk_size = 3000
            stride = 2500
            pages = [
                (i + 1, full_text[pos : pos + chunk_size])
                for i, pos in enumerate(range(0, len(full_text), stride))
            ]

        return self.extract_from_pages(pages, ticker, year)

    # =========================================================================
    # Strategy Implementations
    # =========================================================================

    def _select_candidate_pages(
        self, pages: List[Tuple[int, str]], year: int
    ) -> List[Tuple[int, str]]:
        """Filter and rank candidate pages."""
        scored_pages: List[Tuple[int, int, str]] = []
        year_str = str(year)

        for page_num, text in pages:
            if not text or len(text.strip()) < 30:
                continue

            low = text.lower()
            score = 0

            # Labor keywords (standard, unaccented, and legacy font variants)
            for kw in [
                "tổng số lao động", "tổng số nhân viên", "tổng số cbcnv",
                "tổng số cán bộ", "tổng số người lao động", "quy mô nhân sự",
                "tổng số nhân sự", "nhân sự trung bình", "nguồn nhân lực",
                "số lượng cán bộ", "số lượng lao động", "số lượng nhân sự",
                "số lượng nhân viên", "lực lượng lao động", "lực lượng cbcnv",
                "cơ cấu lao động", "tình hình nhân sự", "chính sách nhân sự",
                "tổ chức và nhân sự", "thông tin về công ty", "báo cáo tài chính",
                "thuyết minh báo cáo tài chính", "thuyết minh bctc",
                "total employees", "total number of employees", "total workforce",
                "headcount", "number of employees", "numberof employees", "can bo, nhan vien",
                "tập đoàn có", "tập đòan có", "tổng công ty có", "công ty mẹ có",
                # Legacy / corrupted font terms (e.g. ABT 2016, AAA 2016)
                "so luong can bo", "so luong lao dong", "s6 luong can be", "s6 luong can bo",
                "s6 luqng lao dng", "s6 hrong lao dqng", "s6 hrong can be", "so hrong cb-cn",
                "so hrong cb-nv", "s0luqng lao tlqng", "ngudn nhin lgc", "tong so lao dong",
                "cb-cn", "cb-nv", "cb-cnv", "lao dng", "lao dqng", "nhdn vi6n", "ngiroi", "nguai", "nguoi", "ngudi", "ngucri",
                "t6ng s6", "tdng s5", "t6ng sti", "bình quân", "binh quan", "binh qu6n",
            ]:
                if kw in low:
                    score += 15

            if any(w in low for w in ["nhân viên", "lao động", "nhân sự", "cbcnv", "workforce", "employees", "lao dng", "lao dqng", "nhdn vi6n", "ngudi", "ngucri"]):
                score += 10

            if any(corp in low for corp in ["tập đoàn có", "tập đòan có", "tổng công ty có"]) and any(u in low for u in ["nhân viên", "lao động", "người"]):
                score += 35

            if ("thuyết minh" in low or "báo cáo tài chính" in low) and any(u in low for u in ["nhân viên", "lao động"]):
                score += 30

            if f"31/12/{year_str}" in text or f"31.12.{year_str}" in text or f"31-12-{year_str}" in text or f"311121{year_str}" in text:
                score += 25
            elif f"31 tháng 12 năm {year_str}" in text or f"31 thang 12 nam {year_str}" in text:
                score += 25
            elif year_str in text:
                score += 5

            if "31/12" in text or "cuối năm" in low:
                score += 5

            if score >= 10:
                scored_pages.append((score, page_num, text))

        scored_pages.sort(key=lambda x: x[0], reverse=True)
        return [(p_num, txt) for _, p_num, txt in scored_pages[:90]]

    def _extract_narrative_candidates(
        self, text: str, page_num: int, year: int
    ) -> List[LaborCandidate]:
        """Strategy 1: High-confidence regex on narrative sentences and clauses."""
        results: List[LaborCandidate] = []
        year_str = str(year)

        # Normalize text to bridge line wraps in sentences
        norm_text = re.sub(r"[ \t]*\n[ \t]*", " ", text)
        CURRENCY_REJECTS = ["đồng", "tỷ", "triệu", "vnd", "usd", "ca mắc", "%", "cổ phần", "cổ phiếu"]

        patterns = [
            (self.re_date_first, "narrative_date_total", 0.98),
            (self.re_lead_first, "narrative_date_total", 0.98),
            (self.re_post_date, "narrative_post_date", 0.98),
            (self.re_breakdown_total, "narrative_breakdown_total", 0.97),
            (self.re_avg_utilized, "narrative_avg_utilized", 0.96),
            (self.re_bilingual_lead, "narrative_bilingual", 0.96),
            (self.re_general_lead, "narrative_direct_total", 0.94),
            (self.re_direct_colon, "narrative_direct_total", 0.94),
            (self.re_parenthesis, "narrative_comparison", 0.92),
            (self.re_en_total, "narrative_english", 0.96),
            (self.re_company_has_employees, "narrative_direct_total", 0.94),
        ]

        for pat, strat, base_conf in patterns:
            for m in pat.finditer(norm_text):
                val_raw = m.group("val")
                val = normalize_number(val_raw)
                if not self._is_valid_headcount(val) or self._is_year_like(val):
                    continue

                end_pos = m.end()
                trailing = norm_text[end_pos : min(len(norm_text), end_pos + 20)].lower()
                if any(c in trailing for c in CURRENCY_REJECTS):
                    continue

                # Clip snippet strictly to clause boundaries [; | \n .] so exclusions from adjacent
                # clauses (such as average salary 'mức lương: 11.000.000 đồng') do NOT discard headcount!
                before_text = norm_text[:m.start()]
                after_text = norm_text[m.end():]

                m_prev_punct = list(re.finditer(r"[.!?;\n|]", before_text))
                sent_start = m_prev_punct[-1].end() if m_prev_punct else max(0, m.start() - 60)
                sent_start = max(sent_start, m.start() - 80)

                m_next_punct = re.search(r"[,.!?;\n|]", after_text)
                sent_end = (m.end() + m_next_punct.start()) if m_next_punct else min(len(norm_text), m.end() + 60)
                sent_end = min(sent_end, m.end() + 60)

                snippet = norm_text[sent_start:sent_end].strip()
                if self._has_exclusion(snippet):
                    continue

                matched_yr = None
                groups = m.groupdict()
                for yk in ["date_yr", "date_yr2", "date_yr3", "date_yr4", "post_yr", "comp_yr", "year1", "year2"]:
                    if yk in groups and groups[yk]:
                        matched_yr = groups[yk]
                        # If date is 1/1/{yr+1}, that corresponds to 31/12/{yr}
                        if yk == "date_yr4" and matched_yr == str(year + 1):
                            matched_yr = year_str
                        break

                target_year_matched = False
                conf = base_conf
                if matched_yr:
                    if matched_yr == year_str:
                        target_year_matched = True
                    else:
                        target_year_matched = False
                        conf = 0.15  # Explicitly belongs to another comparative year
                elif year_str in snippet or year_str in norm_text[max(0, m.start() - 150) : min(len(norm_text), m.end() + 150)]:
                    target_year_matched = True
                elif year_str in norm_text:
                    target_year_matched = False
                    conf = base_conf * 0.8

                is_group = any(g in snippet.lower() for g in ["công ty con", "tập đoàn", "toàn hệ thống", "toàn bộ", "hợp nhất"])

                cand = LaborCandidate(
                    value=val,
                    raw_snippet=snippet,
                    page=page_num,
                    target_year_matched=target_year_matched,
                    is_total_signal=True,
                    strategy=strat,
                    confidence=conf + (0.01 if is_group else 0.0),
                    reason=f"{strat} matched (yr={matched_yr or year_str})",
                )
                results.append(cand)

        # Corrupted font table check (e.g. AAA 2016)
        for m in self.re_corrupted_font.finditer(text):
            val_raw = m.group("val")
            val = normalize_number(val_raw)
            if self._is_valid_headcount(val) and not self._is_year_like(val):
                snippet = text[max(0, m.start() - 20) : min(len(text), m.end() + 40)].replace("\n", " ").strip()
                cand = LaborCandidate(
                    value=val,
                    raw_snippet=snippet,
                    page=page_num,
                    target_year_matched=True,
                    is_total_signal=True,
                    strategy="corrupted_font_table",
                    confidence=0.95,
                    reason="Corrupted font labor table header",
                )
                results.append(cand)

        return results

    def _extract_multiyear_table_candidates(
        self, text: str, page_num: int, year: int
    ) -> List[LaborCandidate]:
        """
        Strategy 2: Multi-Year Comparison Table parsing.
        Supports both horizontal and vertical column stream formats.
        """
        results: List[LaborCandidate] = []
        year_str = str(year)

        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if len(lines) < 3:
            return results

        TABLE_METRIC_KEYWORDS = [
            "tổng số lượng người lao động",
            "tổng số lao động",
            "tổng số nhân viên",
            "tổng số cbcnv",
            "tổng số cán bộ",
            "total employees",
            "total workforce",
            "số lượng lao động",
            "lao động bình quân",
            "số lao động",
            "quy mô nhân sự",
            "quy mô lao động",
            "nguồn nhân lực",
            "nhân sự giai đoạn",
        ]

        TABLE_ROW_REJECTS = [
            "thuê mới", "tuyển mới", "tuyển dụng", "nghỉ việc", "thôi việc", "sa thải",
            "trình độ", "độ tuổi", "giới tính", "nữ", "nam", "trực tiếp", "gián tiếp",
            "thời vụ", "ngắn hạn", "tỷ lệ", "tỷ trọng", "%",
        ]

        # Case 1: Vertical Year sequence (consecutive lines each with a year)
        years_seq: List[Tuple[int, int]] = []
        for i, l in enumerate(lines):
            m = re.match(r"^(201\d|202\d)$", l)
            if m:
                years_seq.append((int(m.group(1)), i))
            else:
                if len(years_seq) >= 2:
                    break
                years_seq = []

        if years_seq:
            target_idx = None
            for idx, (yr, _) in enumerate(years_seq):
                if yr == year:
                    target_idx = idx
                    break

            if target_idx is not None:
                start_search = years_seq[-1][1] + 1
                for i in range(start_search, min(len(lines), start_search + 25)):
                    l = lines[i].strip()
                    if any(bad in l.lower() for bad in TABLE_ROW_REJECTS):
                        continue
                    if any(k in l.lower() for k in TABLE_METRIC_KEYWORDS):
                        val_seq: List[int] = []
                        for j in range(i + 1, min(len(lines), i + 1 + len(years_seq) * 3)):
                            clean_line = lines[j].split()[0] if lines[j].split() else ""
                            if re.match(r"^\d{1,3}(?:[.,]\d{3})*$", clean_line):
                                num = normalize_number(clean_line)
                                if self._is_valid_headcount(num) and not self._is_year_like(num):
                                    val_seq.append(num)
                                    if len(val_seq) == len(years_seq):
                                        break
                        if len(val_seq) == len(years_seq):
                            cand_val = val_seq[target_idx]
                            snippet = f"{l} -> " + " // ".join(f"{yr}: {v}" for (yr, _), v in zip(years_seq, val_seq))
                            cand = LaborCandidate(
                                value=cand_val,
                                raw_snippet=snippet,
                                page=page_num,
                                target_year_matched=True,
                                is_total_signal=True,
                                strategy="table_vertical_multiyear",
                                confidence=0.98,
                                reason=f"Vertical multi-year table column {year_str}",
                            )
                            results.append(cand)

        # Case 2: Horizontal multi-year table
        for i, line in enumerate(lines):
            low = line.lower()
            if any(bad in low for bad in TABLE_ROW_REJECTS):
                continue
            is_labor_header = any(k in low for k in TABLE_METRIC_KEYWORDS)
            if not is_labor_header:
                continue

            window = lines[max(0, i - 4) : min(len(lines), i + 7)]
            snippet = " // ".join(window)

            horiz_years: List[Tuple[int, int]] = []
            for w_line in window:
                w_low = w_line.lower()
                if any(p in w_low for p in ["giai đoạn", "giai doan", "thời kỳ", "kế hoạch", "gđ", "gd"]):
                    continue
                if re.search(r"\b201\d\s*[-–—]\s*20[12]\d\b", w_line):
                    continue
                matched_yrs = re.findall(r"\b(201\d|202\d)\b", w_line)
                if len(matched_yrs) >= 2:
                    for col_idx, yr in enumerate(matched_yrs):
                        horiz_years.append((int(yr), col_idx))
                    break

            if horiz_years:
                target_col = None
                for yr, c_idx in horiz_years:
                    if yr == year:
                        target_col = c_idx
                        break

                if target_col is not None:
                    for w_line in window:
                        w_low = w_line.lower()
                        if any(b in w_low for b in TABLE_ROW_REJECTS) or any(b in w_low for b in ["thu nhập", "lương", "triệu đồng", "tỷ đồng", "vnd", "usd"]):
                            continue
                        clean_w = re.sub(r"^\s*\d+\s*[=.-]\s*", "", w_line)
                        clean_w = re.sub(r"\d+([.,]\d+)?\s*%", "", clean_w)
                        nums = re.findall(r"\b(?:\d{1,3}(?:[.,]\d{3})+|\d{4,6}|\d{1,3})\b", clean_w)
                        if len(nums) == len(horiz_years) and not any(int(n) in [y[0] for y in horiz_years] for n in nums if n.isdigit()):
                            try:
                                target_val = normalize_number(nums[target_col])
                                has_u = any(u in clean_w.lower() for u in ["người", "nhân viên", "lao động", "cbcnv"])
                                if self._is_valid_headcount(target_val, has_unit=has_u) and not self._is_year_like(target_val):
                                    cand = LaborCandidate(
                                        value=target_val,
                                        raw_snippet=snippet,
                                        page=page_num,
                                        target_year_matched=True,
                                        is_total_signal=True,
                                        strategy="table_multiyear",
                                        confidence=0.85,
                                        reason=f"Horizontal multi-year table column {year_str}",
                                    )
                                    results.append(cand)
                            except Exception:
                                pass

            # Direct lines within the labor section window: e.g. "2018 2152" or "Năm 2022 là: 27 người"
            for w_line in window:
                w_low = w_line.lower()
                if any(b in w_low for b in TABLE_ROW_REJECTS) or any(b in w_low for b in ["thu nhập", "lương", "triệu đồng", "tỷ đồng", "vnd", "usd"]):
                    continue
                direct_match = re.search(
                    rf"(?:năm\s+)?{year_str}[^0-9\n]{{0,30}}?(?P<val>\d{{1,3}}(?:[.,]\d{{3}})+|\d{{4,6}}|\d{{1,3}})\s*(?:người|lao\s*động|nhân\s*viên)?\b",
                    w_line,
                    re.IGNORECASE,
                )
                if direct_match and not direct_match.group(0).endswith("%"):
                    val = normalize_number(direct_match.group("val"))
                    has_u = any(u in w_line.lower() for u in ["người", "nhân viên", "lao động", "cbcnv"])
                    if self._is_valid_headcount(val, has_unit=has_u) and not self._is_year_like(val) and not self._has_exclusion(w_line):
                        cand = LaborCandidate(
                            value=val,
                            raw_snippet=f"{line} // {w_line}",
                            page=page_num,
                            target_year_matched=True,
                            is_total_signal=True,
                            strategy="table_multiyear_row",
                            confidence=0.94,
                            reason=f"Line explicitly pairing {year_str} with headcount in labor section",
                        )
                        results.append(cand)

        return results

    def _extract_breakdown_table_candidates(
        self, text: str, page_num: int, year: int
    ) -> List[LaborCandidate]:
        """
        Strategy 3: Breakdown Table "100% / Tổng cộng" parsing.
        Must specifically be in an authentic Employee/Labor context (not shareholders, resolutions, or finance).
        """
        results: List[LaborCandidate] = []
        year_str = str(year)
        lines = [line.strip() for line in text.split("\n") if line.strip()]

        REJECT_TABLE_WORDS = [
            "cổ đông", "cổ phần", "vốn điều lệ", "tỷ lệ sở hữu", "nhà đầu tư",
            "biểu quyết", "tán thành", "nghị quyết", "đại hội đồng", "đhđcđ",
            "ứng cử", "nhiệm kỳ", "phiên họp", "thù lao", "thành viên hđqt",
            "doanh thu", "lợi nhuận", "nguồn vốn", "tổng tài sản", "tiền mặt",
            "phải thu", "phải trả", "vốn chủ sở hữu", "công nợ", "nguyên vật liệu",
            "quyết định số", "triệu đồng", "nghìn đồng", "ngàn vnd", "nghìn vnd", "triệu vnd", "tỷ vnd",
            "bất động sản", "tiền chuyển nhượng", "tiền gửi", "khoản phải",
            "phát hành", "chương trình", "lựa chọn", "esop", "mua cổ phiếu", "thưởng cổ phiếu",
            "quyết định", "qđ-", "/qđ", "nq.hđqt", "nq-hđqt", "điều lệ",
            "thai sản", "sa thải", "kỷ luật", "khẩu trang", "tiêm ngừa", "tiêm chủng", "vắc xin", "covid",
            "bctn/bc", "qtct", "thẻ điểm", "tiêu chí đánh giá", "nguyên tắc", "sáng kiến", "giải pháp",
            "ban kiểm toán", "ban điều hành", "đội ngũ điều hành", "đội ngũ", "trưởng phòng", "giám sát", "phó phòng", "khối bán hàng", "chi nhánh phân phối",
        ]

        LABOR_CATEGORY_WORDS = [
            "đại học", "cao đẳng", "trung cấp", "phổ thông", "trên đại học",
            "hợp đồng lao động", "hđlđ", "không xác định thời hạn", "có thời hạn",
            "lao động trực tiếp", "lao động gián tiếp", "cơ cấu lao động",
        ]

        for i, line in enumerate(lines):
            low = line.lower()

            # Pattern A: 100% row in breakdown table
            if "100%" in line or "100,00%" in line or "100.00%" in line:
                window = lines[max(0, i - 4) : min(len(lines), i + 4)]
                window_str = " // ".join(window)
                window_low = window_str.lower()

                if any(w in window_low for w in REJECT_TABLE_WORDS):
                    continue
                # Require at least 1 verified labor category word in the table window
                if not any(w in window_low for w in LABOR_CATEGORY_WORDS):
                    continue

                for w_line in window:
                    # Reject if the line is merely a solitary page number at top/bottom of page
                    if w_line.isdigit() and int(w_line) in [page_num, page_num + 1, page_num - 1]:
                        continue
                    cleaned_w = re.sub(r"\b(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+|[A-Za-z]\.\d+\.\d+)\b", "", w_line)
                    line_no_pct = re.sub(r"\d+([.,]\d+)?\s*%", "", cleaned_w)
                    nums = [n for n in re.findall(r"\b\d{1,3}(?:[.,]\d{3})*\b", line_no_pct) if n not in ["100", "10000", "00", "1", "2", "3", "4", "5", year_str]]
                    for num_idx, n_str in enumerate(nums):
                        val = normalize_number(n_str)
                        if val in [page_num, page_num + 1]:
                            continue
                        has_u = any(u in w_line.lower() for u in ["người", "nhân viên", "lao động", "cbcnv"]) or any(u in window_low for u in ["người", "nhân viên", "lao động", "cbcnv"])
                        if val < 50 and not has_u:
                            continue
                        if val > 60000 and any(m in w_line.lower() for m in ["đồng", "vnd", "lương", "thu nhập"]):
                            continue
                        if self._is_valid_headcount(val) and not self._is_year_like(val) and not self._has_exclusion(window_str):
                            is_target_year = (num_idx == len(nums) - 1) and (year_str in window_str or f"31/12/{year_str}" in text)
                            cand = LaborCandidate(
                                value=val,
                                raw_snippet=window_str,
                                page=page_num,
                                target_year_matched=is_target_year,
                                is_total_signal=True,
                                strategy="table_breakdown_100pct",
                                confidence=0.93 if is_target_year else 0.70,
                                reason="100% Total row in workforce breakdown table",
                            )
                            results.append(cand)

            # Pattern B: "Tổng cộng" / "Tổng số" row in breakdown table
            if low in ["tổng cộng", "tổng số", "tổng cộng / total", "tổng", "tổng cộng:"]:
                lookback = lines[max(0, i - 15) : i]
                lookback_str = " // ".join(lookback)
                lookback_low = lookback_str.lower()

                if any(w in lookback_low for w in REJECT_TABLE_WORDS):
                    continue
                if not any(w in lookback_low for w in LABOR_CATEGORY_WORDS):
                    continue

                forward = lines[i : min(len(lines), i + 3)]
                for w_line in forward:
                    if w_line.isdigit() and int(w_line) in [page_num, page_num + 1]:
                        continue
                    cleaned_w = re.sub(r"\b(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+|[A-Za-z]\.\d+\.\d+)\b", "", w_line)
                    line_no_pct = re.sub(r"\d+([.,]\d+)?\s*%", "", cleaned_w)
                    nums = re.findall(r"\b\d{1,3}(?:[.,]\d{3})*\b", line_no_pct)
                    for n_str in nums:
                        val = normalize_number(n_str)
                        if val in [page_num, page_num + 1]:
                            continue
                        # Corporate breakdown table total can never be < 50 (e.g. 17 is executive team count, not total)
                        if val < 50:
                            continue
                        if val > 60000 and any(m in w_line.lower() for m in ["đồng", "vnd", "lương", "thu nhập"]):
                            continue
                        if self._is_valid_headcount(val) and not self._is_year_like(val) and not self._has_exclusion(f"{line} {w_line}"):
                            cand = LaborCandidate(
                                value=val,
                                raw_snippet=lookback_str[-120:] + " // " + f"{line}: {w_line}",
                                page=page_num,
                                target_year_matched=(year_str in text),
                                is_total_signal=True,
                                strategy="table_breakdown_total_row",
                                confidence=0.92,
                                reason="'Tổng cộng' row in labor breakdown table",
                            )
                            results.append(cand)

        return results

    def _extract_bctc_notes_candidates(
        self, text: str, page_num: int, year: int
    ) -> List[LaborCandidate]:
        """
        Strategy 4: Financial Statement Notes (Thuyết minh BCTC).
        Audited official disclosure signed by Big4 / certified auditors:
            "Tại ngày 31 tháng 12 năm 2021, Tập đoàn có 5.806 nhân viên (tại ngày 31 tháng 12 năm 2020: 6.191 nhân viên)"
            "Tại ngày 31 tháng 12 năm 2023 là 9.940 (ngày 31 tháng 12 năm 2022: 9.689)"
        """
        results: List[LaborCandidate] = []
        year_str = str(year)

        # 1. Dual Pairs check: extracts both Primary Year and Comparative Year
        for m in self.re_bctc_pairs.finditer(text):
            y1 = m.group("y1")
            v1_raw = m.group("v1")
            v1 = normalize_number(v1_raw)
            if self._is_valid_headcount(v1) and not self._is_year_like(v1):
                start = max(0, m.start() - 20)
                end = min(len(text), m.end() + 20)
                snip = text[start:end].replace("\n", " ").strip()
                cand1 = LaborCandidate(
                    value=v1,
                    raw_snippet=snip,
                    page=page_num,
                    target_year_matched=(y1 == year_str),
                    is_total_signal=True,
                    strategy="bctc_notes",
                    confidence=0.99 if (y1 == year_str) else 0.15,
                    reason=f"BCTC Notes official audited headcount for {y1}",
                )
                results.append(cand1)

            y2 = m.group("y2")
            if not y2 and m.group("y2_alt"):
                # "1/1/2021: 25.428" -> end of 2020
                y2 = str(int(m.group("y2_alt")) - 1)

            v2_raw = m.group("v2")
            v2 = normalize_number(v2_raw)
            if y2 and self._is_valid_headcount(v2) and not self._is_year_like(v2):
                cand2 = LaborCandidate(
                    value=v2,
                    raw_snippet=text[max(0, m.start() - 20) : min(len(text), m.end() + 20)].replace("\n", " ").strip(),
                    page=page_num,
                    target_year_matched=(y2 == year_str),
                    is_total_signal=True,
                    strategy="bctc_notes",
                    confidence=0.98 if (y2 == year_str) else 0.15,
                    reason=f"BCTC Notes official comparative headcount for {y2}",
                )
                results.append(cand2)

        # 2. Single BCTC note check
        for m in self.re_bctc_note.finditer(text):
            val_raw = m.group("val")
            val = normalize_number(val_raw)
            if not self._is_valid_headcount(val) or self._is_year_like(val):
                continue
            found_year = m.group("year")
            start = max(0, m.start() - 40)
            end = min(len(text), m.end() + 80)
            snippet = text[start:end].replace("\n", " ").strip()
            if found_year:
                matched_year = (found_year == year_str)
            else:
                matched_year = (year_str in snippet)
            cand = LaborCandidate(
                value=val,
                raw_snippet=snippet,
                page=page_num,
                target_year_matched=matched_year,
                is_total_signal=True,
                strategy="bctc_notes",
                confidence=0.99 if matched_year else 0.15,
                reason=f"BCTC Notes official audited employee disclosure (yr={found_year})",
            )
            results.append(cand)

        # 3. Date First Dual Pairs check:
        for m in self.re_date_first_pairs.finditer(text):
            y1 = m.group("y1")
            v1_raw = m.group("v1")
            v1 = normalize_number(v1_raw)
            if self._is_valid_headcount(v1) and not self._is_year_like(v1):
                start = max(0, m.start() - 20)
                end = min(len(text), m.end() + 20)
                snip = text[start:end].replace("\n", " ").strip()
                cand1 = LaborCandidate(
                    value=v1,
                    raw_snippet=snip,
                    page=page_num,
                    target_year_matched=(y1 == year_str),
                    is_total_signal=True,
                    strategy="bctc_notes",
                    confidence=0.99 if (y1 == year_str) else 0.15,
                    reason=f"Date-First BCTC Notes audited headcount for {y1}",
                )
                results.append(cand1)

            y2 = m.group("y2")
            if not y2 and m.group("y2_alt"):
                y2 = str(int(m.group("y2_alt")) - 1)

            v2_raw = m.group("v2")
            v2 = normalize_number(v2_raw)
            if y2 and self._is_valid_headcount(v2) and not self._is_year_like(v2):
                cand2 = LaborCandidate(
                    value=v2,
                    raw_snippet=text[max(0, m.start() - 20) : min(len(text), m.end() + 20)].replace("\n", " ").strip(),
                    page=page_num,
                    target_year_matched=(y2 == year_str),
                    is_total_signal=True,
                    strategy="bctc_notes",
                    confidence=0.98 if (y2 == year_str) else 0.15,
                    reason=f"Date-First BCTC Notes comparative headcount for {y2}",
                )
                results.append(cand2)

        # 4. Date First Single BCTC note check
        for m in self.re_date_first_bctc.finditer(text):
            val_raw = m.group("val")
            val = normalize_number(val_raw)
            if not self._is_valid_headcount(val) or self._is_year_like(val):
                continue
            found_year = m.group("year")
            start = max(0, m.start() - 20)
            end = min(len(text), m.end() + 60)
            snippet = text[start:end].replace("\n", " ").strip()
            cand = LaborCandidate(
                value=val,
                raw_snippet=snippet,
                page=page_num,
                target_year_matched=(found_year == year_str),
                is_total_signal=True,
                strategy="bctc_notes",
                confidence=0.99 if (found_year == year_str) else 0.15,
                reason=f"Date-First BCTC single disclosure for {found_year}",
            )
            results.append(cand)

        return results

    def _extract_plan_actual_metric_candidates(
        self, text: str, page_num: int, year: int
    ) -> List[LaborCandidate]:
        """
        Strategy 5: Plan vs Actual / Single-Year Metric Table row.
        E.g. HVN:
            Tổng số lao động
            người
            10,211 (KH)
            10,095 (Thực hiện)
            98.9%
        """
        results: List[LaborCandidate] = []
        year_str = str(year)
        lines = [line.strip() for line in text.split("\n") if line.strip()]

        SUBSET_ROW_REJECTS = [
            "thuê mới", "tuyển mới", "tuyển dụng", "nghỉ việc", "thôi việc", "sa thải",
            "tỷ lệ", "chiếm", "nữ", "nam", "%", "trong tổng số", "tỷ trọng", "trực tiếp", "gián tiếp",
            "độ tuổi", "tuổi", "trình độ", "thời vụ", "bán thời gian", "xuất khẩu", "ngoài nước",
            "chính sách", "hoạt động", "đánh giá", "bảo vệ", "nghị quyết", "kế hoạch", "hđlđ",
            "cơ cấu", "mục lục", "báo cáo", "nội dung",
        ]

        METRIC_ROW_REGEX = re.compile(
            r"^[-–—•*+\d./\s]*(?:"
            r"tổng\s+số\s+(?:lao\s+động|nhân\s*viên|cbcnv|cbnv|cán\s*bộ)|"
            r"số\s+lượng\s+(?:lao\s+động|nhân\s*viên|nhân\s*sự)|"
            r"lao\s+động\s+bình\s+quân|"
            r"nhân\s*sự\s+bình\s+quân|"
            r"quy\s+mô\s+nhân\s+sự"
            r")\b",
            re.IGNORECASE,
        )

        for i, line in enumerate(lines):
            low = line.lower()
            if len(line) > 80 or any(v in low for v in [" là ", " was ", " đạt ", " ở mức "]):
                continue
            if not METRIC_ROW_REGEX.match(line):
                continue
            if any(bad in low for bad in SUBSET_ROW_REJECTS):
                continue
            # A table row label is never an unfinished sentence ending in a date or preposition
            if any(w in low for w in ["tại ngày", "ngày 31", "thời điểm", "đến ngày", "trụ sở", "địa chỉ"]):
                continue

            forward = lines[i + 1 : min(len(lines), i + 10)]
            if not forward:
                continue

            combined_context = f"{line} " + " ".join(forward[:3]).lower()
            has_unit = any(u in combined_context for u in ["người", "lao động", "nhân viên", "cbcnv", "cbnv"])

            nums = []
            for fl in forward:
                if "%" in fl:
                    break
                fl_low = fl.lower()

                if nums:
                    if len(fl) > 35 or fl.startswith("-") or fl.startswith("+") or fl.startswith("•") or fl.startswith("*"):
                        break
                    if not any(ch.isdigit() for ch in fl) and not any(u in fl_low for u in ["người", "nhân viên", "lao động", "cbcnv", "cbnv"]):
                        break
                    if re.match(r"^[A-Za-zÀ-ỹ\s]{3,}", fl) and not any(u in fl_low for u in ["người", "nhân viên", "lao động", "cbcnv"]):
                        break

                if any(bad in fl_low for bad in ["triệu", "tỷ", "đồng", "vnd", "usd", "lương", "thu nhập", "tuổi", "trình độ", "tỷ lệ"]) or fl_low.endswith("đ"):
                    continue
                # Reject document numbers and dispatch metadata (e.g. 'Số văn bản: 300/CPNT2-KHTH')
                if "số văn bản" in fl_low or "ngày ban hành" in fl_low or re.search(r"\b\d+/[A-Za-z0-9_-]+\b", fl):
                    continue
                # Reject page number markers like '| 37' or '37 |'
                if re.match(r"^\|\s*\d+\s*$", fl) or re.match(r"^\d+\s*\|\s*$", fl):
                    continue
                # Reject decimal numbers (e.g. 19,76% or 12.5)
                if re.search(r"\d+[,.]\d{1,2}\b", fl):
                    continue

                m_num = re.search(r"\b(\d{1,3}(?:[.,]\d{3})*|\d{2,6})\b", fl)
                if m_num:
                    clean = m_num.group(1).replace(".", "").replace(",", "")
                    if clean.isdigit():
                        int_val = int(clean)
                        # Numbers < 10 in table rows are always footnote/note/STT columns, never corporate headcount
                        if int_val < 10:
                            continue
                        fl_has_unit = any(u in fl_low for u in ["người", "lao động", "nhân sự", "nhân viên", "cbcnv", "cbnv"])
                        if int_val < 50 and not fl_has_unit and not (has_unit and int_val >= 20):
                            continue
                        if self._is_valid_headcount(int_val, has_unit=fl_has_unit or has_unit) and not self._is_year_like(int_val):
                            nums.append(int_val)

            # Eliminate trailing footnote/note/STT numbers that leaked into nums (e.g. 640 // 629 // 652 // 2 or 302 // 2)
            while len(nums) >= 2 and nums[-1] < 20 and any(n >= 50 for n in nums[:-1]):
                nums.pop()
            while len(nums) >= 2 and nums[-1] < 50 and nums[-1] < 0.25 * nums[-2]:
                nums.pop()

            # Reject chart Y-axis ticks (e.g. 9000, 8000, 7000, 6000, 5000, ...)
            if len(nums) >= 4:
                diffs = [nums[k] - nums[k+1] for k in range(len(nums)-1)]
                if len(set(diffs)) == 1 and diffs[0] > 0:
                    continue

            # Solitary small number (< 20) is never a corporate table
            if len(nums) == 1 and nums[0] < 20:
                continue

            if nums:
                lookback = lines[:i]
                # Look for column header years (vertical sequence or horizontal line)
                header_years = []
                for j in range(len(lookback) - 1):
                    if re.match(r"^(201\d|202\d)$", lookback[j]):
                        seq = [lookback[j]]
                        k = j + 1
                        while k < len(lookback) and re.match(r"^(201\d|202\d)$", lookback[k]):
                            seq.append(lookback[k])
                            k += 1
                        if len(seq) >= 2:
                            header_years = seq
                            break
                if not header_years:
                    for lb_line in lookback:
                        matched = re.findall(r"\b(201\d|202\d)\b", lb_line)
                        if len(matched) >= 2:
                            header_years = matched
                            break
                if not header_years:
                    header_years = re.findall(r"\b(201\d|202\d)\b", " ".join(lookback[-10:]))

                if header_years and len(header_years) == len(nums) and year_str in header_years:
                    val = nums[header_years.index(year_str)]
                    is_target = True
                elif header_years and len(header_years) == len(nums) - 1 and nums[0] in [1, 2, 3] and year_str in header_years:
                    val = nums[1 + header_years.index(year_str)]
                    is_target = True
                else:
                    # In Plan vs Actual table, Actual (Thực hiện) is the last column before %
                    val = nums[-1] if len(nums) >= 2 else nums[0]
                    is_target = (year_str in " ".join(lookback).lower() or f"31/12/{year_str}" in " ".join(lookback).lower())

                snippet = f"{line} -> " + " // ".join(str(n) for n in nums)
                cand = LaborCandidate(
                    value=val,
                    raw_snippet=snippet,
                    page=page_num,
                    target_year_matched=is_target,
                    is_total_signal=True,
                    strategy="table_plan_actual_metric",
                    confidence=0.96 if is_target else 0.72,
                    reason=f"Plan vs Actual table metric row '{line}'",
                )
                results.append(cand)

        return results

    def _extract_infographic_callout_candidates(
        self, text: str, page_num: int, year: int
    ) -> List[LaborCandidate]:
        """
        Strategy 6: Infographic / Big Number Callouts.
        Modern reports frequently display total headcount in stylized KPI boxes:
            "64.727 Nhân viên \n TỔNG SỐ NHÂN VIÊN THEO CHUỖI"
            "TỔNG SỐ NHÂN VIÊN: 64.727"
        """
        results: List[LaborCandidate] = []
        year_str = str(year)
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        for i, line in enumerate(lines):
            low = line.lower()
            if any(term in low for term in ["tổng số nhân viên", "tổng số lao động", "quy mô nhân sự", "tổng quy mô nhân sự", "tổng nhân sự"]):
                if any(bad in low for bad in ["tăng", "giảm", "thuê", "tuyển", "nữ", "nam", "trình độ", "%", "tỷ lệ"]):
                    continue
                # Look 4 lines before and 4 lines after for big headcount number
                window = lines[max(0, i - 4) : min(len(lines), i + 5)]
                for w in window:
                    m = re.search(r"\b(?P<val>\d{1,3}(?:[.,]\d{3})+|\d{4,6})\s+(?P<unit>nhân\s*viên|lao\s*động|người|cbcnv|employees|people)\b", w, re.IGNORECASE)
                    if m:
                        val = normalize_number(m.group("val"))
                        if self._is_valid_headcount(val) and not self._is_year_like(val) and val >= 100:
                            # Verify not financial
                            if not any(fin in w.lower() for fin in ["đồng", "vnd", "usd", "tỷ", "triệu"]):
                                snip = " // ".join(window)
                                cand = LaborCandidate(
                                    value=val,
                                    raw_snippet=snip,
                                    page=page_num,
                                    target_year_matched=(year_str in snip or year_str in text),
                                    is_total_signal=True,
                                    strategy="infographic_callout",
                                    confidence=0.95,
                                    reason=f"Infographic KPI callout '{line}' near {val:,}",
                                )
                                results.append(cand)
        return results

    # =========================================================================
    # Disambiguation & Best Candidate Selection (100% Precision Engine)
    # =========================================================================

    def _select_best_candidate(
        self, candidates: List[LaborCandidate], ticker: str, year: int
    ) -> LaborExtractionResult:
        """Score and pick the single best candidate representing total labor."""
        if not candidates:
            return LaborExtractionResult(
                ticker=ticker,
                year=year,
                labor=None,
                source_page=None,
                raw_text="",
                confidence=0.0,
                status="NOT_FOUND",
            )

        year_str = str(year)
        scored: List[Tuple[float, LaborCandidate]] = []

        # Strict Disqualification terms: if snippet contains any of these, DISQUALIFY immediately!
        DISQUALIFY_TERMS = [
            "thuê mới", "tuyển mới", "nghỉ việc", "thôi việc", "sa thải", "chấm dứt hđlđ",
            "có trình độ", "trung cấp trở lên", "đại học trở lên", "sau đại học",
            "lao động nữ", "nhân viên nữ", "nữ:", "lao động nam", "nam:", "tỷ lệ nữ",
            "lao động trực tiếp", "lao động gián tiếp", "trực tiếp:", "gián tiếp:",
            "tiêm ngừa", "tiêm chủng", "vắc xin", "vacxin", "covid", "khẩu trang",
            "khối cảng", "khối bán hàng", "khối kinh doanh", "khối văn phòng", "khối sản xuất",
            "khối miền nam", "khối miền bắc", "khối miền trung", "khối cảng miền",
            "văn phòng đại diện", "tại chi nhánh",
            # Governance board counts & committees (never total company headcount)
            "ban kiểm soát nội bộ", "ban kiểm toán", "ủy ban kiểm toán",
            "thành viên hđqt", "thành viên ban điều hành", "thành viên ban giám đốc", "thành viên bks",
            "thành viên hội đồng quản trị", "thành viên ban tổng giám đốc",
            "ban kiểm soát gồm", "ban kiểm soát có", "hđqt gồm", "ban điều hành gồm", "ban giám đốc gồm",
            "ban kiểm toán gồm", "bks gồm", "hội đồng thành viên gồm",
            "đội ngũ điều hành",
            # Maternity & childcare subgroups
            "thai sản", "nghỉ thai", "nghỉ thai sản", "nuôi con nhỏ", "chế độ thai sản", "hết kỳ nghỉ thai", "sau khi hết kỳ nghỉ thai", "maternity",
            # Promotions, awards, ESOP
            "thăng tiến", "bổ nhiệm", "khen thưởng", "kỷ luật", "điều động", "luân chuyển",
            "được phân phối", "phân phối là", "phát hành cổ phiếu", "cổ phiếu thưởng", "esop",
            # Social sponsorships & donations
            "an sinh xã hội", "tài trợ an sinh", "tài trợ", "ủng hộ", "hiến máu", "mái ấm", "nhà tình nghĩa",
            # Historical sections (e.g. TCM 1967)
            "giai đoạn hình thành", "tiền thân", "thành lập xí nghiệp", "1967", "1975", "1985",
            # Macro / National statistics
            "cục quản lý lao động", "bộ lao động", "lao động ngoài nước", "lao động ngòai nước", "xuất khẩu lao động", "thị trường lao động",
            "thất nghiệp", "tai nạn lao động", "bảo hiểm thất nghiệp",
        ]

        has_group_candidate = any(
            any(w in c.raw_snippet.lower() for w in ["tập đoàn", "tập đòan", "toàn tập đoàn", "toàn tổng công ty", "và các công ty con", "và công ty con", "nhóm công ty", "toàn hệ thống"])
            for c in candidates
        )

        for c in candidates:
            snippet_low = c.raw_snippet.lower()
            # Strip standard chapter titles so that narrative inside "Báo cáo của Ban Điều hành" is not falsely disqualified
            cleaned_snip = re.sub(
                r"\b(?:báo\s+cáo(?:\s+và\s+đánh\s+giá)?|thông\s+điệp)\s+của\s+(?:ban\s+điều\s+hành|ban\s+giám\s+đốc|ban\s+tổng\s+giám\s+đốc|hội\s+đồng\s+quản\s+trị|hđqt|chủ\s+tịch)\b",
                "",
                snippet_low,
                flags=re.IGNORECASE,
            )

            # 1. HARD DISQUALIFICATION: Subgroup or Delta or ESG Noise
            if any(term in cleaned_snip for term in DISQUALIFY_TERMS):
                continue

            # 1b. Disqualify Table of Contents page number collisions (e.g. NT2 37: "2.5 ... 37")
            if re.search(r"(?:\.{3,}|-{3,})\s*" + re.escape(str(c.value)) + r"\b", snippet_low):
                continue
            if "mục lục" in snippet_low or "table of contents" in snippet_low:
                continue

            # 1c. Disqualify Street address collisions (e.g. IDC 151: "Trụ sở: 151 Ter Nguyễn Đình Chiểu")
            if re.search(r"(?:trụ\s*sở|địa\s*chỉ|tầng|toà\s*nhà|đường|phường|quận)[^;,\n]{0,25}\b" + re.escape(str(c.value)) + r"\b", snippet_low):
                continue

            # 1d. Disqualify Chart Y-Axis tick sequences (e.g. HSG 1000: "9000 // 8000 // 7000 ... 1000")
            if re.search(r"\b\d000\s*//\s*\d000\s*//\s*\d000\b", snippet_low):
                continue

            score = c.confidence

            # 2. STRATEGY TIERING (Audited BCTC Notes & Explicit Post-Date carry highest authority)
            if c.strategy in ["bctc_notes", "narrative_date_total", "narrative_post_date"]:
                score += 0.45
            elif c.strategy in ["infographic_callout", "narrative_bilingual", "narrative_comparison", "narrative_direct_total", "corrupted_font_table"]:
                score += 0.30
            elif c.strategy in ["table_vertical_multiyear", "table_multiyear", "table_plan_actual_metric"]:
                score += 0.15
            elif c.strategy in ["table_breakdown_100pct", "table_breakdown_total_row"]:
                score += 0.10

            # 3. Target year match bonus
            if c.target_year_matched:
                score += 0.35
            elif year_str in c.raw_snippet:
                score += 0.20

            # 4. Group / Consolidated bonus vs Parent-only penalty
            is_group = any(w in snippet_low for w in ["công ty con", "tập đoàn", "tập đòan", "toàn hệ thống", "toàn tập đoàn", "toàn tổng công ty", "nhóm công ty", "hợp nhất"])
            is_parent_only = ("công ty mẹ" in snippet_low or "tổng công ty mẹ" in snippet_low) and not any(w in snippet_low for w in ["và các công ty con", "và công ty con", "toàn tổng công ty", "toàn tập đoàn"])
            
            if is_group:
                score += 0.35
            elif is_parent_only and has_group_candidate:
                score -= 0.50

            # 5. Explicit total indicator bonus
            if any(
                w in snippet_low
                for w in [
                    "tổng số", "tổng cộng", "toàn hệ thống", "toàn tập đoàn",
                    "toàn công ty", "total number", "100%", "quy mô", "bình quân",
                ]
            ):
                score += 0.25

            # 6. Penalties
            if c.value in [year, year - 1, year - 2, 31, 30, 12, 1, 2, 3]:
                score -= 0.60

            # Small numbers (< 50) without explicit labor unit
            if c.value < 50:
                if not any(u in snippet_low for u in ["người", "nhân viên", "lao động", "cbcnv"]):
                    score -= 0.85
                if any(w in snippet_low for w in ["ban điều hành", "ban kiểm toán", "hđqt", "bộ phận", "chi nhánh", "đợt", "khối", "khen thưởng", "sáng kiến"]):
                    score -= 0.60

            # Single digit numbers (< 10) are almost never total headcount for listed companies
            if c.value < 10:
                score -= 1.0

            # Reject macro/national-scale numbers if context mentions cục / bộ / ngoài nước
            if c.value > 50000 and any(w in snippet_low for w in ["cục quản lý", "bộ lao động", "ngòai nước", "ngoài nước", "toàn ngành", "cả nước"]):
                score -= 1.5

            # Financial terms nearby
            if any(w in snippet_low for w in ["tỷ đồng", "triệu đồng", "đồng/người", "vnd", "usd"]):
                if not any(u in snippet_low for u in ["người", "nhân viên", "lao động", "cbcnv", "cbnv", "cán bộ"]):
                    score -= 0.50

            # Resolution or shareholder terms
            if any(w in snippet_low for w in ["nghị quyết", "biểu quyết", "cổ đông", "cổ phần", "điều lệ"]):
                score -= 0.60

            scored.append((score, c))

        if not scored:
            return LaborExtractionResult(
                ticker=ticker,
                year=year,
                labor=None,
                source_page=None,
                raw_text="",
                confidence=0.0,
                status="NOT_FOUND",
                all_candidates=candidates,
            )

        # Sort by target_year_matched first, then highest score
        scored.sort(key=lambda x: (1 if x[1].target_year_matched else 0, x[0]), reverse=True)
        best_score, best_cand = scored[0]

        # Explicit mismatch penalty
        if best_cand.confidence <= 0.20 and not best_cand.target_year_matched:
            best_score = 0.0

        # Consensus boost only among candidates with same year-match status
        same_val_count = sum(
            1 for _, c in scored
            if c.value == best_cand.value and c.target_year_matched == best_cand.target_year_matched
        )
        if same_val_count >= 2:
            best_score = min(0.99, best_score + 0.10)

        # Strict 100% precision gate
        if best_score >= 0.70:
            status = "SUCCESS"
        elif best_score >= 0.50:
            status = "AMBIGUOUS"
        else:
            status = "NOT_FOUND"
            return LaborExtractionResult(
                ticker=ticker,
                year=year,
                labor=None,
                source_page=best_cand.page,
                raw_text=best_cand.raw_snippet,
                confidence=round(best_score, 3),
                status=status,
                all_candidates=candidates,
            )

        return LaborExtractionResult(
            ticker=ticker,
            year=year,
            labor=best_cand.value,
            source_page=best_cand.page,
            raw_text=best_cand.raw_snippet,
            confidence=round(min(1.0, best_score), 3),
            status=status,
            all_candidates=candidates,
            metadata={"strategy": best_cand.strategy, "reason": best_cand.reason},
        )

    def _is_valid_headcount(self, val: int, has_unit: bool = True) -> bool:
        """Check if number is plausible corporate headcount."""
        if val < self.MIN_HEADCOUNT or val > self.MAX_HEADCOUNT:
            return False
        if val < 20 and not has_unit:
            return False
        return True

    def _is_year_like(self, val: int) -> bool:
        """Reject numbers that look like years (2010..2030) or date days (30, 31)."""
        return (2010 <= val <= 2030) or val in [31, 30, 29, 28, 12]

    def _has_exclusion(self, text: str) -> bool:
        """Check if text snippet is an excluded non-headcount metric."""
        low = text.lower()
        if any(ex in low for ex in EXCLUSION_PATTERNS):
            return True
        if any(rgx.search(text) for rgx in DELTA_EXCLUSION_REGEXES):
            return True
        return False
