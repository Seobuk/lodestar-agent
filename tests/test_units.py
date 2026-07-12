"""순수 함수 단위 테스트 — 네트워크·Drive 자격증명 불필요.

실행: agent/ 폴더에서  python -m unittest tests.test_units -v
      (또는 python tests/test_units.py)
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import _migrate, _parse_overlay
from downloader import (
    CITATION_DOI_RE,
    IFRAME_SRC_RE,
    META_REFRESH_RE,
    _candidates_from_landing,
    normalize_doi,
    sanitize_filename,
)
from setup_gui import _folder_id
from updater import _ver_tuple


class TestNormalizeDoi(unittest.TestCase):
    def test_doi_org_url(self):
        self.assertEqual(
            normalize_doi("https://doi.org/10.1109/TIE.2024.12345"),
            "10.1109/TIE.2024.12345",
        )

    def test_doi_prefix(self):
        self.assertEqual(normalize_doi("doi:10.1000/xyz-abc"), "10.1000/xyz-abc")

    def test_bare_doi_trailing_punct(self):
        # 문장에서 복사해 온 끝 구두점은 떼어낸다.
        self.assertEqual(normalize_doi("10.3390/s24010001."), "10.3390/s24010001")

    def test_not_a_doi(self):
        self.assertIsNone(normalize_doi("https://example.com/paper/123"))

    def test_url_query_not_captured(self):
        # URL 쿼리스트링(&type=… 등)은 DOI 일부가 아니다.
        self.assertEqual(
            normalize_doi(
                "https://journals.plos.org/plosone/article/file"
                "?id=10.1371/journal.pone.0123456&type=printable"
            ),
            "10.1371/journal.pone.0123456",
        )


class TestSanitizeFilename(unittest.TestCase):
    def test_forbidden_chars(self):
        self.assertEqual(
            sanitize_filename('a<b>:c"/d\\e|f?g*h'), "a b c d e f g h"
        )

    def test_length_limit_and_empty(self):
        self.assertEqual(len(sanitize_filename("x" * 300)), 150)
        self.assertEqual(sanitize_filename("???"), "paper")


class TestCandidateUrls(unittest.TestCase):
    def test_ieee_stamp(self):
        cands = _candidates_from_landing(
            "https://ieeexplore.ieee.org/document/9876543", ""
        )
        self.assertIn(
            "https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?tp=&arnumber=9876543",
            cands,
        )

    def test_sciencedirect_pdfft(self):
        cands = _candidates_from_landing(
            "https://www.sciencedirect.com/science/article/pii/S0957415824001234",
            "",
        )
        self.assertIn(
            "https://www.sciencedirect.com/science/article/pii/S0957415824001234"
            "/pdfft?isDTMRedir=true&download=true",
            cands,
        )

    def test_wiley_pdfdirect(self):
        cands = _candidates_from_landing(
            "https://onlinelibrary.wiley.com/doi/10.1002/adma.202400001", ""
        )
        self.assertIn(
            "https://onlinelibrary.wiley.com/doi/pdfdirect/10.1002/adma.202400001"
            "?download=true",
            cands,
        )

    def test_citation_pdf_url_meta_first(self):
        page = '<meta name="citation_pdf_url" content="https://pub.example/x.pdf">'
        cands = _candidates_from_landing("https://pub.example/article/1", page)
        self.assertEqual(cands[0], "https://pub.example/x.pdf")

    def test_mdpi_pdf_suffix(self):
        # MDPI 기사 URL(입력에 DOI 없음)에서 /pdf 후보가 생겨야 한다.
        cands = _candidates_from_landing(
            "https://www.mdpi.com/2218-6581/14/3/28", ""
        )
        self.assertIn("https://www.mdpi.com/2218-6581/14/3/28/pdf", cands)

    def test_mdpi_pdf_suffix_not_doubled(self):
        # 이미 /pdf로 끝나면 다시 붙이지 않는다.
        cands = _candidates_from_landing(
            "https://www.mdpi.com/2218-6581/14/3/28/pdf", ""
        )
        self.assertNotIn("https://www.mdpi.com/2218-6581/14/3/28/pdf/pdf", cands)

    def test_taylor_francis_doi_pdf(self):
        cands = _candidates_from_landing(
            "https://www.tandfonline.com/doi/full/10.1080/17521742.2012.699942", ""
        )
        self.assertIn(
            "https://www.tandfonline.com/doi/pdf/10.1080/17521742.2012.699942",
            cands,
        )

    def test_sage_doi_pdf_from_abs(self):
        cands = _candidates_from_landing(
            "https://journals.sagepub.com/doi/abs/10.1177/0887302X07303626", ""
        )
        self.assertIn(
            "https://journals.sagepub.com/doi/pdf/10.1177/0887302X07303626",
            cands,
        )

    def test_acs_doi_pdf_bare(self):
        cands = _candidates_from_landing(
            "https://pubs.acs.org/doi/10.1021/acs.jctc.4c00001", ""
        )
        self.assertIn(
            "https://pubs.acs.org/doi/pdf/10.1021/acs.jctc.4c00001", cands
        )

    def test_aps_abstract_to_pdf(self):
        cands = _candidates_from_landing(
            "https://journals.aps.org/prl/abstract/10.1103/PhysRevLett.132.010001",
            "",
        )
        self.assertIn(
            "https://journals.aps.org/prl/pdf/10.1103/PhysRevLett.132.010001",
            cands,
        )

    def test_nature_pdf_suffix(self):
        cands = _candidates_from_landing(
            "https://www.nature.com/articles/s41586-024-00001-2", ""
        )
        self.assertIn(
            "https://www.nature.com/articles/s41586-024-00001-2.pdf", cands
        )

    def test_iop_article_pdf(self):
        cands = _candidates_from_landing(
            "https://iopscience.iop.org/article/10.1088/1748-3190/acaa01", ""
        )
        self.assertIn(
            "https://iopscience.iop.org/article/10.1088/1748-3190/acaa01/pdf",
            cands,
        )

    def test_science_family_doi_pdf(self):
        # Science 본지·자매지(Science Robotics/Advances 등) 전부 science.org Atypon.
        for doi in ("10.1126/science.adk0001",
                    "10.1126/scirobotics.adn0002",
                    "10.1126/sciadv.abc0003"):
            cands = _candidates_from_landing(
                f"https://www.science.org/doi/{doi}", ""
            )
            self.assertIn(f"https://www.science.org/doi/pdf/{doi}", cands)

    def test_nature_family_pdf_suffix(self):
        # Nature 본지·자매지·npj 전부 nature.com/articles/{id} → .pdf.
        for aid in ("s41586-024-00001-2",     # Nature
                    "s41467-024-00002-3",     # Nature Communications
                    "s41598-024-00003-4",     # Scientific Reports
                    "s41746-024-00004-5"):    # npj Digital Medicine
            cands = _candidates_from_landing(
                f"https://www.nature.com/articles/{aid}", ""
            )
            self.assertIn(f"https://www.nature.com/articles/{aid}.pdf", cands)

    def test_frontiers_full_to_pdf(self):
        cands = _candidates_from_landing(
            "https://www.frontiersin.org/articles/10.3389/frobt.2024.1500000/full",
            "",
        )
        self.assertIn(
            "https://www.frontiersin.org/articles/10.3389/frobt.2024.1500000/pdf",
            cands,
        )

    def test_biorxiv_full_pdf(self):
        cands = _candidates_from_landing(
            "https://www.biorxiv.org/content/10.1101/2024.01.01.573000v1", ""
        )
        self.assertIn(
            "https://www.biorxiv.org/content/10.1101/2024.01.01.573000v1.full.pdf",
            cands,
        )

    def test_non_publisher_url_no_atypon_rule(self):
        # 임의 도메인의 /doi/ URL을 Atypon 규칙이 잘못 건드리지 않아야 한다.
        cands = _candidates_from_landing(
            "https://example.org/doi/full/10.9999/x.y.z", ""
        )
        self.assertEqual(cands, [])


class TestCitationDoiRecovery(unittest.TestCase):
    def test_extracts_own_doi_from_landing_meta(self):
        # URL 입력일 때 랜딩 페이지의 citation_doi로 DOI를 복구한다.
        page = (
            '<meta name="citation_title" content="A Paper">'
            '<meta name="citation_doi" content="10.3390/robotics14030028">'
        )
        m = CITATION_DOI_RE.search(page)
        self.assertIsNotNone(m)
        self.assertEqual(normalize_doi(m.group(1)), "10.3390/robotics14030028")

    def test_no_citation_doi_meta(self):
        self.assertIsNone(CITATION_DOI_RE.search("<html><body>no meta</body></html>"))


class TestInterstitialFollow(unittest.TestCase):
    def test_meta_refresh_url_extracted(self):
        # MDPI류 다운로드 페이지의 meta-refresh에서 실제 PDF 경로를 뽑는다.
        body = (
            b'<html><head><meta http-equiv="refresh" '
            b'content="0; url=/2218-6581/14/3/28/pdf?version=1700000000">'
            b"</head></html>"
        )
        m = META_REFRESH_RE.search(body)
        self.assertIsNotNone(m)
        self.assertEqual(
            m.group(1).decode(), "/2218-6581/14/3/28/pdf?version=1700000000"
        )

    def test_iframe_src_extracted(self):
        body = b'<html><body><iframe src="/stampPDF/getPDF.jsp?arnumber=1"></iframe>'
        m = IFRAME_SRC_RE.search(body)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1).decode(), "/stampPDF/getPDF.jsp?arnumber=1")


class TestVersionCompare(unittest.TestCase):
    def test_newer(self):
        self.assertGreater(_ver_tuple("v0.2.0"), _ver_tuple("0.1.9"))

    def test_equal_with_prefix(self):
        self.assertEqual(_ver_tuple("v1.2.3"), _ver_tuple("1.2.3"))

    def test_garbage_is_zero(self):
        self.assertEqual(_ver_tuple(""), (0,))


class TestEmbeddedOverlay(unittest.TestCase):
    def test_parse_known_keys_only(self):
        tail = (
            b"MZ\x90\x00 ...exe bytes... "
            b'LSAGENTCFG1:{"lodestar_url": "https://x.app",'
            b' "api_token": "lsk_abc", "junk": 1}'
        )
        self.assertEqual(
            _parse_overlay(tail),
            {"lodestar_url": "https://x.app", "api_token": "lsk_abc"},
        )

    def test_no_marker(self):
        self.assertEqual(_parse_overlay(b"MZ\x90\x00 plain exe"), {})


class TestSaveLocal(unittest.TestCase):
    def test_collision_gets_numbered_name(self):
        import tempfile

        from main import save_local

        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "a.pdf").write_bytes(b"%PDF-old")
            src = d / "incoming.pdf"
            src.write_bytes(b"%PDF-new")
            dest = save_local(src, "a.pdf", dest_dir=d)
            self.assertEqual(dest.name, "a (2).pdf")
            self.assertEqual(dest.read_bytes(), b"%PDF-new")
            self.assertFalse(src.exists())  # move라 원본은 사라져야 함


class TestConfigMigrate(unittest.TestCase):
    def test_old_default_20_becomes_60(self):
        self.assertEqual(_migrate({"poll_interval_sec": 20})["poll_interval_sec"], 60)

    def test_custom_values_kept(self):
        # 사용자가 손으로 넣은 값(20 외)은 건드리지 않는다
        self.assertEqual(_migrate({"poll_interval_sec": 30})["poll_interval_sec"], 30)
        self.assertEqual(_migrate({"poll_interval_sec": 60})["poll_interval_sec"], 60)


class TestRobotIcon(unittest.TestCase):
    def test_draw_sizes_and_visible_pixels(self):
        from robot_icon import draw_humanoid

        for n in (16, 64, 256):
            img = draw_humanoid(n)
            self.assertEqual((img.size, img.mode), ((n, n), "RGBA"))
            # 투명 캔버스에 실제로 그려졌는지 — 불투명 픽셀이 있어야 한다.
            self.assertTrue(any(px[3] > 0 for px in img.getdata()))

    def test_save_ico_multisize(self):
        import tempfile

        from PIL import Image

        from robot_icon import save_ico

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "icon.ico"
            save_ico(str(p))
            with Image.open(p) as ico:
                self.assertEqual(ico.format, "ICO")
                self.assertIn((16, 16), ico.info["sizes"])
                self.assertIn((256, 256), ico.info["sizes"])


class TestFolderIdParse(unittest.TestCase):
    def test_url(self):
        self.assertEqual(
            _folder_id(
                "https://drive.google.com/drive/folders/1AbC_dEf-9?usp=sharing"
            ),
            "1AbC_dEf-9",
        )

    def test_bare_id_passthrough(self):
        self.assertEqual(_folder_id(" 1AbC_dEf-9 "), "1AbC_dEf-9")


if __name__ == "__main__":
    unittest.main(verbosity=2)
