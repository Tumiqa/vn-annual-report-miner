# -*- coding: utf-8 -*-
"""
arminer.database.crud
======================
CRUD operations cho database.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session
from loguru import logger

from arminer.database.models import (
    Company, Report, TextMiningResult, Snippet, CustomVariable,
)


def get_or_create_company(session: Session, ticker: str,
                          **kwargs) -> Company:
    """Lấy hoặc tạo company."""
    company = session.query(Company).filter_by(ticker=ticker).first()
    if not company:
        company = Company(ticker=ticker, **kwargs)
        session.add(company)
        session.flush()
    return company


def get_or_create_report(session: Session, ticker: str, year: int,
                         **kwargs) -> Report:
    """Lấy hoặc tạo report."""
    report = session.query(Report).filter_by(
        ticker=ticker, year=year
    ).first()
    if not report:
        report = Report(ticker=ticker, year=year, **kwargs)
        session.add(report)
        session.flush()
    return report


def save_mining_results(session: Session, report_id: int,
                        results: Dict[str, Dict]) -> None:
    """Lưu kết quả text mining theo category."""
    for category, metrics in results.items():
        existing = session.query(TextMiningResult).filter_by(
            report_id=report_id, category=category
        ).first()

        if existing:
            existing.frequency = metrics.get("frequency", 0)
            existing.diversity = metrics.get("diversity", 0)
            existing.normalized_score = metrics.get("normalized_score", 0)
        else:
            result = TextMiningResult(
                report_id=report_id,
                category=category,
                frequency=metrics.get("frequency", 0),
                diversity=metrics.get("diversity", 0),
                normalized_score=metrics.get("normalized_score", 0),
            )
            session.add(result)

    session.flush()


def save_snippets(session: Session, snippets: List[Dict]) -> int:
    """Lưu snippets vào database."""
    count = 0
    for s in snippets:
        snippet = Snippet(
            report_id=s["report_id"],
            keyword_found=s["keyword_found"],
            keyword_canonical=s["keyword_canonical"],
            category=s.get("category", "unknown"),
            match_type=s.get("match_type", "exact"),
            similarity_score=s.get("similarity_score", 100.0),
            levenshtein_distance=s.get("levenshtein_distance", 0),
            context_text=s.get("context_text", ""),
            position_in_text=s.get("position_in_text", 0),
        )
        session.add(snippet)
        count += 1

    session.flush()
    return count


def save_custom_variables(session: Session, report_id: int,
                          variables: Dict[str, any]) -> None:
    """Lưu custom variables."""
    for name, value in variables.items():
        if value is None:
            continue

        existing = session.query(CustomVariable).filter_by(
            report_id=report_id, variable_name=name
        ).first()

        if existing:
            existing.variable_value = float(value)
        else:
            cv = CustomVariable(
                report_id=report_id,
                variable_name=name,
                variable_value=float(value),
            )
            session.add(cv)

    session.flush()


def get_all_reports(session: Session) -> List[Report]:
    """Lấy tất cả reports."""
    return session.query(Report).all()


def get_reports_by_status(session: Session, stage: str,
                          status: str) -> List[Report]:
    """Lấy reports theo trạng thái stage."""
    if stage == "ocr":
        return session.query(Report).filter_by(ocr_status=status).all()
    elif stage == "mining":
        return session.query(Report).filter_by(mining_status=status).all()
    return []
