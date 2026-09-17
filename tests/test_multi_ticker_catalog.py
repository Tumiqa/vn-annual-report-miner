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


def test_exchange_filter_single_and_combo(catalog):
    _, tot_all = catalog.search(return_total=True)
    res_hsx, tot_hsx = catalog.search(exchange="HSX", return_total=True, limit=100)
    res_hnx, tot_hnx = catalog.search(exchange="HNX", return_total=True, limit=100)
    res_upcom, tot_upcom = catalog.search(exchange="UPCOM", return_total=True, limit=100)
    _, tot_hsx_hnx = catalog.search(exchange="HSX,HNX", return_total=True)

    # Check non-empty
    assert tot_hsx > 4000
    assert tot_hnx > 2500
    assert tot_upcom > 5000
    assert tot_hsx + tot_hnx == tot_hsx_hnx

    # Verify each returned record has the expected exchange
    for r in res_hsx:
        assert r["exchange"] in ("HSX", "HOSE")
    for r in res_hnx:
        assert r["exchange"] == "HNX"
    for r in res_upcom:
        assert r["exchange"] == "UPCOM"

    # All 3 exchanges combined = no restriction
    _, tot_three = catalog.search(exchange="HSX,HNX,UPCOM", return_total=True)
    assert tot_three == tot_all


def test_exchange_filter_matched_record_ids(catalog):
    results_hsx, tot_hsx = catalog.search(exchange="HSX", limit=0, return_total=True)
    ids_hsx = catalog.get_matched_record_ids(exchange="HSX")
    assert len(ids_hsx) == tot_hsx
    assert len(ids_hsx) == len(results_hsx)

    results_combo, tot_combo = catalog.search(ticker="VCB,ACB,BSR", exchange="HSX,UPCOM", limit=0, return_total=True)
    ids_combo = catalog.get_matched_record_ids(ticker="VCB,ACB,BSR", exchange="HSX,UPCOM")
    assert len(ids_combo) == tot_combo
    assert len(ids_combo) == len(results_combo)

