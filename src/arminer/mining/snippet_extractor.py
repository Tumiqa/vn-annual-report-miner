# -*- coding: utf-8 -*-
"""
arminer.mining.snippet_extractor
=================================
Trích xuất đoạn ngữ cảnh xung quanh từ khóa.

Cung cấp 2 chế độ:
1. Character-based (±N ký tự) — nhanh, dùng cho DB insert
2. Sentence-boundary (±1 câu) — thông minh, dùng cho sheet Context trong Excel
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from loguru import logger

# ---------------------------------------------------------------------------
# Regex phân tách câu tiếng Việt (sentence splitter)
# ---------------------------------------------------------------------------
# Xử lý ngoại lệ:
#   - Viết tắt VN: TP.HCM, PGS.TS, GS.TS, ThS., CN., TS., Th.S, v.v.
#   - Số thập phân: 3.14, 12.5%, 1.000.000
#   - Viết tắt tiếng Anh phổ biến: Inc., Ltd., Corp., Co., No., vs., etc.

# Known abbreviations that end with a period but do NOT terminate a sentence
_ABBREVIATIONS = frozenset({
    "tp", "pgs", "gs", "ts", "ths", "cn", "th", "ks", "bs", "ds",
    "inc", "ltd", "corp", "co", "no", "vs", "etc", "dr", "mr", "mrs",
    "ms", "prof", "st", "jr", "sr", "tr", "q1", "q2", "q3", "q4",
})

# Forward-scanning regex: finds potential sentence-ending punctuation
# followed by whitespace (or end of string), OR paragraph breaks (\n\n+)
_CANDIDATE_SENTENCE_END_RE = re.compile(
    r"[.!?](?:\s|$)"    # Period, ?, ! followed by space or end
    r"|"
    r"\n\s*\n",          # Paragraph break (double newline)
    re.UNICODE
)

# Phát hiện vùng bảng: dòng chứa ≥2 tab hoặc ≥3 chuỗi số cách nhau bởi whitespace
_TABLE_LINE_RE = re.compile(
    r"(?:\t.*\t)"                          # ≥2 tab trên cùng dòng
    r"|"
    r"(?:[\d,.]+\s+[\d,.]+\s+[\d,.]+)",    # ≥3 nhóm số liên tiếp
    re.UNICODE
)

# Giới hạn tối đa ký tự context để tránh cell Excel quá lớn
_MAX_CONTEXT_CHARS = 800


class SnippetExtractor:
    """Cắt cửa sổ ngữ cảnh xung quanh từ khóa tìm thấy."""

    def __init__(self, context_chars: int = 500):
        self.context_chars = context_chars

    # =========================================================================
    # Mode 1: Character-based snippet (legacy, nhanh)
    # =========================================================================

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

    # =========================================================================
    # Mode 2: Sentence-boundary context (thông minh, cho Excel sheet Context)
    # =========================================================================

    @staticmethod
    def _split_sentences(text: str) -> List[Tuple[int, int]]:
        """
        Phân tách text thành danh sách (start, end) của từng câu.

        Sử dụng forward-scanning regex + post-validation:
        - Tìm tất cả vị trí dấu chấm câu / xuống dòng đôi
        - Loại bỏ false positives: viết tắt (TP.HCM, PGS.TS), số thập phân (3.14)
        """
        if not text:
            return []

        boundaries: List[int] = [0]

        for m in _CANDIDATE_SENTENCE_END_RE.finditer(text):
            match_start = m.start()
            match_char = text[match_start]

            # Paragraph break (\n\n) — always a true sentence boundary
            if match_char == "\n":
                end_pos = m.end()
                if end_pos < len(text):
                    boundaries.append(end_pos)
                continue

            # Period — validate it's not abbreviation or decimal
            if match_char == ".":
                # Check if preceded by a digit (decimal: 3.14, 1.000)
                if match_start > 0 and text[match_start - 1].isdigit():
                    continue

                # Check if preceded by a known abbreviation
                # Extract the word before the period
                word_start = match_start - 1
                while word_start >= 0 and (text[word_start].isalpha() or text[word_start].isdigit()):
                    word_start -= 1
                word_before = text[word_start + 1:match_start].lower()
                if word_before in _ABBREVIATIONS:
                    continue

            # Valid sentence boundary
            end_pos = m.end()
            if end_pos < len(text):
                boundaries.append(end_pos)

        boundaries.append(len(text))

        sentences: List[Tuple[int, int]] = []
        for i in range(len(boundaries) - 1):
            s, e = boundaries[i], boundaries[i + 1]
            # Bỏ qua "câu" chỉ toàn khoảng trắng
            if text[s:e].strip():
                sentences.append((s, e))

        return sentences

    @staticmethod
    def _is_table_region(text: str, position: int) -> bool:
        """
        Phát hiện vị trí nằm trong vùng bảng biểu.

        Dấu hiệu: dòng chứa từ khóa có ≥2 tab hoặc ≥3 cụm số liên tiếp.
        """
        # Tìm dòng chứa position
        line_start = text.rfind("\n", 0, position)
        line_start = line_start + 1 if line_start != -1 else 0
        line_end = text.find("\n", position)
        if line_end == -1:
            line_end = len(text)

        line = text[line_start:line_end]
        return bool(_TABLE_LINE_RE.search(line))

    def extract_sentence_context(self, text: str, position: int,
                                 keyword_length: int) -> str:
        """
        Trích xuất ngữ cảnh thông minh: câu chứa từ khóa ± 1 câu lân cận.

        Nếu từ khóa nằm trong vùng bảng biểu → lấy dòng chứa từ khóa ± 1 dòng.
        Kết quả luôn kết thúc tại ranh giới câu, tối đa _MAX_CONTEXT_CHARS ký tự.
        """
        text_len = len(text)
        if not text or position >= text_len:
            return ""

        # --- Trường hợp bảng biểu ---
        if self._is_table_region(text, position):
            return self._extract_table_context(text, position, keyword_length)

        # --- Trường hợp văn xuôi: tìm câu chứa từ khóa ---
        sentences = self._split_sentences(text)
        if not sentences:
            # Fallback: character-based
            return self.extract_snippet(text, position, keyword_length)

        # Tìm index câu chứa position
        target_idx = 0
        for i, (s, e) in enumerate(sentences):
            if s <= position < e:
                target_idx = i
                break
        else:
            # Position nằm ngoài tất cả câu → lấy câu gần nhất
            target_idx = len(sentences) - 1

        # Lấy ±1 câu lân cận
        start_idx = max(0, target_idx - 1)
        end_idx = min(len(sentences) - 1, target_idx + 1)

        context_start = sentences[start_idx][0]
        context_end = sentences[end_idx][1]

        context = text[context_start:context_end].strip()

        # Nếu quá dài, thu hẹp: chỉ lấy câu chứa từ khóa
        if len(context) > _MAX_CONTEXT_CHARS:
            context = text[sentences[target_idx][0]:sentences[target_idx][1]].strip()

        # Nếu vẫn quá dài (câu siêu dài), cắt tại _MAX_CONTEXT_CHARS, tìm ranh giới từ
        if len(context) > _MAX_CONTEXT_CHARS:
            kw_offset = position - sentences[target_idx][0]
            half = _MAX_CONTEXT_CHARS // 2
            clip_start = max(0, kw_offset - half)
            clip_end = min(len(context), kw_offset + keyword_length + half)
            context = context[clip_start:clip_end].strip()

        # Chuẩn hóa khoảng trắng thừa
        context = re.sub(r"[ \t]+", " ", context)
        context = re.sub(r"\n{3,}", "\n\n", context)

        # Thêm dấu ... nếu cắt
        if context_start > 0:
            context = "..." + context
        if context_end < text_len:
            context = context + "..."

        return context.strip()

    def _extract_table_context(self, text: str, position: int,
                               keyword_length: int) -> str:
        """Trích xuất ngữ cảnh cho vùng bảng biểu: dòng chứa từ khóa ± 1 dòng."""
        lines = text.split("\n")
        if not lines:
            return ""

        # Tìm dòng chứa position
        char_count = 0
        target_line_idx = 0
        for i, line in enumerate(lines):
            line_end = char_count + len(line)
            if char_count <= position <= line_end:
                target_line_idx = i
                break
            char_count = line_end + 1  # +1 for \n
        else:
            target_line_idx = len(lines) - 1

        # Lấy ±1 dòng
        start_line = max(0, target_line_idx - 1)
        end_line = min(len(lines) - 1, target_line_idx + 1)

        context_lines = lines[start_line:end_line + 1]
        context = "\n".join(l for l in context_lines if l.strip())

        # Chuẩn hóa
        context = re.sub(r"[ \t]+", " ", context)
        if len(context) > _MAX_CONTEXT_CHARS:
            context = context[:_MAX_CONTEXT_CHARS].rsplit(" ", 1)[0]

        if start_line > 0:
            context = "..." + context
        if end_line < len(lines) - 1:
            context = context + "..."

        return context.strip()

    def extract_all_with_context(self, text: str, matches: List[Dict],
                                 ticker: str = "",
                                 year: Optional[int] = None) -> List[Dict]:
        """
        Trích xuất sentence-boundary context cho TẤT CẢ matches.

        Dùng cho sheet Context trong Excel export.

        Returns:
            List[Dict] với cấu trúc chuẩn cho DataFrame:
            [{"Firm", "Year", "Keyword", "Canonical", "Category",
              "Match_Type", "Similarity", "Sentence_Context"}, ...]
        """
        results: List[Dict] = []

        for i, match in enumerate(matches, start=1):
            position = match.get("position", 0)
            kw_found = match.get("keyword_found", "")
            kw_canonical = match.get("keyword_canonical", kw_found)

            sentence_ctx = self.extract_sentence_context(
                text, position, len(kw_found)
            )

            results.append({
                "STT": i,
                "Firm": ticker,
                "Year": year,
                "Keyword": kw_found,
                "Canonical": kw_canonical,
                "Category": match.get("category", "unknown"),
                "Match_Type": match.get("match_type", "exact"),
                "Similarity": match.get("similarity", 100.0),
                "Sentence_Context": sentence_ctx,
            })

        logger.debug(
            f"Extracted {len(results)} sentence-boundary contexts "
            f"for {ticker}/{year}"
        )
        return results

    # =========================================================================
    # Merge overlapping (giữ nguyên)
    # =========================================================================

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
