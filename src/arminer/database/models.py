# -*- coding: utf-8 -*-
"""
arminer.database.models
=========================
Generic ORM models — không gắn chủ đề cụ thể.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime,
    ForeignKey, Numeric, Boolean, Index,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Company(Base):
    """Doanh nghiệp niêm yết."""
    __tablename__ = "companies"

    company_id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), unique=True, nullable=False, index=True)
    company_name = Column(String(500))
    tax_id = Column(String(20))
    exchange = Column(String(10))  # HSX, HNX
    industry = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)

    reports = relationship("Report", back_populates="company")


class Report(Base):
    """Báo cáo thường niên."""
    __tablename__ = "reports"

    report_id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.company_id"))
    ticker = Column(String(20), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    pdf_path = Column(Text)
    ocr_path = Column(Text)
    total_pages = Column(Integer)
    total_words = Column(Integer)
    is_scanned = Column(Boolean, default=False)
    ocr_status = Column(String(20), default="pending")
    mining_status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

    company = relationship("Company", back_populates="reports")
    mining_results = relationship("TextMiningResult", back_populates="report")
    snippets = relationship("Snippet", back_populates="report")
    variables = relationship("CustomVariable", back_populates="report")

    __table_args__ = (
        Index("ix_reports_ticker_year", "ticker", "year", unique=True),
    )


class TextMiningResult(Base):
    """Kết quả text mining cấp DN-năm (generic)."""
    __tablename__ = "text_mining_results"

    result_id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("reports.report_id"), nullable=False)
    category = Column(String(100), nullable=False)  # "core", "environment", etc.
    frequency = Column(Integer, default=0)
    diversity = Column(Integer, default=0)
    normalized_score = Column(Numeric(12, 6), default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    report = relationship("Report", back_populates="mining_results")

    __table_args__ = (
        Index("ix_mining_report_category", "report_id", "category", unique=True),
    )


class Snippet(Base):
    """Đoạn ngữ cảnh chứa từ khóa."""
    __tablename__ = "snippets"

    snippet_id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("reports.report_id"), nullable=False)
    keyword_found = Column(String(200), nullable=False)
    keyword_canonical = Column(String(200), nullable=False)
    category = Column(String(100))
    match_type = Column(String(20))  # "exact" | "fuzzy"
    similarity_score = Column(Float)
    levenshtein_distance = Column(Integer)
    context_text = Column(Text)
    position_in_text = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

    report = relationship("Report", back_populates="snippets")


class CustomVariable(Base):
    """Biến nghiên cứu tùy chỉnh do người dùng định nghĩa."""
    __tablename__ = "custom_variables"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("reports.report_id"), nullable=False)
    variable_name = Column(String(100), nullable=False)
    variable_value = Column(Float)
    variable_type = Column(String(50))  # "text_mining", "financial", "classification"
    created_at = Column(DateTime, default=datetime.utcnow)

    report = relationship("Report", back_populates="variables")

    __table_args__ = (
        Index("ix_custom_var", "report_id", "variable_name", unique=True),
    )


class PipelineRun(Base):
    """Theo dõi lịch sử chạy pipeline."""
    __tablename__ = "pipeline_runs"

    run_id = Column(Integer, primary_key=True, autoincrement=True)
    stage = Column(String(50), nullable=False)
    status = Column(String(20), default="running")  # running, completed, failed
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    records_processed = Column(Integer, default=0)
    error_message = Column(Text)
