# -*- coding: utf-8 -*-
"""
arminer.mining.variable_builder
=================================
⭐ Tạo biến nghiên cứu tùy chỉnh dựa trên cấu hình YAML.

Đây là core feature cho phép nhà nghiên cứu tự tạo biến
CHỈ BẰNG cấu hình, không viết code.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from loguru import logger

from arminer.core.config import VariableDefinition
from arminer.mining.metrics import MetricsCalculator


class VariableBuilder:
    """
    Tạo biến nghiên cứu từ kết quả text mining theo cấu hình.

    Ví dụ cấu hình:
        variables:
          - name: "esg_score"
            type: "normalized_score"
            categories: ["environment", "social", "governance"]
          - name: "has_adoption"
            type: "classification"
            rule: "adoption"
    """

    def __init__(self, variable_defs: List[VariableDefinition]):
        self.variable_defs = variable_defs
        self._calculator = MetricsCalculator()

    def build(self, matches: List[Dict], total_words: int,
              classification_rules: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Tính tất cả biến đã định nghĩa.

        Args:
            matches: Kết quả từ GenericFuzzyMatcher.search()
            total_words: Tổng số từ trong báo cáo
            classification_rules: Rules từ Dictionary

        Returns:
            {"esg_score": 12.5, "has_adoption": 1, ...}
        """
        variables: Dict[str, Any] = {}

        for var_def in self.variable_defs:
            try:
                value = self._compute_variable(
                    var_def, matches, total_words, classification_rules
                )
                variables[var_def.name] = value
            except Exception as e:
                logger.warning(f"Error computing variable '{var_def.name}': {e}")
                variables[var_def.name] = None

        return variables

    def _compute_variable(
        self,
        var_def: VariableDefinition,
        matches: List[Dict],
        total_words: int,
        classification_rules: Optional[Dict],
    ) -> Any:
        """Tính 1 biến dựa trên type."""

        # Filter matches theo categories nếu có
        filtered = matches
        if var_def.categories:
            filtered = [
                m for m in matches
                if m.get("category") in var_def.categories
            ]

        if var_def.type == "frequency":
            return len(filtered)

        elif var_def.type == "diversity":
            return len(set(
                m.get("keyword_canonical", m.get("keyword_found"))
                for m in filtered
            ))

        elif var_def.type == "normalized_score":
            if total_words <= 0:
                return 0.0
            freq = len(filtered)
            return round(
                (freq / total_words) * var_def.normalization, 6
            )

        elif var_def.type == "classification":
            return self._classify(
                filtered, var_def.rule, classification_rules
            )

        elif var_def.type == "financial_ratio":
            # Financial ratios xử lý ở PanelBuilder
            return None

        elif var_def.type == "custom":
            # Custom formula — tương lai mở rộng
            return None

        else:
            logger.warning(f"Unknown variable type: {var_def.type}")
            return None

    def _classify(
        self,
        matches: List[Dict],
        rule_name: Optional[str],
        classification_rules: Optional[Dict],
    ) -> int:
        """Phân loại 0/1 dựa trên trigger keywords."""
        if not rule_name or not classification_rules:
            return 0

        rule = classification_rules.get(rule_name, {})
        trigger_keywords = [k.lower() for k in rule.get("trigger_keywords", [])]

        if not trigger_keywords:
            return 0

        # Kiểm tra snippets có chứa trigger keywords không
        for m in matches:
            context = m.get("context_text", "").lower() if "context_text" in m else ""
            keyword_found = m.get("keyword_found", "").lower()

            # Kiểm tra trong keyword_found hoặc context_text
            for trigger in trigger_keywords:
                if trigger in keyword_found or trigger in context:
                    return 1

        return 0

    def get_variable_names(self) -> List[str]:
        """Danh sách tên biến đã định nghĩa."""
        return [v.name for v in self.variable_defs]

    def get_text_mining_variables(self) -> List[VariableDefinition]:
        """Chỉ lấy các biến text mining (không phải financial)."""
        return [
            v for v in self.variable_defs
            if v.type != "financial_ratio"
        ]

    def get_financial_variables(self) -> List[VariableDefinition]:
        """Chỉ lấy các biến financial ratio."""
        return [
            v for v in self.variable_defs
            if v.type == "financial_ratio"
        ]
