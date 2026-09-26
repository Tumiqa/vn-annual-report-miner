# -*- coding: utf-8 -*-
"""
Upload PDFs to Google Drive and auto-update drive_index.json + gap_manifest.csv.

Usage:
    1. First time: Run script → nó mở trình duyệt để xác thực Google Drive
    2. Đặt các file PDF cần upload vào thư mục data/gap_filler/upload/
       Tên file phải theo chuẩn: {TICKER}_{YEAR}_BCTN.pdf (VD: ACB_2015_BCTN.pdf)
    3. Chạy script:  python scripts/upload_gap_filler.py
    4. Script tự động:
       - Upload lên Google Drive shared folder
       - Cập nhật data/gap_filler/drive_index.json
       - Cập nhật data/gap_manifest.csv (status → uploaded)

Dependencies:
    pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import pandas as pd

# Project root
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
UPLOAD_DIR = DATA_DIR / "gap_filler" / "upload"
INDEX_FILE = DATA_DIR / "gap_filler" / "drive_index.json"
GAP_MANIFEST = DATA_DIR / "gap_manifest.csv"

# Google Drive folder ID — set this to your shared folder
DRIVE_FOLDER_ID = os.environ.get("GDRIVE_GAP_FOLDER_ID", "")


def parse_pdf_filename(filename: str):
    """Parse TICKER_YEAR_BCTN.pdf → (ticker, year)."""
    m = re.match(r"^([A-Z0-9]{2,10})_(\d{4})_BCTN\.pdf$", filename, re.IGNORECASE)
    if m:
        return m.group(1).upper(), int(m.group(2))
    return None, None


def get_drive_service():
    """Authenticate and return Google Drive API service."""
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        print("❌ Cần cài đặt: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
        sys.exit(1)

    SCOPES = ["https://www.googleapis.com/auth/drive.file"]
    creds = None
    token_file = DATA_DIR / "gap_filler" / ".gdrive_token.json"
    creds_file = DATA_DIR / "gap_filler" / "credentials.json"

    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not creds_file.exists():
                print(f"❌ Cần file credentials.json tại: {creds_file}")
                print("   Tạo tại: https://console.cloud.google.com/apis/credentials")
                print("   → Create Credentials → OAuth client ID → Desktop app → Download JSON")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)
            creds = flow.run_local_server(port=0)
        token_file.write_text(creds.to_json())

    return build("drive", "v3", credentials=creds)


def upload_simple(filepath: Path, folder_id: str) -> str:
    """Upload file to Google Drive using simple upload (no OAuth needed for shared folders).

    Alternative: Use gdown's upload or rclone for simpler auth.
    Returns the file ID.
    """
    from googleapiclient.http import MediaFileUpload

    service = get_drive_service()
    file_metadata = {
        "name": filepath.name,
        "parents": [folder_id],
    }
    media = MediaFileUpload(str(filepath), mimetype="application/pdf", resumable=True)
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id",
    ).execute()

    file_id = file.get("id")

    # Make publicly accessible
    service.permissions().create(
        fileId=file_id,
        body={"type": "anyone", "role": "reader"},
    ).execute()

    return file_id


def main():
    print("=" * 60)
    print("  📤 Gap Filler: Upload PDFs to Google Drive")
    print("=" * 60)

    if not DRIVE_FOLDER_ID:
        print("\n❌ Chưa cấu hình GDRIVE_GAP_FOLDER_ID!")
        print("   Cách làm:")
        print("   1. Tạo folder trên Google Drive")
        print("   2. Chia sẻ public (Anyone with link)")
        print("   3. Copy folder ID từ URL (phần sau /folders/)")
        print("   4. Set biến môi trường: set GDRIVE_GAP_FOLDER_ID=<folder_id>")
        print("      hoặc thêm vào file .env")
        return

    # Ensure upload dir exists
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # Find PDFs to upload
    pdfs = sorted(UPLOAD_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"\n⚠️  Không có file PDF nào trong: {UPLOAD_DIR}")
        print(f"   Đặt file PDF theo tên chuẩn: ACB_2015_BCTN.pdf")
        return

    # Load existing index
    if INDEX_FILE.exists():
        index = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    else:
        index = {}

    # Load gap manifest
    if GAP_MANIFEST.exists():
        manifest = pd.read_csv(GAP_MANIFEST, encoding="utf-8-sig")
    else:
        manifest = None

    print(f"\n📁 Tìm thấy {len(pdfs)} file PDF trong {UPLOAD_DIR}")
    uploaded = 0
    skipped = 0

    for pdf in pdfs:
        ticker, year = parse_pdf_filename(pdf.name)
        if not ticker:
            print(f"  ⚠️  Bỏ qua {pdf.name} (tên không đúng chuẩn TICKER_YEAR_BCTN.pdf)")
            skipped += 1
            continue

        key = f"{ticker}_{year}"
        if key in index and not key.startswith("_"):
            print(f"  ✓  {key} đã có trong index, bỏ qua")
            skipped += 1
            continue

        print(f"  📤 Đang upload {pdf.name}...", end=" ", flush=True)
        try:
            file_id = upload_simple(pdf, DRIVE_FOLDER_ID)
            index[key] = file_id
            print(f"✅ (ID: {file_id[:12]}...)")

            # Update manifest
            if manifest is not None:
                mask = (manifest["ticker"].str.upper() == ticker) & (manifest["year"] == year)
                if mask.any():
                    manifest.loc[mask, "search_status"] = "uploaded"
                    manifest.loc[mask, "source"] = "google_drive"

            uploaded += 1
        except Exception as e:
            print(f"❌ Lỗi: {e}")

    # Save updated index
    # Remove example entries
    clean_index = {k: v for k, v in index.items() if not k.startswith("_")}
    INDEX_FILE.write_text(
        json.dumps(clean_index, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Save updated manifest
    if manifest is not None:
        manifest.to_csv(GAP_MANIFEST, index=False, encoding="utf-8-sig")

    print(f"\n{'=' * 60}")
    print(f"  ✅ Upload xong: {uploaded} file | Bỏ qua: {skipped}")
    print(f"  📄 Index: {INDEX_FILE} ({len(clean_index)} entries)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
