# -*- coding: utf-8 -*-
"""
arminer.data.catalog
====================
Unified Catalog for Vietnam Annual Reports.
Indexes local PDFs (e.g. blockchain_pipeline, zenodo_sample) and Zenodo Master Index.
Includes ICB Level 1 & Level 2 Industry Taxonomy.
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Set
import pandas as pd
from loguru import logger

from arminer.data.industry import IndustryClassifier
from arminer.data.pdf_source import PDFSource



class UnifiedCatalog:
    """Unified repository index for local files & Zenodo cloud dataset with ICB sectors."""
    _init_lock = threading.Lock()

    def __init__(self, workspace_root: Optional[Path] = None):
        if workspace_root is None:
            workspace_root = Path(__file__).resolve().parent.parent.parent.parent
        self.workspace_root = workspace_root
        self._local_index: Dict[str, Dict[str, Any]] = {}
        self._zenodo_df: Optional[pd.DataFrame] = None
        self.industry_classifier = IndustryClassifier(workspace_root=self.workspace_root)
        self._initialized = False
        # Ultra-fast in-memory inverted indices for O(1) searches
        self._records_cache: List[Dict[str, Any]] = []
        self._ticker_index: Dict[str, List[int]] = {}
        self._unique_tickers: List[str] = []
        self._sector_index: Dict[str, List[int]] = {}
        self._icb_l1_index: Dict[str, List[int]] = {}
        self._icb_l2_index: Dict[str, List[int]] = {}
        self._icb_l3_index: Dict[str, List[int]] = {}
        self._icb_l4_index: Dict[str, List[int]] = {}
        self._year_index: Dict[int, List[int]] = {}
        self._exchange_index: Dict[str, List[int]] = {}
        self._sectors_tree_cache: Optional[Dict[str, Any]] = None

    def initialize(self):
        """Index local directories, load Zenodo master catalog, and construct inverted indices."""
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            self.industry_classifier.initialize()
            self._index_local_sources()
            self._load_zenodo_catalog()
            self._build_inverted_indices()
            self._initialized = True

    def index_directory(self, directory: str | Path, source_name: str = "custom_local"):
        """Chủ động lập chỉ mục cho một thư mục PDF bất kỳ trên máy tính người dùng."""
        p_dir = Path(directory).resolve()
        if not p_dir.exists() or not p_dir.is_dir():
            return 0

        added = 0
        for p in p_dir.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in (".pdf", ".txt"):
                continue

            parsed = PDFSource.parse_filename(p)
            if not parsed:
                # Try parent folder as ticker
                parent = p.parent.name.replace("MST_", "").upper()
                m_yr = re.search(r"(\d{4})", p.name) or re.search(r"(\d{4})", p.parent.name)
                if m_yr and re.match(r"^[A-Z0-9]{2,10}$", parent):
                    parsed = (parent, int(m_yr.group(1)))

            if parsed:
                ticker, year = parsed
                rec_id = f"LOCAL_{ticker}_{year}"
                if rec_id not in self._local_index:
                    l1, l2 = self.industry_classifier.get_industry(ticker)
                    c_info = self.industry_classifier.get_company_info(ticker) or {}
                    raw_ex = str(c_info.get("exchange", "HSX")).upper().strip()
                    norm_ex = "HSX" if raw_ex in ("HOSE", "HSX") else ("HNX" if raw_ex == "HNX" else ("UPCOM" if "UPCOM" in raw_ex else raw_ex))
                    self._local_index[rec_id] = {
                        "record_id": rec_id,
                        "ticker": ticker,
                        "year": year,
                        "exchange": norm_ex,
                        "file_name": p.name,
                        "local_path": str(p.resolve()),
                        "source": source_name,
                        "icb_l1": l1,
                        "icb_l2": l2,
                        "file_size_mb": round(p.stat().st_size / (1024 * 1024), 2),
                        "status": "ready",
                    }
                    added += 1

        return added

    def _index_local_sources(self):
        """Index local PDF repositories on the system in a portable manner."""
        # 1. Environment variable if set
        env_dir = os.environ.get("ARMINER_REPORTS_DIR")
        if env_dir and Path(env_dir).exists():
            self.index_directory(env_dir, source_name="env_configured")

        # 2. Standard workspace data directories
        standard_dirs = [
            Path.cwd() / "data" / "reports",
            Path.cwd() / "data" / "raw_pdfs",
            Path.cwd() / "data" / "zenodo_sample" / "full_data",
            Path.cwd() / "data" / "zenodo_sample",
            Path.cwd() / "data" / "bctn_new_extracted",
            self.workspace_root / "data" / "reports",
            self.workspace_root / "data" / "raw_pdfs",
            self.workspace_root / "data" / "bctn_new_extracted",
            Path.home() / ".arminer" / "reports",
        ]
        for s_dir in standard_dirs:
            if s_dir.exists():
                self.index_directory(s_dir, source_name="local_storage")

        # 3. Google Drive gap filler (Drive for Desktop / Google Colab / Custom Cloud)
        drive_index_file = self.workspace_root / "data" / "gap_filler" / "drive_index.json"
        active_gdrive_base: Optional[Path] = None

        gdrive_path = os.environ.get("ARMINER_GDRIVE_PATH")
        if gdrive_path and Path(gdrive_path).exists():
            active_gdrive_base = Path(gdrive_path)
        else:
            colab_candidates = [
                Path("/content/drive/MyDrive/arminer_bctn_gap"),
                Path("/content/drive/Shareddrives/arminer_bctn_gap"),
                Path("/content/arminer_bctn_gap"),
            ]
            for c_cand in colab_candidates:
                if c_cand.exists() and c_cand.is_dir():
                    active_gdrive_base = c_cand
                    break

            if not active_gdrive_base:
                for drive_letter in ("H", "I", "G", "D"):
                    gdrive_dir = Path(f"{drive_letter}:\\My Drive\\arminer_bctn_gap")
                    if gdrive_dir.exists():
                        active_gdrive_base = gdrive_dir
                        break

        # Fast index from drive_index.json in 0.01s (tuyệt đối không quét rglob trên ổ đĩa ảo)
        if drive_index_file.exists():
            try:
                drive_data = json.loads(drive_index_file.read_text(encoding="utf-8"))
                for key, item in drive_data.items():
                    parts = key.rsplit("_", 1)
                    if len(parts) == 2 and parts[1].isdigit():
                        ticker, year = parts[0].upper(), int(parts[1])
                        rec_id = f"LOCAL_{ticker}_{year}"
                        if rec_id not in self._local_index:
                            l1, l2 = self.industry_classifier.get_industry(ticker)
                            c_info = self.industry_classifier.get_company_info(ticker) or {}
                            raw_ex = str(c_info.get("exchange", "HSX")).upper().strip()
                            norm_ex = "HSX" if raw_ex in ("HOSE", "HSX") else ("HNX" if raw_ex == "HNX" else ("UPCOM" if "UPCOM" in raw_ex else raw_ex))

                            fname = item.get("file_name", f"{ticker}_{year}_BCTN.pdf")
                            local_p = str(active_gdrive_base / ticker / fname) if active_gdrive_base else ""

                            self._local_index[rec_id] = {
                                "record_id": rec_id,
                                "ticker": ticker,
                                "year": year,
                                "exchange": norm_ex,
                                "file_name": fname,
                                "local_path": local_p,
                                "source": "gdrive_gap_filler",
                                "icb_l1": l1,
                                "icb_l2": l2,
                                "file_size_mb": round(item.get("file_size", 0) / (1024 * 1024), 2),
                                "status": "ready" if local_p else "cloud_available",
                                "gdrive_file_id": item.get("file_id", ""),
                                "direct_url": item.get("direct_url", ""),
                            }
            except Exception as e:
                logger.warning(f"UnifiedCatalog: Could not load drive_index.json: {e}")
        elif active_gdrive_base:
            self.index_directory(str(active_gdrive_base), source_name="gdrive_gap_filler")

        logger.info(f"UnifiedCatalog: Indexed {len(self._local_index)} local PDFs")

    def _load_zenodo_catalog(self):
        """Load the Zenodo master catalog from bundled fixture or local cache."""
        # 1. Check bundled package fixture (parquet, fast & compact)
        fixture_parquet = Path(__file__).resolve().parent / "fixtures" / "zenodo_master_index.parquet"
        if fixture_parquet.exists():
            try:
                self._zenodo_df = pd.read_parquet(fixture_parquet)
                logger.info(f"UnifiedCatalog: Loaded bundled Zenodo catalog ({len(self._zenodo_df)} records)")
            except Exception as e:
                logger.warning(f"Could not load bundled parquet: {e}")

        # 2. Check local CSV cache (fallback if no parquet)
        if self._zenodo_df is None:
            csv_path = self.workspace_root / "data" / "zenodo_catalog" / "file_index_full.csv"
            if csv_path.exists():
                try:
                    self._zenodo_df = pd.read_csv(csv_path)
                    logger.info(f"UnifiedCatalog: Loaded Zenodo CSV catalog ({len(self._zenodo_df)} records)")
                except Exception as e:
                    logger.warning(f"UnifiedCatalog: Could not load Zenodo CSV: {e}")

        # 3. Fallback to online download if not present
        if self._zenodo_df is None:
            try:
                import requests
                csv_path = self.workspace_root / "data" / "zenodo_catalog" / "file_index_full.csv"
                url = "https://zenodo.org/api/records/20949551/files/file_index_full.csv/content"
                logger.info("Downloading Zenodo master catalog from online API...")
                r = requests.get(url, timeout=30)
                if r.status_code == 200:
                    csv_path.parent.mkdir(parents=True, exist_ok=True)
                    csv_path.write_bytes(r.content)
                    self._zenodo_df = pd.read_csv(csv_path)
                    logger.info(f"Downloaded and loaded Zenodo catalog ({len(self._zenodo_df)} records)")
            except Exception as e:
                logger.warning(f"Could not auto-download Zenodo catalog: {e}")

        # 4. Merge supplement catalog (546 records from thầy gửi)
        self._load_supplement_catalog()

        # 5. Merge gap filler catalog (missing reports tracked in gap_manifest.csv)
        self._load_gap_filler_catalog()

    def _load_supplement_catalog(self):
        """Load and merge supplement index — mở rộng Zenodo với dữ liệu bổ sung.

        Supplement records có cùng schema với Zenodo master index,
        được merge trong suốt — search() tự động trả cả 2 nguồn.
        """
        supplement_parquet = Path(__file__).resolve().parent / "fixtures" / "bctn_supplement_index.parquet"
        if not supplement_parquet.exists():
            return

        try:
            sup_df = pd.read_parquet(supplement_parquet)
            if self._zenodo_df is not None:
                # Avoid duplicates: only add records not already in Zenodo
                existing_keys = set(
                    zip(self._zenodo_df["ticker_folder"].str.upper(),
                        self._zenodo_df["year_full"])
                )
                sup_new = sup_df[
                    ~sup_df.apply(
                        lambda r: (str(r["ticker_folder"]).upper(), r["year_full"]) in existing_keys,
                        axis=1
                    )
                ]
                if len(sup_new) > 0:
                    self._zenodo_df = pd.concat([self._zenodo_df, sup_new], ignore_index=True)
                    logger.info(
                        f"UnifiedCatalog: Merged {len(sup_new)} supplement records "
                        f"→ total {len(self._zenodo_df)} records"
                    )
            else:
                self._zenodo_df = sup_df
                logger.info(f"UnifiedCatalog: Loaded {len(sup_df)} supplement records (no Zenodo base)")
        except Exception as e:
            logger.warning(f"Could not load supplement catalog: {e}")

    def _load_gap_filler_catalog(self):
        """Load gap filler records from gap_manifest.csv.

        Only records with search_status == 'uploaded' or 'verified' are merged
        into the catalog so they become searchable and downloadable via the
        gap-filler HuggingFace dataset (Stage 1.6 in zenodo_downloader).
        """
        rows = []
        seen_keys = set()

        # 1. From gap_manifest.csv
        gap_csv = self.workspace_root / "data" / "gap_manifest.csv"
        if gap_csv.exists():
            try:
                gap_df = pd.read_csv(gap_csv, encoding="utf-8-sig")
                uploaded = gap_df[gap_df["search_status"].isin(["uploaded", "verified"])]
                for _, r in uploaded.iterrows():
                    ticker = str(r["ticker"]).upper()
                    year = int(r["year"])
                    fname = f"{ticker}_{year}_BCTN.pdf"
                    seen_keys.add((ticker, year))
                    rows.append({
                        "record_id": f"GAP_{ticker}_{year}",
                        "ticker_folder": ticker,
                        "ticker_file": ticker,
                        "year_full": year,
                        "archive_period": "gap_filler",
                        "document_type": "annual_report",
                        "file_name": fname,
                        "relative_path": f"{ticker}/{fname}",
                        "file_size_bytes": 0,
                        "file_size_mb": 0.0,
                        "sha256": "",
                        "status": "gap_filler",
                        "notes": str(r.get("source", "")),
                    })
            except Exception as e:
                logger.warning(f"Could not load gap manifest: {e}")

        # 2. Auto-discover physical PDFs in Google Drive folder
        gdrive_dirs = []
        gdrive_env = os.environ.get("ARMINER_GDRIVE_PATH")
        if gdrive_env and Path(gdrive_env).exists():
            gdrive_dirs.append(Path(gdrive_env))
        for dl in ("H", "I", "G", "D"):
            p = Path(f"{dl}:\\My Drive\\arminer_bctn_gap")
            if p.exists():
                gdrive_dirs.append(p)
                break

        # 2. Fast Auto-discover from drive_index.json (tránh rglob trên ổ đĩa ảo cực chậm)
        drive_index_file = self.workspace_root / "data" / "gap_filler" / "drive_index.json"
        indexed_from_json = False
        if drive_index_file.exists():
            try:
                d_map = json.loads(drive_index_file.read_text(encoding="utf-8"))
                for k, v in d_map.items():
                    parts = k.split("_", 1)
                    if len(parts) == 2 and parts[1].isdigit():
                        t = parts[0].upper()
                        y = int(parts[1])
                        if (t, y) not in seen_keys:
                            seen_keys.add((t, y))
                            fname = v.get("file_name", f"{t}_{y}_BCTN.pdf")
                            f_size = v.get("file_size", 0)
                            rows.append({
                                "record_id": f"GAP_{t}_{y}",
                                "ticker_folder": t,
                                "ticker_file": t,
                                "year_full": y,
                                "archive_period": "gap_filler",
                                "document_type": "annual_report",
                                "file_name": fname,
                                "relative_path": f"{t}/{fname}",
                                "file_size_bytes": f_size,
                                "file_size_mb": round(f_size / (1024 * 1024), 2),
                                "sha256": "",
                                "status": "gap_filler",
                                "notes": "gdrive_cloud",
                            })
                indexed_from_json = True
            except Exception as e:
                logger.warning(f"Could not load drive_index.json: {e}")

        if not indexed_from_json:
            for g_dir in gdrive_dirs:
                try:
                    for pdf_file in g_dir.rglob("*.pdf"):
                        if pdf_file.stat().st_size < 50_000:
                            continue
                        m = re.match(r"^([A-Z0-9]{2,10})_(\d{4})_BCTN\.pdf$", pdf_file.name, re.IGNORECASE)
                        if m:
                            t = m.group(1).upper()
                            y = int(m.group(2))
                            if (t, y) not in seen_keys:
                                seen_keys.add((t, y))
                                size_mb = round(pdf_file.stat().st_size / (1024 * 1024), 2)
                                rows.append({
                                    "record_id": f"GAP_{t}_{y}",
                                    "ticker_folder": t,
                                    "ticker_file": t,
                                    "year_full": y,
                                    "archive_period": "gap_filler",
                                    "document_type": "annual_report",
                                    "file_name": pdf_file.name,
                                    "relative_path": f"{t}/{pdf_file.name}",
                                    "file_size_bytes": pdf_file.stat().st_size,
                                    "file_size_mb": size_mb,
                                    "sha256": "",
                                    "status": "gap_filler",
                                    "notes": "gdrive_physical",
                                })
                except Exception as e:
                    logger.warning(f"Could not scan Google Drive directory: {e}")

        if not rows:
            return

        try:
            gap_records = pd.DataFrame(rows)
            if self._zenodo_df is not None:
                existing_keys = set(
                    zip(self._zenodo_df["ticker_folder"].str.upper(),
                        self._zenodo_df["year_full"])
                )
                gap_new = gap_records[
                    ~gap_records.apply(
                        lambda row: (str(row["ticker_folder"]).upper(), row["year_full"]) in existing_keys,
                        axis=1
                    )
                ]
                if len(gap_new) > 0:
                    self._zenodo_df = pd.concat([self._zenodo_df, gap_new], ignore_index=True)
                    logger.info(
                        f"UnifiedCatalog: Merged {len(gap_new)} gap-filler records "
                        f"→ total {len(self._zenodo_df)} records"
                    )
            else:
                self._zenodo_df = gap_records
                logger.info(f"UnifiedCatalog: Loaded {len(gap_records)} gap-filler records")
        except Exception as e:
            logger.warning(f"Could not load gap filler catalog: {e}")

    def _build_inverted_indices(self):
        """Build high-speed O(1) in-memory indices and pre-formatted record objects."""
        if self._zenodo_df is None:
            return

        # Pre-sort once by ticker asc, year desc and reset index
        self._zenodo_df = self._zenodo_df.sort_values(
            by=["ticker_folder", "year_full"], ascending=[True, False]
        ).reset_index(drop=True)

        df = self._zenodo_df
        records: List[Dict[str, Any]] = []
        ticker_idx: Dict[str, List[int]] = {}
        sector_idx: Dict[str, List[int]] = {}
        icb_l1_idx: Dict[str, List[int]] = {}
        icb_l2_idx: Dict[str, List[int]] = {}
        icb_l3_idx: Dict[str, List[int]] = {}
        icb_l4_idx: Dict[str, List[int]] = {}
        year_idx: Dict[int, List[int]] = {}
        exchange_idx: Dict[str, List[int]] = {}

        full_map = self.industry_classifier._ticker_full_map

        # Map local files from _local_index and Google Drive (in-memory, instant)
        gdrive_map: Dict[Tuple[str, int], str] = {}
        for rec in self._local_index.values():
            if rec.get("local_path"):
                gdrive_map[(rec["ticker"], rec["year"])] = rec["local_path"]

        for i, row in enumerate(df.to_dict("records")):
            t = str(row["ticker_folder"]).upper()
            y = int(row["year_full"]) if pd.notna(row["year_full"]) else 0
            c_info = full_map.get(t, {})

            l1 = c_info.get("icb_l1", "Khác")
            l2 = c_info.get("icb_l2", "Chưa phân loại")
            l3 = c_info.get("icb_l3", "")
            l4 = c_info.get("icb_l4", "")
            icb_code = c_info.get("icb_code", "")
            raw_ex = str(c_info.get("exchange", "Khác")).upper().strip()
            norm_ex = "HSX" if raw_ex in ("HOSE", "HSX") else ("HNX" if raw_ex == "HNX" else ("UPCOM" if "UPCOM" in raw_ex else "Khác"))

            row_status = str(row.get("status", ""))
            row_arch = str(row.get("archive_period", ""))
            rec_id = str(row.get("record_id", ""))

            if row_status == "gap_filler" or row_arch == "gap_filler" or "GAP_" in rec_id:
                src = "gap_filler"
            elif row_arch == "supplement" or "SUPP_" in rec_id:
                src = "supplement"
            else:
                src = "zenodo"

            # Check local file existence in Google Drive or local index
            is_local = False
            local_path = ""
            if (t, y) in gdrive_map:
                is_local = True
                local_path = gdrive_map[(t, y)]
            elif f"{t}_{y}" in self._local_index:
                is_local = True
                local_path = self._local_index[f"{t}_{y}"].get("local_path", "")

            rec = {
                "record_id": rec_id,
                "ticker": t,
                "company_name": c_info.get("name", ""),
                "company_short_name": c_info.get("short_name", ""),
                "year": y,
                "exchange": norm_ex,
                "file_name": str(row["file_name"]),
                "relative_path": str(row["relative_path"]),
                "archive_period": row_arch,
                "source": src,
                "icb_l1": l1,
                "icb_l2": l2,
                "icb_l3": l3,
                "icb_l4": l4,
                "icb_code": icb_code,
                "file_size_mb": float(row["file_size_mb"]) if pd.notna(row["file_size_mb"]) else 0.0,
                "website": c_info.get("website", ""),
                "ir_portal": c_info.get("ir_portal", ""),
                "status": "available",
                "is_local": is_local,
                "local_path": local_path,
            }
            records.append(rec)

            ticker_idx.setdefault(t, []).append(i)
            if y > 0:
                year_idx.setdefault(y, []).append(i)

            # Exchange index (supports both HSX and HOSE alias)
            exchange_idx.setdefault(norm_ex, []).append(i)
            if norm_ex == "HSX":
                exchange_idx.setdefault("HOSE", []).append(i)
            elif norm_ex == "HOSE":
                exchange_idx.setdefault("HSX", []).append(i)

            for sec in (l1, l2, l3, l4):
                if sec:
                    sector_idx.setdefault(sec, []).append(i)
            if l1: icb_l1_idx.setdefault(l1, []).append(i)
            if l2: icb_l2_idx.setdefault(l2, []).append(i)
            if l3: icb_l3_idx.setdefault(l3, []).append(i)
            if l4: icb_l4_idx.setdefault(l4, []).append(i)

        self._records_cache = records
        self._ticker_index = ticker_idx
        self._unique_tickers = sorted(list(ticker_idx.keys()))
        self._sector_index = sector_idx
        self._icb_l1_index = icb_l1_idx
        self._icb_l2_index = icb_l2_idx
        self._icb_l3_index = icb_l3_idx
        self._icb_l4_index = icb_l4_idx
        self._year_index = year_idx
        self._exchange_index = exchange_idx

        # Precompute sectors tree cache (include UPCOM for full coverage across all 3 exchanges)
        self._build_sectors_tree_cache()

    def _build_sectors_tree_cache(self):
        """Precompute and cache taxonomy tree with report counts for 0ms responses."""
        tree = self.industry_classifier.get_taxonomy_tree(include_upcom=True)
        ticker_counts = {t: len(idxs) for t, idxs in self._ticker_index.items()}

        for s in tree.get("sectors", []):
            l1_count = 0
            for sub in s.get("subsectors", []):
                sub_count = sum(ticker_counts.get(t, 0) for t in sub.get("tickers", []))
                sub["report_count"] = sub_count
                sub["local_report_count"] = sub_count
                l1_count += sub_count

                for l3 in sub.get("subsectors_l3", []):
                    l3_count = sum(ticker_counts.get(t, 0) for t in l3.get("tickers", []))
                    l3["report_count"] = l3_count
                    for l4 in l3.get("subsectors_l4", []):
                        l4_count = sum(ticker_counts.get(t, 0) for t in l4.get("tickers", []))
                        l4["report_count"] = l4_count

            s["report_count"] = l1_count
            s["local_report_count"] = l1_count

        self._sectors_tree_cache = tree

    def get_sectors(self) -> Dict[str, Any]:
        """Lấy danh sách ngành ICB L1..L4 kèm số lượng báo cáo thực tế (14,500+ file) trong 0ms."""
        self.initialize()
        if self._sectors_tree_cache is not None:
            return self._sectors_tree_cache
        self._build_sectors_tree_cache()
        return self._sectors_tree_cache

    @staticmethod
    def _parse_ticker_filter(ticker_str: Optional[str]) -> Tuple[List[str], bool]:
        """Parse raw ticker input into a list of uppercase ticker tokens.

        Splits by comma, semicolon, space, tab, or newline.
        Returns:
            (tokens, is_multi)
            tokens: list of cleaned unique uppercase tokens
            is_multi: True if multiple tokens were entered
        """
        if not ticker_str or not ticker_str.strip():
            return [], False
        raw_tokens = [t.strip().upper() for t in re.split(r"[,;\s\n\r]+", ticker_str.strip()) if t.strip()]
        tokens = list(dict.fromkeys(raw_tokens))
        return tokens, len(tokens) > 1

    @staticmethod
    def _normalize_exchanges(exchange: Optional[str | List[str]]) -> Set[str]:
        """Normalize exchange filter into a canonical uppercase set."""
        if not exchange:
            return set()
        if isinstance(exchange, str):
            raw_tokens = [t.strip().upper() for t in re.split(r"[,;\s]+", exchange) if t.strip()]
        else:
            raw_tokens = [str(t).strip().upper() for t in exchange if str(t).strip()]

        result = set()
        for tok in raw_tokens:
            if tok in ("HSX", "HOSE"):
                result.add("HSX")
                result.add("HOSE")
            elif tok == "HNX":
                result.add("HNX")
            elif "UPCOM" in tok:
                result.add("UPCOM")
            else:
                result.add(tok)
        return result

    @staticmethod
    def _is_all_exchanges(exchanges_set: Set[str]) -> bool:
        """Return True if the set represents all 3 main exchanges (no filtering needed)."""
        if not exchanges_set:
            return True
        has_hsx = bool({"HSX", "HOSE"} & exchanges_set)
        has_hnx = "HNX" in exchanges_set
        has_upcom = "UPCOM" in exchanges_set
        return has_hsx and has_hnx and has_upcom

    @staticmethod
    def _strip_vietnamese_accents(text: str) -> str:
        """Chuyển đổi chuỗi tiếng Việt có dấu sang không dấu để tìm kiếm mờ mượt mà."""
        import unicodedata
        nfkd = unicodedata.normalize('NFKD', text)
        return "".join([c for c in nfkd if not unicodedata.combining(c)]).replace('đ', 'd').replace('Đ', 'D')

    def _find_tickers_by_company_name(self, query: str) -> List[str]:
        """Tìm mã chứng khoán theo tên công ty hoặc tên thương hiệu viết tắt."""
        if not query or len(query.strip()) < 4:
            return []
        q = query.strip().upper()
        q_ascii = self._strip_vietnamese_accents(q)
        matched = []
        for t, info in self.industry_classifier._ticker_full_map.items():
            name = str(info.get("name", "")).upper()
            short_name = str(info.get("short_name", "")).upper()
            if q in name or q in short_name:
                matched.append(t)
            elif q_ascii:
                name_ascii = self._strip_vietnamese_accents(name)
                short_ascii = self._strip_vietnamese_accents(short_name)
                if q_ascii in name_ascii or q_ascii in short_ascii:
                    matched.append(t)
        return matched

    def search(
        self,
        ticker: Optional[str] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        icb_l1: Optional[str] = None,
        icb_l2: Optional[str] = None,
        icb_l3: Optional[str] = None,
        icb_l4: Optional[str] = None,
        sector: Optional[str] = None,
        exchange: Optional[str | List[str]] = None,
        source_filter: str = "all",
        limit: int = 500,
        return_total: bool = False,
    ) -> List[Dict[str, Any]] | Tuple[List[Dict[str, Any]], int]:
        """Ultra-fast search across all reports via O(1) Inverted Indices and Company Name matching."""
        self.initialize()
        results: List[Dict[str, Any]] = []
        total_matched = 0

        # Zenodo/Unified search via inverted index
        if source_filter != "local_only" and self._records_cache:
            matched_indices: Optional[Set[int]] = None

            # 1. Ticker & Company Name filter
            if ticker and ticker.strip():
                tokens, is_multi = self._parse_ticker_filter(ticker)
                t_indices: Set[int] = set()

                if tokens:
                    for tok in tokens:
                        if tok in self._ticker_index:
                            t_indices.update(self._ticker_index[tok])
                        for ut in self._unique_tickers:
                            if tok in ut and ut != tok:
                                t_indices.update(self._ticker_index[ut])

                # Mở rộng tìm theo Tên doanh nghiệp & Thương hiệu
                matched_by_name = self._find_tickers_by_company_name(ticker)
                for mt in matched_by_name:
                    if mt in self._ticker_index:
                        t_indices.update(self._ticker_index[mt])

                matched_indices = t_indices

            # 2. Sector filter
            if sector:
                s_indices = set(self._sector_index.get(sector, []))
                matched_indices = s_indices if matched_indices is None else (matched_indices & s_indices)
            elif icb_l1 or icb_l2 or icb_l3 or icb_l4:
                sec_sets = []
                if icb_l1 and icb_l1 in self._icb_l1_index: sec_sets.append(set(self._icb_l1_index[icb_l1]))
                if icb_l2 and icb_l2 in self._icb_l2_index: sec_sets.append(set(self._icb_l2_index[icb_l2]))
                if icb_l3 and icb_l3 in self._icb_l3_index: sec_sets.append(set(self._icb_l3_index[icb_l3]))
                if icb_l4 and icb_l4 in self._icb_l4_index: sec_sets.append(set(self._icb_l4_index[icb_l4]))
                if sec_sets:
                    combined_sec = set.intersection(*sec_sets)
                    matched_indices = combined_sec if matched_indices is None else (matched_indices & combined_sec)
                else:
                    matched_indices = set()

            # 3. Year range filter
            if year_from or year_to:
                y_min = year_from or 1900
                y_max = year_to or 2100
                y_indices: Set[int] = set()
                for y, idx_list in self._year_index.items():
                    if y_min <= y <= y_max:
                        y_indices.update(idx_list)
                matched_indices = y_indices if matched_indices is None else (matched_indices & y_indices)

            # 4. Exchange filter (HSX, HNX, UPCOM)
            target_exchanges = self._normalize_exchanges(exchange)
            if target_exchanges and not self._is_all_exchanges(target_exchanges):
                ex_indices: Set[int] = set()
                for ex in target_exchanges:
                    ex_indices.update(self._exchange_index.get(ex, []))
                matched_indices = ex_indices if matched_indices is None else (matched_indices & ex_indices)

            # Preserve pre-sorted order
            if matched_indices is None:
                final_indices = list(range(len(self._records_cache)))
            else:
                final_indices = sorted(matched_indices)

            total_matched = len(final_indices)
            slice_indices = final_indices[:limit] if (limit is not None and limit > 0) else final_indices
            results = [self._records_cache[i] for i in slice_indices]

        # Local-only search (for CLI / user-uploaded directory compat)
        if source_filter == "local_only":
            local_list = []
            tokens, is_multi = self._parse_ticker_filter(ticker) if (ticker and ticker.strip()) else ([], False)
            token_set = set(tokens)
            target_exchanges = self._normalize_exchanges(exchange)

            for rec in self._local_index.values():
                rec_ticker = rec.get("ticker", "").upper()
                rec_ex = rec.get("exchange", "HSX")
                if target_exchanges and not self._is_all_exchanges(target_exchanges):
                    if rec_ex not in target_exchanges:
                        continue
                if tokens:
                    if not is_multi:
                        if tokens[0] not in rec_ticker:
                            continue
                    elif any(len(t) < 3 for t in tokens):
                        if not any(t in rec_ticker for t in tokens):
                            continue
                    else:
                        if rec_ticker not in token_set:
                            continue
                if year_from and rec["year"] < year_from:
                    continue
                if year_to and rec["year"] > year_to:
                    continue
                if sector and rec.get("icb_l1") != sector and rec.get("icb_l2") != sector:
                    continue
                if icb_l1 and rec.get("icb_l1") != icb_l1:
                    continue
                if icb_l2 and rec.get("icb_l2") != icb_l2:
                    continue
                local_list.append({**rec, "source": "local"})

            local_list.sort(key=lambda x: (x["ticker"], -x["year"]))
            total_matched = len(local_list)
            results = local_list[:limit] if (limit is not None and limit > 0) else local_list

        if return_total:
            return results, total_matched
        return results

    def get_matched_record_ids(
        self,
        ticker: Optional[str] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        icb_l1: Optional[str] = None,
        icb_l2: Optional[str] = None,
        icb_l3: Optional[str] = None,
        icb_l4: Optional[str] = None,
        sector: Optional[str] = None,
        exchange: Optional[str | List[str]] = None,
    ) -> List[str]:
        """Lấy toàn bộ record_id khớp bộ lọc từ Zenodo mà không bị giới hạn số lượng."""
        self.initialize()
        records = self.search(
            ticker=ticker,
            year_from=year_from,
            year_to=year_to,
            icb_l1=icb_l1,
            icb_l2=icb_l2,
            icb_l3=icb_l3,
            icb_l4=icb_l4,
            sector=sector,
            exchange=exchange,
            limit=0,
        )
        if isinstance(records, tuple):
            records = records[0]
        return [r["record_id"] for r in records if r.get("record_id")]

    def lookup_records(self, record_ids: List[str]) -> List[Dict[str, Any]]:
        """Look up specific records by their record_id (Zenodo or Local).
        
        Returns full record info including relative_path and archive_period
        needed for streaming extraction.
        """
        self.initialize()
        results: List[Dict[str, Any]] = []
        id_set = set(record_ids)

        # Check Zenodo DF
        if self._zenodo_df is not None:
            matched = self._zenodo_df[self._zenodo_df["record_id"].isin(id_set)]
            for _, row in matched.iterrows():
                t = str(row["ticker_folder"]).upper()
                y = int(row["year_full"]) if pd.notna(row["year_full"]) else 0
                l1, l2 = self.industry_classifier.get_industry(t)
                results.append({
                    "record_id": str(row["record_id"]),
                    "ticker": t,
                    "year": y,
                    "file_name": str(row["file_name"]),
                    "relative_path": str(row["relative_path"]),
                    "archive_period": str(row["archive_period"]),
                    "source": "zenodo",
                    "icb_l1": l1,
                    "icb_l2": l2,
                    "file_size_mb": float(row["file_size_mb"]) if pd.notna(row["file_size_mb"]) else 0.0,
                })

        # Check Local index
        for rid in id_set:
            if rid in self._local_index:
                results.append(self._local_index[rid])

        return results


    def get_ticker_summary(self) -> List[Dict[str, Any]]:
        """Get summary of all unique tickers with years and availability."""
        self.initialize()
        ticker_map: Dict[str, Dict[str, Any]] = {}

        # Local
        for rec in self._local_index.values():
            t = rec["ticker"]
            if t not in ticker_map:
                ticker_map[t] = {
                    "ticker": t,
                    "local_years": [],
                    "zenodo_years": [],
                    "has_local": True,
                    "icb_l1": rec.get("icb_l1"),
                    "icb_l2": rec.get("icb_l2"),
                }
            ticker_map[t]["local_years"].append(rec["year"])

        # Zenodo
        if self._zenodo_df is not None:
            grouped = self._zenodo_df.groupby("ticker_folder")["year_full"].unique()
            for t_raw, years in grouped.items():
                t = str(t_raw).upper()
                l1, l2 = self.industry_classifier.get_industry(t)
                if t not in ticker_map:
                    ticker_map[t] = {
                        "ticker": t,
                        "local_years": [],
                        "zenodo_years": [],
                        "has_local": False,
                        "icb_l1": l1,
                        "icb_l2": l2,
                    }
                ticker_map[t]["zenodo_years"].extend([int(y) for y in years if pd.notna(y)])

        summaries = []
        for t, data in ticker_map.items():
            loc_yrs = sorted(set(data["local_years"]))
            zen_yrs = sorted(set(data["zenodo_years"]))
            all_yrs = sorted(set(loc_yrs + zen_yrs))
            c_info = self.industry_classifier._ticker_full_map.get(t, {})
            raw_ex = str(c_info.get("exchange", "Khác")).upper().strip()
            norm_ex = "HSX" if raw_ex in ("HOSE", "HSX") else ("HNX" if raw_ex == "HNX" else ("UPCOM" if "UPCOM" in raw_ex else "Khác"))
            summaries.append({
                "ticker": t,
                "company_name": c_info.get("name", ""),
                "company_short_name": c_info.get("short_name", ""),
                "exchange": norm_ex,
                "icb_l1": data["icb_l1"] or c_info.get("icb_l1", "Khác"),
                "icb_l2": data["icb_l2"] or c_info.get("icb_l2", "Chưa phân loại"),
                "website": c_info.get("website", ""),
                "total_reports": len(all_yrs),
                "local_reports": len(loc_yrs),
                "has_local": len(loc_yrs) > 0,
                "year_range": f"{min(all_yrs)}-{max(all_yrs)}" if all_yrs else "N/A",
                "years": all_yrs,
            })

        # Sort so tickers with local files come first, then alphabet
        summaries.sort(key=lambda x: (-x["local_reports"], x["ticker"]))
        return summaries
