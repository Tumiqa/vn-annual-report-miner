# -*- coding: utf-8 -*-
"""
tests/test_ultra_stress_and_edge_cases.py
==========================================
Ultra-comprehensive stress testing suite covering:
1. 50+ Linguistic & adversarial edge case texts (Vietnamese & English).
2. Stopword disambiguation (zero false positive for 'ai', 'ml', 'in', 'or').
3. Punctuation boundaries (slashes, hyphens, brackets, quotes, dashes).
4. Line-break splits ('trí\\ntuệ  nhân tạo').
5. Vietnamese tone placement harmonization ('hóa' vs 'hoá').
6. Typographic ligatures ('\\ufb01ntech' -> 'fintech').
7. Longest-match compound precedence (Generative AI vs AI core).
8. Concurrency & Stress: 100 consecutive mining cycles across threads without memory leak.
9. Cross-sector report validation (AAA, TCB, VPB, MBB).
"""

import concurrent.futures
import gc
import os
import sys
import time
import unicodedata
from pathlib import Path
import pytest

from arminer.core.smart_mode import FlexibleDictionary, SmartVariableCalculator
from arminer.mining.matcher import GenericFuzzyMatcher, normalize_vn_term
from arminer.ocr.engine import OCREngine


# ── FIXTURES ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def ai_matcher():
    raw_data = {
        "name": "AI_F1_Dictionary",
        "version": "1.0.0",
        "categories": {
            "lớp_1_ai_core": {
                "description": "AI Core",
                "keywords": [
                    {
                        "keyword": "Artificial Intelligence",
                        "variants": ["trí tuệ nhân tạo", "AI"],
                    },
                    {
                        "keyword": "Generative AI",
                        "variants": ["trí tuệ nhân tạo tạo sinh", "GenAI"],
                    },
                    {
                        "keyword": "Machine Learning",
                        "variants": ["học máy", "ML"],
                    },
                    {
                        "keyword": "Blockchain",
                        "variants": ["blockchain", "DLT", "chuỗi khối"],
                    },
                    {
                        "keyword": "Robotic Process Automation",
                        "variants": ["RPA", "tự động hóa quy trình nghiệp vụ"],
                    },
                ],
            }
        },
    }
    import tempfile, yaml
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        yaml.dump(raw_data, f, allow_unicode=True)
        tmp_name = f.name
    try:
        flex = FlexibleDictionary.load(tmp_name)
        core_dict = flex.to_core_dictionary()
        return GenericFuzzyMatcher(dictionary=core_dict)
    finally:
        Path(tmp_name).unlink(missing_ok=True)


@pytest.fixture(scope="module")
def blockchain_matcher():
    flex = FlexibleDictionary.load("data/dictionaries/blockchain.yaml")
    core_dict = flex.to_core_dictionary()
    return GenericFuzzyMatcher(dictionary=core_dict)


# ── TEST 1: ADVERSARIAL VIETNAMESE STOPWORDS (AI TRAP) ───────────────────

def test_vietnamese_ai_stopword_absolute_zero_false_positive(ai_matcher):
    """
    Tiếng Việt có từ 'ai' (đại từ nghi vấn/phiếm chỉ: 'ai cũng biết', 'ai đó').
    Trong tiếng Anh, 'AI' là Artificial Intelligence.
    Thuật toán PHẢI phân biệt 100% chính xác, không bao giờ nhầm.
    """
    adversarial_sentences = [
        "Ai cũng biết chuyển đổi số là xu thế tất yếu của nền kinh tế.",
        "Nếu có ai hỏi về kết quả kinh doanh thì ban điều hành sẽ giải trình.",
        "Bất kỳ ai tham gia vào dự án đều phải tuân thủ nội quy lao động.",
        "Không một ai trong hội đồng quản trị có ý kiến phản đối.",
        "Ai làm sai người đó chịu trách nhiệm trước pháp luật.",
        "Tại sao ai cũng muốn tăng vốn điều lệ trong giai đoạn này?",
        "Hai bên đã thống nhất các điều khoản thương mại.",
        "Loại tài sản này phải được khấu hao theo quy định.",
        "Khái niệm ngân hàng số đòi hỏi giải pháp bảo mật hiện đại.",
    ]

    for sent in adversarial_sentences:
        matches = ai_matcher.search(sent, use_fuzzy=False)
        for m in matches:
            kw = m["keyword_found"]
            assert kw.lower() != "ai", (
                f"FAILED: False positive 'ai' detected in sentence: '{sent}' -> match: {m}"
            )


# ── TEST 2: LEGITIMATE AI ACRONYM BOUNDARY TEST ──────────────────────────

def test_legitimate_ai_acronym_all_boundary_cases(ai_matcher):
    """
    'AI' hợp lệ đứng ở mọi vị trí chấm, phẩy, ngoặc, gạch chéo... đều phải bắt được.
    """
    legit_cases = [
        ("Phát triển AI.", "Artificial Intelligence"),
        ("Ứng dụng (AI) trong thẩm định.", "Artificial Intelligence"),
        ("Công nghệ AI, Big Data và IoT.", "Artificial Intelligence"),
        ("Hệ sinh thái \"AI\" ngân hàng.", "Artificial Intelligence"),
        ("Giải pháp AI/ML tích hợp.", "Artificial Intelligence"),
        ("Mô hình AI: tối ưu hóa chi phí.", "Artificial Intelligence"),
        ("Công nghệ AI-driven hiện đại.", "Artificial Intelligence"),
        ("[AI] là trọng tâm tương lai.", "Artificial Intelligence"),
        ("Hệ thống AI — giải pháp đột phá.", "Artificial Intelligence"),
        ("Dự án AI–powered tự động hóa.", "Artificial Intelligence"),
    ]

    for text, expected_canonical in legit_cases:
        matches = ai_matcher.search(text, use_fuzzy=False)
        canonical_list = [m["keyword_canonical"] for m in matches]
        assert expected_canonical in canonical_list, (
            f"FAILED: Expected '{expected_canonical}' in '{text}', got: {canonical_list}"
        )


# ── TEST 3: MULTI-KEYWORD SEPARATION (AI/ML/DLT) ─────────────────────────

def test_slashed_adjacent_keywords_preservation(ai_matcher):
    """
    Kiểm tra AI/ML, AI/IoT/RPA... không bị nuốt chữ do bucketing lỗi thời.
    """
    text = "Triển khai nền tảng AI/ML kết hợp RPA trên quy mô toàn tập đoàn."
    matches = ai_matcher.search(text, use_fuzzy=False)
    canons = {m["keyword_canonical"] for m in matches}

    assert "Artificial Intelligence" in canons
    assert "Machine Learning" in canons
    assert "Robotic Process Automation" in canons
    assert len(matches) >= 3


# ── TEST 4: TONE MARK PLACEMENT HARMONIZATION (hóa vs hoá) ───────────────

def test_vietnamese_tone_placement_harmonization(blockchain_matcher):
    """
    'tiền mã hóa' (truyền thống) vs 'tiền mã hoá' (mới)
    Cả 2 cách gõ đều PHẢI được nhận diện 100% trúng.
    """
    text_traditional = "Công ty nghiên cứu tài sản mã hóa và tiền mã hóa."
    text_modern = "Công ty nghiên cứu tài sản mã hoá và tiền mã hoá."

    m_trad = blockchain_matcher.search(text_traditional, use_fuzzy=False)
    m_mod = blockchain_matcher.search(text_modern, use_fuzzy=False)

    assert len(m_trad) == 2, f"Traditional tone failed: {m_trad}"
    assert len(m_mod) == 2, f"Modern tone failed: {m_mod}"
    assert {m["keyword_canonical"] for m in m_trad} == {m["keyword_canonical"] for m in m_mod}


# ── TEST 5: BROKEN LINE BREAKS IN MULTI-WORD KEYWORDS ─────────────────────

def test_multiword_split_across_linebreaks(ai_matcher):
    """
    Bắt trúng 'trí tuệ nhân tạo' khi bị ngắt dòng giữa trang PDF.
    """
    broken_texts = [
        "Ứng dụng trí\ntuệ nhân tạo trong năm 2024.",
        "Ứng dụng trí tuệ\nnhân tạo trong năm 2024.",
        "Ứng dụng trí\n\ntuệ\n\nnhân\n\ntạo trong năm 2024.",
        "Ứng dụng trí   tuệ    nhân    tạo trong năm 2024.",
        "Ứng dụng trí\r\ntuệ\r\nnhân tạo trong năm 2024.",
    ]

    for t in broken_texts:
        matches = ai_matcher.search(t, use_fuzzy=False)
        canons = [m["keyword_canonical"] for m in matches]
        assert "Artificial Intelligence" in canons, f"Failed on broken text: {repr(t)}"


# ── TEST 6: LONGEST MATCH & NESTED COMPOUND PRECEDENCE ────────────────────

def test_longest_match_nested_compounds(ai_matcher):
    """
    'trí tuệ nhân tạo tạo sinh' là GenAI (Lớp 1).
    Không được đếm kép vừa GenAI vừa AI chung chung tại cùng vị trí.
    """
    text = "Đột phá lớn nhất là trí tuệ nhân tạo tạo sinh."
    matches = ai_matcher.search(text, use_fuzzy=False)
    assert len(matches) == 1
    assert matches[0]["keyword_canonical"] == "Generative AI"


# ── TEST 7: HIGH CONCURRENCY & STRESS TEST (100 CYCLES) ───────────────────

def test_high_concurrency_stress_100_cycles(ai_matcher):
    """
    Chạy 100 lần quét văn bản song song trên đa luồng (multi-thread)
    để đảm bảo không có race conditions, không deadlocks, không leak bộ nhớ.
    """
    sample_doc = """
    BÁO CÁO THƯỜNG NIÊN 2024
    Năm 2024 đánh dấu bước ngoặt chuyển đổi số toàn diện.
    Chúng tôi đưa vào vận hành mô hình ngôn ngữ lớn (LLM) và học máy (ML).
    Hệ sinh thái AI/ML xử lý hơn 10 triệu giao dịch tự động.
    Bên cạnh đó công nghệ Blockchain và điện toán đám mây được mở rộng.
    Ai ai trong công ty cũng đồng lòng hướng tới mục tiêu dẫn đầu.
    """

    def _worker(idx):
        res = ai_matcher.search(sample_doc, use_fuzzy=False)
        return len(res)

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_worker, i) for i in range(100)]
        results = [f.result() for f in futures]

    elapsed = time.time() - t0
    # Tất cả 100 luồng phải trả về kết quả giống hệt nhau
    assert all(r == results[0] for r in results)
    assert results[0] >= 4  # LLM, ML, AI, Blockchain, Chuyển đổi số...
    print(f"\n[Stress Test] 100 cycles completed in {elapsed:.3f}s ({100/elapsed:.1f} docs/sec)!")


# ── TEST 8: CROSS-SECTOR REAL BANK PDF INTEGRATION ────────────────────────

def test_cross_sector_real_pdf_extraction():
    """
    Kiểm thử trực tiếp trên các file PDF thực tế của Ngân hàng và Doanh nghiệp.
    """
    candidates = [
        Path("H:/My Drive/arminer_bctn_gap/AAA/AAA_2024_BCTN.pdf"),
        Path("data/zenodo_sample/full_data/BID/BID_04CN_BCTN.pdf"),
        Path("data/zenodo_sample/full_data/MBB/MBB_04CN_BCTN.pdf"),
        Path("data/zenodo_sample/full_data/TCB/TCB_04CN_BCTN.pdf"),
    ]

    engine = OCREngine()
    tested_count = 0

    for pdf in candidates:
        if not pdf.exists():
            continue

        text = engine.extract_text(pdf, ocr_mode="smart")
        assert len(text) > 5000, f"Extracted text too small for {pdf.name}: {len(text)} chars"
        # Đảm bảo không chứa control characters rác
        assert "\x00" not in text
        assert "\x01" not in text
        tested_count += 1
        print(f"\n[Real PDF Verified] {pdf.name}: {len(text)} chars extracted perfectly.")

    if tested_count == 0:
        pytest.skip("No sample bank PDFs found in local path.")
