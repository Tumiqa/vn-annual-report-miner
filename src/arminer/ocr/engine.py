# -*- coding: utf-8 -*-
"""
arminer.ocr.engine
===================
Hybrid OCR Engine — trích xuất text từ PDF.

Hỗ trợ 3 backend (tự động chọn):
1. PyMuPDF get_text() cho native PDF (nhanh nhất)
2. EasyOCR cho scanned pages (không cần cài thêm binary, hỗ trợ tiếng Việt)
3. Tesseract OCR fallback (cần cài tesseract binary)

Image preprocessing pipeline tăng chất lượng OCR:
- Grayscale → AutoContrast → Sharpen → Contrast boost
- Vietnamese post-processing corrections cho dấu tiếng Việt
"""

from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path
from typing import List, Optional

_OCR_SEMAPHORE = threading.Semaphore(2)  # Giới hạn tối đa 2 tác vụ OCR đồng thời tránh nghẽn CPU/RAM

from loguru import logger


# ── Vietnamese OCR post-processing corrections ────────────────────────────
# Map: common EasyOCR/Tesseract misreads → đúng tiếng Việt
_VN_CORRECTIONS = {
    # ── CỔ PHẦN (Joint Stock) ──
    "CỔ PHẢN": "CỔ PHẦN",
    "CỎ PHẦN": "CỔ PHẦN",
    "CỎ PIIẦN": "CỔ PHẦN",
    "CỎ PIIÀN": "CỔ PHẦN",
    "CỎ PIẦN": "CỔ PHẦN",
    "CỎ PHẢN": "CỔ PHẦN",
    "CÔ PHẦN": "CỔ PHẦN",
    "CÔ PHAN": "CỔ PHẦN",
    "CỎ PHAN": "CỔ PHẦN",
    "CỔ PHAN": "CỔ PHẦN",
    "CỔ PHẨN": "CỔ PHẦN",
    "CỔ PHÀN": "CỔ PHẦN",
    "PIIẦN": "PHẦN",
    "PIIÀN": "PHẦN",
    "PIẦN": "PHẦN",
    # ── THƯỜNG NIÊN (Annual) ──
    "THƯÒNG NIÊN": "THƯỜNG NIÊN",
    "THUÒNG NIÊN": "THƯỜNG NIÊN",
    "THUONG NIÊN": "THƯỜNG NIÊN",
    "THUỜNG NIÊN": "THƯỜNG NIÊN",
    "THƯỞNG NIÊN": "THƯỜNG NIÊN",
    "THUONG NIEN": "THƯỜNG NIÊN",
    "THƯÒNG": "THƯỜNG",
    "THUÒNG": "THƯỜNG",
    "THUONG": "THƯỜNG",
    "THUỜNG": "THƯỜNG",
    # ── CÔNG TY (Company) ──
    "CÔNO TY": "CÔNG TY",
    "CONG TY": "CÔNG TY",
    "CÔNG TỸ": "CÔNG TY",
    "CỒNG TY": "CÔNG TY",
    # ── BÁO CÁO (Report) ──
    "BÁO CÁ0": "BÁO CÁO",
    "BAO CAO": "BÁO CÁO",
    "BAO CÁO": "BÁO CÁO",
    "BÁO CA0": "BÁO CÁO",
    # ── DƯỢC / ĐƯỢC ──
    "DUỢC": "DƯỢC",
    "DUOC": "DƯỢC",
    "DUQC": "DƯỢC",
    "ĐUỢC": "ĐƯỢC",
    # ── ĐỊA CHỈ / ĐƯỜNG (Address terms) ──
    "Đuờng": "Đường",
    "Đja": "Địa",
    "Đia": "Địa",
    "Hả Nội": "Hà Nội",
    # ── NGƯỜI ──
    "NGUỜI": "NGƯỜI",
    "NGUOI": "NGƯỜI",
    # ── VIỆT NAM ──
    "ĐỒNG VlỆT NAM": "ĐỒNG VIỆT NAM",
    "VIET NAM": "VIỆT NAM",
    "VIÊT NAM": "VIỆT NAM",
    "VlỆT NAM": "VIỆT NAM",
    # ── Financial governance terms ──
    "HỘI ĐỒNO": "HỘI ĐỒNG",
    "QUAN TRI": "QUẢN TRỊ",
    "BAN KIEM SOAT": "BAN KIỂM SOÁT",
    "TAI CHINH": "TÀI CHÍNH",
    "DOANH NGHIÊP": "DOANH NGHIỆP",
    "DOANH NGHIEP": "DOANH NGHIỆP",
    # ── Misc ──
    "0P ": "CP ",   # 0(zero)P → CP (Cổ Phần)
    "PHẢN DƯỢC": "PHẦN DƯỢC",  # Cổ Phản Dược → Cổ Phần Dược
    "PHẨN ": "PHẦN ",
}


class OCREngine:
    """
    Trích xuất text từ PDF — tự động phân loại native vs scanned.

    Strategy:
    1. Thử PyMuPDF get_text() trước (nhanh, chính xác cho native PDF)
    2. Nếu text quá ít → dùng EasyOCR (hoặc Tesseract) cho scanned pages
       với image preprocessing để tăng chất lượng nhận dạng
    """

    BACKENDS = ("easyocr", "tesseract")

    def __init__(
        self,
        ocr_backend: str = "auto",
        tesseract_lang: str = "vie+eng",
        tesseract_config: str = "--oem 3 --psm 6",
        easyocr_langs: Optional[List[str]] = None,
        min_text_per_page: int = 400,
        dpi: int = 200,
        use_gpu: Optional[bool] = None,
        preprocess: bool = True,
    ):
        """
        Args:
            ocr_backend: "auto" | "easyocr" | "tesseract"
                - auto: thử easyocr trước, fallback tesseract
            tesseract_lang: ngôn ngữ cho Tesseract (mặc định vie+eng)
            tesseract_config: config cho Tesseract
            easyocr_langs: ngôn ngữ cho EasyOCR (mặc định ["vi", "en"])
            min_text_per_page: ngưỡng ký tự tối thiểu để coi là native text
            dpi: độ phân giải render cho OCR (300 = chính xác, 200 = nhanh)
            use_gpu: dùng GPU cho EasyOCR (None = tự động phát hiện CUDA)
            preprocess: áp dụng image preprocessing trước OCR (khuyến nghị True)
        """
        self.ocr_backend = ocr_backend
        self.tesseract_lang = tesseract_lang
        self.tesseract_config = tesseract_config
        self.easyocr_langs = easyocr_langs or ["vi", "en"]
        self.min_text_per_page = min_text_per_page
        # Resolve flexible DPI: passed argument > ARMINER_OCR_DPI env var > 200 (default)
        if dpi is None or (isinstance(dpi, int) and dpi <= 0):
            env_dpi = os.environ.get("ARMINER_OCR_DPI")
            self.dpi = int(env_dpi) if env_dpi and env_dpi.isdigit() else 200
        else:
            self.dpi = int(dpi)

        # Auto-detect CUDA GPU for hardware acceleration (e.g. Google Colab / GPU servers)
        if use_gpu is None:
            try:
                import torch
                self.use_gpu = bool(torch.cuda.is_available())
                if self.use_gpu:
                    logger.info(f"OCREngine: CUDA GPU hardware acceleration enabled ({torch.cuda.get_device_name(0)})")
            except Exception:
                self.use_gpu = False
        else:
            self.use_gpu = use_gpu

        self.preprocess = preprocess

        # Lazy-initialized (tốn RAM, chỉ init khi cần)
        self._easyocr_reader = None
        self._resolved_backend: Optional[str] = None

    # ── Backend detection ──────────────────────────────────────────────

    def _resolve_backend(self) -> str:
        """Xác định backend OCR khả dụng."""
        if self._resolved_backend:
            return self._resolved_backend

        if self.ocr_backend != "auto":
            self._resolved_backend = self.ocr_backend
            return self._resolved_backend

        # Auto-detect: ưu tiên Tesseract nếu có binary và pytesseract
        from arminer.utils.env import detect_tesseract_path, setup_tesseract
        tess_bin = detect_tesseract_path()
        if tess_bin:
            try:
                import pytesseract  # noqa: F401
                setup_tesseract()
                self._resolved_backend = "tesseract"
                logger.info(f"OCR backend: Tesseract (auto-detected: {tess_bin})")
                return self._resolved_backend
            except ImportError:
                pass
                
        # Fallback: easyocr
        try:
            import easyocr  # noqa: F401
            self._resolved_backend = "easyocr"
            logger.info("OCR backend: EasyOCR (fallback)")
            return self._resolved_backend
        except ImportError:
            pass

        logger.warning("No OCR backend available. Scanned pages will be empty.")
        self._resolved_backend = "none"
        return self._resolved_backend

    def _get_easyocr_reader(self):
        """Lazy-init EasyOCR reader."""
        if self._easyocr_reader is None:
            import easyocr
            logger.info(f"Initializing EasyOCR reader ({self.easyocr_langs})...")
            self._easyocr_reader = easyocr.Reader(
                self.easyocr_langs,
                gpu=self.use_gpu,
                verbose=False,
            )
            logger.info("EasyOCR reader ready")
        return self._easyocr_reader

    # ── Main extraction ────────────────────────────────────────────────

    def extract_text(self, pdf_path: str | Path, ocr_mode: str = "smart", dpi: Optional[int] = None) -> str:
        """
        Extract text từ PDF file theo cơ chế Smart Hybrid thông minh:
        1. Trang nào có native text (>= 50 chars) -> Giữ nguyên 100% native text (tốc độ < 0.001s/trang).
        2. Trang nào ít text (< 50 chars): Phân tích xem có ảnh scan lớn (>= 400x400) không.
           - Nếu có ảnh lớn -> Đánh dấu là trang scan thực sự (báo cáo kiểm toán có dấu đỏ).
           - Nếu không có ảnh lớn (trang bìa lót, trang trống) -> Giữ nguyên, không OCR vô nghĩa.
        3. Chỉ kích hoạt OCR cho đúng các trang scan thực sự.
        
        Args:
            pdf_path: Đường dẫn file PDF.
            ocr_mode: "smart" (mặc định) | "fast" (chỉ lấy native) | "force_ocr" (ép OCR)
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        try:
            try:
                import pymupdf as fitz
            except ImportError:
                import fitz
        except ImportError:
            raise ImportError("PyMuPDF is required. Run: pip install PyMuPDF")

        doc = fitz.open(str(pdf_path))
        pages_text: List[str] = []
        scanned_pages: List[int] = []

        extract_flags = fitz.TEXT_DEHYPHENATE | fitz.TEXT_PRESERVE_WHITESPACE

        import unicodedata

        # Phase 1: Smart Hybrid Page Analysis — Xử lý triệt để 100% các trường hợp PDF
        for i, page in enumerate(doc):
            p_text = page.get_text(flags=extract_flags).strip()
            if p_text:
                p_text = unicodedata.normalize("NFC", p_text)

            if ocr_mode == "fast":
                pages_text.append(p_text)
                continue

            if ocr_mode == "force_ocr":
                scanned_pages.append(i)
                pages_text.append(p_text)
                continue

            # Kiểm tra chất lượng text native (phát hiện lỗi CID font / font mã hóa hỏng)
            alnum_chars = sum(1 for c in p_text if c.isalnum())
            is_corrupted = (
                p_text.count("(cid:") >= 5
                or p_text.count("\ufffd") >= 5
                or (len(p_text) >= 50 and (alnum_chars / len(p_text)) < 0.25)
            )

            # Phân tích toàn diện hình ảnh trên trang (xử lý cả ảnh đơn lẫn trang ghép từ 4-5 ảnh nhỏ/lát cắt)
            imgs = page.get_images()
            total_img_pixels = 0
            max_img_pixels = 0
            has_substantial_single_img = False

            if imgs:
                for img_info in imgs:
                    try:
                        base_img = doc.extract_image(img_info[0])
                        if base_img:
                            w = base_img.get("width", 0)
                            h = base_img.get("height", 0)
                            px = w * h
                            total_img_pixels += px
                            if px > max_img_pixels:
                                max_img_pixels = px
                            if w >= 300 or h >= 200:
                                has_substantial_single_img = True
                    except Exception:
                        pass

            # TRƯỜNG HỢP 1: Văn bản native dày dặn, chuẩn xác (>= 300 ký tự và không hỏng font)
            # -> Giữ nguyên 100%, tốc độ < 0.001s, không tốn tài nguyên OCR.
            if len(p_text) >= 300 and alnum_chars >= 60 and not is_corrupted:
                pages_text.append(p_text)
                continue

            # TRƯỜNG HỢP 2: Văn bản native ngắn (50 <= len < 300 ký tự)
            # Kiểm tra xem đây là trang ngắn thật hay trang scan có đóng dấu số trang/header watermark (CafeF, stamp...)
            if len(p_text) >= 50 and not is_corrupted:
                if total_img_pixels >= 400_000:
                    # Trang scan tài liệu nhưng có header/footer điện tử -> Kích hoạt OCR kết hợp
                    scanned_pages.append(i)
                    pages_text.append(p_text)
                else:
                    # Trang văn bản ngắn tự nhiên (lời đề tặng, trích dẫn) -> Giữ nguyên
                    pages_text.append(p_text)
                continue

            # TRƯỜNG HỢP 3: Văn bản rất ít (< 50 ký tự) hoặc font bị hỏng
            # Phân biệt giữa "Trang scan/ghép ảnh" vs "Trang trắng/bìa lót"
            has_scanned_visual = (
                total_img_pixels >= 50_000
                or max_img_pixels >= 30_000
                or (len(imgs) >= 1 and has_substantial_single_img)
            )

            if has_scanned_visual or is_corrupted:
                # Trang scan thực sự (bao gồm trang ghép từ 4-5 ảnh lát cắt như AAA 2018, AAA 2019)
                scanned_pages.append(i)
                pages_text.append(p_text)
            else:
                # Trang trắng, trang bìa lót không có hình ảnh đáng kể -> Bỏ qua OCR để tiết kiệm tài nguyên
                pages_text.append(p_text)

        # Phase 2: Chạy OCR an toàn cho các trang scan thực sự
        active_dpi = dpi or self.dpi
        if scanned_pages and ocr_mode != "fast":
            logger.info(
                f"Smart Hybrid: PDF {pdf_path.name} có {len(scanned_pages)}/{len(pages_text)} "
                f"trang scan thực sự cần OCR (DPI={active_dpi})"
            )
            ocr_texts = self._ocr_pages(doc, pdf_path, scanned_pages, dpi=active_dpi)
            for page_idx, ocr_text in zip(scanned_pages, ocr_texts):
                orig = pages_text[page_idx]
                if ocr_text and ocr_text.strip():
                    # Kết hợp native text với ocr text để không bao giờ mất thông tin
                    pages_text[page_idx] = f"{orig}\n{ocr_text}".strip() if orig else ocr_text.strip()

        doc.close()

        full_text = "\n\n".join(pages_text)
        full_text = self._clean_text(full_text)

        logger.info(
            f"Extracted {len(full_text)} chars from {pdf_path.name} "
            f"({len(pages_text)} pages, {len(scanned_pages)} OCR)"
        )
        return full_text

    def _ocr_pages(self, doc, pdf_path: Path, page_indices: List[int], dpi: Optional[int] = None) -> List[str]:
        """OCR các trang scanned — tự động chọn backend với semaphore giới hạn tải CPU/RAM."""
        with _OCR_SEMAPHORE:
            backend = self._resolve_backend()
            active_dpi = dpi or self.dpi

            if backend == "easyocr":
                return self._ocr_easyocr(doc, page_indices, dpi=active_dpi)
            elif backend == "tesseract":
                return self._ocr_tesseract(doc, page_indices, dpi=active_dpi)
            else:
                logger.warning(
                    f"No OCR backend — {len(page_indices)} scanned pages skipped. "
                    "Install: pip install easyocr"
                )
                return [""] * len(page_indices)

    # ── Image preprocessing ────────────────────────────────────────────

    def _preprocess_image(self, pix):
        """
        Tiền xử lý ảnh trước OCR — tăng chất lượng nhận dạng đáng kể.

        Pipeline:
        1. Grayscale     → loại nhiễu màu, OCR chỉ cần luminance
        2. AutoContrast  → cân bằng histogram, giúp scan mờ/tối
        3. Sharpen       → làm nét cạnh chữ, quan trọng cho dấu tiếng Việt
        4. Contrast ×1.4 → tách chữ rõ hơn khỏi nền

        Returns:
            numpy.ndarray (RGB) — input trực tiếp cho EasyOCR (nhanh hơn PNG bytes)
        """
        try:
            from PIL import Image, ImageEnhance, ImageFilter, ImageOps
            import numpy as np
        except ImportError:
            logger.debug("Pillow/numpy not available, skipping preprocessing")
            return pix.tobytes("png")

        # Pixmap → PIL Image
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        # 1. Grayscale — loại color noise, OCR chỉ cần luminance
        img = img.convert("L")

        # 2. AutoContrast — stretch histogram, normalize brightness
        img = ImageOps.autocontrast(img, cutoff=0.5)

        # 3. DETAIL filter — nhẹ nhàng hơn SHARPEN, giữ nét dấu tiếng Việt
        #    (SHARPEN quá mạnh có thể méo dấu ơ/ư/ầ/ổ)
        img = img.filter(ImageFilter.DETAIL)

        # 4. Contrast boost nhẹ — tách chữ khỏi nền, không quá mạnh
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.3)

        # → RGB numpy array (EasyOCR nhận ndarray trực tiếp, nhanh hơn PNG)
        return np.array(img.convert("RGB"))

    def _preprocess_image_pil(self, pix):
        """
        Preprocessing trả về PIL Image — dùng cho Tesseract backend.
        """
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps

        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        img = img.convert("L")
        img = ImageOps.autocontrast(img, cutoff=0.5)
        img = img.filter(ImageFilter.DETAIL)
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.3)
        return img.convert("RGB")

    # ── EasyOCR backend ────────────────────────────────────────────────

    def _ocr_easyocr(self, doc, page_indices: List[int], dpi: Optional[int] = None) -> List[str]:
        """
        OCR bằng EasyOCR — với image preprocessing và Vietnamese post-processing.
        """
        results: List[str] = []
        reader = self._get_easyocr_reader()
        start_time = time.time()
        total = len(page_indices)
        active_dpi = dpi or self.dpi

        for i, page_idx in enumerate(page_indices):
            page_start = time.time()
            try:
                page = doc[page_idx]
                pix = page.get_pixmap(dpi=active_dpi)

                # Preprocessing
                if self.preprocess:
                    img_input = self._preprocess_image(pix)
                else:
                    img_input = pix.tobytes("png")

                # Giải phóng pixmap ngay → tiết kiệm RAM
                del pix

                # OCR
                ocr_results = reader.readtext(
                    img_input,
                    detail=0,
                    paragraph=True,
                )
                text = "\n".join(ocr_results).strip()

                # Vietnamese post-processing
                text = self._postprocess_vietnamese(text)
                results.append(text)

                # Giải phóng image array
                del img_input

                # Progress + ETA (mỗi 5 trang hoặc trang cuối)
                page_elapsed = time.time() - page_start
                if (i + 1) % 5 == 0 or (i + 1) == total:
                    total_elapsed = time.time() - start_time
                    avg = total_elapsed / (i + 1)
                    eta = avg * (total - i - 1)
                    logger.info(
                        f"  EasyOCR: {i + 1}/{total} pages "
                        f"({page_elapsed:.1f}s/page, ETA ~{eta:.0f}s)"
                    )

            except Exception as e:
                logger.warning(f"EasyOCR failed on page {page_idx + 1}: {e}")
                results.append("")

        total_elapsed = time.time() - start_time
        logger.info(f"  EasyOCR done: {total} pages in {total_elapsed:.1f}s")
        return results

    # ── Tesseract backend ──────────────────────────────────────────────

    def _ocr_tesseract(self, doc, page_indices: List[int], dpi: Optional[int] = None) -> List[str]:
        """OCR bằng Tesseract — với image preprocessing."""
        results: List[str] = []

        try:
            import pytesseract
            from PIL import Image
        except ImportError:
            logger.warning(
                "Tesseract dependencies missing. "
                "Install: pip install pytesseract pillow"
            )
            return [""] * len(page_indices)

        # Auto-configure tesseract binary path & tessdata
        from arminer.utils.env import setup_tesseract
        setup_tesseract()

        os.environ["OMP_THREAD_LIMIT"] = "1"

        start_time = time.time()
        total = len(page_indices)
        active_dpi = dpi or self.dpi

        for i, page_idx in enumerate(page_indices):
            page_start = time.time()
            try:
                page = doc[page_idx]
                pix = page.get_pixmap(dpi=active_dpi)

                # Preprocessing
                if self.preprocess:
                    img = self._preprocess_image_pil(pix)
                else:
                    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                del pix

                text = pytesseract.image_to_string(
                    img,
                    lang=self.tesseract_lang,
                    config=self.tesseract_config,
                    timeout=45,
                )
                text = self._postprocess_vietnamese(text.strip())
                results.append(text)

                del img

                # Progress
                page_elapsed = time.time() - page_start
                if (i + 1) % 5 == 0 or (i + 1) == total:
                    total_elapsed = time.time() - start_time
                    avg = total_elapsed / (i + 1)
                    eta = avg * (total - i - 1)
                    logger.info(
                        f"  Tesseract: {i + 1}/{total} pages "
                        f"({page_elapsed:.1f}s/page, ETA ~{eta:.0f}s)"
                    )

            except Exception as e:
                logger.warning(f"Tesseract OCR failed on page {page_idx + 1}: {e}")
                results.append("")

        total_elapsed = time.time() - start_time
        logger.info(f"  Tesseract done: {total} pages in {total_elapsed:.1f}s")
        return results

    # ── Post-processing ────────────────────────────────────────────────

    def _postprocess_vietnamese(self, text: str) -> str:
        """
        Sửa lỗi OCR phổ biến cho tiếng Việt.

        Hai giai đoạn:
        1. Exact string matching — nhanh, an toàn
        2. Regex patterns — cho các lỗi có cấu trúc
        """
        # Phase 1: Exact replacements
        for wrong, right in _VN_CORRECTIONS.items():
            text = text.replace(wrong, right)

        # Phase 2: Regex-based context corrections
        # "Cổ Phản" → "Cổ Phần" ("Cổ Phản" không phải cụm từ tiếng Việt hợp lệ)
        text = re.sub(r'[Cc]ổ\s+[Pp]hản', lambda m: m.group().replace('hản', 'hần').replace('HẢN', 'HẦN'), text)

        # Fix l→l (lowercase L) thường bị nhầm với I/1 trong URL
        # "http:Jlwww" → "http://www", "http:llwww" → "http://www"
        text = re.sub(r'http:[JIl/]+www', 'http://www', text)

        return text

    def _clean_text(self, text: str) -> str:
        """
        Làm sạch text sau extraction.

        Chỉ loại bỏ:
        - Control characters (trừ \\n, \\t)
        - Whitespace thừa
        - Dòng trống liên tiếp (> 2)

        Chuẩn hóa:
        - Typographic ligatures (fi, fl, ffi, ffl) và soft-hyphens (\\xad)
        - Unicode NFC
        - Thống nhất quy chuẩn đặt dấu tiếng Việt (hòa/hoà, hóa/hoá, thủy/thuỷ)
        """
        import unicodedata

        # 1. Khử typographic ligatures, soft-hyphens và zero-width spaces
        for lig, rep in [
            ('\ufb01', 'fi'), ('\ufb02', 'fl'), ('\ufb00', 'ff'),
            ('\ufb03', 'ffi'), ('\ufb04', 'ffl'), ('\ufb05', 'st'), ('\ufb06', 'st'),
            ('\xad', ''), ('\u200b', ''), ('\u200c', ''), ('\u200d', ''), ('\ufeff', ''),
            ('\xa0', ' '),
        ]:
            text = text.replace(lig, rep)

        # 2. Chuẩn hóa Unicode NFC toàn diện
        text = unicodedata.normalize("NFC", text)

        # 3. Đồng nhất quy chuẩn dấu tiếng Việt (chuyển kiểu mới hoá/hoà/thuỷ về kiểu chuẩn hóa/hòa/thủy)
        for modern, trad in [
            ('oà', 'òa'), ('oá', 'óa'), ('oả', 'ỏa'), ('oã', 'õa'), ('oạ', 'ọa'),
            ('Oà', 'Òa'), ('Oá', 'Óa'), ('Oả', 'Ỏa'), ('Oã', 'Õa'), ('Oạ', 'Ọa'),
            ('oè', 'òe'), ('oé', 'óe'), ('oẻ', 'ỏe'), ('oẽ', 'õe'), ('oẹ', 'ọe'),
            ('Oè', 'Òe'), ('Oé', 'Óe'), ('Oẻ', 'Ỏe'), ('Oẽ', 'Õe'), ('Oẹ', 'Ọe'),
            ('uỳ', 'ùy'), ('uý', 'úy'), ('uỷ', 'ủy'), ('uỹ', 'ũy'), ('uỵ', 'ụy'),
            ('Uỳ', 'Ùy'), ('Uý', 'Úy'), ('Uỷ', 'Ủy'), ('Uỹ', 'Ũy'), ('Uỵ', 'Ụy'),
        ]:
            text = text.replace(modern, trad)

        # 4. Loại control characters (trừ \n, \t)
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

        # 5. Chuẩn hóa whitespace (giữ nguyên \n)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{4,}', '\n\n\n', text)

        return text.strip()
