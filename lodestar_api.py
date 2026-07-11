"""Lodestar /api/agent/papers 클라이언트. Bearer lsk_ 토큰 인증."""

from pathlib import Path

import requests


class LodestarError(Exception):
    pass


class Lodestar:
    def __init__(self, base_url: str, token: str, agent_id: str):
        self.base = base_url.rstrip("/")
        self.agent_id = agent_id
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"Bearer {token}"

    def _post(self, payload: dict) -> dict:
        r = self.s.post(f"{self.base}/api/agent/papers", json=payload, timeout=30)
        if r.status_code == 401:
            raise LodestarError("토큰 인증 실패(401) — /token에서 재발급 필요")
        r.raise_for_status()
        return r.json()

    def ping(self) -> bool:
        """설정 검증용 — 토큰이 살아 있으면 True."""
        r = self.s.get(f"{self.base}/api/agent/papers", timeout=15)
        return r.status_code == 200

    def pending(self) -> list[dict]:
        r = self.s.get(f"{self.base}/api/agent/papers", timeout=30)
        if r.status_code == 401:
            raise LodestarError("토큰 인증 실패(401)")
        r.raise_for_status()
        return r.json().get("items", [])

    def claim(self, req_id: str) -> bool:
        return bool(
            self._post({"action": "claim", "id": req_id, "agentId": self.agent_id}).get("ok")
        )

    def report_done(self, req_id: str, title: str, file_url: str, file_name: str) -> None:
        self._post({
            "action": "report", "id": req_id, "agentId": self.agent_id,
            "status": "done", "title": title,
            "fileUrl": file_url or None,  # 로컬 저장 모드면 링크 없음
            "fileName": file_name,
        })

    def report_failed(self, req_id: str, error: str) -> None:
        self._post({
            "action": "report", "id": req_id, "agentId": self.agent_id,
            "status": "failed", "error": error[:500],
        })

    # ---------- 서버 업로드 모드(기본) — GCP 자격증명 없이 lsk_ 토큰만으로 ----------

    def server_upload_status(self) -> tuple[bool, str]:
        """설정 검증용 — 서버 업로드 모드 사용 가능 여부와 불가 사유."""
        r = self.s.get(f"{self.base}/api/agent/papers/upload-session", timeout=15)
        if r.status_code == 401:
            raise LodestarError("토큰 인증 실패(401)")
        r.raise_for_status()
        j = r.json()
        return bool(j.get("ok")), str(j.get("reason") or "")

    def upload_pdf_via_server(self, path: Path, name: str) -> str:
        """PDF를 소유자 팀 Drive(첨부 폴더)에 올리고 팀 전용 다운로드 링크를 반환.

        세션 생성만 서버가 하고(부모 폴더 서버 강제), 바이트는 반환된 구글
        세션 URL로 직접 PUT한다 — 세션 URL 자체가 자격증명이라 토큰 불필요.
        """
        size = path.stat().st_size
        r = self.s.post(
            f"{self.base}/api/agent/papers/upload-session",
            json={"name": name, "size": size}, timeout=30,
        )
        if r.status_code == 401:
            raise LodestarError("토큰 인증 실패(401) — /token에서 재발급 필요")
        if not r.ok:
            try:
                reason = r.json().get("error", "")
            except Exception:
                reason = r.text[:200]
            raise LodestarError(f"업로드 세션 생성 실패 HTTP {r.status_code}: {reason}")
        session_url = r.json().get("sessionUrl", "")
        if not session_url:
            raise LodestarError("업로드 세션 URL이 없습니다")

        # 구글 세션에 lsk_ 토큰이 새지 않게 self.s(공용 세션) 대신 bare PUT.
        with path.open("rb") as f:
            up = requests.put(
                session_url, data=f,
                headers={"Content-Type": "application/pdf"}, timeout=900,
            )
        if up.status_code not in (200, 201):
            raise LodestarError(f"Drive 업로드 실패 HTTP {up.status_code}: {up.text[:200]}")
        file_id = up.json().get("id", "")
        if not file_id:
            raise LodestarError("업로드 응답에 파일 id가 없습니다")
        return f"{self.base}/api/attachments/{file_id}"
