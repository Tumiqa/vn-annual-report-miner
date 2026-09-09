<p align="center">
  <h1 align="center">vn-annual-report-miner</h1>
  <p align="center">
    <strong>Bộ công cụ khai phá Báo cáo Thường niên, Tin tức Báo chí Doanh nghiệp & Báo cáo Tài chính niêm yết Việt Nam</strong>
  </p>
  <p align="center">
    Khai phá từ khóa văn bản BCTN (14,000+ báo cáo Zenodo) • Khai phá tin tức đa nguồn (8 cổng báo chí & website ~1,433 doanh nghiệp) • Phân tích 702 chỉ tiêu BCTC & 75 tỷ số tài chính • Xuất Panel Data chuẩn cho hồi quy kinh tế lượng (Stata, Python, R, Excel VBA Macro)
  </p>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.9+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-22c55e?style=flat-square" alt="License: MIT"></a>
  <a href="#hướng-dẫn-cài-đặt--chạy-nhanh-3-bước-cho-mọi-máy"><img src="https://img.shields.io/badge/Cài_đặt-3_bước_siêu_tốc-blue?style=flat-square" alt="Quick Install"></a>
  <a href="#bước-3-bật-giao-diện-và-sử-dụng-100-bằng-chuột"><img src="https://img.shields.io/badge/Web_Studio-Trực_quan-009688?style=flat-square&logo=fastapi&logoColor=white" alt="Web UI"></a>
</p>

---

## Điểm nổi bật

- **Dành cho mọi người (kể cả chưa từng viết code)**: Cung cấp giao diện đồ họa Web Studio trực quan, thao tác hoàn toàn bằng chuột.
- **Cài đặt 1 lệnh trọn gói**: Tự động cài đặt toàn bộ tính năng (Web UI, BCTC 702 chỉ tiêu, Khai phá tin tức đa nguồn, xuất Stata `.dta`, thuật toán Fuzzy) trong duy nhất một lần chạy.
- **Tương thích mọi hệ điều hành**: Hoạt động mượt mà trên **Windows**, **macOS** (MacBook chip M1/M2/M3/Intel) và **Linux**.
- **Kho 14,000+ BCTN gốc (Zenodo 2000–2025)**: Tra cứu và tải các file PDF gốc được tự động phân nhóm theo Mã CK, Ngành hoặc Năm dạng ZIP; khai phá văn bản và hiển thị kết quả tại chỗ.
- **Khai phá Tin tức Đa nguồn (News Text Mining)**: Thu thập và khai phá toàn văn bài báo từ 8 nguồn tin lớn (CafeF, Tin Nhanh Chứng Khoán, VnEconomy, VnExpress Kinh Doanh, CafeBiz, VietnamNet, Website chính thức ~1,433 doanh nghiệp niêm yết) với bộ lọc năm thông minh và cơ chế bù đắp hạn ngạch tự động.
- **702 chỉ tiêu BCTC & 75 tỷ số tài chính**: Dữ liệu chuẩn mực của 692 công ty niêm yết (HSX & HNX), phân bổ 13 nhóm kế toán và các tỷ số WiData chuyên sâu (Margin, FVTPL, AFS...).
- **Excel Macro VBA thông minh (`.xlsm`)**: Tự động lọc mã chứng khoán theo ô `B2` và đồng bộ đa sheet chỉ với 1 click.
- **Đầu ra chuẩn Panel Data**: Sẵn sàng đưa vào Stata (`.dta`), R, Python (`.csv`, `.parquet`) hoặc Excel (`.xlsx`, `.xlsm`).

---

## Hướng dẫn cài đặt & Chạy nhanh 3 bước (Cho mọi máy)

> Dù máy của bạn dùng **Windows**, **macOS** hay **Linux**, và dù bạn **chưa từng học lập trình**, bạn chỉ cần làm theo đúng 3 bước đơn giản dưới đây:

### Bước 1: Cài đặt Python (Nếu máy tính chưa có)
- Tải bộ cài Python (phiên bản 3.9 trở lên) tại trang chủ: [python.org/downloads](https://www.python.org/downloads/)
- ⚠️ **Lưu ý quan trọng riêng cho Windows**: Khi cửa sổ cài đặt hiện lên, hãy **tích chọn vào ô vuông `Add python.exe to PATH`** ở dưới cùng rồi mới nhấn *Install Now*.

---

### Bước 2: Tải và cài đặt trọn gói (1 câu lệnh)

Mở cửa sổ dòng lệnh trên máy của bạn:
- **Windows**: Nhấn tổ hợp phím `Win + R`, gõ `cmd` (hoặc `powershell`) rồi nhấn **Enter**.
- **macOS (MacBook)**: Nhấn `Command + Space`, gõ `Terminal` rồi nhấn **Enter**.
- **Linux**: Nhấn `Ctrl + Alt + T`.

Sau đó sao chép và dán lệnh tương ứng với hệ điều hành của bạn:

#### 👉 Trên Windows:
```bash
git clone https://github.com/Tumiqa/vn-annual-report-miner.git
cd vn-annual-report-miner
pip install -e .
```

#### 👉 Trên macOS / Linux:
```bash
git clone https://github.com/Tumiqa/vn-annual-report-miner.git
cd vn-annual-report-miner
pip3 install -e .
```

> [!TIP]
> **Nếu máy tính chưa cài Git?** Rất đơn giản:
> 1. Nhấn vào nút xanh **`<> Code`** ở góc trên trang GitHub này ➔ Chọn **Download ZIP**.
> 2. Giải nén file ZIP vừa tải về máy tính.
> 3. Mở Terminal / CMD tại thư mục vừa giải nén, rồi chỉ cần gõ:
>    - Windows: `pip install -e .`
>    - macOS / Linux: `pip3 install -e .`

---

### Bước 3: Bật giao diện và sử dụng (100% bằng chuột)

Ngay tại cửa sổ dòng lệnh vừa cài đặt, bạn gõ lệnh sau để mở Web Studio:

```bash
arminer studio
```

*(Nếu máy báo không tìm thấy lệnh `arminer`, bạn chỉ cần dùng lệnh tương đương: `python -m arminer studio` trên Windows hoặc `python3 -m arminer studio` trên macOS/Linux).*

🎉 **Xong!** Trình duyệt web sẽ tự động mở trang **`http://127.0.0.1:8000`**. Giờ đây bạn có thể đóng cửa sổ lệnh và thao tác hoàn toàn bằng chuột trên giao diện trực quan.

---

## Sử dụng Dòng lệnh CLI (Dành cho người thích chạy script)

Nếu bạn muốn chạy trực tiếp qua dòng lệnh hoặc tích hợp vào quy trình tự động:

```bash
# 1. Quét từ khóa BCTN theo chủ đề có sẵn (esg, fintech, blockchain)
arminer scan ./data/pdfs/ --topic esg -o ket_qua_esg.xlsx

# 2. Quét từ khóa tự chọn
arminer scan ./data/pdfs/ -k "chuyển đổi số, điện toán đám mây, dữ liệu lớn" -o ket_qua_cds.xlsx

# 3. Tải BCTC 702 chỉ tiêu & 75 tỷ số tài chính
arminer financial fetch -t VCB,HPG,VNM -y 2018-2024 -o bctc.xlsx
```

---

## Chi tiết các tính năng & Dữ liệu

### 1. Phân hệ Web Studio

Web Studio cung cấp quy trình nghiên cứu khép kín với các phân hệ độc lập, tự hiển thị kết quả tại chỗ:

| Phân hệ | Nghiệp vụ nghiên cứu |
|---|---|
| **Báo Cáo Thường Niên (Zenodo)** | Tra cứu 13,982 BCTN, lọc theo Mã CK / Ngành / Năm, tải gói ZIP chứa PDF gốc, khai phá văn bản và hiển thị kết quả ngay tại chỗ. |
| **Khai Phá Tin Tức Đa Nguồn** | Thu thập và khai phá toàn văn bài báo từ 8 nguồn tin lớn (CafeF, Tin Nhanh CK, VnEconomy, VnExpress, CafeBiz, VietnamNet, Website chính thức ~1,433 DN), lọc theo dải năm, tự bù quota, xuất Panel Data. |
| **Báo Cáo Tài Chính** | Truy vấn 702 chỉ tiêu BCTC & 75 chỉ số tài chính, xuất Excel đa sheet kèm Macro VBA hoặc Stata. |
| **Biên Tập Từ Điển** | Quản lý hệ thống từ khóa nghiên cứu (phân nhóm category, từ đồng nghĩa, trọng số). |
| **Tải File Riêng** | Quét các tệp PDF/TXT lưu trữ trên máy tính cá nhân. |
| **Ghép Nối Dữ Liệu** | Tự động ghép nối biến Text Mining và biến Tài chính theo cặp `(ticker, year)` để ước lượng mô hình hồi quy. |

---

### 2. Phân hệ Khai phá Tin tức Doanh nghiệp Đa Nguồn (News Text Mining)

Phân hệ giải quyết bài toán nghiên cứu tâm lý thị trường, mức độ chú ý của truyền thông và công bố thông tin đột xuất của doanh nghiệp:

- **Bao phủ 8 nguồn tin tài chính & website doanh nghiệp**:
  - **Website chính thức của công ty**: Tự động liên kết danh bạ ~1,433 mã cổ phiếu trên 3 sàn HoSE, HNX, UPCoM; tích hợp cơ chế *Auto-Discovery* dò tìm domain và giao diện chỉnh sửa URL linh hoạt.
  - **6 cổng thông tin kinh tế - chứng khoán lớn chịu cào**: CafeF, Tin Nhanh Chứng Khoán (ĐTCK - cơ quan ngôn luận UBCKNN), VnEconomy, VnExpress Kinh Doanh, CafeBiz, VietnamNet Kinh Doanh.
  - **URL Tùy chỉnh & Chế độ Fallback**: Cho phép dán trực tiếp danh sách link bài viết hoặc dán toàn văn bài báo (Paste Text) khi website nguồn bật tường lửa chặn bot.
- **Cơ chế bù đắp hạn ngạch thông minh ("Thiếu nguồn này thì nguồn khác đắp vào")**: Khi người dùng đặt mục tiêu (ví dụ: 20 bài / mã CK), nếu website doanh nghiệp chỉ có vài bài hoặc lỗi kết nối, hệ thống tự động tăng hạn ngạch truy vấn sang các cổng báo chí lớn khác để đảm bảo luôn gom đủ quota cho phân tích.
- **Bộ lọc theo năm xuất bản (`Từ năm` — `Đến năm`)**: Thuật toán đa tầng tự động phân tích ngày đăng từ thẻ ISO datetime, cấu trúc URL slug và dòng mở đầu bài viết để lọc chuẩn xác các bài báo xuất bản trong dải năm nghiên cứu.
- **Trích xuất toàn văn sạch bằng Trafilatura**: Tự động loại bỏ hoàn toàn mã JavaScript, banner quảng cáo, menu điều hướng và bình luận rác.
- **Nhập mã siêu tốc & Phân cấp ngành ICB**: Hỗ trợ gõ/dán danh sách mã cách nhau bằng dấu phẩy (`VCB, BID, CTG, FPT...`), chọn theo 2 cấp ngành ICB (Cấp 1 & Cấp 2) với nút *Thêm theo ngành*, hoặc bấm chọn nhanh theo rổ chỉ số (VN30, VN100, HNX30, Ngân hàng, BĐS, Chứng khoán, Công nghệ).
- **Đầu ra chuẩn Panel Data**: Xuất file Excel 3 sheets (`Firm_Summary`, `Articles_Panel`, `Context_Snippets`), Stata `.dta` và CSV với đầy đủ biến tần suất, biến quy mô, từ khóa xuất hiện và đoạn ngữ cảnh highlight.

---

### 3. Tải BCTN gốc từ Zenodo dạng ZIP

Hệ thống cho phép tải trực tiếp file PDF gốc từ Zenodo về máy tính với tốc độ cao (Range Request) và tự động đóng gói theo 3 cấu trúc thư mục tùy chọn:

1. **Phân theo Mã CK (`ticker`)** *(Khuyên dùng)*:
   ```text
   BCTN_Goc_ticker.zip
   ├── VCB/VCB_2023_BCTN.pdf
   ├── HPG/HPG_2023_BCTN.pdf
   └── Danh_Muc_Bao_Cao.csv
   ```
2. **Phân theo Ngành ICB (`sector`)**: `Ngan_hang/VCB/VCB_2023_BCTN.pdf`...
3. **Phân theo Năm (`year`)**: `2023/VCB/VCB_2023_BCTN.pdf`...

*Tệp chỉ mục `Danh_Muc_Bao_Cao.csv` (UTF-8 BOM) nằm ở thư mục gốc của file ZIP, chứa đầy đủ mã CK, năm, ngành, dung lượng và mã hash SHA256.*

---

### 4. Hệ thống Báo cáo Tài chính & 75 Tỷ số chuẩn

- **702 chỉ tiêu BCTC**: Phân bổ chuẩn mực theo 13 nhóm kế toán (Tài sản ngắn/dài hạn, Nợ phải trả ngắn/dài hạn, Vốn CSH, Kết quả KD, 4 nhóm Lưu chuyển tiền tệ, Ngoại bảng CTCK, Thuyết minh FVTPL/HTM/AFS).
- **75 tỷ số tài chính chuẩn hóa WiData**:
  - *Sinh lời & Dòng tiền*: ROA, ROE, ROS, Biên EBIT, Thuế suất hiệu dụng, Vòng quay tài sản, CFO/LNST, CFO/Tổng tài sản...
  - *Đòn bẩy & Thanh toán*: Nợ/VCSH, Nợ/Tổng tài sản, Đòn bẩy tài chính, Thanh toán hiện hành, Thanh toán nhanh...
  - *Đặc thù CTCK*: Tỷ lệ cho vay Margin/VCSH, % Margin/Tổng tài sản, Lợi nhuận cho vay Margin, Doanh thu môi giới...
  - *Cơ cấu tài sản & Chi phí*: % FVTPL, % AFS, % HTM, % Tiền mặt, % Chi phí hoạt động, Chi phí dự phòng...
  - *Tăng trưởng cùng kỳ (YoY)* & *Quy mô*: Tăng trưởng Doanh thu, LNST, Tài sản, VCSH, Quy mô Logarit `ln(Tổng tài sản)`...

### 5. File Excel chuyên nghiệp (`.xlsx`) — Chọn mã CK tự động

Khi xuất dữ liệu tài chính từ Web Studio, hệ thống tạo file `financial_data.xlsx` gồm 8 sheet:

| Sheet | Mô tả |
|-------|-------|
| **Trang_Bia** | Trang bìa tổng quan: mã CK, giai đoạn, nguồn dữ liệu |
| **Bao_Cao_Tai_Chinh** | 702 chỉ tiêu kế toán — **chọn mã CK tại ô B2** |
| **Ty_So_Tai_Chinh** | 75 tỷ số WiData — **chọn mã CK tại ô B2** |
| **Panel_Data_Goc** | Bảng phẳng Panel Data (tất cả mã) cho Stata/R/Python |
| **Codebook** | Từ điển biến, công thức tính toán |
| **Huong_Dan** | Hướng dẫn sử dụng |

**Cách lọc theo mã chứng khoán:**
1. Mở sheet `Bao_Cao_Tai_Chinh` hoặc `Ty_So_Tai_Chinh`.
2. Nhấp vào ô **B2** (viền vàng) → chọn mã CK từ dropdown.
3. **Toàn bộ dữ liệu tự động cập nhật** — không cần Macro, không cần bật VBA.

> **Hoạt động trên mọi phiên bản Excel** (Windows, macOS, Online, Google Sheets, LibreOffice).

---

### 6. Định dạng Từ khóa & Thuật toán Khớp mờ (Fuzzy Matching)

Hệ thống hỗ trợ nạp từ khóa linh hoạt từ file `.txt`, `.csv`, `.xlsx` hoặc `.yaml`:

```text
# Ví dụ file keywords.txt
[Môi_Trường]
phát thải ròng
năng lượng tái tạo
kinh tế tuần hoàn

[Quản_Trị]
hội đồng quản trị
kiểm toán độc lập
minh bạch thông tin
```

Thuật toán **Sliding-window Levenshtein** thích ứng:
- **Khắc phục lỗi OCR**: Tự động nhận diện `"bIockchain"` tương đồng với `"blockchain"`.
- **Bảo toàn dấu tiếng Việt**: Phân biệt chính xác giữa `"phi tập trung"` và `"phí tập trung"`.
- **Ngưỡng nhận diện thích ứng**: Tự động tăng độ khắt khe với các từ khóa ngắn (<= 4 ký tự) để hạn chế tối đa sai số dương tính giả (False Positive).

---

### 7. Bảng tra cứu lệnh CLI

```bash
arminer --help
```

| Lệnh | Cú pháp ví dụ | Chức năng |
|---|---|---|
| `studio` | `arminer studio` | Khởi chạy giao diện Web Studio trên trình duyệt |
| `scan` | `arminer scan ./pdfs/ --topic esg -o kq.xlsx` | Quét từ khóa trong tệp hoặc thư mục PDF |
| `financial` | `arminer financial fetch -t VCB,HPG -y 2020-2024 -o fin.csv` | Tải dữ liệu BCTC và tỷ số tài chính |
| `catalog` | `arminer catalog search --ticker VCB` | Tra cứu trong danh mục 14,000+ BCTN Zenodo |
| `dict` | `arminer dict stats --file keywords.txt` | Kiểm tra và thống kê số lượng từ khóa |
| `init` | `arminer init my_project --topic esg` | Khởi tạo thư mục dự án nghiên cứu mới |
| `run` | `arminer run --stage all` | Chạy toàn bộ luồng xử lý theo file cấu hình |

---

## Nguồn dữ liệu & Ghi nhận học thuật (Data Sources & Citation)

Dự án `vn-annual-report-miner` được phát triển trên cơ sở kế thừa và tích hợp 2 bộ dữ liệu học thuật mở của tác giả **Ngo Phu Thanh (Đại học Kinh tế - Luật, ĐHQG TP.HCM - UEL)**:

1. **Kho Báo cáo Thường niên PDF (Zenodo)**:
   - *Vietnam Listed Companies Annual Reports PDF Dataset, 2000–2025*
   - Tác giả: Ngo, Phu Thanh (UEL, ORCID: [0000-0002-9174-4747](https://orcid.org/0000-0002-9174-4747))
   - DOI: [10.5281/zenodo.20949551](https://doi.org/10.5281/zenodo.20949551) (Gần 14,000 tệp BCTN gốc của các doanh nghiệp niêm yết).
2. **Dữ liệu Báo cáo Tài chính chuẩn hóa**:
   - Thư viện Python: [`vnfinancialdata`](https://pypi.org/project/vnfinancialdata/) ([GitHub](https://github.com/thanhnp-uel/vnfinancialdata) / [Hugging Face](https://huggingface.co/datasets/thanhnp-uel/vietnam-listed-companies-financial-statements)).
   - 702 chỉ tiêu kế toán của 692 công ty niêm yết trên HSX và HNX (2014–2024).
3. **Hệ thống tỷ số tài chính**: Tham chiếu và chuẩn hóa theo phương pháp luận phân tích tài chính của **WiData (WiGroup)**.

### Trích dẫn nghiên cứu (BibTeX)

```bibtex
@software{arminer2026,
  title     = {vn-annual-report-miner: Text Mining and Financial Data Mining Tool for Vietnamese Annual Reports},
  author    = {Truong Minh Quan},
  year      = {2026},
  url       = {https://github.com/Tumiqa/vn-annual-report-miner},
  license   = {MIT}
}

@dataset{ngo_phu_thanh_2025_zenodo,
  author       = {Ngo, Phu Thanh},
  title        = {Vietnam Listed Companies Annual Reports PDF Dataset, 2000–2025},
  year         = {2025},
  publisher    = {Zenodo},
  doi          = {10.5281/zenodo.20949551}
}

@software{ngo_phu_thanh_2025_vnfinancialdata,
  author       = {Ngo, Phu Thanh},
  title        = {vnfinancialdata: A Python Package for Accessing Vietnamese Listed Companies Financial Statements},
  year         = {2025},
  url          = {https://github.com/thanhnp-uel/vnfinancialdata}
}
```

---

<p align="center">
  <strong>Được phát triển bởi Truong Minh Quan — DUE</strong><br>
  <em>Phục vụ cộng đồng nghiên cứu kinh tế, tài chính và quản trị tại Việt Nam</em><br>
  Phát hành theo giấy phép tự do <strong>MIT License</strong>.
</p>
