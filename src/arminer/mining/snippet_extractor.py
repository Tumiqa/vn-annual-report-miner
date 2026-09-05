# -*- coding: utf-8 -*-
"""
arminer.mining.snippet_extractor
=================================
Trích xuất đoạn ngữ cảnh ±N ký tự xung quanh từ khóa.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from loguru import logger


class SnippetExtractor:
    """Cắt cửa sổ ngữ cảnh xung quanh từ khóa tìm thấy."""

    def __init__(self, context_chars: int = 500):
        self.context_chars = context_chars

    def extract_snippet(self, text: str, position: int,
                        keyword_length: int) -> str:
        """Cắt 1 snippet ±context_chars."""
        start = max(0, position - self.context_chars)
        end = min(len(text), position + keyword_length + self.context_chars)

        snippet = text[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."

        return snippet.strip()

    def extract_all(self, text: str, matches: List[Dict],
                    report_id: Optional[int] = None) -> List[Dict]:
        """
        Trích xuất snippets cho tất cả matches.

        Returns:
            List[Dict] sẵn sàng insert vào DB
        """
        snippets: List[Dict] = []

        for match in matches:
            position = match.get("position", 0)
            kw_found = match.get("keyword_found", "")
            kw_canonical = match.get("keyword_canonical", kw_found)
            category = match.get("category", "unknown")

            context = self.extract_snippet(text, position, len(kw_found))

            snippets.append({
                "report_id": report_id,
                "keyword_found": kw_found,
                "keyword_canonical": kw_canonical,
                "category": category,
                "match_type": match.get("match_type", "exact"),
                "levenshtein_distance": match.get("levenshtein_distance", 0),
                "similarity_score": match.get("similarity", 100.0),
                "context_text": context,
                "position_in_text": position,
            })

        logger.debug(f"Extracted {len(snippets)} snippets (±{self.context_chars} chars)")
        return snippets

    def merge_overlapping(self, snippets: List[Dict],
                          overlap_threshold: int = 200) -> List[Dict]:
        """Gộp snippets chồng lấn, giữ similarity cao nhất."""
        if not snippets:
            return snippets

        sorted_snips = sorted(snippets, key=lambda x: x.get("position_in_text", 0))
        merged = [sorted_snips[0]]

        for current in sorted_snips[1:]:
            last = merged[-1]
            last_end = (
                last.get("position_in_text", 0)
                + len(last.get("keyword_found", ""))
                + self.context_chars
            )
            current_start = current.get("position_in_text", 0) - self.context_chars

            if current_start < last_end - overlap_threshold:
                if current.get("similarity_score", 0) > last.get("similarity_score", 0):
                    merged[-1] = current
            else:
                merged.append(current)

        return merged
