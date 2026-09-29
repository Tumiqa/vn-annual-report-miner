# -*- coding: utf-8 -*-
"""
arminer.mining.labor_patterns
==============================
Keyword lists & compiled regex patterns cho Total Employee Extractor.

Mục tiêu duy nhất: LABOR(ticker, year) = Tổng số nhân viên cuối năm tài chính.
"""

from __future__ import annotations

import re
from typing import List, Pattern

# =========================================================================
# 1. TRIGGER KEYWORDS — Tín hiệu câu/đoạn chứa số nhân viên
# =========================================================================

TRIGGER_KEYWORDS_VI: List[str] = [
    "tổng số nhân viên",
    "tổng số lao động",
    "tổng số người lao động",
    "tổng số cán bộ nhân viên",
    "tổng số cán bộ, nhân viên",
    "tổng số cán bộ công nhân viên",
    "tổng số cbcnv",
    "tổng số cbnv",
    "tổng số nhân sự",
    "tổng nhân sự",
    "tổng nhân viên",
    "tổng lao động",
    "số lượng nhân viên",
    "số lượng lao động",
    "số lượng người lao động",
    "số lượng cán bộ",
    "quy mô nhân sự",
    "nhân sự của công ty",
    "nhân viên của công ty",
    "nhân viên của tập đoàn",
    "lao động của công ty",
    "nhân viên toàn hệ thống",
    "nhân viên trên toàn hệ thống",
    "nhân viên",
    "người lao động",
    "cbcnv",
    "cbnv",
    "cán bộ nhân viên",
    "cán bộ công nhân viên",
    "nhân sự",
    "lực lượng lao động",
    "nguồn nhân lực",
]

TRIGGER_KEYWORDS_EN: List[str] = [
    "total number of employees",
    "total employees",
    "number of employees",
    "number of employees in the company",
    "number of employees in the group",
    "total workforce",
    "total staff",
    "total personnel",
    "headcount",
    "employee headcount",
    "employees as of",
    "employees as at",
    "employees at",
    "had employees",
    "employees",
    "workforce",
    "personnel",
    "staff",
]

# =========================================================================
# 2. TOTAL SIGNAL — Từ khóa chỉ đây là TỔNG SỐ (không phải nhóm con)
# =========================================================================

TOTAL_SIGNALS_VI: List[str] = [
    "tổng số", "tổng cộng", "toàn bộ", "toàn hệ thống", "toàn công ty",
    "toàn tập đoàn", "tổng nhân sự", "tổng nhân viên", "tổng lao động",
    "quy mô nhân sự", "quy mô lao động",
]

TOTAL_SIGNALS_EN: List[str] = [
    "total", "overall", "aggregate", "in total", "totaling",
    "company-wide", "group-wide", "across the group",
    "as a whole", "entire",
]

# =========================================================================
# 3. SUBSET SIGNALS — Nếu có mặt → KHÔNG phải tổng, chỉ là nhóm con
# =========================================================================

SUBSET_SIGNALS_VI: List[str] = [
    "trong đó", "bao gồm", "chiếm", "tỷ lệ",
    "lao động trực tiếp", "lao động gián tiếp",
    "nhân viên nam", "nhân viên nữ", "lao động nữ", "lao động nam",
    "nhân viên quản lý", "cán bộ quản lý", "ban giám đốc", "ban lãnh đạo",
    "nhân viên kinh doanh", "nhân viên sản xuất", "nhân viên văn phòng",
    "nhân viên tại", "lao động tại",
    "theo trình độ", "theo giới tính", "theo độ tuổi",
    "hợp đồng thời vụ", "hợp đồng ngắn hạn",
    "thực tập", "thời vụ", "bán thời gian",
    "thành viên hội đồng", "thành viên hđqt",
]

SUBSET_SIGNALS_EN: List[str] = [
    "of which", "including", "comprising", "thereof",
    "male", "female", "women", "men",
    "direct", "indirect", "production", "office", "sales",
    "management", "executive", "manager",
    "part-time", "temporary", "seasonal", "contract", "intern",
    "board member", "director",
    "by gender", "by age", "by education", "by qualification",
    "in vietnam", "overseas", "abroad",
]

# =========================================================================
# 4. EXCLUSION PATTERNS — Câu chứa những pattern này thì bỏ qua
#    (Đây là tỷ lệ/chỉ số, KHÔNG phải headcount)
# =========================================================================

EXCLUSION_PATTERNS: List[str] = [
    "giờ đào tạo", "giờ/nhân viên", "giờ/người",
    "triệu đồng/người", "triệu đồng/nhân viên", "triệu đồng", "tỷ đồng", "nghìn đồng", "ngàn đồng",
    "vnd", "usd", "ca mắc", "cổ phần", "cổ phiếu",
    "doanh thu/nhân viên", "lợi nhuận/nhân viên",
    "năng suất lao động", "năng suất nhân viên",
    "thu nhập bình quân", "lương bình quân", "thu nhập/người", "thu nhập/tháng", "thu nhập/năm",
    "thu nhập mỗi người", "thu nhập trung bình", "tổng thu nhập",
    "per employee", "per capita", "per head",
    "training hours", "hours per",
    "productivity", "compensation per",
    "revenue per", "profit per", "income per",
    "tuyển dụng thêm", "tuyển mới", "nghỉ việc", "thôi việc",
    "turnover rate", "attrition", "hiring",
    "tăng thêm", "giảm bớt", "giảm đi",  # delta exclusions
    "xuất khẩu lao động", "đi làm việc ở nước ngoài", "sang thị trường",
    "cục quản lý lao động ngoài nước", "toàn ngành", "cả nước",
    "không còn là nhân viên", "ban kiểm toán nội bộ", "nghỉ thai sản",
    "sáng kiến, giải pháp của", "sáng kiến của", "mua cổ phiếu của cbcnv",
    "phát hành cổ phiếu theo chương trình", "lựa chọn người lao động", "esop",
]

# Regex nhận diện các câu chỉ mức biến động (delta), bộ phận, hoặc quyết định chứ không phải tổng quy mô
DELTA_EXCLUSION_REGEXES: List[Pattern] = [
    re.compile(
        r"\b(?:tăng|giảm|tăng\s+thêm|giảm\s+bớt|tăng\s+trưởng|biến\s+động|thay\s+đổi|tuyển\s+mới|tuyển\s+dụng|nghỉ\s+việc|thôi\s+việc|điều\s+động)\s+"
        r"(?:khoảng\s+|hơn\s+|gần\s+)?\d+\s*(?:người|lao\s*động|nhân\s*viên|cbcnv|cbnv|lao\s*dng)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:tăng|giảm)\s+(?:so\s+với\s+[^\n,.]+?|khoảng\s+|hơn\s+|gần\s+)?(?:là\s+)?\d+\s*(?:người|lao\s*động|nhân\s*viên|nhân\s*sự)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:tổng\s+số\s+lao\s+động|tổng\s+số\s+nhân\s+sự|số\s+lượng\s+lao\s+động)\s+(?:tăng|giảm)\s+\d+\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:\d+[/.-](?:QĐ|NQ)[A-Za-z0-9_./-]*|(?:QĐ|NQ)[/.-]\d+)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:E|C|B|A)\.\d+\.\d+\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:khối\s+bán\s+hàng|chi\s+nhánh\s+phân\s+phối|đội\s+ngũ\s+nhân\s+sự\s+tại\s+\d+\s+chi\s+nhánh)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bđào\s+tạo[^.\n]{0,40}?\b\d+\s*(?:cbql|cán\s+bộ\s+quản\s+lý|lãnh\s+đạo)\b",
        re.IGNORECASE,
    ),
]

# =========================================================================
# 5. YEAR-END DATE PATTERNS — Dấu hiệu đây là số liệu cuối năm
# =========================================================================

YEAR_END_PATTERNS_VI: List[str] = [
    r"31/12/\d{4}",
    r"31\.12\.\d{4}",
    r"ngày 31 tháng 12",
    r"thời\s+điểm\s+31[/.\s-]*(?:12|tháng\s*12)",
    r"cuối năm",
    r"cuối kỳ",
    r"tính đến",
    r"tại thời điểm",
    r"vào thời điểm",
    r"đến ngày",
    r"đến thời điểm",
    r"tại ngày",
]

YEAR_END_PATTERNS_EN: List[str] = [
    r"31\s*december",
    r"december\s*31",
    r"31/12/\d{4}",
    r"12/31/\d{4}",
    r"as\s+(?:of|at)\s+(?:31\s+december|december\s+31)",
    r"year[- ]?end",
    r"end of (?:the )?(?:fiscal )?year",
    r"as at",
    r"as of",
]

# =========================================================================
# 6. COMPILED REGEX — Trích xuất số + đơn vị
# =========================================================================

# Đơn vị nhân viên tiếng Việt
_UNIT_VI = (
    r"(?:nhân\s*viên|người\s*lao\s*động|lao\s*động|CBCNV|CBNV|CB\s*[-–]\s*CNV|"
    r"cán\s*bộ\s*(?:,?\s*)?(?:công\s*nhân\s*)?viên|nhân\s*sự|người|lao\s*dng)"
)

# Đơn vị nhân viên tiếng Anh
_UNIT_EN = (
    r"(?:employees?|personnel|staff|workers?|people|persons?|headcount|FTEs?)"
)

# Pattern số: 1.750, 54,646 (có phân cách) hoặc 1072, 2152 (4-6 chữ số liền nhau) hoặc 1-999
_NUM_PATTERN = r"(?:\d{1,3}(?:[.,]\d{3})+|\d{4,6}|\d{1,3})"

# Pattern 1: SỐ + ĐƠN VỊ  →  "9.960 nhân viên", "1072 người", "54,646 employees"
RE_NUMBER_THEN_UNIT = re.compile(
    r"(?<!\d[.,])"                    # Không nằm trong số thập phân
    r"(?P<number>" + _NUM_PATTERN + r")"
    r"\s*"
    r"(?P<unit>" + _UNIT_VI + r"|" + _UNIT_EN + r")",
    re.IGNORECASE | re.UNICODE,
)

# Pattern 2: ĐƠN VỊ + LÀ/CÓ + SỐ  →  "nhân viên là 606", "employees: 1,255"
RE_UNIT_THEN_NUMBER = re.compile(
    r"(?P<unit>" + _UNIT_VI + r"|" + _UNIT_EN + r")"
    r"\s*(?:là|:|\s+)\s*"
    r"(?P<number>" + _NUM_PATTERN + r")",
    re.IGNORECASE | re.UNICODE,
)

# Pattern 3: "had/have/has/với/có NUMBER employees/nhân viên"
RE_HAD_NUMBER = re.compile(
    r"(?:had|have|has|với|có)\s+"
    r"(?P<number>" + _NUM_PATTERN + r")"
    r"\s*"
    r"(?P<unit>" + _UNIT_VI + r"|" + _UNIT_EN + r")",
    re.IGNORECASE | re.UNICODE,
)

# Pattern 4: Bảng — dòng chứa header + số dạng "NUMBER OF EMPLOYEES ... 1,255"
#   Xử lý riêng trong logic, không regex đơn thuần.

# Pattern 5: Trích năm từ context
RE_YEAR = re.compile(r"(?:20[12]\d)")

# Pattern 6: Trích ngày 31/12/YYYY
RE_DATE_31_12 = re.compile(
    r"(?:31[/.\s-]*(?:12|december|tháng\s*12)[/.\s-]*(\d{4})|thời\s+điểm\s+31[/.\s-]*(?:12|tháng\s*12)[/.\s-]*(\d{4}))",
    re.IGNORECASE,
)


def normalize_number(raw: str) -> int:
    """
    Chuyển chuỗi số Vietnamese/English → int.
    
    Rules:
    - "9.960" (VN: dấu . phân hàng nghìn) → 9960
    - "54,646" (EN: dấu , phân hàng nghìn) → 54646
    - "1.255" → ambiguous (VN: 1255, EN: 1.255) → kiểm tra:
      - Nếu sau dấu . có đúng 3 chữ số → hàng nghìn → 1255
      - Nếu không → giữ nguyên
    """
    s = raw.strip()
    if not s:
        return 0
    
    # Trường hợp chỉ có dấu chấm: "9.960" → 9960
    if "." in s and "," not in s:
        parts = s.split(".")
        # Nếu tất cả phần sau dấu . đều có 3 chữ số → phân hàng nghìn
        if all(len(p) == 3 for p in parts[1:]):
            return int(s.replace(".", ""))
        else:
            # Số thập phân thật → làm tròn
            return int(float(s))
    
    # Trường hợp chỉ có dấu phẩy: "54,646" → 54646
    if "," in s and "." not in s:
        parts = s.split(",")
        if all(len(p) == 3 for p in parts[1:]):
            return int(s.replace(",", ""))
        else:
            return int(float(s.replace(",", ".")))
    
    # Trường hợp cả . và ,: "1.234,56" hoặc "1,234.56"
    if "." in s and "," in s:
        dot_pos = s.rfind(".")
        comma_pos = s.rfind(",")
        if dot_pos > comma_pos:
            # EN format: 1,234.56
            return int(float(s.replace(",", "")))
        else:
            # VN format: 1.234,56
            return int(float(s.replace(".", "").replace(",", ".")))
    
    # Chỉ có chữ số
    return int(s)
