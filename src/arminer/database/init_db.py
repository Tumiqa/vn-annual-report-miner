# -*- coding: utf-8 -*-
"""
arminer.database.init_db
==========================
Khởi tạo database.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from loguru import logger

from arminer.database.models import Base


_engine = None
_SessionLocal = None


def init_database(db_url: str = "sqlite:///data/arminer.db") -> None:
    """Khởi tạo database và tạo bảng."""
    global _engine, _SessionLocal

    # Đảm bảo thư mục tồn tại cho SQLite
    if db_url.startswith("sqlite:///"):
        db_path = db_url.replace("sqlite:///", "")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    _engine = create_engine(db_url, echo=False)
    _SessionLocal = sessionmaker(bind=_engine)

    Base.metadata.create_all(_engine)
    logger.info(f"Database initialized: {db_url}")


def get_session() -> Session:
    """Lấy database session."""
    if _SessionLocal is None:
        init_database()
    return _SessionLocal()


def get_engine():
    """Lấy database engine."""
    if _engine is None:
        init_database()
    return _engine
