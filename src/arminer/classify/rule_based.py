# -*- coding: utf-8 -*-
"""
arminer.classify.rule_based
==============================
Generic rule-based classifier dựa trên từ điển YAML.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from loguru import logger


class RuleBasedClassifier:
    """
    Phân loại văn bản dựa trên rules từ Dictionary.

    Ví dụ: Blockchain Adoption vs Talk
    - Adoption: có trigger keywords (triển khai, ứng dụng...)
    - Talk: mặc định nếu không match adoption
    """

    def __init__(self, classification_rules: Dict):
        self.rules = classification_rules

    def classify(self, matches: List[Dict],
                 text: str = "") -> Dict[str, any]:
        """
        Phân loại dựa trên matches và text.

        Returns:
            {"label": "adoption", "confidence": 0.85, "triggers_found": [...]}
        """
        if not matches:
            return {"label": "none", "confidence": 1.0, "triggers_found": []}

        text_lower = text.lower()
        results: Dict[str, Dict] = {}

        for rule_name, rule_config in self.rules.items():
            trigger_keywords = [
                k.lower() for k in rule_config.get("trigger_keywords", [])
            ]

            if not trigger_keywords:
                continue

            triggers_found = []

            # Check in match contexts
            for m in matches:
                context = m.get("context_text", "").lower()
                kw_found = m.get("keyword_found", "").lower()

                for trigger in trigger_keywords:
                    if trigger in context or trigger in kw_found:
                        triggers_found.append(trigger)

            # Check in full text
            for trigger in trigger_keywords:
                if trigger in text_lower and trigger not in triggers_found:
                    triggers_found.append(trigger)

            triggers_found = list(set(triggers_found))

            results[rule_name] = {
                "triggers_found": triggers_found,
                "trigger_count": len(triggers_found),
                "matched": len(triggers_found) > 0,
            }

        # Determine best label
        best_label = "talk"  # default
        best_count = 0
        all_triggers = []

        for rule_name, result in results.items():
            if result["matched"] and result["trigger_count"] > best_count:
                best_label = rule_name
                best_count = result["trigger_count"]
                all_triggers = result["triggers_found"]

        confidence = min(1.0, best_count / 3) if best_count > 0 else 0.5

        return {
            "label": best_label,
            "label_binary": 1 if best_label != "talk" and best_label != "none" else 0,
            "confidence": round(confidence, 2),
            "triggers_found": all_triggers,
            "all_rules": results,
        }
