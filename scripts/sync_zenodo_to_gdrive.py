# -*- coding: utf-8 -*-
"""
scripts/sync_zenodo_to_gdrive.py
=================================
Công cụ tự động đồng bộ toàn bộ 13,982 báo cáo tài chính từ Zenodo sang Google Drive.
Chạy được trên cả:
1. Google Colab (Cloud-to-Cloud siêu tốc ~1 Gbps, không tốn ổ đĩa cá nhân).
2. Máy tính cá nhân PC (tải theo từng giai đoạn tùy chọn).

Cú pháp sử dụng:
    python scripts/sync_zenodo_to_gdrive.py --period 2006_2010
    python scripts/sync_zenodo_to_gdrive.py --period all
"""
import argparse
import os
import re
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


def sync_period(period: str, gdrive_target: Path, temp_dir: Path):
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
        print(f"[*] Đang tải trực tiếp file nén từ Zenodo ({url})...")
        with requests.get(url, stream=True, timeout=60) as r:
            r.raise_for_status()
            total_len = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(zip_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=10 * 1024 * 1024):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_len:
                            pct = (downloaded / total_len) * 100
                            print(f"\r  Đã tải: {downloaded / (1024*1024):.1f} MB / {total_len / (1024*1024):.1f} MB ({pct:.1f}%)", end="")
        print(f"\n✅ Tải xong file nén: {zip_path.name}")
    else:
        print(f"[*] Sử dụng file nén có sẵn: {zip_path.name}")

    print(f"[*] Đang giải nén và chuẩn hóa vào Google Drive...")
    pattern = re.compile(r"([A-Z0-9]{2,10})_(\d{2,4})", re.IGNORECASE)

    extracted_count = 0
    with zipfile.ZipFile(zip_path, "r") as z:
        for member in z.infolist():
            if member.is_dir() or not member.filename.lower().endswith(".pdf"):
                continue

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
                    print(f"  Đã đồng bộ {extracted_count} báo cáo...")

    print(f"✅ Hoàn tất giai đoạn {period}: Đã đưa {extracted_count} báo cáo vào Google Drive!")


def main():
    parser = argparse.ArgumentParser(description="Sync Zenodo archives directly to Google Drive")
    parser.add_argument("--period", choices=list(ZENODO_ARCHIVES.keys()) + ["all"], default="2006_2010", help="Giai đoạn cần đồng bộ")
    parser.add_argument("--temp-dir", default=None, help="Thư mục tạm để lưu file zip khi tải")
    args = parser.parse_args()

    gdrive_target = get_gdrive_target()
    print(f"Google Drive target folder: {gdrive_target}")

    temp_dir = Path(args.temp_dir) if args.temp_dir else Path.cwd() / "data" / "zenodo_temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    if args.period == "all":
        for p in ("2006_2010", "2011_2015", "2016_2020", "2021_2025"):
            sync_period(p, gdrive_target, temp_dir)
    else:
        sync_period(args.period, gdrive_target, temp_dir)


if __name__ == "__main__":
    main()
