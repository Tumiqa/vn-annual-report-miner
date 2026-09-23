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
from typing import Dict, List, Optional, Any, Tuple, Set
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

            rec = {
                "record_id": str(row["record_id"]),
                "ticker": t,
                "year": y,
                "exchange": norm_ex,
                "file_name": str(row["file_name"]),
                "relative_path": str(row["relative_path"]),
                "archive_period": str(row["archive_period"]),
                "source": "zenodo",
                "icb_l1": l1,
                "icb_l2": l2,
                "icb_l3": l3,
                "icb_l4": l4,
                "icb_code": icb_code,
                "file_size_mb": float(row["file_size_mb"]) if pd.notna(row["file_size_mb"]) else 0.0,
                "status": "available",
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
        """Ultra-fast search across 14,528 reports via O(1) Inverted Indices."""
        self.initialize()
        results: List[Dict[str, Any]] = []
        total_matched = 0

        # Zenodo/Unified search via inverted index
        if source_filter != "local_only" and self._records_cache:
            matched_indices: Optional[Set[int]] = None

            # 1. Ticker filter
            if ticker and ticker.strip():
                tokens, is_multi = self._parse_ticker_filter(ticker)
                if tokens:
                    t_indices: Set[int] = set()
                    if not is_multi:
                        tok = tokens[0]
                        if tok in self._ticker_index:
                            t_indices.update(self._ticker_index[tok])
                        for ut in self._unique_tickers:
                            if tok in ut and ut != tok:
                                t_indices.update(self._ticker_index[ut])
                    else:
                        for tok in tokens:
                            if tok in self._ticker_index:
                                t_indices.update(self._ticker_index[tok])
                            elif len(tok) < 3:
                                for ut in self._unique_tickers:
                                    if tok in ut:
                                        t_indices.update(self._ticker_index[ut])
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
