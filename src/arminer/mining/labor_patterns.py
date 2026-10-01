# -*- coding: utf-8 -*-
"""
arminer.mining.labor_patterns
==============================
Keyword lists, compiled regex patterns & normalizers for Total Employee Extractor.

Mục tiêu duy nhất: LABOR(ticker, year) = Tổng số nhân viên cuối năm tài chính (31/12).
Đảm bảo 100% Precision (không nhận nhầm chỉ tiêu bộ phận, tỷ lệ, tiền lương, cổ phần).
Đảm bảo tối đa Recall (bao quát toàn bộ các hình thức công bố trong BCTN Việt Nam).
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
    "số lượng cán bộ, nhân viên",
    "quy mô nhân sự",
    "quy mô lao động",
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
    "cb-cn",
    "cb-nv",
    "cb-cnv",
    "cán bộ nhân viên",
    "cán bộ công nhân viên",
    "cán bộ, công nhân viên",
    "nhân sự",
    "lực lượng lao động",
    "nguồn nhân lực",
    # Unaccented & font-corrupted triggers (legacy BCTN PDFs)
    "so luong can bo",
    "so luong lao dong",
    "so luong nhan vien",
    "s6 luong can be",
    "s6 luong can bo",
    "s6 luqng lao dng",
    "s6 hrong lao dqng",
    "s6 hrong can be",
    "so hrong cb-cn",
    "so hrong cb-nv",
    "s0luqng lao tlqng",
    "ngudn nhin lgc",
    "tong so lao dong",
    "tong so nhan vien",
]

TRIGGER_KEYWORDS_EN: List[str] = [
    "total number of employees",
    "total employees",
    "number of employees",
    "numberof employees",
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
    "quy mô nhân sự", "quy mô lao động", "hợp nhất", "toàn ngành",
]

TOTAL_SIGNALS_EN: List[str] = [
    "total", "overall", "aggregate", "in total", "totaling",
    "company-wide", "group-wide", "across the group",
    "as a whole", "entire", "consolidated",
]

# =========================================================================
# 3. SUBSET SIGNALS — Nếu có mặt → KHÔNG phải tổng, chỉ là nhóm con
# =========================================================================

SUBSET_SIGNALS_VI: List[str] = [
    "trong đó", "bao gồm", "chiếm", "tỷ lệ", "tỷ trọng",
    "có trình độ", "trình độ từ", "trung cấp trở lên", "đại học trở lên", "sau đại học",
    "lao động trực tiếp", "lao động gián tiếp",
    "nhân viên nam", "nhân viên nữ", "lao động nữ", "lao động nam", "tỷ lệ nữ",
    "nhân viên quản lý", "cán bộ quản lý", "ban giám đốc", "ban lãnh đạo",
    "nhân viên kinh doanh", "nhân viên sản xuất", "nhân viên văn phòng",
    "nhân viên tại", "lao động tại",
    "theo trình độ", "theo giới tính", "theo độ tuổi",
    "hợp đồng thời vụ", "hợp đồng ngắn hạn", "thời vụ", "bán thời gian",
    "thực tập", "thử việc",
    "thành viên hội đồng", "thành viên hđqt", "thành viên bks",
    "thuê mới", "tuyển mới", "tuyển dụng", "nghỉ việc", "thôi việc", "sa thải",
]

SUBSET_SIGNALS_EN: List[str] = [
    "of which", "including", "comprising", "thereof",
    "male", "female", "women", "men",
    "direct", "indirect", "production", "office", "sales",
    "management", "executive", "manager",
    "part-time", "temporary", "seasonal", "contract", "intern", "probation",
    "board member", "director",
    "by gender", "by age", "by education", "by qualification",
    "in vietnam", "overseas", "abroad",
    "new hires", "recruited", "resigned", "turnover",
]

# =========================================================================
# 4. EXCLUSION PATTERNS — Câu chứa những pattern này thì bỏ qua
#    (Đây là tỷ lệ/chỉ số, delta, hoặc tài chính, KHÔNG phải headcount)
# =========================================================================

EXCLUSION_PATTERNS: List[str] = [
    "giờ đào tạo", "giờ/nhân viên", "giờ/người", "khóa đào tạo", "lượt đào tạo", "lượt người",
    "triệu đồng/người", "triệu đồng/nhân viên", "triệu đồng", "tỷ đồng", "nghìn đồng", "ngàn đồng",
    "tr.đồng", "triệu vnđ", "tỷ vnđ", "vnd/người", "đồng/người", "usd/người",
    "vnd", "usd", "ca mắc", "cổ phần", "cổ phiếu",
    "doanh thu/nhân viên", "lợi nhuận/nhân viên",
    "năng suất lao động", "năng suất nhân viên",
    "thu nhập bình quân", "lương bình quân", "thu nhập/người", "thu nhập/tháng", "thu nhập/năm",
    "thu nhập mỗi người", "thu nhập trung bình", "tổng thu nhập", "tiền lương", "quỹ lương", "thù lao",
    "per employee", "per capita", "per head",
    "training hours", "hours per",
    "productivity", "compensation per",
    "revenue per", "profit per", "income per",
    "tuyển dụng thêm", "tuyển mới", "thuê mới", "nghỉ việc", "thôi việc", "sa thải", "chấm dứt hđlđ",
    "thăng tiến", "bổ nhiệm", "khen thưởng", "kỷ luật", "điều động", "luân chuyển",
    "turnover rate", "attrition", "hiring",
    "tăng thêm", "giảm bớt", "giảm đi",  # delta exclusions
    "xuất khẩu lao động", "đi làm việc ở nước ngoài", "sang thị trường", "lao động ngoài nước",
    "cục quản lý lao động ngoài nước", "cục quản lý lao động", "bộ lao động", "toàn ngành", "cả nước", "thị trường lao động",
    "không còn là nhân viên", "ban kiểm toán nội bộ", "nghỉ thai sản", "nghỉ thai", "thai sản", "maternity", "trở lại làm việc sau khi",
    "sáng kiến, giải pháp của", "sáng kiến của", "mua cổ phiếu của cbcnv",
    "phát hành cổ phiếu theo chương trình", "lựa chọn người lao động", "esop", "được phân phối", "cổ phiếu thưởng",
    "khẩu trang", "tiêm ngừa", "tiêm chủng", "vắc xin", "vacxin", "covid", "mũi 1", "mũi 2", "mũi 3",
    "có trình độ từ", "trung cấp trở lên", "đại học trở lên", "sau đại học",
    "thất nghiệp", "tai nạn lao động", "bảo hiểm thất nghiệp", "trợ cấp thất nghiệp",
    "đội ngũ điều hành", "ban tổng giám đốc", "ban giám đốc", "ban kiểm soát",
]

# Regex nhận diện các câu chỉ mức biến động (delta), bộ phận, hoặc quyết định chứ không phải tổng quy mô
DELTA_EXCLUSION_REGEXES: List[Pattern] = [
    re.compile(
        r"\b(?:tăng|giảm|tăng\s+thêm|giảm\s+bớt|tăng\s+trưởng|biến\s+động|thay\s+đổi|tuyển\s+mới|tuyển\s+dụng|thuê\s+mới|nghỉ\s+việc|thôi\s+việc|điều\s+động)\s+"
        r"(?:khoảng\s+|hơn\s+|gần\s+)?\d+\s*(?:người|lao\s*động|nhân\s*viên|cbcnv|cbnv|lao\s*dng)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:tăng|giảm)\s+(?:so\s+với\s+[^\n,.]+?|khoảng\s+|hơn\s+|gần\s+)?(?:là\s+)?\d+\s*(?:người|lao\s*động|nhân\s*viên|nhân\s*sự)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:tổng\s+số\s+lao\s+động|tổng\s+số\s+nhân\s+sự|số\s+lượng\s+lao\s+động)\s+(?:thuê\s+mới|tuyển\s+mới|nghỉ\s+việc|thôi\s+việc|tăng|giảm)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:có\s+trình\s+độ\s+từ|trình\s+độ\s+từ\s+[^\n,.]+?\s+trở\s+lên|trung\s+cấp\s+trở\s+lên|đại\s+học\s+trở\s+lên)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:tiêm\s+(?:ngừa|chủng)|vắc\s*xin|vacxin|covid|khẩu\s+trang)\b",
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
    r"đến\s+31[/.\s-]*(?:12|tháng\s*12)",
    r"tính\s+đến\s+31[/.\s-]*(?:12|tháng\s*12)",
    r"cuối năm",
    r"cuối kỳ",
    r"tính đến",
    r"tại thời điểm",
    r"vào thời điểm",
    r"đến ngày",
    r"đến thời điểm",
    r"tại ngày",
    r"1/1/\d{4}",
    r"01/01/\d{4}",
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

# Đơn vị nhân viên tiếng Việt (bao gồm cả dạng không dấu & font legacy)
_UNIT_VI = (
    r"(?:nhân\s*viên|người\s*lao\s*động|lao\s*động|CBCNV|CBNV|CB\s*[-–]\s*CNV|CB\s*[-–]\s*CN|CB\s*[-–]\s*NV|"
    r"cán\s*bộ\s*(?:,?\s*)?(?:công\s*nhân\s*)?viên|cán\s*bộ|nhân\s*sự|người|ngiroi|nguai|nguoi|"
    r"lao\s*dng|lao\s*dqng|lao\s*tlqng)"
)

# Đơn vị nhân viên tiếng Anh
_UNIT_EN = (
    r"(?:employees?|personnel|staff|workers?|people|persons?|headcount|FTEs?)"
)

# Pattern số: 1.750, 54,646 (có phân cách) hoặc 1072, 2152 (4-6 chữ số liền nhau) hoặc 1-999
_NUM_PATTERN = r"(?:\d{1,3}(?:[.,\s]\d{3})+|\d{4,6}|\d{1,3})"

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

# Pattern 5: Trích năm từ context
RE_YEAR = re.compile(r"(?:20[12]\d)")

# Pattern 6: Trích ngày 31/12/YYYY hoặc 01/01/YYYY (đầu năm = cuối năm trước)
RE_DATE_31_12 = re.compile(
    r"(?:31[/.\s-]*(?:12|december|tháng\s*12)[/.\s-]*(\d{4})|"
    r"thời\s+điểm\s+31[/.\s-]*(?:12|tháng\s*12)[/.\s-]*(\d{4})|"
    r"đến\s+31[/.\s-]*(?:12|tháng\s*12)[/.\s-]*(\d{4})|"
    r"0?1[/.\s-]*(?:0?1|january|tháng\s*1)[/.\s-]*(\d{4}))",
    re.IGNORECASE,
)


def normalize_number(raw: str) -> int:
    """
    Chuyển chuỗi số Vietnamese/English → int.
    
    Rules:
    - "9.960" (VN: dấu . phân hàng nghìn) → 9960
    - "54,646" (EN: dấu , phân hàng nghìn) → 54646
    - "1 250" (khoảng trắng phân cách) → 1250
    - "1.O5O" (OCR nhầm O thành 0) → 1050
    - "1.255" → ambiguous (VN: 1255, EN: 1.255) → kiểm tra:
      - Nếu sau dấu . có đúng 3 chữ số → hàng nghìn → 1255
      - Nếu không → giữ nguyên
    """
    s = raw.strip()
    if not s:
        return 0

    # Fix OCR letter substitutions (O/o -> 0)
    if re.search(r"\d[oO]|[oO]\d", s):
        s = s.replace("O", "0").replace("o", "0")

    # Space-separated thousands: "1 250"
    if " " in s:
        parts = s.split()
        if all(p.isdigit() for p in parts):
            return int("".join(parts))

    # Trường hợp chỉ có dấu chấm: "9.960" → 9960, hoặc "35.8783" (3 là footnote) → 35878
    if "." in s and "," not in s:
        parts = s.split(".")
        # Nếu tất cả phần sau dấu . đều có 3 chữ số → phân hàng nghìn
        if all(len(p) == 3 for p in parts[1:]):
            return int(s.replace(".", ""))
        elif len(parts) == 2 and len(parts[1]) == 4 and parts[0].isdigit() and parts[1].isdigit():
            # Trailing footnote attached (e.g. 35.8783 -> 35878)
            return int(parts[0] + parts[1][:3])
        else:
            # Số thập phân thật → làm tròn
            try:
                return int(float(s))
            except ValueError:
                return 0

    # Trường hợp chỉ có dấu phẩy: "54,646" → 54646
    if "," in s and "." not in s:
        parts = s.split(",")
        if all(len(p) == 3 for p in parts[1:]):
            return int(s.replace(",", ""))
        else:
            try:
                return int(float(s.replace(",", ".")))
            except ValueError:
                return 0

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
    clean_digits = re.sub(r"[^\d]", "", s)
    return int(clean_digits) if clean_digits else 0
