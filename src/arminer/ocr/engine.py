# -*- coding: utf-8 -*-
"""
arminer.ocr.engine
===================
Hybrid OCR Engine — kế thừa logic từ blockchain_pipeline.
Hỗ trợ: PyMuPDF (native text) + Tesseract (scanned pages).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from loguru import logger


class OCREngine:
    """
    Trích xuất text từ PDF — tự động phân loại native vs scanned.

    Strategy:
    1. Thử PyMuPDF get_text() trước (nhanh, chính xác cho native PDF)
    2. Nếu text quá ít → fallback Tesseract OCR cho scanned pages
    """

    def __init__(self, tesseract_lang: str = "vie+eng",
                 tesseract_config: str = "--oem 3 --psm 6",
                 min_text_per_page: int = 100,
                 use_gpu: bool = False):
        self.tesseract_lang = tesseract_lang
        self.tesseract_config = tesseract_config
        self.min_text_per_page = min_text_per_page
        self.use_gpu = use_gpu

    def extract_text(self, pdf_path: str | Path) -> str:
        """
        Extract text từ PDF file.

        Returns:
            Full text content
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError("PyMuPDF is required. Run: pip install PyMuPDF")

        doc = fitz.open(str(pdf_path))
        pages_text: List[str] = []
        scanned_pages: List[int] = []

        for i, page in enumerate(doc):
            text = page.get_text().strip()

            if len(text) >= self.min_text_per_page:
                pages_text.append(text)
            else:
                scanned_pages.append(i)
                pages_text.append("")  # placeholder

        doc.close()

        # OCR scanned pages
        if scanned_pages:
            logger.info(
                f"PDF has {len(scanned_pages)} scanned pages — running OCR"
            )
            ocr_texts = self._ocr_pages(pdf_path, scanned_pages)
            for page_idx, ocr_text in zip(scanned_pages, ocr_texts):
                pages_text[page_idx] = ocr_text

        full_text = "\n\n".join(pages_text)
        full_text = self._clean_text(full_text)

        logger.info(
            f"Extracted {len(full_text)} chars from {pdf_path.name} "
            f"({len(pages_text)} pages, {len(scanned_pages)} OCR)"
        )
        return full_text

    def _ocr_pages(self, pdf_path: Path, page_indices: List[int]) -> List[str]:
        """OCR các trang scanned bằng Tesseract."""
        results = []

        try:
            import pytesseract
            from pdf2image import convert_from_path
        except ImportError:
            logger.warning(
                "OCR dependencies missing. "
                "Install: pip install vn-annual-report-miner[ocr]"
            )
            return [""] * len(page_indices)

        for page_idx in page_indices:
            try:
                images = convert_from_path(
                    str(pdf_path),
                    first_page=page_idx + 1,
                    last_page=page_idx + 1,
                    dpi=300,
                )

                if images:
                    text = pytesseract.image_to_string(
                        images[0],
                        lang=self.tesseract_lang,
                        config=self.tesseract_config,
                    )
                    results.append(text.strip())
                else:
                    results.append("")

            except Exception as e:
                logger.warning(f"OCR failed for page {page_idx}: {e}")
                results.append("")

        return results

    def _clean_text(self, text: str) -> str:
        """Làm sạch text sau extraction."""
        # Loại control characters (trừ \n, \t)
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

        # Chuẩn hóa whitespace
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Loại header/footer lặp (số trang, tên công ty lặp)
        lines = text.split('\n')
        cleaned_lines = []
        seen_short: dict = {}

        for line in lines:
            stripped = line.strip()
            if len(stripped) < 5:
                continue
            if len(stripped) < 30:
                seen_short[stripped] = seen_short.get(stripped, 0) + 1
                if seen_short[stripped] > 5:
                    continue
            cleaned_lines.append(line)

        return '\n'.join(cleaned_lines).strip()
