> **이 저장소는 릴리스 호스트입니다.** 소스 원본은 Seobuk/lodestar(private)의
> `agent/` 디렉토리 — 릴리스 전에 그 파일들을 이 저장소 루트로 **동기화(복사·
> 커밋)**한 뒤, Actions 탭에서 **build-release "Run workflow"**(또는 vX.Y.Z 태그
> 푸시)를 실행하면 windows 러너가 exe를 자동 빌드해 릴리스에 첨부한다
> (`.github/workflows/build-release.yml`) — 수동 빌드 불필요.

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
   MDPI·ACM·arXiv) → %PDF 검증 → 업로드(기본: 서버 경유 팀 Drive, 링크 자동)
```

---

## A. Lodestar 서버 쪽 (이미 적용됨)

서버 쪽(`PaperRequest` 모델, `/api/papers`, `/api/agent/papers`, `/papers` 페이지)은
Lodestar repo에 포함돼 있다. 필요한 것은 **토큰 하나**: Lodestar 로그인 →
`/token` 페이지 → 새 토큰 발급(라벨: "학교 PC") → `lsk_...` 값을 아래 마법사에 입력.

## B. 학교 PC 에이전트 설치

### 1) 저장 방식 — 기본은 "서버 업로드" (자격증명·Drive 설정 전부 불필요)
기본값(마법사 체크박스 "PDF를 팀 Drive로 업로드")은 **서버 업로드 모드**다:
에이전트가 이미 갖고 있는 `lsk_` 토큰으로 Lodestar 서버에 업로드 세션을
요청하면, 서버가 소유자 팀 Drive 첨부 폴더 아래 **"논문" 하위 폴더**(없으면
자동 생성)에 세션을 열어 주고(부모 폴더는 서버가 강제) 에이전트는 그 URL로
PDF를 직접 올린다 — 어느 PC의 에이전트든 같은 폴더에 모인다. `/papers` 카드에는
**팀 로그인 전용 다운로드 링크**(`/api/attachments/...`)가 자동으로 뜬다 —
공개 링크가 아니라서 구독 논문 PDF도 출판사 약관상 안전한 쪽이다.

서버 요구사항은 위키 첨부 기능과 동일(`DRIVE_ATTACH_FOLDER_ID` + CF 프록시
env + 소유자 Drive 연결)이고 이미 운영 중이므로 **추가 설정이 없다**. 서버
쪽이 미설정이거나 일시 장애면 아래 exe 폴더 저장으로 자동 폴백된다.

<details>
<summary>(옵트아웃) exe 폴더 저장 — 체크박스를 끈 경우</summary>

받은 PDF를 **exe가 있는 폴더**에 저장한다. **exe를 구글 드라이브 데스크톱의
동기화 폴더에 넣어두면** 별도 API·자격증명 없이 자동으로 드라이브에 올라간다.
단 `/papers` 카드에 링크는 뜨지 않는다(파일명만 안내).
</details>

<details>
<summary>(고급) 직접 Drive API 업로드 모드 — 마법사에서 폴더를 지정한 경우만</summary>

자기 소유 폴더에 직접 올리고 싶을 때만. 폴더를 지정하면 서버 업로드보다
우선한다.

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
있다. 받은 exe를 실행하면 마법사에 전부 미리 채워져 있으니 "저장 후 검증"만
누르면 끝(기본 서버 업로드 모드라 어디에 두든 상관없다).
**exe 방식(배포용)**: `agent/`에서 `build.bat` → `dist\LodestarAgent.exe` 실행
**Python 방식(바로 시험)**:
```bat
cd agent
pip install -r requirements.txt
python main.py
```

최초 실행 시 설정 마법사가 뜬다: Lodestar URL / `lsk_` 토큰 / 팀 Drive 서버
업로드(기본 on — 링크 자동) / Drive 폴더 URL(고급 — 직접 업로드용) /
공개링크 여부(직접 모드) / 부팅 자동시작.
**저장 후 검증**이 토큰과 업로드 모드(서버 가용성 또는 폴더 접근권한)를
즉시 확인해 준다.
이후 우하단 트레이 아이콘(휴머노이드 로봇)으로 상주하며 상태 확인, **저장
모드 전환**(팀 Drive 업로드 ↔ exe 폴더 저장 — 재시작 없이 다음 건부터 적용),
로그 보기, 업데이트 확인, 자동시작 토글, 종료가 가능하다. exe 아이콘도 같은
로봇(빌드 시 `robot_icon.py`가 `icon.ico` 생성).

- 부팅 자동시작: HKCU Run 키(관리자 권한 불필요), 마법사 체크박스로 on/off
- 로그: `%APPDATA%\LodestarAgent\agent.log`

### 3) 집 PC (선택)
같은 방법으로 설치하면 **백업 에이전트**가 된다. claim이 원자적이라 한 요청을
두 대가 중복 처리하는 일은 없다 — 학교 PC가 꺼져 있으면 집 PC가 OA/arXiv
논문이라도 처리해 준다.

## C. 자동 업데이트 배포 (집에서 → 학교 PC)

1. `agent/version.py`의 `VERSION` 올리기 (예: `0.2.1`)
2. `build.bat`으로 `LodestarAgent.exe` 빌드
3. GitHub `Seobuk/lodestar-agent` 저장소(public)에 **Release 태그 `v0.2.1`**
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
