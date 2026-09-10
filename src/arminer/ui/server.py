# -*- coding: utf-8 -*-
"""
arminer.ui.server
==================
FastAPI Web Server for arminer interactive UI.
Supports:
- Unified Report Catalog (Local 2,645+ PDFs + Zenodo 13,982 records)
- Complete Dictionary Studio (Add, Edit, Delete, Create, Export)
- Single PDF Upload & Batch Folder Scan
- Research Panel Export (Excel Multi-Sheets, Stata .dta, CSV)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
import uuid
import math
import re
from pathlib import Path
from typing import Optional, List, Dict, Any
import warnings
from pydantic import BaseModel

# Suppress harmless Hugging Face Hub unauthenticated warning for public datasets
warnings.filterwarnings("ignore", message=".*unauthenticated requests to the HF Hub.*")

# Auto-load HF_TOKEN from .env if present
_env_file = Path(__file__).resolve().parent.parent.parent.parent / ".env"
if _env_file.exists() and "HF_TOKEN" not in os.environ:
    try:
        for _line in _env_file.read_text(encoding="utf-8").splitlines():
            if _line.strip().startswith("HF_TOKEN="):
                os.environ["HF_TOKEN"] = _line.split("=", 1)[1].strip()
                break
    except Exception:
        pass



from fastapi import FastAPI, File, Form, UploadFile, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse
import pandas as pd
import fitz
from loguru import logger

from arminer.core.smart_mode import FlexibleDictionary, SmartVariableCalculator, ResearchOutputGenerator
from arminer.mining.matcher import GenericFuzzyMatcher
from arminer.data.pdf_source import PDFSource
from arminer.data.catalog import UnifiedCatalog
from arminer.core.dictionary_manager import DictionaryManager
from arminer.data.zenodo_downloader import ZenodoDownloader
from arminer.data.news_scraper import (
    CompanyWebsiteResolver,
    UniversalNewsExtractor,
    MultiSourceNewsAggregator,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
DOWNLOAD_DIR = Path(tempfile.gettempdir()) / "arminer_downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

zenodo_downloader = ZenodoDownloader()
news_resolver = CompanyWebsiteResolver()
news_aggregator = MultiSourceNewsAggregator(resolver=news_resolver)

app = FastAPI(title="arminer Web Studio", description="Enterprise Annual Report Miner", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

catalog = UnifiedCatalog()
dict_mgr = DictionaryManager()


# =====================================================================
# Catalog Endpoints (Kho Dữ Liệu Báo Cáo)
# =====================================================================

@app.get("/api/catalog/tickers")
def get_catalog_tickers():
    """Danh sách tất cả mã chứng khoán kèm số năm báo cáo sẵn có."""
    return {"tickers": catalog.get_ticker_summary()}


@app.get("/api/catalog/sectors")
def get_catalog_sectors():
    """Danh mục phân ngành ICB Level 1 và Level 2 kèm số lượng báo cáo."""
    return catalog.get_sectors()


@app.get("/api/catalog/search")
def search_catalog(
    ticker: Optional[str] = Query(None),
    year_from: Optional[int] = Query(None),
    year_to: Optional[int] = Query(None),
    icb_l1: Optional[str] = Query(None),
    icb_l2: Optional[str] = Query(None),
    source_filter: str = Query("all"),
    limit: int = Query(500),
):
    """Tìm kiếm báo cáo trong kho dữ liệu với lọc theo ngành ICB."""
    results, total_matched = catalog.search(
        ticker=ticker,
        year_from=year_from,
        year_to=year_to,
        icb_l1=icb_l1,
        icb_l2=icb_l2,
        source_filter=source_filter,
        limit=limit,
        return_total=True,
    )
    return {
        "total_found": len(results),
        "total_matched": total_matched,
        "reports": results,
    }


@app.get("/api/catalog/matched-ids")
def get_matched_catalog_ids(
    ticker: Optional[str] = Query(None),
    year_from: Optional[int] = Query(None),
    year_to: Optional[int] = Query(None),
    icb_l1: Optional[str] = Query(None),
    icb_l2: Optional[str] = Query(None),
):
    """Lấy danh sách toàn bộ record_id khớp bộ lọc từ Zenodo mà không bị giới hạn hiển thị."""
    matched_ids = catalog.get_matched_record_ids(
        ticker=ticker,
        year_from=year_from,
        year_to=year_to,
        icb_l1=icb_l1,
        icb_l2=icb_l2,
    )
    return {
        "total_matched": len(matched_ids),
        "record_ids": matched_ids,
    }


class AddFolderRequest(BaseModel):
    folder_path: str


@app.post("/api/catalog/add-folder")
def add_catalog_folder(req: AddFolderRequest):
    """Cho phép người dùng thêm bất kỳ thư mục báo cáo nào trên máy để lập chỉ mục."""
    p = Path(req.folder_path)
    if not p.exists() or not p.is_dir():
        raise HTTPException(status_code=400, detail=f"Thư mục không tồn tại: {req.folder_path}")

    added = catalog.index_directory(p, source_name="user_folder")
    return {
        "success": True,
        "added_count": added,
        "total_local": len(catalog._local_index),
        "message": f"Đã lập chỉ mục thêm {added} báo cáo từ thư mục: {req.folder_path}",
    }



# =====================================================================
# Dictionary Studio Endpoints (Thêm / Sửa / Xóa Từ Điển)
# =====================================================================

@app.get("/api/dictionaries")
def list_dictionaries():
    """Liệt kê tất cả các bộ từ điển."""
    return {"dictionaries": dict_mgr.list_topics()}


@app.get("/api/dictionaries/{topic_id}")
def get_dictionary_detail(topic_id: str):
    """Chi tiết một bộ từ điển và toàn bộ từ khóa."""
    try:
        return dict_mgr.get_dictionary(topic_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


class AddKeywordRequest(BaseModel):
    keyword: str
    category: str = "default"
    weight: float = 1.0
    variants: str = ""


@app.post("/api/dictionaries/{topic_id}/keyword")
def add_keyword(topic_id: str, req: AddKeywordRequest):
    """Thêm một từ khóa mới vào từ điển."""
    try:
        item = dict_mgr.add_keyword(
            topic_id=topic_id,
            keyword=req.keyword,
            category=req.category,
            weight=req.weight,
            variants=req.variants,
        )
        return {"success": True, "added": item}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class UpdateKeywordRequest(BaseModel):
    old_keyword: str
    new_keyword: str
    category: str
    weight: float = 1.0
    variants: Optional[str] = None


@app.put("/api/dictionaries/{topic_id}/keyword")
def update_keyword(topic_id: str, req: UpdateKeywordRequest):
    """Sửa một từ khóa hiện có."""
    try:
        updated = dict_mgr.update_keyword(
            topic_id=topic_id,
            old_keyword=req.old_keyword,
            new_keyword=req.new_keyword,
            category=req.category,
            weight=req.weight,
            variants=req.variants,
        )
        return {"success": True, "updated": updated}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class DeleteKeywordRequest(BaseModel):
    keyword: str


@app.delete("/api/dictionaries/{topic_id}/keyword")
def delete_keyword(topic_id: str, req: DeleteKeywordRequest):
    """Xóa một từ khóa khỏi từ điển."""
    try:
        dict_mgr.delete_keyword(topic_id, req.keyword)
        return {"success": True, "deleted": req.keyword}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class CreateTopicRequest(BaseModel):
    id: str
    name: str
    initial_keywords: Optional[List[Dict[str, Any]]] = None


@app.post("/api/dictionaries/create")
def create_topic(req: CreateTopicRequest):
    """Tạo mới một bộ từ điển hoàn toàn riêng."""
    try:
        new_dict = dict_mgr.create_topic(req.id, req.name, req.initial_keywords)
        return {"success": True, "dictionary": new_dict}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/dictionaries/{topic_id}")
def delete_topic(topic_id: str):
    """Xóa hoàn toàn một bộ từ điển."""
    try:
        dict_mgr.delete_topic(topic_id)
        return {"success": True, "deleted": topic_id}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



# =====================================================================
# Mining Execution Endpoints
# =====================================================================

def _resolve_dictionary(topic: Optional[str] = None, keywords: Optional[str] = None) -> FlexibleDictionary:
    """Load the appropriate dictionary object."""
    if keywords and keywords.strip():
        return FlexibleDictionary.from_string(keywords.strip())

    if topic:
        path = dict_mgr._get_dict_path(topic)
        if path.exists():
            return FlexibleDictionary.load(path)

    # Fallback to default
    templates_dir = Path(__file__).resolve().parent.parent / "templates"
    return FlexibleDictionary.load(templates_dir / "blockchain_dictionary.yaml")


class ScanSelectedRequest(BaseModel):
    record_ids: Optional[List[str]] = None
    report_paths: Optional[List[str]] = None
    topic: Optional[str] = "blockchain"
    keywords: Optional[str] = None
    threshold: int = 85


@app.post("/api/scan-selected")
def scan_selected_reports(req: ScanSelectedRequest):
    """Khai phá danh sách các file báo cáo đã chọn từ kho Zenodo hoặc local."""
    target_items: List[Dict[str, Any]] = []

    # 1. Process Zenodo record_ids (auto-downloads on-demand)
    if req.record_ids:
        records = catalog.lookup_records(req.record_ids)
        if records:
            downloaded = zenodo_downloader.download_reports(records)
            for r in downloaded:
                lp = r.get("local_path")
                if lp and Path(lp).exists():
                    target_items.append({
                        "path": Path(lp),
                        "ticker": r.get("ticker", ""),
                        "year": r.get("year"),
                        "icb_l1": r.get("icb_l1", "Khác"),
                        "icb_l2": r.get("icb_l2", "Khác"),
                    })

    # 2. Process direct local report_paths (Tab 3 or custom)
    if req.report_paths:
        for fp in req.report_paths:
            p = Path(fp)
            if p.exists():
                parsed = PDFSource.parse_filename(p)
                t_val = parsed[0] if parsed else p.parent.name.replace("MST_", "").upper()
                y_val = parsed[1] if parsed else None
                l1, l2 = catalog.industry_classifier.get_industry(t_val)
                target_items.append({
                    "path": p,
                    "ticker": t_val,
                    "year": y_val,
                    "icb_l1": l1,
                    "icb_l2": l2,
                })

    if not target_items:
        err_msg = "Không có báo cáo nào khả dụng để quét."
        if zenodo_downloader.circuit_breaker.is_open:
            err_msg += f" Máy chủ Zenodo (Châu Âu) hiện đang quá tải ({zenodo_downloader.circuit_breaker.last_error})."
        err_msg += " Bạn có thể đặt file PDF vào thư mục 'data/reports/' để quét offline siêu tốc không phụ thuộc mạng."
        raise HTTPException(status_code=400, detail=err_msg)

    flex_dict = _resolve_dictionary(topic=req.topic, keywords=req.keywords)
    core_dict = flex_dict.to_core_dictionary()
    matcher = GenericFuzzyMatcher(dictionary=core_dict, threshold=req.threshold)
    calc = SmartVariableCalculator()

    rows = []
    all_snippets = []
    all_raw_keywords = []

    for item in target_items:
        p = item["path"]
        text = ""
        n_pages = 1
        if p.suffix.lower() == ".pdf":
            try:
                doc = fitz.open(p)
                text = "\n".join(page.get_text() for page in doc)
                n_pages = len(doc)
                doc.close()
            except Exception:
                continue
        else:
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

        words = text.split()
        total_words = len(words)
        matches = matcher.search(text, use_fuzzy=True) if total_words > 0 else []

        vars_r = calc.calculate_all(
            matches, total_words,
            category_names=flex_dict.categories,
            topic_prefix=req.topic or "topic",
            total_dict_keywords=len(flex_dict.entries),
            classification_rules=flex_dict.classification_rules,
        )

        row = {
            "ticker": item["ticker"],
            "year": item["year"],
            "icb_level1": item["icb_l1"],
            "icb_level2": item["icb_l2"],
            "file": p.name,
            "pages": n_pages,
            **vars_r,
        }
        rows.append(row)

        # Collect raw keyword counts for this firm-year (Sheet 1: Raw_Keywords)
        kw_counts = {}
        for m in matches:
            kw = m.get("keyword_canonical", m.get("keyword_found", ""))
            cat = m.get("category", "default")
            kw_counts[(kw, cat)] = kw_counts.get((kw, cat), 0) + 1

        for (kw, cat), cnt in kw_counts.items():
            all_raw_keywords.append({
                "Firm": item["ticker"],
                "Year": item["year"],
                "Keyword": kw,
                "Category": cat,
                "Frequency": cnt,
            })

        # Collect sample snippets (up to 3 per file)
        text_len = len(text)
        for m in matches[:3]:
            pos = m.get("position", 0)
            kw = m.get("keyword_found", "")
            snippet = text[max(0, pos - 70):min(text_len, pos + len(kw) + 70)].replace("\n", " ").strip()
            all_snippets.append({
                "ticker": row["ticker"],
                "year": row["year"],
                "keyword": kw,
                "category": m.get("category", "default"),
                "context": snippet,
            })

    if not rows:
        raise HTTPException(status_code=400, detail="Không thể trích xuất nội dung từ các file đã chọn.")

    df = pd.DataFrame(rows)
    first_cols = [c for c in ["ticker", "year", "icb_level1", "icb_level2", "file", "pages"] if c in df.columns]
    other_cols = [c for c in df.columns if c not in first_cols]
    df = df[first_cols + other_cols]

    # Generate research pack
    raw_df = pd.DataFrame(all_raw_keywords) if all_raw_keywords else None
    generator = ResearchOutputGenerator(DOWNLOAD_DIR)
    generator.generate_all(df, raw_keywords_df=raw_df)

    p_name = (req.topic or "topic").lower()
    freq_col = f"{p_name}_Frequency" if f"{p_name}_Frequency" in df.columns else f"{p_name}_frequency"
    total_mentions = int(df[freq_col].sum()) if freq_col in df.columns else 0
    firms_with_hits = int((df[freq_col] > 0).sum()) if freq_col in df.columns else 0

    return {
        "total_files": len(df),
        "files_with_hits": firms_with_hits,
        "total_mentions": total_mentions,
        "top_rows": df.head(50).to_dict(orient="records"),
        "snippets": all_snippets[:50],
        "excel_download": "/api/download/panel_data.xlsx",
        "stata_download": "/api/download/panel_data.dta",
        "csv_download": "/api/download/panel_data.csv",
    }


class ScanSectorRequest(BaseModel):
    icb_l1: Optional[str] = None
    icb_l2: Optional[str] = None
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    topic: Optional[str] = "blockchain"
    keywords: Optional[str] = None
    threshold: int = 85
    max_reports: Optional[int] = 50


@app.post("/api/scan-sector")
def scan_sector_reports(req: ScanSectorRequest):
    """Khai phá các báo cáo thuộc một ngành từ Zenodo."""
    reports = catalog.search(
        icb_l1=req.icb_l1,
        icb_l2=req.icb_l2,
        year_from=req.year_from,
        year_to=req.year_to,
        limit=req.max_reports or 50,
    )
    if isinstance(reports, tuple):
        reports = reports[0]

    record_ids = [r["record_id"] for r in reports if r.get("record_id")]
    if not record_ids:
        raise HTTPException(status_code=400, detail="Không tìm thấy báo cáo nào khớp với ngành đã chọn trong kho Zenodo.")

    return scan_selected_reports(ScanSelectedRequest(
        record_ids=record_ids,
        topic=req.topic,
        keywords=req.keywords,
        threshold=req.threshold,
    ))



@app.post("/api/scan-selected-stream")
async def scan_selected_stream(req: ScanSelectedRequest):
    """Khai phá báo cáo với progress streaming qua SSE."""

    async def event_generator():
        # --- Phase 1: Resolve target items ---
        target_items: List[Dict[str, Any]] = []

        if req.record_ids:
            yield {"event": "progress", "data": json.dumps(
                {"phase": "download", "current": 0, "total": len(req.record_ids),
                 "message": f"Đang tải {len(req.record_ids)} báo cáo từ Zenodo..."},
                ensure_ascii=False)}

            records = catalog.lookup_records(req.record_ids)
            if records:
                downloaded = zenodo_downloader.download_reports(records)
                for i, r in enumerate(downloaded):
                    lp = r.get("local_path")
                    status_flag = r.get("download_status", "unknown")
                    if lp and Path(lp).exists():
                        target_items.append({
                            "path": Path(lp),
                            "ticker": r.get("ticker", ""),
                            "year": r.get("year"),
                            "icb_l1": r.get("icb_l1", "Khác"),
                            "icb_l2": r.get("icb_l2", "Khác"),
                        })
                        tag = "Sẵn sàng (Local/Cache)" if status_flag == "local_ready" else "Đã tải xong"
                    else:
                        tag = "Bỏ qua (Zenodo bận/quá tải)"

                    yield {"event": "progress", "data": json.dumps(
                        {"phase": "download", "current": i + 1,
                         "total": len(downloaded),
                         "message": f"[{tag}] {i + 1}/{len(downloaded)}: {r.get('ticker', '?')} ({r.get('year', '?')})"},
                        ensure_ascii=False)}
                    await asyncio.sleep(0)  # Yield control

        if req.report_paths:
            for fp in req.report_paths:
                p = Path(fp)
                if p.exists():
                    parsed = PDFSource.parse_filename(p)
                    t_val = parsed[0] if parsed else p.parent.name.replace("MST_", "").upper()
                    y_val = parsed[1] if parsed else None
                    l1, l2 = catalog.industry_classifier.get_industry(t_val)
                    target_items.append({
                        "path": p, "ticker": t_val, "year": y_val,
                        "icb_l1": l1, "icb_l2": l2,
                    })

        if not target_items:
            err_msg = "Không có báo cáo nào khả dụng để quét."
            if zenodo_downloader.circuit_breaker.is_open:
                err_msg += f" Zenodo hiện đang quá tải hoặc từ chối kết nối ({zenodo_downloader.circuit_breaker.last_error})."
            err_msg += " Gợi ý: Bạn có thể sao chép trực tiếp file PDF vào thư mục 'data/reports/' để hệ thống tự nhận diện và quét offline siêu tốc."
            yield {"event": "error", "data": json.dumps(
                {"detail": err_msg},
                ensure_ascii=False)}
            return

        # --- Phase 2: Mining ---
        flex_dict = _resolve_dictionary(topic=req.topic, keywords=req.keywords)
        core_dict = flex_dict.to_core_dictionary()
        matcher = GenericFuzzyMatcher(dictionary=core_dict, threshold=req.threshold)
        calc = SmartVariableCalculator()

        rows = []
        all_snippets = []
        all_raw_keywords = []
        total = len(target_items)

        for idx, item in enumerate(target_items):
            p = item["path"]
            ticker_label = f"{item['ticker']}/{item['year'] or '?'}"

            yield {"event": "progress", "data": json.dumps(
                {"phase": "mining", "current": idx, "total": total,
                 "message": f"Đang khai phá {idx + 1}/{total}: {ticker_label}",
                 "ticker": item['ticker'], "year": item.get('year')},
                ensure_ascii=False)}

            text = ""
            n_pages = 1
            if p.suffix.lower() == ".pdf":
                try:
                    doc = fitz.open(p)
                    text = "\n".join(page.get_text() for page in doc)
                    n_pages = len(doc)
                    doc.close()
                except Exception:
                    await asyncio.sleep(0)
                    continue
            else:
                try:
                    text = p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    await asyncio.sleep(0)
                    continue

            words = text.split()
            total_words = len(words)
            matches = matcher.search(text, use_fuzzy=True) if total_words > 0 else []

            vars_r = calc.calculate_all(
                matches, total_words,
                category_names=flex_dict.categories,
                topic_prefix=req.topic or "topic",
                total_dict_keywords=len(flex_dict.entries),
                classification_rules=flex_dict.classification_rules,
            )

            row = {
                "ticker": item["ticker"],
                "year": item["year"],
                "icb_level1": item["icb_l1"],
                "icb_level2": item["icb_l2"],
                "file": p.name,
                "pages": n_pages,
                **vars_r,
            }
            rows.append(row)

            # Collect raw keyword counts for this firm-year (Sheet 1: Raw_Keywords)
            kw_counts = {}
            for m in matches:
                kw = m.get("keyword_canonical", m.get("keyword_found", ""))
                cat = m.get("category", "default")
                kw_counts[(kw, cat)] = kw_counts.get((kw, cat), 0) + 1

            for (kw, cat), cnt in kw_counts.items():
                all_raw_keywords.append({
                    "Firm": item["ticker"],
                    "Year": item["year"],
                    "Keyword": kw,
                    "Category": cat,
                    "Frequency": cnt,
                })

            text_len = len(text)
            for m in matches[:3]:
                pos = m.get("position", 0)
                kw = m.get("keyword_found", "")
                snippet = text[max(0, pos - 70):min(text_len, pos + len(kw) + 70)].replace("\n", " ").strip()
                all_snippets.append({
                    "ticker": row["ticker"], "year": row["year"],
                    "keyword": kw, "category": m.get("category", "default"),
                    "context": snippet,
                })

            await asyncio.sleep(0)  # Yield control for SSE flush

        # --- Phase 3: Generate output ---
        yield {"event": "progress", "data": json.dumps(
            {"phase": "export", "current": total, "total": total,
             "message": "Đang tạo file kết quả nghiên cứu..."},
            ensure_ascii=False)}

        if not rows:
            yield {"event": "error", "data": json.dumps(
                {"detail": "Không trích xuất được nội dung từ các file."},
                ensure_ascii=False)}
            return

        df = pd.DataFrame(rows)
        first_cols = [c for c in ["ticker", "year", "icb_level1", "icb_level2", "file", "pages"] if c in df.columns]
        other_cols = [c for c in df.columns if c not in first_cols]
        df = df[first_cols + other_cols]

        raw_df = pd.DataFrame(all_raw_keywords) if all_raw_keywords else None
        generator = ResearchOutputGenerator(DOWNLOAD_DIR)
        generator.generate_all(df, raw_keywords_df=raw_df)

        p_name = (req.topic or "topic").lower()
        freq_col = f"{p_name}_Frequency" if f"{p_name}_Frequency" in df.columns else f"{p_name}_frequency"
        total_mentions = int(df[freq_col].sum()) if freq_col in df.columns else 0
        firms_with_hits = int((df[freq_col] > 0).sum()) if freq_col in df.columns else 0

        yield {"event": "complete", "data": json.dumps({
            "total_files": len(df),
            "files_with_hits": firms_with_hits,
            "total_mentions": total_mentions,
            "top_rows": df.head(50).to_dict(orient="records"),
            "snippets": all_snippets[:50],
            "excel_download": "/api/download/panel_data.xlsx",
            "stata_download": "/api/download/panel_data.dta",
            "csv_download": "/api/download/panel_data.csv",
        }, ensure_ascii=False, default=str)}

    return EventSourceResponse(event_generator())


class DownloadReportsZipRequest(BaseModel):
    record_ids: Optional[List[str]] = None
    report_paths: Optional[List[str]] = None
    structure: Optional[str] = "ticker"  # "ticker", "sector", "year"
    cleanup_cache: Optional[bool] = False  # Xoa file PDF sau khi nen vao zip de tiet kiem o dia


@app.post("/api/catalog/download-zip-stream")
async def download_reports_zip_stream(req: DownloadReportsZipRequest):
    """Tải về các file báo cáo gốc và nén ZIP phân thư mục chuẩn với SSE streaming progress."""
    from datetime import datetime
    from arminer.export.zip_export import create_reports_zip_archive

    async def event_generator():
        yield {
            "event": "progress",
            "data": json.dumps(
                {
                    "phase": "prepare",
                    "current": 0,
                    "total": len(req.record_ids or []) + len(req.report_paths or []),
                    "message": "Đang kiểm tra danh mục báo cáo được chọn...",
                },
                ensure_ascii=False,
            ),
        }
        await asyncio.sleep(0)

        target_records: List[Dict[str, Any]] = []

        # 1. Zenodo record_ids
        if req.record_ids:
            records = catalog.lookup_records(req.record_ids)
            if records:
                total_rec = len(records)
                yield {
                    "event": "progress",
                    "data": json.dumps(
                        {
                            "phase": "download",
                            "current": 0,
                            "total": total_rec,
                            "message": f"Đang chuẩn bị tải {total_rec} file gốc từ kho Zenodo...",
                        },
                        ensure_ascii=False,
                    ),
                }
                await asyncio.sleep(0)

                for idx, r in enumerate(records, 1):
                    lp = await asyncio.to_thread(
                        zenodo_downloader.get_pdf_path,
                        ticker=r.get("ticker", ""),
                        year=r.get("year", 0),
                        archive_period=r.get("archive_period", ""),
                        relative_path=r.get("relative_path", ""),
                    )
                    if lp and Path(lp).exists():
                        r["local_path"] = str(Path(lp).resolve())
                        target_records.append(r)
                        status_msg = f"[Sẵn sàng] Đã chuẩn bị {idx}/{total_rec}: {r.get('ticker', '?')} ({r.get('year', '?')})"
                    else:
                        status_msg = f"[Bỏ qua] Không thể tải {idx}/{total_rec}: {r.get('ticker', '?')} ({r.get('year', '?')}) - Zenodo quá tải"

                    yield {
                        "event": "progress",
                        "data": json.dumps(
                            {
                                "phase": "download",
                                "current": idx,
                                "total": total_rec,
                                "message": status_msg,
                            },
                            ensure_ascii=False,
                        ),
                    }
                    await asyncio.sleep(0)

        # 2. Local report_paths
        if req.report_paths:
            for fp in req.report_paths:
                p = Path(fp)
                if p.exists():
                    parsed = PDFSource.parse_filename(p)
                    t_val = parsed[0] if parsed else p.parent.name.replace("MST_", "").upper()
                    y_val = parsed[1] if parsed else None
                    l1, l2 = catalog.industry_classifier.get_industry(t_val)
                    target_records.append({
                        "local_path": str(p.resolve()),
                        "ticker": t_val,
                        "year": y_val,
                        "file_name": p.name,
                        "icb_l1": l1,
                        "icb_l2": l2,
                        "source": "Local",
                    })

        if not target_records:
            err_msg = "Không có báo cáo nào khả dụng để tạo file ZIP."
            if zenodo_downloader.circuit_breaker.is_open:
                err_msg += f" Máy chủ Zenodo hiện đang quá tải ({zenodo_downloader.circuit_breaker.last_error})."
            err_msg += " Bạn có thể sao chép trực tiếp file PDF vào thư mục 'data/reports/' để đóng gói offline."
            yield {
                "event": "error",
                "data": json.dumps(
                    {"detail": err_msg},
                    ensure_ascii=False,
                ),
            }
            return

        # Phase 2: Đóng gói và nén ZIP
        struct_labels = {
            "ticker": "theo Mã CK",
            "sector": "theo Ngành",
            "year": "theo Năm",
        }
        lbl = struct_labels.get(req.structure, "theo Mã CK")
        yield {
            "event": "progress",
            "data": json.dumps(
                {
                    "phase": "zip",
                    "current": 0,
                    "total": len(target_records),
                    "message": f"Đang đóng gói {len(target_records)} file gốc vào tệp ZIP ({lbl})...",
                },
                ensure_ascii=False,
            ),
        }
        await asyncio.sleep(0)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"BCTN_Goc_{req.structure}_{timestamp}.zip"
        zip_path = DOWNLOAD_DIR / zip_filename

        summary = create_reports_zip_archive(
            reports=target_records,
            output_zip_path=zip_path,
            structure=req.structure or "ticker",
        )

        # Neu nguoi dung yeu cau don sach bo nho dem sau khi tao ZIP
        if req.cleanup_cache:
            for r in target_records:
                lp = r.get("local_path")
                if lp and Path(lp).exists():
                    try:
                        Path(lp).unlink()
                    except Exception:
                        pass

        yield {
            "event": "complete",
            "data": json.dumps(
                {
                    "download_url": f"/api/download/{zip_filename}",
                    "filename": zip_filename,
                    "total_files": summary.get("zipped_reports", 0),
                    "zip_size_mb": summary.get("zip_size_mb", 0),
                    "structure": req.structure,
                    "message": f"Đã nén thành công {summary.get('zipped_reports', 0)} báo cáo ({summary.get('zip_size_mb', 0)} MB)",
                },
                ensure_ascii=False,
            ),
        }

    return EventSourceResponse(event_generator())


@app.get("/api/catalog/cache-status")
def catalog_cache_status():
    """Báo cáo tình trạng dung lượng bộ nhớ đệm Zenodo."""
    status = zenodo_downloader.get_cache_status()
    total_pdfs = sum(s.get("cached_pdfs", 0) for s in status.values())
    total_mb = round(sum(s.get("total_size_mb", 0.0) for s in status.values()), 1)
    return {
        "cache_root": str(zenodo_downloader.cache_root),
        "total_cached_pdfs": total_pdfs,
        "total_size_mb": total_mb,
        "details": status,
    }


@app.post("/api/catalog/clear-cache")
def catalog_clear_cache():
    """Xóa sạch bộ nhớ đệm Zenodo để giải phóng dung lượng ổ đĩa."""
    result = zenodo_downloader.clear_cache(also_clear_home_c=True)
    return result


@app.post("/api/scan-file")
async def scan_file(
    file: Optional[UploadFile] = File(None),
    filepath: Optional[str] = Form(None),
    keywords: Optional[str] = Form(None),
    topic: Optional[str] = Form(None),
    fuzzy: bool = Form(True),
    threshold: int = Form(85),
):
    """Quét 1 file PDF hoặc TXT (qua upload hoặc đường dẫn có sẵn)."""
    flex_dict = _resolve_dictionary(topic=topic, keywords=keywords)

    filename = "document"
    text = ""
    n_pages = 1

    if file and file.filename:
        filename = file.filename
        content = await file.read()
        if filename.lower().endswith(".pdf"):
            doc = fitz.open(stream=content, filetype="pdf")
            text = "\n".join(page.get_text() for page in doc)
            n_pages = len(doc)
            doc.close()
        else:
            text = content.decode("utf-8", errors="replace")
    elif filepath and os.path.exists(filepath):
        p = Path(filepath)
        filename = p.name
        if p.suffix.lower() == ".pdf":
            doc = fitz.open(p)
            text = "\n".join(page.get_text() for page in doc)
            n_pages = len(doc)
            doc.close()
        else:
            text = p.read_text(encoding="utf-8", errors="replace")
    else:
        raise HTTPException(status_code=400, detail="Vui lòng tải lên file hoặc cung cấp đường dẫn hợp lệ.")

    core_dict = flex_dict.to_core_dictionary()
    matcher = GenericFuzzyMatcher(dictionary=core_dict, threshold=threshold)
    matches = matcher.search(text, use_fuzzy=fuzzy)
    words = text.split()
    total_words = len(words)

    calc = SmartVariableCalculator()
    variables = calc.calculate_all(
        matches, total_words,
        category_names=flex_dict.categories,
        topic_prefix=topic or "topic",
        classification_rules=flex_dict.classification_rules,
    )

    snippets = []
    text_len = len(text)
    for m in matches[:50]:
        pos = m.get("position", 0)
        kw = m.get("keyword_found", "")
        start = max(0, pos - 80)
        end = min(text_len, pos + len(kw) + 80)
        snippets.append({
            "keyword": kw,
            "canonical": m.get("keyword_canonical", kw),
            "category": m.get("category", "default"),
            "similarity": m.get("similarity", 100),
            "match_type": m.get("match_type", "exact"),
            "context": text[start:end].replace("\n", " ").strip(),
        })

    parsed = PDFSource.parse_filename(filename)
    return {
        "filename": filename,
        "ticker": parsed[0] if parsed else None,
        "year": parsed[1] if parsed else None,
        "pages": n_pages,
        "total_words": total_words,
        "dictionary_name": flex_dict.name,
        "total_keywords": len(flex_dict.entries),
        "variables": variables,
        "snippets": snippets,
        "category_counts": {cat: sum(1 for m in matches if m.get("category") == cat) for cat in flex_dict.categories},
    }


@app.post("/api/scan-folder")
async def scan_folder(
    folder_path: str = Form(...),
    keywords: Optional[str] = Form(None),
    topic: Optional[str] = Form(None),
    fuzzy: bool = Form(True),
    threshold: int = Form(85),
    limit: Optional[int] = Form(None),
):
    """Quét cả thư mục báo cáo và tạo các file tải về."""
    p_folder = Path(folder_path)
    if not p_folder.exists() or not p_folder.is_dir():
        raise HTTPException(status_code=400, detail=f"Thư mục không tồn tại: {folder_path}")

    flex_dict = _resolve_dictionary(topic=topic, keywords=keywords)
    core_dict = flex_dict.to_core_dictionary()
    matcher = GenericFuzzyMatcher(dictionary=core_dict, threshold=threshold)
    calc = SmartVariableCalculator()

    supported_exts = {".pdf", ".txt"}
    files = sorted([f for f in p_folder.rglob("*") if f.is_file() and f.suffix.lower() in supported_exts])
    if limit:
        files = files[:limit]

    if not files:
        raise HTTPException(status_code=400, detail="Không tìm thấy file PDF hoặc TXT nào trong thư mục.")

    rows = []
    all_raw_keywords = []

    for f in files:
        text = ""
        n_pages = 1
        if f.suffix.lower() == ".pdf":
            try:
                doc = fitz.open(f)
                text = "\n".join(page.get_text() for page in doc)
                n_pages = len(doc)
                doc.close()
            except Exception:
                continue
        else:
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

        words = text.split()
        total_words = len(words)
        matches = matcher.search(text, use_fuzzy=fuzzy) if total_words > 0 else []

        vars_r = calc.calculate_all(
            matches, total_words,
            category_names=flex_dict.categories,
            topic_prefix=topic or "topic",
            total_dict_keywords=len(flex_dict.entries),
            classification_rules=flex_dict.classification_rules,
        )

        parsed = PDFSource.parse_filename(f)
        ticker_val = parsed[0] if parsed else None
        year_val = parsed[1] if parsed else None

        row = {
            "ticker": ticker_val,
            "year": year_val,
            "file": f.name,
            "pages": n_pages,
            **vars_r,
        }
        rows.append(row)

        kw_counts = {}
        for m in matches:
            kw = m.get("keyword_canonical", m.get("keyword_found", ""))
            cat = m.get("category", "default")
            kw_counts[(kw, cat)] = kw_counts.get((kw, cat), 0) + 1

        for (kw, cat), cnt in kw_counts.items():
            all_raw_keywords.append({
                "Firm": ticker_val or f.stem,
                "Year": year_val or "N/A",
                "Keyword": kw,
                "Category": cat,
                "Frequency": cnt,
            })

    if not rows:
        raise HTTPException(status_code=400, detail="Không xử lý được file nào.")

    df = pd.DataFrame(rows)
    first_cols = [c for c in ["ticker", "year", "file", "pages"] if c in df.columns]
    other_cols = [c for c in df.columns if c not in first_cols]
    df = df[first_cols + other_cols]

    raw_df = pd.DataFrame(all_raw_keywords) if all_raw_keywords else None
    generator = ResearchOutputGenerator(DOWNLOAD_DIR)
    generator.generate_all(df, raw_keywords_df=raw_df)

    p_name = (topic or "topic").lower()
    freq_col = f"{p_name}_Frequency" if f"{p_name}_Frequency" in df.columns else f"{p_name}_frequency"
    df_sorted = df.sort_values(by=freq_col, ascending=False) if freq_col in df.columns else df

    return {
        "total_files": len(df),
        "files_with_hits": int((df[freq_col] > 0).sum()) if freq_col in df.columns else 0,
        "total_mentions": int(df[freq_col].sum()) if freq_col in df.columns else 0,
        "top_rows": df_sorted.head(30).to_dict(orient="records"),
        "excel_download": "/api/download/panel_data.xlsx",
        "stata_download": "/api/download/panel_data.dta",
        "csv_download": "/api/download/panel_data.csv",
    }


# =====================================================================
# Financial Data Endpoints (vnfinancialdata integration)
# =====================================================================

_VNF_AVAILABLE = None
_CACHED_VNF_TICKERS: Optional[set[str]] = None

def _check_vnf():
    """Check if vnfinancialdata is installed and importable."""
    global _VNF_AVAILABLE
    if _VNF_AVAILABLE is None:
        try:
            import vnfinancialdata
            _VNF_AVAILABLE = True
        except ImportError:
            _VNF_AVAILABLE = False
    return _VNF_AVAILABLE


def _get_supported_vnf_tickers() -> set[str]:
    """Return cached set of uppercase tickers supported by vnfinancialdata."""
    global _CACHED_VNF_TICKERS
    if _CACHED_VNF_TICKERS is not None:
        return _CACHED_VNF_TICKERS

    if not _check_vnf():
        return set()

    try:
        import vnfinancialdata.loader as l
        import pandas as pd
        p_hsx = l._download_parquet('HSX', 'balance_sheet')
        p_hnx = l._download_parquet('HNX', 'balance_sheet')
        s_hsx = set(pd.read_parquet(p_hsx, columns=['ticker'])['ticker'].unique())
        s_hnx = set(pd.read_parquet(p_hnx, columns=['ticker'])['ticker'].unique())
        _CACHED_VNF_TICKERS = {str(t).upper().strip() for t in (s_hsx | s_hnx)}
        logger.info(f"Loaded {len(_CACHED_VNF_TICKERS)} supported tickers from vnfinancialdata")
    except Exception as e:
        logger.warning(f"Could not load VNF tickers: {e}")
        _CACHED_VNF_TICKERS = set()
    return _CACHED_VNF_TICKERS


@app.get("/api/financial/supported-tickers")
def financial_supported_tickers():
    """Return all tickers supported by vnfinancialdata and common missing ticker explanations."""
    valid = _get_supported_vnf_tickers()
    return {
        "supported_tickers": sorted(list(valid)),
        "count": len(valid),
        "notable_missing": {
            "SSI": "Khuyết trong bộ dữ liệu gốc vnfinancialdata (HOSE)",
            "SCR": "Khuyết trong bộ dữ liệu gốc vnfinancialdata (HOSE)",
            "SCS": "Khuyết trong bộ dữ liệu gốc vnfinancialdata (HOSE)",
            "OPC": "Khuyết trong bộ dữ liệu gốc vnfinancialdata (HOSE)",
            "AAS": "Sàn UPCoM (vnfinancialdata chỉ hỗ trợ HSX/HNX)",
            "ABW": "Sàn UPCoM (vnfinancialdata chỉ hỗ trợ HSX/HNX)",
            "ART": "Sàn UPCoM (vnfinancialdata chỉ hỗ trợ HSX/HNX)",
            "PHS": "Sàn UPCoM (vnfinancialdata chỉ hỗ trợ HSX/HNX)",
            "SBS": "Sàn UPCoM (vnfinancialdata chỉ hỗ trợ HSX/HNX)",
        }
    }


@app.get("/api/financial/tickers-by-sector")
def financial_tickers_by_sector():
    """Return ICB L1→L2→tickers tree for the financial tab sector selector, strictly filtered to only tickers present in vnfinancialdata."""
    from arminer.data.industry import IndustryClassifier
    ic = IndustryClassifier()
    ic.initialize()
    raw_tree = ic.get_taxonomy_tree()
    valid_tickers = _get_supported_vnf_tickers()

    if not valid_tickers:
        return raw_tree

    filtered_sectors = []
    for sector in raw_tree.get("sectors", []):
        sub_list = []
        sector_total = 0
        for sub in sector.get("subsectors", []):
            filt_tickers = [t for t in sub.get("tickers", []) if t.upper() in valid_tickers]
            if filt_tickers:
                sector_total += len(filt_tickers)
                sub_list.append({
                    "name": sub["name"],
                    "ticker_count": len(filt_tickers),
                    "tickers": sorted(filt_tickers),
                })
        if sub_list:
            filtered_sectors.append({
                "name": sector["name"],
                "total_tickers": sector_total,
                "subsectors": sub_list,
            })
    return {"sectors": filtered_sectors}


def get_available_financial_ratios(code_set: set) -> list[str]:
    """Determine which financial ratios can actually be calculated from available item codes across all sectors."""
    if not code_set:
        return []

    def has_item(patterns):
        for p in patterns:
            for c in code_set:
                if p.lower() in c.lower():
                    return True
        return False

    eat = has_item(["loi_nhuan_sau_thue", "lai_sau_thue", "lai_lo_thuan_sau_thue", "is_loi_nhuan_ke_toan_sau_thue"])
    revenue = has_item(["doanh_thu_thuan", "doanh_so_thuan", "doanh_thu_hoat_dong", "tong_thu_nhap_hoat_dong", "thu_nhap_lai_thuan", "phi_bao_hiem_thuan"])
    ebt = has_item(["loi_nhuan_truoc_thue", "lai_truoc_thue", "lai_lo_rong_truoc_thue", "tong_loi_nhuan_ke_toan_truoc_thue"])
    tax = has_item(["thue_tndn", "thue_thu_nhap_doanh_nghiep"])
    ebit = has_item(["is_ebit"]) or (ebt and has_item(["lai_vay"]))
    gross_profit = has_item(["loi_nhuan_gop", "lai_gop", "thu_nhap_lai_thuan"]) or (revenue and has_item(["gia_von"]))
    assets = has_item(["tong_tai_san", "tong_cong_tai_san"])
    equity = has_item(["von_chu_so_huu", "von_va_cac_quy"])
    debt = has_item(["no_phai_tra", "tong_no_phai_tra"])
    curr_assets = has_item(["tai_san_ngan_han"])
    curr_liab = has_item(["no_ngan_han"])
    inventory = has_item(["hang_ton_kho"])
    cogs = has_item(["gia_von"])
    payables = has_item(["phai_tra_nguoi_ban"])
    cash = has_item(["tien_va_tuong_duong_tien", "bs_tien"])
    fixed_assets = has_item(["tai_san_co_dinh", "tscd_huu_hinh"])
    retained_earnings = has_item(["chua_phan_phoi"])
    fin_debt = has_item(["vay_ngan_han", "vay_dai_han", "vay_va_no"])

    cfo = has_item(["kinh_doanh", "san_xuat_kinh_doanh"]) and any(c.startswith("cf_") for c in code_set)
    capex = has_item(["mua_sam", "xay_dung_tscd"]) and any(c.startswith("cf_") for c in code_set)

    bank_loans = has_item(["cho_vay_khach_hang"])
    bank_deposits = has_item(["tien_gui_cua_khach_hang", "tien_gui"])
    bank_nii = has_item(["thu_nhap_lai_thuan"])
    bank_toi = has_item(["tong_thu_nhap_hoat_dong"])

    sec_margin = has_item(["cho_vay_va_ung_truoc", "cho_vay_margin", "cac_khoan_cho_vay"])
    sec_fvtpl = has_item(["fvtpl"])
    sec_broker_rev = has_item(["moi_gioi_chung_khoan"])

    re_prep = has_item(["nguoi_mua_tra_tien_truoc", "tra_tien_truoc"])

    checks = {
        # Pillar 1: Sinh loi
        "roa": eat and assets,
        "roe": eat and equity,
        "roce": ebit and assets and curr_liab,
        "roic": ebit and equity,
        "gross_margin": gross_profit and revenue,
        "operating_margin": ebit and revenue,
        "ebitda_margin": ebit and revenue,
        "net_margin": eat and revenue,
        "ebt_margin": ebt and revenue,
        "effective_tax_rate": tax and ebt,
        "dupont_tax_burden": eat and ebt,
        "dupont_interest_burden": ebt and ebit,
        "dupont_operating_margin": ebit and revenue,
        "dupont_asset_turnover": revenue and assets,
        "dupont_equity_multiplier": assets and equity,

        # Pillar 2: Cau truc von & Don bay
        "debt_to_assets": debt and assets,
        "debt_to_equity": debt and equity,
        "fin_debt_to_assets": fin_debt and assets,
        "fin_debt_to_equity": fin_debt and equity,
        "equity_to_assets": equity and assets,
        "equity_multiplier": assets and equity,
        "st_debt_to_total_debt": fin_debt,
        "lt_debt_to_total_debt": fin_debt,
        "interest_coverage": ebit and has_item(["lai_vay"]),
        "debt_to_ebitda": fin_debt and ebit,
        "cfo_to_debt": cfo and fin_debt,
        "cfo_to_liabilities": cfo and debt,
        "fin_leverage_ratio": assets and equity,

        # Pillar 3: Thanh khoan & Von luu dong
        "current_ratio": curr_assets and curr_liab,
        "quick_ratio": curr_assets and curr_liab,
        "cash_ratio": cash and curr_liab,
        "cash_to_assets": cash and assets,
        "working_capital": curr_assets and curr_liab,
        "nwc_to_assets": curr_assets and curr_liab and assets,
        "nwc_to_revenue": curr_assets and curr_liab and revenue,
        "defensive_interval": cash and revenue,

        # Pillar 4: Hieu qua hoat dong
        "asset_turnover": revenue and assets,
        "fixed_asset_turnover": revenue and fixed_assets,
        "inventory_turnover": cogs and inventory,
        "dio": cogs and inventory,
        "ar_turnover": revenue and has_item(["phai_thu"]),
        "dso": revenue and has_item(["phai_thu"]),
        "ap_turnover": cogs and payables,
        "dpo": cogs and payables,
        "ccc": cogs and inventory and payables,
        "working_capital_turnover": revenue and curr_assets,
        "sga_to_revenue": has_item(["quan_ly", "ban_hang"]) and revenue,
        "selling_cost_ratio": has_item(["ban_hang"]) and revenue,
        "admin_cost_ratio": has_item(["quan_ly"]) and revenue,

        # Pillar 5: Chat luong dong tien
        "cfo_to_net_income": cfo and eat,
        "cfo_to_revenue": cfo and revenue,
        "cfo_to_assets": cfo and assets,
        "cfo_to_equity": cfo and equity,
        "fcf": cfo,
        "fcf_to_net_income": cfo and eat,
        "fcf_to_revenue": cfo and revenue,
        "capex_to_revenue": capex and revenue,
        "capex_to_assets": capex and assets,
        "cfo_to_capex": cfo and capex,
        "accruals_to_assets": eat and cfo and assets,

        # Pillar 6: Ngan hang
        "bank_nim": bank_nii and assets,
        "bank_cir": bank_toi and has_item(["chi_phi_hoat_dong"]),
        "bank_ldr": bank_loans and bank_deposits,
        "bank_provision_coverage": has_item(["du_phong_rui_ro_cho_vay"]) and bank_loans,
        "bank_credit_cost": has_item(["chi_phi_du_phong_rui_ro_tin_dung"]) and bank_loans,
        "bank_loans_to_assets": bank_loans and assets,
        "bank_deposits_to_assets": bank_deposits and assets,
        "bank_equity_to_assets": equity and assets,
        "bank_nii_to_toi": bank_nii and bank_toi,
        "bank_non_interest_income_ratio": bank_toi and bank_nii,

        # Pillar 7: Chung khoan
        "margin_to_equity": sec_margin and equity,
        "pct_margin_loans": sec_margin and assets,
        "pct_advances": has_item(["ung_truoc_tien_ban"]) and assets,
        "pct_fvtpl": sec_fvtpl and assets,
        "pct_afs": has_item(["afs"]) and assets,
        "pct_htm": has_item(["htm"]) and assets,
        "pct_cash": cash and assets,
        "pct_brokerage_rev": sec_broker_rev and revenue,
        "pct_proprietary_rev": sec_fvtpl and revenue,
        "pct_margin_profit": has_item(["cho_vay_va_phai_thu"]) and revenue,
        "pct_ib_rev": has_item(["tu_van"]) and revenue,
        "pct_brokerage_cost": has_item(["moi_gioi"]) and has_item(["chi_phi_hoat_dong"]),
        "pct_proprietary_cost": has_item(["tu_doanh"]) and has_item(["chi_phi_hoat_dong"]),
        "pct_provision_cost": has_item(["du_phong"]) and has_item(["chi_phi_hoat_dong"]),

        # Pillar 8: Bat dong san
        "re_prepayments_to_inventory": re_prep and inventory,
        "re_prepayments_to_assets": re_prep and assets,
        "re_inventory_to_assets": inventory and assets,
        "re_wip_to_assets": has_item(["do_dang"]) and assets,
        "re_debt_to_inventory": fin_debt and inventory,
        "re_invest_prop_to_assets": has_item(["bat_dong_san_dau_tu"]) and assets,

        # Pillar 9: YoY
        "rev_growth_yoy": revenue,
        "gross_profit_growth_yoy": gross_profit,
        "ebit_growth_yoy": ebit,
        "ebt_growth_yoy": ebt,
        "eat_growth_yoy": eat,
        "eat_parent_growth_yoy": eat,
        "assets_growth_yoy": assets,
        "equity_growth_yoy": equity,
        "debt_growth_yoy": debt,
        "fin_debt_growth_yoy": fin_debt,
        "cfo_growth_yoy": cfo,
        "bank_loans_growth_yoy": bank_loans,
        "bank_deposits_growth_yoy": bank_deposits,
        "margin_loans_growth_yoy": sec_margin,

        # Pillar 10: Econometrics & Altman
        "size_ln": assets,
        "size_log10": assets,
        "tangibility": has_item(["huu_hinh"]) and assets,
        "firm_age_proxy": retained_earnings and assets,
        "altman_x1": curr_assets and curr_liab and assets,
        "altman_x2": retained_earnings and assets,
        "altman_x3": ebit and assets,
        "altman_x4": equity and debt,
        "altman_x5": revenue and assets,
        "altman_z_prime": curr_assets and curr_liab and retained_earnings and ebit and equity and debt and revenue and assets,
        "charter_capital_to_equity": has_item(["von_dieu_le", "von_gop"]) and equity,
        "retained_earnings_to_equity": retained_earnings and equity,
    }
    return [k for k, v in checks.items() if v]




@app.get("/api/financial/available-items")
def financial_available_items(
    ticker: str = Query(...),
    exchange: str = Query(""),
):
    """Probe which item_codes and financial ratios actually have calculable data for given ticker(s).
    Supports comma-separated tickers (e.g. VCB,CTG,BID).
    Returns lists of available item_codes and available_ratios based on accounting prerequisites.
    """
    if not _check_vnf():
        raise HTTPException(status_code=400, detail="vnfinancialdata chưa được cài đặt.")

    import vnfinancialdata as vnf

    ticker_list = [t.strip().upper() for t in ticker.split(",") if t.strip()]
    if not ticker_list:
        raise HTTPException(status_code=400, detail="Vui lòng cung cấp ít nhất 1 mã chứng khoán.")

    exchanges_to_try = [exchange.strip().upper()] if (isinstance(exchange, str) and exchange.strip()) else ["HSX", "HNX"]
    available_codes = set()
    probe_year = None

    for exch in exchanges_to_try:
        for stmt in ["balance_sheet", "income_statement", "cash_flow"]:
            try:
                df = vnf.get(
                    ticker=ticker_list,
                    statement=stmt,
                    exchange=exch,
                    start=2021,
                    end=2025,
                )
                if df.empty:
                    continue
                # Find latest year with data
                if probe_year is None:
                    probe_year = int(df["year"].max())
                # Get item_codes with non-null and non-zero values
                non_null = df.dropna(subset=["value"])
                non_null = non_null[non_null["value"] != 0]
                available_codes.update(non_null["item_code"].unique())
            except Exception:
                pass

    avail_ratios = get_available_financial_ratios(available_codes)

    return {
        "tickers": ticker_list,
        "probe_year": probe_year,
        "total_available": len(available_codes),
        "item_codes": sorted(available_codes),
        "total_ratios": len(avail_ratios),
        "available_ratios": avail_ratios,
    }


@app.get("/api/financial/status")
def financial_status():
    """Check vnfinancialdata availability and return full dataset metadata."""
    available = _check_vnf()
    result = {"available": available}
    if available:
        import vnfinancialdata as vnf
        from vnfinancialdata import config as vnf_cfg
        try:
            import importlib.metadata
            result["version"] = importlib.metadata.version("vnfinancialdata")
        except Exception:
            result["version"] = getattr(vnf, "__version__", getattr(vnf_cfg, "PACKAGE_VERSION", "0.1.2"))
        result["dataset_revision"] = getattr(vnf_cfg, "DATASET_REVISION", "unknown")
        result["schema_version"] = getattr(vnf_cfg, "DATASET_SCHEMA_VERSION", "unknown")
        result["supported_exchanges"] = sorted(list(getattr(vnf_cfg, "SUPPORTED_EXCHANGES", {"HSX", "HNX"})))
        result["supported_statements"] = sorted(list(getattr(vnf_cfg, "SUPPORTED_STATEMENTS", {"balance_sheet", "income_statement", "cash_flow"})))
        try:
            items_df = vnf.list_items()
            result["total_items"] = len(items_df)
            result["items_per_statement"] = items_df.groupby("statement").size().to_dict()
            result["active_items"] = int(items_df["active"].sum())
        except Exception:
            result["total_items"] = 702
            result["active_items"] = 702
            result["items_per_statement"] = {"balance_sheet": 311, "income_statement": 195, "cash_flow": 196}
        try:
            access = vnf.check_access()
            result["access"] = access
        except Exception:
            result["access"] = None
    else:
        result["install_cmd"] = 'pip install vnfinancialdata'
    return result


@app.get("/api/financial/items")
def financial_items(
    statement: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    active_only: bool = Query(True),
    limit: int = Query(0),
):
    """List or search financial items. limit=0 returns all items."""
    if not _check_vnf():
        raise HTTPException(status_code=400, detail="vnfinancialdata chua duoc cai dat. Chay: pip install vnfinancialdata")

    import vnfinancialdata as vnf

    if search and search.strip():
        df = vnf.search_items(search.strip(), statement=statement, active_only=active_only)
    else:
        df = vnf.list_items(statement=statement, active_only=active_only)

    if limit and limit > 0:
        df = df.head(limit)

    from arminer.export.financial_excel import classify_financial_item

    items = []
    for _, row in df.iterrows():
        desc = row.get("description", "")
        stmt = row.get("statement", "")
        code = row.get("item_code", "")
        name = row.get("item_name", "")
        order = int(row.get("item_order", 0)) if pd.notna(row.get("item_order")) else 0
        cat = classify_financial_item(code, name, stmt, order)
        items.append({
            "statement": stmt,
            "category": cat,
            "item_code": code,
            "item_name": name,
            "item_order": order,
            "unit": row.get("unit", "VND"),
            "description": str(desc) if pd.notna(desc) else "",
            "active": bool(row.get("active", True)),
        })

    return {
        "total": len(items),
        "items": items,
    }


@app.get("/api/financial/preview")
def financial_preview(
    ticker: str = Query(...),
    statement: str = Query("balance_sheet"),
    exchange: str = Query("HSX"),
    year: int = Query(2023),
):
    """Quick preview: get all item values for a single (ticker, year, statement)."""
    if not _check_vnf():
        raise HTTPException(status_code=400, detail="vnfinancialdata chua duoc cai dat.")

    import vnfinancialdata as vnf

    try:
        df = vnf.get(
            ticker=ticker.strip().upper(),
            statement=statement,
            exchange=exchange,
            start=year,
            end=year,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Loi truy van: {str(e)}")

    if df.empty:
        return {"ticker": ticker, "year": year, "statement": statement, "exchange": exchange, "items": []}

    items = []
    for _, row in df.iterrows():
        val = row.get("value")
        items.append({
            "item_code": row.get("item_code", ""),
            "item_name": row.get("item_name", ""),
            "value": float(val) if pd.notna(val) else None,
        })

    return {
        "ticker": ticker.upper(),
        "year": year,
        "statement": statement,
        "exchange": exchange,
        "total": len(items),
        "items": items,
    }


@app.get("/api/financial/presets")
def financial_presets():
    """Return preset item selections for common use cases."""
    return {
        "presets": [
            {
                "id": "basic",
                "name": "Cơ bản (Nghiên cứu)",
                "description": "5 chỉ tiêu cốt lõi + 4 chỉ số tài chính",
                "items": [
                    {"code": "bs_tong_tai_san", "name": "Tổng tài sản", "statement": "balance_sheet"},
                    {"code": "bs_von_chu_so_huu", "name": "Vốn chủ sở hữu", "statement": "balance_sheet"},
                    {"code": "bs_no_phai_tra", "name": "Nợ phải trả", "statement": "balance_sheet"},
                    {"code": "is_doanh_thu_thuan", "name": "Doanh thu thuần", "statement": "income_statement"},
                    {"code": "is_loi_nhuan_sau_thue", "name": "Lợi nhuận sau thuế", "statement": "income_statement"},
                ],
                "ratios": ["roa", "roe", "debt_to_assets", "size_ln"],
            },
            {
                "id": "full",
                "name": "Đầy đủ (Panel Data)",
                "description": "15+ chỉ tiêu phục vụ mô hình hồi quy",
                "items": [
                    {"code": "bs_tong_tai_san", "name": "Tổng tài sản", "statement": "balance_sheet"},
                    {"code": "bs_von_chu_so_huu", "name": "Vốn chủ sở hữu", "statement": "balance_sheet"},
                    {"code": "bs_no_phai_tra", "name": "Nợ phải trả", "statement": "balance_sheet"},
                    {"code": "bs_tai_san_ngan_han", "name": "Tài sản ngắn hạn", "statement": "balance_sheet"},
                    {"code": "bs_tai_san_dai_han", "name": "Tài sản dài hạn", "statement": "balance_sheet"},
                    {"code": "bs_no_ngan_han", "name": "Nợ ngắn hạn", "statement": "balance_sheet"},
                    {"code": "bs_no_dai_han", "name": "Nợ dài hạn", "statement": "balance_sheet"},
                    {"code": "bs_loi_nhuan_chua_phan_phoi", "name": "LNST chưa phân phối", "statement": "balance_sheet"},
                    {"code": "is_doanh_thu_thuan", "name": "Doanh thu thuần", "statement": "income_statement"},
                    {"code": "is_loi_nhuan_gop", "name": "Lợi nhuận gộp", "statement": "income_statement"},
                    {"code": "is_loi_nhuan_sau_thue", "name": "Lợi nhuận sau thuế", "statement": "income_statement"},
                    {"code": "is_tong_loi_nhuan_ke_toan_truoc_thue", "name": "Lợi nhuận trước thuế (LNTT)", "statement": "income_statement"},
                    {"code": "is_chi_phi_ban_hang", "name": "Chi phí bán hàng", "statement": "income_statement"},
                    {"code": "is_chi_phi_quan_ly_doanh_nghiep", "name": "Chi phí QLDN", "statement": "income_statement"},
                    {"code": "cf_luu_chuyen_tien_thuan_tu_hoat_dong_kinh_doanh", "name": "Lưu chuyển tiền thuần từ HĐKD", "statement": "cash_flow"},
                ],
                "ratios": ["roa", "roe", "gross_margin", "net_margin", "current_ratio", "debt_to_equity", "debt_to_assets", "size_ln"],
            },
            {
                "id": "banking",
                "name": "Ngân hàng (CAMELS)",
                "description": "Chỉ tiêu & chỉ số đặc thù ngành ngân hàng",
                "items": [
                    {"code": "bs_tong_tai_san", "name": "Tổng tài sản", "statement": "balance_sheet"},
                    {"code": "bs_von_chu_so_huu", "name": "Vốn chủ sở hữu", "statement": "balance_sheet"},
                    {"code": "bs_cho_vay_khach_hang", "name": "Cho vay khách hàng", "statement": "balance_sheet"},
                    {"code": "bs_tien_gui_cua_khach_hang", "name": "Tiền gửi khách hàng", "statement": "balance_sheet"},
                    {"code": "is_thu_nhap_lai_thuan", "name": "Thu nhập lãi thuần", "statement": "income_statement"},
                    {"code": "is_loi_nhuan_sau_thue", "name": "Lợi nhuận sau thuế", "statement": "income_statement"},
                    {"code": "bs_du_phong_rui_ro_cho_vay_khach_hang", "name": "Dự phòng rủi ro cho vay khách hàng", "statement": "balance_sheet"},
                ],
                "ratios": ["roa", "roe", "bank_nim", "bank_cir", "bank_ldr", "bank_provision_coverage", "bank_loans_to_assets", "bank_deposits_to_assets", "bank_equity_to_assets", "size_ln"],
            },
            {
                "id": "securities",
                "name": "Công ty Chứng khoán",
                "description": "Chỉ tiêu & chỉ số đặc thù CTCK (Margin, FVTPL, AFS, Môi giới)",
                "items": [
                    {"code": "bs_tong_tai_san", "name": "Tổng tài sản", "statement": "balance_sheet"},
                    {"code": "bs_von_chu_so_huu", "name": "Vốn chủ sở hữu", "statement": "balance_sheet"},
                    {"code": "sec_cho_vay_margin", "name": "Cho vay ký quỹ (Margin)", "statement": "balance_sheet"},
                    {"code": "sec_tai_san_tai_chinh_fvtpl", "name": "Tài sản tài chính FVTPL", "statement": "balance_sheet"},
                    {"code": "sec_tai_san_tai_chinh_afs", "name": "Tài sản tài chính AFS", "statement": "balance_sheet"},
                    {"code": "sec_doanh_thu_moi_gioi", "name": "Doanh thu môi giới", "statement": "income_statement"},
                    {"code": "sec_lai_tu_cac_tai_san_tai_chinh_fvtpl", "name": "Lãi tự doanh FVTPL", "statement": "income_statement"},
                    {"code": "is_loi_nhuan_sau_thue", "name": "Lợi nhuận sau thuế", "statement": "income_statement"},
                ],
                "ratios": ["roa", "roe", "margin_to_equity", "pct_margin_loans", "pct_fvtpl", "pct_afs", "pct_brokerage_rev", "pct_proprietary_rev", "size_ln"],
            },
            {
                "id": "profitability",
                "name": "Khả năng sinh lời & Hiệu quả vốn",
                "description": "Các chỉ tiêu và tỷ số sinh lời chuyên sâu (ROA, ROE, ROCE, ROIC, Biên LN)",
                "items": [
                    {"code": "bs_tong_tai_san", "name": "Tổng tài sản", "statement": "balance_sheet"},
                    {"code": "bs_von_chu_so_huu", "name": "Vốn chủ sở hữu", "statement": "balance_sheet"},
                    {"code": "is_doanh_thu_thuan", "name": "Doanh thu thuần", "statement": "income_statement"},
                    {"code": "is_loi_nhuan_gop", "name": "Lợi nhuận gộp", "statement": "income_statement"},
                    {"code": "is_loi_nhuan_sau_thue", "name": "Lợi nhuận sau thuế", "statement": "income_statement"},
                    {"code": "is_tong_loi_nhuan_ke_toan_truoc_thue", "name": "Lợi nhuận trước thuế (LNTT)", "statement": "income_statement"},
                    {"code": "is_ebit", "name": "EBIT", "statement": "income_statement"},
                    {"code": "is_ebitda", "name": "EBITDA", "statement": "income_statement"},
                    {"code": "is_gia_von_hang_ban", "name": "Giá vốn hàng bán", "statement": "income_statement"},
                ],
                "ratios": ["roa", "roe", "roce", "roic", "gross_margin", "operating_margin", "ebitda_margin", "net_margin", "ebt_margin"],
            },
            {
                "id": "solvency",
                "name": "Cấu trúc vốn & Thanh toán",
                "description": "Nợ, vốn, khả năng thanh toán và đòn bẩy tài chính",
                "items": [
                    {"code": "bs_tong_tai_san", "name": "Tổng tài sản", "statement": "balance_sheet"},
                    {"code": "bs_von_chu_so_huu", "name": "Vốn chủ sở hữu", "statement": "balance_sheet"},
                    {"code": "bs_no_phai_tra", "name": "Nợ phải trả", "statement": "balance_sheet"},
                    {"code": "bs_tai_san_ngan_han", "name": "Tài sản ngắn hạn", "statement": "balance_sheet"},
                    {"code": "bs_no_ngan_han", "name": "Nợ ngắn hạn", "statement": "balance_sheet"},
                    {"code": "bs_no_dai_han", "name": "Nợ dài hạn", "statement": "balance_sheet"},
                    {"code": "bs_vay_va_no_ngan_han", "name": "Vay và nợ ngắn hạn", "statement": "balance_sheet"},
                    {"code": "bs_vay_va_no_dai_han", "name": "Vay và nợ dài hạn", "statement": "balance_sheet"},
                    {"code": "bs_hang_ton_kho", "name": "Hàng tồn kho", "statement": "balance_sheet"},
                ],
                "ratios": ["debt_to_assets", "debt_to_equity", "current_ratio", "quick_ratio", "cash_ratio", "equity_multiplier", "interest_coverage"],
            },
        ]
    }


# Full ratio definitions for server-side computation
RATIO_DEFS = {
    "roa": {
        "name": "ROA",
        "group": "profitability",
        "formula_desc": "LNST / Tổng tài sản",
        "requires": ["is_loi_nhuan_sau_thue", "bs_tong_tai_san"],
    },
    "roe": {
        "name": "ROE",
        "group": "profitability",
        "formula_desc": "LNST / Vốn chủ sở hữu",
        "requires": ["is_loi_nhuan_sau_thue", "bs_von_chu_so_huu"],
    },
    "size": {
        "name": "Size (ln)",
        "group": "scale",
        "formula_desc": "ln(Tổng tài sản)",
        "requires": ["bs_tong_tai_san"],
    },
    "leverage": {
        "name": "Leverage",
        "group": "solvency",
        "formula_desc": "Nợ phải trả / Tổng tài sản",
        "requires": ["bs_no_phai_tra", "bs_tong_tai_san"],
    },
    "gross_margin": {
        "name": "Gross Margin",
        "group": "profitability",
        "formula_desc": "Lợi nhuận gộp / Doanh thu thuần",
        "requires": ["is_loi_nhuan_gop", "is_doanh_thu_thuan"],
    },
    "net_margin": {
        "name": "Net Margin",
        "group": "profitability",
        "formula_desc": "LNST / Doanh thu thuần",
        "requires": ["is_loi_nhuan_sau_thue", "is_doanh_thu_thuan"],
    },
    "ebit_margin": {
        "name": "EBIT Margin",
        "group": "profitability",
        "formula_desc": "EBIT / Doanh thu thuần",
        "requires": ["is_ebit", "is_doanh_thu_thuan"],
    },
    "current_ratio": {
        "name": "Current Ratio",
        "group": "solvency",
        "formula_desc": "Tài sản ngắn hạn / Nợ ngắn hạn",
        "requires": ["bs_tai_san_ngan_han", "bs_no_ngan_han"],
    },
    "quick_ratio": {
        "name": "Quick Ratio",
        "group": "solvency",
        "formula_desc": "(TSNH - Hàng tồn kho) / Nợ ngắn hạn",
        "requires": ["bs_tai_san_ngan_han", "bs_hang_ton_kho", "bs_no_ngan_han"],
    },
    "debt_to_equity": {
        "name": "Debt / Equity",
        "group": "solvency",
        "formula_desc": "Nợ phải trả / Vốn chủ sở hữu",
        "requires": ["bs_no_phai_tra", "bs_von_chu_so_huu"],
    },
    "equity_multiplier": {
        "name": "Equity Multiplier",
        "group": "solvency",
        "formula_desc": "Tổng tài sản / Vốn chủ sở hữu",
        "requires": ["bs_tong_tai_san", "bs_von_chu_so_huu"],
    },
    "asset_turnover": {
        "name": "Asset Turnover",
        "group": "efficiency",
        "formula_desc": "Doanh thu thuần / Tổng tài sản",
        "requires": ["is_doanh_thu_thuan", "bs_tong_tai_san"],
    },
}


@app.get("/api/financial/ratios")
def financial_ratios():
    """Return all available ratio definitions (academic standard: CFA, VAS/IFRS, Basel III, CAMELS)."""
    from arminer.export.financial_excel import FINANCIAL_RATIOS
    return {"ratios": FINANCIAL_RATIOS}


class FinancialQueryRequest(BaseModel):
    tickers: List[str]
    start_year: int = 2014
    end_year: int = 2024
    item_codes: List[str] = []
    ratios: Optional[List[str]] = None
    exchange: Optional[str] = None
    drop_empty: bool = True  # Tự động loại bỏ các chỉ tiêu 100% rỗng để tránh làm đầy Excel


@app.post("/api/financial/query")
async def financial_query(req: FinancialQueryRequest):
    """Query financial data with SSE streaming progress."""
    if not _check_vnf():
        raise HTTPException(status_code=400, detail="vnfinancialdata chua duoc cai dat.")

    import vnfinancialdata as vnf
    import math

    async def event_generator():
        total_ops = len(req.tickers)
        exchanges = [req.exchange] if req.exchange else ["HSX", "HNX"]

        # Determine which statements we need
        has_ratios = bool(req.ratios is None or len(req.ratios) > 0)
        is_all_items = not req.item_codes or "all" in req.item_codes
        if is_all_items or has_ratios:
            needed_statements = {"balance_sheet", "income_statement", "cash_flow"}
        else:
            needed_statements = set()
            for ic in req.item_codes:
                if ic.startswith("bs_"): needed_statements.add("balance_sheet")
                elif ic.startswith("is_"): needed_statements.add("income_statement")
                elif ic.startswith("cf_"): needed_statements.add("cash_flow")
            if not needed_statements:
                needed_statements = {"balance_sheet", "income_statement", "cash_flow"}

        # Collect all item_codes we need
        all_item_codes = list(req.item_codes)

        yield {"event": "progress", "data": json.dumps(
            {"phase": "loading", "current": 0, "total": total_ops,
             "message": f"Dang tai du lieu tu HuggingFace..."},
            ensure_ascii=False)}

        # Load raw data for each needed statement+exchange combo
        # NOTE: When ratios are requested, we do NOT restrict item_code in vnf.load
        # because different sectors use different accounts (e.g. is_lai_lo_thuan_sau_thue vs is_loi_nhuan_sau_thue).
        # Strict filtering to user-selected items is done when assembling the final pivot table.
        raw_data = {}
        for stmt in needed_statements:
            for exch in exchanges:
                try:
                    item_code_arg = None if (is_all_items or has_ratios) else [c for c in all_item_codes if c.startswith({"balance_sheet": "bs_", "income_statement": "is_", "cash_flow": "cf_"}[stmt])]
                    if not item_code_arg:
                        item_code_arg = None

                    df = vnf.load(
                        exchange=exch,
                        statement=stmt,
                        ticker=req.tickers,
                        start_year=req.start_year,
                        end_year=req.end_year,
                        item_code=item_code_arg,
                    )
                    key = f"{exch}_{stmt}"
                    raw_data[key] = df
                    yield {"event": "progress", "data": json.dumps(
                        {"phase": "loading", "current": 0, "total": total_ops,
                         "message": f"Da tai {exch}/{stmt}: {len(df)} dong"},
                        ensure_ascii=False)}
                except Exception as e:
                    logger.warning(f"Loi tai {exch}/{stmt}: {e}")
                await asyncio.sleep(0)

        # Combine all raw data
        if not raw_data:
            yield {"event": "error", "data": json.dumps(
                {"detail": "Khong tai duoc du lieu. Kiem tra tickers va nam."},
                ensure_ascii=False)}
            return

        all_data = pd.concat(raw_data.values(), ignore_index=True)

        # Build item_name lookup from the raw data
        item_name_lookup = {}
        if "item_code" in all_data.columns and "item_name" in all_data.columns:
            for _, row in all_data[["item_code", "item_name"]].drop_duplicates().iterrows():
                item_name_lookup[row["item_code"]] = row["item_name"]

        # Pivot: each row = (ticker, year), columns = item_codes
        yield {"event": "progress", "data": json.dumps(
            {"phase": "processing", "current": 0, "total": total_ops,
             "message": "Dang xu ly pivot table..."},
            ensure_ascii=False)}

        if all_data.empty:
            yield {"event": "error", "data": json.dumps(
                {"detail": f"Không tìm thấy số liệu BCTC cho mã: {', '.join(req.tickers)}. Bộ dữ liệu vnfinancialdata hiện hỗ trợ 692 mã trên HSX/HNX nhưng bị khuyết mã SSI từ nguồn cào gốc. Nếu bạn nghiên cứu nhóm Công ty Chứng khoán (CTCK), vui lòng chọn các mã có đầy đủ 100% dữ liệu như: VND, VCI, HCM, SHS, VIX, MBS, FTS, BSI, CTS, AGR, VDS... Hoặc nhóm Bluechips: VCB, VNM, HPG, FPT, TCB, MBB..."},
                ensure_ascii=False)}
            return

        found_tickers = set(all_data["ticker"].str.upper().unique()) if not all_data.empty else set()
        missing_tickers = [t for t in req.tickers if t.upper() not in found_tickers]
        if missing_tickers:
            logger.warning(f"Các mã sau không có trong vnfinancialdata: {missing_tickers}")
            yield {"event": "warning", "data": json.dumps({
                "warning": True,
                "missing_tickers": missing_tickers,
                "message": f"⚠️ Các mã {missing_tickers} không có trong cơ sở dữ liệu vnfinancialdata và đã được tự động loại bỏ khỏi kết quả.",
            }, ensure_ascii=False)}

        pivot = all_data.pivot_table(
            index=["ticker", "year"],
            columns="item_code",
            values="value",
            aggfunc="first",
        ).reset_index()
        pivot.columns.name = None

        # Compute academic financial ratios (116 ratios - 10 pillars)
        from arminer.export.financial_excel import compute_financial_ratios, FINANCIAL_RATIOS, classify_financial_item
        pivot = compute_financial_ratios(pivot)

        # Lay toan bo danh muc goc 702 chi tieu tu vnfinancialdata
        df_master_items = vnf.list_items(active_only=False)
        item_name_lookup = dict(zip(df_master_items["item_code"], df_master_items["item_name"]))

        # Xac dinh danh sach chi tieu can xuat
        if is_all_items:
            target_item_codes = list(df_master_items["item_code"])
        else:
            target_item_codes = [c for c in req.item_codes if not c.startswith("ratio_")]
            if not target_item_codes:
                target_item_codes = list(df_master_items["item_code"])

        # Xac dinh danh sach ty so can xuat
        if req.ratios is not None:
            active_ratios = [r for r in req.ratios if r in FINANCIAL_RATIOS]
        else:
            active_ratios = ["roa", "roe", "gross_margin", "net_margin", "debt_to_assets", "debt_to_equity", "current_ratio", "size_ln"]

        if req.drop_empty:
            # Che do thong minh: Chi giu cac chi tieu thuc su co so lieu trong pivot (loai bo cot toan bo NaN hoac 0)
            target_item_codes = [c for c in target_item_codes if c in pivot.columns]
            cols_to_drop = []
            for col in target_item_codes:
                col_data = pivot[col].dropna()
                if col_data.empty or (col_data == 0).all():
                    cols_to_drop.append(col)
            if cols_to_drop:
                pivot = pivot.drop(columns=cols_to_drop)
                target_item_codes = [c for c in target_item_codes if c not in cols_to_drop]

            # Chi so tai chinh phan tich: chi giu ratios co it nhat 1 gia tri khac NaN
            active_ratios = [r for r in active_ratios if r in pivot.columns and not pivot[r].dropna().empty]
        else:
            # Che do day du: dam bao toan bo chi tieu muc tieu co cot tren pivot (neu DN khong co thi gia tri la None)
            missing_cols = {}
            for icode in target_item_codes:
                if icode not in pivot.columns:
                    missing_cols[icode] = [None] * len(pivot)
            for rk in active_ratios:
                if rk not in pivot.columns:
                    missing_cols[rk] = [None] * len(pivot)
            if missing_cols:
                df_missing = pd.DataFrame(missing_cols, index=pivot.index)
                pivot = pd.concat([pivot, df_missing], axis=1)

        ratio_cols = {rk: rinfo["name"] for rk, rinfo in FINANCIAL_RATIOS.items() if rk in active_ratios}

        # Replace inf with None
        pivot = pivot.replace([float('inf'), float('-inf')], None)

        # Sap xep thu tu cot khoa hoc: ticker, year, toan bo chi tieu BCTC da chon, toan bo chi so tai chinh da chon
        # TUYET DOI KHONG giu lai cac chi so khong duoc chon trong file xuat!
        ordered_cols = ["ticker", "year"] + [c for c in target_item_codes if c in pivot.columns] + [r for r in active_ratios if r in pivot.columns]
        other_cols = [c for c in pivot.columns if c not in ordered_cols and c not in FINANCIAL_RATIOS]
        pivot = pivot[ordered_cols + other_cols]

        # Sort theo ticker va year
        pivot = pivot.sort_values(["ticker", "year"]).reset_index(drop=True)

        # Save to download dir
        export_path = DOWNLOAD_DIR / "financial_data.csv"
        pivot.to_csv(export_path, index=False, encoding="utf-8-sig")

        # Build column info for frontend (include item_name)
        col_info = []
        fin_codebook = []
        for col in pivot.columns:
            if col in ("ticker", "year"):
                continue
            is_ratio = col in FINANCIAL_RATIOS
            if is_ratio:
                rinfo = FINANCIAL_RATIOS[col]
                c_name = rinfo["name"]
                stmt = rinfo["group"]
                ptype = "Chỉ số tài chính phân tích"
                formula = rinfo["formula"]
            else:
                c_name = item_name_lookup.get(col, col)
                stmt = classify_financial_item(col, c_name, "balance_sheet" if col.startswith("bs_") else "income_statement" if col.startswith("is_") else "cash_flow")
                ptype = "Chỉ tiêu kế toán"
                formula = "vnfinancialdata"

            col_info.append({
                "code": col,
                "name": c_name,
                "is_ratio": is_ratio,
            })
            fin_codebook.append({
                "Biến": col,
                "Tên chỉ tiêu": c_name,
                "Phân loại / Nhóm": stmt,
                "Phân loại": ptype,
                "Công thức / Nguồn": formula,
            })

        # Save Excel with professional INDEX/MATCH dynamic formulas
        export_xlsx = DOWNLOAD_DIR / "financial_data.xlsx"
        try:
            from arminer.export.financial_excel import export_financial_workbook
            export_financial_workbook(
                all_data=all_data,
                pivot=pivot,
                ratio_cols=ratio_cols,
                fin_codebook=fin_codebook,
                export_xlsx=export_xlsx,
                missing_tickers=missing_tickers,
            )
        except Exception as e:
            logger.warning(f"Lỗi xuất file Excel nâng cao: {e}, fallback sang cơ bản")
            with pd.ExcelWriter(export_xlsx, engine="openpyxl") as writer:
                pivot.to_excel(writer, sheet_name="Financial_Data", index=False)
                if fin_codebook:
                    pd.DataFrame(fin_codebook).to_excel(writer, sheet_name="Codebook", index=False)
            try:
                from arminer.export.excel_style import style_excel_file
                style_excel_file(export_xlsx)
            except Exception:
                pass

        # Save Stata .dta
        export_dta = DOWNLOAD_DIR / "financial_data.dta"
        try:
            from arminer.core.smart_mode import sanitize_stata_dataframe
            stata_df, labels = sanitize_stata_dataframe(pivot)
            stata_df.to_stata(export_dta, write_index=False, version=118, variable_labels=labels)
        except Exception as e:
            logger.warning(f"Financial Stata export failed: {e}")

        # Prepare data for response (convert to serializable format)
        preview_df = pivot.head(100)
        records = []
        for _, row in preview_df.iterrows():
            record = {}
            for col in pivot.columns:
                val = row[col]
                if pd.isna(val):
                    record[col] = None
                elif isinstance(val, (int, float)):
                    record[col] = float(val)
                else:
                    record[col] = str(val)
            records.append(record)

        yield {"event": "complete", "data": json.dumps({
            "total_rows": len(pivot),
            "total_tickers": pivot["ticker"].nunique(),
            "year_range": [int(pivot["year"].min()), int(pivot["year"].max())],
            "missing_tickers": missing_tickers,
            "columns": col_info,
            "preview": records,
            "csv_download": "/api/download/financial_data.csv",
            "xlsx_download": "/api/download/financial_data.xlsx",
            "dta_download": "/api/download/financial_data.dta",
        }, ensure_ascii=False, default=str)}

    return EventSourceResponse(event_generator())



class FinancialMergeRequest(BaseModel):
    mining_source: str = "latest"  # "latest" or file path


@app.post("/api/financial/merge")
def financial_merge(req: FinancialMergeRequest):
    """Merge financial_data.csv with mining panel_data.csv."""
    fin_path = DOWNLOAD_DIR / "financial_data.csv"
    mining_path = DOWNLOAD_DIR / "panel_data.csv"

    if not fin_path.exists():
        raise HTTPException(status_code=400, detail="Chưa có dữ liệu tài chính. Hãy tải dữ liệu trước.")
    if not mining_path.exists():
        # Try xlsx
        mining_xlsx = DOWNLOAD_DIR / "panel_data.xlsx"
        if mining_xlsx.exists():
            df_mining = pd.read_excel(mining_xlsx)
        else:
            raise HTTPException(status_code=400, detail="Chưa có kết quả mining. Hãy khai phá báo cáo trước.")
    else:
        df_mining = pd.read_csv(mining_path)

    df_fin = pd.read_csv(fin_path)

    # Normalize types for merge
    df_mining["ticker"] = df_mining["ticker"].astype(str).str.strip().str.upper()
    df_fin["ticker"] = df_fin["ticker"].astype(str).str.strip().str.upper()
    df_mining["year"] = pd.to_numeric(df_mining["year"], errors="coerce")
    df_fin["year"] = pd.to_numeric(df_fin["year"], errors="coerce")

    merged = pd.merge(df_mining, df_fin, on=["ticker", "year"], how="left", suffixes=("", "_fin"))

    # Save Excel with premium styling
    out_path = DOWNLOAD_DIR / "merged_panel_data.xlsx"
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        merged.to_excel(writer, sheet_name="Merged_Panel", index=False)
    try:
        from arminer.export.excel_style import style_excel_file
        style_excel_file(out_path)
    except Exception:
        pass

    out_csv = DOWNLOAD_DIR / "merged_panel_data.csv"
    merged.to_csv(out_csv, index=False, encoding="utf-8-sig")

    # Save Stata .dta
    out_dta = DOWNLOAD_DIR / "merged_panel_data.dta"
    try:
        from arminer.core.smart_mode import sanitize_stata_dataframe
        stata_df, labels = sanitize_stata_dataframe(merged)
        stata_df.to_stata(out_dta, write_index=False, version=118, variable_labels=labels)
    except Exception as e:
        logger.warning(f"Merged Stata export failed: {e}")

    # Stats
    fin_cols = [c for c in df_fin.columns if c not in ("ticker", "year")]
    coverage = {}
    for c in fin_cols:
        if c in merged.columns:
            n = merged[c].notna().sum()
            coverage[c] = {"count": int(n), "pct": round(n / len(merged) * 100, 1)}

    return {
        "total_rows": len(merged),
        "mining_rows": len(df_mining),
        "financial_rows": len(df_fin),
        "coverage": coverage,
        "preview": merged.head(30).to_dict(orient="records"),
        "xlsx_download": "/api/download/merged_panel_data.xlsx",
        "csv_download": "/api/download/merged_panel_data.csv",
        "dta_download": "/api/download/merged_panel_data.dta",
    }


@app.get("/api/download/{filename}")
def download_file(filename: str):
    """Tải file kết quả nghiên cứu đã tạo."""
    file_path = DOWNLOAD_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File không tồn tại.")
    return FileResponse(
        file_path,
        filename=filename,
        media_type="application/octet-stream",
    )


# =====================================================================
# News Mining & Multi-Source Crawler Endpoints
# =====================================================================

class CompanyWebsiteUpdateRequest(BaseModel):
    ticker: str
    website: Optional[str] = None
    ir_portal: Optional[str] = None


class NewsScrapeRequest(BaseModel):
    tickers: List[str]
    sources: List[str] = [
        "company_website", "cafef", "vnexpress", "cafebiz",
        "tinnhanhchungkhoan", "vneconomy", "vietnamnet"
    ]
    target_articles_per_ticker: int = 20
    year_from: Optional[int] = 2020
    year_to: Optional[int] = 2026
    custom_urls: Optional[List[str]] = None


class NewsMineRequest(BaseModel):
    tickers: List[str]
    sources: List[str] = [
        "company_website", "cafef", "vnexpress", "cafebiz",
        "tinnhanhchungkhoan", "vneconomy", "vietnamnet"
    ]
    target_articles_per_ticker: int = 20
    year_from: Optional[int] = 2020
    year_to: Optional[int] = 2026
    custom_urls: Optional[List[str]] = None
    topic: Optional[str] = "blockchain"
    keywords: Optional[str] = None
    threshold: int = 85


class NewsPasteMineRequest(BaseModel):
    ticker: str = "CUSTOM"
    text: str
    title: Optional[str] = "Văn bản nhập thủ công"
    topic: Optional[str] = "blockchain"
    keywords: Optional[str] = None
    threshold: int = 85


@app.get("/api/news/sources")
def get_news_sources():
    """Danh sách các nguồn tin tức tài chính được hỗ trợ."""
    return {
        "sources": [
            {
                "id": "company_website",
                "name": "Website chính thức công ty",
                "badge": "Chính thống",
                "desc": "Cào tự động mục tin tức, quan hệ cổ đông (IR) trên website DN (~1,430+ mã)",
                "default": True,
            },
            {
                "id": "cafef",
                "name": "CafeF",
                "badge": "Tốc độ cao",
                "desc": "Trang tin tức & dữ liệu tài chính - chứng khoán hàng đầu Việt Nam",
                "default": True,
            },
            {
                "id": "vnexpress",
                "name": "VnExpress Kinh Doanh",
                "badge": "Báo lớn",
                "desc": "Báo điện tử nhiều người đọc nhất Việt Nam, chuyên mục kinh doanh & thị trường",
                "default": True,
            },
            {
                "id": "cafebiz",
                "name": "CafeBiz",
                "badge": "Kinh tế DN",
                "desc": "Thông tin chuyên sâu về kinh doanh, doanh nghiệp và tài chính đầu tư",
                "default": True,
            },
            {
                "id": "tinnhanhchungkhoan",
                "name": "Tin Nhanh Chứng Khoán (ĐTCK)",
                "badge": "UBCKNN",
                "desc": "Báo Đầu tư Chứng khoán - cơ quan ngôn luận của Ủy ban Chứng khoán Nhà nước",
                "default": True,
            },
            {
                "id": "vneconomy",
                "name": "VnEconomy",
                "badge": "Kinh tế",
                "desc": "Tạp chí Kinh tế Việt Nam - phân tích vĩ mô & thông tin doanh nghiệp",
                "default": True,
            },
            {
                "id": "vietnamnet",
                "name": "VietnamNet Kinh Doanh",
                "badge": "Chính luận",
                "desc": "Báo VietnamNet - chuyên trang tin tức kinh doanh và doanh nghiệp niêm yết",
                "default": True,
            },
            {
                "id": "custom",
                "name": "URL Tùy chỉnh",
                "badge": "Linh hoạt",
                "desc": "Dán danh sách các đường link bài viết cụ thể để thu thập",
                "default": False,
            },
        ]
    }


@app.get("/api/news/companies")
def get_news_companies(
    query: Optional[str] = Query(None),
    exchange: Optional[str] = Query(None),
    has_website_only: bool = Query(False),
    limit: int = Query(100),
):
    """Tra cứu danh bạ website doanh nghiệp niêm yết."""
    companies = news_resolver.list_companies(
        query=query,
        exchange=exchange,
        has_website_only=has_website_only,
        limit=limit,
    )
    total_in_db = len(news_resolver._db)
    with_website_count = sum(1 for v in news_resolver._db.values() if v.get("website"))
    return {
        "total_in_db": total_in_db,
        "with_website_count": with_website_count,
        "companies": companies,
    }


@app.post("/api/news/companies/update")
def update_news_company(req: CompanyWebsiteUpdateRequest):
    """Cập nhật hoặc thêm thủ công URL website cho mã chứng khoán."""
    news_resolver.update_company(req.ticker, website=req.website, ir_portal=req.ir_portal)
    return {"success": True, "company": news_resolver.get_company(req.ticker)}


@app.post("/api/news/scrape-stream")
async def scrape_news_stream(req: NewsScrapeRequest):
    """Cào tin tức đa nguồn có streaming tiến độ và tự động bù đắp thiếu hụt."""
    async def event_generator():
        all_articles = []
        total_tickers = len(req.tickers)

        for i, ticker in enumerate(req.tickers):
            t = ticker.upper().strip()
            yield {"event": "progress", "data": json.dumps({
                "phase": "crawl",
                "current_ticker_idx": i + 1,
                "total_tickers": total_tickers,
                "ticker": t,
                "message": f"Đang cào tin tức [{i + 1}/{total_tickers}]: {t} (năm {req.year_from or ''}-{req.year_to or ''})...",
            }, ensure_ascii=False)}
            await asyncio.sleep(0)

            loop = asyncio.get_event_loop()
            articles = await loop.run_in_executor(
                None,
                lambda: news_aggregator.crawl_ticker(
                    ticker=t,
                    sources=req.sources,
                    target_articles=req.target_articles_per_ticker,
                    year_from=req.year_from,
                    year_to=req.year_to,
                    custom_urls=req.custom_urls,
                )
            )
            all_articles.extend(articles)

            yield {"event": "progress", "data": json.dumps({
                "phase": "crawl",
                "current_ticker_idx": i + 1,
                "total_tickers": total_tickers,
                "ticker": t,
                "articles_found": len(articles),
                "message": f"Hoàn tất {t}: đã thu thập {len(articles)} bài viết.",
            }, ensure_ascii=False)}
            await asyncio.sleep(0)

        preview = [{
            "ticker": a.get("ticker"),
            "year": a.get("published_year") or "",
            "news_source": a.get("news_source"),
            "title": a.get("title"),
            "published_date": a.get("published_date"),
            "url": a.get("url"),
            "word_count": a.get("word_count"),
            "snippet": (a.get("text") or "")[:150] + "...",
        } for a in all_articles]

        yield {"event": "complete", "data": json.dumps({
            "total_articles": len(all_articles),
            "articles": preview,
        }, ensure_ascii=False)}

    return EventSourceResponse(event_generator())


@app.post("/api/news/mine-stream")
async def mine_news_stream(req: NewsMineRequest):
    """Crawl tin tức + khai phá từ điển nghiên cứu trong một luồng streaming duy nhất."""
    async def event_generator():
        all_articles: List[Dict[str, Any]] = []
        total_tickers = len(req.tickers)

        for i, ticker in enumerate(req.tickers):
            t = ticker.upper().strip()
            yield {"event": "progress", "data": json.dumps({
                "phase": "crawl",
                "current": i + 1,
                "total": total_tickers,
                "ticker": t,
                "message": f"[{i + 1}/{total_tickers}] Đang thu thập tin tức: {t} từ {len(req.sources)} nguồn (năm {req.year_from or ''}-{req.year_to or ''})...",
            }, ensure_ascii=False)}
            await asyncio.sleep(0)

            loop = asyncio.get_event_loop()
            articles = await loop.run_in_executor(
                None,
                lambda: news_aggregator.crawl_ticker(
                    ticker=t,
                    sources=req.sources,
                    target_articles=req.target_articles_per_ticker,
                    year_from=req.year_from,
                    year_to=req.year_to,
                    custom_urls=req.custom_urls,
                )
            )
            all_articles.extend(articles)

        if not all_articles:
            yield {"event": "error", "data": json.dumps({
                "detail": "Không thu thập được bài viết nào phù hợp bộ lọc từ các nguồn đã chọn. Hãy thử nới rộng khoảng năm hoặc chọn thêm nguồn báo."
            }, ensure_ascii=False)}
            return

        yield {"event": "progress", "data": json.dumps({
            "phase": "mining",
            "current": 0,
            "total": len(all_articles),
            "message": f"Bắt đầu khai phá văn bản trên {len(all_articles)} bài báo...",
        }, ensure_ascii=False)}
        await asyncio.sleep(0)

        flex_dict = _resolve_dictionary(topic=req.topic, keywords=req.keywords)
        core_dict = flex_dict.to_core_dictionary()
        matcher = GenericFuzzyMatcher(dictionary=core_dict, threshold=req.threshold)
        calc = SmartVariableCalculator()

        article_rows = []
        all_snippets = []
        all_raw_keywords = []

        for idx, art in enumerate(all_articles):
            text = art.get("text") or ""
            words = text.split()
            total_words = len(words)
            text_len = len(text)

            matches = matcher.search(text, use_fuzzy=True) if total_words > 0 else []

            vars_r = calc.calculate_all(
                matches, total_words,
                category_names=flex_dict.categories,
                topic_prefix=req.topic or "news",
                total_dict_keywords=len(flex_dict.entries),
                classification_rules=flex_dict.classification_rules,
            )

            row = {
                "ticker": art["ticker"],
                "year": art.get("published_year") or "",
                "news_source": art.get("news_source", ""),
                "title": art.get("title", ""),
                "published_date": art.get("published_date", ""),
                "url": art.get("url", ""),
                "word_count": total_words,
                **vars_r,
            }
            article_rows.append(row)

            kw_counts = {}
            for m in matches:
                kw = m.get("keyword_canonical", m.get("keyword_found", ""))
                cat = m.get("category", "default")
                kw_counts[(kw, cat)] = kw_counts.get((kw, cat), 0) + 1

            for (kw, cat), cnt in kw_counts.items():
                all_raw_keywords.append({
                    "ticker": art["ticker"],
                    "title": art.get("title", "")[:60],
                    "keyword": kw,
                    "category": cat,
                    "frequency": cnt,
                })

            for m in matches[:3]:
                pos = m.get("position", 0)
                kw = m.get("keyword_found", "")
                snippet = text[max(0, pos - 70):min(text_len, pos + len(kw) + 70)].replace("\n", " ").strip()
                all_snippets.append({
                    "ticker": art["ticker"],
                    "source": art.get("news_source", ""),
                    "title": art.get("title", ""),
                    "url": art.get("url", ""),
                    "keyword": kw,
                    "category": m.get("category", "default"),
                    "context": snippet,
                })

            if (idx + 1) % 5 == 0 or idx == len(all_articles) - 1:
                yield {"event": "progress", "data": json.dumps({
                    "phase": "mining",
                    "current": idx + 1,
                    "total": len(all_articles),
                    "message": f"Đang khai phá {idx + 1}/{len(all_articles)}: {art.get('title', '')[:35]}...",
                }, ensure_ascii=False)}
                await asyncio.sleep(0)

        df_articles = pd.DataFrame(article_rows)

        # Ensure year is integer
        df_articles["year"] = pd.to_numeric(df_articles["year"], errors="coerce")
        df_articles["year"] = df_articles["year"].fillna(req.year_to or 2026).astype(int)

        freq_col = next((c for c in df_articles.columns if "frequency" in c.lower() and "log" not in c.lower()), None)
        dummy_col = next((c for c in df_articles.columns if "dummy" in c.lower() or "mention" in c.lower()), None)

        # Category frequency columns
        cat_cols = [c for c in df_articles.columns if "_freq" in c.lower() and c != freq_col]

        # Aggregate strictly by (ticker, year) — standard Firm-Year Panel Data matching other tabs
        firm_year_summary = []
        for (ticker, yr), grp in df_articles.groupby(["ticker", "year"]):
            tot_art = len(grp)
            tot_words = int(grp["word_count"].sum())
            tot_hits = int(grp[freq_col].sum()) if freq_col and freq_col in grp else 0
            art_with_hits = int((grp[dummy_col] > 0).sum()) if dummy_col and dummy_col in grp else 0
            hit_ratio = round(art_with_hits / tot_art * 100, 2) if tot_art > 0 else 0.0
            density = round(tot_hits / tot_words * 1000, 4) if tot_words > 0 else 0.0
            log_freq = round(math.log1p(tot_hits), 4)

            row_data = {
                "ticker": ticker,
                "year": int(yr),
                "total_articles": tot_art,
                "articles_with_hits": art_with_hits,
                "article_hit_ratio_pct": hit_ratio,
                "total_mentions": tot_hits,
                "log_frequency": log_freq,
                "mention": 1 if tot_hits > 0 else 0,
                "total_words": tot_words,
                "keyword_density_per_1k": density,
            }
            for cc in cat_cols:
                row_data[cc] = int(grp[cc].sum())

            firm_year_summary.append(row_data)

        df_firm_year = pd.DataFrame(firm_year_summary)
        if not df_firm_year.empty:
            df_firm_year = df_firm_year.sort_values(by=["ticker", "year"]).reset_index(drop=True)

        raw_df = pd.DataFrame(all_raw_keywords) if all_raw_keywords else pd.DataFrame()

        out_xlsx = DOWNLOAD_DIR / "news_panel_data.xlsx"
        try:
            with pd.ExcelWriter(out_xlsx, engine="openpyxl") as writer:
                df_firm_year.to_excel(writer, sheet_name="Firm_Year_Panel", index=False)
                df_articles.to_excel(writer, sheet_name="Articles_Detail", index=False)
                if not raw_df.empty:
                    raw_df.to_excel(writer, sheet_name="Raw_Keywords", index=False)
            from arminer.export.excel_style import style_excel_file
            style_excel_file(out_xlsx)
        except Exception as e:
            logger.error(f"Failed writing news_panel_data.xlsx: {e}")

        out_csv = DOWNLOAD_DIR / "news_panel_data.csv"
        df_firm_year.to_csv(out_csv, index=False, encoding="utf-8-sig")

        out_dta = DOWNLOAD_DIR / "news_panel_data.dta"
        try:
            from arminer.core.smart_mode import sanitize_stata_dataframe
            stata_df, labels = sanitize_stata_dataframe(df_firm_year)
            stata_df.to_stata(out_dta, write_index=False, version=118, variable_labels=labels)
        except Exception as e:
            logger.warning(f"News Stata export failed: {e}")

        total_mentions = int(df_firm_year["total_mentions"].sum()) if not df_firm_year.empty and "total_mentions" in df_firm_year.columns else 0
        firms_with_hits = int((df_firm_year["articles_with_hits"] > 0).sum()) if not df_firm_year.empty and "articles_with_hits" in df_firm_year.columns else 0
        unique_firms = len(df_firm_year["ticker"].unique()) if not df_firm_year.empty else 0

        yield {"event": "complete", "data": json.dumps({
            "total_articles": len(df_articles),
            "total_firms": unique_firms,
            "total_obs": len(df_firm_year),
            "firms_with_hits": firms_with_hits,
            "total_mentions": total_mentions,
            "firm_rows": df_firm_year.to_dict(orient="records"),
            "article_rows": df_articles.head(100).to_dict(orient="records"),
            "snippets": all_snippets[:50],
            "excel_download": "/api/download/news_panel_data.xlsx",
            "csv_download": "/api/download/news_panel_data.csv",
            "dta_download": "/api/download/news_panel_data.dta",
        }, ensure_ascii=False, default=str)}

    return EventSourceResponse(event_generator())


@app.post("/api/news/mine-text")
def mine_news_text(req: NewsPasteMineRequest):
    """Khai phá từ điển trực tiếp trên văn bản paste thủ công."""
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=400, detail="Văn bản không được để trống.")

    flex_dict = _resolve_dictionary(topic=req.topic, keywords=req.keywords)
    core_dict = flex_dict.to_core_dictionary()
    matcher = GenericFuzzyMatcher(dictionary=core_dict, threshold=req.threshold)
    calc = SmartVariableCalculator()

    text = req.text.strip()
    words = text.split()
    total_words = len(words)
    text_len = len(text)

    matches = matcher.search(text, use_fuzzy=True) if total_words > 0 else []

    vars_r = calc.calculate_all(
        matches, total_words,
        category_names=flex_dict.categories,
        topic_prefix=req.topic or "news",
        total_dict_keywords=len(flex_dict.entries),
        classification_rules=flex_dict.classification_rules,
    )

    snippets = []
    for m in matches[:10]:
        pos = m.get("position", 0)
        kw = m.get("keyword_found", "")
        snippet = text[max(0, pos - 70):min(text_len, pos + len(kw) + 70)].replace("\n", " ").strip()
        snippets.append({
            "keyword": kw,
            "category": m.get("category", "default"),
            "context": snippet,
        })

    return {
        "ticker": req.ticker,
        "title": req.title,
        "total_words": total_words,
        "total_hits": len(matches),
        "variables": vars_r,
        "snippets": snippets,
    }


# Mount static files
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


def run_ui_server(host: str = "127.0.0.1", port: int = 8000, open_browser: bool = True):
    """Khởi chạy UI server."""
    import uvicorn
    import webbrowser

    url = f"http://{host}:{port}"
    print(f"\nDang khoi chay arminer Web Studio tai: {url}")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    run_ui_server()
