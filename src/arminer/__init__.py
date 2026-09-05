# -*- coding: utf-8 -*-
"""
vn-annual-report-miner (arminer)
================================
Công cụ khai phá dữ liệu Báo cáo Thường niên DN niêm yết Việt Nam.
Hỗ trợ bất kỳ chủ đề nghiên cứu nào — Blockchain, ESG, Fintech, CSR, ...

Usage::

    pip install vn-annual-report-miner
    arminer init my_research --template blockchain
    arminer run --stage all
"""

__version__ = "0.1.0"
__author__ = "NCKH Team"

from arminer.core.dictionary import Dictionary
from arminer.core.config import ProjectConfig

__all__ = [
    "__version__",
    "Dictionary",
    "ProjectConfig",
]
