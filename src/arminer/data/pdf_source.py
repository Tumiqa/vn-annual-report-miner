# -*- coding: utf-8 -*-
"""
arminer.data.pdf_source
========================
Quản lý nguồn PDF báo cáo thường niên.
Hỗ trợ: Local folder, Zenodo dataset (thanhnp-uel).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from loguru import logger


class PDFSource:
    """
    Quản lý nguồn PDF — tương thích với Zenodo dataset
    (thanhnp-uel/vietnam-listed-companies-annual-reports).
    """

    # Pattern tên file Zenodo: {TICKER}_{YY}N_BCTN.pdf hoặc {TICKER}_{YY}CN_BCTN.pdf (hoặc .txt)
    ZENODO_PATTERN = re.compile(
        r"^(?P<ticker>[A-Z0-9]+)_(?P<yy>\d{2})(?:C?N)_BCTN\.(?:pdf|txt)$",
        re.IGNORECASE,
    )

    @classmethod
    def parse_filename(cls, path: Path | str) -> Optional[Tuple[str, int]]:
        """Parse tên file hoặc path → (ticker, year)."""
        p = Path(path)
        name = p.name

        # 1. Zenodo pattern: VNM_19N_BCTN.pdf → (VNM, 2019)
        m = cls.ZENODO_PATTERN.match(name)
        if m:
            ticker = m.group("ticker").upper()
            yy = int(m.group("yy"))
            year = 2000 + yy if yy < 50 else 1900 + yy
            return (ticker, year)

        # 2. Simple pattern: VNM_2019.pdf / VNM_2019_BCTN.pdf
        m2 = re.match(r"^([A-Z0-9]+)[_\-](\d{4}).*\.(?:pdf|txt)$", name, re.IGNORECASE)
        if m2:
            return (m2.group(1).upper(), int(m2.group(2)))

        # 3. Try parent directory as ticker: {TICKER}/2019_report.pdf
        parent = p.parent.name.replace("MST_", "")
        if re.match(r"^[A-Z0-9]{2,10}$", parent, re.IGNORECASE):
            year_match = re.search(r"(\d{4})", name)
            if year_match:
                return (parent.upper(), int(year_match.group(1)))

        # 4. Nested pattern: {TICKER}/{YEAR}/report.pdf or MST_{TICKER}/{YEAR}/report.pdf
        if len(p.parts) >= 3:
            p_year = p.parent.name
            p_ticker = p.parent.parent.name.replace("MST_", "")
            if re.match(r"^\d{4}$", p_year) and re.match(r"^[A-Z0-9]{2,10}$", p_ticker, re.IGNORECASE):
                return (p_ticker.upper(), int(p_year))

        return None


    def _parse_filename(self, path: Path) -> Optional[Tuple[str, int]]:
        return self.parse_filename(path)

    def __init__(self, source_dir: str | Path,
                 naming_pattern: str = "{ticker}_{yy}N_BCTN.pdf"):
        self.source_dir = Path(source_dir).resolve()
        self.naming_pattern = naming_pattern
        self._index: Optional[Dict[Tuple[str, int], Path]] = None

    def build_index(self) -> Dict[Tuple[str, int], Path]:
        """
        Scan thư mục PDF và xây dựng index: {(ticker, year): path}.

        Hỗ trợ cấu trúc:
        1. Zenodo: full_data/{TICKER}/{TICKER}_{YY}N_BCTN.pdf
        2. Flat: {TICKER}_{YEAR}.pdf
        3. Nested: {TICKER}/{YEAR}/report.pdf
        """
        if self._index is not None:
            return self._index

        self._index = {}

        if not self.source_dir.exists():
            logger.warning(f"PDF source directory not found: {self.source_dir}")
            return self._index

        for pdf in self.source_dir.rglob("*.pdf"):
            parsed = self._parse_filename(pdf)
            if parsed:
                ticker, year = parsed
                self._index[(ticker, year)] = pdf

        logger.info(
            f"PDF index built: {len(self._index)} reports "
            f"from {self.source_dir}"
        )
        return self._index

    def get_pdf(self, ticker: str, year: int) -> Optional[Path]:
        """Lấy đường dẫn PDF cho 1 DN + 1 năm."""
        index = self.build_index()
        return index.get((ticker.upper(), year))

    def get_available_tickers(self) -> List[str]:
        """Danh sách các ticker có PDF."""
        index = self.build_index()
        return sorted(set(t for t, _ in index.keys()))

    def get_available_years(self, ticker: str) -> List[int]:
        """Các năm có PDF cho 1 ticker."""
        index = self.build_index()
        return sorted(y for t, y in index.keys() if t == ticker.upper())

    def get_coverage_stats(self) -> Dict:
        """Thống kê bao phủ."""
        index = self.build_index()
        tickers = self.get_available_tickers()
        years = sorted(set(y for _, y in index.keys()))
        return {
            "total_pdfs": len(index),
            "unique_tickers": len(tickers),
            "year_range": f"{min(years)}-{max(years)}" if years else "N/A",
            "years": years,
        }



class ZenodoDownloader:
    """Tải dataset PDF từ Zenodo."""

    ZENODO_API = "https://zenodo.org/api/records"

    def __init__(self, doi: str = "10.5281/zenodo.20949551"):
        self.doi = doi
        self._record_id = doi.split(".")[-1] if "." in doi else doi

    def download(self, output_dir: str | Path, max_files: int = None) -> Path:
        """
        Tải dataset từ Zenodo.

        Returns:
            Path đến thư mục đã tải
        """
        import requests

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Fetching Zenodo record: {self.doi}")

        url = f"{self.ZENODO_API}/{self._record_id}"
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        files = data.get("files", [])
        logger.info(f"Found {len(files)} files on Zenodo")

        if max_files:
            files = files[:max_files]

        for f in files:
            fname = f["key"]
            furl = f["links"]["self"]
            fpath = output_dir / fname

            if fpath.exists():
                logger.debug(f"Skipping (exists): {fname}")
                continue

            logger.info(f"Downloading: {fname}")
            with requests.get(furl, stream=True, timeout=300) as r:
                r.raise_for_status()
                with open(fpath, "wb") as out:
                    for chunk in r.iter_content(chunk_size=8192):
                        out.write(chunk)

        logger.success(f"Download complete: {output_dir}")
        return output_dir
