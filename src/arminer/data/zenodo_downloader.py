# -*- coding: utf-8 -*-
"""
arminer.data.zenodo_downloader
===============================
Download and cache individual PDFs from Zenodo ZIP archives on-demand
using HTTP Range requests.

No need to download 58 GB ZIP files:
Zenodo supports HTTP Range requests (status 206). We read the ZIP central
directory remotely and stream-extract only the requested PDF files (usually
1-10 MB each), caching them locally in ~/.arminer/zenodo_cache/ for future use.
"""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from loguru import logger


ZENODO_RECORD_ID = "20949551"
ZENODO_BASE_URL = f"https://zenodo.org/api/records/{ZENODO_RECORD_ID}/files"

ARCHIVE_ZIP_MAP = {
    "2000_2005": "vn_bctn_2000_2005.zip",
    "2006_2010": "vn_bctn_2006_2010.zip",
    "2011_2015": "vn_bctn_2011_2015.zip",
    "2016_2020": "vn_bctn_2016_2020.zip",
    "2021_2025": "vn_bctn_2021_2025.zip",
}


def _get_cache_root() -> Path:
    """
    Get or create the Zenodo cache root directory.
    Priority:
    1. Environment variable: ARMINER_CACHE_DIR
    2. Non-C working drive (e.g. D:/.../data/zenodo_cache) to prevent filling OS drive C
    3. Fallback: User home directory (~/.arminer/zenodo_cache)
    """
    env_dir = os.environ.get("ARMINER_CACHE_DIR")
    if env_dir:
        cache_root = Path(env_dir)
    else:
        try:
            cwd = Path.cwd()
            if cwd.drive and cwd.drive.upper() != "C:":
                cache_root = cwd / "data" / "zenodo_cache"
            else:
                cache_root = Path.home() / ".arminer" / "zenodo_cache"
        except Exception:
            cache_root = Path.home() / ".arminer" / "zenodo_cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    return cache_root


class CachedHTTPRangeReader(io.RawIOBase):
    """
    Seekable file-like stream backed by HTTP Range requests with 1MB block caching.
    Allows zipfile.ZipFile to read central directory and extract single files
    from multi-gigabyte remote ZIP archives without downloading the entire file.
    """

    def __init__(self, url: str, block_size: int = 1024 * 1024, session: Optional[requests.Session] = None):
        self.url = url
        self.block_size = block_size
        self.cache: Dict[int, bytes] = {}
        self.pos = 0

        if session is None:
            self.session = requests.Session()
            retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
            self.session.mount("https://", HTTPAdapter(max_retries=retries))
        else:
            self.session = session

        resp = self.session.head(self.url, timeout=30)
        resp.raise_for_status()
        self.size = int(resp.headers.get("content-length", 0))

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self.pos = offset
        elif whence == 1:
            self.pos += offset
        elif whence == 2:
            self.pos = self.size + offset
        self.pos = max(0, min(self.pos, self.size))
        return self.pos

    def _get_block(self, idx: int) -> bytes:
        if idx not in self.cache:
            start = idx * self.block_size
            end = min(start + self.block_size - 1, self.size - 1)
            headers = {"Range": f"bytes={start}-{end}"}
            resp = self.session.get(self.url, headers=headers, timeout=60)
            resp.raise_for_status()
            self.cache[idx] = resp.content
        return self.cache[idx]

    def readinto(self, b) -> int:
        if self.pos >= self.size:
            return 0
        total_read = 0
        target_len = len(b)
        while total_read < target_len and self.pos < self.size:
            block_idx = self.pos // self.block_size
            offset_in_block = self.pos % self.block_size
            block_data = self._get_block(block_idx)
            available = len(block_data) - offset_in_block
            if available <= 0:
                break
            to_copy = min(target_len - total_read, available)
            b[total_read : total_read + to_copy] = block_data[offset_in_block : offset_in_block + to_copy]
            self.pos += to_copy
            total_read += to_copy
        return total_read


class ZenodoDownloader:
    """Download and cache individual PDFs from Zenodo on-demand."""

    def __init__(self, cache_root: Optional[Path] = None):
        self.cache_root = cache_root or _get_cache_root()
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self._session = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        self._session.mount("https://", HTTPAdapter(max_retries=retries))
        self._zip_handles: Dict[str, zipfile.ZipFile] = {}
        self._zip_namelists: Dict[str, Dict[str, str]] = {}  # period -> {normalized_name: full_entry_name}

    def _get_zip_handle(self, archive_period: str) -> Optional[zipfile.ZipFile]:
        """Get or initialize a remote ZipFile handle for the given archive period."""
        if archive_period in self._zip_handles:
            return self._zip_handles[archive_period]

        zip_name = ARCHIVE_ZIP_MAP.get(archive_period)
        if not zip_name:
            logger.error(f"Unknown archive_period: {archive_period}")
            return None

        url = f"{ZENODO_BASE_URL}/{zip_name}/content"
        logger.info(f"Connecting to Zenodo remote ZIP: {zip_name}...")
        try:
            reader = CachedHTTPRangeReader(url=url, session=self._session)
            zf = zipfile.ZipFile(reader)
            self._zip_handles[archive_period] = zf

            # Build fast lookup map: maps both "VCB/VCB_21CN_BCTN.pdf" and "VCB_21CN_BCTN.pdf" to entry
            name_map: Dict[str, str] = {}
            for name in zf.namelist():
                norm = name.replace("\\", "/").lstrip("/")
                name_map[norm] = name
                # also map without "full_data/" prefix
                if norm.startswith("full_data/"):
                    without_prefix = norm[len("full_data/"):]
                    name_map[without_prefix] = name
                # also map by basename
                base = Path(name).name
                if base not in name_map:
                    name_map[base] = name

            self._zip_namelists[archive_period] = name_map
            logger.info(f"Connected to {zip_name}: {len(zf.namelist())} files in catalog")
            return zf
        except Exception as e:
            logger.error(f"Failed to open Zenodo ZIP {zip_name}: {e}")
            return None

    def get_pdf_path(
        self,
        ticker: str,
        year: int,
        archive_period: str,
        relative_path: str,
    ) -> Optional[Path]:
        """
        Get local path to a cached PDF. If not yet cached, stream-extracts it from Zenodo.
        Returns Path to the local PDF file, or None on failure.
        """
        period_dir = self.cache_root / archive_period
        cached_pdf = period_dir / relative_path

        if cached_pdf.exists() and cached_pdf.stat().st_size > 1000:
            return cached_pdf

        # Stream extract single file
        zf = self._get_zip_handle(archive_period)
        if not zf:
            return None

        name_map = self._zip_namelists.get(archive_period, {})
        norm_rel = relative_path.replace("\\", "/").lstrip("/")
        entry_name = name_map.get(norm_rel) or name_map.get(Path(relative_path).name)

        if not entry_name:
            # Try searching in namelist directly
            for n in zf.namelist():
                if Path(n).name.upper() == Path(relative_path).name.upper():
                    entry_name = n
                    break

        if not entry_name:
            logger.error(f"File {relative_path} not found in Zenodo ZIP for {archive_period}")
            return None

        try:
            logger.info(f"Extracting {entry_name} from Zenodo {archive_period}...")
            cached_pdf.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(entry_name) as src, open(cached_pdf, "wb") as dst:
                chunk = src.read(1024 * 1024)
                while chunk:
                    dst.write(chunk)
                    chunk = src.read(1024 * 1024)

            logger.info(f"Successfully cached: {cached_pdf} ({cached_pdf.stat().st_size / (1024*1024):.1f} MB)")
            return cached_pdf
        except Exception as e:
            logger.error(f"Failed extracting {entry_name}: {e}")
            if cached_pdf.exists():
                try:
                    cached_pdf.unlink()
                except Exception:
                    pass
            return None

    def download_reports(
        self,
        reports: List[Dict[str, Any]],
        progress_callback=None,
    ) -> List[Dict[str, Any]]:
        """
        Download multiple reports on-demand and attach 'local_path' to each record.
        """
        total = len(reports)
        for idx, r in enumerate(reports, 1):
            rel_path = r.get("relative_path", "")
            period = r.get("archive_period", "")
            ticker = r.get("ticker", "")
            year = r.get("year", 0)

            # Check if local path already exists (from local storage or previous cache)
            existing = self.cache_root / period / rel_path
            if existing.exists() and existing.stat().st_size > 1000:
                r["local_path"] = str(existing.resolve())
                if progress_callback:
                    progress_callback(idx, total, f"Sẵn sàng trong bộ nhớ: {ticker} ({year})")
                continue

            if progress_callback:
                progress_callback(idx, total, f"Đang tải từ Zenodo: {ticker} ({year}) [{idx}/{total}]...")

            p = self.get_pdf_path(
                ticker=ticker,
                year=year,
                archive_period=period,
                relative_path=rel_path,
            )
            if p and p.exists():
                r["local_path"] = str(p.resolve())
            else:
                r["local_path"] = None

        return reports

    def get_cache_status(self) -> Dict[str, Any]:
        """Report what's currently cached in ~/.arminer/zenodo_cache/."""
        status = {}
        for period, zip_name in ARCHIVE_ZIP_MAP.items():
            period_dir = self.cache_root / period
            if period_dir.exists():
                pdfs = list(period_dir.rglob("*.pdf"))
                total_size = sum(f.stat().st_size for f in pdfs)
                status[period] = {
                    "cached_pdfs": len(pdfs),
                    "total_size_mb": round(total_size / (1024 * 1024), 1),
                }
            else:
                status[period] = {"cached_pdfs": 0, "total_size_mb": 0.0}
        return status

    def clear_cache(self, also_clear_home_c: bool = True) -> Dict[str, Any]:
        """
        Xoa toan bo file PDF trong bo nho dem de giai phong dung luong o dia.
        """
        deleted_count = 0
        freed_bytes = 0

        targets = [self.cache_root]
        if also_clear_home_c:
            home_cache = Path.home() / ".arminer" / "zenodo_cache"
            if home_cache != self.cache_root and home_cache.exists():
                targets.append(home_cache)

        for t in targets:
            if t.exists():
                for p in list(t.rglob("*.pdf")):
                    try:
                        freed_bytes += p.stat().st_size
                        p.unlink()
                        deleted_count += 1
                    except Exception:
                        pass

        logger.info(f"Đã dọn dẹp cache: xóa {deleted_count} file, giải phóng {freed_bytes / (1024*1024):.1f} MB")
        return {
            "deleted_files": deleted_count,
            "freed_mb": round(freed_bytes / (1024 * 1024), 2),
            "current_cache_root": str(self.cache_root),
        }

    # Alias for compatibility
    get_cached_path = get_pdf_path

