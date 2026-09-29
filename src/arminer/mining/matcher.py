# -*- coding: utf-8 -*-
"""
arminer.mining.matcher
=======================
Generic Fuzzy Matcher — Tìm kiếm từ khóa trong văn bản OCR.

Kế thừa thuật toán đã tối ưu 20x-50x từ blockchain_pipeline:
- Exact match → sliding window trên tập n-gram duy nhất (unique)
- Fuzzy match → Levenshtein trên n-gram theo nhóm độ dài
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional, Set, Tuple

from Levenshtein import distance as lev_distance, ratio as lev_ratio
from loguru import logger

from arminer.core.dictionary import Dictionary


# Danh sách từ vựng thông dụng (tiếng Anh & tiếng Việt) tuyệt đối không được match nhầm dạng fuzzy
# với thuật ngữ chuyên sâu (ví dụ: together vs tether, finance vs binance, bảo đảm vs tiền ảo).
COMMON_GENERAL_WORDS = {
    # English common stopwords and business terms
    "together", "whether", "weather", "gather", "gathering", "another", "brother",
    "mother", "father", "other", "rather", "further", "either", "neither",
    "leather", "nether", "bother", "finance", "financial", "general", "company",
    "annual", "report", "market", "meeting", "system", "service", "management",
    "operation", "business", "statement", "audited", "executive", "director",
    "shareholder", "capital", "revenue", "profit", "investment", "growth",
    "overview", "quarter", "forward", "between", "through", "without",
    # Vietnamese common words and administrative/financial phrases
    "bảo đảm", "dòng tiền", "tiền mặt", "bảo hiểm", "bảo toàn", "bảo vệ",
    "bảo lãnh", "phân cấp", "phân quyền", "hội đồng", "quản trị", "ban giám đốc",
    "cổ đông", "kế hoạch", "kinh doanh", "lợi nhuận", "doanh thu", "tăng trưởng",
    "vốn chủ", "sở hữu", "tài chính", "ngân sách", "ngân hàng", "kiểm soát",
}


# Fast punctuation sets for O(1) checks
PUNCT_BREAKS = {",", ";", ":", ".", "!", "?", "\n", "—", "–", ")", "]", "}", "\"", "”"}
STRIP_CHARS = ".,;:!?()[]{}\"'“”—–/\\"

_VN_TONE_PAIRS = [
    ('oà', 'òa'), ('oá', 'óa'), ('oả', 'ỏa'), ('oã', 'õa'), ('oạ', 'ọa'),
    ('Oà', 'Òa'), ('Oá', 'Óa'), ('Oả', 'Ỏa'), ('Oã', 'Õa'), ('Oạ', 'Ọa'),
    ('oè', 'òe'), ('oé', 'óe'), ('oẻ', 'ỏe'), ('oẽ', 'õe'), ('oẹ', 'ọe'),
    ('Oè', 'Òe'), ('Oé', 'Óe'), ('Oẻ', 'Ỏe'), ('Oẽ', 'Õe'), ('Oẹ', 'Ọe'),
    ('uỳ', 'ùy'), ('uý', 'úy'), ('uỷ', 'ủy'), ('uỹ', 'ũy'), ('uỵ', 'ụy'),
    ('Uỳ', 'Ùy'), ('Uý', 'Úy'), ('Uỷ', 'Ủy'), ('Uỹ', 'Ũy'), ('Uỵ', 'Ụy'),
]


def normalize_vn_term(text: str) -> str:
    """Chuẩn hóa Unicode NFC và thống nhất quy chuẩn dấu tiếng Việt (hóa/hoá, hòa/hoà)."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    for modern, trad in _VN_TONE_PAIRS:
        text = text.replace(modern, trad)
    return text


class GenericFuzzyMatcher:
    """
    Khớp nối từ khóa chuẩn xác trong văn bản báo cáo thường niên.
    Hỗ trợ 100% tiếng Việt đa chuẩn, tiếng Anh chuyên ngành.
    """

    def __init__(self, dictionary: Dictionary, threshold: int = 85,
                 include_ambiguous: bool = False,
                 categories: Optional[List[str]] = None):
        """
        Args:
            dictionary: Bộ từ điển đã load
            threshold: Ngưỡng similarity cho fuzzy match (0-100)
            include_ambiguous: Bao gồm từ khóa đa nghĩa
            categories: Lọc theo nhóm category (None = tất cả)
        """
        self.dictionary = dictionary
        self.threshold = threshold
        self.categories = categories

        # Load and normalize keywords (NFC + tone mark harmonization)
        raw_keywords = dictionary.get_flat_list(
            include_variants=True,
            include_ambiguous=include_ambiguous,
            categories=categories,
        )
        self.keywords = [normalize_vn_term(kw) for kw in raw_keywords]

        raw_canon = dictionary.get_canonical_map(
            include_ambiguous=include_ambiguous,
            categories=categories,
        )
        self.canonical_map = {
            normalize_vn_term(k): normalize_vn_term(v)
            for k, v in raw_canon.items()
        }

        raw_cat = dictionary.get_category_map()
        self.category_map = {
            normalize_vn_term(k): v
            for k, v in raw_cat.items()
        }

        # Exclusions list
        self.exclusions = set()
        if hasattr(dictionary, "exclusions") and dictionary.exclusions:
            for exc in dictionary.exclusions:
                kw = exc.get("keyword") if isinstance(exc, dict) else str(exc)
                if kw:
                    self.exclusions.add(normalize_vn_term(kw.strip().lower()))

        # Safety exclusions: Tránh nhầm lẫn phân cấp quản trị doanh nghiệp và từ tiếng Anh thông dụng
        self.exclusions.add("phân quyền")
        self.exclusions.add("phan quyen")
        self.exclusions.add("phân cấp")
        self.exclusions.add("together")

        # Precompile high-speed regex patterns for exact match
        self._exact_patterns: List[Tuple[str, re.Pattern]] = []
        for kw in self.keywords:
            if kw.lower() in self.exclusions:
                continue
            words = kw.split()
            if not words:
                continue
            if len(words) == 1:
                pat = re.compile(r'(?<!\w)' + re.escape(words[0]) + r'(?!\w)', re.IGNORECASE)
            else:
                pat = re.compile(r'(?<!\w)' + r'\s+'.join(re.escape(w) for w in words) + r'(?!\w)', re.IGNORECASE)
            self._exact_patterns.append((kw, pat))

        # Pre-index theo word count + char length (tối ưu sliding window cho fuzzy fallback)
        self._kw_by_wc_len: Dict[int, Dict[int, List[str]]] = {}
        for kw in self.keywords:
            if kw.lower() in self.exclusions:
                continue
            wc = len(kw.split())
            cl = len(kw)
            self._kw_by_wc_len.setdefault(wc, {}).setdefault(cl, []).append(kw)

        # Pre-index character sets and max allowed edits for mathematical early rejection
        self._kw_charsets: Dict[str, Set[str]] = {
            kw: set(kw) for kw in self.keywords if kw.lower() not in self.exclusions
        }
        self._kw_max_edits: Dict[str, int] = {
            kw: int(len(kw) * (1.0 - threshold / 100.0) + 0.5) + 1
            for kw in self.keywords if kw.lower() not in self.exclusions
        }

        logger.info(
            f"KeywordMatcher: Đã tải {len(self.keywords)} từ khóa "
            f"(Mặc định: 100% Exact Match chuẩn NCKH; fuzzy_threshold={threshold}%)"
        )

    # =========================================================================
    # Core search
    # =========================================================================

    def exact_search(self, text: str) -> List[Dict]:
        """Tìm kiếm chính xác 100% (Exact match chuẩn khoa học)."""
        if not text:
            return []
        results: List[Dict] = []
        text_norm = normalize_vn_term(text)

        for keyword, pat in self._exact_patterns:
            for m in pat.finditer(text_norm):
                start = m.start()
                end = m.end()
                actual_chunk = text_norm[start:end]

                # Guard cho từ viết tắt ngắn (<= 3 ký tự, e.g. 'ico', 'dlt', 'nft', 'evm', 'bnb', 'xrp', 'ai', 'ml'):
                # Trong báo cáo thường niên, thuật ngữ viết tắt tiếng Anh bắt buộc phải viết HOA (ICO, NFT, DLT, AI, ML).
                # Chữ thường xuất hiện trong văn bản là từ thông dụng tiếng Việt ("ai", "ml") hoặc nhiễu OCR.
                if len(keyword) <= 3 and keyword.isascii():
                    if not actual_chunk.isupper():
                        continue

                    # OCR noise check: Nếu ngữ cảnh xung quanh chứa nhiều ký tự lỗi OCR, bỏ qua
                    c_start = max(0, start - 25)
                    c_end = min(len(text_norm), end + 25)
                    snippet_context = text_norm[c_start:c_end]
                    noise_chars = sum(1 for c in snippet_context if c in "@#%^*~`'{}/\\")
                    if noise_chars >= 3:
                        continue

                canonical = self.canonical_map.get(keyword, keyword)
                cat = self.category_map.get(canonical, self.category_map.get(keyword, "unknown"))
                results.append({
                    "keyword_found": actual_chunk,
                    "keyword_canonical": canonical,
                    "category": cat,
                    "position": start,
                    "end_position": end,
                    "match_type": "exact",
                    "similarity": 100.0,
                    "levenshtein_distance": 0,
                })

        return results

    def fuzzy_search(self, text: str) -> List[Dict]:
        """
        Tìm kiếm mờ bằng sliding window trên n-gram duy nhất có bảo vệ ranh giới câu.

        Thuật toán tối ưu:
        1. Chia text → tokens, ghi nhận ranh giới dấu ngắt câu (, ; : . ! ? ...)
        2. Gom n-gram duy nhất (không nối qua dấu ngắt vế/câu)
        3. So khớp Levenshtein theo nhóm độ dài từ khóa với bộ lọc từ thông dụng
        4. Ánh xạ kết quả lại tất cả vị trí xuất hiện
        """
        results: List[Dict] = []
        raw_tokens = text.lower().split()

        if not raw_tokens:
            return results

        tokens: List[str] = []
        token_positions: List[int] = []
        has_break_after: List[bool] = []
        pos = 0
        text_lower = text.lower()

        for raw_tok in raw_tokens:
            idx = text_lower.find(raw_tok, pos)
            pos = idx + len(raw_tok)

            ends_with_break = bool(raw_tok and raw_tok[-1] in PUNCT_BREAKS)
            clean_tok = raw_tok.strip(STRIP_CHARS)
            if clean_tok:
                tokens.append(clean_tok)
                token_positions.append(idx)
                has_break_after.append(ends_with_break)

        # Gom n-gram duy nhất: {n_words: {ngram_str: [indices]}}
        n_tokens = len(tokens)
        ngram_occurrences: Dict[int, Dict[str, List[int]]] = {}
        for n_words in self._kw_by_wc_len:
            if n_words > n_tokens:
                continue
            occ: Dict[str, List[int]] = {}
            if n_words == 1:
                for i, tok in enumerate(tokens):
                    occ.setdefault(tok, []).append(i)
            else:
                for i in range(n_tokens - n_words + 1):
                    # Không nối n-gram vượt qua ranh giới dấu phẩy/chấm ngắt vế câu
                    has_break = False
                    for j in range(i, i + n_words - 1):
                        if has_break_after[j]:
                            has_break = True
                            break
                    if has_break:
                        continue
                    window = " ".join(tokens[i:i + n_words])
                    occ.setdefault(window, []).append(i)
            ngram_occurrences[n_words] = occ

        # Fuzzy match trên n-gram duy nhất
        for n_words, length_map in self._kw_by_wc_len.items():
            if n_words not in ngram_occurrences:
                continue

            for window, indices in ngram_occurrences[n_words].items():
                len_w = len(window)
                min_len_k = int(0.73 * len_w)
                max_len_k = int(1.37 * len_w) + 1
                w_chars = set(window)

                for len_k in range(min_len_k, max_len_k + 1):
                    if len_k not in length_map:
                        continue

                    for keyword in length_map[len_k]:
                        # Skip quá ngắn (< 6 chars)
                        if len_k < 6:
                            continue

                        # Guard 0: Ràng buộc toán học hiệu độ dài (lev_distance >= |len_w - len_k|)
                        max_edits = self._kw_max_edits.get(keyword, 2)
                        if abs(len_w - len_k) > max_edits:
                            continue

                        # Guard 1: Từ vựng thông dụng tiếng Anh/tiếng Việt không thể là fuzzy match
                        if window in COMMON_GENERAL_WORDS and window != keyword:
                            continue

                        # Guard 2: Exclusions từ cấu hình từ điển
                        if window in self.exclusions:
                            continue

                        # Guard 3: Lọc toán học theo tập ký tự (loại bỏ 95% phép tính Levenshtein dư thừa)
                        k_chars = self._kw_charsets.get(keyword)
                        if k_chars is not None and len(k_chars - w_chars) > self._kw_max_edits.get(keyword, 2):
                            continue

                        # Guard 4: Ràng buộc khoảng cách Levenshtein và độ lệch độ dài cho từ đơn (n_words == 1)
                        if n_words == 1:
                            len_diff = abs(len_w - len_k)
                            if len_k <= 8 and len_diff > 1:
                                continue
                            dist = lev_distance(window, keyword)
                            if len_k <= 7 and dist > 1:
                                continue
                            if len_k <= 10 and dist > 2:
                                continue
                        else:
                            dist = lev_distance(window, keyword)

                        sim = lev_ratio(window, keyword) * 100

                        if sim >= self.threshold and sim < 100:
                            # Guard 4: Ràng buộc từng word cho cụm từ nhiều từ (n_words > 1)
                            if n_words > 1:
                                kw_words = keyword.split()
                                w_words = window.split()
                                skip_ngram = False
                                for w, k in zip(w_words, kw_words):
                                    if w == k:
                                        continue
                                    len_min = min(len(w), len(k))
                                    len_max = max(len(w), len(k))

                                    # Từ rất ngắn (<= 3 ký tự, e.g. "ảo", "vũ", "số"):
                                    # Phải bằng độ dài tuyệt đối, không được chênh ký tự (chống "bảo" vs "ảo")
                                    if len_min <= 3:
                                        if len_min != len_max or lev_ratio(w, k) < 0.85:
                                            skip_ngram = True
                                            break
                                    else:
                                        if (len_min / len_max <= 0.65) or lev_ratio(w, k) < 0.75:
                                            skip_ngram = True
                                            break
                                if skip_ngram:
                                    continue

                            canonical = self.canonical_map.get(keyword, keyword)

                            for idx in indices:
                                w_pos = token_positions[idx] if idx < len(token_positions) else 0
                                results.append({
                                    "keyword_found": window,
                                    "keyword_canonical": canonical,
                                    "category": self.category_map.get(canonical, "unknown"),
                                    "position": w_pos,
                                    "match_type": "fuzzy",
                                    "similarity": round(sim, 2),
                                    "levenshtein_distance": dist,
                                })

        return results

    def search(self, text: str, use_fuzzy: bool = False) -> List[Dict]:
        """Tìm kiếm từ khóa: Exact match mặc định (use_fuzzy=False chuẩn nghiên cứu khoa học)."""
        if not text:
            return []

        exact = self.exact_search(text)
        fuzzy = self.fuzzy_search(text) if use_fuzzy else []

        all_results = exact + fuzzy
        all_results = self._deduplicate(all_results)
        all_results.sort(key=lambda x: x["position"])

        return all_results

    # =========================================================================
    # Helpers
    # =========================================================================

    def _deduplicate(self, results: List[Dict]) -> List[Dict]:
        """
        Loại bỏ trùng lặp dựa trên khoảng ký tự thực tế [start, end].
        - Giữ cả 2 từ khóa nếu không đè lên nhau (ví dụ: 'AI/ML' -> cả 'AI' lẫn 'ML' đều được giữ).
        - Nếu 2 từ khóa chồng lấn lên nhau (ví dụ: 'trí tuệ nhân tạo tạo sinh' và 'trí tuệ nhân tạo'):
          ưu tiên từ khóa dài hơn, bao quát hơn (longest match).
        - Nếu cùng độ dài và chồng lấn: ưu tiên exact match hoặc similarity cao hơn.
        """
        if not results:
            return results

        # Đảm bảo có end_position cho từng kết quả
        for r in results:
            if "end_position" not in r:
                r["end_position"] = r["position"] + len(r.get("keyword_found", ""))

        # Sắp xếp ưu tiên:
        # 1. Exact match trước fuzzy match
        # 2. Độ dài từ khóa dài hơn trước (longest match)
        # 3. Similarity cao hơn
        sorted_results = sorted(
            results,
            key=lambda x: (
                1 if x.get("match_type") == "exact" else 0,
                len(x.get("keyword_found", "")),
                x.get("similarity", 0),
            ),
            reverse=True,
        )

        accepted: List[Dict] = []
        for cand in sorted_results:
            cand_start = cand["position"]
            cand_end = cand["end_position"]

            overlap = False
            for acc in accepted:
                acc_start = acc["position"]
                acc_end = acc["end_position"]
                # Hai khoảng [cand_start, cand_end) và [acc_start, acc_end) giao nhau khi:
                if max(cand_start, acc_start) < min(cand_end, acc_end):
                    overlap = True
                    break

            if not overlap:
                accepted.append(cand)

        accepted.sort(key=lambda x: x["position"])
        return accepted

    def get_summary(self, matches: List[Dict]) -> Dict:
        """Thống kê kết quả matching."""
        if not matches:
            return {
                "total_matches": 0,
                "exact_matches": 0,
                "fuzzy_matches": 0,
                "unique_keywords": 0,
                "keywords_found": [],
                "by_category": {},
            }

        exact = [m for m in matches if m["match_type"] == "exact"]
        fuzzy = [m for m in matches if m["match_type"] == "fuzzy"]
        unique_kws = set(m["keyword_canonical"] for m in matches)

        # Count by category
        by_cat: Dict[str, int] = {}
        for m in matches:
            cat = m.get("category", "unknown")
            by_cat[cat] = by_cat.get(cat, 0) + 1

        return {
            "total_matches": len(matches),
            "exact_matches": len(exact),
            "fuzzy_matches": len(fuzzy),
            "unique_keywords": len(unique_kws),
            "keywords_found": sorted(unique_kws),
            "by_category": by_cat,
        }
