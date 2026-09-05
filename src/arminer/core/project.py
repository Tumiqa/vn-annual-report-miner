# -*- coding: utf-8 -*-
"""
arminer.core.project
=====================
Quản lý project lifecycle: init, load, validate.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from loguru import logger

from arminer.core.config import ProjectConfig
from arminer.core.dictionary import Dictionary


_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


class Project:
    """Đại diện cho một dự án nghiên cứu arminer."""

    CONFIG_FILE = "arminer.yaml"
    DEFAULT_DIRS = ["data", "data/pdfs", "data/ocr_output", "output", "logs"]

    def __init__(self, root: Path, config: ProjectConfig,
                 dictionary: Optional[Dictionary] = None):
        self.root = root.resolve()
        self.config = config
        self._dictionary = dictionary

    # =========================================================================
    # Factory
    # =========================================================================

    @classmethod
    def init(cls, directory: str | Path, template: str = "blank",
             project_name: Optional[str] = None) -> "Project":
        """
        Khởi tạo project mới trong directory.

        Args:
            directory: Thư mục chứa project
            template: "blank", "blockchain", "esg", "fintech"
            project_name: Tên project (mặc định = tên thư mục)
        """
        root = Path(directory).resolve()
        root.mkdir(parents=True, exist_ok=True)

        name = project_name or root.name

        # 1. Tạo thư mục con
        for subdir in cls.DEFAULT_DIRS:
            (root / subdir).mkdir(parents=True, exist_ok=True)

        # 2. Copy template dictionary
        dict_filename = f"{template}_dictionary.yaml"
        template_src = _TEMPLATES_DIR / dict_filename

        if template != "blank" and template_src.exists():
            shutil.copy2(template_src, root / "dictionary.yaml")
            logger.info(f"Copied template dictionary: {dict_filename}")
        elif template == "blank":
            # Tạo file dictionary trống
            _create_blank_dictionary(root / "dictionary.yaml")
        else:
            logger.warning(
                f"Template '{template}' not found at {template_src}. "
                f"Creating blank dictionary."
            )
            _create_blank_dictionary(root / "dictionary.yaml")

        # 3. Tạo arminer.yaml config
        config = ProjectConfig(
            project_name=name,
            description=f"{name} — created with arminer",
        )
        config.to_yaml(root / cls.CONFIG_FILE)

        # 4. Tạo .gitignore
        gitignore = root / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(
                "data/pdfs/\ndata/ocr_output/\n*.db\nlogs/\n__pycache__/\n.env\n",
                encoding="utf-8",
            )

        logger.success(f"Project '{name}' initialized at {root}")
        return cls.load(root)

    @classmethod
    def load(cls, directory: str | Path) -> "Project":
        """Load project đã tồn tại từ directory."""
        root = Path(directory).resolve()
        config_path = root / cls.CONFIG_FILE

        if not config_path.exists():
            raise FileNotFoundError(
                f"No arminer.yaml found in {root}. "
                f"Run 'arminer init' first."
            )

        config = ProjectConfig.from_yaml(config_path)

        # Load dictionary nếu có
        dict_path = root / config.dictionary.file
        dictionary = None
        if dict_path.exists():
            dictionary = Dictionary.from_yaml(dict_path)

        return cls(root=root, config=config, dictionary=dictionary)

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def dictionary(self) -> Dictionary:
        if self._dictionary is None:
            dict_path = self.root / self.config.dictionary.file
            if dict_path.exists():
                self._dictionary = Dictionary.from_yaml(dict_path)
            else:
                raise FileNotFoundError(
                    f"Dictionary file not found: {dict_path}"
                )
        return self._dictionary

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def pdf_dir(self) -> Path:
        p = Path(self.config.pdf_source.local_dir)
        if not p.is_absolute():
            p = self.root / p
        return p

    @property
    def output_dir(self) -> Path:
        p = Path(self.config.export.output_dir)
        if not p.is_absolute():
            p = self.root / p
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def db_url(self) -> str:
        url = self.config.database_url
        if url.startswith("sqlite:///") and not Path(url.split("///")[1]).is_absolute():
            return f"sqlite:///{self.root / url.split('///')[1]}"
        return url


def _create_blank_dictionary(path: Path) -> None:
    """Tạo file từ điển trống mẫu."""
    content = """# Dictionary cho dự án nghiên cứu
# Chỉnh sửa file này để thêm từ khóa cho chủ đề của bạn.
# Hướng dẫn: https://github.com/nckh-team/vn-annual-report-miner

name: "My Dictionary"
version: "1.0"
description: "Từ điển tùy chỉnh"

categories:
  default:
    display_name: "Nhóm mặc định"
    keywords:
      - keyword: "example keyword"
        variants: "ví dụ từ khóa"
        language: "en"
        weight: 1.0

# Từ khóa loại trừ (false positives)
exclusions: []

# Quy tắc phân loại
classification_rules:
  adoption:
    trigger_keywords: ["triển khai", "ứng dụng", "implemented"]
  talk:
    description: "Default nếu không match adoption"
"""
    path.write_text(content, encoding="utf-8")
