# -*- coding: utf-8 -*-
"""
arminer.core.dictionary_manager
================================
Quản lý từ điển nghiên cứu: Xem, Thêm, Sửa, Xóa (CRUD), Xuất/Nhập.
Hỗ trợ lưu trữ bền vững (persistent storage) cho từ điển tùy biến của người dùng.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from loguru import logger

from arminer.core.smart_mode import FlexibleDictionary


class DictionaryManager:
    """Quản lý các bộ từ điển hệ thống và từ điển người dùng tạo."""

    def __init__(self, workspace_root: Optional[Path] = None):
        if workspace_root is None:
            workspace_root = Path(__file__).resolve().parent.parent.parent.parent
        self.workspace_root = workspace_root
        self.templates_dir = Path(__file__).resolve().parent.parent / "templates"
        self.custom_dir = self.workspace_root / "data" / "dictionaries"
        self.custom_dir.mkdir(parents=True, exist_ok=True)

    def list_topics(self) -> List[Dict[str, Any]]:
        """Liệt kê tất cả các từ điển (cả mẫu hệ thống lẫn từ điển người dùng)."""
        topics = []
        seen_ids = set()

        # 1. Custom user dictionaries
        for f in self.custom_dir.glob("*.yaml"):
            tid = f.stem
            try:
                d = FlexibleDictionary.load(f)
                topics.append({
                    "id": tid,
                    "name": d.name or tid.replace("_", " ").title(),
                    "is_custom": True,
                    "file_path": str(f),
                    "total_keywords": len(d.entries),
                    "categories": d.categories,
                })
                seen_ids.add(tid)
            except Exception as e:
                logger.warning(f"Error loading custom dict {f}: {e}")

        # 2. Built-in templates
        if self.templates_dir.exists():
            for f in self.templates_dir.glob("*_dictionary.yaml"):
                tid = f.stem.replace("_dictionary", "")
                if tid not in seen_ids:
                    try:
                        d = FlexibleDictionary.load(f)
                        topics.append({
                            "id": tid,
                            "name": d.name or tid.title(),
                            "is_custom": False,
                            "file_path": str(f),
                            "total_keywords": len(d.entries),
                            "categories": d.categories,
                        })
                    except Exception as e:
                        logger.warning(f"Error loading template dict {f}: {e}")

        return topics

    def _get_dict_path(self, topic_id: str) -> Path:
        """Tìm đường dẫn file từ điển."""
        custom_file = self.custom_dir / f"{topic_id}.yaml"
        if custom_file.exists():
            return custom_file

        template_file = self.templates_dir / f"{topic_id}_dictionary.yaml"
        if template_file.exists():
            return template_file

        return custom_file

    def get_dictionary(self, topic_id: str) -> Dict[str, Any]:
        """Lấy chi tiết từ điển bao gồm tất cả từ khóa, nhóm, trọng số."""
        p = self._get_dict_path(topic_id)
        if not p.exists():
            raise FileNotFoundError(f"Không tìm thấy từ điển: {topic_id}")

        d = FlexibleDictionary.load(p)
        keywords = []
        for idx, entry in enumerate(d.entries):
            keywords.append({
                "id": idx + 1,
                "keyword": entry.get("keyword", ""),
                "category": entry.get("category", "default"),
                "weight": entry.get("weight", 1.0),
                "variants": entry.get("variants") or "",
                "language": entry.get("language", "vi"),
            })

        return {
            "id": topic_id,
            "name": d.name,
            "is_custom": p.parent == self.custom_dir,
            "total_keywords": len(keywords),
            "categories": d.categories,
            "keywords": keywords,
        }

    def save_dictionary(self, topic_id: str, name: str, keywords: List[Dict[str, Any]]) -> Path:
        """Lưu toàn bộ từ điển vào thư mục data/dictionaries/."""
        custom_path = self.custom_dir / f"{topic_id}.yaml"
        
        # Group by category
        categories: Dict[str, List[Dict[str, Any]]] = {}
        for kw in keywords:
            cat = str(kw.get("category", "default")).strip().lower() or "default"
            if cat not in categories:
                categories[cat] = []
            
            categories[cat].append({
                "keyword": str(kw.get("keyword", "")).strip().lower(),
                "weight": float(kw.get("weight", 1.0)),
                "variants": [v.strip() for v in str(kw.get("variants", "")).split("|") if v.strip()] if kw.get("variants") else [],
                "language": kw.get("language", "vi"),
            })

        data = {
            "name": name,
            "version": "1.0.0",
            "categories": {
                cat_name: {
                    "description": f"Category {cat_name}",
                    "keywords": kws,
                }
                for cat_name, kws in categories.items()
            }
        }

        with open(custom_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        logger.info(f"Saved dictionary {topic_id} ({len(keywords)} keywords) to {custom_path}")
        return custom_path

    def add_keyword(self, topic_id: str, keyword: str, category: str = "default", weight: float = 1.0) -> Dict[str, Any]:
        """Thêm từ khóa mới vào từ điển."""
        dict_data = self.get_dictionary(topic_id)
        kw_clean = keyword.strip().lower()
        if not kw_clean:
            raise ValueError("Từ khóa không được để trống.")

        # Check existing
        for item in dict_data["keywords"]:
            if item["keyword"].lower() == kw_clean:
                raise ValueError(f"Từ khóa '{kw_clean}' đã tồn tại trong nhóm '{item['category']}'.")

        new_entry = {
            "id": len(dict_data["keywords"]) + 1,
            "keyword": kw_clean,
            "category": category.strip().lower() or "default",
            "weight": float(weight),
            "variants": "",
            "language": "vi",
        }
        dict_data["keywords"].append(new_entry)

        self.save_dictionary(topic_id, dict_data["name"], dict_data["keywords"])
        return new_entry

    def update_keyword(self, topic_id: str, old_keyword: str, new_keyword: str, category: str, weight: float = 1.0) -> Dict[str, Any]:
        """Sửa một từ khóa hiện có."""
        dict_data = self.get_dictionary(topic_id)
        found = False
        updated = None

        for item in dict_data["keywords"]:
            if item["keyword"].lower() == old_keyword.strip().lower():
                item["keyword"] = new_keyword.strip().lower()
                item["category"] = category.strip().lower() or "default"
                item["weight"] = float(weight)
                found = True
                updated = item
                break

        if not found:
            raise ValueError(f"Không tìm thấy từ khóa: '{old_keyword}'")

        self.save_dictionary(topic_id, dict_data["name"], dict_data["keywords"])
        return updated

    def delete_keyword(self, topic_id: str, keyword: str) -> bool:
        """Xóa từ khóa khỏi từ điển."""
        dict_data = self.get_dictionary(topic_id)
        initial_len = len(dict_data["keywords"])
        dict_data["keywords"] = [k for k in dict_data["keywords"] if k["keyword"].lower() != keyword.strip().lower()]

        if len(dict_data["keywords"]) == initial_len:
            raise ValueError(f"Không tìm thấy từ khóa: '{keyword}'")

        self.save_dictionary(topic_id, dict_data["name"], dict_data["keywords"])
        return True

    def create_topic(self, topic_id: str, name: str, initial_keywords: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Tạo mới một bộ từ điển hoàn chỉnh."""
        clean_id = re.sub(r"[^a-z0-9_]", "_", topic_id.strip().lower())
        if not clean_id:
            raise ValueError("Mã từ điển không hợp lệ.")

        kws = initial_keywords or []
        self.save_dictionary(clean_id, name, kws)
        return self.get_dictionary(clean_id)

    def delete_topic(self, topic_id: str) -> bool:
        """Xóa hoàn toàn một bộ từ điển (custom hoặc template)."""
        clean_id = re.sub(r"[^a-z0-9_]", "_", topic_id.strip().lower())
        custom_file = self.custom_dir / f"{clean_id}.yaml"
        template_file = self.templates_dir / f"{clean_id}_dictionary.yaml"

        deleted = False
        if custom_file.exists():
            custom_file.unlink()
            deleted = True

        if not deleted and template_file.exists():
            template_file.unlink()
            deleted = True

        if not deleted:
            raise FileNotFoundError(f"Không tìm thấy bộ từ điển: '{topic_id}'")

        logger.info(f"Deleted dictionary topic: {clean_id}")
        return True

