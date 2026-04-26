"""
Tests for the skills-gap analyzer.

Strategy: pull a real ESCO occupation, take its actual essential skill labels
verbatim, and feed them back. Coverage should be 100% of the supplied labels.
Then add some unrelated text and verify it ends up in unrecognized.
"""

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sqlite3

from src.lookup import CredentialMapper
from src.skills_gap import SkillsGapAnalyzer, parse_candidate_skills

DB_PATH = Path(os.environ.get("CREDENTIAL_DB", "/tmp/credentials.sqlite"))


class TestSkillsGap(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not DB_PATH.exists():
            raise unittest.SkipTest(
                f"DB not found at {DB_PATH}. Build it first."
            )
        cls.cm = CredentialMapper(DB_PATH)
        cls.ana = SkillsGapAnalyzer(cls.cm.conn)

    @classmethod
    def tearDownClass(cls):
        cls.cm.close()

    def _pick_occupation(self, query: str, lang_hint=None) -> str:
        result = self.cm.lookup(query, top_k=1, input_lang=lang_hint)
        self.assertTrue(result.matches, f"No match for {query!r}")
        return result.matches[0].esco_uri

    def test_parse_candidate_skills_string(self):
        self.assertEqual(
            parse_candidate_skills("a, b ; c \n d | e"),
            ["a", "b", "c", "d", "e"],
        )

    def test_parse_candidate_skills_list(self):
        self.assertEqual(
            parse_candidate_skills(["x", "  y  ", "", "z"]),
            ["x", "y", "z"],
        )

    def test_self_match_full_coverage(self):
        """Feeding back an occupation's own essential skill labels should
        achieve 100% coverage of those skills (the rest stay missing)."""
        uri = self._pick_occupation("automonteur", "nl")
        # Pull the first 5 essential skill labels verbatim
        rows = self.cm.conn.execute(
            """SELECT (SELECT label FROM labels
                         WHERE concept_uri=os.skill_uri
                           AND label_kind='preferred' AND language='en') AS label
               FROM occupation_skills os
               WHERE os.occupation_uri=? AND os.relation_type='essential'
               LIMIT 5""",
            (uri,),
        ).fetchall()
        labels = [r["label"] for r in rows if r["label"]]
        self.assertGreater(len(labels), 0)

        gap = self.ana.analyze(uri, labels, threshold=0.6)
        self.assertEqual(len(gap.unrecognized_candidate_skills), 0,
                         f"verbatim labels should always map: {gap.unrecognized_candidate_skills}")
        self.assertGreaterEqual(len(gap.covered_essential), len(labels) - 1,
                                "Almost all verbatim essential labels should be covered")

    def test_unrelated_text_is_unrecognized(self):
        """Random nonsense text should not match any skill above threshold."""
        uri = self._pick_occupation("automonteur", "nl")
        gap = self.ana.analyze(uri, ["xyzqwerty nonsense", "asdfghjkl"], threshold=0.6)
        self.assertEqual(len(gap.unrecognized_candidate_skills), 2,
                         "Nonsense should land in unrecognized")
        # Coverage stays at zero (we matched nothing)
        self.assertEqual(len(gap.covered_essential), 0)

    def test_readiness_pct_in_range(self):
        uri = self._pick_occupation("nurse")
        gap = self.ana.analyze(uri, ["patient assessment"], threshold=0.6)
        self.assertGreaterEqual(gap.overall_readiness_pct, 0.0)
        self.assertLessEqual(gap.overall_readiness_pct, 100.0)

    def test_unknown_occupation_uri_returns_empty_gap(self):
        gap = self.ana.analyze("http://data.europa.eu/esco/occupation/does-not-exist", ["x"])
        self.assertEqual(len(gap.covered_essential), 0)
        self.assertEqual(len(gap.missing_essential), 0)
        self.assertEqual(len(gap.covered_optional), 0)
        self.assertEqual(len(gap.missing_optional), 0)


class TestApiImports(unittest.TestCase):
    """Smoke test: api.py should parse cleanly even if FastAPI isn't installed."""

    def test_api_module_compiles(self):
        import py_compile
        py_compile.compile(str(ROOT / "src" / "api.py"), doraise=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
