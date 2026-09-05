<p align="center">
  <h1 align="center">vn-annual-report-miner</h1>
  <p align="center">
    <strong>Công cụ khai phá dữ liệu Báo cáo Thường niên & Báo cáo Tài chính Doanh nghiệp niêm yết Việt Nam</strong>
  </p>
  <p align="center">
    Tự động quét từ khóa văn bản BCTN, tải tệp PDF gốc từ kho lưu trữ Zenodo, phân tích 702 chỉ tiêu BCTC và 75 tỷ số tài chính chuẩn, xuất Panel Data chuẩn cho hồi quy kinh tế lượng (OLS, FEM, REM, GMM).
  </p>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.9+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-22c55e?style=flat-square" alt="License: MIT"></a>
  <a href="#cài-đặt"><img src="https://img.shields.io/badge/pip_install-vn--annual--report--miner-blue?style=flat-square&logo=pypi&logoColor=white" alt="PyPI"></a>
  <a href="#giao-diện-web-studio-ui"><img src="https://img.shields.io/badge/Web_UI-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white" alt="Web UI"></a>
</p>

---

## Dành cho ai?

Dự án được thiết kế chuyên biệt phục vụ các **nhà nghiên cứu kinh tế, tài chính, kế toán và quản trị doanh nghiệp**:

- **Không yêu cầu kỹ năng lập trình phức tạp**: Cung cấp giao diện đồ họa Web Studio tương tác trực quan cùng công cụ dòng lệnh CLI.
- **Tự chủ hoàn toàn biến số nghiên cứu**: Tự do nhập từ khóa nghiên cứu thông qua file văn bản TXT, bảng tính Excel, CSV hoặc YAML cho mọi chủ đề (ESG, Chuyển đổi số, Fintech, Trí tuệ nhân tạo AI, Blockchain, Trách nhiệm xã hội CSR...).
- **Kho lưu trữ 14,000+ Báo cáo Thường niên gốc**: Tích hợp danh mục BCTN từ kho Zenodo (giai đoạn 2000 - 2025), hỗ trợ trích xuất và tải về các file PDF gốc được đóng gói phân cấp theo Mã CK, Ngành hoặc Năm.
- **Dữ liệu Báo cáo Tài chính toàn diện**: Hỗ trợ 702 chỉ tiêu kế toán chuẩn mực phân bổ vào 13 nhóm và 75 chỉ số tài chính chuyên sâu chuẩn (bao gồm các chỉ tiêu đặc thù CTCK như nghiệp vụ ký quỹ Margin, tài sản FVTPL, AFS, HTM).
- **Hỗ trợ tự động lọc thông minh bằng VBA Macro trong Excel**: Cung cấp file `.xlsm` có sẵn Macro cho phép chọn mã chứng khoán để tự động lọc và đồng bộ dữ liệu giữa các sheet.
- **Đầu ra chuẩn mực cho nghiên cứu định lượng**: Xuất dữ liệu bảng Panel Data (Firm x Year) sẵn sàng đưa trực tiếp vào Stata (`.dta`), R, Python, SPSS hoặc Excel.

---

## Nguồn dữ liệu tích hợp & Lời cảm ơn (Data Sources & Acknowledgments)

Dự án `vn-annual-report-miner` được phát triển trên cơ sở tích hợp và kế thừa 2 bộ dữ liệu học thuật mở vô cùng giá trị do tác giả **Ngo Phu Thanh (Trường Đại học Kinh tế - Luật, ĐHQG TP.HCM - UEL)** xây dựng và công bố cho cộng đồng nghiên cứu:

1. **Kho Báo cáo Thường niên PDF (Zenodo Dataset)**:
   - **Tên bộ dữ liệu**: *Vietnam Listed Companies Annual Reports PDF Dataset, 2000–2025*
   - **Tác giả**: Ngo, Phu Thanh (University of Economics and Law - UEL, ORCID: [0000-0002-9174-4747](https://orcid.org/0000-0002-9174-4747))
   - **DOI**: [10.5281/zenodo.20949551](https://doi.org/10.5281/zenodo.20949551)
   - **Quy mô**: Gần 14,000 tệp PDF báo cáo thường niên gốc của các công ty niêm yết trên thị trường chứng khoán Việt Nam từ năm 2000 đến 2025, kèm theo bảng chỉ mục tổng hợp và mã băm SHA256.

2. **Dữ liệu Báo cáo Tài chính dạng bảng (Hugging Face & vnfinancialdata)**:
   - **Tên bộ dữ liệu**: *Vietnam Listed Companies Financial Statements Dataset*
   - **Thư viện Python**: [`vnfinancialdata`](https://pypi.org/project/vnfinancialdata/) ([GitHub: thanhnp-uel/vnfinancialdata](https://github.com/thanhnp-uel/vnfinancialdata))
   - **Kho lưu trữ Hugging Face**: [`thanhnp-uel/vietnam-listed-companies-financial-statements`](https://huggingface.co/datasets/thanhnp-uel/vietnam-listed-companies-financial-statements)
   - **Tác giả**: Ngo, Phu Thanh (`thanhnp-uel`, UEL)
   - **Quy mô**: Dữ liệu tài chính chuẩn hóa của 692 công ty niêm yết trên 2 sàn HSX và HNX, bao gồm 702 chỉ tiêu kế toán (Bảng cân đối kế toán, Kết quả kinh doanh, Lưu chuyển tiền tệ) giai đoạn 2014–2024.

3. **Hệ thống chỉ số tài chính phân tích**:
   - Tham chiếu và chuẩn hóa theo hệ thống công thức phân tích tài chính chuyên sâu của **WiData (WiGroup)**.

Nhóm nghiên cứu xin chân thành cảm ơn tác giả Ngo Phu Thanh và cộng đồng nghiên cứu UEL đã chia sẻ các nguồn tài nguyên dữ liệu mở quý báu cho nền nghiên cứu tài chính - kinh tế Việt Nam.

---

## Mục lục

- [Nguồn dữ liệu & Lời cảm ơn](#nguồn-dữ-liệu-tích-hợp--lời-cảm-ơn-data-sources--acknowledgments)
- [Cài đặt](#cài-đặt)
- [Bắt đầu nhanh trong 60 giây](#bắt-đầu-nhanh-trong-60-giây)
- [Giao diện Web Studio UI](#giao-diện-web-studio-ui)
- [Tải về Báo cáo Thường niên gốc dạng ZIP](#tải-về-báo-cáo-thường-niên-gốc-dạng-zip)
- [Hệ thống Báo cáo Tài chính & 75 Chỉ số](#hệ-thống-báo-cáo-tài-chính--75-chỉ-số)
- [File Excel Macro VBA và Hướng dẫn Lọc](#file-excel-macro-vba-và-hướng-dẫn-lọc)
- [Lệnh CLI đầy đủ](#lệnh-cli-đầy-đủ)
- [Định dạng từ khóa linh hoạt](#định-dạng-từ-khóa-linh-hoạt)
- [Thuật toán khớp mờ Fuzzy Matching](#thuật-toán-khớp-mờ-fuzzy-matching)
- [Kho BCTN Zenodo](#kho-bctn-zenodo-14000-báo-cáo)
- [Kiến trúc dự án](#kiến-trúc-dự-án)
- [Đóng góp & Giấy phép](#đóng-góp--giấy-phép)

---

## Cài đặt

### Bước 1: Clone mã nguồn từ GitHub

```bash
git clone https://github.com/Tumiqa/vn-annual-report-miner.git
cd vn-annual-report-miner
```

### Bước 2: Cài đặt gói thư viện

Khuyến nghị cài đặt bản chuẩn kèm module Báo cáo tài chính (`vnfinancialdata`):

```bash
pip install -e ".[financial]"
```

Hoặc cài đặt đầy đủ tất cả module nâng cao (OCR, Stata .dta, GPU, NLP):

```bash
pip install -e ".[full]"
```

Hoặc cài đặt nhanh qua file `requirements.txt`:

```bash
pip install -r requirements.txt
```

### Cài đặt từng module chuyên biệt (tùy chọn)

```bash
pip install -e ".[financial]"   # Dữ liệu BCTC 702 chỉ tiêu (vnfinancialdata)
pip install -e ".[stata]"       # Hỗ trợ xuất file định dạng Stata .dta
pip install -e ".[ocr]"         # OCR nâng cao (Tesseract + OpenCV)
pip install -e ".[gpu]"         # EasyOCR xử lý GPU
pip install -e ".[nlp]"         # Xử lý ngôn ngữ tự nhiên tiếng Việt
```

### Yêu cầu hệ thống

- Python phiên bản từ 3.9 trở lên
- Hệ điều hành: Windows, macOS, Linux
- RAM: Tối thiểu 4 GB (khuyến nghị 8 GB trở lên khi xử lý đồng thời nhiều tài liệu PDF)

---

## Bắt đầu nhanh trong 60 giây

### 1. Khởi chạy Giao diện Web Studio

```bash
arminer studio
# hoặc
arminer ui
```
Trình duyệt sẽ tự động mở địa chỉ `http://127.0.0.1:8000`.

### 2. Quét từ khóa nhanh qua dòng lệnh (CLI)

```bash
# Quét 1 file PDF đơn lẻ
arminer scan baocao.pdf -k "blockchain, hợp đồng thông minh, sổ cái phân tán"

# Quét toàn bộ thư mục và xuất file Excel
arminer scan ./data/pdfs/ -k "esg, phát thải ròng, kinh tế tuần hoàn" -o ket_qua_esg.xlsx

# Dùng bộ từ điển chuyên đề có sẵn (blockchain, esg, fintech)
arminer scan ./data/pdfs/ --topic esg -o panel_esg.xlsx
```

### 3. Tải và xử lý dữ liệu tài chính qua CLI

```bash
# Tải dữ liệu BCTC và tỷ số tài chính
arminer financial fetch -t VCB,HPG,VNM -y 2018-2024 -o fin_data.csv

# Ghép kết quả Text Mining và BCTC thành Panel Data hoàn chỉnh
arminer financial merge -f fin_data.csv -o merged_panel.xlsx
```

---

## Giao diện Web Studio UI

Web Studio là môi trường đồ họa khép kín cho toàn bộ quy trình nghiên cứu:

| Tab chức năng | Nội dung và Nghiệp vụ |
|---|---|
| **Kho Báo Cáo Zenodo** | Duyệt 13,982 bản ghi BCTN, lọc theo mã CK, ngành ICB, năm. Hỗ trợ chọn hàng loạt để khai phá nội dung hoặc tải về tệp gốc `.zip`. |
| **Báo Cáo Tài Chính** | Truy vấn 702 chỉ tiêu BCTC và 75 chỉ số WiData cho 693 mã niêm yết (HSX/HNX), xuất Excel đa sheet kèm Macro VBA, CSV và Stata. |
| **Biên Tập Từ Điển** | Quản lý hệ thống từ điển nghiên cứu: thêm, sửa, xóa từ khóa, phân nhóm chuyên mục (category), thiết lập trọng số và từ đồng nghĩa. |
| **Tải File Riêng** | Quét tài liệu PDF/TXT tự lưu trữ trên máy tính hoặc tải file trực tiếp lên giao diện để phân tích. |
| **Kết Quả Nghiên Cứu** | Trực quan hóa dữ liệu bảng Panel Data, xem đoạn trích ngữ cảnh (snippets), tải báo cáo Excel thống kê mô tả và ma trận tương quan. |
| **Ghép Nối Panel Data** | Tự động kết hợp biến Text Mining với biến Kế toán - Tài chính theo cặp khóa `(ticker, year)` để sẵn sàng ước lượng mô hình. |

---

## Tải về Báo cáo Thường niên gốc dạng ZIP

Hệ thống cho phép các nhà nghiên cứu tải trực tiếp các tệp PDF gốc nguyên bản từ kho lưu trữ Zenodo về máy tính với dung lượng tối ưu hóa qua HTTP Range Request (không cần tải gói nén 50GB của Zenodo).

### Cấu trúc tổ chức thư mục ZIP

Người dùng có thể lựa chọn 1 trong 3 cơ chế tổ chức thư mục tự động:

1. **Phân theo Mã Chứng Khoán (`structure: ticker`)** *(Khuyến nghị)*:
   ```text
   BCTN_Goc_ticker_20260905.zip
   ├── VCB/
   │   ├── VCB_2023_BCTN.pdf
   │   └── VCB_2022_BCTN.pdf
   ├── HPG/
   │   └── HPG_2023_BCTN.pdf
   └── Danh_Muc_Bao_Cao.csv
   ```
2. **Phân theo Ngành ICB Cấp 1 (`structure: sector`)**:
   ```text
   BCTN_Goc_sector_20260905.zip
   ├── Ngan_hang/
   │   └── VCB/
   │       └── VCB_2023_BCTN.pdf
   ├── Tai_nguyen_Co_ban/
   │   └── HPG/
   │       └── HPG_2023_BCTN.pdf
   └── Danh_Muc_Bao_Cao.csv
   ```
3. **Phân theo Năm báo cáo (`structure: year`)**:
   ```text
   BCTN_Goc_year_20260905.zip
   ├── 2023/
   │   ├── VCB/VCB_2023_BCTN.pdf
   │   └── HPG/HPG_2023_BCTN.pdf
   └── Danh_Muc_Bao_Cao.csv
   ```

### File chỉ mục `Danh_Muc_Bao_Cao.csv`
Nằm tại thư mục gốc của tệp ZIP, được tạo với định dạng UTF-8 BOM hiển thị chuẩn tiếng Việt trên Microsoft Excel, chứa các trường: `Mã CK`, `Năm`, `Ngành cấp 1`, `Ngành cấp 2`, `Tên file gốc`, `Đường dẫn trong ZIP`, `Dung lượng (KB)`, `Nguồn lưu trữ`, `Trạng thái`.

---

## Hệ thống Báo cáo Tài chính & 75 Chỉ số 

### 1. Phân loại 702 chỉ tiêu kế toán thành 13 nhóm chuẩn mực

Hệ thống cam kết xuất đầy đủ **100% (702 dòng)** chỉ tiêu cho từng doanh nghiệp trên bảng tính dọc theo năm, được gom nhóm theo trật tự kế toán chuẩn:

1. `CĐKT. TÀI SẢN NGẮN HẠN`: Tiền, đầu tư ngắn hạn, phải thu ngắn hạn, hàng tồn kho, tài sản ngắn hạn khác.
2. `CĐKT. TÀI SẢN DÀI HẠN`: Phải thu dài hạn, tài sản cố định, bất động sản đầu tư, tài sản dở dang, đầu tư dài hạn.
3. `CĐKT. NỢ PHẢI TRẢ NGẮN HẠN`: Phải trả người bán, người mua trả tiền trước, vay ngắn hạn, chi phí phải trả.
4. `CĐKT. NỢ PHẢI TRẢ DÀI HẠN`: Vay dài hạn, trái phiếu phát hành, dự phòng phải trả dài hạn.
5. `CĐKT. VỐN CHỦ SỞ HỮU`: Vốn góp của chủ sở hữu, thặng dư vốn cổ phần, các quỹ, lợi nhuận sau thuế chưa phân phối.
6. `KQKD. DOANH THU, CHI PHÍ, LỢI NHUẬN`: Doanh thu thuần, giá vốn hàng bán, chi phí tài chính, chi phí bán hàng, chi phí QLDN, LNTT, LNST.
7. `LCTT. DÒNG TIỀN TỪ HOẠT ĐỘNG KINH DOANH`: Lưu chuyển tiền thuần từ hoạt động kinh doanh (phương pháp trực tiếp và gián tiếp).
8. `LCTT. DÒNG TIỀN TỪ HOẠT ĐỘNG ĐẦU TƯ`: Tiền mua sắm/thanh lý TSCĐ, tiền cho vay, thu hồi đầu tư.
9. `LCTT. DÒNG TIỀN TỪ HOẠT ĐỘNG TÀI CHÍNH`: Tiền thu/trả nợ gốc vay, tiền phát hành cổ phiếu, cổ tức đã trả.
10. `LCTT. DÒNG TIỀN THUẦN, TIỀN CUỐI KÌ`: Lưu chuyển tiền thuần trong kỳ, tiền và tương đương tiền đầu/cuối kỳ.
11. `NGOẠI BẢNG. A TÀI SẢN CỦA CTCK VÀ TÀI SẢN QUẢN LÝ THEO CAM KẾT`: Tài sản tài chính nhận quản lý, tài sản bảo đảm.
12. `NGOẠI BẢNG. B TÀI SẢN VÀ CÁC KHOẢN PHẢI TRẢ VỀ TÀI SẢN QUẢN LÝ CAM KẾT VỚI KHÁCH HÀNG`: Tiền gửi của khách hàng về giao dịch chứng khoán, các nghĩa vụ cam kết.
13. `THUYẾT MINH. CÁC LOẠI TÀI SẢN TÀI CHÍNH`: Chi tiết tài sản tài chính FVTPL, HTM, AFS, các khoản cho vay và phải thu.

### 2. Hệ thống 75 tỷ số tài chính chuẩn 

Được chia thành 6 nhóm phân tích học thuật:

| Phân nhóm tỷ số | Các chỉ tiêu tiêu biểu | Đơn vị / Định dạng |
|---|---|---|
| **Hiệu quả sinh lời & Dòng tiền** | ROA, ROE, Biên lợi nhuận gộp, Biên lợi nhuận ròng, Biên EBIT, Thuế suất hiệu dụng, Vòng quay tổng tài sản, CFO/LNST, CFO/Tổng tài sản, CFO/VCSH | %, Lần |
| **Cơ cấu vốn & Thanh toán** | Nợ/Tổng tài sản, Nợ/VCSH, VCSH/Tổng tài sản, Đòn bẩy tài chính (Tổng tài sản/VCSH), Thanh toán hiện hành, Thanh toán nhanh | %, Lần |
| **Đặc thù CTCK & Nghiệp vụ Ký quỹ Margin** | Tỷ lệ cho vay Margin/VCSH, % Cho vay Margin/Tổng tài sản, % Ứng trước tiền bán, Lợi nhuận cho vay Margin, Lợi nhuận môi giới, Lợi nhuận tư vấn, % Phải thu dịch vụ CTCK | %, VND |
| **Cơ cấu tài sản tài chính & Chi phí** | % Tài sản FVTPL, % Tài sản AFS, % Tài sản HTM, % Tiền mặt, % Doanh thu môi giới, % Doanh thu tự doanh, % Chi phí môi giới, % Chi phí tự doanh, % Chi phí dự phòng | % |
| **Tăng trưởng cùng kỳ (YoY %)** | Tăng trưởng Doanh thu, LNTT, LNST, LNST Công ty mẹ, Tổng tài sản, VCSH, Nợ phải trả, Cho vay Margin, FVTPL, AFS, HTM, Tiền | % |
| **Quy mô tài chính** | Tổng tài sản, Vốn chủ sở hữu, Doanh thu thuần, LNST, LNST công ty mẹ, Dòng tiền CFO, Dòng tiền CFI, Dòng tiền CFF, Quy mô Logarit `ln(Tổng tài sản)` | VND, Số thực |

---

## File Excel Macro VBA và Hướng dẫn Lọc

Khi xuất dữ liệu tài chính từ Web Studio, hệ thống tự động sinh 2 file song song:
- `financial_data.xlsx`: File Excel chuẩn (không chứa mã Macro, tương thích mọi hệ điều hành và thiết bị di động).
- `financial_data.xlsm`: File Excel kích hoạt Macro VBA hỗ trợ tương tác nâng cao.

### Cấu trúc 5 Sheet trong Workbook

1. **`Bao_Cao_Tai_Chinh`**: Trình bày theo chiều dọc, cột phân loại 13 nhóm kế toán, các cột năm tài chính, có ô lọc tại `B2`.
2. **`Ty_So_Tai_Chinh`**: Trình bày 75 chỉ số, kèm cột phân nhóm, mã chỉ số, tên tiếng Việt và công thức tính toán.
3. **`Panel_Data_Goc`**: Dữ liệu bảng phẳng chuẩn hóa (779 cột: `ticker`, `year`, 702 chỉ tiêu kế toán, 75 tỷ số tài chính).
4. **`Codebook`**: Bảng từ điển mã biến phục vụ tra cứu định nghĩa, công thức và nguồn dữ liệu.
5. **`Huong_Dan_VBA`**: Bảng hướng dẫn sử dụng phím tắt và thao tác lọc mã chứng khoán.

### Cách sử dụng bộ lọc VBA trên file `.xlsm`

1. Khi mở file `financial_data.xlsm`, nhấn **Enable Editing** và **Enable Content** (hoặc *Enable Macros*).
2. Tại sheet `Bao_Cao_Tai_Chinh` hoặc `Ty_So_Tai_Chinh`:
   - **Cách 1 (Tự động)**: Nhấp vào ô **B2**, chọn mã chứng khoán từ danh sách thả xuống. Bảng tính sẽ tự động lọc ngay lập tức.
   - **Cách 2 (Nút bấm trên sheet)**:
     - Bấm `[ Lọc Mã CK ]` để áp dụng giá trị ô B2.
     - Bấm `[ Hiện Tất Cả ]` để xem toàn bộ danh sách doanh nghiệp.
     - Bấm `[ Đồng Bộ 2 Sheet ]` để áp dụng lựa chọn sang cả sheet Báo Cáo và Tỷ Số.
   - **Cách 3 (Phím tắt)**:
     - `Ctrl + Shift + F`: Lọc theo mã đang chọn tại B2.
     - `Ctrl + Shift + A`: Hủy lọc, hiện tất cả mã.
     - `Ctrl + Shift + S`: Đồng bộ lựa chọn sang cả hai sheet.

---

## Lệnh CLI đầy đủ

```bash
arminer --help
```

| Lệnh CLI | Mô tả chức năng |
|---|---|
| `arminer studio` / `arminer ui` | Khởi chạy giao diện Web Studio trên trình duyệt |
| `arminer scan` | Quét từ khóa trực tiếp trên file PDF hoặc thư mục chứa nhiều file |
| `arminer financial` | Tải dữ liệu BCTC và tỷ số, ghép nối panel data |
| `arminer catalog` | Tìm kiếm và duyệt danh mục 14,000+ BCTN từ kho Zenodo |
| `arminer dict` | Kiểm tra, thống kê và xuất khẩu từ điển nghiên cứu |
| `arminer init` | Khởi tạo thư mục dự án nghiên cứu mới theo cấu trúc chuẩn |
| `arminer run` | Thực thi toàn bộ quy trình nghiên cứu theo kịch bản cấu hình |

### Chi tiết tham số lệnh `arminer scan`

```bash
arminer scan [TARGET] [OPTIONS]

Tham số:
  -k, --keywords TEXT    Danh sách từ khóa: "blockchain, smart contract, DeFi"
  --dict TEXT            Đường dẫn file từ khóa (.txt, .csv, .xlsx, .yaml)
  -t, --topic TEXT       Từ điển tích hợp: blockchain, esg, fintech
  -o, --output TEXT      Đường dẫn file kết quả (.xlsx, .csv, .dta, .parquet)
  --fuzzy / --no-fuzzy   Bật hoặc tắt khớp mờ (Mặc định: Bật)
  --threshold INTEGER    Ngưỡng tương đồng khớp mờ từ 0 - 100 (Mặc định: 85)
  --limit INTEGER        Giới hạn số lượng file cần quét
```

---

## Định dạng từ khóa linh hoạt

Hệ thống hỗ trợ 4 định dạng cung cấp từ khóa:

### 1. File văn bản Text (`.txt`)
```text
# Phân nhóm chuyên mục bằng ngoặc vuông
[Moi_Truong]
phát thải ròng
năng lượng tái tạo
kinh tế tuần hoàn

[Quan_Tri]
hội đồng quản trị
kiểm toán độc lập
minh bạch thông tin
```

### 2. File Bảng tính Excel (`.xlsx`) hoặc CSV
| keyword | category | variants |
|---|---|---|
| phát thải ròng | Môi trường | net zero, giảm phát thải |
| năng lượng tái tạo | Môi trường | năng lượng xanh, điện mặt trời |
| hội đồng quản trị | Quản trị | HĐQT, ban quản trị |

### 3. Cấu hình YAML chuyên sâu
```yaml
name: ESG Research Dictionary
version: "1.0"
categories:
  Environmental:
    - keyword: phát thải ròng
      weight: 1.0
      variants: [net zero, giảm phát thải]
    - keyword: kinh tế tuần hoàn
      weight: 1.0
      variants: [kinh tế xanh, tái chế]
```

### 4. Nhập trực tiếp trên dòng lệnh
```bash
arminer scan report.pdf -k "chuyển đổi số, điện toán đám mây, dữ liệu lớn"
```

---

## Thuật toán khớp mờ Fuzzy Matching

Để giải quyết triệt để vấn đề văn bản tiếng Việt quét từ tài liệu scan OCR, `arminer` sử dụng cơ chế so khớp trượt (Sliding-window Levenshtein) tối ưu:

- **Khắc phục lỗi OCR phổ biến**: Tự động nhận diện `"bIockchain"` tương đồng với `"blockchain"`.
- **Phân biệt chuẩn xác dấu tiếng Việt**: Phân biệt ngữ nghĩa giữa `"phi tập trung"` và `"phí tập trung"`, bảo vệ tính đúng đắn của dữ liệu.
- **Xử lý từ ghép và khoảng trắng**: Tự động liên kết `"block chain"` và `"blockchain"`.
- **Ngưỡng nhận diện thích ứng (Adaptive Threshold)**: Tự động nâng cao ngưỡng khắt khe đối với các từ khóa ngắn (<= 4 ký tự) để hạn chế tối đa sai số dương tính giả (False Positive).

---

## Kho BCTN Zenodo (14,000+ báo cáo)

| Tiêu chí | Thông số |
|---|---|
| Tổng số lượng báo cáo PDF | 13,982 bản ghi |
| Số lượng doanh nghiệp | 1,421 mã chứng khoán |
| Khoảng thời gian thu thập | 2000 – 2025 |
| Cơ chế phân ngành | Chuẩn ICB Cấp 1 và Cấp 2 |
| Phương thức tải | Phân đoạn theo nhu cầu (HTTP Range Request) |

---

## Kiến trúc dự án

```text
vn-annual-report-miner/
├── src/arminer/
│   ├── cli.py                  # Điểm khởi động giao diện dòng lệnh CLI (Click)
│   ├── core/                   # Xử lý thông minh, từ điển và cấu hình
│   │   ├── smart_mode.py       # Tính toán các biến nghiên cứu và làm sạch dữ liệu
│   │   ├── dictionary.py       # Bộ phân giải từ điển đa định dạng
│   │   └── dictionary_manager.py # Quản lý CRUD từ điển
│   ├── mining/
│   │   └── matcher.py          # Thuật toán so khớp mờ Fuzzy Matching
│   ├── data/
│   │   ├── catalog.py          # Quản lý danh mục báo cáo tổng hợp (Local & Zenodo)
│   │   ├── financial.py        # Module kết nối vnfinancialdata
│   │   ├── industry.py         # Phân loại ngành doanh nghiệp theo chuẩn ICB
│   │   └── zenodo_downloader.py# Tải file PDF trực tiếp từ Zenodo bằng Range Request
│   ├── export/
│   │   ├── financial_excel.py  # Xuất bản báo cáo tài chính 13 nhóm và 75 chỉ số
│   │   ├── zip_export.py       # Đóng gói và phân cấp thư mục tệp ZIP BCTN gốc
│   │   └── excel.py            # Xuất bản bảng dữ liệu Text Mining đa sheet
│   ├── ui/
│   │   ├── server.py           # Máy chủ ứng dụng FastAPI và giao thức SSE
│   │   └── static/             # Giao diện người dùng Web Studio (HTML, CSS, JS)
│   └── templates/              # Bộ từ điển và biểu mẫu Excel Macro tích hợp sẵn
├── tests/                      # Bộ kiểm thử tự động Pytest
├── pyproject.toml              # Cấu hình gói thư viện và môi trường phụ thuộc
├── LICENSE                     # Giấy phép phần mềm MIT
└── README.md                   # Tài liệu hướng dẫn sử dụng tổng thể
```

---

## Đóng góp & Giấy phép

### Đóng góp cho dự án

Dự án khuyến khích các đóng góp học thuật từ cộng đồng:
- Xây dựng bộ từ điển mới phục vụ các chủ đề nghiên cứu chuyên sâu.
- Nâng cấp mô hình phân đoạn từ vựng và nhận dạng thực thể tiếng Việt.
- Bổ sung các chỉ báo tài chính kinh tế lượng phục vụ nghiên cứu thực nghiệm.

### Giấy phép

Dự án phát hành theo giấy phép tự do [MIT License](LICENSE), cho phép sử dụng hoàn toàn miễn phí cho mục đích học thuật, nghiên cứu khoa học, giảng dạy và ứng dụng thực tiễn.

### Trích dẫn học thuật

Nếu công cụ hoặc dữ liệu hỗ trợ công trình nghiên cứu của bạn, vui lòng trích dẫn đầy đủ công cụ và các bộ dữ liệu nguồn theo định dạng:

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
  doi          = {10.5281/zenodo.20949551},
  url          = {https://doi.org/10.5281/zenodo.20949551}
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
  <strong>Được phát triển bởi Truong Minh Quan - DUE</strong><br>
  <em>Phục vụ cộng đồng nghiên cứu kinh tế, tài chính và quản trị tại Việt Nam</em>
</p>
