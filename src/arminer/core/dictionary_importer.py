# -*- coding: utf-8 -*-
"""
arminer.core.dictionary_importer
================================
Bộ nhập từ điển nghiên cứu đa định dạng và dung lỗi (Fault-tolerant):
Hỗ trợ:
- Excel (.xlsx, .xls)
- Word (.docx)
- Text / CSV (.txt, .csv)

Tự động nhận diện tiêu đề mờ (Fuzzy header matching), sửa lỗi nhập liệu phổ biến,
lược qua dòng lỗi nghiêm trọng và trả về danh sách cảnh báo chi tiết.
"""

from __future__ import annotations

import io
import re
import csv
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from loguru import logger

# Try importing python-docx if available
try:
    import docx
    HAS_PYTHON_DOCX = True
except ImportError:
    HAS_PYTHON_DOCX = False


@dataclass
class ImportResult:
    """Kết quả phân tích và nhập file từ điển."""
    success: bool
    name: str
    entries: List[Dict[str, Any]] = field(default_factory=list)
    total_parsed: int = 0
    skipped_count: int = 0
    warnings: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)


class DictionaryFileImporter:
    """Trình nạp file từ điển với khả năng dung sai và xử lý lỗi linh hoạt."""

    # Từ khóa nhận diện cột chính xác
    HEADER_KEYWORD_PATTERNS = [
        r"\b(?:t[uừ]\s*kh[oó]a|keyword|canonical|thu[aậ]t\s*ng[uữ]|t[uừ]\s*ch[ií]nh|term|t[uừ]\s*ng[uữ])\b",
    ]
    HEADER_VARIANTS_PATTERNS = [
        r"\b(?:bi[eế]n\s*th[eể]|t[uừ]\s*[đd][oồ]ng\s*ngh[iĩ]a|variants?|synonyms?|d[aạ]ng\s*kh[aá]c|t[uừ]\s*li[eê]n\s*quan)\b",
    ]
    HEADER_CATEGORY_PATTERNS = [
        r"\b(?:nh[oó]m|category|categories|ph[aâ]n\s*lo[aạ]i|l[iĩ]nh\s*v[uự]c|ch[uủ]\s*[đd][eề]|ph[aâ]n\s*nh[oó]m)\b",
    ]
    HEADER_WEIGHT_PATTERNS = [
        r"\b(?:tr[oọ]ng\s*s[oố]|weights?|h[eệ]\s*s[oố]|[đd]i[eể]m|scores?|t[yỷ]\s*tr[oọ]ng)\b",
    ]

    @classmethod
    def parse_file(
        cls,
        file_content: bytes,
        filename: str,
        default_name: Optional[str] = None
    ) -> ImportResult:
        """Phân tích nội dung file từ điển theo phần mở rộng."""
        p = Path(filename)
        ext = p.suffix.lower()
        topic_name = default_name or p.stem.replace("_", " ").replace("-", " ").title()

        if not file_content:
            return ImportResult(
                success=False,
                name=topic_name,
                warnings=["File rỗng, không có dữ liệu để xử lý."]
            )

        try:
            if ext in (".xlsx", ".xls"):
                return cls._parse_excel(file_content, topic_name)
            elif ext == ".docx":
                return cls._parse_docx(file_content, topic_name)
            elif ext in (".txt", ".csv", ".tsv"):
                return cls._parse_text(file_content, topic_name, is_csv=(ext in (".csv", ".tsv")))
            else:
                return ImportResult(
                    success=False,
                    name=topic_name,
                    warnings=[f"Định dạng file '{ext}' không được hỗ trợ. Vui lòng chọn .xlsx, .docx, .txt hoặc .csv."]
                )
        except Exception as e:
            logger.error(f"Lỗi phân tích file từ điển '{filename}': {e}")
            return ImportResult(
                success=False,
                name=topic_name,
                warnings=[f"Lỗi không xác định khi đọc file: {str(e)}"]
            )

    @classmethod
    def _match_header(cls, text: str, patterns: List[str]) -> bool:
        """Kiểm tra một chuỗi tiêu đề cột có khớp với danh sách regex không."""
        clean = text.strip().lower()
        for pat in patterns:
            if re.search(pat, clean, re.IGNORECASE):
                return True
        return False

    @classmethod
    def _normalize_string(cls, val: Any) -> str:
        """Chuẩn hóa chuỗi an toàn."""
        if val is None or pd.isna(val):
            return ""
        s = str(val).strip()
        # Loại bỏ các ký tự điều khiển lạ
        return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s).strip()

    @classmethod
    def _parse_variants(cls, val: Any) -> List[str]:
        """Tách các biến thể từ chuỗi (hỗ trợ dấu |, dấu phẩy, chấm phẩy hoặc tab)."""
        s = cls._normalize_string(val)
        if not s:
            return []
        parts = re.split(r"[|;,\t\n\r]+", s)
        res = []
        for p in parts:
            p_clean = p.strip()
            if p_clean and p_clean.lower() not in [x.lower() for x in res]:
                res.append(p_clean)
        return res

    @classmethod
    def _parse_weight(cls, val: Any, row_idx: int, warnings: List[str]) -> float:
        """Chuẩn hóa trọng số, tự sửa dấu phẩy thành dấu chấm hoặc fallback về 1.0."""
        s = cls._normalize_string(val)
        if not s:
            return 1.0
        # Thay thế dấu phẩy số học (ví dụ 1,5 -> 1.5)
        s_dot = s.replace(",", ".")
        try:
            w = float(s_dot)
            if w <= 0:
                warnings.append(f"Dòng {row_idx}: Trọng số '{s}' <= 0, hệ thống tự động gán lại 1.0.")
                return 1.0
            return w
        except ValueError:
            warnings.append(f"Dòng {row_idx}: Trọng số '{s}' không hợp lệ, hệ thống tự động gán mặc định 1.0.")
            return 1.0

    @classmethod
    def _merge_entries(cls, raw_entries: List[Dict[str, Any]], warnings: List[str]) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Hợp nhất các từ khóa bị trùng lặp trong file và sắp xếp theo nhóm."""
        merged: Dict[str, Dict[str, Any]] = {}
        all_categories = set()

        for idx, item in enumerate(raw_entries, 1):
            kw = item["keyword"].strip()
            kw_lower = kw.lower()
            cat = item.get("category", "").strip() or "Chung"
            weight = item.get("weight", 1.0)
            variants = item.get("variants", [])

            all_categories.add(cat)

            if kw_lower in merged:
                # Trùng lặp -> Hợp nhất variants và lấy weight lớn nhất
                existing = merged[kw_lower]
                # Merge variants
                cur_vars = existing["variants"]
                for v in variants:
                    if v.lower() != kw_lower and v.lower() not in [x.lower() for x in cur_vars]:
                        cur_vars.append(v)
                # Keep max weight
                if weight > existing["weight"]:
                    existing["weight"] = weight
                warnings.append(f"Dòng {idx}: Từ khóa '{kw}' bị lặp, hệ thống đã tự động gộp các từ đồng nghĩa và giữ trọng số cao nhất.")
            else:
                # Lọc bỏ chính keyword khỏi variants nếu có
                clean_vars = [v for v in variants if v.lower() != kw_lower]
                merged[kw_lower] = {
                    "id": len(merged) + 1,
                    "keyword": kw,
                    "variants": clean_vars,
                    "category": cat,
                    "weight": weight,
                    "language": "vi",
                }

        final_list = list(merged.values())
        return final_list, sorted(list(all_categories))

    # --------------------------------------------------------------------------
    # 1. EXCEL PARSER (.xlsx, .xls)
    # --------------------------------------------------------------------------
    @classmethod
    def _parse_excel(cls, file_content: bytes, topic_name: str) -> ImportResult:
        warnings: List[str] = []
        try:
            # Đọc toàn bộ bảng tính đầu tiên mà không định trước header
            df_raw = pd.read_excel(io.BytesIO(file_content), header=None, dtype=str)
        except Exception as e:
            return ImportResult(
                success=False,
                name=topic_name,
                warnings=[f"Không thể đọc bảng tính Excel: {str(e)}"]
            )

        if df_raw.empty:
            return ImportResult(
                success=False,
                name=topic_name,
                warnings=["File Excel không chứa hàng dữ liệu nào."]
            )

        # 1. Tìm hàng tiêu đề (nếu có) trong 5 hàng đầu tiên
        header_row_idx = -1
        col_kw = -1
        col_var = -1
        col_cat = -1
        col_w = -1

        for r_idx in range(min(5, len(df_raw))):
            row_vals = [cls._normalize_string(v) for v in df_raw.iloc[r_idx]]
            kw_candidates = [i for i, v in enumerate(row_vals) if cls._match_header(v, cls.HEADER_KEYWORD_PATTERNS)]
            if kw_candidates:
                header_row_idx = r_idx
                col_kw = kw_candidates[0]
                # Tìm các cột còn lại
                for i, v in enumerate(row_vals):
                    if i == col_kw:
                        continue
                    if cls._match_header(v, cls.HEADER_VARIANTS_PATTERNS) and col_var == -1:
                        col_var = i
                    elif cls._match_header(v, cls.HEADER_CATEGORY_PATTERNS) and col_cat == -1:
                        col_cat = i
                    elif cls._match_header(v, cls.HEADER_WEIGHT_PATTERNS) and col_w == -1:
                        col_w = i
                break

        # Nếu không tìm thấy hàng tiêu đề rõ ràng, ngầm định theo thứ tự cột:
        # Cột 0: Từ khóa chính, Cột 1: Biến thể, Cột 2: Nhóm, Cột 3: Trọng số
        start_row = 0
        if header_row_idx != -1:
            start_row = header_row_idx + 1
        else:
            col_kw = 0
            if df_raw.shape[1] > 1:
                col_var = 1
            if df_raw.shape[1] > 2:
                col_cat = 2
            if df_raw.shape[1] > 3:
                col_w = 3
            warnings.append("Hệ thống không tìm thấy hàng tiêu đề rõ ràng, tự động ánh xạ: Cột 1 là Từ khóa, Cột 2 là Biến thể, Cột 3 là Nhóm, Cột 4 là Trọng số.")

        raw_entries = []
        skipped = 0

        for r_idx in range(start_row, len(df_raw)):
            row = df_raw.iloc[r_idx]
            display_row = r_idx + 1

            kw_val = cls._normalize_string(row.iloc[col_kw]) if col_kw < len(row) else ""
            kw_val = re.sub(r"^(?:[\-\*\•\+]|\d+[\.\)])\s*", "", kw_val).strip()
            if not kw_val:
                # Kiểm tra nếu toàn bộ hàng rỗng thì bỏ qua không báo lỗi
                all_empty = all(not cls._normalize_string(v) for v in row)
                if not all_empty:
                    skipped += 1
                    warnings.append(f"Hàng {display_row}: Không có từ khóa chính, hệ thống đã bỏ qua.")
                continue

            var_val = cls._parse_variants(row.iloc[col_var]) if (col_var != -1 and col_var < len(row)) else []
            cat_val = cls._normalize_string(row.iloc[col_cat]) if (col_cat != -1 and col_cat < len(row)) else "Chung"
            w_val = cls._parse_weight(row.iloc[col_w], display_row, warnings) if (col_w != -1 and col_w < len(row)) else 1.0

            raw_entries.append({
                "keyword": kw_val,
                "variants": var_val,
                "category": cat_val or "Chung",
                "weight": w_val,
            })

        if not raw_entries:
            return ImportResult(
                success=False,
                name=topic_name,
                warnings=["Không tìm thấy từ khóa hợp lệ nào trong file Excel."] + warnings,
                skipped_count=skipped
            )

        entries, categories = cls._merge_entries(raw_entries, warnings)
        return ImportResult(
            success=True,
            name=topic_name,
            entries=entries,
            total_parsed=len(entries),
            skipped_count=skipped,
            warnings=warnings,
            categories=categories
        )

    # --------------------------------------------------------------------------
    # 2. WORD PARSER (.docx)
    # --------------------------------------------------------------------------
    @classmethod
    def _parse_docx(cls, file_content: bytes, topic_name: str) -> ImportResult:
        warnings: List[str] = []
        raw_rows: List[List[str]] = []

        # Thử dùng python-docx nếu có
        if HAS_PYTHON_DOCX:
            try:
                doc = docx.Document(io.BytesIO(file_content))
                # 1. Đọc tất cả các bảng trong Word trước
                for table in doc.tables:
                    for row in table.rows:
                        row_text = [cls._normalize_string(cell.text) for cell in row.cells]
                        if any(row_text):
                            raw_rows.append(row_text)

                # 2. Nếu không có bảng, đọc các đoạn văn (Paragraphs)
                if not raw_rows:
                    for p in doc.paragraphs:
                        text = cls._normalize_string(p.text)
                        if text:
                            # Tách theo phân cách tab hoặc gạch đứng
                            if "\t" in text:
                                parts = [x.strip() for x in text.split("\t") if x.strip()]
                            elif "|" in text:
                                parts = [x.strip() for x in text.split("|") if x.strip()]
                            else:
                                parts = [text]
                            raw_rows.append(parts)
            except Exception as e:
                logger.warning(f"python-docx error, fallback to xml parser: {e}")
                raw_rows = []

        # Fallback pure-python (đọc trực tiếp file zip xml) nếu python-docx không có hoặc lỗi
        if not raw_rows:
            try:
                with zipfile.ZipFile(io.BytesIO(file_content)) as z:
                    xml_content = z.read("word/document.xml")
                root = ET.fromstring(xml_content)
                # Namespace Word
                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                # Tìm tất cả bảng
                for tbl in root.findall(".//w:tbl", ns):
                    for tr in tbl.findall(".//w:tr", ns):
                        cells = []
                        for tc in tr.findall(".//w:tc", ns):
                            texts = [t.text for t in tc.findall(".//w:t", ns) if t.text]
                            cells.append("".join(texts).strip())
                        if any(cells):
                            raw_rows.append(cells)

                # Nếu vẫn không có bảng, tìm các đoạn văn w:p
                if not raw_rows:
                    for p in root.findall(".//w:p", ns):
                        texts = [t.text for t in p.findall(".//w:t", ns) if t.text]
                        line = "".join(texts).strip()
                        if line:
                            if "|" in line:
                                raw_rows.append([x.strip() for x in line.split("|") if x.strip()])
                            elif "\t" in line:
                                raw_rows.append([x.strip() for x in line.split("\t") if x.strip()])
                            else:
                                raw_rows.append([line])
            except Exception as e:
                return ImportResult(
                    success=False,
                    name=topic_name,
                    warnings=[f"Không thể giải mã file Word (.docx): {str(e)}"]
                )

        if not raw_rows:
            return ImportResult(
                success=False,
                name=topic_name,
                warnings=["File Word trống hoặc không có nội dung văn bản."]
            )

        # Chuyển raw_rows thành DataFrame và gọi _parse_table_data
        df_raw = pd.DataFrame(raw_rows)
        return cls._parse_tabular_list(df_raw, topic_name, warnings)

    # --------------------------------------------------------------------------
    # 3. TEXT / CSV PARSER (.txt, .csv)
    # --------------------------------------------------------------------------
    @classmethod
    def _parse_text(cls, file_content: bytes, topic_name: str, is_csv: bool = False) -> ImportResult:
        warnings: List[str] = []

        # Thử các bộ mã giải mã tiếng Việt phổ biến
        text = ""
        for encoding in ("utf-8-sig", "utf-8", "cp1258", "windows-1258", "latin-1"):
            try:
                text = file_content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

        if not text:
            return ImportResult(
                success=False,
                name=topic_name,
                warnings=["Không thể giải mã nội dung text (lỗi font encoding). Vui lòng lưu file với bảng mã UTF-8."]
            )

        lines = [line.strip() for line in text.splitlines()]
        # Lọc bỏ comment (# hoặc //)
        data_lines = [l for l in lines if l and not l.startswith("#") and not l.startswith("//")]

        if not data_lines:
            return ImportResult(
                success=False,
                name=topic_name,
                warnings=["File văn bản không có dòng dữ liệu hợp lệ nào."]
            )

        # Thử detect dấu phân cách nếu là CSV hoặc Text phân cách
        # Kiểm tra sự xuất hiện của |, tab, dấu phẩy, chấm phẩy
        sample = "\n".join(data_lines[:10])
        delimiter = None
        if "|" in sample:
            delimiter = "|"
        elif "\t" in sample:
            delimiter = "\t"
        elif is_csv:
            delimiter = "," if sample.count(",") >= sample.count(";") else ";"

        raw_rows = []
        if delimiter:
            for l in data_lines:
                # Đọc CSV chuẩn nếu có dấu phẩy
                if delimiter in (",", ";"):
                    try:
                        reader = csv.reader([l], delimiter=delimiter)
                        row = next(reader)
                    except Exception:
                        row = [x.strip() for x in l.split(delimiter)]
                else:
                    row = [x.strip() for x in l.split(delimiter)]
                if row:
                    row[0] = re.sub(r"^(?:[\-\*\•\+]|\d+[\.\)])\s*", "", row[0]).strip()
                raw_rows.append(row)
        else:
            # Danh sách thuần 1 từ khóa trên mỗi dòng
            for l in data_lines:
                # Loại bỏ các ký tự bullet point gạch đầu dòng: "- ", "* ", "1. ", "• "
                clean_l = re.sub(r"^(?:[\-\*\•\+]|\d+[\.\)])\s*", "", l).strip()
                if clean_l:
                    raw_rows.append([clean_l])

        df_raw = pd.DataFrame(raw_rows)
        return cls._parse_tabular_list(df_raw, topic_name, warnings)

    # --------------------------------------------------------------------------
    # COMMON TABULAR PROCESSING
    # --------------------------------------------------------------------------
    @classmethod
    def _parse_tabular_list(cls, df_raw: pd.DataFrame, topic_name: str, initial_warnings: List[str]) -> ImportResult:
        warnings = list(initial_warnings)
        if df_raw.empty:
            return ImportResult(success=False, name=topic_name, warnings=["Không có dữ liệu hợp lệ."])

        # Tìm hàng tiêu đề (nếu có)
        header_row_idx = -1
        col_kw = -1
        col_var = -1
        col_cat = -1
        col_w = -1

        for r_idx in range(min(3, len(df_raw))):
            row_vals = [cls._normalize_string(v) for v in df_raw.iloc[r_idx]]
            kw_candidates = [i for i, v in enumerate(row_vals) if cls._match_header(v, cls.HEADER_KEYWORD_PATTERNS)]
            if kw_candidates:
                header_row_idx = r_idx
                col_kw = kw_candidates[0]
                for i, v in enumerate(row_vals):
                    if i == col_kw:
                        continue
                    if cls._match_header(v, cls.HEADER_VARIANTS_PATTERNS) and col_var == -1:
                        col_var = i
                    elif cls._match_header(v, cls.HEADER_CATEGORY_PATTERNS) and col_cat == -1:
                        col_cat = i
                    elif cls._match_header(v, cls.HEADER_WEIGHT_PATTERNS) and col_w == -1:
                        col_w = i
                break

        start_row = 0
        if header_row_idx != -1:
            start_row = header_row_idx + 1
        else:
            col_kw = 0
            if df_raw.shape[1] > 1:
                col_var = 1
            if df_raw.shape[1] > 2:
                col_cat = 2
            if df_raw.shape[1] > 3:
                col_w = 3

        raw_entries = []
        skipped = 0

        for r_idx in range(start_row, len(df_raw)):
            row = df_raw.iloc[r_idx]
            display_row = r_idx + 1

            kw_val = cls._normalize_string(row.iloc[col_kw]) if col_kw < len(row) else ""
            kw_val = re.sub(r"^(?:[\-\*\•\+]|\d+[\.\)])\s*", "", kw_val).strip()
            if not kw_val:
                all_empty = all(not cls._normalize_string(v) for v in row)
                if not all_empty:
                    skipped += 1
                    warnings.append(f"Dòng {display_row}: Không có từ khóa chính, hệ thống đã bỏ qua.")
                continue

            var_val = cls._parse_variants(row.iloc[col_var]) if (col_var != -1 and col_var < len(row)) else []
            cat_val = cls._normalize_string(row.iloc[col_cat]) if (col_cat != -1 and col_cat < len(row)) else "Chung"
            w_val = cls._parse_weight(row.iloc[col_w], display_row, warnings) if (col_w != -1 and col_w < len(row)) else 1.0

            raw_entries.append({
                "keyword": kw_val,
                "variants": var_val,
                "category": cat_val or "Chung",
                "weight": w_val,
            })

        if not raw_entries:
            return ImportResult(
                success=False,
                name=topic_name,
                warnings=["Không tìm thấy từ khóa hợp lệ nào trong file."] + warnings,
                skipped_count=skipped
            )

        entries, categories = cls._merge_entries(raw_entries, warnings)
        return ImportResult(
            success=True,
            name=topic_name,
            entries=entries,
            total_parsed=len(entries),
            skipped_count=skipped,
            warnings=warnings,
            categories=categories
        )
