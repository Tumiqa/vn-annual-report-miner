# -*- coding: utf-8 -*-
"""
arminer.core.config
====================
Pydantic-based configuration schema cho arminer projects.
Validate & load arminer.yaml tự động.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator
from loguru import logger


# =============================================================================
# Sub-models
# =============================================================================

class ScopeConfig(BaseModel):
    """Phạm vi nghiên cứu."""
    year_start: int = 2014
    year_end: int = 2025
    exchanges: List[str] = ["HOSE", "HNX", "HSX"]
    tickers: Optional[List[str]] = None
    tickers_file: Optional[str] = None


class PDFSourceConfig(BaseModel):
    """Cấu hình nguồn PDF."""
    type: Literal["local", "zenodo", "cafef", "auto"] = "local"
    local_dir: str = "./data/pdfs"
    naming_pattern: str = "{ticker}_{yy}N_BCTN.pdf"
    zenodo_doi: str = "10.5281/zenodo.20949551"
    index_file: Optional[str] = None


class DictionaryConfig(BaseModel):
    """Cấu hình từ điển."""
    file: str = "dictionary.yaml"
    include_ambiguous: bool = False
    fuzzy_threshold: int = 85


class VariableDefinition(BaseModel):
    """Định nghĩa 1 biến đầu ra."""
    name: str
    type: Literal[
        "frequency", "diversity", "normalized_score",
        "classification", "financial_ratio", "custom"
    ]
    categories: Optional[List[str]] = None
    rule: Optional[str] = None
    formula: Optional[str] = None
    normalization: int = 10_000


class FinancialDataConfig(BaseModel):
    """Cấu hình dữ liệu tài chính từ vnfinancialdata."""
    enabled: bool = True
    source: str = "vnfinancialdata"
    variables: List[Dict[str, Any]] = Field(default_factory=list)
    auto_ratios: List[str] = Field(
        default_factory=lambda: ["roa", "roe", "size", "leverage"]
    )


class OCRConfig(BaseModel):
    """Cấu hình OCR."""
    use_gpu: bool = False
    tesseract_lang: str = "vie+eng"
    tesseract_config: str = "--oem 3 --psm 6"
    min_text_per_page: int = 100


class ExportConfig(BaseModel):
    """Cấu hình xuất dữ liệu."""
    formats: List[Literal["csv", "parquet", "stata", "excel"]] = ["csv", "parquet"]
    output_dir: str = "./output"
    panel_id: str = "ticker"
    time_var: str = "year"


class SnippetConfig(BaseModel):
    """Cấu hình trích xuất ngữ cảnh."""
    context_chars: int = 500


# =============================================================================
# Main Config
# =============================================================================

class ProjectConfig(BaseModel):
    """
    Cấu hình chính cho arminer project.
    Tương ứng với file arminer.yaml.
    """
    project_name: str = "My Research"
    description: str = ""

    scope: ScopeConfig = Field(default_factory=ScopeConfig)
    pdf_source: PDFSourceConfig = Field(default_factory=PDFSourceConfig)
    dictionary: DictionaryConfig = Field(default_factory=DictionaryConfig)
    variables: List[VariableDefinition] = Field(default_factory=list)
    financial_data: FinancialDataConfig = Field(default_factory=FinancialDataConfig)
    ocr: OCRConfig = Field(default_factory=OCRConfig)
    export: ExportConfig = Field(default_factory=ExportConfig)
    snippet: SnippetConfig = Field(default_factory=SnippetConfig)

    database_url: str = ""
    log_level: str = "INFO"

    @field_validator("database_url", mode="before")
    @classmethod
    def _set_default_db(cls, v: str) -> str:
        if not v:
            return "sqlite:///data/arminer.db"
        return v

    # =========================================================================
    # Factory
    # =========================================================================

    @classmethod
    def from_yaml(cls, path: str | Path) -> "ProjectConfig":
        """Load config từ arminer.yaml."""
        import yaml

        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        # Flatten nested 'project' key nếu có
        if "project" in data:
            project_data = data.pop("project")
            data["project_name"] = project_data.get("name", "")
            data["description"] = project_data.get("description", "")

        config = cls(**data)
        logger.info(f"Loaded config: {config.project_name}")
        return config

    @classmethod
    def default(cls) -> "ProjectConfig":
        """Trả về config mặc định."""
        return cls()

    def to_yaml(self, path: str | Path) -> None:
        """Ghi config ra file YAML."""
        import yaml

        path = Path(path)
        data = self.model_dump(mode="json")
        # Restructure for readability
        output = {
            "project": {
                "name": data.pop("project_name"),
                "description": data.pop("description"),
            },
            **data,
        }

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(
                output, f,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
                width=100,
            )

        logger.info(f"Config saved to {path}")

    @property
    def years(self) -> List[int]:
        """Danh sách năm nghiên cứu."""
        return list(range(self.scope.year_start, self.scope.year_end + 1))
