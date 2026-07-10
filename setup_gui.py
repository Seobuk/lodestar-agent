"""최초 실행 설정 마법사. Tkinter 폼(없으면 콘솔 입력 폴백).

입력 항목: Lodestar URL / lsk_ 토큰 / Drive 폴더(URL 또는 ID) / 공개링크 여부 /
Unpaywall 이메일(선택) / 부팅 자동시작. 저장 시 토큰·폴더 접근을 즉시 검증한다.
"""

import re
import webbrowser

import autostart
import config as C
from gdrive import check_folder, credentials_status
from lodestar_api import Lodestar

FOLDER_RE = re.compile(r"folders/([\w\-]+)")


def _folder_id(text: str) -> str:
    text = text.strip()
    m = FOLDER_RE.search(text)
    return m.group(1) if m else text


def _apply(cfg: dict) -> None:
    C.save(cfg)
    if cfg.get("autostart"):
        try:
            autostart.enable()
        except Exception:
            pass
    else:
        autostart.disable()


def _validate(cfg: dict) -> list[str]:
    msgs = []
    try:
        ok = Lodestar(cfg["lodestar_url"], cfg["api_token"], cfg["agent_id"]).ping()
        msgs.append("Lodestar 토큰: OK" if ok else "Lodestar 토큰: 실패(401)")
    except Exception as e:
        msgs.append(f"Lodestar 접속 실패: {e}")
    st = credentials_status()
    if st == "missing":
        msgs.append(f"Drive 자격증명 없음 → {C.config_dir()} 에 service_account.json 배치 필요")
    else:
        msgs.append("Drive 폴더 접근: OK" if check_folder(cfg["gdrive_folder_id"])
                    else "Drive 폴더 접근 실패 — 폴더를 SA 이메일에 공유했는지 확인")
    return msgs


def run_wizard() -> dict:
    cfg = C.load()
    try:
        import tkinter as tk
        from tkinter import messagebox
    except Exception:
        return _console_wizard(cfg)

    root = tk.Tk()
    root.title("Lodestar Agent 설정")
    root.geometry("560x360")
    root.resizable(False, False)

    fields = [
        ("Lodestar URL", "lodestar_url", "https://lodestar-…vercel.app"),
        ("API 토큰 (lsk_…)", "api_token", "/token 페이지에서 발급"),
        ("Drive 폴더 URL/ID", "gdrive_folder_id", "https://drive.google.com/drive/folders/…"),
        ("Unpaywall 이메일(선택)", "unpaywall_email", "OA 폴백용"),
    ]
    entries = {}
    for i, (label, key, ph) in enumerate(fields):
        tk.Label(root, text=label).grid(row=i, column=0, sticky="e",
                                        padx=(14, 6), pady=6)
        e = tk.Entry(root, width=50)
        e.insert(0, str(cfg.get(key, "")))
        e.grid(row=i, column=1, sticky="w", pady=6)
        if not cfg.get(key):
            e.insert(0, "")
        entries[key] = e
        tk.Label(root, text=ph, fg="#888").grid(row=i, column=1, sticky="w",
                                                padx=(0, 0), pady=(38, 0))

    share_var = tk.BooleanVar(value=bool(cfg.get("share_anyone", True)))
    auto_var = tk.BooleanVar(value=bool(cfg.get("autostart", True)))
    tk.Checkbutton(root, text="업로드 후 '링크 있는 사람 보기' 공유",
                   variable=share_var).grid(row=4, column=1, sticky="w")
    tk.Checkbutton(root, text="Windows 부팅 시 자동 시작",
                   variable=auto_var).grid(row=5, column=1, sticky="w")

    status = tk.Label(root, text=f"자격증명 폴더: {C.config_dir()}", fg="#555",
                      justify="left", wraplength=520)
    status.grid(row=6, column=0, columnspan=2, sticky="w", padx=14, pady=(8, 0))

    def open_dir():
        webbrowser.open(str(C.config_dir()))

    def save():
        for key, e in entries.items():
            cfg[key] = e.get().strip()
        cfg["gdrive_folder_id"] = _folder_id(cfg["gdrive_folder_id"])
        cfg["share_anyone"] = share_var.get()
        cfg["autostart"] = auto_var.get()
        if not C.is_configured(cfg):
            messagebox.showwarning("입력 부족", "URL·토큰·폴더는 필수입니다.")
            return
        _apply(cfg)
        msgs = _validate(cfg)
        status.config(text="\n".join(msgs))
        if all(("OK" in m) for m in msgs):
            messagebox.showinfo("완료", "설정 저장·검증 완료. 에이전트를 시작합니다.")
            root.destroy()

    tk.Button(root, text="설정 폴더 열기", command=open_dir)\
        .grid(row=7, column=0, padx=14, pady=14, sticky="w")
    tk.Button(root, text="저장 후 검증", command=save, width=16)\
        .grid(row=7, column=1, pady=14, sticky="e", padx=(0, 14))

    root.mainloop()
    return C.load()


def _console_wizard(cfg: dict) -> dict:
    print(f"[설정] 자격증명 폴더: {C.config_dir()} (service_account.json 배치)")
    for key, prompt in [("lodestar_url", "Lodestar URL"),
                        ("api_token", "API 토큰(lsk_)"),
                        ("gdrive_folder_id", "Drive 폴더 URL/ID"),
                        ("unpaywall_email", "Unpaywall 이메일(선택)")]:
        cur = cfg.get(key, "")
        v = input(f"{prompt} [{cur}]: ").strip()
        if v:
            cfg[key] = v
    cfg["gdrive_folder_id"] = _folder_id(cfg["gdrive_folder_id"])
    _apply(cfg)
    for m in _validate(cfg):
        print(" -", m)
    return cfg
