# Lodestar Paper Pipeline

어디서든 Lodestar `/papers`에 DOI·URL을 넣으면, **학교 PC의 상주 에이전트**가
기관 네트워크로 PDF를 받아 **Google Drive 지정 폴더**에 올리고 링크를 회신한다.

```
[아무 기기: Lodestar /papers 페이지]
        │  DOI/URL 입력 → PaperRequest(pending)
        ▼
[Lodestar API]  /api/agent/papers  (Bearer lsk_ 토큰, 기존 토큰 시스템 재사용)
        ▲  20초 폴링 · 원자적 claim          │ done + Drive 링크 회신
        │                                    ▼
[학교 PC: LodestarAgent (트레이 상주, 부팅 자동시작, GitHub Releases 자동 업데이트)]
   DOI 해석 → citation_pdf_url/퍼블리셔 규칙(IEEE·ScienceDirect·Wiley·Springer·
   MDPI·ACM·arXiv) → %PDF 검증 → Drive 업로드 → (선택) 링크 공유
```

---

## A. Lodestar 서버 쪽 (이미 적용됨)

서버 쪽(`PaperRequest` 모델, `/api/papers`, `/api/agent/papers`, `/papers` 페이지)은
Lodestar repo에 포함돼 있다. 필요한 것은 **토큰 하나**: Lodestar 로그인 →
`/token` 페이지 → 새 토큰 발급(라벨: "학교 PC") → `lsk_...` 값을 아래 마법사에 입력.

## B. 학교 PC 에이전트 설치

### 1) 저장 방식 — 기본은 "exe 폴더에 저장" (Drive 설정 불필요)
받은 PDF는 기본적으로 **exe가 있는 폴더**에 저장된다. 그래서 **exe를 구글
드라이브 데스크톱의 동기화 폴더에 넣어두면** 별도 API·자격증명 없이 자동으로
드라이브에 올라간다 — 이것이 권장 방식이다.

<details>
<summary>(선택) Drive API 업로드 모드 — 마법사에서 폴더를 지정한 경우만</summary>

1. [GCP 콘솔] 프로젝트 선택 → **Drive API 사용 설정**
2. IAM → 서비스 계정 → 새로 만들기 → 키(JSON) 다운로드
3. 다운로드한 JSON을 `%APPDATA%\LodestarAgent\service_account.json` 으로 저장
4. **대상 Drive 폴더를 SA 이메일(…@…iam.gserviceaccount.com)에 '편집자'로 공유**

> 일반 OAuth를 쓰려면 대신 `client_secret.json`(데스크톱 앱)을 같은 폴더에
> 두면 최초 1회 브라우저 로그인 후 자동 갱신된다.
</details>

### 2) 실행
**가장 쉬운 방법(토큰 내장 exe)**: Lodestar `/token`에서 토큰 발급 직후
**"에이전트 exe (토큰 내장)"** 버튼 — 서버 주소·토큰이 exe 꼬리에 심어져
있다. 받은 exe를 **구글 드라이브 동기 폴더에 넣고** 실행하면 마법사에 전부
미리 채워져 있으니 "저장 후 검증"만 누르면 끝.
**exe 방식(배포용)**: `agent/`에서 `build.bat` → `dist\LodestarAgent.exe` 실행
**Python 방식(바로 시험)**:
```bat
cd agent
pip install -r requirements.txt
python main.py
```

최초 실행 시 설정 마법사가 뜬다: Lodestar URL / `lsk_` 토큰 / Drive 폴더
URL(선택 — 비우면 exe 폴더 저장) / 공개링크 여부 / 부팅 자동시작.
**저장 후 검증**이 토큰(과 폴더를 지정했다면 접근권한)을 즉시 확인해 준다.
이후 트레이 아이콘(별 모양)으로 상주하며 상태 확인, 로그 보기, 업데이트 확인,
자동시작 토글이 가능하다.

- 부팅 자동시작: HKCU Run 키(관리자 권한 불필요), 마법사 체크박스로 on/off
- 로그: `%APPDATA%\LodestarAgent\agent.log`

### 3) 집 PC (선택)
같은 방법으로 설치하면 **백업 에이전트**가 된다. claim이 원자적이라 한 요청을
두 대가 중복 처리하는 일은 없다 — 학교 PC가 꺼져 있으면 집 PC가 OA/arXiv
논문이라도 처리해 준다.

## C. 자동 업데이트 배포 (집에서 → 학교 PC)

1. `agent/version.py`의 `VERSION` 올리기 (예: `0.1.1`)
2. `build.bat`으로 `LodestarAgent.exe` 빌드
3. GitHub `Seobuk/lodestar-agent` 저장소(public)에 **Release 태그 `v0.1.1`**
   생성, exe를 자산으로 첨부
4. 학교 PC 에이전트가 부팅 시 + 6시간마다 확인 → 스스로 교체 후 재시작
   (트레이 "업데이트 확인"으로 즉시 적용도 가능)

저장소 이름을 바꾸려면 `%APPDATA%\LodestarAgent\config.json`의
`github_repo` 값을 수정.

## 참고

- 다운로드 성공률: `citation_pdf_url` 메타 + 퍼블리셔 규칙으로 주요 저널
  대부분 커버. 일부 사이트(강한 봇 차단·세션 요구)는 `failed`가 뜰 수 있고,
  웹에서 **재시도** 버튼 또는 수동 다운로드로 처리. 실패 사유는 카드에 표시됨.
- `unpaywall_email`을 넣어두면 구독이 없는 논문도 OA 사본으로 폴백.
- 공유 링크는 "링크가 있는 사람 보기" 수준 — 구독 논문 PDF는 개인 연구용
  접근에 한정하고 링크를 외부에 재배포하지 않는 것이 출판사 약관상 안전하다.
