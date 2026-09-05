# -*- coding: utf-8 -*-
"""
arminer.core.dictionary
========================
Generic Dictionary Loader — Trái tim của thư viện.

Cho phép người dùng định nghĩa bộ từ khóa cho BẤT KỲ chủ đề nghiên cứu nào
thông qua file YAML/JSON/CSV đơn giản, thay vì hardcode trong Python.

Usage::

    # Load từ YAML
    d = Dictionary.from_yaml("my_dictionary.yaml")

    # Hoặc tạo inline
    d = Dictionary(name="ESG")
    d.add_category("environment", keywords=[
        {"keyword": "carbon emission", "variants": "khí thải carbon"},
    ])

    # Sử dụng
    keywords = d.get_flat_list()
    mapping = d.get_canonical_map()
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml
from loguru import logger


class KeywordEntry:
    """Đại diện cho 1 từ khóa trong từ điển."""

    __slots__ = (
        "keyword", "variants", "language", "weight",
        "is_ambiguous", "ambiguity_note", "category",
    )

    def __init__(
        self,
        keyword: str,
        variants: Optional[str] = None,
        language: str = "en",
        weight: float = 1.0,
        is_ambiguous: bool = False,
        ambiguity_note: Optional[str] = None,
        category: Optional[str] = None,
    ):
        self.keyword = keyword.strip().lower()
        self.variants = variants
        self.language = language
        self.weight = weight
        self.is_ambiguous = is_ambiguous
        self.ambiguity_note = ambiguity_note
        self.category = category

    @property
    def all_forms(self) -> List[str]:
        """Trả về keyword + tất cả biến thể."""
        forms = [self.keyword]
        if self.variants:
            if isinstance(self.variants, str):
                var_list = self.variants.split("|")
            elif isinstance(self.variants, (list, tuple, set)):
                var_list = list(self.variants)
            else:
                var_list = [str(self.variants)]

            for v in var_list:
                v = str(v).strip().lower()
                if v and v not in forms:
                    forms.append(v)
        return forms

    def __repr__(self) -> str:
        return f"KeywordEntry({self.keyword!r}, cat={self.category!r})"


class Category:
    """Đại diện cho 1 nhóm từ khóa (ví dụ: environment, social, governance)."""

    def __init__(self, name: str, display_name: Optional[str] = None):
        self.name = name
        self.display_name = display_name or name.replace("_", " ").title()
        self.keywords: List[KeywordEntry] = []

    def add_keyword(self, entry: KeywordEntry) -> None:
        entry.category = self.name
        self.keywords.append(entry)

    def __len__(self) -> int:
        return len(self.keywords)

    def __repr__(self) -> str:
        return f"Category({self.name!r}, {len(self.keywords)} keywords)"


class Dictionary:
    """
    Generic Dictionary — Tải và quản lý bộ từ khóa cho nghiên cứu.

    Hỗ trợ: YAML, JSON, CSV, hoặc tạo inline bằng Python.
    """

    def __init__(self, name: str = "Untitled", version: str = "1.0",
                 description: str = ""):
        self.name = name
        self.version = version
        self.description = description
        self.categories: Dict[str, Category] = {}
        self.exclusions: List[Dict[str, str]] = []
        self.classification_rules: Dict[str, Dict] = {}

    # =========================================================================
    # Factory Methods
    # =========================================================================

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Dictionary":
        """Tải từ điển từ file YAML."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Không tìm thấy file từ điển: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        d = cls(
            name=data.get("name", path.stem),
            version=data.get("version", "1.0"),
            description=data.get("description", ""),
        )

        # Parse categories
        for cat_name, cat_data in data.get("categories", {}).items():
            display = cat_data.get("display_name", cat_name)
            category = Category(name=cat_name, display_name=display)

            for kw_data in cat_data.get("keywords", []):
                entry = KeywordEntry(
                    keyword=kw_data["keyword"],
                    variants=kw_data.get("variants"),
                    language=kw_data.get("language", "en"),
                    weight=kw_data.get("weight", 1.0),
                    is_ambiguous=kw_data.get("is_ambiguous", False),
                    ambiguity_note=kw_data.get("ambiguity_note"),
                )
                category.add_keyword(entry)

            d.categories[cat_name] = category

        # Parse exclusions
        d.exclusions = data.get("exclusions", [])

        # Parse classification rules
        d.classification_rules = data.get("classification_rules", {})

        logger.info(
            f"Loaded dictionary '{d.name}' v{d.version}: "
            f"{d.total_keywords} keywords in {len(d.categories)} categories"
        )
        return d

    @classmethod
    def from_json(cls, path: str | Path) -> "Dictionary":
        """Tải từ điển từ file JSON (cùng schema với YAML)."""
        path = Path(path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Reuse YAML parser (cùng schema)
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as tmp:
            yaml.dump(data, tmp, allow_unicode=True)
            tmp_path = tmp.name

        try:
            return cls.from_yaml(tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @classmethod
    def from_csv(cls, path: str | Path, name: str = "CSV Dictionary",
                 category_col: str = "category",
                 keyword_col: str = "keyword",
                 variants_col: str = "variants") -> "Dictionary":
        """
        Tải từ điển từ file CSV.

        CSV phải có ít nhất cột `keyword`. Các cột tùy chọn:
        category, variants, language, weight, is_ambiguous
        """
        path = Path(path)
        d = cls(name=name)

        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cat_name = row.get(category_col, "default").strip().lower()
                if cat_name not in d.categories:
                    d.categories[cat_name] = Category(name=cat_name)

                entry = KeywordEntry(
                    keyword=row[keyword_col],
                    variants=row.get(variants_col),
                    language=row.get("language", "en"),
                    weight=float(row.get("weight", 1.0)),
                    is_ambiguous=row.get("is_ambiguous", "").lower() in ("true", "1", "yes"),
                    ambiguity_note=row.get("ambiguity_note"),
                )
                d.categories[cat_name].add_keyword(entry)

        logger.info(f"Loaded CSV dictionary: {d.total_keywords} keywords")
        return d

    # =========================================================================
    # Inline API
    # =========================================================================

    def add_category(self, name: str, display_name: Optional[str] = None,
                     keywords: Optional[List[Dict]] = None) -> Category:
        """Thêm một category mới (hoặc lấy existing)."""
        if name not in self.categories:
            self.categories[name] = Category(name=name, display_name=display_name)
        cat = self.categories[name]

        if keywords:
            for kw_data in keywords:
                entry = KeywordEntry(
                    keyword=kw_data["keyword"],
                    variants=kw_data.get("variants"),
                    language=kw_data.get("language", "en"),
                    weight=kw_data.get("weight", 1.0),
                    is_ambiguous=kw_data.get("is_ambiguous", False),
                )
                cat.add_keyword(entry)

        return cat

    # =========================================================================
    # Query API
    # =========================================================================

    @property
    def total_keywords(self) -> int:
        """Tổng số từ khóa chính (không tính biến thể)."""
        return sum(len(cat) for cat in self.categories.values())

    def get_flat_list(self, include_variants: bool = True,
                      include_ambiguous: bool = False,
                      categories: Optional[List[str]] = None) -> List[str]:
        """
        Trả về danh sách phẳng tất cả từ khóa + biến thể.

        Args:
            include_variants: Có bao gồm biến thể viết không
            include_ambiguous: Có bao gồm từ khóa đa nghĩa không
            categories: Lọc theo nhóm (None = tất cả)

        Returns:
            Danh sách strings lowercase, đã loại trùng, sắp xếp
        """
        excluded = {e["keyword"].lower() for e in self.exclusions}
        result: Set[str] = set()

        for cat_name, cat in self.categories.items():
            if categories and cat_name not in categories:
                continue

            for entry in cat.keywords:
                if entry.is_ambiguous and not include_ambiguous:
                    continue
                if entry.keyword in excluded:
                    continue

                result.add(entry.keyword)
                if include_variants:
                    for form in entry.all_forms:
                        if form not in excluded:
                            result.add(form)

        return sorted(result)

    def get_canonical_map(self, include_ambiguous: bool = False,
                          categories: Optional[List[str]] = None) -> Dict[str, str]:
        """
        Mapping: mọi biến thể → từ khóa chính (canonical form).

        Ví dụ: {"block chain": "blockchain", "block-chain": "blockchain"}
        """
        excluded = {e["keyword"].lower() for e in self.exclusions}
        mapping: Dict[str, str] = {}

        for cat_name, cat in self.categories.items():
            if categories and cat_name not in categories:
                continue

            for entry in cat.keywords:
                if entry.is_ambiguous and not include_ambiguous:
                    continue
                if entry.keyword in excluded:
                    continue

                for form in entry.all_forms:
                    if form not in excluded:
                        mapping[form] = entry.keyword

        return mapping

    def get_category_map(self) -> Dict[str, str]:
        """Mapping: từ khóa chính → category name."""
        result: Dict[str, str] = {}
        for cat_name, cat in self.categories.items():
            for entry in cat.keywords:
                result[entry.keyword] = cat_name
        return result

    def get_keywords_by_category(self, category: str,
                                 include_variants: bool = True) -> List[str]:
        """Lấy tất cả keywords cho 1 category."""
        return self.get_flat_list(
            include_variants=include_variants,
            categories=[category],
        )

    def get_classification_trigger_keywords(self, rule_name: str) -> List[str]:
        """Lấy trigger keywords cho 1 classification rule."""
        rule = self.classification_rules.get(rule_name, {})
        return [k.lower() for k in rule.get("trigger_keywords", [])]

    # =========================================================================
    # Statistics
    # =========================================================================

    def stats(self) -> Dict[str, Any]:
        """Thống kê tổng quan về từ điển."""
        flat_all = self.get_flat_list(include_variants=True, include_ambiguous=True)
        flat_active = self.get_flat_list(include_variants=True, include_ambiguous=False)
        ambiguous_count = sum(
            1 for cat in self.categories.values()
            for entry in cat.keywords
            if entry.is_ambiguous
        )
        lang_counts: Dict[str, int] = {}
        for cat in self.categories.values():
            for entry in cat.keywords:
                lang_counts[entry.language] = lang_counts.get(entry.language, 0) + 1

        return {
            "name": self.name,
            "version": self.version,
            "total_keywords": self.total_keywords,
            "total_with_variants": len(flat_all),
            "active_keywords": len(flat_active),
            "ambiguous_count": ambiguous_count,
            "exclusions": len(self.exclusions),
            "categories": {
                name: len(cat) for name, cat in self.categories.items()
            },
            "languages": lang_counts,
            "classification_rules": list(self.classification_rules.keys()),
        }

    def __repr__(self) -> str:
        return (
            f"Dictionary(name={self.name!r}, "
            f"categories={len(self.categories)}, "
            f"keywords={self.total_keywords})"
        )
