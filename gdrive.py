"""Google Drive 업로드 (REST v3 직접 호출 — googleapiclient 미사용으로 배포 경량화).

인증(설정 폴더 %APPDATA%/LodestarAgent 안의 파일로 자동 선택):
  1) service_account.json  ← 권장. 무인 PC에 적합(브라우저 로그인·토큰만료 없음).
     GCP 콘솔에서 SA 생성 → 키(JSON) 다운로드 → 대상 Drive 폴더를 SA 이메일에
     '편집자'로 공유해 두면 끝.
  2) client_secret.json    ← 일반 OAuth(데스크톱 앱). 최초 1회 브라우저 로그인,
     token.json으로 갱신.
"""

import json
import uuid
from pathlib import Path

import requests
from google.auth.transport.requests import Request as GARequest

from config import config_dir, log

SA_FILE = "service_account.json"
CS_FILE = "client_secret.json"
TOKEN_FILE = "token.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]


class DriveError(Exception):
    pass


def credentials_status() -> str:
    d = config_dir()
    if (d / SA_FILE).exists():
        return "service_account"
    if (d / CS_FILE).exists():
        return "oauth"
    return "missing"


def _get_creds():
    d = config_dir()
    sa = d / SA_FILE
    if sa.exists():
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_file(
            str(sa), scopes=SCOPES
        )
        creds.refresh(GARequest())
        return creds

    cs = d / CS_FILE
    if cs.exists():
        from google.oauth2.credentials import Credentials
        tok = d / TOKEN_FILE
        creds = None
        if tok.exists():
            creds = Credentials.from_authorized_user_file(str(tok), SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(GARequest())
            else:
                from google_auth_oauthlib.flow import InstalledAppFlow
                flow = InstalledAppFlow.from_client_secrets_file(str(cs), SCOPES)
                creds = flow.run_local_server(port=0)
            tok.write_text(creds.to_json(), encoding="utf-8")
        return creds

    raise DriveError(
        f"Drive 자격증명이 없습니다 — {d} 에 {SA_FILE}(권장) 또는 {CS_FILE}을 두세요."
    )


def upload_pdf(path: Path, name: str, folder_id: str, share_anyone: bool) -> str:
    """PDF 업로드 후 webViewLink 반환. share_anyone이면 '링크 보기' 권한 부여."""
    creds = _get_creds()
    headers = {"Authorization": f"Bearer {creds.token}"}

    # multipart/related 본문 수동 구성 (Drive 업로드 규격)
    boundary = f"ls{uuid.uuid4().hex}"
    meta = json.dumps({"name": name, "parents": [folder_id]}, ensure_ascii=False)
    body = (
        f"--{boundary}\r\n"
        "Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{meta}\r\n"
        f"--{boundary}\r\n"
        "Content-Type: application/pdf\r\n\r\n"
    ).encode("utf-8") + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()

    r = requests.post(
        "https://www.googleapis.com/upload/drive/v3/files",
        params={
            "uploadType": "multipart",
            "fields": "id,webViewLink",
            "supportsAllDrives": "true",
        },
        headers={**headers,
                 "Content-Type": f"multipart/related; boundary={boundary}"},
        data=body, timeout=300,
    )
    if not r.ok:
        raise DriveError(f"업로드 실패 HTTP {r.status_code}: {r.text[:300]}")
    info = r.json()
    file_id, link = info["id"], info.get("webViewLink", "")

    if share_anyone:
        pr = requests.post(
            f"https://www.googleapis.com/drive/v3/files/{file_id}/permissions",
            params={"supportsAllDrives": "true"},
            headers={**headers, "Content-Type": "application/json"},
            json={"role": "reader", "type": "anyone"}, timeout=60,
        )
        if not pr.ok:
            log(f"공유 권한 설정 실패(파일은 업로드됨): {pr.text[:200]}")

    return link or f"https://drive.google.com/file/d/{file_id}/view"


def check_folder(folder_id: str) -> bool:
    """설정 검증용 — 폴더 메타 조회 가능 여부."""
    try:
        creds = _get_creds()
        r = requests.get(
            f"https://www.googleapis.com/drive/v3/files/{folder_id}",
            params={"fields": "id,name", "supportsAllDrives": "true"},
            headers={"Authorization": f"Bearer {creds.token}"}, timeout=30,
        )
        return r.ok
    except Exception:
        return False
