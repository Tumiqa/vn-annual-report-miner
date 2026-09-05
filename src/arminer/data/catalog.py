# -*- coding: utf-8 -*-
"""
arminer.data.catalog
====================
Unified Catalog for Vietnam Annual Reports.
Indexes local PDFs (e.g. blockchain_pipeline, zenodo_sample) and Zenodo Master Index.
Includes ICB Level 1 & Level 2 Industry Taxonomy.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import pandas as pd
from loguru import logger

from arminer.data.industry import IndustryClassifier
from arminer.data.pdf_source import PDFSource



class UnifiedCatalog:
    """Unified repository index for local files & Zenodo cloud dataset with ICB sectors."""

    def __init__(self, workspace_root: Optional[Path] = None):
        if workspace_root is None:
            workspace_root = Path(__file__).resolve().parent.parent.parent.parent
        self.workspace_root = workspace_root
        self._local_index: Dict[str, Dict[str, Any]] = {}
        self._zenodo_df: Optional[pd.DataFrame] = None
        self.industry_classifier = IndustryClassifier(workspace_root=self.workspace_root)
        self._initialized = False

    def initialize(self):
        """Index local directories and load Zenodo master catalog."""
        if self._initialized:
            return

        self.industry_classifier.initialize()
        self._index_local_sources()
        self._load_zenodo_catalog()
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
                    self._local_index[rec_id] = {
                        "record_id": rec_id,
                        "ticker": ticker,
                        "year": year,
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
            self.workspace_root / "data" / "reports",
            self.workspace_root / "data" / "raw_pdfs",
            Path.home() / ".arminer" / "reports",
        ]
        for s_dir in standard_dirs:
            if s_dir.exists():
                self.index_directory(s_dir, source_name="local_storage")

        logger.info(f"UnifiedCatalog: Indexed {len(self._local_index)} local PDFs")

    def _load_zenodo_catalog(self):
        """Load the Zenodo master catalog from bundled fixture or local cache."""
        # 1. Check bundled package fixture (parquet, fast & compact)
        fixture_parquet = Path(__file__).resolve().parent / "fixtures" / "zenodo_master_index.parquet"
        if fixture_parquet.exists():
            try:
                self._zenodo_df = pd.read_parquet(fixture_parquet)
                logger.info(f"UnifiedCatalog: Loaded bundled Zenodo catalog ({len(self._zenodo_df)} records)")
                return
            except Exception as e:
                logger.warning(f"Could not load bundled parquet: {e}")

        # 2. Check local CSV cache
        csv_path = self.workspace_root / "data" / "zenodo_catalog" / "file_index_full.csv"
        if csv_path.exists():
            try:
                self._zenodo_df = pd.read_csv(csv_path)
                logger.info(f"UnifiedCatalog: Loaded Zenodo CSV catalog ({len(self._zenodo_df)} records)")
                return
            except Exception as e:
                logger.warning(f"UnifiedCatalog: Could not load Zenodo CSV: {e}")

        # 3. Fallback to online download if not present
        try:
            import requests
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


    def get_sectors(self) -> Dict[str, Any]:
        """Lấy danh sách ngành ICB L1 và L2 kèm số lượng báo cáo thực tế trong Zenodo (13,982 file)."""
        self.initialize()
        tree = self.industry_classifier.get_taxonomy_tree()

        # Precompute report counts per ticker in Zenodo
        ticker_counts: Dict[str, int] = {}
        if self._zenodo_df is not None:
            ticker_counts = self._zenodo_df["ticker_folder"].astype(str).str.upper().value_counts().to_dict()

        for s in tree["sectors"]:
            l1_name = s["name"]
            l1_count = 0
            for sub in s["subsectors"]:
                l2_name = sub["name"]
                sub_tickers = [
                    t for t, (l1, l2) in self.industry_classifier._ticker_map.items()
                    if l1 == l1_name and l2 == l2_name
                ]
                sub_count = sum(ticker_counts.get(t, 0) for t in sub_tickers)
                sub["report_count"] = sub_count
                sub["local_report_count"] = sub_count  # backward compat
                l1_count += sub_count

            s["report_count"] = l1_count
            s["local_report_count"] = l1_count  # backward compat

        return tree

    def search(
        self,
        ticker: Optional[str] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        icb_l1: Optional[str] = None,
        icb_l2: Optional[str] = None,
        sector: Optional[str] = None,
        source_filter: str = "all",
        limit: int = 500,
        return_total: bool = False,
    ) -> List[Dict[str, Any]] | Tuple[List[Dict[str, Any]], int]:
        """Search the Zenodo master catalog (13,982 reports).
        
        The primary and default source is Zenodo. Local files are only included
        if source_filter is 'local_only' (for Tab 3 / CLI compatibility).
        """
        self.initialize()
        results: List[Dict[str, Any]] = []
        total_matched = 0

        # Zenodo search (default and primary)
        if source_filter != "local_only" and self._zenodo_df is not None:
            df = self._zenodo_df

            if ticker and ticker.strip():
                t_clean = ticker.strip().upper()
                df = df[df["ticker_folder"].astype(str).str.upper().str.contains(t_clean, na=False)]
            if year_from:
                df = df[df["year_full"] >= year_from]
            if year_to:
                df = df[df["year_full"] <= year_to]

            # Industry filter
            if sector:
                matching_tickers = {
                    t for t, (l1, l2) in self.industry_classifier._ticker_map.items()
                    if l1 == sector or l2 == sector
                }
                df = df[df["ticker_folder"].astype(str).str.upper().isin(matching_tickers)]
            elif icb_l1 or icb_l2:
                matching_tickers = {
                    t for t, (l1, l2) in self.industry_classifier._ticker_map.items()
                    if (not icb_l1 or l1 == icb_l1) and (not icb_l2 or l2 == icb_l2)
                }
                df = df[df["ticker_folder"].astype(str).str.upper().isin(matching_tickers)]

            total_matched = len(df)
            # Sort by ticker asc, year desc
            df = df.sort_values(by=["ticker_folder", "year_full"], ascending=[True, False])

            df_slice = df.head(limit) if (limit is not None and limit > 0) else df
            for _, row in df_slice.iterrows():
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
                    "status": "available",
                })

        # Local-only search (for CLI / user-uploaded directory compat)
        if source_filter == "local_only":
            local_list = []
            for rec in self._local_index.values():
                if ticker and ticker.upper() not in rec["ticker"]:
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
        sector: Optional[str] = None,
    ) -> List[str]:
        """Lấy toàn bộ record_id khớp bộ lọc từ Zenodo mà không bị giới hạn số lượng."""
        self.initialize()
        if self._zenodo_df is None:
            return []

        df = self._zenodo_df
        if ticker and ticker.strip():
            df = df[df["ticker_folder"].astype(str).str.upper().str.contains(ticker.strip().upper(), na=False)]
        if year_from:
            df = df[df["year_full"] >= year_from]
        if year_to:
            df = df[df["year_full"] <= year_to]

        if sector:
            matching_tickers = {
                t for t, (l1, l2) in self.industry_classifier._ticker_map.items()
                if l1 == sector or l2 == sector
            }
            df = df[df["ticker_folder"].astype(str).str.upper().isin(matching_tickers)]
        elif icb_l1 or icb_l2:
            matching_tickers = {
                t for t, (l1, l2) in self.industry_classifier._ticker_map.items()
                if (not icb_l1 or l1 == icb_l1) and (not icb_l2 or l2 == icb_l2)
            }
            df = df[df["ticker_folder"].astype(str).str.upper().isin(matching_tickers)]

        return df["record_id"].astype(str).tolist()

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
            summaries.append({
                "ticker": t,
                "icb_l1": data["icb_l1"],
                "icb_l2": data["icb_l2"],
                "total_reports": len(all_yrs),
                "local_reports": len(loc_yrs),
                "has_local": len(loc_yrs) > 0,
                "year_range": f"{min(all_yrs)}-{max(all_yrs)}" if all_yrs else "N/A",
                "years": all_yrs,
            })

        # Sort so tickers with local files come first, then alphabet
        summaries.sort(key=lambda x: (-x["local_reports"], x["ticker"]))
        return summaries
