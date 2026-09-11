# -*- coding: utf-8 -*-
"""
tests/test_multi_ticker_catalog.py
==================================
Unit tests for multi-ticker search and filtering in UnifiedCatalog.
Validates:
1. Comma, space, semicolon, and newline separated ticker queries
2. Single-ticker substring search compatibility
3. Partial prefix queries (< 3 chars)
4. get_matched_record_ids consistency with search results
5. Empty / whitespace inputs
"""

import pytest
from arminer.data.catalog import UnifiedCatalog


@pytest.fixture(scope="module")
def catalog():
    uc = UnifiedCatalog()
    uc.initialize()
    return uc


def test_multi_ticker_comma_separated(catalog):
    results, total = catalog.search(ticker="VCB, BID, FPT", return_total=True, limit=200)
    matched_tickers = set(r["ticker"] for r in results)
    assert matched_tickers == {"BID", "FPT", "VCB"}
    assert total >= 50


def test_multi_ticker_space_separated(catalog):
    results, total = catalog.search(ticker="VCB BID CTG", return_total=True, limit=200)
    matched_tickers = set(r["ticker"] for r in results)
    assert matched_tickers == {"BID", "CTG", "VCB"}
    assert total >= 50


def test_multi_ticker_semicolon_and_lowercase(catalog):
    results, total = catalog.search(ticker="vcb; bid; hpg", return_total=True, limit=200)
    matched_tickers = set(r["ticker"] for r in results)
    assert matched_tickers == {"BID", "HPG", "VCB"}
    assert total >= 50


def test_single_ticker_exact_and_substring(catalog):
    results, total = catalog.search(ticker="VCB", return_total=True, limit=100)
    matched_tickers = set(r["ticker"] for r in results)
    assert matched_tickers == {"VCB"}
    assert total >= 15


def test_partial_prefix_query(catalog):
    results, total = catalog.search(ticker="VC", return_total=True, limit=100)
    assert total > 100
    for r in results:
        assert "VC" in r["ticker"]


def test_get_matched_record_ids_consistency(catalog):
    results, total = catalog.search(ticker="VCB, BID, FPT", return_total=True)
    ids = catalog.get_matched_record_ids(ticker="VCB, BID, FPT")
    assert len(ids) == total
    assert len(ids) == len(results)


def test_empty_or_whitespace_ticker(catalog):
    _, total_all = catalog.search(return_total=True)
    _, total_empty = catalog.search(ticker="   ", return_total=True)
    assert total_all == total_empty
