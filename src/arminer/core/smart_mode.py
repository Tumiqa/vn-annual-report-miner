# -*- coding: utf-8 -*-
"""
arminer.core.smart_mode
=========================
Flexible Input + Comprehensive Output.

Nhà nghiên cứu KIỂM SOÁT — nhưng input cực dễ, output cực đầy đủ.

Input từ khóa có thể là:
  - File .txt (1 keyword/dòng)
  - File .csv / .xlsx (cột keyword, category, variants)
  - File .yaml (power users)
  - List Python: ["blockchain", "smart contract"]
  - String phân tách: "blockchain, smart contract, DeFi"
  - CLI inline: --keywords "blockchain, smart contract"

Tool tự xử lý: detect format, parse, normalize, sinh tất cả biến chuẩn.
"""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
from loguru import logger


# =====================================================================
# FlexibleDictionary — Nhận input KIỂU GÌ CŨNG ĐƯỢC
# =====================================================================

class FlexibleDictionary:
    """
    Bộ từ điển linh hoạt — nhận input bằng MỌI CÁCH.

    Ví dụ::

        # Cách 1: Từ file text (1 keyword/dòng)
        d = FlexibleDictionary.load("keywords.txt")

        # Cách 2: Từ CSV/Excel
        d = FlexibleDictionary.load("keywords.csv")
        d = FlexibleDictionary.load("keywords.xlsx")

        # Cách 3: Từ YAML (power users)
        d = FlexibleDictionary.load("dictionary.yaml")

        # Cách 4: Từ list Python
        d = FlexibleDictionary.from_list(["blockchain", "smart contract", "DeFi"])

        # Cách 5: Từ string
        d = FlexibleDictionary.from_string("blockchain, smart contract, DeFi")

        # Cách 6: Từ dict Python
        d = FlexibleDictionary.from_dict({
            "core": ["blockchain", "smart contract"],
            "finance": ["cryptocurrency", "bitcoin"],
        })

    Tất cả đều cho ra cùng 1 Dictionary object chuẩn.
    """

    @staticmethod
    def load(source: Union[str, Path, list, dict]) -> "FlexibleDictionary":
        """
        Auto-detect và load từ BẤT KỲ nguồn nào.

        Args:
            source: filepath (.txt/.csv/.xlsx/.yaml/.json), list, dict, hoặc string

        Returns:
            Dictionary object sẵn sàng sử dụng
        """
        # List → from_list
        if isinstance(source, (list, tuple)):
            return FlexibleDictionary.from_list(source)

        # Dict → from_dict
        if isinstance(source, dict):
            return FlexibleDictionary.from_dict(source)

        source = str(source)

        # Nếu là string chứa dấu phẩy và không phải filepath → from_string
        if "," in source and not Path(source).suffix:
            return FlexibleDictionary.from_string(source)

        # File path → detect by extension
        path = Path(source)
        if not path.exists():
            # Có thể là string keywords
            return FlexibleDictionary.from_string(source)

        ext = path.suffix.lower()
        if ext == ".txt":
            return FlexibleDictionary._from_txt(path)
        elif ext == ".csv":
            return FlexibleDictionary._from_csv(path)
        elif ext in (".xlsx", ".xls"):
            return FlexibleDictionary._from_excel(path)
        elif ext in (".yaml", ".yml"):
            return FlexibleDictionary._from_yaml(path)
        elif ext == ".json":
            return FlexibleDictionary._from_yaml(path)  # same schema
        else:
            # Try as text file
            return FlexibleDictionary._from_txt(path)

    # -----------------------------------------------------------------
    # Factory methods
    # -----------------------------------------------------------------

    @staticmethod
    def from_list(keywords: List[str], category: str = "default") -> "FlexibleDictionary":
        """
        Từ list đơn giản::

            ["blockchain", "smart contract", "DeFi"]
        """
        d = FlexibleDictionary()
        d.name = "Custom Dictionary"
        for kw in keywords:
            kw = kw.strip()
            if kw:
                d._add(kw, category=category)
        logger.info(f"Loaded {len(d.entries)} keywords from list")
        return d

    @staticmethod
    def from_string(text: str) -> "FlexibleDictionary":
        """
        Từ string phân tách bằng dấu phẩy hoặc xuống dòng::

            "blockchain, smart contract, DeFi"
        """
        # Split by comma, semicolon, or newline
        parts = re.split(r"[,;\n]+", text)
        keywords = [p.strip() for p in parts if p.strip()]
        return FlexibleDictionary.from_list(keywords)

    @staticmethod
    def from_dict(data: Dict[str, List[str]]) -> "FlexibleDictionary":
        """
        Từ dict phân nhóm::

            {
                "core": ["blockchain", "distributed ledger"],
                "finance": ["cryptocurrency", "bitcoin"],
            }
        """
        d = FlexibleDictionary()
        d.name = "Custom Dictionary"
        for category, keywords in data.items():
            for kw in keywords:
                kw = kw.strip()
                if kw:
                    d._add(kw, category=category)
        logger.info(
            f"Loaded {len(d.entries)} keywords in "
            f"{len(d.categories)} categories from dict"
        )
        return d

    @staticmethod
    def _from_txt(path: Path) -> "FlexibleDictionary":
        """
        File text — format cực đơn giản:

        Cách 1 — Flat (1 keyword/dòng)::

            blockchain
            smart contract
            cryptocurrency

        Cách 2 — Có category (dùng [Header])::

            [Core]
            blockchain
            distributed ledger
            smart contract

            [Finance]
            cryptocurrency
            bitcoin
            DeFi
        """
        d = FlexibleDictionary()
        d.name = path.stem.replace("_", " ").title()

        text = path.read_text(encoding="utf-8-sig")
        lines = text.strip().split("\n")

        current_cat = "default"
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Check for category header: [Category] or ## Category
            header_match = re.match(r"^\[(.+)\]$|^#{1,3}\s+(.+)$", line)
            if header_match:
                current_cat = (header_match.group(1) or header_match.group(2)).strip().lower()
                continue

            # Keyword line — có thể có variants sau dấu | hoặc tab
            parts = re.split(r"\t+|\s*\|\s*", line, maxsplit=1)
            keyword = parts[0].strip()
            variants = parts[1].strip() if len(parts) > 1 else None

            if keyword:
                d._add(keyword, category=current_cat, variants=variants)

        logger.info(
            f"Loaded {len(d.entries)} keywords from {path.name} "
            f"({len(d.categories)} categories)"
        )
        return d

    @staticmethod
    def _from_csv(path: Path) -> "FlexibleDictionary":
        """
        File CSV — tự detect cột:

        Tối thiểu chỉ cần 1 cột 'keyword'::

            keyword
            blockchain
            smart contract

        Đầy đủ::

            keyword,category,variants,language
            blockchain,core,block chain|block-chain,en
            chuỗi khối,core,chuoi khoi,vi
        """
        d = FlexibleDictionary()
        d.name = path.stem.replace("_", " ").title()

        with open(path, "r", encoding="utf-8-sig") as f:
            # Detect delimiter
            sample = f.read(4096)
            f.seek(0)

            if "\t" in sample and "," not in sample:
                dialect = csv.excel_tab
            else:
                try:
                    dialect = csv.Sniffer().sniff(sample)
                except csv.Error:
                    dialect = csv.excel

            reader = csv.DictReader(f, dialect=dialect)
            headers = [h.lower().strip() for h in (reader.fieldnames or [])]

            # Auto-detect column mapping
            kw_col = _find_col(headers, ["keyword", "keywords", "term", "terms",
                                          "word", "words", "từ khóa", "tu khoa"])
            cat_col = _find_col(headers, ["category", "categories", "group", "functional_group",
                                           "functional group", "nhóm", "nhom", "cat"])
            var_col = _find_col(headers, ["variants", "variant", "keyword_variants", "synonyms",
                                           "biến thể", "bien the", "alias"])
            lang_col = _find_col(headers, ["language", "lang", "ngôn ngữ"])
            amb_col = _find_col(headers, ["is_ambiguous", "ambiguous", "đa nghĩa", "da nghia"])
            act_col = _find_col(headers, ["is_active", "active", "hoạt động", "hoat dong"])

            if not kw_col:
                # Không có header → assume cột đầu tiên là keyword
                f.seek(0)
                for line in f:
                    keyword = line.strip().split(",")[0].strip().strip('"')
                    if keyword and keyword.lower() not in ("keyword", "term"):
                        d._add(keyword)
            else:
                for row in reader:
                    keyword = row.get(kw_col, "").strip()
                    if not keyword:
                        continue

                    # Filter inactive
                    if act_col:
                        act_val = str(row.get(act_col, "1")).strip().lower()
                        if act_val in ("0", "false", "no", "inactive"):
                            continue

                    raw_cat = row.get(cat_col, "").strip().lower() if cat_col else ""
                    category = raw_cat if raw_cat else "default"
                    variants = row.get(var_col, "").strip() if var_col else None
                    language = row.get(lang_col, "en").strip() if lang_col else "en"

                    # Parse ambiguity
                    is_amb = False
                    if amb_col:
                        amb_val = str(row.get(amb_col, "0")).strip().lower()
                        is_amb = amb_val in ("1", "true", "yes")

                    d._add(keyword, category=category, variants=variants,
                           language=language, is_ambiguous=is_amb)

        logger.info(f"Loaded {len(d.entries)} keywords from CSV: {path.name}")
        return d

    @staticmethod
    def _from_excel(path: Path) -> "FlexibleDictionary":
        """File Excel — cùng logic với CSV."""
        try:
            df = pd.read_excel(path, engine="openpyxl")
        except ImportError:
            raise ImportError("openpyxl needed for Excel. Run: pip install openpyxl")

        d = FlexibleDictionary()
        d.name = path.stem.replace("_", " ").title()

        cols = [c.lower().strip() for c in df.columns]
        kw_idx = _find_col_idx(cols, ["keyword", "keywords", "term", "từ khóa"])
        cat_idx = _find_col_idx(cols, ["category", "nhóm", "group", "functional_group"])
        var_idx = _find_col_idx(cols, ["variants", "biến thể", "keyword_variants", "synonyms"])
        amb_idx = _find_col_idx(cols, ["is_ambiguous", "ambiguous", "đa nghĩa"])
        act_idx = _find_col_idx(cols, ["is_active", "active", "hoạt động"])

        kw_col = df.columns[kw_idx] if kw_idx is not None else df.columns[0]
        cat_col = df.columns[cat_idx] if cat_idx is not None else None
        var_col = df.columns[var_idx] if var_idx is not None else None
        amb_col = df.columns[amb_idx] if amb_idx is not None else None
        act_col = df.columns[act_idx] if act_idx is not None else None

        for _, row in df.iterrows():
            keyword = str(row[kw_col]).strip()
            if not keyword or keyword == "nan":
                continue

            if act_col:
                act_val = str(row[act_col]).strip().lower()
                if act_val in ("0", "false", "no", "inactive"):
                    continue

            category = str(row[cat_col]).strip().lower() if cat_col and pd.notna(row[cat_col]) else "default"
            variants = str(row[var_col]).strip() if var_col and pd.notna(row[var_col]) else None
            is_amb = False
            if amb_col and pd.notna(row[amb_col]):
                is_amb = str(row[amb_col]).strip().lower() in ("1", "true", "yes")

            d._add(keyword, category=category, variants=variants, is_ambiguous=is_amb)

        logger.info(f"Loaded {len(d.entries)} keywords from Excel: {path.name}")
        return d

    @staticmethod
    def _from_yaml(path: Path) -> "FlexibleDictionary":
        """Delegate to existing Dictionary.from_yaml."""
        from arminer.core.dictionary import Dictionary
        core_dict = Dictionary.from_yaml(path)

        d = FlexibleDictionary()
        d.name = core_dict.name
        d._core_dict = core_dict
        d.entries = []
        d._categories = set()

        for cat_name, cat in core_dict.categories.items():
            d._categories.add(cat_name)
            for entry in cat.keywords:
                d.entries.append({
                    "keyword": entry.keyword,
                    "category": cat_name,
                    "variants": entry.variants,
                    "language": entry.language,
                    "weight": entry.weight,
                    "is_ambiguous": entry.is_ambiguous,
                })

        d._classification_rules = core_dict.classification_rules
        d._exclusions = [e["keyword"].lower() for e in core_dict.exclusions]
        return d

    # -----------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------

    def __init__(self):
        self.name = "Dictionary"
        self.entries: List[Dict[str, Any]] = []
        self._categories: set = set()
        self._core_dict = None
        self._classification_rules: Dict = {}
        self._exclusions: List[str] = []

    def _add(self, keyword: str, category: str = "default",
             variants: Optional[str] = None, language: str = "en",
             weight: float = 1.0, is_ambiguous: bool = False):
        keyword = keyword.strip().lower()
        if not keyword:
            return
        self._categories.add(category)
        self.entries.append({
            "keyword": keyword,
            "category": category,
            "variants": variants,
            "language": language,
            "weight": weight,
            "is_ambiguous": is_ambiguous,
        })

    @property
    def categories(self) -> List[str]:
        return sorted(self._categories)

    @property
    def classification_rules(self) -> Dict:
        return self._classification_rules

    @property
    def exclusions(self) -> List[str]:
        return self._exclusions

    def to_core_dictionary(self):
        """Convert to core Dictionary object for matcher."""
        if self._core_dict:
            return self._core_dict

        from arminer.core.dictionary import Dictionary, Category, KeywordEntry

        d = Dictionary(name=self.name)
        d.classification_rules = self._classification_rules
        d.exclusions = [{"keyword": k} for k in self._exclusions]

        for entry in self.entries:
            cat_name = entry["category"]
            if cat_name not in d.categories:
                d.categories[cat_name] = Category(name=cat_name)

            kw_entry = KeywordEntry(
                keyword=entry["keyword"],
                variants=entry.get("variants"),
                language=entry.get("language", "en"),
                weight=entry.get("weight", 1.0),
                is_ambiguous=entry.get("is_ambiguous", False),
            )
            d.categories[cat_name].add_keyword(kw_entry)

        return d

    def get_flat_list(self) -> List[str]:
        """All keywords + variants, flattened."""
        result = set()
        for entry in self.entries:
            kw = entry["keyword"]
            if kw not in self._exclusions:
                result.add(kw)
                if entry.get("variants"):
                    for v in entry["variants"].split("|"):
                        v = v.strip().lower()
                        if v and v not in self._exclusions:
                            result.add(v)
        return sorted(result)

    def stats(self) -> Dict:
        """Thống kê."""
        by_cat = {}
        for e in self.entries:
            cat = e["category"]
            by_cat[cat] = by_cat.get(cat, 0) + 1

        return {
            "name": self.name,
            "total_keywords": len(self.entries),
            "total_with_variants": len(self.get_flat_list()),
            "categories": by_cat,
            "exclusions": len(self._exclusions),
        }

    def __repr__(self):
        return f"FlexibleDictionary({self.name!r}, {len(self.entries)} keywords)"
    
    def __len__(self):
        return len(self.entries)


# =====================================================================
# SmartVariableCalculator — Tự sinh TẤT CẢ biến chuẩn
# =====================================================================

class SmartVariableCalculator:
    """
    Tự tính TẤT CẢ biến nghiên cứu chuẩn.

    Nhà nghiên cứu chỉ cần cung cấp từ khóa.
    Tool tự sinh output đầy đủ cho bài báo:
    - frequency, diversity, score, intensity, binary, classification
    - Per-category breakdown
    - Descriptive stats, correlation matrix
    """

    def __init__(self, normalization: int = 10_000):
        self.normalization = normalization

    def calculate_all(
        self,
        matches: List[Dict],
        total_words: int,
        category_names: List[str],
        topic_prefix: str = "topic",
        classification_rules: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Tính TẤT CẢ biến cho 1 báo cáo → 1 dòng panel."""
        p = topic_prefix.lower()
        result: Dict[str, Any] = {}

        freq = len(matches)
        unique_kws = set(
            m.get("keyword_canonical", m.get("keyword_found", ""))
            for m in matches
        )

        result[f"{p}_frequency"] = freq
        result[f"{p}_diversity"] = len(unique_kws)
        result[f"{p}_score"] = (
            round((freq / total_words) * self.normalization, 6)
            if total_words > 0 else 0.0
        )
        result[f"{p}_intensity"] = round(math.log(1 + freq), 6)
        result[f"{p}_has_mention"] = 1 if freq > 0 else 0
        result[f"{p}_adoption"] = self._classify(matches, classification_rules)

        # Per-category
        for cat in category_names:
            cat_matches = [m for m in matches if m.get("category") == cat]
            cc = cat.lower().replace(" ", "_")
            cat_freq = len(cat_matches)
            cat_unique = set(
                m.get("keyword_canonical", m.get("keyword_found", ""))
                for m in cat_matches
            )
            result[f"{p}_{cc}_freq"] = cat_freq
            result[f"{p}_{cc}_div"] = len(cat_unique)
            result[f"{p}_{cc}_score"] = (
                round((cat_freq / total_words) * self.normalization, 6)
                if total_words > 0 else 0.0
            )

        result["total_words"] = total_words
        return result

    def _classify(self, matches, rules):
        if not rules or not matches:
            return 0
        adoption = rules.get("adoption") or rules.get("implemented")
        if not adoption:
            return 0
        triggers = [k.lower() for k in adoption.get("trigger_keywords", [])]
        for m in matches:
            kw = m.get("keyword_found", "").lower()
            for t in triggers:
                if t in kw:
                    return 1
        return 0


# =====================================================================
# Stata & Codebook Helpers
# =====================================================================

def sanitize_stata_dataframe(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """Làm sạch DataFrame để xuất Stata .dta an toàn, không trùng lặp cột.

    Quy tắc Stata 118:
    - Tên biến tối đa 32 ký tự, chỉ gồm [a-zA-Z0-9_], bắt đầu bằng chữ cái hoặc gạch dưới.
    - Tuyệt đối không trùng lặp tên biến (tự động thêm hậu tố _1, _2 nếu trùng sau khi cắt ngắn).
    - Lưu giữ toàn bộ tên gốc đầy đủ trong Stata variable_labels (lên đến 80 ký tự).
    - Chuẩn hóa kiểu dữ liệu dạng chuỗi để tránh lỗi kiểu dữ liệu hỗn hợp.
    """
    sdf = df.copy()
    seen = set()
    new_cols = []
    labels = {}

    for col in sdf.columns:
        col_str = str(col).strip()
        # Chuyển ký tự không hợp lệ thành gạch dưới
        clean = re.sub(r"[^a-zA-Z0-9_]", "_", col_str)
        if not clean or clean[0].isdigit():
            clean = "_" + clean
        clean = clean[:32]
        base = clean[:28]
        candidate = clean
        counter = 1
        while candidate.lower() in seen:
            candidate = f"{base}_{counter}"[:32]
            counter += 1
        seen.add(candidate.lower())
        new_cols.append(candidate)
        labels[candidate] = col_str[:80]

    sdf.columns = new_cols

    # Xử lý các cột dạng chuỗi / object
    for c in sdf.columns:
        if sdf[c].dtype == "object":
            sdf[c] = sdf[c].fillna("").astype(str)

    return sdf, labels


def auto_generate_codebook(df: pd.DataFrame) -> List[Dict[str, str]]:
    """Tự động sinh bảng giải thích biến (Codebook) chuẩn bài báo nghiên cứu."""
    codebook = []
    for col in df.columns:
        c_lower = col.lower()
        if c_lower == "ticker":
            desc = "Mã chứng khoán niêm yết (HOSE, HNX, UPCoM)"
            vtype = "Mã định danh (Identifier)"
            formula = "Mã cổ phiếu chuẩn 3 chữ cái"
        elif c_lower == "year":
            desc = "Năm công bố báo cáo thường niên / tài chính"
            vtype = "Biến thời gian (Time ID)"
            formula = "Năm dương lịch (YYYY)"
        elif c_lower == "icb_level1":
            desc = "Ngành cấp 1 theo chuẩn phân ngành ICB"
            vtype = "Biến phân loại (Categorical)"
            formula = "10 ngành cấp 1 (Tài chính, Công nghệ, Bất động sản...)"
        elif c_lower == "icb_level2":
            desc = "Ngành cấp 2 theo chuẩn phân ngành ICB"
            vtype = "Biến phân loại (Categorical)"
            formula = "Ngành chi tiết cấp 2"
        elif c_lower == "file":
            desc = "Tên tệp tin báo cáo thường niên gốc"
            vtype = "Thông tin tệp (Metadata)"
            formula = "Tên file PDF/TXT phân tích"
        elif c_lower == "pages":
            desc = "Độ dài báo cáo thường niên (tổng số trang)"
            vtype = "Định lượng (Continuous)"
            formula = "Tổng số trang của file PDF"
        elif c_lower == "total_words":
            desc = "Tổng số từ trong toàn văn báo cáo thường niên"
            vtype = "Định lượng (Continuous)"
            formula = "Tổng số từ trích xuất sau khi làm sạch văn bản"
        elif c_lower.endswith("_frequency"):
            topic = col[:-10]
            desc = f"Tổng tần suất xuất hiện các từ khóa liên quan đến {topic}"
            vtype = "Đếm số lần (Count)"
            formula = "Tổng số lần từ khóa thuộc chủ đề xuất hiện trong báo cáo"
        elif c_lower.endswith("_diversity"):
            topic = col[:-10]
            desc = f"Độ phong phú từ vựng chủ đề {topic} (số từ khóa phân biệt)"
            vtype = "Đếm số lượng (Count)"
            formula = "Số lượng từ khóa chuyên biệt khác nhau xuất hiện ít nhất 1 lần"
        elif c_lower.endswith("_score"):
            topic = col[:-6]
            desc = f"Tần suất chuẩn hóa (Normalized Disclosure Score) cho {topic}"
            vtype = "Chỉ số liên tục (Continuous Index)"
            formula = "(Tổng tần suất từ khóa / Tổng số từ) * 10,000"
        elif c_lower.endswith("_intensity"):
            topic = col[:-10]
            desc = f"Cường độ công bố thông tin (Log Intensity) về {topic}"
            vtype = "Biến Logarit (Continuous Log)"
            formula = "ln(1 + frequency)"
        elif c_lower.endswith("_has_mention"):
            topic = col[:-12]
            desc = f"Biến giả nhận diện công bố thông tin về {topic}"
            vtype = "Biến giả (Dummy 0/1)"
            formula = "1 nếu frequency > 0, ngược lại bằng 0"
        elif c_lower.endswith("_adoption"):
            topic = col[:-9]
            desc = f"Mức độ áp dụng thực tế (Action-Oriented Adoption) về {topic}"
            vtype = "Biến giả (Dummy 0/1)"
            formula = "1 nếu có từ khóa hành động/thực thi, ngược lại bằng 0"
        elif "_freq" in c_lower:
            desc = f"Tần suất từ khóa theo nhóm danh mục {col}"
            vtype = "Đếm số lần (Count)"
            formula = "Số lần xuất hiện từ khóa trong nhóm"
        elif "_div" in c_lower:
            desc = f"Độ phong phú từ khóa theo nhóm danh mục {col}"
            vtype = "Đếm số lượng (Count)"
            formula = "Số từ khóa phân biệt trong nhóm"
        elif "_score" in c_lower:
            desc = f"Tần suất chuẩn hóa theo nhóm danh mục {col}"
            vtype = "Chỉ số liên tục"
            formula = "(Tần suất từ khóa nhóm / Tổng số từ) * 10,000"
        elif c_lower == "roa":
            desc = "Tỷ suất sinh lời trên tổng tài sản (Return on Assets)"
            vtype = "Tỷ số tài chính (Financial Ratio)"
            formula = "Lợi nhuận sau thuế / Tổng tài sản"
        elif c_lower == "roe":
            desc = "Tỷ suất sinh lời trên vốn chủ sở hữu (Return on Equity)"
            vtype = "Tỷ số tài chính (Financial Ratio)"
            formula = "Lợi nhuận sau thuế / Vốn chủ sở hữu"
        elif c_lower == "size":
            desc = "Quy mô doanh nghiệp (Firm Size)"
            vtype = "Biến kiểm soát (Control Variable)"
            formula = "ln(Tổng tài sản)"
        elif c_lower == "leverage":
            desc = "Hệ số đòn bẩy tài chính (Financial Leverage)"
            vtype = "Biến kiểm soát (Control Variable)"
            formula = "Nợ phải trả / Tổng tài sản"
        elif c_lower == "gross_margin":
            desc = "Biên lợi nhuận gộp (Gross Profit Margin)"
            vtype = "Tỷ số tài chính (Financial Ratio)"
            formula = "Lợi nhuận gộp / Doanh thu thuần"
        elif c_lower == "net_margin":
            desc = "Biên lợi nhuận ròng (Net Profit Margin)"
            vtype = "Tỷ số tài chính (Financial Ratio)"
            formula = "Lợi nhuận sau thuế / Doanh thu thuần"
        elif c_lower == "ebit_margin":
            desc = "Biên EBIT (EBIT Margin)"
            vtype = "Tỷ số tài chính (Financial Ratio)"
            formula = "EBIT / Doanh thu thuần"
        elif c_lower == "current_ratio":
            desc = "Hệ số thanh toán hiện hành (Current Ratio)"
            vtype = "Tỷ số tài chính (Financial Ratio)"
            formula = "Tài sản ngắn hạn / Nợ ngắn hạn"
        elif c_lower == "quick_ratio":
            desc = "Hệ số thanh toán nhanh (Quick Ratio)"
            vtype = "Tỷ số tài chính (Financial Ratio)"
            formula = "(Tài sản ngắn hạn - Hàng tồn kho) / Nợ ngắn hạn"
        elif c_lower == "debt_to_equity":
            desc = "Tỷ số nợ trên vốn chủ sở hữu (Debt-to-Equity D/E)"
            vtype = "Tỷ số tài chính (Financial Ratio)"
            formula = "Nợ phải trả / Vốn chủ sở hữu"
        elif c_lower == "equity_multiplier":
            desc = "Đòn bẩy vốn chủ sở hữu (Equity Multiplier)"
            vtype = "Tỷ số tài chính (Financial Ratio)"
            formula = "Tổng tài sản / Vốn chủ sở hữu"
        elif c_lower == "asset_turnover":
            desc = "Vòng quay tổng tài sản (Asset Turnover)"
            vtype = "Tỷ số tài chính (Financial Ratio)"
            formula = "Doanh thu thuần / Tổng tài sản"
        elif c_lower.startswith("bs_"):
            desc = f"Chỉ tiêu Bảng cân đối kế toán: {col}"
            vtype = "Chỉ tiêu kế toán (VNĐ)"
            formula = "Báo cáo tài chính từ vnfinancialdata"
        elif c_lower.startswith("is_"):
            desc = f"Chỉ tiêu Kết quả hoạt động kinh doanh: {col}"
            vtype = "Chỉ tiêu kế toán (VNĐ)"
            formula = "Báo cáo tài chính từ vnfinancialdata"
        elif c_lower.startswith("cf_"):
            desc = f"Chỉ tiêu Lưu chuyển tiền tệ: {col}"
            vtype = "Chỉ tiêu kế toán (VNĐ)"
            formula = "Báo cáo tài chính từ vnfinancialdata"
        else:
            desc = f"Biến nghiên cứu: {col}"
            vtype = "Biến số (Variable)"
            formula = "Trích xuất từ báo cáo"

        codebook.append({
            "Biến": col,
            "Phân loại": vtype,
            "Mô tả chi tiết": desc,
            "Công thức / Nguồn": formula,
        })
    return codebook


# =====================================================================
# ResearchOutputGenerator
# =====================================================================

class ResearchOutputGenerator:
    """Tự động sinh TOÀN BỘ output files chuẩn nghiên cứu định lượng."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

    def generate_all(self, panel_df: pd.DataFrame,
                     variable_info: Optional[List[Dict]] = None) -> Dict[str, Path]:
        outputs = {}

        if variable_info is None:
            variable_info = auto_generate_codebook(panel_df)

        # Panel data (Excel, CSV, Parquet, Stata)
        for fmt in ("excel", "csv", "parquet", "stata"):
            try:
                outputs[f"panel_{fmt}"] = self._export(panel_df, fmt, variable_info)
            except Exception as e:
                logger.warning(f"Failed exporting format {fmt}: {e}")

        # Descriptive statistics
        outputs["desc_stats"] = self._descriptive(panel_df)

        # Correlation matrix
        outputs["correlation"] = self._correlation(panel_df)

        # Variable codebook
        outputs["codebook"] = self._codebook(variable_info)

        # Summary
        outputs["report"] = self._report(panel_df, outputs)

        return outputs

    def _export(self, df: pd.DataFrame, fmt: str, variable_info=None) -> Path:
        if fmt == "excel":
            p = self.output_dir / "panel_data.xlsx"
            with pd.ExcelWriter(p, engine="openpyxl") as writer:
                # Sheet 1: Panel Data
                df.to_excel(writer, sheet_name="Panel_Data", index=False)

                # Sheet 2: Descriptive Statistics
                num = df.select_dtypes(include=["number"])
                if not num.empty:
                    desc = num.describe().T
                    desc["N"] = num.count()
                    desc["missing"] = num.isna().sum()
                    desc.index.name = "Variable"
                    cols_desc = [c for c in ["N", "mean", "std", "min", "25%", "50%", "75%", "max", "missing"] if c in desc.columns]
                    desc[cols_desc].round(4).to_excel(writer, sheet_name="Descriptive_Stats")

                    # Sheet 3: Correlation Matrix
                    skip_corr = {"year", "pages"}
                    cols = [c for c in num.columns if c not in skip_corr and not c.startswith(("year_", "ind_")) and num[c].std() > 0]
                    if len(cols) > 1:
                        corr = num[cols].corr().round(4)
                        corr.index.name = "Variable"
                        corr.to_excel(writer, sheet_name="Correlation")

                # Sheet 4: Variable Codebook
                if variable_info:
                    pd.DataFrame(variable_info).to_excel(writer, sheet_name="Codebook", index=False)

        elif fmt == "csv":
            p = self.output_dir / "panel_data.csv"
            df.to_csv(p, index=False, encoding="utf-8-sig")

        elif fmt == "parquet":
            p = self.output_dir / "panel_data.parquet"
            df.to_parquet(p, index=False, engine="pyarrow")

        elif fmt == "stata":
            p = self.output_dir / "panel_data.dta"
            sdf, labels = sanitize_stata_dataframe(df)
            try:
                sdf.to_stata(p, write_index=False, version=118, variable_labels=labels)
            except Exception as e:
                logger.warning(f"Stata export with labels failed ({e}), retrying without labels")
                sdf.to_stata(p, write_index=False, version=118)
        return p

    def _descriptive(self, df: pd.DataFrame) -> Path:
        p = self.output_dir / "descriptive_statistics.csv"
        num = df.select_dtypes(include=["number"])
        if num.empty:
            pd.DataFrame().to_csv(p, encoding="utf-8-sig")
            return p
        desc = num.describe().T
        desc["N"] = num.count()
        desc["missing"] = num.isna().sum()
        desc.index.name = "Variable"
        cols_desc = [c for c in ["N", "mean", "std", "min", "25%", "50%", "75%", "max", "missing"] if c in desc.columns]
        desc[cols_desc].round(4).to_csv(p, encoding="utf-8-sig")
        return p

    def _correlation(self, df: pd.DataFrame) -> Path:
        p = self.output_dir / "correlation_matrix.csv"
        num = df.select_dtypes(include=["number"])
        skip_corr = {"year", "pages"}
        cols = [c for c in num.columns if c not in skip_corr and not c.startswith(("year_", "ind_")) and num[c].std() > 0]
        if len(cols) > 1:
            corr = num[cols].corr().round(4)
            corr.index.name = "Variable"
            corr.to_csv(p, encoding="utf-8-sig")
        else:
            pd.DataFrame().to_csv(p, encoding="utf-8-sig")
        return p

    def _codebook(self, info: List[Dict]) -> Path:
        p = self.output_dir / "variable_codebook.csv"
        pd.DataFrame(info).to_csv(p, index=False, encoding="utf-8-sig")
        return p

    def _report(self, df: pd.DataFrame, outputs: Dict[str, Path]) -> Path:
        p = self.output_dir / "REPORT.md"
        n = len(df)
        firms = df["ticker"].nunique() if "ticker" in df.columns else "N/A"
        yrs = df["year"].nunique() if "year" in df.columns else "N/A"
        lines = [
            "# Research Output Report (Báo Cáo Tổng Hợp Kết Quả)", "",
            f"- Số quan sát (Observations): {n:,}",
            f"- Số doanh nghiệp (Firms): {firms}",
            f"- Số năm nghiên cứu (Years): {yrs}",
            f"- Tổng số biến (Variables): {len(df.columns)}", "",
            "## Danh Sách Tệp Kết Quả Đã Tạo (Output Files)", "",
        ]
        for name, path in outputs.items():
            if path and path.exists():
                sz = path.stat().st_size
                sz_str = f"{sz/1024/1024:.1f} MB" if sz > 1024*1024 else f"{sz/1024:.1f} KB"
                lines.append(f"- `{path.name}` ({sz_str})")
        p.write_text("\n".join(lines), encoding="utf-8")
        return p


# =====================================================================
# Helpers
# =====================================================================

def _find_col(headers: List[str], candidates: List[str]) -> Optional[str]:
    """Find matching column name from candidates."""
    for h in headers:
        for c in candidates:
            if h.strip().lower() == c.lower():
                return h
    return None


def _find_col_idx(headers: List[str], candidates: List[str]) -> Optional[int]:
    for i, h in enumerate(headers):
        for c in candidates:
            if h.strip().lower() == c.lower():
                return i
    return None
