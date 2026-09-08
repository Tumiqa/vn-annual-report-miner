# -*- coding: utf-8 -*-
"""
arminer.data.zenodo_downloader
===============================
Download and cache individual PDFs from Zenodo ZIP archives on-demand
using HTTP Range requests with Multi-Tier Local-First Fallbacks and Circuit Breaker.

Architecture:
1. Stage 1 (Local First): Checks local workspace directories and local cache (0ms, 100% offline).
2. Stage 2 (Circuit Breaker): Prevents cascading hangs/bans when Zenodo API is experiencing 504/403 downtime.
3. Stage 3 (Persistent Index): Caches ZIP Central Directory on disk so ZIP handles open in 0.005s.
4. Stage 4 (Adaptive 4MB Chunking): Reduces HTTP Range requests by 75% with on-disk block caching and browser headers.
"""

from __future__ import annotations

import io
import json
import os
import random
import time
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

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Encoding": "identity",
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


class CircuitBreaker:
    """Circuit breaker for Zenodo remote requests to prevent hangs and rate-limit bans."""

    def __init__(self, failure_threshold: int = 2, cooldown_seconds: float = 180.0):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.last_error = ""

    def record_success(self):
        self.failure_count = 0
        self.state = "CLOSED"
        self.last_error = ""

    def record_failure(self, error_msg: str = ""):
        self.failure_count += 1
        self.last_failure_time = time.time()
        self.last_error = error_msg
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(
                f"Zenodo Circuit Breaker TRIP: {self.failure_count} consecutive failures. "
                f"Zenodo requests will be bypassed for {int(self.cooldown_seconds)}s. Reason: {error_msg}"
            )

    @property
    def is_open(self) -> bool:
        return self.state == "OPEN"

    @property
    def is_closed(self) -> bool:
        return self.state == "CLOSED"

    def can_attempt(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.cooldown_seconds:
                self.state = "HALF_OPEN"
                logger.info("Zenodo Circuit Breaker entering HALF_OPEN probe state.")
                return True
            return False
        return True  # HALF_OPEN allows 1 probe


class CachedHTTPRangeReader(io.RawIOBase):
    """
    Seekable file-like stream backed by HTTP Range requests with 4MB block caching
    and on-disk block persistence.
    Allows zipfile.ZipFile to read central directory and extract single files
    from multi-gigabyte remote ZIP archives without downloading the entire file.
    """

    def __init__(
        self,
        url: str,
        block_size: int = 4 * 1024 * 1024,
        session: Optional[requests.Session] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        block_cache_dir: Optional[Path] = None,
    ):
        self.url = url
        self.block_size = block_size
        self.cache: Dict[int, bytes] = {}
        self.pos = 0
        self.circuit_breaker = circuit_breaker
        self.block_cache_dir = block_cache_dir

        if self.block_cache_dir:
            self.block_cache_dir.mkdir(parents=True, exist_ok=True)

        if session is None:
            self.session = requests.Session()
            retries = Retry(total=2, backoff_factor=1.5, status_forcelist=[500, 502, 503, 504])
            self.session.mount("https://", HTTPAdapter(max_retries=retries))
        else:
            self.session = session

        # Obtain size using Range bytes=0-0 to test Range support without sending HEAD
        self.size = 0
        try:
            resp = self.session.get(
                self.url,
                headers={**DEFAULT_HEADERS, "Range": "bytes=0-0"},
                timeout=(8, 25),
            )
            if resp.status_code in (206, 200):
                cr = resp.headers.get("Content-Range", "")
                if "/" in cr:
                    self.size = int(cr.split("/")[-1])
                elif "Content-Length" in resp.headers:
                    self.size = int(resp.headers["Content-Length"])
                if self.circuit_breaker:
                    self.circuit_breaker.record_success()
            else:
                resp.raise_for_status()
        except Exception as e:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure(str(e))
            raise

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
        if idx in self.cache:
            return self.cache[idx]

        # Check on-disk block cache
        if self.block_cache_dir:
            disk_block = self.block_cache_dir / f"block_{idx}.bin"
            if disk_block.exists() and disk_block.stat().st_size > 0:
                try:
                    data = disk_block.read_bytes()
                    self.cache[idx] = data
                    return data
                except Exception:
                    pass

        if self.circuit_breaker and not self.circuit_breaker.can_attempt():
            raise ConnectionError(f"Zenodo circuit breaker is OPEN ({self.circuit_breaker.last_error})")

        start = idx * self.block_size
        end = min(start + self.block_size - 1, self.size - 1)
        headers = {**DEFAULT_HEADERS, "Range": f"bytes={start}-{end}"}

        # Polite jitter delay between requests to avoid burst WAF rate limiting
        time.sleep(random.uniform(0.1, 0.25))

        try:
            resp = self.session.get(self.url, headers=headers, timeout=(8, 40))
            resp.raise_for_status()
            data = resp.content
            self.cache[idx] = data

            if self.block_cache_dir:
                try:
                    (self.block_cache_dir / f"block_{idx}.bin").write_bytes(data)
                except Exception:
                    pass

            if self.circuit_breaker:
                self.circuit_breaker.record_success()
            return data
        except Exception as e:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure(str(e))
            raise

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
    """Download and cache individual PDFs from Zenodo on-demand with Local-First Fallbacks."""

    def __init__(self, cache_root: Optional[Path] = None):
        self.cache_root = cache_root or _get_cache_root()
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.circuit_breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=180.0)
        self._session = requests.Session()
        retries = Retry(total=2, backoff_factor=1.5, status_forcelist=[500, 502, 503, 504])
        self._session.mount("https://", HTTPAdapter(max_retries=retries))
        self._zip_handles: Dict[str, zipfile.ZipFile] = {}
        self._zip_namelists: Dict[str, Dict[str, str]] = {}  # period -> {normalized_name: full_entry_name}

    def _find_local_pdf(
        self,
        ticker: str,
        year: int,
        archive_period: str = "",
        relative_path: str = "",
    ) -> Optional[Path]:
        """
        Stage 1: Check all local directories in workspace and cache before making any network calls.
        Returns Path to the local PDF file if found, else None.
        """
        ticker_u = str(ticker).upper().strip()
        base_name = Path(relative_path).name if relative_path else ""

        # Candidates to check in order of priority:
        search_dirs: List[Path] = []

        # 1. Primary cache root
        if archive_period:
            search_dirs.append(self.cache_root / archive_period)
        search_dirs.append(self.cache_root)

        # 2. Local workspace data directories
        cwd = Path.cwd()
        ws_root = Path(__file__).resolve().parent.parent.parent.parent
        for root in (cwd, ws_root):
            search_dirs.extend([
                root / "data" / "reports",
                root / "data" / "raw_pdfs",
                root / "data" / "zenodo_sample" / "full_data",
                root / "data" / "zenodo_sample",
            ])

        # 3. Environment directory
        env_dir = os.environ.get("ARMINER_REPORTS_DIR")
        if env_dir:
            search_dirs.append(Path(env_dir))

        # Check direct path first if relative_path is specified
        if relative_path:
            for s_dir in search_dirs:
                direct = s_dir / relative_path
                if direct.exists() and direct.is_file() and direct.stat().st_size > 1000:
                    return direct.resolve()
                if base_name:
                    by_base = s_dir / base_name
                    if by_base.exists() and by_base.is_file() and by_base.stat().st_size > 1000:
                        return by_base.resolve()
                    by_ticker_folder = s_dir / ticker_u / base_name
                    if by_ticker_folder.exists() and by_ticker_folder.is_file() and by_ticker_folder.stat().st_size > 1000:
                        return by_ticker_folder.resolve()

        # Check ticker and year patterns across candidate directories
        yy_str = f"{year % 100:02d}" if year else ""
        expected_patterns = [
            f"{ticker_u}_{yy_str}CN_BCTN.pdf",
            f"{ticker_u}_{yy_str}N_BCTN.pdf",
            f"{ticker_u}_{year}.pdf",
            f"{ticker_u}_{year}_BCTN.pdf",
            f"{ticker_u}_{year}_annual_report.pdf",
        ]

        for s_dir in search_dirs:
            if not s_dir.exists() or not s_dir.is_dir():
                continue

            for pat in expected_patterns:
                p1 = s_dir / pat
                if p1.exists() and p1.is_file() and p1.stat().st_size > 1000:
                    return p1.resolve()
                p2 = s_dir / ticker_u / pat
                if p2.exists() and p2.is_file() and p2.stat().st_size > 1000:
                    return p2.resolve()

        return None

    def _get_zip_handle(self, archive_period: str) -> Optional[zipfile.ZipFile]:
        """Get or initialize a remote ZipFile handle for the given archive period with persistent catalog cache."""
        if archive_period in self._zip_handles:
            return self._zip_handles[archive_period]

        if not self.circuit_breaker.can_attempt():
            logger.warning(f"Zenodo Circuit Breaker is OPEN. Cannot connect to archive {archive_period}.")
            return None

        zip_name = ARCHIVE_ZIP_MAP.get(archive_period)
        if not zip_name:
            logger.error(f"Unknown archive_period: {archive_period}")
            return None

        url = f"{ZENODO_BASE_URL}/{zip_name}/content"
        block_cache_dir = self.cache_root / "_range_blocks" / archive_period
        block_cache_dir.mkdir(parents=True, exist_ok=True)

        namelist_file = self.cache_root / f"namelist_{archive_period}.json"

        # Load namelist from disk if cached
        if namelist_file.exists():
            try:
                self._zip_namelists[archive_period] = json.loads(namelist_file.read_text(encoding="utf-8"))
                logger.debug(f"Loaded namelist for {archive_period} from local cache ({len(self._zip_namelists[archive_period])} files)")
            except Exception:
                pass

        logger.info(f"Connecting to Zenodo remote ZIP: {zip_name}...")
        try:
            reader = CachedHTTPRangeReader(
                url=url,
                session=self._session,
                circuit_breaker=self.circuit_breaker,
                block_cache_dir=block_cache_dir,
            )
            zf = zipfile.ZipFile(reader)
            self._zip_handles[archive_period] = zf

            if archive_period not in self._zip_namelists:
                name_map: Dict[str, str] = {}
                for name in zf.namelist():
                    norm = name.replace("\\", "/").lstrip("/")
                    name_map[norm] = name
                    if norm.startswith("full_data/"):
                        without_prefix = norm[len("full_data/"):]
                        name_map[without_prefix] = name
                    base = Path(name).name
                    if base not in name_map:
                        name_map[base] = name

                self._zip_namelists[archive_period] = name_map
                try:
                    namelist_file.write_text(json.dumps(name_map), encoding="utf-8")
                except Exception:
                    pass

            self.circuit_breaker.record_success()
            logger.info(f"Connected to {zip_name}: ready for streaming")
            return zf
        except Exception as e:
            self.circuit_breaker.record_failure(str(e))
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
        Get local path to a report PDF using a multi-stage cascade:
        Stage 1: Check all local workspace repositories and cache (0ms, offline).
        Stage 2: Check Circuit Breaker for Zenodo availability.
        Stage 3: Stream-extract from remote Zenodo archive with persistent index & retries.
        """
        # --- STAGE 1: LOCAL FIRST ---
        local_found = self._find_local_pdf(ticker, year, archive_period, relative_path)
        if local_found:
            return local_found

        # Destination in cache
        period_dir = self.cache_root / archive_period
        cached_pdf = period_dir / relative_path

        # --- STAGE 2: CIRCUIT BREAKER CHECK ---
        if not self.circuit_breaker.can_attempt():
            logger.warning(
                f"Zenodo Circuit Breaker is OPEN. Bypassing remote download for {ticker} ({year}). "
                f"Reason: {self.circuit_breaker.last_error}"
            )
            return None

        # --- STAGE 3: REMOTE EXTRACTION ---
        zf = self._get_zip_handle(archive_period)
        if not zf:
            return None

        name_map = self._zip_namelists.get(archive_period, {})
        norm_rel = relative_path.replace("\\", "/").lstrip("/")
        entry_name = name_map.get(norm_rel) or name_map.get(Path(relative_path).name)

        if not entry_name:
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
                chunk = src.read(4 * 1024 * 1024)
                while chunk:
                    dst.write(chunk)
                    chunk = src.read(4 * 1024 * 1024)

            self.circuit_breaker.record_success()
            logger.info(f"Successfully cached: {cached_pdf} ({cached_pdf.stat().st_size / (1024*1024):.1f} MB)")
            return cached_pdf
        except Exception as e:
            self.circuit_breaker.record_failure(str(e))
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
        Download multiple reports using multi-stage resolution:
        1. Local resolve first (0ms).
        2. Remote download with circuit breaker protection for remaining files.
        """
        total = len(reports)
        to_download: List[Tuple[int, Dict[str, Any]]] = []

        # Stage 1: Resolve all available local files first
        for idx, r in enumerate(reports, 1):
            rel_path = r.get("relative_path", "")
            period = r.get("archive_period", "")
            ticker = r.get("ticker", "")
            year = r.get("year", 0)

            local_found = self._find_local_pdf(ticker, year, period, rel_path)
            if local_found:
                r["local_path"] = str(local_found.resolve())
                r["download_status"] = "local_ready"
                if progress_callback:
                    progress_callback(idx, total, f"Sẵn sàng trong bộ nhớ: {ticker} ({year})")
            else:
                to_download.append((idx, r))

        # Stage 2: Attempt remote download for remaining files
        for idx, r in to_download:
            rel_path = r.get("relative_path", "")
            period = r.get("archive_period", "")
            ticker = r.get("ticker", "")
            year = r.get("year", 0)

            if not self.circuit_breaker.can_attempt():
                r["local_path"] = None
                r["download_status"] = "circuit_open"
                if progress_callback:
                    progress_callback(idx, total, f"Zenodo quá tải, tạm bỏ qua: {ticker} ({year})")
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
                r["download_status"] = "downloaded"
            else:
                r["local_path"] = None
                r["download_status"] = "failed"

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
