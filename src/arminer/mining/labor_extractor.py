# -*- coding: utf-8 -*-
"""
arminer.mining.labor_extractor
==============================
Lean & High-Precision Total Employee Extractor for Vietnamese Annual Reports.

Target:
    LABOR(ticker, year) = Total headcount of the enterprise at fiscal year-end (31/12).

Output:
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

        # Units for employees (Vietnamese + English + unaccented variations)
        self.unit_re = (
            r"(?:người|lao\s*động|nhân\s*viên|cb\s*[-–]\s*cnv|cbcnv|cbnv|cán\s*bộ|cán\s*bộ\s*nhân\s*viên|"
            r"người\s*lao\s*động|nhân\s*sự|lao\s*dng|nhan\s*vien|can\s*b[oộ]?|employees?|workforce|staff|personnel|people|headcount)"
        )
        unit_opt = rf"(?:\s*(?P<unit>{self.unit_re}))?"
        unit_req = rf"\s*(?P<unit>{self.unit_re})"

        # Numbers: 1.750, 54,646, 1072, 2152, 48
        num_re = r"(?P<val>\d{1,3}(?:[.,]\d{3})+|\d{4,6}|\d{1,3})"

        date_anchor = (
            r"(?:(?:tại|vào|đến|tính\s+đến|ghi\s+nhận\s+tại|thời\s+điểm|ở)?\s*"
            r"(?:thời\s+điểm|ngày)?\s*31[/.\s-]*(?:12|tháng\s*12|december)[/.\s-]*(?:năm\s+)?(?P<date_yr>201\d|202\d)|"
            r"(?:thời\s+điểm\s+)?cuối\s+năm\s+(?P<date_yr2>201\d|202\d)|"
            r"(?:năm\s+tài\s+chính|kết\s+thúc\s+năm)\s+(?P<date_yr3>201\d|202\d))"
        )

        lead_re = (
            r"(?P<lead>(?:tổng\s+số|tổng\s+lượng|tổng\s+cộng|quy\s+mô|lực\s+lượng|đội\s+ngũ|số\s+lượng)\s+"
            r"(?:cán\s*bộ\s*,?\s*)?(?:công\s*nhân\s*)?(?:viên|nhân\s*viên|lao\s*động|người\s*lao\s*động|nhân\s*sự|cbcnv|cbnv)|"
            r"lực\s+lượng\s+cbcnv|lực\s+lượng\s+lao\s+động|đội\s+ngũ\s+nhân\s+sự|tổng\s+nhân\s+sự|tổng\s+lao\s+động|tổng\s+nhân\s+viên|"
            r"total\s+number\s+of\s+employees|total\s+employees|number\s+of\s+employees)"
        )

        verb_re = r"(?:là|was|đạt|có|ở\s+mức|quy\s+mô\s+là|quy\s+mô|bình\s+quân\s+là|bình\s+quân|[:=─–-])\s*"

        # 1. Date First: "Tại ngày 31 tháng 12 năm 2024 số lượng nhân viên công ty mẹ và các công ty con là 4.765 người"
        self.re_date_first = re.compile(
            rf"{date_anchor}[^.\n]{{0,120}}?{lead_re}(?![^.\n]*\b(?:tăng|giảm)\b)[^0-9\n]{{0,60}}?{verb_re}{num_re}{unit_opt}",
            re.IGNORECASE,
        )

        # 2. Lead First: "Số lượng nhân sự tại công ty mẹ AAA thời điểm 31/12/2021 là 1.750 người"
        #    "Tổng số lao động của Công ty tại ngày 31/12/2012 là 1072 người"
        self.re_lead_first = re.compile(
            rf"{lead_re}[^.\n]{{0,100}}?{date_anchor}(?![^.\n]*\b(?:tăng|giảm)\b)[^0-9\n]{{0,60}}?{verb_re}{num_re}{unit_opt}",
            re.IGNORECASE,
        )

        # 3. General Lead with Mandatory Unit: "Tổng số lao động: 1.255 người", "Lực lượng CBCNV là 1.097 người"
        self.re_general_lead = re.compile(
            rf"{lead_re}(?![^.\n]*\b(?:tăng|giảm)\b)[^.\n]{{0,80}}?{verb_re}{num_re}\s*{unit_req}",
            re.IGNORECASE,
        )

        # 4. Comparison in Parentheses: "(tại ngày 31/12/2023 là 2.928 người)" or "(tại ngày 31/12/2021: 1.241 người)"
        self.re_parenthesis = re.compile(
            rf"(?:tại|vào|đến|tính\s+đến|năm)?\s*(?:thời\s+điểm|ngày)?\s*31[/.\s-]*(?:12|tháng\s*12)[/.\s-]*(?:năm\s+)?(?P<comp_yr>201\d|202\d)[^0-9\n]{{0,40}}?{verb_re}{num_re}\s*{unit_req}",
            re.IGNORECASE,
        )

        # 5. English Total
        self.re_en_total = re.compile(
            r"(?:total\s+(?:number\s+of\s+)?(?:employees|workforce|staff|personnel)|had)\s*"
            r"(?:as\s+(?:of|at)\s+31\s+december\s+(?P<year1>201\d|202\d))?"
            r"\s*(?:was|is|reached|:|\s+)\s*"
            rf"{num_re}\b(?!\s*%)"
            r"\s*(?:employees|people|staff|headcount)?"
            r"(?:\s*as\s+(?:of|at)\s+31[/.\s-]*(?:12|december)[/.\s-]*(?P<year2>201\d|202\d))?",
            re.IGNORECASE,
        )

        # 6. Corrupted Font Table (e.g. AAA 2016 style: S0luqng lao tlQng 1737)
        self.re_corrupted_font = re.compile(
            r"(?:S[0oOô]lu[qg]ng\s+lao\s+tlQng|Ngudn\s+nhin\s+lgc)\s*\n?\s*(?P<val>\d{3,5})",
            re.IGNORECASE,
        )

        # 7. BCTC Note Pattern
        self.re_bctc_note = re.compile(
            r"(?:số\s+lượng\s+(?:nhân\s*viên|lao\s*động|người\s*lao\s*động|nhân\s*sự)|number\s+of\s+employees)\b"
            r"(?!\s+(?:thôi\s*việc|nghỉ\s*việc|thuê\s*mới|tuyển\s*dụng|tuyển\s*mới|nữ|nam))"
            r"[^0-9\n]{0,120}?"
            r"(?:(?:tại|vào|đến|tính\s+đến|thời\s+điểm)\s+(?:ngày\s+)?31[/.\s-]*(?:12|tháng\s*12|december)[/.\s-]*(?:năm\s+)?(?P<year>201\d|202\d))"
            r"[^0-9\n]{0,50}?"
            r"(?:là|was|đạt|có|:|=|\s+)\s*"
            rf"{num_re}\b"
            r"(?!\s*%)"
            rf"{unit_opt}",
            re.IGNORECASE,
        )

        # 8. Direct Colon Disclosure (e.g. ICF 2015: "Nhu cầu lao động: + Tổng số : 550 người")
        self.re_direct_colon = re.compile(
            r"(?:(?:nhu\s+cầu|kế\s+hoạch|tình\s+hình)\s+lao\s+động[^.\n]{0,80}?)?"
            r"(?:(?:\+|-|\*|\d+[/.])\s*)?"
            r"(?:tổng\s+số|tổng\s+cộng)\s*[:=]\s*"
            rf"{num_re}\s*{unit_req}",
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

        # Fallback to OCR if PDF has no text layer
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

            # 5. Plan vs Actual Metric Table Strategy (e.g. HVN)
            cands_plan_actual = self._extract_plan_actual_metric_candidates(text, page_num, year)
            candidates.extend(cands_plan_actual)

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
            chunk_size = 2500
            pages = [
                (i + 1, full_text[pos : pos + chunk_size])
                for i, pos in enumerate(range(0, len(full_text), chunk_size))
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

            # Labor keywords
            for kw in [
                "tổng số lao động", "tổng số nhân viên", "tổng số cbcnv",
                "tổng số cán bộ", "tổng số người lao động", "quy mô nhân sự",
                "tổng số nhân sự", "nhân sự trung bình", "nguồn nhân lực",
                "số lượng cán bộ", "số lượng lao động", "số lượng nhân sự",
                "số lượng nhân viên", "lực lượng lao động", "lực lượng cbcnv",
                "cơ cấu lao động", "tình hình nhân sự", "chính sách nhân sự",
                "tổ chức và nhân sự", "thông tin về công ty", "báo cáo tài chính",
                "total employees", "total number of employees", "total workforce",
                "headcount", "number of employees", "can bo, nhan vien",
            ]:
                if kw in low:
                    score += 15

            if any(w in low for w in ["nhân viên", "lao động", "nhân sự", "cbcnv", "workforce", "employees"]):
                score += 5

            if f"31/12/{year_str}" in text or f"31.12.{year_str}" in text or f"31-12-{year_str}" in text:
                score += 20
            elif f"31 tháng 12 năm {year_str}" in text:
                score += 25
            elif year_str in text:
                score += 5

            if "31/12" in text or "cuối năm" in low:
                score += 5

            # Font-corrupted / legacy encoding labor indicators (e.g. AAA 2016)
            if any(w in low for w in ["ngudn nhin lgc", "s0luqng lao", "lao tlqng", "c6ng nhdn", "nhdn sp", "nhdn vi6n", "can bq"]):
                score += 30

            if score >= 10:
                scored_pages.append((score, page_num, text))

        scored_pages.sort(key=lambda x: x[0], reverse=True)
        return [(p_num, txt) for _, p_num, txt in scored_pages[:40]]

    def _extract_narrative_candidates(
        self, text: str, page_num: int, year: int
    ) -> List[LaborCandidate]:
        """Strategy 1: High-confidence regex on narrative sentences."""
        results: List[LaborCandidate] = []
        year_str = str(year)

        # Normalize text to bridge line wraps in sentences
        norm_text = re.sub(r"[ \t]*\n[ \t]*", " ", text)
        CURRENCY_REJECTS = ["đồng", "tỷ", "triệu", "vnd", "usd", "ca mắc", "%", "cổ phần", "cổ phiếu"]

        patterns = [
            (self.re_date_first, "narrative_date_total", 0.98),
            (self.re_lead_first, "narrative_date_total", 0.98),
            (self.re_general_lead, "narrative_direct_total", 0.94),
            (self.re_direct_colon, "narrative_direct_total", 0.94),
            (self.re_parenthesis, "narrative_comparison", 0.92),
            (self.re_en_total, "narrative_english", 0.96),
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

                # Clip snippet to sentence boundaries [.!?;\n] so exclusions from adjacent sentences do not spill over
                before_text = norm_text[:m.start()]
                after_text = norm_text[m.end():]
                m_prev_punct = list(re.finditer(r"[.!?;\n]", before_text))
                sent_start = m_prev_punct[-1].end() if m_prev_punct else max(0, m.start() - 60)
                sent_start = max(sent_start, m.start() - 80)

                m_next_punct = re.search(r"[.!?;\n]", after_text)
                sent_end = (m.end() + m_next_punct.start()) if m_next_punct else min(len(norm_text), m.end() + 60)
                sent_end = min(sent_end, m.end() + 60)

                snippet = norm_text[sent_start:sent_end].strip()
                if self._has_exclusion(snippet):
                    continue

                matched_yr = None
                groups = m.groupdict()
                for yk in ["date_yr", "date_yr2", "date_yr3", "comp_yr", "year1", "year2"]:
                    if yk in groups and groups[yk]:
                        matched_yr = groups[yk]
                        break

                target_year_matched = False
                conf = base_conf
                if matched_yr:
                    if matched_yr == year_str:
                        target_year_matched = True
                    else:
                        target_year_matched = False
                        conf = 0.15  # Explicitly belongs to another year (e.g. comparative year)
                elif year_str in snippet:
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
            "theo trình độ lao động",
            "cơ cấu lao động",
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
                # Scan lines after year sequence for metric header
                start_search = years_seq[-1][1] + 1
                for i in range(start_search, min(len(lines), start_search + 25)):
                    l = lines[i].strip()
                    # Skip rate/percentage/delta headers or broken trailing paren
                    if (l.endswith(")") and "(" not in l) or any(bad in l.lower() for bad in ["tăng/giảm", "tỷ lệ", "tỷ trọng", "%", "thôi việc", "nghỉ việc", "thuê mới", "tuyển", "đào tạo", "chi phí", "thu nhập"]):
                        continue
                    if re.search(r"(?:/|%\s*[/)]|\btăng\b|\bgiảm\b)", l.lower()):
                        continue
                    if any(k in l.lower() for k in TABLE_METRIC_KEYWORDS):
                        # Gather following numbers
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
            is_labor_header = any(k in low for k in TABLE_METRIC_KEYWORDS)
            if not is_labor_header:
                continue

            window = lines[max(0, i - 4) : min(len(lines), i + 7)]
            snippet = " // ".join(window)

            horiz_years: List[Tuple[int, int]] = []
            for w_line in window:
                # Exclude period titles like 'Giai đoạn 2015 - 2018' or 'GIAI DOAN 2015 - 2019' from being treated as column headers
                w_low = w_line.lower()
                if any(p in w_low for p in ["giai đoạn", "giai doan", "thời kỳ", "thoi ky", "kế hoạch", "ke hoach", "gđ", "gd"]):
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
                        # Strictly reject lines with currency, income, rate, delta, age, gender, qualification
                        if any(b in w_low for b in ["%", "tỷ lệ", "tỷ trọng", "thu nhập", "lương", "triệu đồng", "tỷ đồng", "vnd", "usd", "tuổi", "độ tuổi", "trình độ", "giới tính", "nữ", "nam"]):
                            continue
                        clean_w = re.sub(r"^\s*\d+\s*[=.-]\s*", "", w_line)
                        clean_w = re.sub(r"\d+([.,]\d+)?\s*%", "", clean_w)
                        nums = re.findall(r"\b(?:\d{1,3}(?:[.,]\d{3})+|\d{4,6}|\d{1,3})\b", clean_w)
                        # Ensure row does not just repeat the year headers
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
                                        confidence=0.75,
                                        reason=f"Horizontal multi-year table column {year_str}",
                                    )
                                    results.append(cand)
                            except Exception:
                                pass

            # Direct lines within the labor section window: e.g. "2018 2152" or "Năm 2022 là: 27 người"
            for w_line in window:
                w_low = w_line.lower()
                if any(b in w_low for b in ["%", "tỷ lệ", "tỷ trọng", "thu nhập", "lương", "triệu đồng", "tỷ đồng", "vnd", "usd", "tuổi", "độ tuổi"]):
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
        Must specifically be in an Employee/Labor context (not shareholders, resolutions, or finance).
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
            "thai sản", "nghỉ việc", "thôi việc", "sa thải", "kỷ luật",
            "bctn/bc", "qtct", "thẻ điểm", "tiêu chí đánh giá", "nguyên tắc", "sáng kiến", "giải pháp",
            "ban kiểm toán", "ban điều hành", "khối bán hàng", "chi nhánh phân phối",
        ]

        LABOR_CONTEXT_WORDS = [
            "trình độ", "hợp đồng lao động", "hđlđ", "loại hợp đồng", "giới tính", "lao động",
            "nhân sự", "cán bộ", "nhân viên", "cbcnv", "cbnv", "người lao động", "workforce",
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
                if not any(w in window_low for w in LABOR_CONTEXT_WORDS):
                    continue

                for w_line in window:
                    # Strip decision codes / question codes like 32/QĐ or E.3.20
                    cleaned_w = re.sub(r"\b(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+|[A-Za-z]\.\d+\.\d+)\b", "", w_line)
                    # Strip percentages first to avoid false matches
                    line_no_pct = re.sub(r"\d+([.,]\d+)?\s*%", "", cleaned_w)
                    nums = [n for n in re.findall(r"\b\d{1,3}(?:[.,]\d{3})*\b", line_no_pct) if n not in ["100", "10000", "00", "1", "2", "3", "4", "5", year_str]]
                    for num_idx, n_str in enumerate(nums):
                        val = normalize_number(n_str)
                        # Small numbers (< 50) MUST have explicit labor unit on the line
                        if val < 50 and not any(u in w_line.lower() for u in ["người", "nhân viên", "lao động", "cbcnv"]):
                            continue
                        if val > 60000 and any(m in w_line.lower() for m in ["đồng", "vnd", "lương", "thu nhập"]):
                            continue
                        if self._is_valid_headcount(val) and not self._is_year_like(val) and not self._has_exclusion(window_str):
                            # In multi-column historical breakdown, the latest/last column is the current year
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
                # Look back up to 15 lines to identify table context / header
                lookback = lines[max(0, i - 15) : i]
                lookback_str = " // ".join(lookback)
                lookback_low = lookback_str.lower()

                if any(w in lookback_low for w in REJECT_TABLE_WORDS):
                    continue
                if not any(w in lookback_low for w in LABOR_CONTEXT_WORDS):
                    continue

                # Look forward only 1-2 lines for the total row numbers to prevent picking up subsequent chart titles
                forward = lines[i : min(len(lines), i + 3)]
                forward_str = " // ".join(forward)

                for w_line in forward:
                    cleaned_w = re.sub(r"\b(?:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+|[A-Za-z]\.\d+\.\d+)\b", "", w_line)
                    line_no_pct = re.sub(r"\d+([.,]\d+)?\s*%", "", cleaned_w)
                    nums = re.findall(r"\b\d{1,3}(?:[.,]\d{3})*\b", line_no_pct)
                    for n_str in nums:
                        val = normalize_number(n_str)
                        if val < 50 and not any(u in w_line.lower() for u in ["người", "nhân viên", "lao động", "cbcnv"]):
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
        Note on Labor:
            "Số lượng nhân viên của Công ty và các công ty con tại ngày 31 tháng 12 năm 2021 là 2.445 người"
        """
        results: List[LaborCandidate] = []
        year_str = str(year)

        for m in self.re_bctc_note.finditer(text):
            val_raw = m.group("val")
            val = normalize_number(val_raw)
            if not self._is_valid_headcount(val) or self._is_year_like(val):
                continue

            found_year = m.group("year")
            start = max(0, m.start() - 40)
            end = min(len(text), m.end() + 80)
            snippet = text[start:end].replace("\n", " ").strip()

            matched_year = (found_year == year_str) or (year_str in snippet)
            cand = LaborCandidate(
                value=val,
                raw_snippet=snippet,
                page=page_num,
                target_year_matched=matched_year,
                is_total_signal=True,
                strategy="bctc_notes",
                confidence=0.98 if matched_year else 0.85,
                reason="BCTC Notes official employee disclosure",
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
            "tỷ lệ", "chiếm", "nữ", "nam", "%", "trong tổng số", "tỷ trọng", "trực tiếp", "gián tiếp",
            "độ tuổi", "tuổi", "trình độ", "thời vụ", "bán thời gian", "xuất khẩu", "ngoài nước",
            "chính sách", "hoạt động", "đánh giá", "bảo vệ", "nghị quyết", "kế hoạch",
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
            if len(line) > 60 or any(v in low for v in [" là ", " đạt ", " người", " nhân viên"]):
                continue
            if not METRIC_ROW_REGEX.match(line):
                continue
            if any(bad in low for bad in SUBSET_ROW_REJECTS):
                continue

            forward = lines[i + 1 : min(len(lines), i + 10)]
            if not forward:
                continue

            combined_context = f"{line} " + " ".join(forward[:3]).lower()
            has_unit = any(u in combined_context for u in ["người", "lao động", "nhân viên", "cbcnv", "cbnv"])

            nums = []
            for fl in forward:
                # Row ends upon encountering percentage column (e.g. 98.9%)
                if "%" in fl:
                    break
                fl_low = fl.lower()

                # If nums already collected, stop immediately when a new row title or category begins
                if nums:
                    if not any(ch.isdigit() for ch in fl) and not any(u in fl_low for u in ["người", "nhân viên", "lao động", "cbcnv", "cbnv"]):
                        break
                    if re.match(r"^[A-Za-zÀ-ỹ\s]{3,}", fl) and not any(u in fl_low for u in ["người", "nhân viên", "lao động", "cbcnv"]):
                        break

                if any(bad in fl_low for bad in ["triệu", "tỷ", "đồng", "vnd", "usd", "lương", "thu nhập", "tuổi", "trình độ", "tỷ lệ"]) or fl_low.endswith("đ"):
                    continue
                m_num = re.search(r"\b(\d{1,3}(?:[.,]\d{3})*|\d{2,6})\b", fl)
                if m_num:
                    clean = m_num.group(1).replace(".", "").replace(",", "")
                    if clean.isdigit():
                        int_val = int(clean)
                        # Small numbers (< 50) in a table row must have explicit headcount unit on their line
                        if int_val < 50 and not any(u in fl_low for u in ["người", "nhân viên", "lao động", "cbcnv"]):
                            continue
                        fl_has_unit = has_unit or any(u in fl_low for u in ["người", "lao động", "nhân sự", "nhân viên", "cbcnv", "cbnv"])
                        if self._is_valid_headcount(int_val, has_unit=fl_has_unit) and not self._is_year_like(int_val):
                            nums.append(int_val)

            if nums:
                lookback = lines[max(0, i - 8) : i]
                header_str = " ".join(lookback).lower()
                # Check for explicit year columns in table header
                header_years = re.findall(r"\b(201\d|202\d)\b", " ".join(lookback))
                if header_years and len(header_years) == len(nums) and year_str in header_years:
                    val = nums[header_years.index(year_str)]
                else:
                    # If multiple numbers (e.g. Plan vs Actual), actual realized is the last column
                    val = nums[-1] if len(nums) >= 2 else nums[0]
                snippet = f"{line} -> " + " // ".join(str(n) for n in nums)
                lookback = lines[max(0, i - 8) : i]
                header_str = " ".join(lookback).lower()
                is_target = (year_str in header_str or f"31/12/{year_str}" in header_str)
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

    # =========================================================================
    # Disambiguation & Best Candidate Selection
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

        for c in candidates:
            score = c.confidence

            # Bonus for explicit target year match
            if c.target_year_matched:
                score += 0.35
            elif year_str in c.raw_snippet:
                score += 0.20

            # Bonus for group / consolidated total
            snippet_low = c.raw_snippet.lower()
            if any(w in snippet_low for w in ["công ty con", "tập đoàn", "toàn hệ thống", "hợp nhất"]):
                score += 0.20

            # Bonus for explicit total indicators
            if any(
                w in snippet_low
                for w in [
                    "tổng số", "tổng cộng", "toàn hệ thống", "toàn tập đoàn",
                    "toàn công ty", "total number", "100%", "quy mô", "bình quân",
                ]
            ):
                score += 0.25

            # Penalty for subset terms
            if any(
                w in snippet_low
                for w in [
                    "lao động trực tiếp", "lao động gián tiếp", "trong đó",
                    "chiếm", "nữ", "nam", "thời vụ", "bán thời gian", "bộ phận",
                ]
            ) and "100%" not in c.raw_snippet and "tổng" not in snippet_low:
                score -= 0.40

            # Penalty for suspicious numbers
            if c.value in [year, year - 1, year - 2, 31, 30, 12, 1, 2, 3]:
                score -= 0.60

            # Heavy penalty for small numbers (< 50) without explicit labor unit
            if c.value < 50:
                if not any(u in snippet_low for u in ["người", "nhân viên", "lao động", "cbcnv"]):
                    score -= 0.85
                if any(w in snippet_low for w in ["ban điều hành", "ban kiểm toán", "hđqt", "bộ phận", "chi nhánh", "đợt", "khối", "khen thưởng", "sáng kiến"]):
                    score -= 0.60

            # Penalty for financial terms nearby (only if no explicit labor unit)
            if any(w in snippet_low for w in ["tỷ đồng", "triệu đồng", "đồng/người", "vnd", "usd"]):
                if not any(u in snippet_low for u in ["người", "nhân viên", "lao động", "cbcnv", "cbnv", "cán bộ"]):
                    score -= 0.50

            # Penalty for resolution or shareholder terms
            if any(w in snippet_low for w in ["nghị quyết", "biểu quyết", "cổ đông", "cổ phần", "điều lệ"]):
                score -= 0.60

            # Bonus for high-specificity aligned strategies
            if c.strategy in ["narrative_date_total", "bctc_notes"]:
                score += 0.35
            elif c.strategy in ["narrative_direct_total", "narrative_comparison", "narrative_english", "corrupted_font_table", "table_plan_actual_metric"]:
                score += 0.25
            elif c.strategy in ["table_vertical_multiyear", "table_multiyear"]:
                score += 0.05

            scored.append((score, c))

        # Sort by target_year_matched first, then score
        scored.sort(key=lambda x: (1 if x[1].target_year_matched else 0, x[0]), reverse=True)
        best_score, best_cand = scored[0]

        # If best candidate is an explicit mismatch from another year
        if best_cand.confidence <= 0.20 and not best_cand.target_year_matched:
            best_score = 0.0

        # Consensus boost only among candidates with same year-match status
        same_val_count = sum(
            1 for _, c in scored
            if c.value == best_cand.value and c.target_year_matched == best_cand.target_year_matched
        )
        if same_val_count >= 2:
            best_score = min(0.99, best_score + 0.10)

        if best_score >= 0.70:
            status = "SUCCESS"
        elif best_score >= 0.45:
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
