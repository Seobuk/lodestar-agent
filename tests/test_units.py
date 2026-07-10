"""순수 함수 단위 테스트 — 네트워크·Drive 자격증명 불필요.

실행: agent/ 폴더에서  python -m unittest tests.test_units -v
      (또는 python tests/test_units.py)
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import _parse_overlay
from downloader import _candidates_from_landing, normalize_doi, sanitize_filename
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
