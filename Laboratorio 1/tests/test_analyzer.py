from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from analyzer import CompiscriptAnalyzer  # noqa: E402


class AnalyzerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.analyzer = CompiscriptAnalyzer()

    def analyze_example(self, name: str):
        source = (PROJECT / "examples" / name).read_text(encoding="utf-8")
        return self.analyzer.analyze(source)

    def test_complete_program_is_valid(self) -> None:
        result = self.analyze_example("valido_completo.cps")
        self.assertTrue(result.is_valid, result.diagnostics)
        self.assertGreater(result.token_count, 100)

    def test_lexer_recovers_after_multiple_invalid_characters(self) -> None:
        result = self.analyze_example("errores_lexicos.cps")
        self.assertGreaterEqual(result.lexical_count, 3)
        self.assertTrue(any(item.line == 6 for item in result.diagnostics))

    def test_parser_reports_more_than_first_error(self) -> None:
        result = self.analyze_example("errores_sintacticos.cps")
        self.assertGreaterEqual(result.syntactic_count, 4)
        self.assertGreater(len({item.line for item in result.diagnostics}), 2)

    def test_diagnostics_are_localized_and_complete(self) -> None:
        result = self.analyze_example("errores_combinados.cps")
        self.assertFalse(result.is_valid)
        for item in result.diagnostics:
            self.assertIn(item.kind, {"Léxico", "Sintáctico"})
            self.assertGreaterEqual(item.line, 1)
            self.assertGreaterEqual(item.column, 1)
            self.assertTrue(item.symbol)
            self.assertTrue(item.description.endswith("."))
            self.assertNotIn("mismatched input", item.description)
            self.assertNotIn("token recognition error", item.description)

    def test_recovery_terminates_without_duplicate_diagnostics(self) -> None:
        source = "\n".join(f"@{number};" for number in range(40))
        result = self.analyzer.analyze(source)
        lexical = [item for item in result.diagnostics if item.kind == "Léxico"]
        keys = {(item.line, item.column, item.symbol, item.description) for item in lexical}
        self.assertEqual(len(lexical), 40)
        self.assertEqual(len(keys), len(lexical))
        self.assertLess(result.elapsed_ms, 2000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
