# -*- coding: utf-8 -*-
"""
arminer.mining.metrics
=======================
Tính toán các chỉ số đo lường text mining cấp DN-năm.
Generic — hoạt động với bất kỳ Dictionary nào.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from loguru import logger


class MetricsCalculator:
    """
    Tính toán biến nghiên cứu từ kết quả matching.

    Các biến cơ bản:
    - frequency: Tổng tần suất
    - diversity: Số từ khóa khác nhau
    - normalized_score: (frequency / total_words) × normalization_factor
    """

    def __init__(self, normalization_factor: int = 10_000):
        self.normalization_factor = normalization_factor

    def calculate(self, matches: List[Dict], total_words: int,
                  categories: Optional[List[str]] = None) -> Dict:
        """
        Tính toán metrics từ kết quả matching.

        Args:
            matches: List[Dict] từ GenericFuzzyMatcher.search()
            total_words: Tổng số từ trong văn bản
            categories: Lọc theo nhóm (None = tất cả)

        Returns:
            Dict chứa frequency, diversity, normalized_score,
            keyword_frequencies, by_category
        """
        # Filter theo categories nếu cần
        if categories:
            matches = [m for m in matches if m.get("category") in categories]

        if not matches:
            return {
                "frequency": 0,
                "diversity": 0,
                "normalized_score": 0.0,
                "keyword_frequencies": {},
                "by_category": {},
            }

        # 1. Frequency
        frequency = len(matches)

        # 2. Diversity (canonical form)
        unique_keywords: set = set()
        keyword_freq: Dict[str, int] = {}
        for m in matches:
            canonical = m.get("keyword_canonical", m.get("keyword_found"))
            unique_keywords.add(canonical)
            keyword_freq[canonical] = keyword_freq.get(canonical, 0) + 1

        diversity = len(unique_keywords)

        # 3. Normalized Score
        normalized_score = 0.0
        if total_words > 0:
            normalized_score = (frequency / total_words) * self.normalization_factor

        # 4. By category
        by_category: Dict[str, Dict] = {}
        for m in matches:
            cat = m.get("category", "unknown")
            if cat not in by_category:
                by_category[cat] = {"frequency": 0, "unique_keywords": set()}
            by_category[cat]["frequency"] += 1
            by_category[cat]["unique_keywords"].add(
                m.get("keyword_canonical", m.get("keyword_found"))
            )

        # Convert sets to counts
        for cat_data in by_category.values():
            cat_data["diversity"] = len(cat_data["unique_keywords"])
            del cat_data["unique_keywords"]

        return {
            "frequency": frequency,
            "diversity": diversity,
            "normalized_score": round(normalized_score, 6),
            "keyword_frequencies": dict(
                sorted(keyword_freq.items(), key=lambda x: x[1], reverse=True)
            ),
            "by_category": by_category,
        }

    def calculate_per_category(self, matches: List[Dict], total_words: int,
                               category_names: List[str]) -> Dict[str, Dict]:
        """
        Tính metrics riêng cho từng category.

        Returns:
            {"environment": {"frequency": 5, ...}, "social": {"frequency": 3, ...}}
        """
        result: Dict[str, Dict] = {}
        for cat in category_names:
            result[cat] = self.calculate(matches, total_words, categories=[cat])
        return result
