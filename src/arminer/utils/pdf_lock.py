# -*- coding: utf-8 -*-
"""
arminer.utils.pdf_lock
======================
Thread synchronization lock for PyMuPDF (fitz / mupdfcpp64.dll).

MuPDF C library uses non-thread-safe global contexts, font caches, and memory allocators.
Concurrent calls from multiple threads in ThreadPoolExecutor can corrupt heap structures
and trigger Windows Access Violation (0xc0000005) crashes.
This module provides a process-wide reentrant lock to serialize all C-level MuPDF calls.
"""

import threading

# Global reentrant lock for all PyMuPDF / fitz operations
PYMUPDF_LOCK = threading.RLock()

