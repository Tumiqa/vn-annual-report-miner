# -*- coding: utf-8 -*-
"""
tests/test_zenodo_resilience.py
================================
Unit tests for ZenodoDownloader resilience features:
1. Circuit Breaker tripping and cooling down
2. Stage 1 Local-First lookup (offline, 0ms)
3. Namelist persistent caching
4. Fault tolerance when network is degraded or unavailable
"""

import time
from pathlib import Path
import pytest
from arminer.data.zenodo_downloader import (
    ZenodoDownloader,
    CircuitBreaker,
    ARCHIVE_ZIP_MAP,
)


def test_circuit_breaker_behavior():
    cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=2)
    assert cb.can_attempt() is True
    assert cb.is_open is False

    # First failure
    cb.record_failure("504 Gateway Timeout")
    assert cb.can_attempt() is True
    assert cb.failure_count == 1
    assert cb.is_open is False

    # Second failure -> Trips circuit breaker
    cb.record_failure("Read timed out")
    assert cb.failure_count == 2
    assert cb.is_open is True
    assert cb.can_attempt() is False

    # Wait for cooldown
    time.sleep(2.1)
    # Should allow attempt after cooldown
    assert cb.can_attempt() is True

    # Record success resets failure count
    cb.record_success()
    assert cb.failure_count == 0
    assert cb.is_open is False


def test_local_first_lookup(tmp_path):
    cache_dir = tmp_path / "zenodo_cache"
    downloader = ZenodoDownloader(cache_root=cache_dir)

    # Place a mock PDF in cache
    mock_pdf = cache_dir / "2021_2025" / "full_data" / "FPT" / "FPT_23CN_BCTN.pdf"
    mock_pdf.parent.mkdir(parents=True, exist_ok=True)
    mock_pdf.write_bytes(b"%PDF-1.4 Mock PDF Content" + b"0" * 2000)

    # Trip the circuit breaker deliberately to prove NO network call is made
    downloader.circuit_breaker.record_failure("Simulated network outage")
    downloader.circuit_breaker.record_failure("Simulated network outage")
    assert downloader.circuit_breaker.is_open is True

    # Call get_pdf_path - should succeed via Stage 1 (Local-First) despite Circuit Breaker being OPEN
    found_path = downloader.get_pdf_path(
        ticker="FPT",
        year=2023,
        archive_period="2021_2025",
        relative_path="full_data/FPT/FPT_23CN_BCTN.pdf",
    )

    assert found_path is not None
    assert found_path.exists()
    assert found_path.name == "FPT_23CN_BCTN.pdf"


def test_download_reports_multi_stage(tmp_path):
    cache_dir = tmp_path / "zenodo_cache"
    downloader = ZenodoDownloader(cache_root=cache_dir)

    # Prepare 1 local file
    fpt_pdf = cache_dir / "2021_2025" / "FPT_23CN_BCTN.pdf"
    fpt_pdf.parent.mkdir(parents=True, exist_ok=True)
    fpt_pdf.write_bytes(b"%PDF-1.4 Mock PDF Content" + b"X" * 2000)

    reports = [
        {
            "ticker": "FPT",
            "year": 2023,
            "archive_period": "2021_2025",
            "relative_path": "FPT_23CN_BCTN.pdf",
        },
        {
            "ticker": "VNM",
            "year": 2023,
            "archive_period": "2021_2025",
            "relative_path": "full_data/VNM/VNM_23CN_BCTN.pdf",
        },
    ]

    # Trip circuit breaker to prevent remote network attempt for VNM
    downloader.circuit_breaker.record_failure("Offline")
    downloader.circuit_breaker.record_failure("Offline")

    results = downloader.download_reports(reports)
    assert len(results) == 2

    # FPT was local -> ready
    assert results[0]["download_status"] == "local_ready"
    assert results[0]["local_path"] is not None
    assert Path(results[0]["local_path"]).exists()

    # VNM had circuit open -> circuit_open (does not hang or crash)
    assert results[1]["download_status"] == "circuit_open"
    assert results[1]["local_path"] is None
