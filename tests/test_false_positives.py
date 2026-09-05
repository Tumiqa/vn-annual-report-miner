# -*- coding: utf-8 -*-
"""
tests/test_false_positives.py
==============================
Kiểm thử ngăn chặn lỗi nhận diện sai (False Positives) và đảm bảo nhận diện đúng (True Positives):
1. 'tiền, bảo' không bị nhận diện nhầm thành 'tiền ảo'
2. 'together' không bị nhận diện nhầm thành 'tether'
3. 'phân quyền' quản trị công ty không bị nhận diện nhầm thành 'phi tập trung'
4. 'ico' trong văn bản OCR nhiễu không bị nhận diện nhầm thành 'initial coin offering'
5. Các thuật ngữ hợp lệ thực tế vẫn được nhận diện chính xác 100%.
"""
from pathlib import Path
import pytest
from arminer.core.smart_mode import FlexibleDictionary
from arminer.mining.matcher import GenericFuzzyMatcher


@pytest.fixture(scope="module")
def matcher():
    dict_path = Path("data/dictionaries/blockchain.yaml")
    if not dict_path.exists():
        dict_path = Path("src/arminer/templates/blockchain_dictionary.yaml")
    flex_dict = FlexibleDictionary.load(dict_path)
    core_dict = flex_dict.to_core_dictionary()
    return GenericFuzzyMatcher(dictionary=core_dict, threshold=85)


def test_false_positives_prevention(matcher):
    """Đảm bảo các ngữ cảnh thông thường không bao giờ kích hoạt từ khóa sai."""
    snippets = [
        ("LHG_tien_bao", "kiểm soát hiệu quả dòng tiền, bảo đảm nền tảng tài chính vững mạnh"),
        ("LHG_together", "the slowdown in global economic growth together with potential geopolitical risks"),
        ("LHG_together2", "pleased to submit this report together with the audited financial statements"),
        ("IDC_phan_quyen", "IDICO sẽ tiếp tục tinh gọn bộ máy, đẩy mạnh phân cấp phân quyền để tăng tính chủ động"),
        ("IDC_phan_quyen2", "từng bước xác lập cơ chế và chính sách phân cấp, phân quyền nhằm tăng cường tính chủ động"),
        ("IDC_phan_quyen3", "cơ cấu tổ chức theo hướng tăng cường chuyên môn hóa, tổ chức phân cấp - phân quyền để nâng cao tính chủ động"),
        ("NTC_ico_garbage", "h kinh t@cao cho xii h9i, IQ'iich kinh t@cho dia phuang va khu VIJCnO' ico KCN hinh thanh va phat triSn. - Chidn /u(1cphat tridn trung va did hg"),
    ]

    for name, text in snippets:
        matches = matcher.search(text, use_fuzzy=True)
        assert len(matches) == 0, f"False positive found in [{name}]: {matches}"


def test_true_positives_detection(matcher):
    """Đảm bảo các thuật ngữ thực thụ vẫn được nhận diện đầy đủ và chính xác."""
    tp_snippets = [
        ("TP_blockchain", "doanh nghiệp thử nghiệm ứng dụng blockchain trong truy xuất nguồn gốc"),
        ("TP_ICO_valid", "công ty nghiên cứu đợt phát hành ICO quốc tế theo quy định"),
        ("TP_tether_valid", "giao dịch thanh toán bằng đồng Tether và Ethereum trên thị trường"),
        ("TP_tien_ao_valid", "ngân hàng cảnh báo rủi ro về tiền ảo và tiền mã hóa"),
        ("TP_phi_tap_trung", "hệ thống tài chính phi tập trung trên nền tảng chuỗi khối"),
    ]

    for name, text in tp_snippets:
        matches = matcher.search(text, use_fuzzy=True)
        assert len(matches) > 0, f"Expected matches in [{name}], but got 0!"
