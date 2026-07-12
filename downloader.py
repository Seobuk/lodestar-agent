"""DOI/URL → PDF 다운로드.

전략(순서대로 시도, 첫 성공에서 종료):
  1) arXiv — 직행
  2) DOI → doi.org 리다이렉트로 퍼블리셔 랜딩 페이지 →
     <meta name="citation_pdf_url"> (대부분 퍼블리셔가 제공) + 도메인별 특수 규칙.
       - IEEE stampPDF, Elsevier(ScienceDirect) pdfft, Wiley pdfdirect,
         Springer content/pdf, MDPI /pdf, ACM /doi/pdf
       - Atypon/Literatum(/doi/pdf/{DOI}): Taylor&Francis, SAGE, ACS,
         英왕립학회, Science(AAAS), PNAS, SIAM, AMS, ASME
       - APS(Physical Review), Nature(.pdf), IOP(/pdf), Frontiers(/pdf),
         Emerald, bioRxiv·medRxiv(.full.pdf), JSTOR
       - Oxford·AIP·Cambridge·RSC 등 토큰형 PDF는 citation_pdf_url에 의존
     PDF 대신 HTML 인터스티셜(<iframe>·<meta refresh>)이 오면 그 안의
     실제 PDF 링크를 추적한다(MDPI 다운로드 페이지 등).
  3) Unpaywall OA 폴백 (unpaywall_email 설정 시)

URL로 들어와 입력에 DOI가 없을 때는 랜딩 페이지의 citation_doi 메타에서
DOI를 복구해 3)의 OA 폴백과 파일명 메타(Crossref)를 살린다.

기관 IP(학교/연구소 네트워크)에서 실행되어야 구독 논문이 열린다.
응답 첫 바이트가 %PDF 인지 반드시 검증한다.
"""

import html
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

DOI_RE = re.compile(r"(?:doi\.org/|doi:\s*)?(10\.\d{4,9}/[^\s\"'<>]+)", re.I)

# 랜딩 페이지에서 논문 자신의 DOI(참고문헌 DOI가 아니라) 메타.
CITATION_DOI_RE = re.compile(
    r'<meta[^>]+name=["\']citation_doi["\'][^>]+content=["\']([^"\']+)',
    re.I,
)
# HTML 인터스티셜의 실제 PDF 링크: IEEE stampPDF는 <iframe>,
# MDPI 등 일부 퍼블리셔의 다운로드 페이지는 <meta http-equiv=refresh>.
IFRAME_SRC_RE = re.compile(rb'<iframe[^>]+src=["\']([^"\']+)', re.I)
META_REFRESH_RE = re.compile(
    rb'<meta[^>]+http-equiv=["\']?refresh["\']?[^>]+'
    rb'content=["\'][^"\';]*;\s*url=([^"\'>\s]+)',
    re.I,
)


class DownloadError(Exception):
    pass


def normalize_doi(text: str) -> str | None:
    m = DOI_RE.search(text.strip())
    if not m:
        return None
    # URL 속 DOI 뒤의 쿼리·프래그먼트(?type=…, &x=…, #sec)는 DOI가 아니다.
    return re.split(r"[?#&]", m.group(1))[0].rstrip(").,;")


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "text/html,application/pdf,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
    })
    return s


def _is_pdf(resp: requests.Response) -> bool:
    head = resp.content[:5] if resp.content else b""
    return head.startswith(b"%PDF")


def _try_pdf(s: requests.Session, url: str, referer: str | None,
             _depth: int = 0) -> bytes | None:
    """url을 PDF로 시도. 응답이 PDF가 아니라 HTML 인터스티셜이면 그 안의
    실제 PDF 링크(IEEE stampPDF의 <iframe>, MDPI 등 다운로드 페이지의
    <meta http-equiv=refresh>)를 최대 2회까지 추적한다."""
    try:
        h = {"Referer": referer} if referer else {}
        r = s.get(url, headers=h, timeout=90, allow_redirects=True)
        if not r.ok:
            return None
        if _is_pdf(r):
            return r.content
        if _depth >= 2:
            return None
        body = r.content[:8000]
        m = IFRAME_SRC_RE.search(body) or META_REFRESH_RE.search(body)
        if m:
            nxt = html.unescape(m.group(1).decode("utf-8", "replace"))
            inner = requests.compat.urljoin(r.url, nxt)
            if inner != r.url:  # 자기 자신으로 도는 리프레시는 무한루프
                return _try_pdf(s, inner, r.url, _depth + 1)
    except requests.RequestException:
        pass
    return None


def _candidates_from_landing(final_url: str, page: str) -> list[str]:
    """랜딩 페이지 HTML에서 PDF 후보 URL 목록(우선순위순)."""
    cands: list[str] = []

    # 표준: Google Scholar용 citation_pdf_url 메타 (대부분 퍼블리셔 제공)
    for m in re.finditer(
        r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)',
        page, re.I,
    ):
        cands.append(html.unescape(m.group(1)))

    u = final_url
    if "ieeexplore.ieee.org" in u:
        m = re.search(r"(?:document|abstract/document)/(\d+)", u) or \
            re.search(r"arnumber=(\d+)", u)
        if m:
            cands.append(
                f"https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber={m.group(1)}"
            )
    if "sciencedirect.com" in u:
        m = re.search(r"/pii/([A-Z0-9]+)", u, re.I)
        if m:
            cands.append(
                f"https://www.sciencedirect.com/science/article/pii/{m.group(1)}/pdfft?isDTMRedir=true&download=true"
            )
    if "onlinelibrary.wiley.com" in u and "/doi/" in u:
        cands.append(re.sub(r"/doi/(epdf/|abs/|full/)?", "/doi/pdfdirect/", u) + "?download=true")
    if "link.springer.com" in u:
        m = re.search(r"(?:article|chapter)/(10\.\d{4,9}/[^?#]+)", u)
        if m:
            cands.append(f"https://link.springer.com/content/pdf/{m.group(1)}.pdf")
    if "mdpi.com" in u and not u.rstrip("/").endswith("/pdf"):
        cands.append(u.rstrip("/") + "/pdf")
    if "dl.acm.org" in u:
        m = re.search(r"/doi/(?:abs/|full/)?(10\.\d{4,9}/[^?#]+)", u)
        if m:
            cands.append(f"https://dl.acm.org/doi/pdf/{m.group(1)}")

    host = urlparse(u).netloc.lower()
    # URL 경로에 박힌 논문 DOI(대부분 Atypon/Literatum 계열이 이렇게 노출).
    md = re.search(r"/(10\.\d{4,9}/[^?#]+)", u)
    url_doi = md.group(1).rstrip("/") if md else None

    # Atypon/Literatum 플랫폼(대형 구독 출판사 다수) — /doi/…/{DOI} → /doi/pdf/{DOI}.
    # T&F·SAGE·ACS·英왕립학회·PNAS, 그리고 Science 계열 전체(본지·Science
    # Robotics·Advances·Immunology 등 자매지 모두 science.org)가 같은 규칙.
    ATYPON = ("tandfonline.com", "journals.sagepub.com", "pubs.acs.org",
              "royalsocietypublishing.org", "science.org", "www.pnas.org",
              "pnas.org", "epubs.siam.org", "journals.ametsoc.org",
              "asmedigitalcollection.asme.org")
    if any(host.endswith(h) for h in ATYPON):
        if re.search(r"/doi/(?:abs/|full/|epdf/|epub/|reader/)?10\.", u):
            cands.append(
                re.sub(r"/doi/(?:abs/|full/|epdf/|epub/|reader/)?", "/doi/pdf/",
                       u.split("#")[0].split("?")[0])
            )
        elif url_doi:
            cands.append(f"https://{host}/doi/pdf/{url_doi}")

    # APS(Physical Review): /{jcode}/abstract/10.1103/… → /{jcode}/pdf/10.1103/…
    if "journals.aps.org" in host:
        m = re.search(r"/([a-z]+)/(?:abstract|accepted|cited-by)/(10\.\d{4,9}/[^?#]+)", u)
        if m:
            cands.append(f"https://journals.aps.org/{m.group(1)}/pdf/{m.group(2)}")

    # Nature 계열 전체(본지·Nature Communications·Scientific Reports·npj 등
    # 모든 자매지가 nature.com/articles/{id}): → /articles/{id}.pdf
    if host.endswith("nature.com"):
        m = re.search(r"/articles/([^/?#]+)", u)
        if m and not m.group(1).endswith(".pdf"):
            cands.append(f"https://{host}/articles/{m.group(1)}.pdf")

    # IOP Science: /article/10.1088/… → /article/10.1088/…/pdf
    if "iopscience.iop.org" in host:
        m = re.search(r"/article/(10\.\d{4,9}/[^?#]+)", u)
        if m:
            cands.append(f"https://iopscience.iop.org/article/{m.group(1).rstrip('/')}/pdf")

    # Frontiers: /articles/{DOI}(/full) → /articles/{DOI}/pdf
    if "frontiersin.org" in host and "/articles/" in u:
        base = u.split("#")[0].split("?")[0].rstrip("/")
        if base.endswith("/full"):
            base = base[:-len("/full")]
        if not base.endswith("/pdf"):
            cands.append(base + "/pdf")

    # Emerald Insight: /insight/content/doi/{DOI}/full/(html) → …/full/pdf
    if "emerald.com" in host and url_doi:
        cands.append(f"https://www.emerald.com/insight/content/doi/{url_doi}/full/pdf")

    # bioRxiv/medRxiv 프리프린트: /content/10.1101/… → ….full.pdf
    if host.endswith("biorxiv.org") or host.endswith("medrxiv.org"):
        base = u.split("#")[0].split("?")[0].rstrip("/")
        base = re.sub(r"\.(full|abstract|article-info|article-metrics)$", "", base)
        if not base.endswith(".full.pdf"):
            cands.append(base + ".full.pdf")

    # JSTOR: /stable/{id} → /stable/pdf/{id}.pdf (강한 봇차단이라 실패할 수 있음)
    if "jstor.org" in host:
        m = re.search(r"/stable/(?:pdf/)?([^/?#]+?)(?:\.pdf)?$", u)
        if m:
            cands.append(f"https://www.jstor.org/stable/pdf/{m.group(1)}.pdf")

    # 중복 제거(순서 유지)
    seen, out = set(), []
    for c in cands:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _crossref_meta(doi: str) -> dict:
    """제목/연도/제1저자 — 파일명용. 실패해도 치명적이지 않음."""
    try:
        r = requests.get(f"https://api.crossref.org/works/{doi}",
                         headers={"User-Agent": UA}, timeout=20)
        if not r.ok:
            return {}
        msg = r.json().get("message", {})
        title = (msg.get("title") or [""])[0]
        year = ""
        for k in ("published-print", "published-online", "issued", "created"):
            dp = (msg.get(k) or {}).get("date-parts")
            if dp and dp[0] and dp[0][0]:
                year = str(dp[0][0])
                break
        family = ""
        for a in msg.get("author") or []:
            if a.get("family"):
                family = a["family"]
                break
        return {"title": title, "year": year, "family": family}
    except Exception:
        return {}


def _unpaywall_pdf(doi: str, email: str) -> str | None:
    if not email:
        return None
    try:
        r = requests.get(f"https://api.unpaywall.org/v2/{doi}",
                         params={"email": email}, timeout=20)
        if r.ok:
            loc = r.json().get("best_oa_location") or {}
            return loc.get("url_for_pdf") or loc.get("url")
    except Exception:
        pass
    return None


def sanitize_filename(name: str, limit: int = 150) -> str:
    name = unicodedata.normalize("NFKC", name)
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return (name[:limit] or "paper")


def fetch_pdf(user_input: str, workdir: Path, unpaywall_email: str = "") -> dict:
    """반환: {path, file_name, title, doi}. 실패 시 DownloadError."""
    s = _session()
    doi = normalize_doi(user_input)
    start_url = f"https://doi.org/{doi}" if doi else user_input.strip()

    # 1) arXiv 직행
    aid = None
    ax = re.search(r"arxiv\.org/(?:abs|pdf)/([\w.\-/]+?)(?:v\d+)?(?:\.pdf)?$",
                   start_url, re.I)
    if ax:
        aid = ax.group(1)
    elif doi and doi.lower().startswith("10.48550/arxiv."):
        aid = doi[len("10.48550/arxiv."):]
    if aid:
        pdf = _try_pdf(s, f"https://arxiv.org/pdf/{aid}", None)
        if pdf:
            fname = sanitize_filename(f"arXiv_{aid}") + ".pdf"
            path = workdir / fname
            path.write_bytes(pdf)
            return {"path": path, "file_name": fname,
                    "title": f"arXiv:{aid}", "doi": doi or ""}

    # 2) 랜딩 페이지 → 후보 PDF들
    landing_url, page = start_url, ""
    try:
        r = s.get(start_url, timeout=90, allow_redirects=True)
        landing_url = r.url
        if r.ok and _is_pdf(r):  # 드물게 DOI가 바로 PDF로 감
            page, pdf_direct = "", r.content
        else:
            page, pdf_direct = (r.text if r.ok else ""), None
    except requests.RequestException as e:
        raise DownloadError(f"랜딩 페이지 접속 실패: {e}") from e

    # URL로 들어왔으면(입력에 DOI가 없으면) 랜딩 페이지의 citation_doi 메타에서
    # 논문 DOI를 복구한다. 이래야 아래 Unpaywall OA 폴백과 Crossref 파일명
    # 메타가 URL 입력(예: MDPI 기사 링크)에서도 살아난다.
    if not doi and page:
        dm = CITATION_DOI_RE.search(page)
        if dm:
            doi = normalize_doi(dm.group(1))

    pdf = pdf_direct
    if not pdf:
        for cand in _candidates_from_landing(landing_url, page):
            pdf = _try_pdf(s, requests.compat.urljoin(landing_url, cand), landing_url)
            if pdf:
                break

    # 3) Unpaywall 폴백
    if not pdf and doi:
        oa = _unpaywall_pdf(doi, unpaywall_email)
        if oa:
            pdf = _try_pdf(s, oa, None)

    if not pdf:
        raise DownloadError(
            "PDF를 찾지 못했습니다 — 기관 네트워크·구독 범위 확인 또는 수동 다운로드 필요"
        )

    # 파일명: {연도}_{제1저자}_{제목}.pdf (Crossref), 없으면 <title>/입력값
    meta = _crossref_meta(doi) if doi else {}
    title = meta.get("title") or ""
    if not title:
        m = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
        title = html.unescape(m.group(1)).strip() if m else user_input
    parts = [p for p in (meta.get("year", ""), meta.get("family", ""), title) if p]
    fname = sanitize_filename("_".join(parts) or "paper") + ".pdf"
    path = workdir / fname
    path.write_bytes(pdf)
    return {"path": path, "file_name": fname, "title": title, "doi": doi or ""}
