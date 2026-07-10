"""Lodestar /api/agent/papers 클라이언트. Bearer lsk_ 토큰 인증."""

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
            "status": "done", "title": title, "fileUrl": file_url, "fileName": file_name,
        })

    def report_failed(self, req_id: str, error: str) -> None:
        self._post({
            "action": "report", "id": req_id, "agentId": self.agent_id,
            "status": "failed", "error": error[:500],
        })
