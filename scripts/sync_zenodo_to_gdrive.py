# -*- coding: utf-8 -*-
r"""
scripts/sync_zenodo_to_gdrive.py
=================================
Công cụ tự động đồng bộ báo cáo tài chính từ Zenodo sang Google Drive.
Hỗ trợ:
1. Tải siêu tốc bằng aria2c (16 luồng song song, tối đa băng thông).
2. Trích xuất trực tiếp từ file ZIP tải thủ công (IDM, trình duyệt, v.v.).
3. Tương thích cả Google Colab (Cloud-to-Cloud) và máy tính cá nhân PC.

Cú pháp sử dụng:
    # 1. Trích xuất từ file zip đã tải thủ công bằng IDM trên PC:
    python scripts/sync_zenodo_to_gdrive.py --from-zip "F:\vn_bctn_2006_2010.zip"

    # 2. Tự động tải và đồng bộ theo từng giai đoạn:
    python scripts/sync_zenodo_to_gdrive.py --period 2006_2010 --temp-dir "F:\zenodo_temp"

    # 3. Đồng bộ toàn bộ trên Colab hoặc PC:
    python scripts/sync_zenodo_to_gdrive.py --period all --temp-dir "/content"
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
import requests

# Set stdout encoding for Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ZENODO_ARCHIVES = {
    "2006_2010": {
        "url": "https://zenodo.org/api/records/20949551/files/vn_bctn_2006_2010.zip/content",
        "size_gb": 3.86,
    },
    "2011_2015": {
        "url": "https://zenodo.org/api/records/20949551/files/vn_bctn_2011_2015.zip/content",
        "size_gb": 17.40,
    },
    "2016_2020": {
        "url": "https://zenodo.org/api/records/20949551/files/vn_bctn_2016_2020.zip/content",
        "size_gb": 47.56,
    },
    "2021_2025": {
        "url": "https://zenodo.org/api/records/20949551/files/vn_bctn_2021_2025.zip/content",
        "size_gb": 56.58,
    },
}


def get_gdrive_target() -> Path:
    """Tự động phát hiện thư mục arminer_bctn_gap trên Google Drive."""
    # Colab
    for cand in [
        Path("/content/drive/MyDrive/arminer_bctn_gap"),
        Path("/content/drive/Shareddrives/arminer_bctn_gap"),
        Path("/content/arminer_bctn_gap"),
    ]:
        if cand.exists():
            return cand

    # Windows Drive for Desktop
    for dl in ("H", "I", "G", "D"):
        cand = Path(f"{dl}:\\My Drive\\arminer_bctn_gap")
        if cand.exists():
            return cand

    env_p = os.environ.get("ARMINER_GDRIVE_PATH")
    if env_p and Path(env_p).exists():
        return Path(env_p)

    # Fallback to local data folder
    fb = Path.cwd() / "data" / "arminer_bctn_gap"
    fb.mkdir(parents=True, exist_ok=True)
    return fb


def download_file(url: str, dest_path: Path):
    """Tải file hỗ trợ tăng tốc 16 luồng qua aria2c nếu có, hoặc requests dự phòng."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    
    aria2_bin = shutil.which("aria2c")
    if aria2_bin:
        print(f"[*] 🚀 Phát hiện aria2c! Bắt đầu tải tăng tốc 16 luồng song song...")
        cmd = [
            aria2_bin,
            "-x", "16",
            "-s", "16",
            "-k", "1M",
            "--file-allocation=none",
            "--continue=true",
            "-d", str(dest_path.parent),
            "-o", dest_path.name,
            url,
        ]
        ret = subprocess.run(cmd)
        if ret.returncode == 0 and dest_path.exists():
            print(f"✅ Tải xong siêu tốc qua aria2c: {dest_path.name}")
            return
        print("[!] aria2c gặp lỗi, chuyển về phương thức tải tiêu chuẩn...")

    print(f"[*] Đang tải trực tiếp file nén từ Zenodo ({url})...")
    headers = {}
    downloaded = 0
    if dest_path.exists():
        downloaded = dest_path.stat().st_size
        headers["Range"] = f"bytes={downloaded}-"
        print(f"[*] Tiếp tục tải nối tiếp từ byte {downloaded}...")

    mode = "ab" if downloaded > 0 else "wb"
    with requests.get(url, stream=True, headers=headers, timeout=60) as r:
        if r.status_code == 416: # Range not satisfiable (already fully downloaded)
            return
        r.raise_for_status()
        total_len = int(r.headers.get("content-length", 0)) + downloaded
        with open(dest_path, mode) as f:
            for chunk in r.iter_content(chunk_size=10 * 1024 * 1024):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_len:
                        pct = (downloaded / total_len) * 100
                        print(f"\r  Đã tải: {downloaded / (1024*1024):.1f} MB / {total_len / (1024*1024):.1f} MB ({pct:.1f}%)", end="")
    print(f"\n✅ Tải xong file nén: {dest_path.name}")


def extract_zip_to_gdrive(zip_path: Path, gdrive_target: Path, delete_after: bool = False):
    """Trích xuất và chuẩn hóa phân loại ticker vào Google Drive."""
    if not zip_path.exists():
        print(f"❌ Không tìm thấy file zip: {zip_path}")
        return

    print(f"\n[*] Đang giải nén và phân loại chuẩn hóa vào Google Drive: {gdrive_target}")
    pattern = re.compile(r"([A-Z0-9]{2,10})_(\d{2,4})", re.IGNORECASE)

    extracted_count = 0
    skipped_count = 0
    with zipfile.ZipFile(zip_path, "r") as z:
        members = [m for m in z.infolist() if not m.is_dir() and m.filename.lower().endswith(".pdf")]
        total_members = len(members)
        print(f"[*] Tìm thấy {total_members} file PDF trong archive...")

        for member in members:
            fname = Path(member.filename).name
            m = pattern.search(fname)
            if m:
                ticker = m.group(1).upper()
                raw_yr = m.group(2)
                yr = int(raw_yr) if len(raw_yr) == 4 else (2000 + int(raw_yr) if int(raw_yr) < 50 else 1900 + int(raw_yr))
                target_fname = f"{ticker}_{yr}_BCTN.pdf"
            else:
                ticker = "MISC"
                target_fname = fname

            dest_folder = gdrive_target / ticker
            dest_file = dest_folder / target_fname

            if not dest_file.exists() or dest_file.stat().st_size < 1000:
                dest_folder.mkdir(parents=True, exist_ok=True)
                with z.open(member) as src, open(dest_file, "wb") as dst:
                    dst.write(src.read())
                extracted_count += 1
                if extracted_count % 100 == 0:
                    print(f"  Đã đồng bộ {extracted_count}/{total_members} báo cáo mới...")
            else:
                skipped_count += 1

    print(f"✅ Hoàn tất trích xuất: Đã thêm mới {extracted_count} báo cáo (Đã có sẵn: {skipped_count}).")

    if delete_after:
        try:
            zip_path.unlink()
            print(f"🧹 Đã xóa file zip {zip_path.name} để giải phóng dung lượng đĩa.")
        except Exception as e:
            print(f"[!] Không thể xóa file zip: {e}")


def sync_period(period: str, gdrive_target: Path, temp_dir: Path, clean_zip: bool = False):
    if period not in ZENODO_ARCHIVES:
        print(f"❌ Giai đoạn không hợp lệ: {period}. Chọn trong: {list(ZENODO_ARCHIVES.keys())}")
        return

    info = ZENODO_ARCHIVES[period]
    url = info["url"]
    print(f"\n=======================================================")
    print(f"  BẮT ĐẦU ĐỒNG BỘ GIAI ĐOẠN: {period} (~{info['size_gb']:.2f} GB)")
    print(f"  Đích đến: {gdrive_target}")
    print(f"=======================================================")

    zip_path = temp_dir / f"vn_bctn_{period}.zip"
    if not zip_path.exists():
        download_file(url, zip_path)
    else:
        print(f"[*] Sử dụng file nén có sẵn: {zip_path.name} ({zip_path.stat().st_size / (1024**3):.2f} GB)")

    extract_zip_to_gdrive(zip_path, gdrive_target, delete_after=clean_zip)


def main():
    parser = argparse.ArgumentParser(description="Sync Zenodo archives directly to Google Drive")
    parser.add_argument("--period", choices=list(ZENODO_ARCHIVES.keys()) + ["all"], default=None, help="Giai đoạn cần đồng bộ")
    parser.add_argument("--from-zip", default=None, help="Đường dẫn đến file zip đã tải thủ công (vd: F:\\vn_bctn_2006_2010.zip)")
    parser.add_argument("--temp-dir", default=None, help="Thư mục tạm để lưu file zip khi tải (Nên chọn ổ có dung lượng lớn như F:)")
    parser.add_argument("--clean-zip", action="store_true", help="Tự động xóa file zip sau khi trích xuất để tiết kiệm dung lượng")
    args = parser.parse_args()

    gdrive_target = get_gdrive_target()
    print(f"Google Drive target folder: {gdrive_target}")

    # Case 1: Người dùng đã tải file zip thủ công
    if args.from_zip:
        zip_p = Path(args.from_zip)
        extract_zip_to_gdrive(zip_p, gdrive_target, delete_after=args.clean_zip)
        return

    # Case 2: Tải tự động
    temp_dir = Path(args.temp_dir) if args.temp_dir else Path.cwd() / "data" / "zenodo_temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    period = args.period if args.period else "2006_2010"
    if period == "all":
        for p in ("2006_2010", "2011_2015", "2016_2020", "2021_2025"):
            sync_period(p, gdrive_target, temp_dir, clean_zip=args.clean_zip)
    else:
        sync_period(period, gdrive_target, temp_dir, clean_zip=args.clean_zip)


if __name__ == "__main__":
    main()
