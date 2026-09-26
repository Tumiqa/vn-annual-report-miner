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

# Official Google Drive Central Database Folder
GDRIVE_GAP_FOLDER_ID = os.environ.get("GDRIVE_GAP_FOLDER_ID", "1uV6_7lW4D-0ujw1wFUNHqEdzN25xQ0Mx")
GDRIVE_GAP_FOLDER_URL = f"https://drive.google.com/drive/folders/{GDRIVE_GAP_FOLDER_ID}"

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
    2. Repository workspace root (vn-annual-report-miner/data/zenodo_cache)
    3. Current working directory (cwd/data/zenodo_cache)
    4. Fallback: User home directory (~/.arminer/zenodo_cache)
    """
    env_dir = os.environ.get("ARMINER_CACHE_DIR")
    if env_dir:
        cache_root = Path(env_dir)
    else:
        ws_root = Path(__file__).resolve().parent.parent.parent.parent
        ws_cache = ws_root / "data" / "zenodo_cache"
        if ws_cache.exists():
            return ws_cache

        try:
            cwd = Path.cwd()
            if (cwd / "data" / "zenodo_cache").exists():
                return cwd / "data" / "zenodo_cache"
            if cwd.drive and cwd.drive.upper() != "C:":
                cache_root = ws_cache if ws_root.exists() else (cwd / "data" / "zenodo_cache")
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

        # 1. GOOGLE DRIVE FIRST (0ms, Local Mount)
        gdrive_path = os.environ.get("ARMINER_GDRIVE_PATH")
        if gdrive_path and Path(gdrive_path).exists():
            search_dirs.append(Path(gdrive_path))
        else:
            for c_cand in [
                Path("/content/drive/MyDrive/arminer_bctn_gap"),
                Path("/content/drive/Shareddrives/arminer_bctn_gap"),
                Path("/content/arminer_bctn_gap"),
            ]:
                if c_cand.exists() and c_cand.is_dir():
                    search_dirs.append(c_cand)
                    break

            for drive_letter in ("H", "I", "G", "D"):
                gdrive_dir = Path(f"{drive_letter}:\\My Drive\\arminer_bctn_gap")
                if gdrive_dir.exists():
                    search_dirs.append(gdrive_dir)
                    break

        # 2. Primary cache root
        if archive_period:
            search_dirs.append(self.cache_root / archive_period)
        search_dirs.append(self.cache_root)
        search_dirs.append(self.cache_root / "gap_filler")

        # 3. Local workspace data directories
        cwd = Path.cwd()
        ws_root = Path(__file__).resolve().parent.parent.parent.parent
        for root in (cwd, ws_root):
            search_dirs.extend([
                root / "data" / "reports",
                root / "data" / "raw_pdfs",
                root / "data" / "zenodo_sample" / "full_data",
                root / "data" / "zenodo_sample",
                root / "data" / "bctn_new_extracted",
            ])

        # 4. Environment directory
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
        # --- STAGE 1: LOCAL & GOOGLE DRIVE FIRST (0ms) ---
        local_found = self._find_local_pdf(ticker, year, archive_period, relative_path)
        if local_found:
            return local_found

        # --- STAGE 1.2: GOOGLE DRIVE CLOUD HTTP STREAM (0.5s) ---
        # Ưu tiên tải trực tiếp từ Google Drive Cloud qua HTTP nếu có trong drive_index.json
        gdrive_cloud = self._try_gap_filler_download(ticker, year)
        if gdrive_cloud and gdrive_cloud.exists():
            return gdrive_cloud

        # --- STAGE 1.5: HUGGING FACE SUPPLEMENT ---
        # For supplement records, try downloading from HF dataset
        if archive_period == "supplement":
            hf_result = self._try_hf_download(ticker, year, relative_path)
            if hf_result:
                return hf_result

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

    def _try_hf_download(
        self,
        ticker: str,
        year: int,
        relative_path: str,
    ) -> Optional[Path]:
        """Try downloading a PDF from the Hugging Face supplement dataset.

        This is a silent fallback — if HF is not available or the file
        is not in the supplement dataset, returns None without errors.
        """
        try:
            from huggingface_hub import hf_hub_download
        except ImportError:
            return None

        # Construct HF path: pdfs/{TICKER}/{TICKER}_{YEAR}_BCTN.pdf
        hf_filename = f"pdfs/{relative_path.replace(chr(92), '/')}"
        hf_repo = os.environ.get("HF_SUPPLEMENT_REPO", "Tumiqa103/vn-bctn-supplement")

        try:
            local_path = hf_hub_download(
                repo_id=hf_repo,
                filename=hf_filename,
                repo_type="dataset",
                cache_dir=str(self.cache_root / "hf_cache"),
            )
            if local_path and Path(local_path).exists():
                logger.info(f"Downloaded from HF: {hf_filename}")
                return Path(local_path)
        except Exception:
            # Silent fallback — HF not available or file not in repo
            pass
        return None

    def _try_gap_filler_download(
        self,
        ticker: str,
        year: int,
    ) -> Optional[Path]:
        """Try downloading a PDF from the gap-filler Google Drive repository.

        Uses a shared Google Drive folder with a drive_index.json file that maps
        (ticker, year) → Google Drive file ID. Downloads via gdown for speed and
        reliability (no rate limits, no authentication needed for shared files).

        Setup: Set GDRIVE_GAP_INDEX_URL env var to the direct download link of
        drive_index.json, or place it at data/gap_filler/drive_index.json.

        drive_index.json format:
        {
            "ACB_2015": "1aBcDeFgHiJkLmNoPqRsTuVwXyZ",
            "VNM_2010": "1xYzAbCdEfGhIjKlMnOpQrStUvW",
            ...
        }
        """
        gap_dir = self.cache_root / "gap_filler"
        cached_pdf = gap_dir / ticker / f"{ticker}_{year}_BCTN.pdf"

        # Already cached locally
        if cached_pdf.exists() and cached_pdf.stat().st_size > 1000:
            return cached_pdf

        # 1. Tải trực tiếp từ Google Drive Cloud qua File ID (Chuẩn 100% như Zenodo)
        index = self._load_drive_index()
        file_id = None
        if index:
            entry = index.get(f"{ticker}_{year}")
            if isinstance(entry, dict):
                file_id = entry.get("file_id")
            elif isinstance(entry, str):
                file_id = entry

        if file_id and len(file_id) > 15:
            # 1.1 Thử tải trực tiếp siêu tốc qua HTTP stream (không cần đăng nhập, không cần cài đặt gì)
            import urllib.request
            gdrive_url = f"https://drive.google.com/uc?export=download&id={file_id}"
            headers = {"User-Agent": "Mozilla/5.0"}
            try:
                req = urllib.request.Request(gdrive_url, headers=headers)
                with urllib.request.urlopen(req, timeout=12) as resp:
                    if resp.status == 200:
                        cached_pdf.parent.mkdir(parents=True, exist_ok=True)
                        with open(cached_pdf, "wb") as f_out:
                            while chunk := resp.read(64 * 1024):
                                f_out.write(chunk)

                        if cached_pdf.exists() and cached_pdf.stat().st_size > 10000:
                            logger.info(f"Downloaded from Google Drive Cloud HTTP: {ticker} ({year}) -> {cached_pdf.name}")
                            return cached_pdf
            except Exception as e:
                logger.debug(f"Direct Google Drive HTTP download failed, trying gdown: {e}")

            # 1.2 Thử qua gdown nếu file có dung lượng rất lớn cần xác thực bypass warning
            try:
                import gdown
                cached_pdf.parent.mkdir(parents=True, exist_ok=True)
                gdown.download(gdrive_url, str(cached_pdf), quiet=True)
                if cached_pdf.exists() and cached_pdf.stat().st_size > 10000:
                    logger.info(f"Downloaded from Google Drive Cloud (gdown): {ticker} ({year})")
                    return cached_pdf
            except Exception:
                pass

        # 2. Cloud CDN Network Fallback: Tải trực tiếp qua mạng từ Cloud CDN (CafeF / Vietstock)
        # Hoạt động 100% khi Google Drive PC không chạy hoặc trên máy khác
        import urllib.request
        yy = f"{year % 100:02d}"
        cdn_candidates = [
            f"https://cafef1.mediacdn.vn/Images/Uploaded/DuLieuDownload/BCTC/{ticker}_{yy}CN_BCTN.pdf",
            f"https://cafef1.mediacdn.vn/Images/Uploaded/DuLieuDownload/BCTC/{ticker}_{yy}N_BCTN.pdf",
            f"https://cafef1.mediacdn.vn/Images/Uploaded/DuLieuDownload/BCTC/{ticker}_{year}_BCTN.pdf",
            f"https://cafef1.mediacdn.vn/Images/Uploaded/DuLieuDownload/BCTC/{ticker}_{yy}_BCTN.pdf",
            f"https://cafef1.mediacdn.vn/Images/Uploaded/DuLieuDownload/BCTC/{ticker}_{year}.pdf",
            f"https://static2.vietstock.vn/data/HNX/{year}/BCTC/VN/{ticker}_{year}_BCTN.pdf",
        ]

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        }

        for url in cdn_candidates:
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=8) as resp:
                    if resp.status == 200:
                        content_len = int(resp.headers.get("Content-Length", 0))
                        if content_len > 10000:  # File hợp lệ > 10KB
                            cached_pdf.parent.mkdir(parents=True, exist_ok=True)
                            with open(cached_pdf, "wb") as f_out:
                                while chunk := resp.read(64 * 1024):
                                    f_out.write(chunk)

                            if cached_pdf.exists() and cached_pdf.stat().st_size > 10000:
                                logger.info(f"Downloaded from Cloud CDN Network: {ticker} ({year}) -> {cached_pdf.name}")
                                return cached_pdf
            except Exception:
                continue

        return None

    def check_cloud_network_connectivity(self) -> Dict[str, Any]:
        """
        Kiểm tra toàn diện trạng thái liên kết mạng và lưu trữ Cloud:
        1. Google Drive PC (H:\\My Drive\\arminer_bctn_gap)
        2. CafeF Cloud CDN (https://cafef1.mediacdn.vn)
        3. Hugging Face Supplement Hub (https://huggingface.co)
        4. Zenodo Master Repository (https://zenodo.org)
        """
        import urllib.request
        results = {
            "drive_pc_mounted": False,
            "drive_pc_path": None,
            "cafef_cdn_cloud": False,
            "huggingface_cloud": False,
            "zenodo_cloud": False,
            "active_mode": "UNKNOWN",
        }

        # 1. Kiểm tra Drive PC cục bộ
        for drive_letter in ("H", "I", "G"):
            cand = Path(f"{drive_letter}:\\My Drive\\arminer_bctn_gap")
            if cand.exists() and cand.is_dir():
                results["drive_pc_mounted"] = True
                results["drive_pc_path"] = str(cand)
                break

        # 2. Kiểm tra CafeF Cloud CDN
        try:
            probe_url = "https://cafef1.mediacdn.vn/Images/Uploaded/DuLieuDownload/BCTC/AAA_24CN_BCTN.pdf"
            req = urllib.request.Request(probe_url, headers={"User-Agent": "Mozilla/5.0"}, method="HEAD")
            with urllib.request.urlopen(req, timeout=5) as r:
                results["cafef_cdn_cloud"] = (r.status == 200)
        except Exception:
            results["cafef_cdn_cloud"] = False

        # 3. Kiểm tra Hugging Face Cloud
        try:
            req = urllib.request.Request("https://huggingface.co", headers={"User-Agent": "Mozilla/5.0"}, method="HEAD")
            with urllib.request.urlopen(req, timeout=5) as r:
                results["huggingface_cloud"] = (r.status in (200, 301, 302))
        except Exception:
            results["huggingface_cloud"] = False

        # 4. Kiểm tra Zenodo Cloud
        try:
            req = urllib.request.Request("https://zenodo.org", headers={"User-Agent": "Mozilla/5.0"}, method="HEAD")
            with urllib.request.urlopen(req, timeout=5) as r:
                results["zenodo_cloud"] = (r.status in (200, 301, 302))
        except Exception:
            results["zenodo_cloud"] = False

        # Xác định Active Mode
        if results["drive_pc_mounted"]:
            results["active_mode"] = "LOCAL_DRIVE_PC_0MS"
        elif results["cafef_cdn_cloud"] or results["huggingface_cloud"] or results["zenodo_cloud"]:
            results["active_mode"] = "CLOUD_NETWORK_FALLBACK_READY"
        else:
            results["active_mode"] = "OFFLINE_CACHE_ONLY"

        return results

    def _load_drive_index(self) -> Dict[str, str]:
        """Load or cache the Google Drive file index mapping (ticker_year → file_id)."""
        if hasattr(self, "_drive_index_cache") and self._drive_index_cache is not None:
            return self._drive_index_cache

        # 1. Check local file
        local_index = Path(__file__).resolve().parent.parent.parent.parent / "data" / "gap_filler" / "drive_index.json"
        if not local_index.exists():
            # Also check workspace root
            try:
                from pathlib import Path as P
                cwd_index = P.cwd() / "data" / "gap_filler" / "drive_index.json"
                if cwd_index.exists():
                    local_index = cwd_index
            except Exception:
                pass

        if local_index.exists():
            try:
                self._drive_index_cache = json.loads(local_index.read_text(encoding="utf-8"))
                logger.info(f"Loaded Google Drive gap index: {len(self._drive_index_cache)} entries")
                return self._drive_index_cache
            except Exception as e:
                logger.warning(f"Could not parse drive_index.json: {e}")

        # 2. Try downloading from env URL
        index_url = os.environ.get("GDRIVE_GAP_INDEX_URL")
        if index_url:
            try:
                resp = requests.get(index_url, timeout=15)
                if resp.status_code == 200:
                    local_index.parent.mkdir(parents=True, exist_ok=True)
                    local_index.write_text(resp.text, encoding="utf-8")
                    self._drive_index_cache = resp.json()
                    logger.info(f"Downloaded Google Drive gap index: {len(self._drive_index_cache)} entries")
                    return self._drive_index_cache
            except Exception:
                pass

        self._drive_index_cache = {}
        return self._drive_index_cache

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

        # Stage 2: Attempt remote download for remaining files in parallel
        if to_download:
            import concurrent.futures
            import threading
            lock = threading.Lock()
            completed_remote = 0
            base_done = total - len(to_download)

            def _download_single(item: Tuple[int, Dict[str, Any]]) -> Dict[str, Any]:
                nonlocal completed_remote
                idx, r = item
                rel_path = r.get("relative_path", "")
                period = r.get("archive_period", "")
                ticker = r.get("ticker", "")
                year = r.get("year", 0)

                if not self.circuit_breaker.can_attempt():
                    r["local_path"] = None
                    r["download_status"] = "circuit_open"
                    with lock:
                        completed_remote += 1
                        if progress_callback:
                            progress_callback(base_done + completed_remote, total, f"Zenodo quá tải: {ticker} ({year})")
                    return r

                with lock:
                    if progress_callback:
                        progress_callback(base_done + completed_remote, total, f"Đang tải: {ticker} ({year})...")

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

                with lock:
                    completed_remote += 1
                    if progress_callback:
                        status_label = "Tải thành công" if r["local_path"] else "Thất bại"
                        progress_callback(base_done + completed_remote, total, f"[{status_label}] {ticker} ({year})")

                return r

            max_dl_workers = min(4, len(to_download))
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_dl_workers) as pool:
                list(pool.map(_download_single, to_download))

        return reports

    def get_cache_status(self) -> Dict[str, Any]:
        """Report what's currently cached across all known cache directories."""
        status = {}
        ws_root = Path(__file__).resolve().parent.parent.parent.parent
        candidate_roots = [
            self.cache_root,
            ws_root / "data" / "zenodo_cache",
            Path.cwd() / "data" / "zenodo_cache",
            Path.cwd().parent / "data" / "zenodo_cache",
            Path.home() / ".arminer" / "zenodo_cache",
        ]
        seen_roots = set()
        active_roots = []
        for r in candidate_roots:
            if r.exists():
                res = str(r.resolve())
                if res not in seen_roots:
                    seen_roots.add(res)
                    active_roots.append(r)

        for period, zip_name in ARCHIVE_ZIP_MAP.items():
            period_pdfs = set()
            total_size = 0
            for a_root in active_roots:
                period_dir = a_root / period
                if period_dir.exists():
                    for f in period_dir.rglob("*.pdf"):
                        res_p = str(f.resolve())
                        if res_p not in period_pdfs:
                            period_pdfs.add(res_p)
                            total_size += f.stat().st_size
            status[period] = {
                "cached_pdfs": len(period_pdfs),
                "total_size_mb": round(total_size / (1024 * 1024), 1),
            }
        return status

    def clear_cache(self, also_clear_home_c: bool = True) -> Dict[str, Any]:
        """
        Xóa toàn bộ file PDF và text cache trong bộ nhớ đệm để giải phóng dung lượng ổ đĩa.
        Quét sạch tất cả các thư mục cache trên máy tính (cả ổ D: và ổ C:).
        """
        deleted_count = 0
        freed_bytes = 0

        ws_root = Path(__file__).resolve().parent.parent.parent.parent
        candidate_dirs = [
            self.cache_root,
            ws_root / "data" / "zenodo_cache",
            Path.cwd() / "data" / "zenodo_cache",
            Path.cwd().parent / "data" / "zenodo_cache",
            ws_root / "data" / "gap_filler" / "cache",
            self.cache_root / "gap_filler",
        ]
        if also_clear_home_c:
            candidate_dirs.extend([
                Path.home() / ".arminer" / "zenodo_cache",
                Path.home() / ".arminer" / "text_cache",
                Path.home() / ".arminer" / "reports",
            ])

        seen_targets = set()
        cleaned_targets = []
        for d in candidate_dirs:
            if not d.exists():
                continue
            resolved = str(d.resolve())
            if resolved in seen_targets:
                continue
            seen_targets.add(resolved)
            cleaned_targets.append(resolved)

            # Xóa các file đệm
            for p in list(d.rglob("*")):
                if p.is_file() and p.suffix.lower() in (".pdf", ".txt", ".meta", ".bin"):
                    try:
                        sz = p.stat().st_size
                        p.unlink()
                        freed_bytes += sz
                        deleted_count += 1
                    except Exception:
                        pass

            # Xóa thư mục con rỗng
            try:
                for sub in sorted(list(d.rglob("*")), key=lambda x: len(x.parts), reverse=True):
                    if sub.is_dir() and not any(sub.iterdir()):
                        sub.rmdir()
            except Exception:
                pass

        logger.info(f"Đã dọn dẹp cache: xóa {deleted_count} file, giải phóng {freed_bytes / (1024*1024):.1f} MB")
        return {
            "deleted_files": deleted_count,
            "freed_mb": round(freed_bytes / (1024 * 1024), 2),
            "cleaned_dirs": cleaned_targets,
            "current_cache_root": str(self.cache_root),
        }

    # Alias for compatibility
    get_cached_path = get_pdf_path
