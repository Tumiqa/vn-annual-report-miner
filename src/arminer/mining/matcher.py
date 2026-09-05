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


class GenericFuzzyMatcher:
    """
    Khớp nối mờ từ khóa trong văn bản OCR.

    Sử dụng Dictionary object thay vì hardcode — hoạt động
    với bất kỳ chủ đề nghiên cứu nào.
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

        # Load keywords
        self.keywords = dictionary.get_flat_list(
            include_variants=True,
            include_ambiguous=include_ambiguous,
            categories=categories,
        )
        self.canonical_map = dictionary.get_canonical_map(
            include_ambiguous=include_ambiguous,
            categories=categories,
        )
        self.category_map = dictionary.get_category_map()

        # Exclusions list
        self.exclusions = set()
        if hasattr(dictionary, "exclusions") and dictionary.exclusions:
            for exc in dictionary.exclusions:
                kw = exc.get("keyword") if isinstance(exc, dict) else str(exc)
                if kw:
                    self.exclusions.add(kw.strip().lower())

        # Safety exclusions: Tránh nhầm lẫn phân cấp quản trị doanh nghiệp và từ tiếng Anh thông dụng
        self.exclusions.add("phân quyền")
        self.exclusions.add("phan quyen")
        self.exclusions.add("phân cấp")
        self.exclusions.add("together")

        # Pre-index theo word count + char length (tối ưu sliding window)
        self._kw_by_wc_len: Dict[int, Dict[int, List[str]]] = {}
        for kw in self.keywords:
            if kw in self.exclusions:
                continue
            wc = len(kw.split())
            cl = len(kw)
            self._kw_by_wc_len.setdefault(wc, {}).setdefault(cl, []).append(kw)

        logger.info(
            f"GenericFuzzyMatcher: {len(self.keywords)} keywords, "
            f"threshold={threshold}%"
        )

    # =========================================================================
    # Core search
    # =========================================================================

    def exact_search(self, text: str) -> List[Dict]:
        """Tìm kiếm chính xác (nhanh, pass đầu tiên)."""
        results: List[Dict] = []
        text_lower = text.lower()

        for keyword in self.keywords:
            if keyword in self.exclusions:
                continue

            start = 0
            while True:
                pos = text_lower.find(keyword, start)
                if pos == -1:
                    break

                # Word boundary check
                before_ok = (pos == 0) or (not text_lower[pos - 1].isalnum())
                end_pos = pos + len(keyword)
                after_ok = (end_pos >= len(text_lower)) or (not text_lower[end_pos].isalnum())

                if before_ok and after_ok:
                    # Guard cho từ viết tắt ngắn (<= 3 ký tự, e.g. 'ico', 'dlt', 'nft', 'evm', 'bnb', 'xrp'):
                    # Trong báo cáo thường niên, thuật ngữ viết tắt tiếng Anh bắt buộc phải viết HOA (ICO, NFT, DLT).
                    # Chữ thường xuất hiện trong văn bản OCR quét kém hoặc từ thông dụng là nhiễu.
                    if len(keyword) <= 3 and keyword.isascii():
                        actual_chunk = text[pos:end_pos]
                        if not actual_chunk.isupper():
                            start = pos + 1
                            continue

                        # OCR noise check: Nếu ngữ cảnh xung quanh chứa nhiều ký tự lỗi OCR, bỏ qua
                        c_start = max(0, pos - 25)
                        c_end = min(len(text), end_pos + 25)
                        snippet_context = text[c_start:c_end]
                        noise_chars = sum(1 for c in snippet_context if c in "@#%^*~`'{}/\\")
                        if noise_chars >= 2:
                            start = pos + 1
                            continue

                    canonical = self.canonical_map.get(keyword, keyword)
                    results.append({
                        "keyword_found": keyword,
                        "keyword_canonical": canonical,
                        "category": self.category_map.get(canonical, "unknown"),
                        "position": pos,
                        "match_type": "exact",
                        "similarity": 100.0,
                        "levenshtein_distance": 0,
                    })

                start = pos + 1

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

            ends_with_break = any(
                raw_tok.endswith(p)
                for p in [",", ";", ":", ".", "!", "?", "\n", "—", "–", ")", "]", "}", "\"", "”"]
            )
            clean_tok = raw_tok.strip(".,;:!?()[]{}\"'“”—–/\\")
            if clean_tok:
                tokens.append(clean_tok)
                token_positions.append(idx)
                has_break_after.append(ends_with_break)

        # Gom n-gram duy nhất: {n_words: {ngram_str: [indices]}}
        ngram_occurrences: Dict[int, Dict[str, List[int]]] = {}
        for n_words in self._kw_by_wc_len:
            if n_words > len(tokens):
                continue
            ngram_occurrences[n_words] = {}
            for i in range(len(tokens) - n_words + 1):
                # Không nối n-gram vượt qua ranh giới dấu phẩy/chấm ngắt vế câu
                # Ví dụ: "dòng tiền," và "bảo đảm" không được nối thành cụm "tiền bảo"
                if n_words > 1 and any(has_break_after[j] for j in range(i, i + n_words - 1)):
                    continue

                window = " ".join(tokens[i:i + n_words])
                ngram_occurrences[n_words].setdefault(window, []).append(i)

        # Fuzzy match trên n-gram duy nhất
        for n_words, length_map in self._kw_by_wc_len.items():
            if n_words not in ngram_occurrences:
                continue

            for window, indices in ngram_occurrences[n_words].items():
                len_w = len(window)
                min_len_k = int(0.73 * len_w)
                max_len_k = int(1.37 * len_w) + 1

                for len_k in range(min_len_k, max_len_k + 1):
                    if len_k not in length_map:
                        continue

                    for keyword in length_map[len_k]:
                        # Skip quá ngắn (< 6 chars)
                        if len_k < 6:
                            continue

                        # Guard 1: Từ vựng thông dụng tiếng Anh/tiếng Việt không thể là fuzzy match
                        # của từ khóa chuyên sâu (ví dụ: together vs tether, finance vs binance)
                        if window in COMMON_GENERAL_WORDS and window != keyword:
                            continue

                        # Guard 2: Exclusions từ cấu hình từ điển
                        if window in self.exclusions:
                            continue

                        # Guard 3: Ràng buộc khoảng cách Levenshtein và độ lệch độ dài cho từ đơn (n_words == 1)
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

    def search(self, text: str, use_fuzzy: bool = True) -> List[Dict]:
        """Tìm kiếm kết hợp: Exact + Fuzzy."""
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
        """Loại trùng: cùng vị trí → giữ exact, hoặc similarity cao nhất."""
        if not results:
            return results

        unique: Dict[int, Dict] = {}
        for r in results:
            key = r["position"] // 5
            if key not in unique:
                unique[key] = r
            elif r["match_type"] == "exact" and unique[key]["match_type"] == "fuzzy":
                unique[key] = r
            elif r["similarity"] > unique[key]["similarity"]:
                unique[key] = r

        return list(unique.values())

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
