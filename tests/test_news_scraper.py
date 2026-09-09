# -*- coding: utf-8 -*-
"""
Tests for arminer.data.news_scraper and company website resolution.
"""

import pytest
from arminer.data.news_scraper import (
    CompanyWebsiteResolver,
    UniversalNewsExtractor,
    MultiSourceNewsAggregator,
)


def test_company_website_resolver_preloaded():
    resolver = CompanyWebsiteResolver()
    assert len(resolver._db) >= 1400

    # Test top companies from web.txt
    ssi = resolver.get_company("SSI")
    assert ssi is not None
    assert "ssi.com.vn" in (ssi.get("website") or "")

    hpg = resolver.get_company("HPG")
    assert hpg is not None
    assert "hoaphat.com.vn" in (hpg.get("website") or "")

    fpt = resolver.get_company("FPT")
    assert fpt is not None
    assert "fpt.com" in (fpt.get("website") or "")


def test_company_website_resolver_listing():
    resolver = CompanyWebsiteResolver()
    comps = resolver.list_companies(query="chứng khoán", limit=10)
    assert len(comps) > 0


def test_universal_news_extractor_html():
    extractor = UniversalNewsExtractor()
    sample_html = """
    <!DOCTYPE html>
    <html>
    <head><title>FPT công bố kết quả kinh doanh quý 1 vượt kế hoạch</title></head>
    <body>
      <article>
        <h1>FPT công bố kết quả kinh doanh quý 1 vượt kế hoạch</h1>
        <time datetime="2026-03-31">31/03/2026</time>
        <div class="content">
          <p>Tập đoàn FPT ghi nhận doanh thu và lợi nhuận trước thuế tăng trưởng mạnh mẽ trong quý đầu năm.</p>
          <p>Khối công nghệ và viễn thông tiếp tục đóng góp tỷ trọng lớn nhất với nhu cầu chuyển đổi số và giải pháp trí tuệ nhân tạo ngày càng gia tăng trên toàn cầu.</p>
        </div>
      </article>
    </body>
    </html>
    """
    res = extractor.extract_from_html(sample_html, "https://fpt.com/news/1")
    assert res is not None
    assert "FPT" in res["title"]
    assert "chuyển đổi số" in res["text"]
    assert res["word_count"] > 10


def test_news_aggregator_deduplication():
    agg = MultiSourceNewsAggregator()
    # Test deduplication with simulated articles
    arts = [
        {"title": "FPT đầu tư mạnh vào AI", "text": "Nội dung 1...", "ticker": "FPT", "news_source": "cafef"},
        {"title": "FPT đầu tư mạnh vào AI!", "text": "Nội dung 2...", "ticker": "FPT", "news_source": "tinnhanhck"},
        {"title": "Vietcombank báo lãi kỷ lục", "text": "Nội dung 3...", "ticker": "VCB", "news_source": "cafef"},
    ]
    seen = []
    from difflib import SequenceMatcher
    deduped = []
    for a in arts:
        t_clean = a["title"].lower().strip()
        is_dup = any(SequenceMatcher(None, t_clean, prev).ratio() > 0.75 for prev in seen)
        if not is_dup:
            seen.append(t_clean)
            deduped.append(a)

    assert len(deduped) == 2


def test_parse_year():
    extractor = UniversalNewsExtractor()
    assert extractor.parse_year("2024-03-15") == 2024
    assert extractor.parse_year("15/08/2023") == 2023
    assert extractor.parse_year(url="https://vnexpress.net/kinh-doanh/2022/bai-bao-123.html") == 2022
    assert extractor.parse_year(text="Hà Nội, ngày 12/04/2021 - Tập đoàn Hòa Phát hôm nay...") == 2021
    assert extractor.parse_year() is None


def test_universal_news_extractor_with_year():
    extractor = UniversalNewsExtractor()
    sample_html = """
    <!DOCTYPE html>
    <html>
    <head><title>FPT công bố kết quả kinh doanh năm 2024</title></head>
    <body>
      <article>
        <h1>FPT công bố kết quả kinh doanh năm 2024</h1>
        <time datetime="2024-03-31">31/03/2024</time>
        <div class="content">
          <p>Tập đoàn FPT ghi nhận doanh thu và lợi nhuận trước thuế tăng trưởng mạnh mẽ trong quý đầu năm 2024.</p>
          <p>Khối công nghệ và viễn thông tiếp tục đóng góp tỷ trọng lớn nhất với nhu cầu chuyển đổi số toàn cầu.</p>
        </div>
      </article>
    </body>
    </html>
    """
    res = extractor.extract_from_html(sample_html, "https://fpt.com/news/1")
    assert res is not None
    assert res["published_year"] == 2024

